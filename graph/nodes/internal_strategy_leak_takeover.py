"""Minimal internal-strategy-leak boundary takeover.

This module does not inspect prompts, skills, or user keywords. It only acts
when final output observation has already classified the visible answer as an
internal strategy leak.
"""

from __future__ import annotations

from graph.state import GraphState


SUPPORTED_DELIVERABLES = {
    "direct_answer",
    "framework",
    "steps",
    "options",
    "script",
    "emotional_support",
}


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
    value = getattr(context, "primary_scene", "") or trace.get("primary_scene") or trace.get("scene") or ""
    if not value and getattr(context, "scene_config", None):
        value = getattr(context.scene_config, "scene_id", "")
    return str(value or "general")


def _points(scene: str) -> dict[str, list[str]]:
    if scene == "sales":
        return {
            "framework": ["接住价格异议", "把价值说具体", "给两个方案", "约一个小下一步"],
            "steps": ["确认客户真正卡点", "把结果和成本对应起来", "给范围不同的处理口径", "推动一个低风险决定"],
            "options": ["保价格调范围", "拆阶段推进", "给试用或样板案例"],
        }
    if scene == "negotiation":
        return {
            "framework": ["明确底线", "把让步变成交换", "换取对等承诺", "落到可复盘节点"],
            "steps": ["明确不可让的边界", "提出条件式让步", "要求对方同步给承诺", "把结果写下来"],
            "options": ["价格不动换范围", "时间让步换资源", "阶段交付换确定性"],
        }
    if scene == "emotion":
        return {
            "framework": ["让争吵降温", "不要逼对方立刻表态", "确认这是不是长期感受", "约一个冷静沟通时间"],
            "steps": ["暂停继续争辩", "给彼此一点空间", "用低压方式表达在乎", "等冷静后确认真实想法"],
            "options": ["先冷静半小时", "发一段低压消息", "晚点面对面聊清楚"],
        }
    if scene == "management":
        return {
            "framework": ["目标清不清楚", "责任有没有到人", "节奏是否固定", "卡点能否及时暴露", "反馈是否跟得上"],
            "steps": ["把共同目标压成一句话", "写清负责人和交付物", "约定固定复盘时间", "当场清掉一个阻塞点"],
            "options": ["抓目标对齐", "抓责任拆解", "抓节奏复盘"],
        }
    return {
        "framework": ["先定义问题", "拆出关键因素", "给出可执行动作", "根据反馈调整"],
        "steps": ["确认目标", "列出限制条件", "做一个最小动作", "看结果后继续调整"],
        "options": ["稳妥推进", "快速试错", "补齐信息后再决策"],
    }


def _format_points(points: list[str]) -> str:
    return "\n".join(f"{index}. {point}" for index, point in enumerate(points, 1))


def _format_framework_points(points: list[str]) -> str:
    return "\n".join(f"- {point}" for point in points)


def _direct_answer(scene: str) -> str:
    if scene == "sales":
        return (
            "直接结论：先回应客户的贵，再把价值落到结果上。"
            "原因是只解释价格会显得防御，讲清结果才有继续谈的空间。"
            "你可以先补一个具体收益，再给客户两个范围不同的选择。"
        )
    if scene == "negotiation":
        return (
            "直接结论：不要先让价，先换条件。"
            "原因是无条件让步会变成新的起点，对方很可能继续往下压。"
            "你可以先说清底线，再问对方能给出什么对应承诺。"
        )
    if scene == "emotion":
        return (
            "直接结论：先降温，再确认对方到底是在气头上还是长期不满。"
            "原因是情绪最重的时候追问答案，通常只会让双方更防御。"
            "你可以先暂停争辩，晚点发一句不逼表态的话。"
        )
    if scene == "management":
        return (
            "直接结论：先抓目标和责任，再抓节奏。"
            "原因是执行问题多数不是一句动员能解决，而是需要把事情拆到人和时间点。"
            "你可以先挑一个关键任务，写清负责人、交付标准和复盘时间。"
        )
    return (
        "直接结论：先给一个明确判断，再做一个小动作验证。"
        "原因是只停在分析里，问题不会变清楚，行动反馈反而能帮你校准。"
        "现在先写一句核心结论，再定一个今天能完成的下一步，做完再根据反馈调整。"
    )


