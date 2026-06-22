"""本地3B模型批量筛选文献 — 识别含定量滞尘数据的论文"""
import torch, time, json, csv, sys
import pandas as pd
from transformers import AutoModelForVision2Seq, AutoProcessor
from pathlib import Path
from datetime import datetime

MODEL_PATH = Path.home() / ".cache/modelscope/hub/models/qwen/Qwen2___5-VL-3B-Instruct"

PROMPT = """判断这篇论文是否包含植物叶片滞尘的定量数据。
标准：论文必须包含g/m2或mg/cm2等单位的叶片单位叶面积滞尘量具体数值。
仅有定性描述（如"滞尘能力强"）、仅有排序、仅提总悬浮颗粒物(TSP)但没有数值的，不算。
只回答一个字：是 或 否

论文信息：
{text}"""

def load_model():
    print("加载Qwen2.5-VL-3B...", flush=True)
    model = AutoModelForVision2Seq.from_pretrained(
        str(MODEL_PATH), torch_dtype=torch.float16, device_map="auto"
    )
    processor = AutoProcessor.from_pretrained(str(MODEL_PATH))
    vram = torch.cuda.memory_allocated() / 1e9
    print(f"模型就绪, 显存: {vram:.1f}GB", flush=True)
    return model, processor

def screen_one(model, processor, title, abstract=""):
    """返回 (is_positive: bool, answer: str, time: float)"""
    text = f"标题：{title}"
    if abstract:
        text += f"\n摘要：{abstract}"
    prompt = PROMPT.format(text=text[:2000])  # 截断过长文本

    messages = [{"role": "user", "content": [{"type": "text", "text": prompt}]}]
    inputs = processor.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True,
        return_dict=True, return_tensors="pt"
    ).to(model.device)

    t0 = time.time()
    with torch.no_grad():
        outputs = model.generate(**inputs, max_new_tokens=5, temperature=0.0, do_sample=False)
    elapsed = time.time() - t0

    response = processor.decode(outputs[0], skip_special_tokens=True)
    answer = response.split('\n')[-1].strip()
    is_yes = '是' in answer and '否' not in answer
    return is_yes, answer, elapsed

def read_papers(input_path):
    """支持CSV/TSV/Excel/CNKI-HTML"""
    path = Path(input_path)
    suffix = path.suffix.lower()

    if suffix in ('.xls', '.xlsx'):
        # 知网导出的.xls实际是HTML，先尝试read_html
        try:
            dfs = pd.read_html(path, encoding='utf-8')
            if dfs:
                df = dfs[0]
                # 跳过可能的元数据行（第一行可能是"SrcDatabase-来源库"）
                if df.shape[1] >= 2:
                    df.columns = df.iloc[0]  # 第一行作列名
                    df = df.iloc[1:].reset_index(drop=True)
        except Exception:
            df = pd.read_excel(path, engine='xlrd')
    elif suffix == '.csv':
        df = pd.read_csv(path, encoding='utf-8')
    elif suffix in ('.html', '.htm'):
        dfs = pd.read_html(path, encoding='utf-8')
        df = dfs[0] if dfs else pd.DataFrame()
        if df.shape[1] >= 2:
            df.columns = df.iloc[0]
            df = df.iloc[1:].reset_index(drop=True)
    else:
        raise ValueError(f"不支持格式: {suffix}")

    # 标准化列名
    col_map = {}
    for col in df.columns:
        if '题名' in str(col) or '标题' in str(col) or 'title' in str(col).lower():
            col_map[col] = 'title'
        elif '摘要' in str(col) or 'abstract' in str(col).lower():
            col_map[col] = 'abstract'
        elif '作者' in str(col) or 'author' in str(col).lower():
            col_map[col] = 'author'
        elif '来源' in str(col) or '期刊' in str(col) or 'source' in str(col).lower():
            col_map[col] = 'source'
        elif '时间' in str(col) or '年份' in str(col) or 'year' in str(col).lower():
            col_map[col] = 'year'

    df = df.rename(columns=col_map)
    return df

def main():
    if len(sys.argv) < 2:
        print("用法: python screen_papers_local.py <输入文件.csv/xlsx/html> [输出前缀]")
        print("输入需含'题名'/'标题'列，可选'摘要'列")
        sys.exit(1)

    input_path = sys.argv[1]
    prefix = sys.argv[2] if len(sys.argv) > 2 else Path(input_path).stem

    df = read_papers(input_path)
    print(f"读取 {len(df)} 篇论文")

    # 确保有必要列
    if 'title' not in df.columns:
        print(f"错误: 找不到标题列。可用列: {list(df.columns)}")
        sys.exit(1)

    has_abstract = 'abstract' in df.columns
    if not has_abstract:
        print("注意: 未找到摘要列，仅用标题筛选（准确率会下降）")

    model, processor = load_model()

    results = []
    stats = {'yes': 0, 'no': 0, 'total_time': 0}

    print(f"\n开始筛选...")
    for i, row in df.iterrows():
        title = str(row['title'])
        abstract = str(row['abstract']) if has_abstract and pd.notna(row.get('abstract')) else ""

        is_yes, answer, elapsed = screen_one(model, processor, title, abstract)
        stats['total_time'] += elapsed

        if is_yes:
            stats['yes'] += 1
        else:
            stats['no'] += 1

        results.append({
            'title': title,
            'abstract': abstract[:500] if abstract else '',
            'author': str(row.get('author', '')),
            'source': str(row.get('source', '')),
            'year': str(row.get('year', '')),
            'has_data': is_yes,
            'raw_answer': answer,
        })

        if (i+1) % 10 == 0:
            eta = stats['total_time'] / (i+1) * (len(df) - i - 1)
            print(f"  [{i+1}/{len(df)}] Y={stats['yes']} N={stats['no']} | {stats['total_time']/(i+1):.1f}s/篇 | 剩余约{eta:.0f}s", flush=True)

    # 输出
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out_csv = Path(f"{prefix}_screened_{ts}.csv")
    out_json = Path(f"{prefix}_screened_{ts}.json")

    with open(out_csv, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=['title','author','source','year','abstract','has_data','raw_answer'])
        writer.writeheader()
        writer.writerows(results)

    positive = [r for r in results if r['has_data']]
    negative = [r for r in results if not r['has_data']]

    summary = {
        'total': len(df),
        'positive': len(positive),
        'negative': len(negative),
        'positive_rate': f"{len(positive)/len(df)*100:.1f}%",
        'total_time_s': stats['total_time'],
        'avg_time_per_paper_s': stats['total_time'] / len(df),
    }
    with open(out_json, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n完成:")
    print(f"  总计: {len(df)} 篇")
    print(f"  阳性(可能有数据): {len(positive)} 篇 ({summary['positive_rate']})")
    print(f"  阴性(无数据): {len(negative)} 篇")
    print(f"  耗时: {stats['total_time']:.0f}秒 ({stats['total_time']/len(df):.1f}s/篇)")
    print(f"  输出: {out_csv}")
    print(f"        {out_json}")

if __name__ == '__main__':
    main()
