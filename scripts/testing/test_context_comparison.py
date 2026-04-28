# -*- coding: utf-8 -*-
"""
Human-OS Engine 3.0 — 上下文优化前后对比测试

测试方法：
1. 用同一个输入 + 同一个场景配置
2. 分别用旧版（long_term_memory）和新版（unified_context）注入 Prompt
3. 让 LLM-as-Judge 对两个回复打分
4. 输出对比结果
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import time
from schemas.context import Context
from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from modules.L5.scene_loader import load_scene_config
from modules.memory import store_memory
from llm.nvidia_client import invoke_deep

# 测试用例：覆盖 4 个场景
TEST_CASES = [
    {
        "scene": "emotion",
        "input": "你根本就不爱我，否则怎么可能忘了我们的纪念日？",
        "desc": "情感场景-关系冲突",
    },
    {
        "scene": "sales",
        "input": "你们的价格太贵了，竞品便宜 30%",
        "desc": "销售场景-价格异议",
    },
    {
        "scene": "management",
        "input": "我觉得自己不适合这份工作",
        "desc": "管理场景-员工自我怀疑",
    },
    {
        "scene": "negotiation",
        "input": "这个价格我们接受不了，最多只能给 70%",
        "desc": "谈判场景-价格谈判",
    },
]

# LLM-as-Judge 对比 Prompt
JUDGE_PROMPT = """你是一个对话质量评估专家。请对比两个系统回复的质量。

用户输入：{user_input}

【旧版回复】（只用长期记忆字符串）
{old_output}

【新版回复】（统一上下文：画像+状态+笔记+记忆+经验）
{new_output}

评估维度（1-10分）：
1. 相关性：回复是否与用户输入直接相关
2. 共情度：是否理解并回应了用户需求
3. 专业性：回复是否专业、得体
4. 个性化：是否体现了对用户历史/状态的了解
5. 引导性：是否有效引导对话推进

请输出 JSON：
{{
  "old_scores": {{"relevance": 0, "empathy": 0, "professionalism": 0, "personalization": 0, "guidance": 0}},
  "new_scores": {{"relevance": 0, "empathy": 0, "professionalism": 0, "personalization": 0, "guidance": 0}},
  "old_total": 0,
  "new_total": 0,
  "winner": "old/new/tie",
  "reason": "一句话说明为什么新版更好/更差/持平"
}}"""


def run_with_old_context(scene_id: str, user_input: str) -> str:
    """用旧版方式运行（只用 long_term_memory）"""
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    ctx = Context(session_id=f"old-{scene_id}-{int(time.time())}")
    ctx.scene_config = load_scene_config(scene_id)

    # 注入一些测试记忆
    store_memory(ctx.session_id, f"用户之前提到过对{scene_id}场景的关注", importance=0.6)

    engine_result = runtime.run_stream(
        EngineRequest(session_id=ctx.session_id, user_input=user_input, context=ctx)
    )
    return engine_result.output, engine_result.context


def run_with_new_context(scene_id: str, user_input: str) -> str:
    """用新版方式运行（unified_context）"""
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    ctx = Context(session_id=f"new-{scene_id}-{int(time.time())}")
    ctx.scene_config = load_scene_config(scene_id)

    # 注入相同的测试记忆
    store_memory(ctx.session_id, f"用户之前提到过对{scene_id}场景的关注", importance=0.6)

    engine_result = runtime.run_stream(
        EngineRequest(session_id=ctx.session_id, user_input=user_input, context=ctx)
    )
    return engine_result.output, engine_result.context


def judge_comparison(user_input: str, old_output: str, new_output: str) -> dict:
    """LLM-as-Judge 对比评分"""
    prompt = JUDGE_PROMPT.format(
        user_input=user_input[:200],
        old_output=old_output[:300],
        new_output=new_output[:300],
    )

    try:
        result = invoke_deep(prompt, "你是专业的对话质量评估专家。")
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        if result.startswith("json"):
            result = result[4:].strip()
        return json.loads(result)
    except Exception as e:
        return {"error": str(e)}


def main():
    print("=" * 70)
    print("  上下文优化前后对比测试")
    print("=" * 70)

    results = []

    for i, tc in enumerate(TEST_CASES, 1):
        scene = tc["scene"]
        user_input = tc["input"]
        desc = tc["desc"]

        print(f"\n{'─' * 70}")
        print(f"  测试 {i}/{len(TEST_CASES)}: {desc} ({scene})")
        print(f"{'─' * 70}")
        print(f"\n用户输入: {user_input}")

        # 旧版
        print(f"\n[旧版运行中...]", end="", flush=True)
        old_output, old_ctx = run_with_old_context(scene, user_input)
        print(f"\r{' ' * 20}\r")
        print(f"旧版回复: {old_output[:150]}...")

        # 新版
        print(f"\n[新版运行中...]", end="", flush=True)
        new_output, new_ctx = run_with_new_context(scene, user_input)
        print(f"\r{' ' * 20}\r")
        print(f"新版回复: {new_output[:150]}...")

        # LLM 对比评分
        print(f"\n[LLM 对比评分中...]", end="", flush=True)
        judge = judge_comparison(user_input, old_output, new_output)
        print(f"\r{' ' * 20}\r")

        if "error" in judge:
            print(f"  ⚠️ 评分失败: {judge['error']}")
        else:
            old_total = judge.get("old_total", 0)
            new_total = judge.get("new_total", 0)
            winner = judge.get("winner", "?")
            reason = judge.get("reason", "")

            icon = "✅" if winner == "new" else ("❌" if winner == "old" else "⚖️")
            print(f"  {icon} 旧版: {old_total}/50 | 新版: {new_total}/50 | 胜者: {winner}")
            print(f"  理由: {reason}")

        results.append({
            "scene": scene,
            "desc": desc,
            "judge": judge,
            "old_output_len": len(old_output),
            "new_output_len": len(new_output),
        })

    # 汇总
    print(f"\n{'=' * 70}")
    print("  汇总结果")
    print(f"{'=' * 70}")

    new_wins = sum(1 for r in results if r.get("judge", {}).get("winner") == "new")
    old_wins = sum(1 for r in results if r.get("judge", {}).get("winner") == "old")
    ties = sum(1 for r in results if r.get("judge", {}).get("winner") == "tie")
    errors = sum(1 for r in results if "error" in r.get("judge", {}))

    print(f"\n  新版胜出: {new_wins}/{len(TEST_CASES)}")
    print(f"  旧版胜出: {old_wins}/{len(TEST_CASES)}")
    print(f"  持平: {ties}/{len(TEST_CASES)}")
    print(f"  评分失败: {errors}/{len(TEST_CASES)}")

    if new_wins > old_wins:
        print(f"\n  ✅ 结论：新版统一上下文整体优于旧版")
    elif new_wins == old_wins:
        print(f"\n  ⚖️ 结论：新版与旧版持平")
    else:
        print(f"\n  ❌ 结论：新版不如旧版，需要优化")

    # 详细对比
    print(f"\n{'─' * 70}")
    print("  详细对比")
    print(f"{'─' * 70}")
    for r in results:
        j = r.get("judge", {})
        if "error" not in j:
            print(f"\n  [{r['scene']}] {r['desc']}")
            print(f"    旧版: {j.get('old_scores', {})} (总分: {j.get('old_total', 0)})")
            print(f"    新版: {j.get('new_scores', {})} (总分: {j.get('new_total', 0)})")
            print(f"    胜者: {j.get('winner', '?')} | 理由: {j.get('reason', '')}")


if __name__ == "__main__":
    main()