def _minimum_final_answer(context, trace: dict) -> str:
    obligation = trace.get("response_obligation") or {}
    expected = str(obligation.get("expected_deliverable") or "direct_answer")
    scene = _scene(context, trace)
    points = _points(scene)

    if expected == "emotional_support":
        return (
            "她这样说，这一下确实会很刺人，但先别急着把它当成最终结论。"
            "更稳的做法是让争吵先降温，等双方冷静后再确认她是在气头上，还是这段关系里长期有不满。"
            "\n\n你可以发一句低压的话。刚才我们都在情绪里，我不想逼你马上表态。等你冷静一点，我想认真听你说真实感受。"
        )
    if expected == "script":
        if scene == "sales":
            return "这句可以直接发：我知道你担心价格，我们先不急着压价。你先看这笔钱对应的结果，如果结果对得上，再定一个更合适的推进版本。"
        if scene == "negotiation":
            return "这句可以直接说：这个点我可以配合，但不能变成单向让步。如果要调整范围或时间，我也需要你这边确认对应的承诺。"
        if scene == "emotion":
            return "这句可以放软一点发：刚才我有点急，但我不是想逼你表态。我很看重这段关系，也想等你冷静后听听你的真实感受。"
        return "这句可以直接说：我先把目标和卡点讲清楚，再给两个推进口径，我们一起选一个最稳的推进方式。"
    if expected == "options":
        option_points = points["options"][:3]
        return (
            "这事可以拆成三个选择来看："
            f"稳一点：{option_points[0]}；推进一点：{option_points[1]}；"
            f"保留余地：{option_points[2]}。"
        )
    if expected == "steps":
        return "直接落到动作上，先走这几步：\n" + _format_points(points["steps"])
    if expected == "framework":
        return "这里先别散开想，我帮你把层次收住。\n" + _format_framework_points(points["framework"])
    return _direct_answer(scene)


def _should_takeover(trace: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    obligation = trace.get("response_obligation")
    final_obs = trace.get("final_answer_observed")
    if not isinstance(obligation, dict) or not isinstance(final_obs, dict):
        return False, reasons

    expected = str(obligation.get("expected_deliverable") or "")
    observed = str(final_obs.get("deliverable_observed") or "unknown")
    leak_observed = bool(final_obs.get("internal_strategy_leak_observed") is True or observed == "meta_strategy")
    if not leak_observed:
        return False, reasons

    reasons.append("internal_leak:observed_meta_strategy")
    if trace.get("identity_truth_takeover_used") is True or expected == "identity_answer":
        return False, reasons + ["internal_leak:takeover_skipped_identity"]
    if expected == "safety_support" or trace.get("crisis_safety_takeover_used") is True:
        return False, reasons + ["internal_leak:takeover_skipped_crisis"]
    if expected == "repair_answer":
        return False, reasons + ["internal_leak:takeover_skipped_repair_scope"]
    if expected not in SUPPORTED_DELIVERABLES:
        return False, reasons

    if obligation.get("final_response_boundary_required", True):
        reasons.append("internal_leak:final_response_boundary_required")
    reasons.append("internal_leak:takeover_minimum_final_answer")
    return True, reasons


def apply_internal_strategy_leak_takeover(state: GraphState | dict, context, final_output: str) -> str:
    trace = _runtime_trace(state, context)
    trace.setdefault("internal_strategy_leak_takeover_used", False)
    trace.setdefault("internal_strategy_leak_detected", False)
    trace.setdefault("internal_strategy_leak_reason", [])
    trace.setdefault("internal_strategy_leak_original_deliverable", "")
    trace.setdefault("internal_strategy_leak_expected_deliverable", "")
    trace.setdefault("internal_strategy_leak_takeover_source", "none")
    trace.setdefault("internal_strategy_leak_takeover_output_type", "none")

    final_obs = trace.get("final_answer_observed") if isinstance(trace.get("final_answer_observed"), dict) else {}
    if final_obs:
        trace.setdefault("original_final_answer_observed", dict(final_obs))
        trace["post_answer_first_observed"] = dict(final_obs)

    should_takeover, reasons = _should_takeover(trace)
    trace["internal_strategy_leak_detected"] = bool(
        isinstance(final_obs, dict)
        and (final_obs.get("internal_strategy_leak_observed") is True or final_obs.get("deliverable_observed") == "meta_strategy")
    )
    trace["internal_strategy_leak_reason"] = reasons

    obligation = trace.get("response_obligation") or {}
    trace["internal_strategy_leak_original_deliverable"] = str(final_obs.get("deliverable_observed") or "")
    trace["internal_strategy_leak_expected_deliverable"] = str(obligation.get("expected_deliverable") or "")

    if not should_takeover:
        _set_runtime_field(context, "runtime_trace", trace)
        if isinstance(state, dict):
            state["runtime_trace"] = trace
        return final_output

    trace["internal_strategy_leak_takeover_used"] = True
    trace["internal_strategy_leak_takeover_source"] = "final_answer_observed"
    trace["internal_strategy_leak_takeover_output_type"] = "minimum_final_answer"
    answer = _minimum_final_answer(context, trace)
    _set_runtime_field(context, "runtime_trace", trace)
    if isinstance(state, dict):
        state["runtime_trace"] = trace
    return answer
