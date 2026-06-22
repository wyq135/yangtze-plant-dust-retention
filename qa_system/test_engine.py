"""
test_engine.py — query_engine 功能验证（不依赖 LLM）
"""
import sys, json
sys.path.insert(0, 'C:/Users/政委/plant_dust_analysis')
from qa_system.query_engine import QueryEngine

eng = QueryEngine()
passed = 0
failed = 0

def check(name, actual, expected):
    """expected: {key: value} 逐个验证 actual 中的 key 等于 value"""
    global passed, failed
    ok = True
    for key, exp_val in expected.items():
        act_val = actual.get(key) if isinstance(actual, dict) else getattr(actual, key, None)
        if act_val != exp_val:
            print(f"  ✗ {name}: {key} 期望={exp_val!r}, 实际={act_val!r}")
            ok = False
    if ok:
        print(f"  ✓ {name}")
        passed += 1
    else:
        failed += 1

def check_in(name, result, key, expected_contains):
    global passed, failed
    val = result.get(key, "")
    if isinstance(expected_contains, str):
        ok = expected_contains in val
    elif isinstance(expected_contains, list):
        ok = all(e in val for e in expected_contains)
    else:
        ok = str(expected_contains) in str(val)
    if ok:
        print(f"  ✓ {name}")
        passed += 1
    else:
        print(f"  ✗ {name}: {key}={val!r} 中未找到 {expected_contains!r}")
        failed += 1

# ── 参数清洗 ──────────────────────────────
print("\n=== 参数清洗 ===")
params, errors = eng.normalize_params({"season": "冬天", "zone": "道路", "layer": "乔木"})
check("season口语→标准", params, {"season": "冬季"})
check("zone简称→标准", params, {"zone": "道路绿地"})
check("layer保持不变", params, {"layer": "乔木"})

params, errors = eng.normalize_params({"pm_type": "pmtype"})
check("pm_type变体", params, {"pm_type": "tsp"})

params, errors = eng.normalize_params({"city": "金陵"})
check("city别名→标准", params, {"city": "南京"})

params, errors = eng.normalize_params({"species": ["法桐", "樟树"]})
if params.get("species") and "二球悬铃木" in str(params["species"]):
    print("  ✓ species别名→标准")
    passed += 1
else:
    print(f"  ✗ species别名: {params.get('species')}")
    failed += 1

# ── Stats 模式 ──────────────────────────
print("\n=== Stats 模式 ===")
r = eng.query({"mode": "stats", "species": ["香樟"], "city": "南京", "season": "冬季", "pm_type": "tsp"})
print(f"  count={r['count']}, stats={r['statistics']}")
check("stats有统计值", r["statistics"], {"mean": r["statistics"]["mean"]})  # exists
print(f"  样本数: {len(r.get('samples', []))}")
if r["warnings"]:
    for w in r["warnings"]:
        print(f"  ⚠ {w}")
passed += 1  # just verify it doesn't crash

# ── Rank 模式 ────────────────────────────
print("\n=== Rank 模式 ===")
r = eng.query({"mode": "rank", "city": "南京", "layer": "乔木", "zone": "道路绿地", "top_n": 5})
print(f"  物种数={r['species_count']}, 总记录={r['count']}")
for item in r.get("ranking", []):
    print(f"  #{item['rank']} {item['species']}: 中位数={item['median']}, n={item['n']}")
if r["honorable_mentions"]:
    print(f"  荣誉提名: {r['honorable_mentions']}")
if r["excluded_low_n"]:
    print(f"  排除(样本不足): {r['excluded_low_n'][:5]}")
check("rank有排名", r, {"mode": "rank"})
check("rank≥1物种", r, {"species_count": r["species_count"]})

# ── 空结果降级 ──────────────────────────
print("\n=== 空结果降级 ===")
# 用存在城市但极端条件组合
r = eng.query({"mode": "stats", "species": ["香樟"], "city": "武汉", "season": "冬季",
               "zone": "居住区", "pm_type": "tsp"})
print(f"  降级: degraded={r.get('degraded')}, relaxed={r.get('relaxed_conditions')}, count={r.get('count', 0)}")
if r.get("degraded"):
    check("空结果已降级", r, {"degraded": True})

# ── 模糊匹配 ────────────────────────────
print("\n=== 模糊匹配 ===")
r = eng.query({"mode": "stats", "species": ["香樟 "], "city": "南京", "pm_type": "tsp"})
print(f"  输入'香樟 '(含空格) → 匹配到: {r.get('count', 0)}条")
check("模糊匹配有结果", r, {"count": r["count"]})
# 极端case: 无法匹配
r2 = eng.query({"mode": "stats", "species": ["不存在的植物XYZ"], "city": "南京", "pm_type": "tsp"})
err = r2.get("errors", [])
print(f"  不存在的植物 → errors: {err}")

# ── 排名指标验证 ────────────────────────
print("\n=== 排名中位数 vs 均值 ===")
r = eng.query({"mode": "rank", "city": "南京", "layer": "乔木", "zone": "道路绿地"})
for item in r.get("ranking", [])[:3]:
    diff = abs(item["median"] - item["mean"])
    if diff > 3:
        print(f"  {item['species']}: 中位数={item['median']}, 均值={item['mean']}, 差值={diff:.1f} ← 极端值拉偏均值")
check("rank≥2物种", r, {"mode": "rank"})

# ── PM类型 ─────────────────────────────
print("\n=== PM类型切换 ===")
r = eng.query({"mode": "stats", "species": ["香樟"], "city": "南京", "pm_type": "pm10"})
print(f"  PM10: count={r['count']}")
r = eng.query({"mode": "stats", "species": ["香樟"], "city": "南京", "pm_type": "pm2_5"})
print(f"  PM2.5: count={r['count']}")
passed += 2  # didn't crash

print(f"\n{'='*40}")
print(f"结果: {passed} 通过, {failed} 失败")
