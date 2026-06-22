"""
植物滞尘数据查询引擎 — pandas过滤 + 参数清洗 + 排名 + 动态警告 + 空结果降级
"""
import json
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process

warnings.filterwarnings('ignore')

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# 有效枚举值——normalize_params 优先映射到这些值
VALID_SEASONS = ["春季", "夏季", "秋季", "冬季", "全年", "秋冬", "全年最大", "室内模拟"]
VALID_ZONES = ["交通干道", "道路绿地", "公园清洁区", "城市混合", "居住区", "工业区", "文教区", "室内模拟", "跨功能区均值"]
VALID_LAYERS = ["乔木", "灌木", "草本", "地被", "藤木"]
VALID_PM_TYPES = ["tsp", "pm10", "pm2_5"]

# 显式口语→标准映射（fuzzy ratio 不足 85% 时靠这个兜底）
HARD_MAP_SEASON = {"冬天": "冬季", "夏天": "夏季", "春天": "春季", "秋天": "秋季"}
HARD_MAP_ZONE = {"道路": "道路绿地", "街道": "交通干道", "公园": "公园清洁区",
                  "居住": "居住区", "工业": "工业区", "文教": "文教区", "交通": "交通干道"}
HARD_MAP_LAYER = {"树": "乔木", "草": "草本", "藤": "藤木"}
HARD_MAP_PM = {"pmtype": "tsp", "pm_type": "tsp", "pm": "tsp", "pm2.5": "pm2_5",
               "pm2_5": "pm2_5", "pm25": "pm2_5", "pm_10": "pm10"}


def _numpy_to_native(obj):
    """递归将 numpy 类型转为 Python 原生类型，确保 json.dumps 可用"""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: _numpy_to_native(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_numpy_to_native(v) for v in obj]
    return obj


