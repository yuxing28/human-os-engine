# -*- coding: utf-8 -*-
"""
雷军扩展包 A/B 对比测试

这套脚本只做一件事：
同一条输入，分别跑
1. 默认主系统
2. 默认主系统 + 指定雷军扩展

然后把结果落成 json + markdown。
"""

from __future__ import annotations

import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import argparse
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import os
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
except Exception:
    pass

from graph.builder import build_graph
from llm.nvidia_client import invoke_deep
from modules.engine_runtime import EngineRequest, EngineRuntime
from modules.L5.extension_pack_loader import build_extension_pack_prompt
from modules.L5.scene_loader import load_scene_config
from modules.L5.skill_registry import get_registry
from schemas.context import Context


OUTPUT_DIR = PROJECT_ROOT / "data" / "leijun_ab_tests"

DEFAULT_CASES = [
    {
        "id": "decision_anchor",
        "scene": "management",
        "desc": "管理决策：事情很多，但真正先抓哪一件",
        "user_input": "最近事情特别多，团队、老板、项目都在拉我，我现在最怕的是每件都顾一点，最后什么都没推进。你说我到底先抓哪一件？",
        "packs": ["leijun_persona_core", "leijun_decision"],
    },
    {
        "id": "product_tradeoff",
        "scene": "sales",
        "desc": "产品取舍：价值、价格、体验怎么说得更清楚",
        "user_input": "客户一直说我们价格高，但我又不想把话说成单纯便宜和贵。怎么讲，既不虚，也不把价值说散？",
        "packs": ["leijun_persona_core", "leijun_product", "leijun_communication"],
    },
    {
        "id": "management_alignment",
        "scene": "management",
        "desc": "带人推进：标准高，但不能把团队压散",
        "user_input": "我知道团队现在状态一般，但事情又不能慢下来。我不想变成只会压人的管理者，可也不能什么都往后拖。怎么带？",
        "packs": ["leijun_persona_core", "leijun_management", "leijun_communication"],
    },
    {
        "id": "recap_reset",
        "scene": "negotiation",
        "desc": "复盘重整：谈崩之后怎么收回来",
        "user_input": "这轮谈判其实没拿到结果，我最怕的是团队现在只会互相怪。怎么复盘，才能让下一轮更稳一点？",
        "packs": ["leijun_persona_core", "leijun_decision", "leijun_recap"],
    },
]


@dataclass
class RunResult:
    scene: str
    output: str
    elapsed_ms: int
    skill_prompt: str


def _extract_json_block(text: str) -> str:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("LLM 评审结果里没有找到 JSON")
    return match.group(0)


def _normalize_judge_payload(raw: dict[str, Any]) -> dict[str, Any]:
    preferred = str(raw.get("preferred_version", "")).strip().lower()
    if preferred not in {"baseline", "experiment", "tie"}:
        preferred = "tie"

    return {
        "preferred_version": preferred,
        "score_baseline": int(raw.get("score_baseline", 0) or 0),
        "score_experiment": int(raw.get("score_experiment", 0) or 0),
        "more_like_leijun": bool(raw.get("more_like_leijun", False)),
        "too_hard_or_performance_like": bool(raw.get("too_hard_or_performance_like", False)),
        "steals_main_system_judgment": bool(raw.get("steals_main_system_judgment", False)),
        "summary": str(raw.get("summary", "")).strip(),
        "strengths": [str(x).strip() for x in raw.get("strengths", []) if str(x).strip()][:5],
        "risks": [str(x).strip() for x in raw.get("risks", []) if str(x).strip()][:5],
        "suggestion": str(raw.get("suggestion", "")).strip(),
        "raw_text": str(raw.get("raw_text", "")).strip(),
    }


