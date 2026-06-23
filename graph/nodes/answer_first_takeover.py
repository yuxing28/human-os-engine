"""Minimal answer-first boundary takeover.

This boundary is intentionally narrow: it only runs after final output
observation has already found an answer-first violation.
"""

from __future__ import annotations

from graph.state import GraphState


ANSWER_FIRST_DELIVERABLES = {
    "direct_answer",
    "framework",
    "steps",
    "options",
    "script",
    "emotional_support",
    "repair_answer",
}

VIOLATING_DELIVERABLES = {"question_only", "generic_fallback", "unknown"}


def _set_runtime_field(context, name: str, value):
    object.__setattr__(context, name, value)


def _runtime_trace(state: GraphState | dict, context) -> dict:
    trace = state.get("runtime_trace") if isinstance(state, dict) else None
    if not isinstance(trace, dict):
        trace = getattr(context, "runtime_trace", None)
    if not isinstance(trace, dict):
        trace = {}
    _set_runtime_field(context, "runtime_trace", trace)
    if isinstance(state, dict):
        state["runtime_trace"] = trace
    return trace


def _scene(context, trace: dict) -> str:
    value = (
        getattr(context, "primary_scene", "")
        or trace.get("primary_scene")
        or trace.get("scene")
        or ""
    )
    if not value and getattr(context, "scene_config", None):
        value = getattr(context.scene_config, "scene_id", "")
    return str(value or "general")


def _tail_question(output: str) -> str:
    text = str(output or "").strip()
    if not text or not text.endswith(("?", "？")):
        return ""
    generic_tail_markers = ("最卡", "多说一点", "具体背景", "哪类", "想先解决")
    if any(marker in text for marker in generic_tail_markers):
        return ""
    for sep in ("。", "！", "!", "\n"):
        if sep in text:
            candidate = text.rsplit(sep, 1)[-1].strip()
            return candidate if candidate.endswith(("?", "？")) else ""
    return text if len(text) <= 80 else ""


def _scene_points(scene: str) -> dict[str, list[str]]:
    if scene == "sales":
        return {
            "framework": ["接住异议", "重申价值", "给推进方案", "约定下一步"],
            "steps": ["先确认客户真正卡点", "把价值讲具体", "给两个处理口径", "推动一个小承诺"],
            "options": ["降范围不降价值", "拆分套餐", "给试用或阶段方案"],
        }
    if scene == "negotiation":
        return {
            "framework": ["先守住底线", "把让步变成条件", "换取对等资源", "约定回看节点"],
            "steps": ["先明确边界", "提出条件式让步", "交换对方承诺", "落成文字确认"],
            "options": ["价格不动换范围", "时间让步换资源", "阶段交付换确定性"],
        }
    if scene == "emotion":
        return {
            "framework": ["先稳住情绪", "别急着逼对方表态", "确认真实状态", "约一个冷静沟通时间"],
            "steps": ["先暂停争辩", "表达你听见了对方感受", "讲清自己的担心", "约晚点再聊"],
            "options": ["先冷静半小时", "发一段低压消息", "约面对面把话说清"],
        }
    if scene == "management":
        return {
            "framework": ["目标是否清楚", "责任是否到人", "节奏是否固定", "卡点是否暴露", "反馈是否及时"],
            "steps": ["先把目标压成一句话", "把负责人和交付物写清", "约定固定复盘时间", "当场处理一个卡点"],
            "options": ["先抓目标对齐", "先抓责任拆解", "先抓节奏复盘"],
        }
    return {
        "framework": ["先定义问题", "拆出关键影响因素", "给出可执行下一步", "再根据反馈调整"],
        "steps": ["先确认目标", "列出限制条件", "做一个最小动作", "根据结果继续调整"],
        "options": ["保守推进", "快速试错", "先收集信息再决策"],
    }


def _format_points(points: list[str]) -> str:
    return "\n".join(f"{index}. {point}" for index, point in enumerate(points, 1))


def _format_framework_points(points: list[str]) -> str:
    return "\n".join(f"- {point}" for point in points)


def _direct_answer(scene: str) -> str:
    if scene == "sales":
        return (
            "直接结论：先回应客户的顾虑，再把价值说具体。"
            "原因是客户说贵时，真正卡住的通常不是价格本身，而是不确定这笔钱值不值。"
            "你可以先补一个具体结果，再给一个低风险下一步。"
        )
    if scene == "negotiation":
        return (
            "直接结论：先守住底线，再把让步换成条件。"
            "原因是直接退让会让对方继续压价，条件式让步才有交换价值。"
            "你可以先说清不可让的点，再提出一个可交换的小方案。"
        )
    if scene == "emotion":
        return (
            "直接结论：先让情绪降下来，不要立刻逼对方表态。"
            "原因是争吵后说出的重话未必是最终决定，继续追问只会把关系推得更紧。"
            "你可以先停一下，晚点用一句低压表达确认真实感受。"
        )
    if scene == "management":
        return (
            "直接结论：先把目标、责任和复盘节奏定清楚。"
            "原因是执行力差通常不是大家不努力，而是目标不够清、责任不够实、卡点没人及时处理。"
            "你可以先选一个项目，把负责人、交付物和下次检查时间写下来。"
        )
    return (
        "直接结论：先定主判断，再补最小下一步。"
        "原因是信息不完整时，最容易陷在反复分析里，先有判断才能推动反馈。"
        "现在先把结论写成一句话，再定一个今天能完成的小动作，做完再看要不要展开。"
    )


