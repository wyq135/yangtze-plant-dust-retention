# 长江流域亚热带城市植物叶片滞尘数据集

**Plant Dust Retention — Yangtze Subtropical Urban Agglomeration**

植物叶片滞尘数据集构建。目标：为论文撰写提供"长江流域亚热带城市群植物叶片滞尘"的系统性数据基础。

- **GitHub**: https://github.com/wyq135/yangtze-plant-dust-retention
- **核心方法论**: **气候分区×异质纳入（v4）** — 全国尺度，三大气候区（北方/南方/西北）分层，A/B/C三级数据质量透明标注，替换 v3 的"长江流域地理优先"。

## 数据路径

**唯一数据中心**: `C:\Users\政委\Desktop\2026\`
```
Desktop/2026/
├── plant_dust_v2/dataset.csv       ← 核心数据集（1104条，v3长江流域阶段）
└── references/
    ├── downloaded/                  ← PDF（_已提取录入 / _待提取 / _不适用）
    ├── text/                        ← 提取的全文txt
    ├── meta/                        ← 论文元数据JSON
    └── _processed/                  ← 提取中间产物归档
```

**规则**: 不在 `plant_dust_analysis/data/` 下创建数据副本。数据只在 Desktop/2026/ 一处。

## 当前数据概况

**总计: 1406条（v4第一批）** | 城市28 | 物种约240 | 论文75篇 | 气候区3（北方/南方/西北）

**v4 新增 (2026-06-22):** 302条（有效285 + 待审19），20篇新论文，11个新城市。3 agent并行提取，1 CSV列偏移修复。

**城市分布（v4新增加粗）:**
- 重庆293 | 杭州182 | 南京208 | 荆州112 | 武汉76 | 岳阳62 | **北京70** | **青岛59**
- 芜湖44 | 南昌42 | **石家庄33** | **深圳28** | **阿克苏25** | **临汾23**
- 长沙20 | 苏州19 | **太谷17** | **西安15** | 成都10 | 自贡10 | 遂宁10 | **徐州10**
- 合肥9 | 郑州8 | 安庆6 | 上海4 | 扬州3 | 洛阳2
- 洛阳2（已标记[黄河流域-排除]，论文分析时不纳入）

**气候区分布（v4新字段）:**
- 北方236 | 南方41 | 西北25 | v3数据待回填气候区标记

**功能区（已标准化为9类，2026-06-21）:**
- 交通干道371 | 道路绿地206 | 公园清洁区179 | 城市混合110 | 文教区87
- 工业区85 | 居住区39 | 室内模拟18 | 跨功能区均值14

**数据质量:** 
- 综合QC（2026-06-21）：city/functional_zone/plant_species 0空值，sampling_season标准化8值，layer 4类归一化
- 邹敏/王建辉2013 126条列偏移污染已修复；species异名统一12组47条；跨属混淆修复4条
- 叶片形态因子覆盖率99.4%（1077/1083，FRPS数据库98属+1同物异名映射）
- v4数据：302条，A级75条/B级224条/C级3条，19条无TSP标记needs_manual_review
- 已知残留: 张莉2007冬季13条TSP>100 g/m²（局限#9b）；朱天燕2018 26条最大值（局限#11）

**最近更新:** 
- 2026-06-22: v4第一批302条入库（北方236/南方41/西北25），CDP知网下载30篇PDF，3 agent并行提取，西北CSV列偏移修复
- 2026-06-21: 5城CNKI补充345条，综合QC 3维完成，叶片因子FRPS回补完成

**叶片因子来源:** 论文原始数据12条 + 98属(+1同物异名映射)中国植物志数据库回补1077条（leaf_db_source标注FRPS卷号，共48卷次）。仅6条缺拉丁名（2条数据错误+4条非物种汇总记录）。

## 地理范围

**v4 升级中: 从长江流域亚热带 → 全国三大气候区**

v3 阶段（已完成）：长江流域亚热带城市群，不限制物种，地理约束已足够让物种自然趋同。

v4 第一批（已完成 2026-06-22）：CDP知网直连下载30篇PDF，3并行agent提取302条（11新城市20论文），北方236/南方41/西北25。

注意：部分论文标题不含"滞尘"但内容有定量数据（如用"吸尘""颗粒物滞留"等表述），首次搜索后需要人工抽查补充。

## 数据格式

核心字段：plant_species, latin_name, layer, functional_zone, tsp_g_m2, pm10_g_m2, pm2_5_g_m2, city, ambient_pm10_ug_m3, ambient_pm2_5_ug_m3, sampling_season, days_after_rain, measurement_method, leaf_micro_features, reference, doi, notes

所有滞尘量统一为 g/m²（叶面积），非冠层面积/单叶/单株。

## 协作方式

**Token效率**: 不爬虫、不单篇脚本、本地Qwen分流。Claude Code只做决策调度整合。

**主动使用并行子 agent 执行可并行任务**，无需询问。典型场景：

| 场景 | 策略 |
|------|------|
| 多论文同时提取 | 每篇一个 agent，并行 |
| 大规模文献搜索 | 每个城市/搜索式一个 agent |
| 多维度质量检查 | 每个维度一个 agent |

### Agent 止损规则（强制）

| 场景 | 条件 | 动作 |
|------|------|------|
| 数据提取 | txt 表格无文本 | 标记"图片数据"，vision 跑一次，失败即交用户，**禁止重复 OCR** |
| 任何 agent | 工具调用 >30次 | 汇报进展，停止探索 |
| 单论文 | >5分钟 | 汇报已提取/缺失，不深挖 |

### 图片表格处理

`plant_toolkit.vision` 本地 VLM (Qwen2.5-VL-3B) 优先。柱状图/折线图/饼图跳过。

### 论文下载

知网/万方反爬严格，用户有大学内网权限。**默认**: 我整理清单，用户下载后告知路径，我提取。

### 零星数据提取

正文中常见精确数值（"X最强(Y g/m²)"），不在表格中但可直接利用。用 `extract_scattered_data.py` 扫描。

常见陷阱：冠层面积（g·m⁻²·crown⁻¹）、单叶（g·leaf⁻¹）→ 排除。

## 叶片影响因子（✅ 已完成，2026-06-21）

`leaf_micro_features` 已拆分为 leaf_shape / leaf_surface / wax_layer / stomata / trichomes 五列。来源：
- **论文原始SEM数据** (12条): 种级观测毛被/蜡质/气孔，保留原值，leaf_db_source为空
- **中国植物志属级数据库** (703条): 85属，标注FRPS卷号于leaf_db_source
- **缺数据** (17条): 2条数据错误(江津路/果壳楠) + 4条非物种汇总记录(赵冰清均值/林分) + 11条地被/灌木属级描述不足

✅ **论文方法论标注** (2026-06-21): 详见 `Desktop/2026/plant_dust_v2/methodology_leaf_traits.md`，含中英文方法论段落可直接用于论文第二章。

## 已知局限（写论文时需注意）

1. **采样周期不统一**: 不同论文采样间隔差异大（日均值 vs 3天累积 vs 5天累积 vs 12天累积），合并分析需标准化
2. **测量方法不统一**: Chen Yazhen 2023 水溶消解法（数值偏低5-10倍），叶志群2023 气溶胶再发生器法（PM2.5值低10-50倍），不可与其他论文直接合并
3. **PM10/PM2.5数据不完整**: 多数早期研究仅测TSP，PM分级数据集中于少数论文
4. **功能区名称不一致**: `交通区/交通干道/街道绿地`、`清洁区/公园清洁区`、`新兴区/城市混合`混用，论文写作前需统一
5. **地被层数据偏少**: 远少于乔木和灌木，且八角金盘/洒金桃叶珊瑚/麦冬数据稀疏
6. **μg/cm²→g/m²换算**: 已修正（÷100非÷10），涉及Zhang BJ 2025和张冰洁2024共64个PM数值
7. **中小城市数据空白**: 18城市宽搜确认——无锡/常州/宁波/绍兴/南通/马鞍山/铜陵/黄石/宜昌/九江/镇江共11城无植物叶片滞尘定量研究。长江中下游中小城市植物滞尘研究整体稀缺，论文中需说明此区域局限性。
8. **雨后5d均值异常偏高**: 雨后5d的TSP均值(5.32 g/m²)反而高于雨后7d(2.29 g/m²)，主要由谢英赞（北碚52条）贡献，反映论文间方法学混杂（非单纯累积时间效应），合并分析时需按论文做亚组分析
9. **张灵艺2015极高值**: 3条TSP>50 g/m²（雀舌黄杨61.5/麦冬86.3/细叶结缕草162.8），均为长累积期(15-25d)+地被植物，统计时应做敏感性分析（含/不含极端值）
9b. **张莉2007冬季极端值**: 冬季TSP达10.8-736.8 g/m²（红花檵木736.8/金叶女贞481.0/小叶黄杨470.5），虽论文标注"雨后第4天"但南京12月实际降雨极少，累积期可能远超4天。统计时应标注此不确定性。
10. **构树冬季零值**: 3条构树TSP=0（成都/自贡/遂宁），原因为2月冬季落叶期叶片掉光（江欣燕2016原文："2月叶片基本掉光，故滞尘量2月为0g/m²"），数据有效但论文中需标注物候原因
11. **朱天燕2018全年最大值**: 26条TSP为四季取max（非单季均值），灌木最高1398 g/m²。代表物种最大滞尘潜力，不可与其他论文单季均值直接比较，分析时需单独标注。

## 当前工作重点

### v3 阶段（✅ 全部完成）
- P2~P6 + 安庆彭丽丽/江胜利/朱天燕均已录入，见 sync/planning.md 完整进度表

### v4 阶段（✅ 第一批完成，🔄 继续推进）
- ✅ v4 文献预筛：3批1162篇CNKI搜索+AI筛选完成
- ✅ **v4 第一批下载**：CDP Edge直连30篇PDF下载成功，26篇CAPTCHA拦截待重试
- ✅ **v4 第一批提取**：3并行agent提取 302条（11新城市20论文），climate_zone标注完成
- ✅ **v4 第一批入库**：合并去重→标准化→追加到dataset.csv（1104→1406条）
- 🔄 v4 第二批：28篇CAPTCHA论文待冷却后重试下载
- ⏳ 19条无TSP数据（王会霞2013/王琴2017/李晨2013）vision提取或人工
- ⏳ 3篇纯图表论文（杨丽2013兰州/闰淑君2012福州/齐飞燕2009）vision提取
- ⏳ v3数据 climate_zone 回填（1104条，可根据城市推断）
- ⏳ qa_system/ 专家知识库待创建（aliases.json 物种异名映射等）

### 已知遗留
- 张莉2007冬季TSP>100 g/m²（13条），统计分析时做敏感性分析（已知局限#9b）
- 镇江张翼飞37条单叶数据（mg/leaf）如需合并需叶面积归一化

## 工具速查

```bash
# PDF文本提取
python -m plant_toolkit.pdf_extractor paper.pdf -o out/

