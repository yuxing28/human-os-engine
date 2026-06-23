"""
Response Obligation observation layer.

This module is intentionally read-only for behavior: it writes runtime trace
fields but must not change prompts, routing, fallback text, memory gates, or
final output.
"""

from __future__ import annotations

from typing import Any

from graph.state import GraphState


DELIVERABLES = {
    "direct_answer",
    "framework",
    "steps",
    "options",
    "script",
    "emotional_support",
    "repair_answer",
    "identity_answer",
    "safety_support",
    "none",
}


def _set_runtime_field(context, name: str, value):
    object.__setattr__(context, name, value)


def _get_runtime_trace(state: GraphState | dict, context) -> dict:
    trace = state.get("runtime_trace") if isinstance(state, dict) else None
    if not isinstance(trace, dict):
        trace = getattr(context, "runtime_trace", None)
    if not isinstance(trace, dict):
        trace = {}
    _set_runtime_field(context, "runtime_trace", trace)
    if isinstance(state, dict):
        state["runtime_trace"] = trace
    return trace


def _clip(text: Any, limit: int = 120) -> str:
    value = str(text or "").strip().replace("\r", " ").replace("\n", " ")
    return value[:limit]


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _recent_previous_system_observation(context) -> tuple[dict, dict]:
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


def _looks_like_identity_request(text: str) -> bool:
    lowered = text.lower()
    return (
        ("模型" in text and ("你是" in text or "你是什么" in text or "哪个" in text))
        or "模型身份" in text
        or "模型版本" in text
        or "模型名" in text
        or "你是谁" in text
        or "你叫什么" in text
        or "助手身份" in text
        or ("你是" in text and ("系统" in text or "ai" in lowered or "AI" in text))
        or (
            "你是" in text
            and (
                "GPT" in text or "gpt" in lowered or "Claude" in text or "claude" in lowered
                or "OpenAI" in text or "openai" in lowered or "DeepSeek" in text
                or "deepseek" in lowered or "Qwen" in text or "qwen" in lowered
            )
        )
        or (
            "你是不是" in text
            and (
                "GPT" in text or "gpt" in lowered or "Claude" in text or "claude" in lowered
                or "OpenAI" in text or "openai" in lowered or "DeepSeek" in text
                or "deepseek" in lowered or "Qwen" in text or "qwen" in lowered
            )
        )
        or "你能做什么" in text
        or "说明自己的身份" in text
        or "哪家的模型" in text
        or "当前对话模型" in text
        or "用什么模型" in text
        or "运行在哪个模型" in text
        or "哪种 AI" in text
        or "GPT 几" in text
        or "gpt 几" in lowered
        or "GPT-4" in text
        or "GPT-4o" in text
        or "gpt-4" in lowered
        or "gpt-4o" in lowered
        or "Claude" in text
        or "claude" in lowered
        or "OpenAI" in text
        or "openai" in lowered
        or "什么架构" in text
        or "哪个 model" in lowered
        or "什么 provider" in lowered
        or "哪个 provider" in lowered
        or ("基于什么" in text and "你" in text)
        or ("底层" in text and ("model" in lowered or "模型" in text))
        or ("背后" in text and ("provider" in lowered or "model" in lowered or "模型" in text))
        or ("模型" in text and ("运行" in text or "身份" in text))
        or ("AI" in text and ("哪个" in text or "什么" in text))
        or ("model" in lowered and ("what" in lowered or "which" in lowered))
    )


def _looks_like_crisis(text: str, route_state: dict) -> bool:
    if str(route_state.get("risk_level", "") or "") == "crisis":
        return True
    markers = ("不想活", "想死", "自杀", "伤害自己", "活不下去", "结束生命")
    return _contains_any(text, markers)


def _looks_like_negative_feedback(text: str, context) -> bool:
    feedback = getattr(context, "last_feedback", "")
    feedback_str = feedback.value if hasattr(feedback, "value") else str(feedback)
    if feedback_str == "negative":
        return True
    markers = (
        "没用", "废话", "不对", "离谱", "听不懂", "啥意思", "什么意思",
        "你刚刚", "你这回答", "不是让你", "我问的是", "别反问", "滚",
        "没明白", "不明白", "不懂", "看不懂", "不是这个意思", "跑偏",
        "没回答", "别绕", "重新答", "重新说", "说人话",
    )
    return _contains_any(text, markers)