def _minimum_answer(context, trace: dict) -> str:
    obligation = trace.get("response_obligation") or {}
    expected = str(obligation.get("expected_deliverable") or "direct_answer")
    scene = _scene(context, trace)
    points = _scene_points(scene)

    if expected == "options":
        option_points = points["options"][:3]
        return (
            "先别急着定死，可以分三个选择看："
            f"稳一点是{option_points[0]}；推进一点是{option_points[1]}；"
            f"保留余地的是{option_points[2]}。"
        )
    if expected == "steps":
        return "别先铺太开，先照这个顺序往前推：\n" + _format_points(points["steps"])
    if expected == "script":
        if scene == "sales":
            return "这句可以直接发：我知道你担心价格，我们先不急着压价。你先看这笔钱对应的结果，如果结果对得上，再定一个更合适的推进版本。"
        if scene == "negotiation":
            return "这句可以直接说：这个点我可以配合，但不能变成单向让步。如果要调整范围或时间，我也需要你这边确认对应的承诺。"
        if scene == "emotion":
            return "这句可以轻一点发：我刚才有点急，但我不是想逼你表态。我很看重这段关系，也想听听你真实的感受，我们晚点冷静聊一次。"
        return "这句可以直接说：我先把现在的目标和卡点说清楚，再给你两个推进口径，我们一起选一个最稳的推进方式。"
    if expected == "emotional_support":
        return (
            "这句话听起来像是把你推开了，你会慌是很正常的。"
            "可以先停一下争辩，给彼此一点空间，然后用低压方式确认：她是在气头上，还是这段关系真的长期累积了问题。"
        )
    if expected == "repair_answer":
        return "刚才那版没有接住重点，我把答案补实一点：\n" + _format_points(points["framework"][:4])
    if expected == "framework":
        return "先把判断主线压清楚，不然很容易越想越散。\n" + _format_framework_points(points["framework"])
    return _direct_answer(scene)


def _should_takeover(trace: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    obligation = trace.get("response_obligation")
    final_obs = trace.get("final_answer_observed")
    if not isinstance(obligation, dict) or not isinstance(final_obs, dict):
        return False, reasons

    if trace.get("identity_truth_takeover_used") is True or obligation.get("expected_deliverable") == "identity_answer":
        return False, ["answer_first:takeover_skipped_identity"]
    if obligation.get("expected_deliverable") == "safety_support" or trace.get("crisis_safety_takeover_used") is True:
        return False, ["answer_first:takeover_skipped_crisis"]
    if obligation.get("answer_first_required") is not True:
        return False, reasons

    reasons.append("answer_first:required_by_obligation")
    clarification = str(obligation.get("clarification_allowed") or "")
    if clarification == "before_answer":
        return False, reasons + ["answer_first:takeover_skipped_clarification_allowed_before_answer"]
    if clarification not in {"after_answer", "not_allowed"}:
        return False, reasons

    reasons.append("answer_first:clarification_not_allowed_before_answer")
    expected = str(obligation.get("expected_deliverable") or "")
    if expected not in ANSWER_FIRST_DELIVERABLES:
        return False, reasons

    observed = str(final_obs.get("deliverable_observed") or "unknown")
    satisfied = final_obs.get("answer_first_satisfied")
    if observed == "meta_strategy":
        return False, reasons + ["answer_first:takeover_skipped_meta_strategy"]
    if satisfied is False:
        reasons.append("answer_first:final_output_question_only")
    if observed in VIOLATING_DELIVERABLES:
        reasons.append(
            "answer_first:generic_fallback_replaced"
            if observed == "generic_fallback"
            else "answer_first:minimum_deliverable_missing"
        )
    if expected == "options" and observed != "options":
        reasons.append("answer_first:options_deliverable_missing")

    return bool(
        satisfied is False
        or observed in VIOLATING_DELIVERABLES
        or (expected == "options" and observed != "options")
    ), reasons


def apply_answer_first_takeover(state: GraphState | dict, context, final_output: str) -> str:
    trace = _runtime_trace(state, context)
    trace.setdefault("answer_first_takeover_used", False)
    trace.setdefault("answer_first_violation_detected", False)
    trace.setdefault("answer_first_violation_reason", [])
    trace.setdefault("answer_first_takeover_source", "none")
    trace.setdefault("answer_first_expected_deliverable", "")
    trace.setdefault("answer_first_original_deliverable_observed", "")
    trace.setdefault("answer_first_takeover_preserved_tail_question", False)

    should_takeover, reasons = _should_takeover(trace)
    trace["answer_first_violation_detected"] = bool(should_takeover)
    trace["answer_first_violation_reason"] = reasons

    obligation = trace.get("response_obligation") or {}
    final_obs = trace.get("final_answer_observed") or {}
    trace["answer_first_expected_deliverable"] = str(obligation.get("expected_deliverable") or "")
    trace["answer_first_original_deliverable_observed"] = str(final_obs.get("deliverable_observed") or "")

    if not should_takeover:
        _set_runtime_field(context, "runtime_trace", trace)
        if isinstance(state, dict):
            state["runtime_trace"] = trace
        return final_output

    answer = _minimum_answer(context, trace)
    tail = _tail_question(final_output)
    if tail:
        answer = f"{answer}\n\n后面可以再按你最卡的一点细化：{tail}"
        trace["answer_first_takeover_preserved_tail_question"] = True

    trace["answer_first_takeover_used"] = True
    trace["answer_first_takeover_source"] = "response_obligation"
    _set_runtime_field(context, "runtime_trace", trace)
    if isinstance(state, dict):
        state["runtime_trace"] = trace
    return answer
