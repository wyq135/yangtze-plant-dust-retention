"""
知网批量下载器 v2 — 原始CDP WebSocket + requests下载

用法：
  1. 关闭所有Edge窗口
  2. 终端执行: "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222
  3. 在打开的Edge中登录知网 (https://kns.cnki.net/)
  4. 运行本脚本: python .claude/cnki_downloader.py [CSV文件路径]
     默认读取 .claude/batch1_precise_screened_20260620_2118.csv

原理: CDP直连真实Edge（含登录态、浏览器指纹）。
搜索→提取下载直链→Cookie同步→requests静默下载，完全免疫webdriver检测。
"""

import asyncio
import sys
import json
import os
import re
import time
import random
from datetime import datetime
from urllib.parse import quote
from pathlib import Path
import csv

import aiohttp
import requests

# ==================== 配置 ====================
CDP_BASE = "http://localhost:9222"
DOWNLOAD_DIR = os.path.expanduser("~/Desktop/2026/references/downloaded/_待提取")
LOG_FILE = ".claude/download_log.jsonl"
DELAY_BETWEEN_PAPERS = (3, 7)   # 论文间随机延迟(秒)
MAX_RETRIES = 2                  # 下载重试次数
PAGE_LOAD_WAIT = 4               # CNKI页面加载等待(秒)

# ==================== 辅助函数 ====================

def load_papers(csv_path):
    """加载论文清单，筛选 has_data=True 的论文"""
    papers = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            has_data = row.get('has_data', '').strip().lower()
            if has_data in ('true', 'yes', '是', '1'):
                papers.append({
                    'title': row.get('title', '').strip(),
                    'author': row.get('author', '').strip(),
                    'year': row.get('year', '').strip(),
                    'source': row.get('source', '').strip(),
                })
    return papers


def load_papers_all(csv_path):
    """加载全部论文（不过滤 has_data）"""
    papers = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get('title', '').strip()
            if len(title) > 5:  # 有实质标题
                papers.append({
                    'title': title,
                    'author': row.get('author', '').strip(),
                    'year': row.get('year', '').strip(),
                    'source': row.get('source', '').strip(),
                })
    return papers


def save_log(entry):
    """追加JSONL日志行"""
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')


def safe_filename(s):
    """去除文件名非法字符并截断"""
    s = re.sub(r'[\\/*?:"<>|\n\r\t]', '', s)
    return s[:80]


def detect_format(content):
    """通过 magic bytes 检测文件格式"""
    if content[:4] == b'%PDF':
        return 'PDF'
    if content[:2] == b'HN':
        return 'CAJ'
    if content[:2] == b'PK':
        return 'ZIP'
    return 'UNKNOWN'


def get_search_query(paper):
    """构造搜索词：取主标题核心部分"""
    title = paper.get('title', '')
    for sep in ['——', '：', ':', '—']:
        if sep in title:
            title = title.split(sep)[0]
    return title[:60]


def title_match_score(result_title, target_title):
    """计算标题匹配度，返回 0-1"""
    if result_title.strip() == target_title.strip():
        return 1.0
    if target_title[:20] in result_title or result_title[:20] in target_title:
        return 0.8
    keywords = target_title[:30].replace('研究', '').replace('分析', '').replace('的', '')
    for kw in [keywords[:8], keywords[:6], keywords[:4]]:
        if len(kw) >= 4 and kw in result_title:
            return 0.6
    return 0.0


# ==================== CDP 操作 ====================

async def get_cnki_ws():
    """获取知网页面的 WebSocket 连接（复用已打开的，或新建）"""
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{CDP_BASE}/json/list") as resp:
            pages = await resp.json()
        for p in pages:
            if 'cnki.net' in p.get('url', ''):
                return p['webSocketDebuggerUrl']
        # 新建知网标签页
        async with session.put(f"{CDP_BASE}/json/new?https://www.cnki.net") as resp:
            new_page = await resp.json()
            return new_page['webSocketDebuggerUrl']