def _looks_like_script_request(text: str, route_state: dict) -> bool:
    if route_state.get("needs_script") or route_state.get("input_intent") == "ask_script":
        return True
    return _contains_any(text, ("话术", "怎么说", "怎么回", "帮我写", "给我一段", "直接发"))


def _looks_like_options_request(text: str) -> bool:
    return _contains_any(
        text,
        (
            "选哪个", "怎么选", "几种", "几个选择", "方案对比", "A还是B",
            "哪个更", "可选", "两种", "两条路", "选择", "处理方式",
            "有哪些方案", "哪些方案", "有哪些方向", "有哪些路径",
            "不同打法", "不同路径", "选项", "不只给一种",
        ),
    )


def _strong_options_request(text: str) -> bool:
    return _contains_any(
        text,
        (
            "给选项", "给几个选择", "几个方向", "几种方向", "几个方案", "可选方案",
            "选择抓手", "哪几种路", "不同选择路径", "列一下选择", "处理方式",
            "哪个打法", "怎么选", "A 和 B 怎么选", "A还是B", "方案对比",
        ),
    )


def _looks_like_expand_request(text: str, frame_act: str) -> bool:
    if frame_act == "followup_detail":
        return True
    return _contains_any(
        text,
        (
            "展开", "细说", "讲讲", "详细", "具体点", "多说点", "继续讲",
            "继续说", "再往下", "更完整", "再解释", "多解释", "怎么落地",
            "把第二点", "上一点没听够",
        ),
    )


def _looks_like_method_request(text: str, route_state: dict, dialogue_task: str) -> bool:
    if route_state.get("needs_action") or route_state.get("input_intent") in {"ask_action", "ask_plan"}:
        return True
    if dialogue_task == "advance":
        return True
    return _contains_any(
        text,
        (
            "怎么办", "怎么做", "如何", "下一步", "建议", "方法", "效率",
            "管理", "怎么", "思路", "推进", "提升", "落地", "执行",
            "协作", "安排", "框架",
        ),
    )


def _looks_like_emotional_help(text: str, route_state: dict, dialogue_task: str, scene: str) -> bool:
    if route_state.get("input_intent") == "emotion_support" or dialogue_task == "contain":
        return True
    emotional_markers = (
        "吵架", "难受", "委屈", "不喜欢我", "分手", "崩溃", "心里堵",
        "烦", "慌", "关系", "被否定", "不理我", "冷淡", "恋爱",
        "情绪", "很难受",
    )
    if scene == "emotion" and _contains_any(text, emotional_markers):
        return True
    return _contains_any(
        text,
        emotional_markers,
    )


def _derive_user_goal(text: str, context, route_state: dict, expected: str) -> str:
    frame = getattr(context, "dialogue_frame", None)
    active_topic = _clip(getattr(frame, "active_topic", "") if frame else "", 100)
    if expected == "identity_answer":
        return "想知道当前系统/模型身份"
    if expected == "safety_support":
        return "需要安全支持和当下稳定"
    if expected == "repair_answer":
        previous_obligation, _ = _recent_previous_system_observation(context)
        return _clip(previous_obligation.get("user_goal") or active_topic or text, 100)
    if active_topic and str(getattr(frame, "user_act", "")) in {"followup_detail", "repair_challenge"}:
        return active_topic
    goal = getattr(getattr(context, "goal", None), "current", None)
    goal_text = _clip(getattr(goal, "description", "") if goal else "", 100)
    if goal_text and goal_text not in {"用户放弃", "未明确"}:
        return goal_text
    if route_state.get("main_scene") and route_state.get("main_scene") != "general":
        return _clip(text, 100)
    return _clip(text, 100)


def _fallback_requirement(expected: str, repair_required: bool) -> str:
    if repair_required:
        return "fallback 必须回到上一轮目标并补一个可见答案"
    mapping = {
        "direct_answer": "fallback 至少给一个直接默认答案",
        "framework": "fallback 至少给一个简短框架",
        "steps": "fallback 至少给一组可执行步骤",
        "options": "fallback 至少给可选路径",
        "script": "fallback 至少给一段可直接使用的话术",
        "emotional_support": "fallback 至少给可用承接和一个轻下一步",
        "identity_answer": "fallback 必须说明身份且不能编造底层模型",
        "safety_support": "fallback 必须优先安全支持",
    }
    return mapping.get(expected, "fallback 至少不能空泛换题")


