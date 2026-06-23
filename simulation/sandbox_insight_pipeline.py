"""
沙盒洞察管线

这层只读沙盒/大循环报告，把指标翻译成“候选优化建议”。
它不改主系统，也不自动写入主系统规则。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SandboxInsight:
    scene: str
    observation: str
    hypothesis: str
    proposal: str
    risk: str
    evidence: list[str] = field(default_factory=list)
    gate: str = "observe"


def _rate(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _phase_sandbox_summaries(report: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        phase.get("summary") or {}
        for phase in report.get("phases", [])
        if phase.get("kind") == "sandbox" and isinstance(phase.get("summary"), dict)
    ]


def _collect_scene_summaries(report: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    scenes: dict[str, list[dict[str, Any]]] = {}
    for summary in _phase_sandbox_summaries(report):
        for scene, scene_summary in (summary.get("scenes") or {}).items():
            if isinstance(scene_summary, dict):
                scenes.setdefault(scene, []).append(scene_summary)
    return scenes


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _candidate_key(scene: str, reason: str) -> str:
    cleaned_reason = " ".join((reason or "").split())
    return f"{scene}:{cleaned_reason}"


def _scene_label(scene: str) -> str:
    labels = {
        "sales": "销售",
        "management": "管理",
        "negotiation": "谈判",
        "emotion": "情绪",
    }
    return labels.get(scene, scene or "未知场景")


def _human_summary_for_review(item: dict[str, Any]) -> dict[str, Any]:
    scene = item.get("scene") or "unknown"
    scene_label = _scene_label(scene)
    reason = item.get("reason") or "这个场景里出现了连续候选问题。"
    risk = item.get("risk") or "修得太猛，可能影响原本稳定的主线。"

    if "扰动" in reason and "焦点恢复偏弱" in reason:
        plain_meaning = (
            f"{scene_label}场景里，一旦局面突然变化，系统能发现变化，"
            "但下一轮有时没有自然接回重点，容易像停了一下。"
        )
        why_user_cares = (
            "如果你希望它未来更像一个会继续推进事情的人，这类问题值得看；"
            "如果你现在更看重主线别乱动，可以先继续观察。"
        )
    elif "偏观察" in reason:
        plain_meaning = (
            f"{scene_label}场景里，系统有时会过于保守，"
            "知道有目标，但没有顺手留下下一步。"
        )
        why_user_cares = "这会影响它像不像一个能把事情往前带的人，但也可能只是样本偏短。"
    else:
        plain_meaning = reason
        why_user_cares = "你只需要判断这个现象是否影响项目想要的“像人、会做人、会做事”。"

    return {
        "plain_meaning": plain_meaning,
        "why_user_cares": why_user_cares,
        "user_decision_question": "你只需要决定：这个问题现在要不要让我进入小范围修复？",
        "decision_options": [
            {
                "code": "A",
                "label": "继续观察",
                "meaning": "先不修，再跑一轮，看它是不是继续出现。",
            },
            {
                "code": "B",
                "label": "小范围修",
                "meaning": f"只修 {scene_label} 这个场景里的这个问题，修完马上回归测试。",
            },
            {
                "code": "C",
                "label": "提高优先级",
                "meaning": "把它作为下一轮重点问题，我先做更细分析再动手。",
            },
        ],
        "recommended_option": "B",
        "recommended_reason": "它已经连续出现，适合小范围处理；但不应该大改主线。",
        "risk_in_plain_words": risk,
    }


def _build_scene_insight(scene: str, scene_summaries: list[dict[str, Any]], report: dict[str, Any]) -> SandboxInsight:
    evidence: list[str] = []
    total_turns = 0
    commitment_rates: list[float] = []
    focus_rates: list[float] = []
    disturbance_rates: list[float] = []
    recovery_focus_rates: list[float] = []
    recovery_commitment_rates: list[float] = []
    progress_counts: dict[str, int] = {}

    for summary in scene_summaries:
        action_loop = summary.get("action_loop_metrics") or {}
        disturbance = summary.get("disturbance_metrics") or {}
        recovery = summary.get("disturbance_recovery_metrics") or {}

        commitment_rates.append(_rate(action_loop.get("commitment_rate")))
        focus_rates.append(_rate(action_loop.get("focus_rate")))
        disturbance_rates.append(_rate(disturbance.get("disturbance_rate")))
        recovery_focus_rates.append(_rate(recovery.get("recovery_focus_rate")))
        recovery_commitment_rates.append(_rate(recovery.get("recovery_commitment_rate")))

        for label, count in (action_loop.get("action_loop_state_counts") or {}).items():
            progress_counts[label] = progress_counts.get(label, 0) + int(count or 0)

        total_turns += int(action_loop.get("active_goal_turns") or 0)

    avg_commitment = sum(commitment_rates) / len(commitment_rates) if commitment_rates else 0.0
    avg_focus = sum(focus_rates) / len(focus_rates) if focus_rates else 0.0
    avg_disturbance = sum(disturbance_rates) / len(disturbance_rates) if disturbance_rates else 0.0
    avg_recovery_focus = sum(recovery_focus_rates) / len(recovery_focus_rates) if recovery_focus_rates else 0.0
    avg_recovery_commitment = sum(recovery_commitment_rates) / len(recovery_commitment_rates) if recovery_commitment_rates else 0.0

    observe_turns = sum(count for label, count in progress_counts.items() if "先观察" in label)
    observe_rate = round((observe_turns / total_turns) * 100, 1) if total_turns else 0.0

    _append_unique(evidence, f"commitment_rate={avg_commitment:.1f}%")
    _append_unique(evidence, f"focus_rate={avg_focus:.1f}%")
    _append_unique(evidence, f"observe_rate={observe_rate:.1f}%")
    if avg_disturbance:
        _append_unique(evidence, f"disturbance_rate={avg_disturbance:.1f}%")
    if avg_recovery_focus or avg_recovery_commitment:
        _append_unique(evidence, f"recovery_focus_rate={avg_recovery_focus:.1f}%")
        _append_unique(evidence, f"recovery_commitment_rate={avg_recovery_commitment:.1f}%")

    trend = (report.get("scene_trends") or {}).get(scene) or {}
    if trend.get("summary"):
        _append_unique(evidence, f"trend={trend['summary']}")

    if observe_rate >= 70 and avg_commitment <= 20 and avg_focus <= 20:
        return SandboxInsight(
            scene=scene,
            observation=f"{scene} 这轮明显偏观察，目标存在但没有形成承诺和下一轮焦点。",
            hypothesis="系统可能把早期破冰或低风险局面理解成不宜推进，导致动作闭环停在表面记录。",
            proposal="先不要改主系统，建议扩大同场景样本；如果连续两轮仍这样，再检查 world_state 的 progress_state 与 next_turn_focus 生成条件。",
            risk="如果直接放宽推进条件，可能把本来该观察的局面过早推成动作。",
            evidence=evidence,
            gate="observe",
        )

    if avg_disturbance >= 30 and avg_recovery_focus <= 30:
        return SandboxInsight(
            scene=scene,
            observation=f"{scene} 有扰动，但扰动后的下一轮焦点恢复偏弱。",
            hypothesis="系统能识别扰动，但没有稳定把扰动影响转成下一轮承接点。",
            proposal="作为候选优化，优先检查 disturbance_event 到 next_turn_focus 的桥接逻辑。",
            risk="过度强化扰动恢复，可能让普通对话也被误判成风险处理。",
            evidence=evidence,
            gate="candidate",
        )

    if avg_commitment >= 50 and avg_focus >= 50:
        return SandboxInsight(
            scene=scene,
            observation=f"{scene} 的动作闭环比较稳，承诺和下一轮焦点都能形成。",
            hypothesis="当前场景的状态识别和输出承接能形成正向闭环。",
            proposal="先保持，不建议动主线；后续只做趋势观察。",
            risk="稳定样本量如果太小，不能过度外推。",
            evidence=evidence,
            gate="hold",
        )

    return SandboxInsight(
        scene=scene,
        observation=f"{scene} 当前没有明显失控，但也还不能证明已经稳定。",
        hypothesis="样本可能偏短，或者状态变化还没有触发足够多的承诺/恢复信号。",
        proposal="继续用 smoke 看门，用正式大循环看趋势；暂时不进入主线修改。",
        risk="如果只看单轮，容易把正常波动误判成系统问题。",
        evidence=evidence,
        gate="observe",
    )


def analyze_large_cycle_report(report: dict[str, Any]) -> dict[str, Any]:
    scene_summaries = _collect_scene_summaries(report)
    insights = [
        _build_scene_insight(scene, summaries, report)
        for scene, summaries in sorted(scene_summaries.items())
    ]
    gates = [item.gate for item in insights]
    if "candidate" in gates:
        gate_summary = "candidate"
    elif gates and all(gate == "hold" for gate in gates):
        gate_summary = "hold"
    else:
        gate_summary = "observe"

    return {
        "source": "large_cycle_report",
        "all_passed": bool(report.get("all_passed")),
        "stable_candidate": bool(report.get("stable_candidate")),
        "gate_summary": gate_summary,
        "main_system_write_allowed": False,
        "rule": "沙盒只产候选洞察，不直接改主系统。",
        "insights": [asdict(item) for item in insights],
    }


def analyze_large_cycle_report_file(path: str | Path) -> dict[str, Any]:
    report_path = Path(path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    result = analyze_large_cycle_report(payload)
    result["report_path"] = str(report_path)
    return result


def build_validation_queue(
    insight_report: dict[str, Any],
    previous_queue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    把 candidate 洞察整理成待验证队列。

    这层仍然不改主系统，只是把“可能值得修”的点先排队，
    等下一轮复测继续给证据。
    """
    source_report = insight_report.get("report_path") or insight_report.get("source") or "unknown"
    items: list[dict[str, Any]] = []
    previous_items = {
        item.get("key") or _candidate_key(item.get("scene") or "unknown", item.get("reason") or ""): item
        for item in (previous_queue or {}).get("items", [])
        if isinstance(item, dict)
    }

    for insight in insight_report.get("insights") or []:
        if insight.get("gate") != "candidate":
            continue

        scene = insight.get("scene") or "unknown"
        reason = insight.get("observation") or ""
        key = _candidate_key(scene, reason)
        previous_item = previous_items.get(key) or {}
        occurrence_count = int(previous_item.get("occurrence_count") or 0) + 1
        status = "ready_for_review" if occurrence_count >= 2 else "needs_retest"
        priority = "high" if status == "ready_for_review" else "medium"
        next_check = (
            "连续两轮仍为 candidate，允许进入人工改动讨论；仍然不能自动改主系统。"
            if status == "ready_for_review"
            else "下一轮同场景大循环复测；连续两轮仍为 candidate 才允许进入人工改动讨论。"
        )

        items.append({
            "id": previous_item.get("id") or f"{scene}:candidate:{len(items) + 1}",
            "key": key,
            "scene": scene,
            "status": status,
            "priority": priority,
            "occurrence_count": occurrence_count,
            "reason": reason,
            "hypothesis": insight.get("hypothesis") or "",
            "proposal": insight.get("proposal") or "",
            "risk": insight.get("risk") or "",
            "evidence": list(insight.get("evidence") or []),
            "source_report": source_report,
            "previous_source_report": previous_item.get("source_report"),
            "main_system_write_allowed": False,
            "next_check": next_check,
        })

    ready_count = sum(1 for item in items if item.get("status") == "ready_for_review")
    return {
        "source": "sandbox_insight_report",
        "main_system_write_allowed": False,
        "rule": "验证队列只排候选，不直接改主系统。",
        "queue_size": len(items),
        "ready_for_review_count": ready_count,
        "items": items,
    }


