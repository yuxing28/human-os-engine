"""Minimal fallback-contract boundary takeover.

Fallback can degrade generation, but it should not bypass the current response
obligation. This module only runs when fallback was used and the observed final
output still does not satisfy the expected deliverable.
"""

from __future__ import annotations

from graph.state import GraphState
from graph.nodes.repair_contract_takeover import _minimum_repair_answer


SUPPORTED_DELIVERABLES = {
    "direct_answer",
    "framework",
    "steps",
    "options",
    "script",
    "emotional_support",
    "repair_answer",
}

BAD_OBSERVED_DELIVERABLES = {"generic_fallback", "question_only", "meta_strategy", "unknown"}


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
            "framework": ["客户卡点先说清", "价值和成本对应", "给两个方案", "约一个小下一步"],
            "steps": ["先确认客户最担心什么", "把核心价值讲具体", "给不同范围的推进口径", "推动一个低风险决定"],
            "options": ["保价格调范围", "拆阶段推进", "给试用或样板案例"],
        }
    if scene == "negotiation":
        return {
            "framework": ["守住底线", "让步要换条件", "换到对等承诺", "留复盘节点"],
            "steps": ["先明确边界", "提出条件式让步", "拿到对方承诺", "落成文字确认"],
            "options": ["价格不动换范围", "时间让步换资源", "阶段交付换确定性"],
        }
    if scene == "emotion":
        return {
            "framework": ["先让情绪降下来", "不要逼对方立刻表态", "确认这是不是长期感受", "约冷静后再聊"],
            "steps": ["先停下争辩", "给彼此一点空间", "低压表达你的在乎", "等冷静后再确认真实想法"],
            "options": ["先冷静半小时", "发一段低压消息", "晚点面对面聊"],
        }
    if scene == "management":
        return {
            "framework": ["目标清楚", "责任到人", "节奏固定", "卡点暴露", "反馈及时"],
            "steps": ["先把目标压成一句话", "写清负责人和交付物", "约定固定复盘时间", "及时清掉阻塞点"],
            "options": ["先抓目标", "先抓责任", "先抓节奏"],
        }
    return {
        "framework": ["先定义问题", "拆关键因素", "给下一步动作", "按反馈再调整"],
        "steps": ["确认目标", "列出限制", "做一个最小动作", "根据结果调整"],
        "options": ["稳妥推进", "快速试错", "补齐信息后再决策"],
    }


def _format_points(points: list[str]) -> str:
    return "\n".join(f"{index}. {point}" for index, point in enumerate(points, 1))


def _format_framework_points(points: list[str]) -> str:
    return "\n".join(f"- {point}" for point in points)


def _direct_answer(scene: str) -> str:
    if scene == "sales":
        return (
            "直接结论：先别急着降价，先把客户要买到的结果说清楚。"
            "原因是 fallback 也不能只承接情绪，客户异议需要一个能继续谈的价值落点。"
            "你可以先补一句具体价值，再给一个低风险选择。"
        )
    if scene == "negotiation":
        return (
            "直接结论：先守边界，再谈交换。"
            "原因是底线不清时，任何让步都会变成继续被压的入口。"
            "你可以先说清不能让的部分，再给一个带条件的小让步。"
        )
    if scene == "emotion":
        return (
            "直接结论：先稳住局面，不要马上逼对方给最终答案。"
            "原因是情绪高的时候，继续追问容易把话说死。"
            "你可以先停下争辩，晚点用低压方式确认她真实想法。"
        )
    if scene == "management":
        return (
            "直接结论：先把目标、责任和检查节奏落下来。"
            "原因是执行力靠清晰机制，不靠临时催促。"
            "你可以先定一个本周目标，再明确负责人和下一次复盘时间。"
        )
    return (
        "直接结论：先给出主判断，再做一个最小可执行动作。"
        "原因是信息不全时，空等更多背景会拖慢推进。"
        "现在先把结论写成一句话，再安排一个今天能完成的小步骤，做完再决定要不要展开。"
    )


def _minimum_fallback_answer(context, trace: dict) -> str:
    obligation = trace.get("response_obligation") or {}
    expected = str(obligation.get("expected_deliverable") or "direct_answer")
    scene = _scene(context, trace)
    points = _points(scene)

    if expected == "repair_answer":
        previous = trace.get("repair_contract_target_obligation")
        if isinstance(previous, dict) and previous:
            return _minimum_repair_answer(context, previous)
        previous_like = {
            "user_goal": str(obligation.get("user_goal") or "").strip(),
            "expected_deliverable": "direct_answer",
            "observation_basis": {"route_scene": scene},
        }
        return _minimum_repair_answer(context, previous_like)
    if expected == "emotional_support":
        return (
            "这件事会让人心里发紧，先别急着把局面往更僵的方向推。"
            "更稳的做法是先让情绪降一点，再确认对方是在气头上，还是这段关系里真的长期有不满。"
            "\n\n你现在可以先做一个小动作：先停下争辩，晚一点发一句低压的话，告诉对方你愿意认真听她说真实感受。"
        )
    if expected == "script":
        if scene == "sales":
            return "这句可以直接发：我知道你担心价格，我们先不急着压价。你先看这笔钱对应的结果，如果结果对得上，再定一个更合适的推进版本。"
        if scene == "negotiation":
            return "这句可以直接说：这个点我可以配合，但不能变成单向让步。如果要调整范围或时间，我也需要你这边确认对应的承诺。"
        if scene == "emotion":
            return "这句可以轻一点发：刚才我们都有情绪，我不想逼你马上表态。等你冷静一点，我想认真听你说真实感受。"
        return "这句可以直接说：我先把目标和卡点说清楚，再给你两个推进口径，我们一起选一个最稳的推进方式。"
    if expected == "options":
        option_points = points["options"][:3]
        return (
            "至少可以先看这三个方向：\n"
            f"稳一点：{option_points[0]}\n"
            f"推进一点：{option_points[1]}\n"
            f"保留余地：{option_points[2]}"
        )
    if expected == "steps":
        return "先别等更多背景，按这个顺序做起来：\n" + _format_points(points["steps"])
    if expected == "framework":
        return "先用一个轻框架把主线抓住。\n" + _format_framework_points(points["framework"])
    return _direct_answer(scene)


