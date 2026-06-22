"""
QABot — 对话管理，Ollama HTTP 客户端。
提供 chat() 和 chat_stream() 两个接口，供终端和 Web 共用。
"""
import json
import ollama

from .tools import QUERY_TOOL
from .query_engine import QueryEngine

MODEL = "qwen2.5:7b-instruct-q4_K_M"
MODEL_FALLBACK = "qwen2.5:3b-instruct-q8_0"
OLLAMA_OPTS = {"num_ctx": 8192}

SYSTEM_PROMPT = """你是植物叶片滞尘数据分析助手，基于长江流域亚热带城市实测数据集（1104条记录、19城市、~169物种）回答问题。

## 核心规则
1. 必须通过 query_dust_retention 函数查询数据后再回答，禁止编造任何数值。
2. 对于任何涉及数据查询、统计、排名的请求，必须重新调用 query_dust_retention，严禁复用历史工具返回结果。
3. 如果查询结果 count=0 且 degraded=true，必须明确告知用户"未找到[原条件]的数据，以下为放宽条件后的结果"。
4. 如果查询返回 warnings，必须在回答中呈现关键的警告信息。

## 输出规范
- 所有滞尘量单位统一为 **g/m²**（克/平方米叶面积），严禁写成 mg/m²、mg/cm² 等其他单位。
- 先给出统计摘要（均值/中位数/范围/样本量）
- 再列出注意事项和警告
- 最后如有数据局限性，加以说明

## 已知全局局限
- PM10数据仅80条，PM2.5数据仅89条，远少于TSP(>1000条)，统计结论置信度有限。
- 构树冬季落叶期TSP=0，数据有效但需标注物候原因。
- 数据集覆盖长江流域亚热带城市19个，黄河流域城市(郑州/洛阳)已标记排除。
"""


class QABot:
    def __init__(self, model=None):
        self.model = model or MODEL
        self.engine = QueryEngine()
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def reset(self):
        """清空对话历史"""
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    def chat(self, prompt):
        """完整对话（阻塞式，返回最终回答文本）"""
        return "".join(self.chat_stream(prompt))

    def chat_stream(self, prompt):
        """流式对话——分两轮：Tool Call提取参数 + 总结回答"""
        self.messages.append({"role": "user", "content": prompt})

        try:
            # 第一轮：Tool Call（非流式）
            response = ollama.chat(
                model=self.model,
                messages=self.messages,
                tools=[QUERY_TOOL],
                options=OLLAMA_OPTS,
            )
        except Exception as e:
            yield f"\n[错误: 无法连接Ollama — {e}]\n"
            return

        # 无 tool_call：普通对话
        if not response.message.tool_calls:
            self.messages.append(response.message)
            try:
                for chunk in ollama.chat(
                    model=self.model,
                    messages=self.messages,
                    stream=True,
                    options=OLLAMA_OPTS,
                ):
                    yield chunk["message"]["content"]
            except Exception:
                yield response.message.content or ""
            return

        # 提取参数并查询
        tool_call = response.message.tool_calls[0]
        try:
            params = tool_call.function.arguments
        except AttributeError:
            # 旧版 ollama SDK 返回 dict
            params = tool_call["function"]["arguments"]

        if isinstance(params, str):
            try:
                params = json.loads(params)
            except json.JSONDecodeError:
                yield f"\n[错误: 参数解析失败 — {params[:100]}]\n"
                return

        result = self.engine.query(params)

        # 构建 tool response
        self.messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [tool_call] if hasattr(tool_call, 'function') else [{
                "function": {"name": tool_call["function"]["name"],
                             "arguments": tool_call["function"]["arguments"]}
            }],
        })
        self.messages.append({
            "role": "tool",
            "content": json.dumps(result, ensure_ascii=False,
                                  default=lambda o: o.item() if hasattr(o, "item") else str(o)),
            "name": "query_dust_retention",
        })

        # 第二轮：流式总结
        full = ""
        try:
            for chunk in ollama.chat(
                model=self.model,
                messages=self.messages,
                stream=True,
                options=OLLAMA_OPTS,
            ):
                token = chunk["message"]["content"]
                full += token
                yield token
        except Exception as e:
            if not full:
                yield f"\n[错误: 总结生成失败 — {e}]\n"

        # 保存 assistant 的回答到历史
        self.messages.append({"role": "assistant", "content": full})

    def test_tool_calling(self, questions):
        """批量测试 Tool Calling 稳定性，返回成功率"""
        success = 0
        for i, q in enumerate(questions):
            try:
                response = ollama.chat(
                    model=self.model,
                    messages=[{"role": "system", "content": SYSTEM_PROMPT},
                              {"role": "user", "content": q}],
                    tools=[QUERY_TOOL],
                    options=OLLAMA_OPTS,
                )
                if response.message.tool_calls:
                    success += 1
                else:
                    print(f"  #{i+1} 未触发 tool_call: {q[:40]}...")
            except Exception as e:
                print(f"  #{i+1} 错误: {e}")
        return success / len(questions) if questions else 0
