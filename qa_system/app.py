"""
Web 演示入口 — Streamlit，会议室投屏/局域网访问。
启动: streamlit run qa_system/app.py --server.address 0.0.0.0 --server.port 8501
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
from qa_system.qa_bot import QABot

st.set_page_config(page_title="植物滞尘分析", page_icon="🌿", layout="wide")

# 标题
st.title("🌿 植物叶片滞尘数据分析助手")
st.caption("基于 1104 条实测数据 | Qwen2.5-7B 本地推理 | 全程离线")

# ── 初始化 ──
if "bot" not in st.session_state:
    try:
        st.session_state.bot = QABot()
    except Exception as e:
        st.error(f"无法初始化 QABot: {e}")
        st.stop()
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_question" not in st.session_state:
    st.session_state.pending_question = None

# ── 处理待处理问题（来自侧边栏按钮） ──
if st.session_state.pending_question:
    q = st.session_state.pending_question
    st.session_state.pending_question = None
    with st.chat_message("assistant"):
        try:
            response_stream = st.session_state.bot.chat_stream(q)
            full_response = st.write_stream(response_stream)
        except Exception as e:
            full_response = f"⚠️ 错误: {e}"
            st.error(full_response)
    st.session_state.messages.append({"role": "assistant", "content": full_response})
    st.rerun()

# ── 侧边栏：黄金问题 ──
with st.sidebar:
    st.header("🎯 演示预设问题")
    golden = [
        ("精准统计", "南京冬季香樟的TSP滞尘量是多少？"),
        ("模糊匹配", "法桐在杭州全年的滞尘表现如何？"),
        ("智能降级", "武汉冬季居住区桂花的数据"),
        ("跨物种排名", "南京道路绿地种植什么乔木滞尘效果比较好？"),
        ("动态警告", "对比桂花和香樟在南京的全年滞尘能力"),
    ]
    for label, q in golden:
        if st.button(f"**{label}**：{q[:20]}…", use_container_width=True):
            if not st.session_state.messages or st.session_state.messages[-1].get("content") != q:
                st.session_state.messages.append({"role": "user", "content": q})
                st.session_state.pending_question = q
                st.rerun()

    st.divider()
    col1, col2 = st.columns(2)
    col1.metric("📊 数据集", "1,104 条")
    col2.metric("🌳 物种", "169 种")

    if st.button("🗑️ 清空对话历史", use_container_width=True):
        st.session_state.messages = []
        st.session_state.bot.reset()
        st.rerun()

# ── 聊天历史 ──
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg.get("content", ""))

# ── 用户输入 ──
if prompt := st.chat_input("请输入您的问题…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        try:
            response_stream = st.session_state.bot.chat_stream(prompt)
            full_response = st.write_stream(response_stream)
        except Exception as e:
            full_response = f"⚠️ 错误: {e}"
            st.error(full_response)

    st.session_state.messages.append({"role": "assistant", "content": full_response})