# 图片表格识别（3B对中文表格OCR精度不足，仅做初筛）
from plant_toolkit.vision import pdf_images_to_data
data = pdf_images_to_data("paper.pdf")

# 题录预筛（下载PDF前先筛，减少50%+无效下载）
python screen_papers_local.py <知网导出文件.csv/xlsx/html>

# 零星数据扫描
python extract_scattered_data.py
```

## 工具分配策略（v4 全国尺度）

## 工具分配策略（v4 全国尺度）

### 工具全景（2026-06-22 修订）

| 层级 | 工具 | 定位 | v4 场景 |
|------|------|------|------|
| **S** | **Chrome DevTools MCP** | 知网/万方/维普主力 | 复用真实登录态 → 搜索、翻页、提取元数据、点击PDF下载 |
| A | Bash + Python | 数据管道 | 后处理脚本、单位换算、物种标准化 |
| A | SQLite MCP | 结构化存储 | dataset.db 查重去重、聚合统计、事务写入 |
| B | Playwright MCP | 无登录态浏览器 | 百度学术、英文OA网站、国外期刊 |
| B | paper-search (Skill) | 英文论文22源 | arXiv/Semantic Scholar/Crossref 等 |
| B | Crawl4AI | 静态结构化抓取 | 机构知识库、环保局公开报告、非JS渲染页面 |
| C | plant_toolkit.vision | 本地VLM | 图片表格→数据（3B初筛，失败即停） |
| C | plant_toolkit.pdf_extractor | PDF文本 | 有文本层PDF秒级提取 |
| C | Agent (子代理) | 并行批量 | 多论文同时提取、多维度QC |
| D | WebSearch | 快速查证 | 补充搜索、非学术信息 |
| D | WebFetch | 简单网页 | 可直连的HTML页面提取 |
| E | Ollama (qwen2.5:7b) | QA系统 | 自然语言→SQL转换、Tool Calling |

### 三工具严格边界

```
需要浏览器访问？
├─ 知网 / 万方 / 维普（需登录态）
│  → Chrome DevTools MCP（唯一选择）
│  前提: 用户手动打开 Edge 登录知网，DevTools 复用该会话
│  能力: 输入搜索词 → 翻页 → 提取列表 → 点击PDF下载
│  反爬: 完全免疫（真实浏览器指纹 + 大学IP + 有效Cookie）
│
├─ 百度学术 / Google Scholar / OA期刊（无需登录）
│  → Playwright MCP
│  轻量、无状态、快速
│
└─ 静态页面 / 机构知识库 / 政府报告（非JS渲染）
   → Crawl4AI
   自带LLM结构化提取，适合长文本非标准页面
