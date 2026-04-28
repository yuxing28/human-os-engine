# -*- coding: utf-8 -*-
"""
Human-OS Engine 3.0 — 交互式多轮对话测试

选择一个场景，手动输入，实时查看系统回复。
如需查看内部状态，可手动开启调试模式。
"""
import os
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from schemas.context import Context
from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from modules.L5.scene_loader import load_scene_config

SCENES = {
    "1": ("sales", "销售场景"),
    "2": ("management", "管理场景"),
    "3": ("negotiation", "谈判场景"),
    "4": ("emotion", "情感场景"),
}


def debug_enabled() -> bool:
    return os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip().lower() in {"1", "true", "yes", "on"}


def print_status(ctx, mode: str = ""):
    print(f"\n--- 当前状态 ---")
    print(f"  场景: {ctx.scene_config.scene_id if ctx.scene_config else 'None'}")
    print(f"  目标: {ctx.goal.granular_goal or '未识别'}")
    if mode:
        print(f"  模式: {mode}")
    else:
        print(f"  模式: {ctx.current_mode}")
    print(f"  情绪: {ctx.user.emotion.type}({ctx.user.emotion.intensity:.1f})")
    print(f"  信任: {ctx.user.trust_level}")
    print(f"  历史: {len(ctx.history)} 轮")

def main():
    debug_mode = debug_enabled()
    print("=" * 60)
    print("Human-OS Engine 3.0 — 交互式多轮对话测试")
    print("=" * 60)
    print()
    for k, (sid, name) in SCENES.items():
        print(f"  {k}. {name} ({sid})")
    print()
    
    choice = input("选择场景 (1-4): ").strip()
    scene_id, scene_name = SCENES.get(choice, ("sales", "销售场景"))
    
    print(f"\n已选择: {scene_name}")
    print("输入 'quit' 或 'exit' 退出")
    if debug_mode:
        print("输入 'status' 查看当前状态")
        print("当前为调试模式，会显示内部状态")
    else:
        print("当前为展示模式，只显示最终回复")
    print("-" * 60)
    
    # 初始化
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    ctx = Context(session_id=f"interactive-{scene_id}")
    ctx.scene_config = load_scene_config(scene_id)
    
    round_num = 0
    while True:
        print()
        user_input = input(f"[你] ").strip()
        
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("\n对话结束")
            break
        if user_input.lower() == "status":
            if debug_mode:
                print_status(ctx)
            else:
                print("\n展示模式下不显示内部状态。需要调试时请设置环境变量 HUMAN_OS_DEBUG_VIEW=1。")
            continue
        
        round_num += 1
        print(f"\n[系统思考中...]", end="", flush=True)
        
        try:
            engine_result = runtime.run_stream(
                EngineRequest(session_id=ctx.session_id, user_input=user_input, context=ctx)
            )
            result = engine_result.raw_result
            output = engine_result.output
            ctx = engine_result.context
            priority = result.get("priority", {})
            mode = result.get("selected_mode", "")
            
            print(f"\r{' ' * 20}\r")  # Clear thinking indicator
            print(f"\n--- 第 {round_num} 轮 ---")
            print(f"[系统] {output}")
            if debug_mode:
                print(f"\n[内部状态]")
                print(f"  场景: {ctx.scene_config.scene_id if ctx.scene_config else 'None'}")
                print(f"  目标: {ctx.goal.granular_goal or '未识别'} ({ctx.goal.display_name or ''})")
                print(f"  模式: {mode}")
                print(f"  优先级: {priority.get('priority_type', 'N/A')}")
                print(f"  情绪: {ctx.user.emotion.type}({ctx.user.emotion.intensity:.1f})")
                print(f"  信任: {ctx.user.trust_level}")
            
        except Exception as e:
            print(f"\r{' ' * 20}\r")
            print(f"\n[错误] {e}")

if __name__ == "__main__":
    main()
