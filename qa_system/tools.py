"""
Tool Calling Schema — OpenAI 格式，Ollama 原生解析。
query_engine 提供两种查询模式：stats(统计) / rank(排名)。
"""
QUERY_TOOL = {
    "type": "function",
    "function": {
        "name": "query_dust_retention",
        "description": (
            "查询植物叶片滞尘数据，返回指定条件下的统计摘要或跨物种排名。\n"
            "支持两种模式：\n"
            "- stats: 给定物种的统计摘要（均值/中位数/范围/样本）\n"
            "- rank: 不指定物种时的跨物种排名（TOP N，按中位数排序）"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["stats", "rank"],
                    "description": "查询模式。stats=给定物种的统计摘要(默认)；rank=不指定物种时按物种分组排名",
                },
                "species": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "植物中文名或拉丁名，如['香樟','桂花']。stats模式必填，rank模式留空",
                },
                "city": {
                    "type": "string",
                    "description": "城市名，如'南京'、'杭州'。留空=不限城市",
                },
                "season": {
                    "type": "string",
                    "enum": ["春季", "夏季", "秋季", "冬季", "全年", "秋冬", "全年最大"],
                    "description": "采样季节。留空=不限季节",
                },
                "zone": {
                    "type": "string",
                    "enum": [
                        "交通干道", "道路绿地", "公园清洁区", "城市混合",
                        "居住区", "工业区", "文教区", "室内模拟",
                    ],
                    "description": "功能区类型。留空=不限功能区",
                },
                "layer": {
                    "type": "string",
                    "enum": ["乔木", "灌木", "草本", "地被", "藤木"],
                    "description": "植物层次。留空=不限层次",
                },
                "pm_type": {
                    "type": "string",
                    "enum": ["tsp", "pm10", "pm2_5"],
                    "description": "颗粒物类型。不指定时默认tsp（总悬浮颗粒物）",
                },
                "days_after_rain": {
                    "type": "string",
                    "description": "雨后天数，如'7'或'3-7'。留空=不限",
                },
                "top_n": {
                    "type": "integer",
                    "default": 10,
                    "description": "排名模式返回前N个物种，默认10",
                },
                "min_samples": {
                    "type": "integer",
                    "default": 2,
                    "description": "排名模式下每个物种最少样本数，默认2(排除单条极端值)",
                },
            },
            "required": [],
        },
    },
}