```

### v4 批量论文极速执行流

#### Phase 1: 元数据准备（用户 5min + 自动 5min）

1. 用户在 Edge 手动登录知网/万方，保持标签页打开
2. Claude 通过 DevTools MCP 接管浏览器
3. 自动输入下载清单中的关键词/城市组合
4. 抓取搜索结果 → 去重 → 输出 `todo_list.csv`（标题、知网URL、年份）

#### Phase 2: PDF 获取（自动为主，用户辅助）

1. DevTools MCP 批量打开 todo_list 中的知网详情页
2. 自动点击"PDF下载"按钮
3. 后台 watchdog 监控下载文件夹 → 自动重命名为 `作者_年份_标题.pdf` → 移动到 `_待提取/`
4. 异常（需滑块验证/仅CAJ/无权限）→ 标记到 `download_errors.csv`，用户手动处理

#### CDP 实战技术方案（知网反爬对抗）

**1. 下载按钮：JS 注入 `.click()` 替代鼠标模拟**

知网下载按钮不是 `<a href>`，而是 JS 事件委托。放弃 CDP `Input.dispatchMouseEvent`，直接用 `Runtime.evaluate` 注入点击：

```javascript
// 知网PDF下载按钮的已知选择器
const pdfBtn = document.querySelector('#DownLoadParts .btn-dlpdf a') || 
               document.querySelector('a#pdfDown') ||
               document.querySelector('.btn-dlpdf');