def build_review_cards(queue: dict[str, Any]) -> dict[str, Any]:
    """
    把 ready_for_review 项整理成人工复盘卡。

    复盘卡只帮人判断，不代表系统已经决定修改主线。
    """
    cards: list[dict[str, Any]] = []
    for item in queue.get("items") or []:
        if item.get("status") != "ready_for_review":
            continue

        evidence = list(item.get("evidence") or [])
        human_decision = _human_summary_for_review(item)
        cards.append({
            "id": item.get("id") or "",
            "scene": item.get("scene") or "unknown",
            "title": f"{_scene_label(item.get('scene') or 'unknown')}候选问题决策卡",
            "decision_status": "needs_human_review",
            "main_system_write_allowed": False,
            "plain_meaning": human_decision["plain_meaning"],
            "why_user_cares": human_decision["why_user_cares"],
            "user_decision_question": human_decision["user_decision_question"],
            "decision_options": human_decision["decision_options"],
            "recommended_option": human_decision["recommended_option"],
            "recommended_reason": human_decision["recommended_reason"],
            "risk_in_plain_words": human_decision["risk_in_plain_words"],
            "why_it_matters": item.get("reason") or "",
            "evidence": evidence,
            "hypothesis": item.get("hypothesis") or "",
            "proposal": item.get("proposal") or "",
            "risk": item.get("risk") or "",
            "recommended_decision": "先人工复盘证据；如果确认连续问题成立，再开一个小范围定向修复，不直接改主线。",
            "source_reports": [
                report
                for report in [item.get("previous_source_report"), item.get("source_report")]
                if report
            ],
        })

    return {
        "source": "sandbox_validation_queue",
        "main_system_write_allowed": False,
        "rule": "复盘卡只给人工判断，不自动改主系统。",
        "card_count": len(cards),
        "cards": cards,
    }