def infer_response_obligation(context, user_input: str) -> dict:
    text = (user_input or "").strip()
    route_state = getattr(context, "route_state", None) or {}
    if not isinstance(route_state, dict):
        route_state = {}
    dialogue_task = getattr(context, "dialogue_task", "") or "clarify"
    frame = getattr(context, "dialogue_frame", None)
    frame_act = getattr(frame, "user_act", "") if frame else ""
    answer_contract = getattr(frame, "answer_contract", "") if frame else ""
    scene = getattr(context, "primary_scene", "") or (
        getattr(getattr(context, "scene_config", None), "scene_id", "") if getattr(context, "scene_config", None) else ""
    )

    previous_obligation, previous_final = _recent_previous_system_observation(context)
    previous_observed = str(previous_final.get("deliverable_observed") or "")
    previous_failed = bool(
        previous_final.get("output_satisfies_obligation") is False
        or previous_final.get("output_satisfies_obligation") == "Unknown"
        or previous_observed in {"question_only", "generic_fallback", "meta_strategy", "unknown"}
    )
    negative_feedback = _looks_like_negative_feedback(text, context)
    repair_required = bool(
        previous_failed
        and (negative_feedback or frame_act == "repair_challenge" or _contains_any(text, ("啥", "什么意思", "没听懂", "不对")))
    )

    current_task = "casual_chat"
    expected = "none"
    source = "current_turn"
    confidence = 0.55

    if _looks_like_identity_request(text):
        current_task = "ask_identity"
        expected = "identity_answer"
        source = "identity"
        confidence = 0.9
    elif _looks_like_crisis(text, route_state):
        current_task = "crisis_support"
        expected = "safety_support"
        source = "crisis"
        confidence = 0.9
    elif repair_required or frame_act == "repair_challenge":
        current_task = "repair_previous_answer" if previous_failed else "negative_feedback_repair"
        expected = "repair_answer"
        source = "repair"
        repair_required = True
        confidence = 0.82 if previous_failed else 0.72
    elif _looks_like_script_request(text, route_state):
        current_task = "ask_script"
        expected = "script"
        confidence = 0.82
    elif _looks_like_options_request(text):
        current_task = "ask_options"
        expected = "options"
        confidence = 0.84 if _strong_options_request(text) else 0.72
    elif _looks_like_emotional_help(text, route_state, dialogue_task, scene):
        current_task = "ask_emotional_help"
        expected = "emotional_support"
        confidence = 0.74
    elif _looks_like_expand_request(text, frame_act):
        current_task = "ask_expand"
        expected = "framework" if frame_act == "followup_detail" else "direct_answer"
        source = "inherited_context" if frame_act == "followup_detail" else "current_turn"
        confidence = 0.74
    elif _looks_like_method_request(text, route_state, dialogue_task):
        current_task = "ask_how_to"
        expected = "steps" if route_state.get("needs_action") or dialogue_task == "advance" else "framework"
        confidence = 0.78
    elif route_state.get("input_intent") == "explain":
        current_task = "ask_explanation"
        expected = "direct_answer"
        confidence = 0.68
    elif frame_act == "acknowledge":
        current_task = "casual_chat"
        expected = "none"
        source = "inherited_context"
        confidence = 0.58
    else:
        if dialogue_task == "reflect":
            current_task = "ask_explanation"
            expected = "framework"
            confidence = 0.68
        elif dialogue_task == "clarify" and answer_contract:
            current_task = "ask_explanation"
            expected = "direct_answer"
            confidence = 0.6

    answer_first_required = expected not in {"none"} and current_task not in {"casual_chat"}
    if expected in {"identity_answer", "repair_answer", "safety_support"}:
        clarification_allowed = "not_allowed"
    elif answer_first_required:
        clarification_allowed = "after_answer"
    else:
        clarification_allowed = "before_answer"

    user_goal = _derive_user_goal(text, context, route_state, expected)
    obligation = {
        "user_goal": user_goal,
        "current_task": current_task,
        "expected_deliverable": expected if expected in DELIVERABLES else "direct_answer",
        "answer_first_required": bool(answer_first_required),
        "clarification_allowed": clarification_allowed,
        "skill_may_enrich": True,
        "skill_may_decide_structure": False,
        "fallback_must_satisfy": _fallback_requirement(expected, repair_required),
        "repair_required": bool(repair_required),
        "repair_target": _clip(previous_obligation.get("user_goal", "") if previous_obligation else "", 100),
        "identity_answer_required": expected == "identity_answer",
        "internal_plan_allowed_in_final": False,
        "final_response_boundary_required": True,
        "source": source,
        "confidence": round(float(confidence), 2),
        "observation_basis": {
            "dialogue_task": dialogue_task,
            "dialogue_task_reason": getattr(context, "dialogue_task_reason", ""),
            "frame_act": frame_act,
            "route_intent": route_state.get("input_intent", "unknown"),
            "route_phase": route_state.get("conversation_phase", "new"),
            "route_scene": route_state.get("main_scene", "general"),
            "previous_obligation_failed": bool(previous_failed),
            "negative_feedback_observed": bool(negative_feedback),
        },
    }
    return obligation


