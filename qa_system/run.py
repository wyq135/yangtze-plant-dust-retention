"""
终端 REPL 入口 — rich 美化，开发/调试用。
启动: python qa_system/run.py  或  python -m qa_system.run
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import ollama
from rich.console import Console
from rich.markdown import Markdown
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

from qa_system.qa_bot import QABot, MODEL

console = Console()

# ── 启动健康检查 ──
def check_ollama():
    try:
        models = ollama.list()
        if not any(m.model.startswith("qwen2.5:7b") for m in models.models):
            console.print(f"[red]未找到模型 {MODEL}[/red]")
            console.print(f"[yellow]请运行: ollama pull {MODEL}[/yellow]")
            return False
        console.print(f"[green]✓ Ollama 已连接，{MODEL} 就绪[/green]")
        return True
    except Exception:
        console.print("[red]无法连接 Ollama 服务[/red]")
        console.print("[yellow]请确保已安装并启动 Ollama (ollama serve)[/yellow]")
        return False


def show_help():
    t = Table(title="命令速查")
    t.add_column("命令", style="cyan")
    t.add_column("说明")
    t.add_row("/help", "显示此帮助")
    t.add_row("/stats", "数据集全局统计")
    t.add_row("/reset", "清空对话历史")
    t.add_row("/model", "显示当前模型")
    t.add_row("Ctrl+C", "退出")
    console.print(t)


def show_stats(engine):
    df = engine.df
    t = Table(title="数据集概况")
    t.add_column("指标")
    t.add_column("值")
    t.add_row("总记录", str(len(df)))
    t.add_row("物种数", str(df["plant_species"].nunique()))
    t.add_row("城市数", str(df["city"].nunique()))
    t.add_row("TSP有效值", str(df["tsp_g_m2"].notna().sum()))
    t.add_row("PM10有效值", str(df["pm10_g_m2"].notna().sum()))
    t.add_row("PM2.5有效值", str(df["pm2_5_g_m2"].notna().sum()))
    t.add_row("功能区类型", str(df["functional_zone"].nunique()))
    t.add_row("TSP中位数", f"{df['tsp_g_m2'].median():.2f} g/m²")
    console.print(t)


def main():
    console.print(Panel("🌿 植物叶片滞尘数据分析助手", subtitle="基于 Qwen2.5-7B + Ollama"))

    if not check_ollama():
        return

    bot = QABot()
    console.print("\n[dim]输入问题开始对话，/help 查看命令。Ctrl+C 退出。[/dim]\n")

    while True:
        try:
            user_input = console.input("[bold cyan]你[/]: ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]再见。[/dim]")
            break

        if not user_input:
            continue

        # 命令处理
        if user_input.startswith("/"):
            cmd = user_input.split()[0].lower()
            if cmd == "/help":
                show_help()
            elif cmd == "/stats":
                show_stats(bot.engine)
            elif cmd == "/reset":
                bot.reset()
                console.print("[green]对话历史已清空[/green]")
            elif cmd == "/model":
                console.print(f"当前模型: [bold]{bot.model}[/bold]")
            else:
                console.print(f"[yellow]未知命令: {cmd}[/yellow]")
            continue

        # 正常对话
        console.print("\n[bold green]🌿 助手[/]: ", end="")
        full_text = ""
        try:
            with Live("", refresh_per_second=10, vertical_overflow="visible") as live:
                for token in bot.chat_stream(user_input):
                    full_text += token
                    live.update(Markdown(full_text))
        except Exception as e:
            console.print(f"\n[red]错误: {e}[/red]")
        console.print()


if __name__ == "__main__":
    main()