async def search_by_title(ws, title):
    """通过 URL 导航搜索知网，返回 [{title, href}] 列表"""
    search_url = f'https://kns.cnki.net/kns8s/defaultresult/index?kw={quote(title)}'
    await ws.send_json({"id": 1, "method": "Page.navigate",
                        "params": {"url": search_url}})
    await ws.receive_json()
    await asyncio.sleep(PAGE_LOAD_WAIT)

    await ws.send_json({"id": 2, "method": "Runtime.evaluate", "params": {"expression": """
        (() => {
            const results = [];
            for (let a of document.querySelectorAll('a')) {
                const t = (a.innerText || '').trim();
                const h = a.href || '';
                if (t.length > 10 && (h.includes('detail.aspx') ||
                    h.includes('article/abstract')))
                    results.push({title: t, href: h});
            }
            return JSON.stringify(results.slice(0, 8));
        })()
    """}})
    resp = await ws.receive_json()
    return json.loads(resp["result"]["result"]["value"])


async def get_download_url(ws, detail_url):
    """导航到详情页，提取PDF下载直链"""
    await ws.send_json({"id": 3, "method": "Page.navigate",
                        "params": {"url": detail_url}})
    await ws.receive_json()
    await asyncio.sleep(3)

    await ws.send_json({"id": 4, "method": "Runtime.evaluate", "params": {"expression": """
        (() => {
            for (let sel of ['#pdfDown', 'a.downloadlink', 'a.btn-download',
                              '.btn-dlpdf a', 'a[href*="bar.cnki.net"]']) {
                const el = document.querySelector(sel);
                if (el && el.href) return el.href;
            }
            for (let a of document.querySelectorAll('a')) {
                if ((a.href || '').includes('bar.cnki.net/bar/download'))
                    return a.href;
            }
            return null;
        })()
    """}})
    resp = await ws.receive_json()
    return resp["result"]["result"]["value"]


async def get_cookies_and_ua(ws):
    """从CDP获取Edge的Cookie和User-Agent"""
    await ws.send_json({"id": 5, "method": "Network.getCookies"})
    cookies = (await ws.receive_json())["result"]["cookies"]
    await ws.send_json({"id": 6, "method": "Runtime.evaluate",
                        "params": {"expression": "navigator.userAgent"}})
    ua = (await ws.receive_json())["result"]["result"]["value"]
    return cookies, ua


def download_with_cookies(dl_url, cookies, ua, referer):
    """Python requests 带Cookie下载，模拟正常浏览器"""
    session = requests.Session()
    for c in cookies:
        for domain in ['.cnki.net', '.bar.cnki.net']:
            session.cookies.set(c['name'], c['value'], domain=domain)
    headers = {'User-Agent': ua, 'Referer': referer}
    return session.get(dl_url, headers=headers, allow_redirects=True, timeout=45)


# ==================== 主循环 ====================