def step1_8_response_obligation_observation(state: GraphState) -> GraphState:
    """Step 1.8: observe response obligation without changing behavior."""
    context = state["context"]
    user_input = state.get("user_input", "")
    trace = _get_runtime_trace(state, context)
    obligation = infer_response_obligation(context, user_input)
    trace["response_obligation"] = obligation
    trace["response_obligation_source"] = obligation.get("source", "unknown")
    trace["response_obligation_confidence"] = obligation.get("confidence", 0.0)
    trace["expected_deliverable"] = obligation.get("expected_deliverable", "")
    trace["answer_first_required_observed"] = bool(obligation.get("answer_first_required"))
    trace["clarification_allowed_observed"] = obligation.get("clarification_allowed", "")
    trace["skill_structure_override_risk"] = False
    trace["fallback_obligation"] = obligation.get("fallback_must_satisfy", "")
    trace["repair_obligation_required"] = bool(obligation.get("repair_required"))
    trace["identity_truth_required"] = bool(obligation.get("identity_answer_required"))
    trace["final_response_boundary_required"] = bool(obligation.get("final_response_boundary_required"))
    _set_runtime_field(context, "response_obligation", obligation)
    _set_runtime_field(context, "runtime_trace", trace)
    return {**state, "context": context, "runtime_trace": trace, "response_obligation": obligation}


def observe_skill_context(state: GraphState | dict, context) -> None:
    """Observe skill prompt authority after Step2 has had a chance to inject it."""
    trace = _get_runtime_trace(state, context)
    skill_prompt = str(getattr(context, "skill_prompt", "") or "")
    flags = getattr(context, "skill_flags", {}) or {}
    extension_used = []
    if isinstance(flags, dict):
        for name, value in flags.items():
            enabled = bool(value.get("enabled")) if isinstance(value, dict) else bool(value)
            if enabled:
                extension_used.append(str(name))
    if "【可选人格扩展包】" in skill_prompt and "leijun" not in extension_used:
        extension_used.append("leijun")

    primary_scene = getattr(context, "primary_scene", "") or (
        getattr(getattr(context, "scene_config", None), "scene_id", "") if getattr(context, "scene_config", None) else ""
    )
    default_scene_skill_used = bool(skill_prompt and primary_scene in {"sales", "management", "negotiation", "emotion"})
    structure_markers = ("往前接", "最终回复要体现", "开场", "结尾", "先看", "重点", "本轮")
    reasons = []
    for marker in structure_markers:
        if marker in skill_prompt:
            reasons.append(f"skill_prompt_contains_structure_signal:{marker}")
    if default_scene_skill_used and not extension_used:
        reasons.append("default_scene_skill_still_loaded_without_extension")
    if extension_used:
        reasons.append("extension_skill_enabled")

    trace["skill_context_used"] = bool(skill_prompt)
    trace["skill_extension_used"] = extension_used
    trace["default_scene_skill_used"] = default_scene_skill_used
    trace["skill_prompt_position"] = "late" if skill_prompt else "none"
    trace["skill_may_decide_structure"] = False
    trace["skill_override_risk_reason"] = reasons
    trace["skill_structure_override_risk"] = bool(reasons)
    obligation = trace.get("response_obligation")
    if isinstance(obligation, dict):
        obligation["skill_may_enrich"] = True
        obligation["skill_may_decide_structure"] = False
    _set_runtime_field(context, "runtime_trace", trace)