def evaluate_with_llm(
    scene: str,
    user_input: str,
    packs: list[str],
    baseline_output: str,
    experiment_output: str,
) -> dict[str, Any]:
    judge_prompt = f"""
你现在是一个严格但讲人话的评审员。你要判断“默认主系统输出”和“主系统+雷军扩展输出”谁更好。

评审标准只看这几件事：
1. 有没有更清楚地抓住主线
2. 有没有更像雷军式的方法：真诚、直接、讲清为什么、抓重点、做收敛
3. 有没有变成模仿秀、太硬、太像表演人格
4. 有没有抢主系统的判断位置，导致不像辅助层

场景：{scene}
扩展包：{", ".join(packs) if packs else "无"}

用户输入：
{user_input}

默认主系统输出：
{baseline_output}

主系统 + 雷军扩展输出：
{experiment_output}

请只返回 JSON，不要额外解释。格式严格如下：
{{
  "preferred_version": "baseline | experiment | tie",
  "score_baseline": 0,
  "score_experiment": 0,
  "more_like_leijun": true,
  "too_hard_or_performance_like": false,
  "steals_main_system_judgment": false,
  "summary": "一句人话总结",
  "strengths": ["最多三条"],
  "risks": ["最多三条"],
  "suggestion": "下一步最值得怎么调"
}}
分数范围 0-100。
""".strip()

    response = invoke_deep(judge_prompt, "你是一个严谨的 A/B 文风评审。只返回 JSON。")
    raw = json.loads(_extract_json_block(response))
    normalized = _normalize_judge_payload(raw)
    normalized["raw_text"] = response
    return normalized


def _run_single(scene: str, user_input: str, extension_prompt: str = "") -> RunResult:
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    registry = get_registry()

    session_id = f"sandbox-mt-leijun-ab-{scene}-{int(time.time() * 1000)}"
    context = Context(session_id=session_id)
    context.scene_config = load_scene_config(scene)
    context.primary_scene = scene
    context.matched_scenes = {scene: 1.0}
    context.secondary_scenes = []
    context.secondary_configs = {}

    base_prompt = registry.build_skill_prompt(scene, getattr(context, "world_state", None))
    context.skill_prompt = (
        f"{base_prompt}\n\n{extension_prompt}" if extension_prompt and base_prompt
        else extension_prompt or base_prompt
    )
    if extension_prompt:
        context.skill_prompt += (
            "\n\n【本轮扩展使用提醒】\n"
            "这次是手动开启的雷军扩展测试。回复仍然按主系统判断走，"
            "但表达上要比默认版多一点：先抓主线、讲清为什么、给一个更收敛的现实落点。"
            "不要变成模仿秀，也不要加口号。"
        )

        result = runtime.run_stream(EngineRequest(session_id=session_id, user_input=user_input, context=context))
    return RunResult(
        scene=scene,
        output=result.output,
        elapsed_ms=result.elapsed_ms,
        skill_prompt=context.skill_prompt,
    )


