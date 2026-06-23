"""
随机场景多轮短句测试

目标：随机选择任意场景，进行多轮对话，并在对话中明确注入短句输入，
观察系统是否保持动态承接而非模板化回复。
"""

import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from schemas.context import Context
from modules.L5.scene_loader import load_scene_config


def debug_enabled() -> bool:
    return os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip().lower() in {"1", "true", "yes", "on"}


SCENE_PRELUDES = {
    "sales": [
        "我在对比你们和另外两家方案，担心买了之后落地不了。",
        "价格是一个方面，但我更怕团队用不起来。",
        "如果你是我，你会怎么判断这个投入值不值？",
    ],
    "management": [
        "团队最近状态下滑，我担心目标会失控。",
        "我不想再靠加班硬扛，想要一个可执行节奏。",
        "你先别讲大道理，给我一个本周能落地的动作。",
    ],
    "negotiation": [
        "这个条款我们压力很大，风险几乎都在我方。",
        "你给的条件离我们底线还有距离。",
        "你能不能给一个双方都能接受的折中方案？",
    ],
    "emotion": [
        "我最近一直紧绷，感觉快撑不住了。",
        "我知道要调整，但每次都卡在第一步。",
        "你说的我听进去了，但我现在还很乱。",
    ],
}

SHORT_PHRASES = ["嗯", "好", "可以", "收到", "行", "ok", "嗯嗯"]


def run_turn(runtime: EngineRuntime, ctx: Context, user_input: str):
    result = runtime.run_stream(
        EngineRequest(session_id=ctx.session_id, user_input=user_input, context=ctx)
    )
    return result.context or ctx, result.output, result.raw_result


def build_round_inputs(scene_id: str, rounds: int) -> list[str]:
    prelude = SCENE_PRELUDES.get(scene_id, SCENE_PRELUDES["sales"])
    inputs = []

    # 前两轮用正常上下文建立语境
    inputs.extend(prelude[:2])

    # 中间轮次注入短句
    while len(inputs) < max(3, rounds - 1):
        inputs.append(random.choice(SHORT_PHRASES))

    # 最后一轮给一个非短句收尾，观察承接结果
    inputs.append(prelude[-1])
    return inputs[:rounds]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3, help="随机会话数量")
    parser.add_argument("--rounds", type=int, default=7, help="每个会话轮数")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    random.seed(args.seed)
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    debug_mode = debug_enabled()

    scene_pool = ["sales", "management", "negotiation", "emotion"]

    print("=" * 100, flush=True)
    print("随机场景多轮短句测试", flush=True)
    print("=" * 100, flush=True)
    print(f"runs={args.runs}, rounds={args.rounds}, seed={args.seed}", flush=True)
    if debug_mode:
        print("当前为调试模式，会额外显示模式、目标、情绪等内部状态", flush=True)

    total_short = 0
    total_template_like = 0

    for run_idx in range(1, args.runs + 1):
        scene_id = random.choice(scene_pool)
        session_id = f"rand-short-{run_idx}-{int(time.time())}"
        ctx = Context(session_id=session_id)
        try:
            ctx.scene_config = load_scene_config(scene_id)
        except Exception:
            pass

        inputs = build_round_inputs(scene_id, args.rounds)

        print("\n" + "-" * 100, flush=True)
        print(f"会话 {run_idx} | 初始场景={scene_id}", flush=True)
        print("-" * 100, flush=True)

        for turn_idx, user_input in enumerate(inputs, 1):
            is_short = len(user_input.strip()) <= 3
            if is_short:
                total_short += 1

            ctx, output, raw = run_turn(runtime, ctx, user_input)

            template_like = output.strip() in {
                "好的。",
                "能再说详细一点吗？",
                "我听到了。你想继续聊这个，还是换个话题？",
            }
            if is_short and template_like:
                total_template_like += 1

            print(f"\n[第{turn_idx}轮] 用户: {user_input}", flush=True)
            print(f"  短句: {'是' if is_short else '否'} | 模板命中: {'是' if template_like else '否'}", flush=True)
            print(f"  系统: {output}", flush=True)
            if debug_mode:
                mode = raw.get("selected_mode", "")
                goal = getattr(ctx.goal, "granular_goal", "")
                primary_scene = ctx.primary_scene or (ctx.scene_config.scene_id if ctx.scene_config else "")
                emotion_type = ctx.user.emotion.type.value if hasattr(ctx.user.emotion.type, "value") else str(ctx.user.emotion.type)
                emotion_int = ctx.user.emotion.intensity
                print(f"  场景: {primary_scene} | 模式: {mode} | 目标: {goal}", flush=True)
                print(f"  情绪: {emotion_type}({emotion_int:.2f})", flush=True)

    print("\n" + "=" * 100, flush=True)
    print("汇总", flush=True)
    print("=" * 100, flush=True)
    print(f"短句总轮次: {total_short}", flush=True)
    if total_short > 0:
        rate = total_template_like / total_short
        print(f"短句模板命中轮次: {total_template_like}", flush=True)
        print(f"短句模板命中率: {rate:.1%}", flush=True)
    else:
        print("短句模板命中轮次: 0", flush=True)
        print("短句模板命中率: 0.0%", flush=True)


if __name__ == "__main__":
    main()