def render_review_cards_markdown(review_cards: dict[str, Any]) -> str:
    lines = [
        "# 沙盒人话决策卡",
        "",
        "> 你不需要懂代码，只需要选方向；代码怎么改、怎么测试由 Codex 负责。",
        "",
        f"- 卡片数量：{review_cards.get('card_count', 0)}",
        f"- 允许直接改主系统：{str(review_cards.get('main_system_write_allowed', False)).lower()}",
        "",
    ]

    cards = review_cards.get("cards") or []
    if not cards:
        lines.extend([
            "## 当前结论",
            "",
            "暂无需要人工复盘的连续候选问题。",
            "",
        ])
        return "\n".join(lines)

    for index, card in enumerate(cards, start=1):
        lines.extend([
            f"## {index}. {card.get('title') or '候选问题复盘'}",
            "",
            f"- 场景：{card.get('scene') or 'unknown'}",
            f"- 决策状态：{card.get('decision_status') or 'needs_human_review'}",
            f"- 允许直接改主系统：{str(card.get('main_system_write_allowed', False)).lower()}",
            "",
            "### 这件事是什么意思",
            "",
            card.get("plain_meaning") or "暂无说明。",
            "",
            "### 为什么你需要看",
            "",
            card.get("why_user_cares") or "暂无说明。",
            "",
            "### 你只需要决定",
            "",
            card.get("user_decision_question") or "要不要继续观察、还是让我小范围修。",
            "",
            "### 你可以选",
            "",
        ])
        options = card.get("decision_options") or []
        if options:
            for option in options:
                lines.append(
                    f"- {option.get('code')}. {option.get('label')}：{option.get('meaning')}"
                )
        else:
            lines.append("- A. 继续观察")
            lines.append("- B. 小范围修")
            lines.append("- C. 提高优先级")
        lines.extend([
            "",
            f"Codex 建议：选 {card.get('recommended_option') or 'B'}。{card.get('recommended_reason') or ''}",
            "",
            "### 证据",
            "",
        ])
        evidence = card.get("evidence") or []
        if evidence:
            lines.extend([f"- {item}" for item in evidence])
        else:
            lines.append("- 暂无证据。")
        lines.extend([
            "",
            "### 初步假设",
            "",
            card.get("hypothesis") or "暂无假设。",
            "",
            "### 候选建议",
            "",
            card.get("proposal") or "暂无建议。",
            "",
            "### 风险",
            "",
            card.get("risk_in_plain_words") or card.get("risk") or "暂无风险。",
            "",
            "### 技术备注",
            "",
            card.get("recommended_decision") or "先人工复盘，不直接改主线。",
            "",
        ])
        source_reports = card.get("source_reports") or []
        if source_reports:
            lines.extend(["### 来源报告", ""])
            lines.extend([f"- {report}" for report in source_reports])
            lines.append("")

    return "\n".join(lines)


def save_insight_report(insight: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(insight, ensure_ascii=False, indent=2), encoding="utf-8")


def save_validation_queue(queue: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(queue, ensure_ascii=False, indent=2), encoding="utf-8")


def save_review_cards(review_cards: dict[str, Any], output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".md":
        path.write_text(render_review_cards_markdown(review_cards), encoding="utf-8")
    else:
        path.write_text(json.dumps(review_cards, ensure_ascii=False, indent=2), encoding="utf-8")
