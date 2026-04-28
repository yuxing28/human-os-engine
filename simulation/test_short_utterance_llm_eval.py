"""
短词场景 LLM 评测脚本

目标：验证短词输入（嗯/好/可以/收到）在不同上下文下是否仍能动态输出，
并通过 LLMJudge 做质量评估。
"""

import argparse
import os
import sys
import time
from statistics import mean

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from schemas.context import Context
from modules.L5.scene_loader import load_scene_config
from simulation.llm_judge import LLMJudge
from simulation.customer_agent import Persona


TEMPLATE_LIKE = {
    "好的。",
    "能再说详细一点吗？",
    "我听到了。你想继续聊这个，还是换个话题？",
}


def run_turn(runtime: EngineRuntime, ctx: Context, user_input: str) -> tuple[Context, str]:
    result = runtime.run_stream(
        EngineRequest(session_id=ctx.session_id, user_input=user_input, context=ctx)
    )
    return result.context or ctx, result.output


def build_persona() -> Persona:
    return Persona(
        name="短词测试客户",
        role="业务负责人",
        age=33,
        personality="理性但敏感，重视上下文连贯和专业度",
        hidden_agenda="希望对方真正理解我的状态，而不是套话",
        budget_range="20-40万",
        pain_points=["沟通低效", "决策焦虑"],
        trigger_words=["具体", "下一步", "风险"],
        dealbreakers=["模板化回复", "答非所问"],
        product="咨询服务",
    )


def scenario_data():
    return [
        {
            "name": "销售推进后的短确认",
            "scene": "sales",
            "prelude": [
                "我现在最担心的是这事落地不了，投入以后没有结果。",
                "你说的方案听起来还行，但我对执行细节还是没底。",
            ],
            "short_input": "嗯",
        },
        {
            "name": "高情绪后的短回应",
            "scene": "emotion",
            "prelude": [
                "我最近整个人都绷着，真的快扛不住了。",
                "你刚才那句我能理解，但我还是很乱。",
            ],
            "short_input": "好",
        },
        {
            "name": "谈判僵持后的短回应",
            "scene": "negotiation",
            "prelude": [
                "这个条件我们很难接受，风险都在我们这边。",
                "你再说一个双方都能接受的方案。",
            ],
            "short_input": "可以",
        },
        {
            "name": "管理压力后的短确认",
            "scene": "management",
            "prelude": [
                "团队最近状态很差，我担心再这样下去会失控。",
                "我需要一个可执行的节奏，不是口号。",
            ],
            "short_input": "收到",
        },
    ]


def estimate_trust(ctx: Context) -> float:
    try:
        val = ctx.user.trust_level.value if hasattr(ctx.user.trust_level, "value") else str(ctx.user.trust_level)
        if val == "high":
            return 0.8
        if val == "low":
            return 0.2
        return 0.5
    except Exception:
        return 0.5


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="仅运行2个轻量场景")
    args = parser.parse_args()

    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    judge = LLMJudge()
    persona = build_persona()

    scenarios = scenario_data()
    if args.quick:
        scenarios = scenarios[:2]

    rows = []

    print("=" * 90, flush=True)
    print("短词场景 LLM 评测", flush=True)
    print("=" * 90, flush=True)

    for idx, sc in enumerate(scenarios, 1):
        ctx = Context(session_id=f"short-llm-{idx}-{int(time.time())}")
        try:
            ctx.scene_config = load_scene_config(sc["scene"])
        except Exception:
            pass

        print(f"\n[准备] 场景{idx}: {sc['name']}", flush=True)
        prelude = sc["prelude"][:1] if args.quick else sc["prelude"]
        for text in prelude:
            ctx, _ = run_turn(runtime, ctx, text)

        print(f"[执行] 场景{idx}: 注入短词 `{sc['short_input']}`", flush=True)
        ctx, output = run_turn(runtime, ctx, sc["short_input"])

        trust = estimate_trust(ctx)
        emotion = getattr(ctx.user.emotion, "intensity", 0.5) or 0.5

        print(f"[评测] 场景{idx}: 调用 LLMJudge", flush=True)
        eval_result = judge.evaluate(
            persona,
            sc["short_input"],
            output,
            {"trust": trust, "emotion": emotion},
        )

        template_like = output.strip() in TEMPLATE_LIKE
        row = {
            "scenario": sc["name"],
            "scene": sc["scene"],
            "short_input": sc["short_input"],
            "output": output,
            "len": len(output),
            "template_like": template_like,
            "trust_delta": eval_result.get("trust_delta", 0.0),
            "emotion_delta": eval_result.get("emotion_delta", 0.0),
            "reason": eval_result.get("reason", ""),
        }
        rows.append(row)

        print(f"\n[{idx}] {row['scenario']} ({row['scene']})", flush=True)
        print(f"  用户短词: {row['short_input']}", flush=True)
        print(f"  系统输出: {row['output']}", flush=True)
        print(f"  模板命中: {'是' if row['template_like'] else '否'}", flush=True)
        print(
            f"  LLM评估: trust_delta={row['trust_delta']:+.2f}, emotion_delta={row['emotion_delta']:+.2f}",
            flush=True,
        )
        print(f"  评估理由: {row['reason']}", flush=True)

    outputs = [r["output"] for r in rows if r["output"]]
    unique_ratio = (len(set(outputs)) / len(outputs)) if outputs else 0.0
    template_rate = (sum(1 for r in rows if r["template_like"]) / len(rows)) if rows else 1.0
    avg_trust = mean([r["trust_delta"] for r in rows]) if rows else 0.0

    print("\n" + "=" * 90, flush=True)
    print("汇总", flush=True)
    print("=" * 90, flush=True)
    print(f"样本数: {len(rows)}", flush=True)
    print(f"模板命中率: {template_rate:.1%}", flush=True)
    print(f"输出多样性比率(唯一输出/总输出): {unique_ratio:.1%}", flush=True)
    print(f"平均 trust_delta: {avg_trust:+.2f}", flush=True)

    passed = template_rate <= 0.25 and unique_ratio >= 0.75
    print(
        f"结论: {'PASS 通过（短词已表现出动态承接）' if passed else 'WARN 需继续优化'}",
        flush=True,
    )


if __name__ == "__main__":
    main()