def _build_markdown_report(payload: dict) -> str:
    lines = [
        "# 雷军扩展包 A/B 测试报告",
        "",
        f"- 时间：{payload['timestamp']}",
        f"- 场景：{payload['scene']}",
        f"- 用例：{payload['case_id']} / {payload['case_desc']}",
        f"- 雷军扩展：{', '.join(payload['packs']) if payload['packs'] else '无'}",
        "",
        "## 用户输入",
        "",
        payload["user_input"],
        "",
        "## 默认主系统",
        "",
        f"- 耗时：{payload['baseline']['elapsed_ms']} ms",
        "",
        payload["baseline"]["output"],
        "",
        "## 默认主系统 + 雷军扩展",
        "",
        f"- 耗时：{payload['experiment']['elapsed_ms']} ms",
        "",
        payload["experiment"]["output"],
        "",
    ]

    judge = payload.get("llm_judge")
    if judge:
        lines.extend(
            [
                "## LLM 评审结论",
                "",
                f"- 更优版本：`{judge['preferred_version']}`",
                f"- 默认分：`{judge['score_baseline']}`",
                f"- 雷军版分：`{judge['score_experiment']}`",
                f"- 更像雷军方法：`{judge['more_like_leijun']}`",
                f"- 是否偏硬/表演感过强：`{judge['too_hard_or_performance_like']}`",
                f"- 是否抢主系统判断：`{judge['steals_main_system_judgment']}`",
                "",
                judge["summary"],
                "",
            ]
        )
        if judge.get("strengths"):
            lines.extend(["### 优点", ""])
            lines.extend([f"- {item}" for item in judge["strengths"]])
            lines.append("")
        if judge.get("risks"):
            lines.extend(["### 风险", ""])
            lines.extend([f"- {item}" for item in judge["risks"]])
            lines.append("")
        if judge.get("suggestion"):
            lines.extend(["### 下一步建议", "", judge["suggestion"], ""])

    lines.extend(
        [
            "## 注入的扩展摘要",
            "",
            "```text",
            payload["experiment_extension_prompt"] or "（无）",
            "```",
        ]
    )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="雷军扩展包 A/B 对比测试")
    parser.add_argument("--case", default="all", help="用例 id，默认 all")
    parser.add_argument("--scene", default="", help="手动指定场景，覆盖用例场景")
    parser.add_argument("--input", default="", help="手动指定输入，覆盖用例输入")
    parser.add_argument("--packs", default="", help="手动指定扩展包，逗号分隔")
    parser.add_argument("--judge", action="store_true", help="调用 LLM 对 A/B 结果做人话评审")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    selected_cases = DEFAULT_CASES if args.case == "all" else [c for c in DEFAULT_CASES if c["id"] == args.case]
    if not selected_cases:
        raise SystemExit(f"找不到用例: {args.case}")

    for case in selected_cases:
        scene = args.scene.strip() or case["scene"]
        user_input = args.input.strip() or case["user_input"]
        packs = [p.strip() for p in (args.packs.split(",") if args.packs else case["packs"]) if p.strip()]
        extension_prompt = build_extension_pack_prompt("leijun", packs) if packs else ""

        print("=" * 72)
        print(f"雷军扩展 A/B 测试 | {case['id']} | 场景: {scene}")
        print("=" * 72)
        print(f"输入: {user_input}")
        print(f"扩展: {', '.join(packs) if packs else '无'}")

        print("\n[默认系统运行中...]", end="", flush=True)
        baseline = _run_single(scene, user_input)
        print("\r[默认系统运行完成]          ")

        print("[雷军扩展运行中...]", end="", flush=True)
        experiment = _run_single(scene, user_input, extension_prompt=extension_prompt)
        print("\r[雷军扩展运行完成]          ")

        judge_result = None
        if args.judge:
            print("[LLM 评审中...]", end="", flush=True)
            judge_result = evaluate_with_llm(
                scene=scene,
                user_input=user_input,
                packs=packs,
                baseline_output=baseline.output,
                experiment_output=experiment.output,
            )
            print("\r[LLM 评审完成]          ")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        payload = {
            "timestamp": datetime.now().isoformat(),
            "case_id": case["id"],
            "case_desc": case["desc"],
            "scene": scene,
            "packs": packs,
            "user_input": user_input,
            "baseline": asdict(baseline),
            "experiment": asdict(experiment),
            "experiment_extension_prompt": extension_prompt,
            "llm_judge": judge_result,
        }

        json_path = OUTPUT_DIR / f"leijun_ab_{case['id']}_{timestamp}.json"
        md_path = OUTPUT_DIR / f"leijun_ab_{case['id']}_{timestamp}.md"
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(_build_markdown_report(payload), encoding="utf-8")

        print(f"\n默认输出：{baseline.output}")
        print(f"\n雷军版输出：{experiment.output}")
        if judge_result:
            print("\nLLM 评审：")
            print(f"- 更优版本：{judge_result['preferred_version']}")
            print(f"- 默认分：{judge_result['score_baseline']}")
            print(f"- 雷军分：{judge_result['score_experiment']}")
            print(f"- 总结：{judge_result['summary']}")
        print("\n结果已写入：")
        print(f"- {json_path}")
        print(f"- {md_path}")
        print()


if __name__ == "__main__":
    main()