def _first_chunk(text: str) -> str:
    clean = str(text or "").strip()
    if not clean:
        return ""
    for sep in ("\n\n", "。", "！", "？", "!", "?"):
        if sep in clean:
            chunk = clean.split(sep, 1)[0].strip()
            return f"{chunk}{sep}" if sep in {"?", "？"} else chunk
    return clean[:80]


def _looks_question_only(output: str) -> bool:
    text = str(output or "").strip()
    if not text:
        return False
    question_marks = text.count("？") + text.count("?")
    return question_marks > 0 and len(text) <= 80 and not _contains_any(text, ("可以", "先", "建议", "做法", "答案"))


def _looks_generic_fallback(output: str) -> bool:
    text = str(output or "").strip()
    generic = (
        "这压力确实大", "我理解", "换谁都会这样", "最卡的是哪一步",
        "你是想先解决A", "还是先处理B", "我在", "再多说一点",
        "可以先这样做：先给一个默认动作",
    )
    return _contains_any(text, generic) or text in {"嗯。", "没问题。", "..."}


def _looks_internal_strategy(output: str) -> bool:
    text = str(output or "").strip()
    markers = (
        "本轮", "先承认", "先接住", "留一句", "收口", "策略", "框架是",
        "应该怎么接", "表达策略", "输出要求", "内部", "prompt", "场景原则",
        "内部计划", "生成计划", "五层结构",
        "武器库", "Mode A", "Mode B", "Mode C",
    )
    return _contains_any(text, markers)


