# -*- coding: utf-8 -*-
"""
主线能力人工观察脚本

默认跑四个主场景的代表句，快速看系统现在是不是按“任务路由”在工作。
也支持只看某一个场景。
"""

import argparse
import os
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from graph.builder import build_graph
from schemas.context import Context
from modules.L5.scene_loader import load_scene_config


REPRESENTATIVE_CASES = {
    "sales": [
        "你们的价格太贵了，竞品便宜 30%",
        "客户说需要跟老板汇报，让我等",
    ],
    "management": [
        "领导对 AI 转型进度不满，但实际情况是技术债很重",
        "又是新工具，能不能消停会？",
    ],
    "negotiation": [
        "对方坚持 90 天账期，否则不签",
        "好的，我明白了。那接下来呢？",
    ],
    "emotion": [
        "我现在没精力想这么多。",
        "如果失败了怎么办，我现在真的很怕。",
    ],
}


def _scene_sub_intent(ctx: Context, scene_name: str) -> str:
    return getattr(ctx, f"{scene_name}_sub_intent", "") or "未识别"


def _run_case(graph, scene_name: str, user_input: str, idx: int) -> None:
    ctx = Context(session_id=f"mainline-capability-{scene_name}-{idx}")
    ctx.scene_config = load_scene_config(scene_name)
    ctx.primary_scene = scene_name

    result = graph.invoke({"context": ctx, "user_input": user_input})
    ctx = result.get("context", ctx)

    final_scene = ctx.primary_scene or (ctx.scene_config.scene_id if ctx.scene_config else "")
    sub_intent = _scene_sub_intent(ctx, scene_name)
    output = (result.get("output", "") or "").replace("\n", " | ")

    print("-" * 100)
    print(f"目标场景: {scene_name}")
    print(f"最终场景: {final_scene}")
    print(f"子意图:   {sub_intent}")
    print(f"用户输入: {user_input}")
    print(f"系统输出: {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--scene",
        choices=["sales", "management", "negotiation", "emotion", "all"],
        default="all",
        help="只看某一个主场景，默认全看",
    )
    args = parser.parse_args()

    graph = build_graph()
    scene_list = list(REPRESENTATIVE_CASES.keys()) if args.scene == "all" else [args.scene]

    print("=" * 100)
    print("主线能力人工观察")
    print("=" * 100)

    case_idx = 1
    for scene_name in scene_list:
        for user_input in REPRESENTATIVE_CASES[scene_name]:
            _run_case(graph, scene_name, user_input, case_idx)
            case_idx += 1

    print("-" * 100)
    print("观察结束")


if __name__ == "__main__":
    main()