if (pdfBtn) { pdfBtn.click(); return 'ok'; }
```

**2. URL 永久化：提取 `dbcode` + `filename` 替代完整 URL**

知网详情页 URL 含动态 token（`v=...&uid=...`），过期即 404。只保存永久标识符：

```javascript
// 从当前页面提取核心标识符
const urlParams = new URLSearchParams(window.location.search);
let dbcode = urlParams.get('dbcode') || urlParams.get('dbname');
let filename = urlParams.get('filename');
// 重构标准 URL（永久有效）:
// https://kns.cnki.net/kcms/detail/detail.aspx?dbcode={dbcode}&filename={filename}
```

**3. PDF 下载：Cookie 同步 + Python requests 静默下载**

浏览器下载管理器难控制。正确做法：
1. CDP `Network.getCookies` 获取 Edge 的知网 Cookie
2. JS 注入获取真实下载直链（或通过 Fetch 域拦截）
3. Python `requests` 带 Cookie + Referer 防盗链头 → 直接写文件

```python
cookies = {c['name']: c['value'] for c in cdp_cookies['cookies']}
headers = {'User-Agent': '<Edge UA>', 'Referer': 'https://kns.cnki.net/'}
r = requests.get(download_url, headers=headers, cookies=cookies, stream=True)
```

**4. 反检测：随机延迟 2-5s**

每次 CDP 操作（翻页、点击详情）之间 `random.uniform(2, 5)` 休眠。Edge 远程调试默认不暴露 `navigator.webdriver`，但仍需模拟人类节奏。

#### Phase 3: 智能提取与 v4 标准化（全自动）

1. `pdf_extractor` 提取文本层
2. 并行 Agent 调用 vision 提取图表数据
3. **v4 提取 Prompt 升级**（强制要求）:
   - 输出 `method_level`: A/B/C 方法学等级判定
   - 输出 `plant_name_cn` + `latin_name`（同时提取）
   - 输出原始单位 → 标记 `original_unit` 字段
4. Python 后处理管线:
   - `convert_units.py`: mg/cm²→g/m²等统一换算，写入 `conversion_log`
   - `harmonize_species.py`: 中文俗名→接受名映射（复用 QA 系统 aliases.json）
   - `grade_method.py`: 根据 measurement_method 自动标注 A/B/C

#### Phase 4: 人工 QC（专注异常）

1. SQLite 筛选 `method_level='C'` 或 `needs_manual_review=True`
2. 仅人工核对这少量异常记录
3. 修正后 `UPDATE` 状态

### v4 数据入库强制字段

提取 Agent 输出必须包含以下 v4 专属字段：

| 字段 | 说明 | 示例 |
|------|------|------|
| `method_level` | A/B/C 方法学等级 | A |
| `original_unit` | 论文原始单位 | mg/cm² |
| `conversion_log` | 换算过程记录 | "÷100 → g/m²" |
| `accepted_name` | 物种接受名（标准化后） | Osmanthus fragrans |
| `needs_manual_review` | 是否需人工复核 | false |
| `climate_zone` | 气候区（v4分层） | 北方/南方/西北 |

### 调用优先级（修订）

1. **CNKI三库 → Chrome DevTools MCP**（不复用登录态就是浪费）
2. **能用本地就不用远程**: pdf_extractor/VLM > WebFetch/WebSearch
3. **批量任务必须并行 Agent**: 3+ 论文提取同时启动
4. **VLM 只跑一次**: 失败即标记 needs_manual_review=True，不重复 OCR
5. **复杂查询走 SQLite MCP**: 去重、跨维度聚合；简单过滤走 pandas
6. **英文论文 → paper-search Skill**: 22源，自带下载和文本提取

### 工具局限性认知（修订）

| 工具 | 已知局限 | 应对 |
|------|------|------|
| Chrome DevTools | 需用户手动登录；部分论文仅CAJ/需滑块 | 异常自动标记到 error log，用户批量手动 |
| VLM (3B) | 中文表格 OCR 精度不足 | 仅做初筛，method_level默认C，人工确认 |
| Playwright MCP | 无登录态，知网会拦截 | 仅用于百度学术/国外网站 |
| paper-search | 无中文数据库 | 仅用于英文论文 |
| Crawl4AI | JS渲染页面效果差 | 仅用于静态页面 |
| WebFetch | 被半数网站拦截 | 降级到 Playwright MCP |