def _should_takeover(trace: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    obligation = trace.get("response_obligation")
    final_obs = trace.get("final_answer_observed")
    fallback_check = trace.get("fallback_obligation_check")
    if not isinstance(obligation, dict) or not isinstance(final_obs, dict):
        return False, reasons

    expected = str(obligation.get("expected_deliverable") or "")
    if trace.get("identity_truth_takeover_used") is True or expected == "identity_answer":
        return False, ["fallback_contract:skipped_identity"]
    if expected == "safety_support" or trace.get("crisis_safety_takeover_used") is True:
        return False, ["fallback_contract:skipped_crisis"]
    if trace.get("repair_contract_takeover_used") is True:
        post_repair = trace.get("post_repair_final_answer_observed")
        if isinstance(post_repair, dict) and post_repair.get("output_satisfies_obligation") is True:
            return False, ["fallback_contract:skipped_repair_completed"]
    if str(obligation.get("clarification_allowed") or "") == "before_answer":
        return False, ["fallback_contract:skipped_clarification_before_answer"]
    if expected not in SUPPORTED_DELIVERABLES:
        return False, reasons

    fallback_used = False
    if isinstance(fallback_check, dict) and fallback_check.get("fallback_used") is True:
        fallback_used = True
    if trace.get("output_path") == "fallback":
        fallback_used = True
    if int(trace.get("fallback_count", 0) or 0) > 0:
        fallback_used = True
    if not fallback_used:
        return False, reasons
    reasons.append("fallback_contract:fallback_used")

    observed = str(final_obs.get("deliverable_observed") or "unknown")
    satisfies = final_obs.get("output_satisfies_obligation")
    fallback_satisfies = (
        fallback_check.get("fallback_satisfies_obligation")
        if isinstance(fallback_check, dict)
        else "Unknown"
    )
    if fallback_satisfies is False or satisfies is False:
        reasons.append("fallback_contract:fallback_not_satisfy_obligation")
    if observed == "generic_fallback":
        reasons.append("fallback_contract:generic_fallback_detected")
    elif observed == "question_only":
        reasons.append("fallback_contract:question_only_detected")
    elif observed in {"meta_strategy", "unknown"}:
        reasons.append("fallback_contract:unknown_deliverable_detected")

    should_take = bool(
        fallback_satisfies is False
        or satisfies is False
        or observed in BAD_OBSERVED_DELIVERABLES
    )
    if should_take:
        reasons.append("fallback_contract:takeover_minimum_obligation_answer")
    return should_take, reasons


def apply_fallback_contract_takeover(state: GraphState | dict, context, final_output: str) -> str:
    trace = _runtime_trace(state, context)
    trace.setdefault("fallback_contract_takeover_used", False)
    trace.setdefault("fallback_contract_required", False)
    trace.setdefault("fallback_contract_reason", [])
    trace.setdefault("fallback_contract_expected_deliverable", "")
    trace.setdefault("fallback_contract_original_deliverable", "")
    trace.setdefault("fallback_contract_previous_output_path", "")
    trace.setdefault("fallback_contract_takeover_source", "none")
    trace.setdefault("fallback_contract_output_type", "none")

    current_obs = trace.get("final_answer_observed")
    if isinstance(current_obs, dict):
        trace["pre_fallback_contract_final_answer_observed"] = dict(current_obs)

    should_takeover, reasons = _should_takeover(trace)
    obligation = trace.get("response_obligation") or {}
    final_obs = trace.get("final_answer_observed") or {}
    trace["fallback_contract_required"] = bool(
        isinstance(trace.get("fallback_obligation_check"), dict)
        and trace["fallback_obligation_check"].get("fallback_used") is True
        or trace.get("output_path") == "fallback"
        or int(trace.get("fallback_count", 0) or 0) > 0
    )
    trace["fallback_contract_reason"] = reasons
    trace["fallback_contract_expected_deliverable"] = str(obligation.get("expected_deliverable") or "")
    trace["fallback_contract_original_deliverable"] = str(final_obs.get("deliverable_observed") or "")
    trace["fallback_contract_previous_output_path"] = str(trace.get("output_path") or "unknown")

    if not should_takeover:
        _set_runtime_field(context, "runtime_trace", trace)
        if isinstance(state, dict):
            state["runtime_trace"] = trace
        return final_output

    trace["fallback_contract_takeover_used"] = True
    trace["fallback_contract_takeover_source"] = "response_obligation"
    trace["fallback_contract_output_type"] = "minimum_obligation_answer"
    answer = _minimum_fallback_answer(context, trace)
    _set_runtime_field(context, "runtime_trace", trace)
    if isinstance(state, dict):
        state["runtime_trace"] = trace
    return answer