async def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else \
        ".claude/batch1_precise_screened_20260620_2118.csv"

    # 尝试加载 has_data=True 的论文，如果太少则加载全部
    papers = load_papers(csv_path)
    if len(papers) < 5:
        print(f"⚠️  has_data=True 仅 {len(papers)} 篇，改为加载全部（跳过空标题）")
        papers = load_papers_all(csv_path)

    print(f"📋 待下载: {len(papers)} 篇")
    print(f"📁 下载目录: {DOWNLOAD_DIR}")
    print(f"📝 日志文件: {LOG_FILE}")

    if not papers:
        print("无待下载论文，退出")
        return

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    pdf_ok = caj_ok = fail = 0

    for idx, paper in enumerate(papers):
        title = paper.get('title', '')
        author = paper.get('author', '')
        year = paper.get('year', '')
        print(f"\n{'='*60}")
        print(f"[{idx+1}/{len(papers)}] {author} ({year})")
        print(f"  {title[:60]}")

        try:
            # 1. CDP 连接知网页面
            ws_url = await get_cnki_ws()

            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(ws_url, max_msg_size=0) as ws:
                    # 2. 搜索
                    query = get_search_query(paper)
                    print(f"  🔍 搜索: {query[:50]}")
                    results = await search_by_title(ws, query)

                    if not results:
                        print(f"  ⚠️  无搜索结果")
                        save_log({**paper, 'status': 'NO_RESULTS',
                                  'timestamp': datetime.now().isoformat()})
                        fail += 1
                        continue

                    # 3. 匹配最佳结果
                    best = None
                    best_score = 0
                    for r in results:
                        score = title_match_score(r['title'], title)
                        if author and author[:2] in r['title']:
                            score += 0.1
                        if score > best_score:
                            best_score = score
                            best = r

                    if not best:
                        best = results[0]

                    print(f"  🎯 匹配({best_score:.1f}): {best['title'][:60]}")

                    # 4. 进详情页取下载链接
                    dl_url = await get_download_url(ws, best['href'])

                    if not dl_url:
                        print(f"  ⚠️  详情页无PDF下载链接")
                        save_log({**paper, 'status': 'NO_DOWNLOAD_ON_DETAIL',
                                  'matched_title': best['title'][:80],
                                  'timestamp': datetime.now().isoformat()})
                        fail += 1
                        continue

                    # 5. 获取Cookie并下载
                    cookies, ua = await get_cookies_and_ua(ws)

                    resp = None
                    for retry in range(MAX_RETRIES + 1):
                        try:
                            resp = download_with_cookies(dl_url, cookies, ua, best['href'])
                            if resp.status_code == 200 and len(resp.content) > 1000:
                                break
                            print(f"    重试{retry+1}: HTTP{resp.status_code} "
                                  f"{len(resp.content)}B")
                            await asyncio.sleep(random.uniform(2, 4))
                        except Exception as e:
                            print(f"    重试{retry+1}: {e}")
                            if retry == MAX_RETRIES:
                                raise
                            await asyncio.sleep(random.uniform(2, 4))

                    if not resp or resp.status_code != 200 or len(resp.content) < 1000:
                        print(f"  ❌ 下载失败")
                        save_log({**paper, 'status': 'DOWNLOAD_FAILED',
                                  'timestamp': datetime.now().isoformat()})
                        fail += 1
                        continue

                    # 6. 检测格式并保存
                    fmt = detect_format(resp.content)
                    ext = '.pdf' if fmt == 'PDF' else '.caj' if fmt == 'CAJ' else '.bin'
                    filename = safe_filename(f"{author}_{year}_{title[:50]}{ext}")
                    filepath = os.path.join(DOWNLOAD_DIR, filename)

                    with open(filepath, 'wb') as f:
                        f.write(resp.content)

                    size_kb = len(resp.content) / 1024
                    status = ('PDF_OK' if fmt == 'PDF' else
                              'CAJ_ONLY' if fmt == 'CAJ' else f'UNKNOWN_{fmt}')

                    print(f"  ✅ {status} | {size_kb:.0f}KB | {filename}")
                    save_log({
                        **paper,
                        'status': status,
                        'file': filename,
                        'size_kb': f'{size_kb:.0f}',
                        'matched_title': best['title'][:80],
                        'match_score': f'{best_score:.1f}',
                        'timestamp': datetime.now().isoformat()
                    })

                    if fmt == 'PDF':
                        pdf_ok += 1
                    elif fmt == 'CAJ':
                        caj_ok += 1
                    else:
                        fail += 1

        except Exception as e:
            print(f"  ❌ 异常: {str(e)[:150]}")
            save_log({**paper, 'status': f'ERROR: {str(e)[:100]}',
                      'timestamp': datetime.now().isoformat()})
            fail += 1

        # 随机延迟，模拟人类节奏
        delay = random.uniform(*DELAY_BETWEEN_PAPERS)
        print(f"  ⏳ {delay:.0f}s...")
        await asyncio.sleep(delay)

    # ==================== 报告 ====================
    print(f"\n{'='*60}")
    print(f"📊 批量下载完成")
    print(f"  ✅ PDF: {pdf_ok}")
    print(f"  🟡 CAJ: {caj_ok}")
    print(f"  ❌ 失败: {fail}")
    print(f"  📋 总计: {len(papers)}")
    print(f"  📝 日志: {LOG_FILE}")
    print(f"  📁 文件: {DOWNLOAD_DIR}")


if __name__ == '__main__':
    asyncio.run(main())
