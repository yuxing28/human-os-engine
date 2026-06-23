"""Minimal repair-contract boundary takeover.

Repair is intentionally narrow: it only runs when the current response
obligation already says repair is required and the previous answer observation
shows the previous obligation was not satisfied.
"""

from __future__ import annotations

from graph.state import GraphState


BAD_PREVIOUS_DELIVERABLES = {"question_only", "generic_fallback", "meta_strategy", "unknown"}
SUPPORTED_PREVIOUS_DELIVERABLES = {
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


def _previous_observation(context) -> tuple[dict, dict]:
    for item in reversed(getattr(context, "history", []) or []):
        if getattr(item, "role", "") != "system":
            continue
        metadata = getattr(item, "metadata", {}) or {}
        obligation = metadata.get("response_obligation")
        final_obs = metadata.get("final_answer_observed")
        return (
            obligation if isinstance(obligation, dict) else {},
            final_obs if isinstance(final_obs, dict) else {},
        )
    return {}, {}


def _previous_scene(context, previous_obligation: dict) -> str:
    basis = previous_obligation.get("observation_basis") if isinstance(previous_obligation, dict) else {}
    scene = ""
    if isinstance(basis, dict):
        scene = str(basis.get("route_scene") or "")
    if not scene or scene == "general":
        scene = getattr(context, "primary_scene", "") or scene
    if not scene and getattr(context, "scene_config", None):
        scene = getattr(context.scene_config, "scene_id", "")
    return str(scene or "general")


def _points(scene: str) -> dict[str, list[str]]:
    if scene == "sales":
        return {
            "framework": ["先确认客户卡在价格还是信任", "把结果和成本对应起来", "给范围不同的选择", "约一个低风险下一步"],
            "steps": ["问清楚客户觉得贵的参照物", "把核心价值讲具体", "给两个处理口径", "推动一个小承诺"],
            "options": ["保价格调范围", "拆阶段推进", "给试用或样板案例"],
        }
    if scene == "negotiation":
        return {
            "framework": ["明确底线", "把让步变成交换", "要求对方给对等承诺", "落到文字确认"],
            "steps": ["明确不可让的边界", "提出条件式让步", "交换对方承诺", "确认复盘节点"],
            "options": ["价格不动换范围", "时间让步换资源", "阶段交付换确定性"],
        }
    if scene == "emotion":
        return {
            "framework": ["让情绪降温", "不要逼对方马上表态", "确认这是不是长期感受", "约冷静后再聊"],
            "steps": ["停止继续争辩", "给彼此一点空间", "低压表达你的在乎", "冷静后确认真实想法"],
            "options": ["冷静半小时", "发一段低压消息", "晚点面对面聊清楚"],
        }
    if scene == "management":
        return {
            "framework": ["目标是否清楚", "责任是否到人", "节奏是否固定", "卡点是否暴露", "反馈是否及时"],
            "steps": ["把共同目标压成一句话", "写清负责人和交付物", "约定固定复盘时间", "当场清掉一个阻塞点"],
            "options": ["抓目标对齐", "抓责任拆解", "抓节奏复盘"],
        }
    return {
        "framework": ["明确问题", "拆出关键因素", "给出下一步动作", "根据反馈调整"],
        "steps": ["确认目标", "列出限制", "做一个最小动作", "看结果后调整"],
        "options": ["稳妥推进", "快速试错", "补齐信息后再决策"],
    }


def _format_points(points: list[str]) -> str:
    return "\n".join(f"{index}. {point}" for index, point in enumerate(points, 1))


def _format_framework_points(points: list[str]) -> str:
    return "\n".join(f"- {point}" for point in points)


def _repair_intro(previous_obligation: dict, expected: str) -> str:
    goal = str(previous_obligation.get("user_goal") or "").strip()
    expected = str(expected or "direct_answer")
    variants = {
        "direct_answer": "刚才我绕了一下，直接补你要的判断。",
        "framework": "你说得对，刚才没有把框架给出来，我重新接一下。",
        "steps": "前面那句太空了，我直接补成可执行步骤。",
        "options": "刚才没把选择列清楚，我直接把几个方向补上。",
        "script": "刚才没有给到能直接用的话，我把话术补出来。",
        "emotional_support": "刚才没有真正接住你的处境，我重新补一版更有用的。",
    }
    intro = variants.get(expected, "刚才我没有答到点上，直接补完整。")
    if not goal:
        return intro
    return f"{intro}你要解决的是：{goal}。"


def _minimum_repair_answer(context, previous_obligation: dict) -> str:
    expected = str(previous_obligation.get("expected_deliverable") or "direct_answer")
    scene = _previous_scene(context, previous_obligation)
    points = _points(scene)
    intro = _repair_intro(previous_obligation, expected)

    if expected == "emotional_support":
        return (
            f"{intro}\n\n"
            "这类关系冲突里，先别急着追问对方到底还喜不喜欢你。更稳的是把争吵停下来，给彼此一点空间，"
            "等情绪降下来后再确认她是在气头上，还是长期积累了不满。\n\n"
            "你可以发一句低压的话：刚才我们都有情绪，我不想逼你马上表态。等你冷静一点，我想认真听你说真实感受。"
        )
    if expected == "script":
        if scene == "sales":
            script = "我知道你担心价格，我们先不急着压价。你先看这笔钱对应的结果，如果结果对得上，再定一个更合适的推进版本。"
        elif scene == "negotiation":
            script = "这个点我可以配合，但不能变成单向让步。如果要调整范围或时间，我也需要你这边确认对应的承诺。"
        elif scene == "emotion":
            script = "刚才我有点急，但我不是想逼你表态。我很看重这段关系，也想等你冷静后听听你的真实感受。"
        else:
            script = "我先把现在的目标和卡点说清楚，再给你两个推进口径，我们一起选一个最稳的推进方式。"
        return f"{intro}\n\n这句可以直接发给对方：{script}"
    if expected == "options":
        option_points = points["options"][:3]
        return (
            f"{intro}\n\n"
            "可以按三个方向补：\n"
            f"稳一点：{option_points[0]}\n"
            f"推进一点：{option_points[1]}\n"
            f"保留余地：{option_points[2]}"
        )
    if expected == "steps":
        return f"{intro}\n\n我把它补成能直接执行的顺序：\n" + _format_points(points["steps"])
    if expected == "framework":
        return f"{intro}\n\n我先把判断层次补清楚。\n" + _format_framework_points(points["framework"])
    return f"{intro}\n\n我的判断是：先把目标、限制和下一步动作说清楚。这样不会继续绕在泛泛解释里，也能马上往前推进一步。"


def _previous_failed(previous_final: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not isinstance(previous_final, dict) or not previous_final:
        return False, ["repair:takeover_skipped_no_previous_observation"]

    satisfied = previous_final.get("output_satisfies_obligation")
    observed = str(previous_final.get("deliverable_observed") or "unknown")
    if satisfied is False or satisfied == "Unknown":
        reasons.append("repair:previous_output_not_satisfied")
    if observed == "question_only":
        reasons.append("repair:previous_question_only")
    elif observed == "generic_fallback":
        reasons.append("repair:previous_generic_fallback")
    elif observed == "meta_strategy":
        reasons.append("repair:previous_meta_strategy")
    elif observed == "unknown":
        reasons.append("repair:previous_unknown")
    return bool(reasons), reasons


def _should_takeover(trace: dict, previous_obligation: dict, previous_final: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    obligation = trace.get("response_obligation")
    if not isinstance(obligation, dict):
        return False, reasons

    expected = str(obligation.get("expected_deliverable") or "")
    if trace.get("identity_truth_takeover_used") is True or expected == "identity_answer":
        return False, ["repair:takeover_skipped_identity"]
    if expected == "safety_support" or trace.get("crisis_safety_takeover_used") is True:
        return False, ["repair:takeover_skipped_crisis"]
    if expected == "none" or str(obligation.get("current_task") or "") == "casual_chat":
        return False, ["repair:takeover_skipped_new_task"]

    repair_required = trace.get("repair_obligation_required") is True or obligation.get("repair_required") is True
    if not repair_required:
        return False, reasons
    reasons.append("repair:required_by_current_obligation")
    reasons.append("repair:negative_feedback_without_crisis")

    if not isinstance(previous_obligation, dict) or not previous_obligation:
        return False, reasons + ["repair:takeover_skipped_no_previous_obligation"]

    previous_expected = str(previous_obligation.get("expected_deliverable") or "")
    if previous_expected in {"identity_answer", "safety_support", "none"}:
        return False, reasons + ["repair:takeover_skipped_previous_scope"]
    if previous_expected not in SUPPORTED_PREVIOUS_DELIVERABLES:
        previous_expected = "direct_answer"

    failed, previous_reasons = _previous_failed(previous_final)
    reasons.extend(previous_reasons)
    if not failed:
        return False, reasons

    reasons.append("repair:takeover_minimum_repair_answer")
    return True, reasons


def apply_repair_contract_takeover(state: GraphState | dict, context, final_output: str) -> str:
    trace = _runtime_trace(state, context)
    trace.setdefault("repair_contract_takeover_used", False)
    trace.setdefault("repair_contract_required", False)
    trace.setdefault("repair_contract_reason", [])
    trace.setdefault("repair_contract_target_obligation", {})
    trace.setdefault("repair_contract_previous_deliverable_observed", "")
    trace.setdefault("repair_contract_previous_satisfied", "Unknown")
    trace.setdefault("repair_contract_takeover_source", "none")
    trace.setdefault("repair_contract_output_type", "none")

    current_obs = trace.get("final_answer_observed")
    if isinstance(current_obs, dict):
        trace["pre_repair_final_answer_observed"] = dict(current_obs)

    previous_obligation, previous_final = _previous_observation(context)
    trace["repair_contract_target_obligation"] = previous_obligation if isinstance(previous_obligation, dict) else {}
    trace["repair_contract_previous_deliverable_observed"] = str(previous_final.get("deliverable_observed") or "")
    trace["repair_contract_previous_satisfied"] = previous_final.get("output_satisfies_obligation", "Unknown")

    should_takeover, reasons = _should_takeover(trace, previous_obligation, previous_final)
    trace["repair_contract_required"] = bool(
        trace.get("repair_obligation_required") is True
        or (isinstance(trace.get("response_obligation"), dict) and trace["response_obligation"].get("repair_required") is True)
    )
    trace["repair_contract_reason"] = reasons

    if not should_takeover:
        _set_runtime_field(context, "runtime_trace", trace)
        if isinstance(state, dict):
            state["runtime_trace"] = trace
        return final_output

    trace["repair_contract_takeover_used"] = True
    trace["repair_contract_takeover_source"] = "previous_obligation"
    trace["repair_contract_output_type"] = "minimum_repair_answer"
    answer = _minimum_repair_answer(context, previous_obligation)
    _set_runtime_field(context, "runtime_trace", trace)
    if isinstance(state, dict):
        state["runtime_trace"] = trace
    return answer