class QueryEngine:
    def __init__(self):
        # 加载数据
        self.df = pd.read_csv(DATA_DIR / "dataset.csv", encoding="utf-8-sig")
        self.df.columns = [c.strip().replace("﻿", "") for c in self.df.columns]

        # 加载别名
        with open(DATA_DIR / "aliases.json", "r", encoding="utf-8") as f:
            aliases_raw = json.load(f)
        self.species_aliases = aliases_raw.get("species_aliases", {})
        self.city_aliases = aliases_raw.get("city_aliases", {})
        # 反查：standard→别名列表（运行时生成）
        self._species_standards = {v["standard"] for v in self.species_aliases.values()}

        # 加载警告配置
        with open(DATA_DIR / "warnings_config.json", "r", encoding="utf-8") as f:
            self.warnings_config = json.load(f)

        # 有效值集合——快速过滤
        self._valid_species = set(self.df["plant_species"].dropna().unique())
        self._valid_cities = set(self.df["city"].dropna().unique())

    # ── 参数清洗 ──────────────────────────────────────────
    def _fuzzy_map(self, value, candidates, threshold=80):
        """单个值模糊匹配到候选列表，返回 (最佳匹配, 置信度)"""
        if not value or not isinstance(value, str):
            return value, 0
        value = value.strip()
        if value in candidates:
            return value, 100
        try:
            result = process.extractOne(value, candidates, scorer=fuzz.ratio)
        except Exception:
            return value, 0
        if result is None:
            return value, 0
        # rapidfuzz >=3.0: result.choice / result.score
        if hasattr(result, 'choice'):
            return result.choice, result.score
        # rapidfuzz <3.0: (match, score, index)
        match, score = result[0], result[1]
        return match, score

    def normalize_params(self, params):
        """入口：清洗 LLM 输出的参数，默默修正，仅严重歧义报错"""
        errors = []

        # season: "冬天"→"冬季" (显式映射优先，fuzzy ratio 不足 85% 兜底)
        if "season" in params and params["season"]:
            raw = params["season"].strip()
            if raw in HARD_MAP_SEASON:
                params["season"] = HARD_MAP_SEASON[raw]
            elif raw in VALID_SEASONS:
                pass
            else:
                mapped, score = self._fuzzy_map(raw, VALID_SEASONS, threshold=80)
                if score >= 80:
                    params["season"] = mapped
                else:
                    errors.append(f"season '{raw}' 无法匹配，有效值: {VALID_SEASONS}")

        # zone: "道路"→"道路绿地"
        if "zone" in params and params["zone"]:
            raw = params["zone"].strip()
            if raw in HARD_MAP_ZONE:
                params["zone"] = HARD_MAP_ZONE[raw]
            elif raw in VALID_ZONES:
                pass
            else:
                mapped, score = self._fuzzy_map(raw, VALID_ZONES, threshold=80)
                if score >= 80:
                    params["zone"] = mapped
                else:
                    errors.append(f"zone '{raw}' 无法匹配，有效值: {VALID_ZONES}")

        # layer
        if "layer" in params and params["layer"]:
            raw = params["layer"].strip()
            if raw in HARD_MAP_LAYER:
                params["layer"] = HARD_MAP_LAYER[raw]
            elif raw in VALID_LAYERS:
                pass
            else:
                mapped, score = self._fuzzy_map(raw, VALID_LAYERS, threshold=80)
                if score >= 80:
                    params["layer"] = mapped
                else:
                    errors.append(f"layer '{raw}' 无法匹配，有效值: {VALID_LAYERS}")

        # pm_type: "pmtype"→"tsp"
        if "pm_type" in params and params["pm_type"]:
            raw = params["pm_type"].lower().replace("_", "").replace("-", "").strip()
            if raw in HARD_MAP_PM:
                params["pm_type"] = HARD_MAP_PM[raw]
            elif raw in VALID_PM_TYPES:
                params["pm_type"] = raw
            else:
                mapped, score = self._fuzzy_map(raw, VALID_PM_TYPES, threshold=80)
                if score >= 80:
                    params["pm_type"] = mapped
                else:
                    errors.append(f"pm_type '{raw}' 无法匹配，有效值: {VALID_PM_TYPES}")

        # species 别名解析
        if "species" in params and params["species"]:
            resolved = []
            for s in params["species"]:
                std = self._resolve_species(s)
                if std is None:
                    errors.append(f"物种 '{s}' 在数据集中未找到，可用模糊匹配候选")
                else:
                    resolved.append(std)
            params["species"] = resolved if resolved else None

        # city 别名解析
        if "city" in params and params["city"]:
            raw = params["city"]
            # 先查别名
            alias = self.city_aliases.get(raw, {})
            if alias.get("standard"):
                raw = alias["standard"]
            if raw in self._valid_cities:
                params["city"] = raw
            else:
                mapped, score = self._fuzzy_map(raw, list(self._valid_cities), threshold=85)
                if score >= 85:
                    params["city"] = mapped
                else:
                    errors.append(f"城市 '{raw}' 未找到，有效值: {sorted(self._valid_cities)}")

        return params, errors

    def _resolve_species(self, name):
        """解析物种别名→标准名，支持模糊匹配"""
        if not name or not isinstance(name, str):
            return None
        name = name.strip()
        # 精确匹配标准名
        if name in self._valid_species:
            return name
        # 查别名表
        alias = self.species_aliases.get(name, {})
        if alias.get("standard") and alias["standard"] in self._valid_species:
            return alias["standard"]
        # 模糊匹配
        try:
            result = process.extractOne(name, list(self._valid_species), scorer=fuzz.ratio)
        except Exception:
            return None
        if result is None:
            return None
        # rapidfuzz >=3.0
        if hasattr(result, 'choice'):
            if result.score >= 85:
                return result.choice
            return None
        # rapidfuzz <3.0: (match, score, index)
        if result[1] >= 85:
            return result[0]
        return None

    # ── 主入口 ────────────────────────────────────────────
    def query(self, params):
        """params: LLM Tool Calling 提取的参数字典。返回统计结果JSON。"""
        params, errors = self.normalize_params(params)
        if errors:
            return {"mode": "error", "errors": errors, "hint": "请修正参数后重试"}

        mode = params.get("mode", "stats")
        if mode == "rank":
            return self._query_rank(params)
        return self._query_stats(params)

    # ── 统计模式 ──────────────────────────────────────────
    def _query_stats(self, params):
        df = self.df.copy()
        original_conditions = {}

        # 逐条件过滤
        for col, key in [("city", "city"), ("sampling_season", "season"),
                         ("functional_zone", "zone"), ("layer", "layer")]:
            if params.get(key):
                original_conditions[key] = params[key]
                df = df[df[col] == params[key]]

        # species 过滤
        if params.get("species"):
            original_conditions["species"] = params["species"]
            df = df[df["plant_species"].isin(params["species"])]

        # PM 类型
        pm_type = params.get("pm_type", "tsp")
        pm_col = f"{pm_type}_g_m2"
        if pm_col in df.columns:
            df = df[df[pm_col].notna()]
        else:
            pm_col = "tsp_g_m2"
            df = df[df["tsp_g_m2"].notna()]

        # 雨后天数过滤
        if params.get("days_after_rain"):
            try:
                days_val = float(params["days_after_rain"])
                df = df[df["days_after_rain"].astype(str).str.extract(r'(\d+)')[0].astype(float) <= days_val + 1]
            except (ValueError, KeyError):
                pass

        count = len(df)

        # 空结果降级
        degraded = False
        relaxed = []
        if count == 0 and original_conditions:
            df, degraded, relaxed = self._degrade(params, original_conditions)

        count = len(df)
        values = df[pm_col].dropna()

        # 统计
        stats = {
            "count": count,
            "pm_type": pm_type,
            "statistics": {
                "mean": round(float(values.mean()), 2) if len(values) > 0 else None,
                "median": round(float(values.median()), 2) if len(values) > 0 else None,
                "std": round(float(values.std()), 2) if len(values) > 1 else None,
                "min": round(float(values.min()), 2) if len(values) > 0 else None,
                "max": round(float(values.max()), 2) if len(values) > 0 else None,
                "p25": round(float(values.quantile(0.25)), 2) if len(values) >= 4 else None,
                "p75": round(float(values.quantile(0.75)), 2) if len(values) >= 4 else None,
            },
        }

        # 样本
        samples = []
        for _, row in df.head(5).iterrows():
            samples.append({
                "species": row.get("plant_species", ""),
                "value": round(float(row.get(pm_col)), 2) if pd.notna(row.get(pm_col)) else None,
                "city": row.get("city", ""),
                "season": row.get("sampling_season", ""),
                "zone": row.get("functional_zone", ""),
                "paper": row.get("reference_short", ""),
                "notes": str(row.get("notes", ""))[:120] if pd.notna(row.get("notes")) else "",
            })
        stats["samples"] = samples

        # 动态警告
        stats["warnings"] = self._generate_warnings(df, pm_type, values)

        # 降级信息
        stats["degraded"] = degraded
        stats["relaxed_conditions"] = relaxed
        if degraded:
            original_desc = " · ".join(f"{k}={v}" for k, v in original_conditions.items() if v)
            actual_desc = ", ".join(
                f"{k}={params[k]}" for k in ["city", "season", "zone", "layer"]
                if params.get(k)
            ) if any(params.get(k) for k in ["city", "season", "zone", "layer"]) else "全国"
            stats["original_query"] = original_desc
            stats["actual_query"] = actual_desc or "全国(所有条件放宽)"

        return _numpy_to_native(stats)

    # ── 排名模式 ──────────────────────────────────────────
    def _query_rank(self, params):
        df = self.df.copy()
        pm_type = params.get("pm_type", "tsp")
        pm_col = f"{pm_type}_g_m2"

        # 过滤条件（不按species）
        for col, key in [("city", "city"), ("sampling_season", "season"),
                         ("functional_zone", "zone"), ("layer", "layer")]:
            if params.get(key):
                df = df[df[col] == params[key]]

        df = df[df[pm_col].notna()] if pm_col in df.columns else df[df["tsp_g_m2"].notna()]
        pm_col = pm_col if pm_col in df.columns else "tsp_g_m2"

        count = len(df)
        species_list = df["plant_species"].unique()
        species_count = len(species_list)

        min_samples = params.get("min_samples", 2)
        top_n = params.get("top_n", 10)

        # 按物种分组统计
        ranking = []
        excluded = []
        honorable = []
        for sp in species_list:
            sp_df = df[df["plant_species"] == sp]
            vals = sp_df[pm_col].dropna()
            n = len(vals)
            if n < min_samples:
                if n == 1 and len(vals) > 0 and vals.iloc[0] > df[pm_col].median():
                    honorable.append({
                        "species": sp, "median": round(float(vals.iloc[0]), 2),
                        "n": n,
                        "note": f"仅{n}条记录但数值较高，仅供参考"
                    })
                else:
                    excluded.append(f"{sp}({n}条)")
                continue
            ranking.append({
                "species": sp,
                "median": round(float(vals.median()), 2),
                "mean": round(float(vals.mean()), 2),
                "n": n,
            })

        # 按中位数降序
        ranking.sort(key=lambda x: x["median"], reverse=True)
        ranked = ranking[:top_n]
        for i, item in enumerate(ranked):
            item["rank"] = i + 1

        result = {
            "mode": "rank",
            "pm_type": pm_type,
            "count": count,
            "species_count": species_count,
            "ranking": ranked,  # 已瘦身: rank/species/median/mean/n
            "excluded_low_n": excluded[:8],
            "honorable_mentions": honorable[:3],
            "warnings": self._generate_warnings(df, pm_type, df[pm_col]),
            "degraded": False,
            "relaxed_conditions": [],
        }

        # 空结果降级
        if len(ranking) == 0:
            # 放宽逐级条件
            for key in ["season", "zone", "layer"]:
                if key in params and params[key]:
                    del params[key]
                    sub = self._query_rank(params)
                    if sub["ranking"]:
                        sub["degraded"] = True
                        sub["relaxed_conditions"] = [k for k in ["season", "zone", "layer"]
                                                      if k in params and k not in sub.get("relaxed", [])]
                        sub["original_query"] = f"rank: {params}"
                        sub["actual_query"] = "放宽条件后的查询"
                        return _numpy_to_native(sub)

        return _numpy_to_native(result)

    # ── 降级策略 ──────────────────────────────────────────
    def _degrade(self, params, original_conditions):
        """逐级放宽：season → zone → layer → species"""
        relax_order = ["season", "zone", "layer", "species"]
        df = self.df.copy()
        relaxed = []

        for key in relax_order:
            if key not in params or not params.get(key):
                continue
            old = params[key]
            params[key] = None
            relaxed.append(key)

            # 重新过滤
            df = self.df.copy()
            pm_col = f"{params.get('pm_type', 'tsp')}_g_m2"
            if pm_col not in df.columns:
                pm_col = "tsp_g_m2"
            df = df[df[pm_col].notna()]

            for col, pkey in [("city", "city"), ("sampling_season", "season"),
                              ("functional_zone", "zone"), ("layer", "layer")]:
                if params.get(pkey):
                    df = df[df[col] == params[pkey]]
            if params.get("species"):
                df = df[df["plant_species"].isin(params["species"])]

            if len(df) > 0:
                return df, True, relaxed
            params[key] = old  # 恢复，继续放宽下一个

        # 全放宽仍为空
        df = self.df.copy()
        _col = pm_col if pm_col in df.columns else "tsp_g_m2"
        df = df[df[_col].notna()]
        return df, True, relaxed

    # ── 动态警告 ──────────────────────────────────────────
    def _generate_warnings(self, df, pm_type, values):
        warnings_list = []

        # 离群论文警告
        for rule in self.warnings_config.get("outlier_papers", []):
            field = rule["field"]
            ref = rule["reference"]
            matched = df[df[field].astype(str).str.contains(ref, na=False)] if rule["match"] == "contains" else df[df[field] == ref]
            n = len(matched)
            if n == 0:
                continue
            # 额外条件
            if rule.get("condition"):
                if "value" in rule["condition"]:
                    threshold = float(rule["condition"].split(">")[-1].strip())
                    matched = matched[matched["tsp_g_m2"] > threshold]
                    n = len(matched)
                    if n == 0:
                        continue
            vals_matched = matched["tsp_g_m2"].dropna()
            max_val = float(vals_matched.max()) if len(vals_matched) > 0 else 0
            # 排除后的均值
            excluded_idx = matched.index
            remaining = df.drop(excluded_idx, errors="ignore")["tsp_g_m2"].dropna()
            adj_mean = float(remaining.mean()) if len(remaining) > 0 else 0
            adj_n = len(remaining)
            msg = rule["message_template"].format(n=n, max_val=max_val, adj_mean=adj_mean, adj_n=adj_n)
            warnings_list.append(msg)

        # 方法偏差警告
        for rule in self.warnings_config.get("method_bias", []):
            field = rule["field"]
            method = rule["method"]
            matched_series = df[field].astype(str).str.contains(method, na=False) if rule["match"] == "contains" else df[field] == method
            n = matched_series.sum()
            if n > 0:
                warnings_list.append(rule["message"].format(n=n))

        # 全局警告
        for rule in self.warnings_config.get("global_warnings", []):
            condition = rule.get("condition", "")
            n = len(values)
            if "pm_type in" in condition:
                if pm_type in ["pm10", "pm2_5"]:
                    warnings_list.append(rule["message"].format(count=n, pm_type=pm_type.upper()))
            elif "count < 5" in condition:
                if n < 5:
                    warnings_list.append(rule["message"].format(count=n))
            elif "构树" in condition:
                if "构树" in df["plant_species"].values and any(values == 0):
                    warnings_list.append(rule["message"])

        return warnings_list