def _looks_option_shape(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned:
        return False
    enumerated_count = sum(cleaned.count(marker) for marker in ("1.", "2.", "3.", "①", "②", "③"))
    choice_markers = (
        "一种是", "另一种", "第三种", "三个方向", "三个选择", "三个方案",
        "至少可以先看这三个方向", "可以按三个方向", "几个选择", "几个方向",
        "选项", "可选方案",
    )
    if _contains_any(cleaned, choice_markers):
        return True
    return enumerated_count >= 3 and _contains_any(cleaned, ("方向", "选择", "方案", "打法", "路径"))


def classify_deliverable_observed(output: str) -> str:
    text = str(output or "").strip()
    if not text:
        return "unknown"
    if _looks_internal_strategy(text):
        return "meta_strategy"
    if _looks_generic_fallback(text):
        return "generic_fallback"
    if _looks_question_only(text):
        return "question_only"
    if _looks_option_shape(text):
        return "options"
    if text.startswith("直接结论："):
        return "direct_answer"
    if _contains_any(text, ("可以这样说", "你可以这样说", "可以先这样回", "这句可以", "：")) and _contains_any(text, ("说", "回", "发")):
        return "script"
    if _contains_any(text, ("第一", "第二", "第三", "1.", "2.", "3.", "三步", "几步")):
        return "steps"
    if _contains_any(text, ("先", "核心", "重点", "方向", "可以")) and len(text) >= 40:
        return "framework"
    if _contains_any(text, ("难受", "委屈", "吵架", "不喜欢", "先稳住", "陪")):
        return "support"
    return "direct_answer"


def _deliverable_satisfies(expected: str, observed: str) -> bool | str:
    if observed == "unknown":
        return "Unknown"
    if expected == "none":
        return True
    if observed in {"meta_strategy", "generic_fallback", "question_only"}:
        return False
    accepted = {
        "direct_answer": {"direct_answer", "framework", "steps", "options", "script", "support"},
        "framework": {"framework", "steps", "options", "script", "direct_answer"},
        "steps": {"steps", "framework"},
        "options": {"options"},
        "script": {"script"},
        "emotional_support": {"support", "framework", "direct_answer"},
        "repair_answer": {"direct_answer", "framework", "steps", "options", "script", "support"},
        "identity_answer": {"direct_answer"},
        "safety_support": {"support", "direct_answer", "framework"},
    }
    return observed in accepted.get(expected, {expected})


def observe_final_output(
    state: GraphState | dict,
    context,
    final_output: str,
    *,
    fallback_used: bool | None = None,
) -> dict:
    """Observe whether final output appears to satisfy the obligation."""
    trace = _get_runtime_trace(state, context)
    obligation = trace.get("response_obligation")
    if not isinstance(obligation, dict):
        obligation = getattr(context, "response_obligation", None)
    if not isinstance(obligation, dict):
        obligation = infer_response_obligation(context, state.get("user_input", "") if isinstance(state, dict) else "")
        trace["response_obligation"] = obligation

    expected = str(obligation.get("expected_deliverable", "none") or "none")
    observed = classify_deliverable_observed(final_output)
    satisfies = _deliverable_satisfies(expected, observed)
    first = _first_chunk(final_output)
    first_is_question = first.endswith(("?", "？")) or _looks_question_only(first)
    answer_first_required = bool(obligation.get("answer_first_required"))
    answer_first_satisfied: bool | str
    if not answer_first_required:
        answer_first_satisfied = "Unknown"
    else:
        answer_first_satisfied = bool(first and not first_is_question and observed != "question_only")

    clarification_allowed = str(obligation.get("clarification_allowed", "") or "")
    clarification_violation = bool(
        clarification_allowed == "not_allowed"
        and ("?" in str(final_output) or "？" in str(final_output))
        and observed in {"question_only", "generic_fallback"}
    )
    internal_leak = observed == "meta_strategy" or _looks_internal_strategy(final_output)
    previous_fallback_check = trace.get("fallback_obligation_check")
    previous_fallback_generic = (
        isinstance(previous_fallback_check, dict)
        and previous_fallback_check.get("fallback_generic_observed") is True
    )
    fallback_generic = bool(
        previous_fallback_generic
        or ((fallback_used or trace.get("output_path") == "fallback") and observed == "generic_fallback")
    )
    skill_override = bool(trace.get("skill_structure_override_risk")) and observed in {"meta_strategy", "question_only"}

    repair_required = bool(obligation.get("repair_required"))
    if not repair_required:
        repair_completed: bool | str = "Unknown"
    else:
        repair_completed = bool(satisfies is True and not clarification_violation and observed != "generic_fallback")

    identity_required = bool(obligation.get("identity_answer_required"))
    identity_truth: bool | str = "Unknown"
    if identity_required:
        out = str(final_output or "")
        if trace.get("identity_truth_takeover_used") is True:
            identity_truth = True
        elif "GPT-4" in out or "gpt-4" in out.lower():
            identity_truth = False
        elif trace.get("llm_provider") not in {"", "unknown", None} or trace.get("llm_model"):
            identity_truth = True

    final_obs = {
        "output_satisfies_obligation": satisfies,
        "deliverable_observed": observed,
        "answer_first_satisfied": answer_first_satisfied,
        "clarification_violation_observed": clarification_violation,
        "internal_strategy_leak_observed": internal_leak,
        "fallback_generic_observed": fallback_generic,
        "skill_override_observed": skill_override,
        "repair_completed_observed": repair_completed,
        "identity_answer_truthful_observed": identity_truth,
    }
    trace["final_answer_observed"] = final_obs
    if trace.get("internal_strategy_leak_takeover_used") is True:
        trace["post_internal_leak_takeover_observed"] = final_obs
    if trace.get("repair_contract_takeover_used") is True:
        trace["post_repair_final_answer_observed"] = final_obs
    if trace.get("fallback_contract_takeover_used") is True:
        trace["post_fallback_contract_final_answer_observed"] = final_obs
    trace["fallback_obligation_check"] = {
        "fallback_used": bool(fallback_used if fallback_used is not None else trace.get("output_path") == "fallback"),
        "expected_deliverable": expected,
        "fallback_deliverable_observed": observed if (fallback_used or trace.get("output_path") == "fallback") else "unknown",
        "fallback_satisfies_obligation": satisfies if (fallback_used or trace.get("output_path") == "fallback") else "Unknown",
        "fallback_generic_observed": fallback_generic,
        "fallback_bypassed_final_gate": "Unknown",
    }
    _set_runtime_field(context, "runtime_trace", trace)
    if isinstance(state, dict):
        state["runtime_trace"] = trace
    return final_obs


def attach_observation_to_latest_system_history(state: GraphState | dict, context) -> None:
    """Persist observation in history metadata for next-turn repair observation."""
    trace = _get_runtime_trace(state, context)
    if not getattr(context, "history", None):
        return
    latest = context.history[-1]
    if getattr(latest, "role", "") != "system":
        return
    obligation = trace.get("response_obligation")
    final_obs = trace.get("final_answer_observed")
    if isinstance(obligation, dict):
        latest.metadata["response_obligation"] = obligation
    if isinstance(final_obs, dict):
        latest.metadata["final_answer_observed"] = final_obs
