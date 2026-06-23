"""
Human-OS Engine 3.0 - 入口文件

用法：
    python main.py              # 启动交互式对话
    python main.py --api        # 启动 FastAPI 服务
    python main.py --port 8080  # 指定端口启动 API
"""

import sys
import argparse
from rich.console import Console
from rich.panel import Panel

console = Console()


def run_interactive():
    """启动交互式对话"""
    from schemas.context import Context
    from graph.builder import build_graph
    from modules.engine_runtime import EngineRequest, EngineRuntime

    console.print(Panel.fit(
        "[bold blue]Human-OS Engine 3.0[/bold blue]\n"
        "[dim]目标导向 · 注意力驱动 · 平等博弈[/dim]",
        border_style="blue"
    ))

    # 构建 LangGraph 工作流
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)

    # 初始化 Context
    context = Context(session_id="interactive-001")

    console.print("\n[green]系统已就绪。输入 'quit' 退出。[/green]\n")

    # 交互循环
    while True:
        try:
            user_input = console.input("[bold cyan]你: [/bold cyan]")

            if user_input.lower() in ("quit", "exit", "q"):
                console.print("\n[yellow]再见。[/yellow]")
                break

            if not user_input.strip():
                continue

            engine_result = runtime.run_stream(
                EngineRequest(session_id=context.session_id, user_input=user_input, context=context)
            )

            # 输出系统回复
            output = engine_result.output or "（无输出）"
            console.print(f"\n[bold green]系统: [/bold green]{output}\n")

            # 更新 context
            context = engine_result.context

        except KeyboardInterrupt:
            console.print("\n\n[yellow]中断退出。[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]错误: {e}[/red]\n")


def run_api(port: int = 8000):
    """启动 FastAPI 服务"""
    import uvicorn
    from api.routes import app

    console.print(Panel.fit(
        f"[bold blue]Human-OS Engine API[/bold blue]\n"
        f"[dim]http://localhost:{port}[/dim]\n"
        f"[dim]文档: http://localhost:{port}/docs[/dim]",
        border_style="blue"
    ))

    uvicorn.run(app, host="0.0.0.0", port=port)


def main():
    parser = argparse.ArgumentParser(description="Human-OS Engine 3.0")
    parser.add_argument("--api", action="store_true", help="启动 FastAPI 服务")
    parser.add_argument("--port", type=int, default=8000, help="API 端口（默认 8000）")

    args = parser.parse_args()

    if args.api:
        run_api(args.port)
    else:
        run_interactive()


if __name__ == "__main__":
    main()
