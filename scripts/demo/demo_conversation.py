# -*- coding: utf-8 -*-
"""
Human-OS Engine 3.0 — 自动多轮对话演示

预定义对话脚本，自动运行并展示完整效果。
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from schemas.context import Context
from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from modules.L5.scene_loader import load_scene_config

# 对话脚本：情感场景 - 从冲突到修复
EMOTION_SCRIPT = [
    "你根本就不爱我，否则怎么可能忘了我们的纪念日？",
    "每次都是这样，你永远把工作放在第一位",
    "我觉得自己在你心里一点都不重要",
    "也许你说得对，我确实需要改变",
    "那我们现在该怎么办？",
]

# 对话脚本：销售场景
SALES_SCRIPT = [
    "你们的价格太贵了，竞品便宜 30%",
    "我需要跟老板汇报，你能给我一些数据支持吗？",
    "如果出了问题，你们能 guarantee SLA 吗？",
    "好吧，那我们先从小规模试点开始",
]

# 对话脚本：管理场景
MANAGEMENT_SCRIPT = [
    "我觉得自己不适合这份工作",
    "每天加班到很晚，身体快撑不住了",
    "团队里其他人也都有同样的感受",
    "你觉得我该怎么跟领导沟通这件事？",
]


def debug_enabled() -> bool:
    return os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip().lower() in {"1", "true", "yes", "on"}

def run_demo(scene_id: str, script: list[str], scene_name: str):
    debug_mode = debug_enabled()
    print("=" * 70)
    print(f"  {scene_name} 多轮对话演示 ({len(script)} 轮)")
    print("=" * 70)
    if debug_mode:
        print("  当前为调试模式，会额外显示内部状态")
        print()
    print()
    
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    ctx = Context(session_id=f"demo-{scene_id}")
    ctx.scene_config = load_scene_config(scene_id)
    
    for i, user_input in enumerate(script, 1):
        print(f"{'─' * 70}")
        print(f"  第 {i}/{len(script)} 轮")
        print(f"{'─' * 70}")
        print(f"\n[用户] {user_input}")
        print(f"\n[系统思考中...]", end="", flush=True)
        
        try:
            engine_result = runtime.run_stream(
                EngineRequest(session_id=ctx.session_id, user_input=user_input, context=ctx)
            )
            result = engine_result.raw_result
            output = engine_result.output
            ctx = engine_result.context
            
            print(f"\r{' ' * 20}\r")
            
            print(f"\n[系统回复]")
            # 格式化输出，每行缩进
            for line in output.split('\n'):
                print(f"  {line}")

            if debug_mode:
                mode = result.get("selected_mode", "")
                priority = result.get("priority", {})
                print(f"\n[内部状态]")
                print(f"  场景: {ctx.scene_config.scene_id}")
                print(f"  目标: {ctx.goal.granular_goal or '未识别'} ({ctx.goal.display_name or ''})")
                print(f"  模式: {mode}")
                print(f"  优先级: {priority.get('priority_type', 'N/A')}")
                print(f"  情绪: {ctx.user.emotion.type}({ctx.user.emotion.intensity:.1f})")
                print(f"  信任: {ctx.user.trust_level}")
            
        except Exception as e:
            print(f"\r{' ' * 20}\r")
            print(f"\n[错误] {e}")
        
        print()
    
    # 最终汇总
    print("=" * 70)
    print("  对话总结")
    print("=" * 70)
    print(f"  总轮数: {len(script)}")
    print(f"  历史条数: {len(ctx.history)}")
    if debug_mode:
        print(f"  最终目标: {ctx.goal.granular_goal or '未识别'}")
        print(f"  最终情绪: {ctx.user.emotion.type}({ctx.user.emotion.intensity:.1f})")
        print(f"  最终信任: {ctx.user.trust_level}")
    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="自动多轮对话演示")
    parser.add_argument("--scene", default="all", choices=["sales", "management", "emotion", "all"])
    args = parser.parse_args()
    
    demos = {
        "sales": ("销售场景", SALES_SCRIPT),
        "management": ("管理场景", MANAGEMENT_SCRIPT),
        "emotion": ("情感场景", EMOTION_SCRIPT),
    }
    
    if args.scene == "all":
        for sid, (name, script) in demos.items():
            run_demo(sid, script, name)
    else:
        name, script = demos[args.scene]
        run_demo(args.scene, script, name)
