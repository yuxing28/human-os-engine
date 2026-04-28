"""
Human-OS Engine - LangGraph 节点实现

对应总控规格的 Step 0-9。
"""

import time

from graph.state import GraphState
from graph.nodes.step0_input import (
    _estimate_text_chars,
    _record_memory_skip_reason,
    _record_memory_write_trace,
    _set_memory_gate_decision,
    _set_memory_stats,
    _set_runtime_field,
)
from graph.nodes.helpers import (
    _advance_mode_sequence,
    _build_memory_material_summary,
    _is_light_turn,
    _turn_behavior_profile,
    _update_trust_level,
    _record_strategy_to_library,
    _record_scene_evolution,
    _evaluate_strategy_experience,
    _extract_session_notes,
)


def _get_runtime_trace(state: GraphState, context) -> dict:
    trace = state.get("runtime_trace") if isinstance(state, dict) else None
    if not isinstance(trace, dict):
        trace = getattr(context, "runtime_trace", None)
    return trace if isinstance(trace, dict) else {}


def _set_runtime_trace(state: GraphState, context, trace: dict) -> None:
    _set_runtime_field(context, "runtime_trace", trace)
    if isinstance(state, dict):
        state["runtime_trace"] = trace


def _refresh_memory_trace_stats(context) -> None:
    from modules.memory import get_long_term_memory_stats, get_session_note_stats

    session_id = getattr(context, "session_id", "") or ""
    if not session_id:
        return
    try:
        note_stats = get_session_note_stats(session_id)
        long_term_stats = get_long_term_memory_stats(session_id)
        _set_memory_stats(
            context,
            session_note_size=note_stats.get("chars", 0),
            session_note_count=note_stats.get("count", 0),
            long_term_memory_size=long_term_stats.get("chars", 0),
            long_term_memory_count=long_term_stats.get("count", 0),
        )
    except Exception:
        return


def _resolve_step9_mode(state: GraphState, context) -> str:
    trace = _get_runtime_trace(state, context)
    turn_load_level = str(
        trace.get("turn_load_level")
        or getattr(context, "turn_load_level", "")
        or (state.get("turn_load_level") if isinstance(state, dict) else "")
        or "standard"
    ).strip().lower()
    step8_mode = str(trace.get("step8_mode") or getattr(context, "step8_mode", "") or "").strip().lower()

    if turn_load_level == "crisis" or step8_mode == "crisis":
        return "crisis_minimal"
    if turn_load_level == "light" or step8_mode == "minimal":
        return "light_minimal"
    if turn_load_level == "deep":
        return "full"
    return "standard_limited"


def _clip_text(text: str, limit: int = 28) -> str:
    clean = (text or "").strip().replace("\n", " ")
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip("，。！？：:；; ")


def _score_material_quality(material: dict, *, field: str = "session_note") -> int:
    if not isinstance(material, dict):
        return 0
    situation = str(material.get("situation", "") or "")
    decision_needed = str(material.get("decision_needed", "") or "")
    suggested_direction = str(material.get("suggested_direction", "") or "")
    avoid_next = str(material.get("avoid_next", "") or "")
    recommended_answer = str(material.get("recommended_answer", "") or "")
    risk_if_wrong = str(material.get("risk_if_wrong", "") or "")
    next_action = str(material.get("next_action", "") or "")
    if not any([situation, decision_needed, suggested_direction, avoid_next, recommended_answer, risk_if_wrong, next_action]):
        return 0
    score = 1
    if situation:
        score = 2
    if decision_needed:
        score += 1
    if recommended_answer or suggested_direction:
        score += 1
    if avoid_next:
        score += 1
    if risk_if_wrong:
        score += 1
    if next_action:
        score += 1
    return max(0, min(score, 5))


def _format_material_note(material: dict, *, kind: str = "session_note") -> str:
    if not isinstance(material, dict):
        return ""
    scene = _clip_text(str(material.get("scene", "") or ""), 16)
    situation = _clip_text(str(material.get("situation", "") or ""), 44)
    user_pressure = _clip_text(str(material.get("user_pressure", "") or ""), 36)
    decision_needed = _clip_text(str(material.get("decision_needed", "") or ""), 34)
    suggested_direction = _clip_text(str(material.get("suggested_direction", "") or ""), 40)
    recommended_answer = _clip_text(str(material.get("recommended_answer", "") or ""), 44)
    risk_if_wrong = _clip_text(str(material.get("risk_if_wrong", "") or ""), 36)
    next_action = _clip_text(str(material.get("next_action", "") or ""), 36)
    first_sentence_bias = _clip_text(str(material.get("first_sentence_bias", "") or ""), 44)
    avoid_next = _clip_text(str(material.get("avoid_next", "") or ""), 32)
    if kind == "next_pickup":
        if first_sentence_bias or decision_needed or recommended_answer or suggested_direction or avoid_next:
            parts = []
            if first_sentence_bias:
                parts.append(first_sentence_bias)
            if decision_needed:
                parts.append(f"判断：{decision_needed}")
            if recommended_answer:
                parts.append(f"建议：{recommended_answer}")
            if suggested_direction:
                parts.append(f"方向：{suggested_direction}")
            if risk_if_wrong:
                parts.append(f"风险：{risk_if_wrong}")
            if next_action:
                parts.append(f"下一步：{next_action}")
            if avoid_next:
                parts.append(f"避免：{avoid_next}")
            return "；".join(parts)[:160]
        return ""
    if kind == "world_state":
        parts = []
        if scene:
            parts.append(f"[{scene}]")
        if situation:
            parts.append(f"局面: {situation}")
        if user_pressure:
            parts.append(f"压力: {user_pressure}")
        if decision_needed:
            parts.append(f"判断: {decision_needed}")
        if recommended_answer:
            parts.append(f"建议: {recommended_answer}")
        if suggested_direction:
            parts.append(f"方向: {suggested_direction}")
        if risk_if_wrong:
            parts.append(f"风险: {risk_if_wrong}")
        if next_action:
            parts.append(f"下一步: {next_action}")
        if avoid_next:
            parts.append(f"避免: {avoid_next}")
        return " | ".join(parts)[:180]
    parts = []
    if scene:
        parts.append(f"[{scene}]")
    if situation:
        parts.append(f"局面: {situation}")
    if user_pressure:
        parts.append(f"压力: {user_pressure}")
    if decision_needed:
        parts.append(f"判断: {decision_needed}")
    if recommended_answer:
        parts.append(f"建议: {recommended_answer}")
    if suggested_direction:
        parts.append(f"方向: {suggested_direction}")
    if risk_if_wrong:
        parts.append(f"风险: {risk_if_wrong}")
    if next_action:
        parts.append(f"下一步: {next_action}")
    if avoid_next:
        parts.append(f"避免: {avoid_next}")
    return "；".join(parts)[:180]


def _build_session_summary_note(mode: str, context, user_input: str, output: str) -> str:
    material = _build_memory_material_summary(context, user_input, output)
    structured_note = _format_material_note(material, kind="session_note")
    text_in = _clip_text(user_input, 24)
    text_out = _clip_text(output, 24)
    if mode == "crisis_minimal":
        return structured_note or "高风险情绪，已进入安全支持路径。"
    if mode == "light_minimal":
        if structured_note and material.get("scene") in {"preference", "crisis_recovery"}:
            return structured_note
        if text_in:
            return f"轻量收束：{text_in}"
        return "轻量收束。"
    if mode == "standard_limited":
        if structured_note:
            return structured_note
        scene_id = context.scene_config.scene_id if getattr(context, "scene_config", None) else getattr(context, "primary_scene", "")
        focus = text_in or text_out or "本轮已收束"
        if scene_id:
            return f"本轮收束[{scene_id}]：{focus}"
        return f"本轮收束：{focus}"
    return _clip_text(text_out or text_in or "本轮已收束", 36)


def _should_write_long_term_memory_standard(context, user_input: str, output: str) -> bool:
    text = f"{(user_input or '').strip()} {(output or '').strip()}".strip()
    if not text:
        return False

    preference_markers = ("以后都", "一直", "更喜欢", "尽量", "不要", "更短", "更直接", "默认", "习惯", "总是", "每次都")
    project_markers = ("项目", "进度", "已经", "完成", "开始", "上线", "延期", "卡住", "需求", "目标", "客户", "团队")
    commitment_markers = ("我会", "我们会", "下次", "明天", "本周", "接下来", "先做", "先把", "跟进", "确认", "承诺")
    repeated_markers = ("反复", "每次", "老是", "还是", "又", "总是")
    relationship_markers = ("老板", "同事", "客户", "合作", "关系", "信任", "沟通", "对方")

    if any(marker in text for marker in preference_markers):
        return True
    if any(marker in text for marker in project_markers):
        return True
    if any(marker in text for marker in commitment_markers):
        return True
    if any(marker in text for marker in repeated_markers):
        return True
    if any(marker in text for marker in relationship_markers):
        return True

    frame = getattr(context, "dialogue_frame", None)
    if frame and getattr(frame, "answer_contract", ""):
        return True

    return False


def _build_standard_long_term_memory(context, user_input: str, output: str) -> tuple[str, str, float] | None:
    text = f"{(user_input or '').strip()} {(output or '').strip()}".strip()
    if not text:
        return None

    preference_markers = ("以后都", "一直", "更喜欢", "尽量", "不要", "更短", "更直接", "默认", "习惯", "总是", "每次都")
    project_markers = ("项目", "进度", "已经", "完成", "开始", "上线", "延期", "卡住", "需求", "目标", "客户", "团队")
    commitment_markers = ("我会", "我们会", "下次", "明天", "本周", "接下来", "先做", "先把", "跟进", "确认", "承诺")
    repeated_markers = ("反复", "每次", "老是", "还是", "又", "总是")
    relationship_markers = ("老板", "同事", "客户", "合作", "关系", "信任", "沟通", "对方")

    if any(marker in text for marker in preference_markers):
        return ("用户偏好：更喜欢更短、更直接的输出", "preference", 0.82)
    if any(marker in text for marker in project_markers):
        return ("项目状态：当前项目/对话进度需要先接顾虑再推进", "fact", 0.7)
    if any(marker in text for marker in commitment_markers):
        return ("明确承诺：下一轮会继续推进已确认的动作", "decision", 0.75)
    if any(marker in text for marker in repeated_markers):
        return ("重复问题：同一阻力反复出现，需要保持简短接住", "pattern", 0.68)
    if any(marker in text for marker in relationship_markers):
        return ("关系状态：需要先稳住沟通节奏和边界", "relationship", 0.72)

    frame = getattr(context, "dialogue_frame", None)
    if frame and getattr(frame, "answer_contract", ""):
        contract = _clip_text(getattr(frame, "answer_contract", ""), 36)
        if contract:
            return (f"本轮契约：{contract}", "decision", 0.7)

    return None


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    clean = (text or "").strip()
    return bool(clean) and any(marker in clean for marker in markers)


def _is_fallback_output(text: str) -> bool:
    return _contains_any(
        text,
        (
            "[流式生成失败",
            "使用默认回复",
            "可以先这样做：先给一个默认动作",
            "先给一个默认动作",
            "默认回复",
        ),
    )


def _is_template_like_output(text: str) -> bool:
    if not text:
        return False
    template_markers = (
        "可以先这样发",
        "可以先这样说",
        "你可以先说",
        "你可以直接发",
        "可以先回",
        "你可以先回",
        "先做这一步",
        "可以先这样做",
    )
    return _contains_any(text, template_markers)


def _set_semantic_extract_trace(
    context,
    *,
    input_chars: int | None = None,
    latency_ms: float | None = None,
    result_count: int | None = None,
    stored_count: int | None = None,
    skipped_reason: str | None = None,
) -> None:
    trace = _get_runtime_trace({}, context)
    if input_chars is not None:
        trace["semantic_extract_input_chars"] = max(0, int(input_chars))
    if latency_ms is not None:
        trace["semantic_extract_latency_ms"] = round(float(latency_ms or 0.0), 3)
    if result_count is not None:
        trace["semantic_extract_result_count"] = max(0, int(result_count))
    if stored_count is not None:
        trace["semantic_extract_stored_count"] = max(0, int(stored_count))
    if skipped_reason:
        reasons = trace.setdefault("semantic_extract_skipped_reason", [])
        if skipped_reason not in reasons:
            reasons.append(skipped_reason)
    _set_runtime_field(context, "runtime_trace", trace)


def _raw_user_memory_reason(context, user_input: str, output: str, step9_mode: str) -> tuple[bool, str]:
    text_in = (user_input or "").strip()
    text_out = (output or "").strip()
    if not text_in or not text_out:
        return False, "memory_write_skip:raw_user_no_long_term_value"

    if step9_mode == "crisis_minimal" or str(getattr(context, "turn_load_level", "")).strip().lower() == "crisis":
        return False, "memory_write_skip:raw_user_crisis_content"

    preference_markers = ("以后", "从现在开始", "记住", "默认", "直接一点", "更直接", "更短", "我偏好", "习惯")
    project_state_markers = ("项目", "客户压价", "这周必须", "先处理", "收口", "进度", "卡住", "上线", "交付")
    commitment_markers = ("我会", "我准备", "我打算", "接下来要", "明天要", "本周要", "必须")
    relationship_markers = ("关系", "合作状态", "信任", "老板", "同事", "客户")
    repeated_pattern_markers = ("每次", "总是", "老是", "一遇到", "反复", "都会先")
    short_term_emotion_markers = ("今天很累", "有点烦", "心里堵", "不想分析", "不想说太多", "有点懵", "委屈", "难受")
    complaint_markers = ("烦死了", "受不了", "真无语", "吐了", "气死", "好烦")

    if _contains_any(text_in, preference_markers):
        return True, "memory_write_reason:raw_user_long_term_preference"
    if _contains_any(text_in, project_state_markers):
        return True, "memory_write_reason:raw_user_project_state"
    if _contains_any(text_in, commitment_markers):
        return True, "memory_write_reason:raw_user_commitment"
    if _contains_any(text_in, relationship_markers) and len(text_in) >= 12:
        return True, "memory_write_reason:raw_user_relationship_state"
    if _contains_any(text_in, repeated_pattern_markers):
        return True, "memory_write_reason:raw_user_repeated_pattern"
    if _contains_any(text_in, short_term_emotion_markers) or getattr(context, "primary_scene", "") == "emotion":
        return False, "memory_write_skip:raw_user_short_term_emotion"
    if _contains_any(text_in, complaint_markers):
        return False, "memory_write_skip:raw_user_temporary_complaint"
    if len(text_in) <= 12:
        return False, "memory_write_skip:raw_user_session_note_enough"
    return False, "memory_write_skip:raw_user_no_long_term_value"


def _raw_system_memory_reason(context, output: str, step9_mode: str) -> tuple[bool, str]:
    text_out = (output or "").strip()
    if not text_out:
        return False, "memory_write_skip:raw_system_no_long_term_value"
    if step9_mode == "crisis_minimal" or str(getattr(context, "turn_load_level", "")).strip().lower() == "crisis":
        return False, "memory_write_skip:raw_system_crisis_support"
    if _is_fallback_output(text_out):
        return False, "memory_write_skip:raw_system_fallback_output"
    if len(text_out) < 40:
        return False, "memory_write_skip:raw_system_too_short"
    if _is_template_like_output(text_out):
        return False, "memory_write_skip:raw_system_template_like"

    turn_level = str(getattr(context, "turn_load_level", "")).strip().lower()
    if turn_level == "deep" and len(text_out) >= 120 and any(sep in text_out for sep in ("1.", "2.", "3.", "：", ":")):
        if _contains_any(text_out, ("审计", "路线图", "修复", "结论", "风险", "优先级", "下一步")):
            return True, "memory_write_reason:raw_system_deep_audit_summary"
        return True, "memory_write_reason:raw_system_structured_decision"

    if len(text_out) >= 100 and _contains_any(text_out, ("下一步", "先做", "最后", "结论", "决定", "对齐", "收口")):
        return True, "memory_write_reason:raw_system_high_value_closure"

    return False, "memory_write_skip:raw_system_low_value"


def _semantic_extract_reason(context, user_input: str, output: str, step9_mode: str, should_skip_heavy_memory: bool) -> tuple[bool, str]:
    text_in = (user_input or "").strip()
    text_out = (output or "").strip()
    turn_level = str(getattr(context, "turn_load_level", "")).strip().lower()

    if step9_mode == "crisis_minimal" or turn_level == "crisis":
        return False, "memory_write_skip:semantic_extract_crisis"
    if should_skip_heavy_memory:
        return False, "memory_write_skip:semantic_extract_no_long_term_signal"
    if _is_fallback_output(text_out):
        return False, "memory_write_skip:semantic_extract_fallback_output"
    if _is_template_like_output(text_out):
        return False, "memory_write_skip:semantic_extract_template_like"
    if len(text_in) + len(text_out) < 80:
        return False, "memory_write_skip:semantic_extract_too_short"
    if turn_level == "deep":
        return True, "memory_write_reason:semantic_extract_deep_task"
    if _contains_any(text_in, ("项目", "这周", "必须", "以后", "记住", "偏好", "决定", "先处理")):
        return True, "memory_write_reason:semantic_extract_project_state"
    if _contains_any(text_in, ("以后", "记住", "偏好", "默认", "习惯")):
        return True, "memory_write_reason:semantic_extract_preference_or_decision"
    return False, "memory_write_skip:semantic_extract_no_long_term_signal"


def _record_duplicate_skip_if_needed(context, result: dict | None) -> None:
    if isinstance(result, dict) and result.get("reason") == "duplicate_recent":
        _record_memory_skip_reason(context, "memory_write_skip:duplicate_recent_memory")


def _record_session_note_size_warnings(context) -> None:
    trace = _get_runtime_trace({}, context)
    note_size = int(trace.get("session_note_size", 0) or 0)
    note_count = int(trace.get("session_note_count", 0) or 0)
    if note_size > 12000 or note_count > 30:
        _record_memory_skip_reason(context, "memory_write_warning:session_note_compaction_needed")


def _record_focus_material_trace(context, material: dict) -> None:
    trace = _get_runtime_trace({}, context)
    session_score = _score_material_quality(material, field="session_note")
    next_score = _score_material_quality({
        "situation": material.get("decision_needed", ""),
        "decision_needed": material.get("decision_needed", ""),
        "suggested_direction": material.get("suggested_direction", ""),
        "avoid_next": material.get("avoid_next", ""),
    }, field="next_pickup")
    world_score = _score_material_quality({
        "situation": material.get("situation", ""),
        "decision_needed": material.get("decision_needed", ""),
        "suggested_direction": material.get("suggested_direction", ""),
        "avoid_next": material.get("avoid_next", ""),
    }, field="world_state")
    trace["session_note_quality_score"] = session_score
    trace["next_pickup_quality_score"] = next_score
    trace["world_state_quality_score"] = world_score
    trace["focus_source_quality"] = {
        "session_note": session_score,
        "next_pickup": next_score,
        "world_state": world_score,
    }
    trace["focus_material_has_decision_point"] = bool(material.get("decision_needed"))
    trace["focus_material_has_recommended_bias"] = bool(material.get("suggested_direction"))
    trace["memory_material_has_recommended_answer"] = bool(material.get("recommended_answer"))
    trace["memory_material_has_risk_if_wrong"] = bool(material.get("risk_if_wrong"))
    trace["memory_material_has_next_action"] = bool(material.get("next_action"))
    trace["next_pickup_first_sentence_ready"] = bool(material.get("first_sentence_bias"))
    trace["world_state_decision_card_ready"] = bool(
        material.get("decision_needed")
        and material.get("recommended_answer")
        and material.get("risk_if_wrong")
        and material.get("next_action")
    )
    trace["focus_material_too_generic"] = not bool(
        material.get("decision_needed")
        and material.get("suggested_direction")
        and material.get("recommended_answer")
    )
    reasons = trace.setdefault("memory_used_in_output_reason", [])
    if session_score >= 4 and "memory_material:session_note_decision_ready" not in reasons:
        reasons.append("memory_material:session_note_decision_ready")
    if next_score >= 4 and "memory_material:next_pickup_decision_ready" not in reasons:
        reasons.append("memory_material:next_pickup_decision_ready")
    if world_score >= 4 and "memory_material:world_state_decision_ready" not in reasons:
        reasons.append("memory_material:world_state_decision_ready")
    if trace["world_state_decision_card_ready"] and "memory_material:decision_card_ready" not in reasons:
        reasons.append("memory_material:decision_card_ready")
    if trace["next_pickup_first_sentence_ready"] and "memory_material:first_sentence_ready" not in reasons:
        reasons.append("memory_material:first_sentence_ready")
    if not material.get("decision_needed") and "memory_material:missing_decision_point" not in reasons:
        reasons.append("memory_material:missing_decision_point")
    if not material.get("suggested_direction") and "memory_material:missing_recommended_bias" not in reasons:
        reasons.append("memory_material:missing_recommended_bias")
    if not material.get("recommended_answer") and "memory_material:missing_recommended_answer" not in reasons:
        reasons.append("memory_material:missing_recommended_answer")
    if not material.get("risk_if_wrong") and "memory_material:missing_risk_if_wrong" not in reasons:
        reasons.append("memory_material:missing_risk_if_wrong")
    if not material.get("next_action") and "memory_material:missing_next_action" not in reasons:
        reasons.append("memory_material:missing_next_action")
    if trace["focus_material_too_generic"] and "memory_material:too_generic" not in reasons:
        reasons.append("memory_material:too_generic")
    _set_runtime_field(context, "runtime_trace", trace)


def _should_block_standard_long_term_for_crisis(context, step9_mode: str, user_input: str = "") -> tuple[bool, str]:
    trace = _get_runtime_trace({}, context)
    route_state = trace.get("route_state", {}) if isinstance(trace.get("route_state"), dict) else {}
    policy_state = route_state.get("policy_state", {}) if isinstance(route_state.get("policy_state"), dict) else {}
    text_in = (user_input or "").strip()

    turn_load_level = str(
        trace.get("turn_load_level")
        or getattr(context, "turn_load_level", "")
        or ""
    ).strip().lower()
    risk_level = str(route_state.get("risk_level", "") or "").strip().lower()
    conversation_phase = str(route_state.get("conversation_phase", "") or "").strip().lower()

    if step9_mode == "crisis_minimal" or turn_load_level == "crisis" or risk_level == "crisis":
        return True, "memory_write_skip:standard_long_term_crisis_content"
    if conversation_phase == "crisis_continuation":
        return True, "memory_write_skip:standard_long_term_safety_context"
    if conversation_phase == "crisis_recovery":
        return True, "memory_write_skip:standard_long_term_crisis_recovery"
    if bool(policy_state.get("is_safety_or_crisis")):
        return True, "memory_write_skip:standard_long_term_crisis_content"
    if bool(policy_state.get("is_crisis_recovery")):
        return True, "memory_write_skip:standard_long_term_crisis_recovery"
    crisis_continuation_source = str(trace.get("crisis_continuation_source", "") or "").strip().lower()
    if crisis_continuation_source and crisis_continuation_source != "none":
        return True, "memory_write_skip:standard_long_term_safety_context"
    pollution_risks = trace.get("memory_pollution_risk", [])
    if isinstance(pollution_risks, list) and "crisis_content_write_attempt" in pollution_risks:
        return True, "memory_write_skip:standard_long_term_safety_context"
    recovery_markers = ("安全了", "缓过来了", "缓一缓", "有点怕", "有点慌")
    if (
        text_in
        and _contains_any(text_in, recovery_markers)
        and str(trace.get("next_step_policy", "") or "").strip().lower() == "soft"
    ):
        return True, "memory_write_skip:standard_long_term_crisis_recovery"
    return False, ""


def _finalize_step9_trace(
    state: GraphState,
    context,
    *,
    mode: str,
    memory_write_count: int,
    experience_write_count: int,
    evolved_write_count: int,
    session_note_written: bool,
    semantic_extract_called: bool,
    skipped_writes: list[str],
) -> None:
    trace = _get_runtime_trace(state, context)
    trace["step9_mode"] = mode
    trace["memory_write_count"] = memory_write_count
    trace["experience_write_count"] = experience_write_count
    trace["evolved_write_count"] = evolved_write_count
    trace["session_note_written"] = session_note_written
    trace["semantic_extract_called"] = semantic_extract_called
    trace["step9_skipped_writes"] = skipped_writes
    _set_runtime_trace(state, context, trace)


def _should_use_light_feedback_path(context, user_input: str, output: str) -> bool:
    """
    默认先保速度，只有“这轮真的有沉淀价值”时才开重反馈。

    轻路径：
    - 普通闲聊
    - 情绪承接但没有明确推进
    - 输出没有动作性/决策性
    """
    text_in = (user_input or "").strip()
    text_out = (output or "").strip()
    if not text_in or not text_out:
        return True

    scene_id = context.scene_config.scene_id if getattr(context, "scene_config", None) else getattr(context, "primary_scene", "")
    turn_level = _turn_behavior_profile(context, text_in, scene_id)["level"]
    if turn_level == "light":
        return True

    heavy_markers = (
        "下一步", "先做", "先把", "方案", "计划", "执行", "推进", "验证", "对比",
        "边界", "选择", "动作", "清单", "落地", "本周", "明天", "回头", "跟进",
    )
    has_action_signal = any(marker in text_out for marker in heavy_markers) or any(marker in text_in for marker in ("怎么办", "怎么做", "下一步", "如何"))
    feedback_str = context.last_feedback.value if hasattr(context.last_feedback, "value") else str(context.last_feedback)

    if feedback_str == "negative":
        return False

    if turn_level == "medium":
        return not has_action_signal

    if scene_id in {"sales", "negotiation", "management"} and has_action_signal:
        return False

    return not has_action_signal


def _should_skip_feedback_learning(context, user_input: str, output: str) -> bool:
    """只有重轮才值得把学习链路完整跑一遍。"""
    scene_id = context.scene_config.scene_id if getattr(context, "scene_config", None) else getattr(context, "primary_scene", "")
    profile = _turn_behavior_profile(context, user_input, scene_id)
    strategic_scenes = {"sales", "negotiation", "management", "emotion"}
    if profile["level"] == "light":
        return True
    if profile["level"] == "medium":
        if scene_id in strategic_scenes:
            return False
        return _should_use_light_feedback_path(context, user_input, output)
    return False


def _should_store_raw_user_memory(user_input: str, output: str, context) -> bool:
    """
    控制用户原话写入长期记忆，避免把低信息噪音写进去。

    规则尽量保守：
    - 短句确认类输入不写
    - 纯寒暄/口头反馈不写
    - 输入或输出为空不写
    """
    text_in = (user_input or "").strip()
    text_out = (output or "").strip()
    if not text_in or not text_out:
        return False

    quick_acks = {"好的", "收到", "谢谢", "嗯", "ok", "OK", "行", "可以", "好", "嗯嗯"}
    if text_in in quick_acks:
        return False

    if getattr(context, "short_utterance", False) and len(text_in) <= 8:
        return False

    if len(text_in) <= 2 and len(text_out) <= 20:
        return False

    return True


def _should_store_raw_system_memory(output: str, context) -> bool:
    """
    控制系统原话是否入库。

    只有真正带动作、带推进、带边界的信息才保留，
    纯口头安抚、纯确认、纯空话尽量不写。
    """
    text_out = (output or "").strip()
    if not text_out:
        return False

    generic_responses = {"好的", "收到", "谢谢", "嗯", "ok", "OK", "行", "可以", "好", "嗯嗯", "明白", "了解"}
    if text_out in generic_responses:
        return False

    if getattr(context, "short_utterance", False) and len(text_out) <= 18:
        return False

    actionable_markers = (
        "下一步",
        "动作",
        "方案",
        "验证",
        "对比",
        "确认",
        "回看",
        "试点",
        "推进",
        "选择",
        "边界",
        "落地",
        "计划",
        "清单",
        "建议",
        "开始做",
        "先做",
        "先把",
        "拉齐",
        "收口",
        "对齐",
        "稳住",
    )
    if any(marker in text_out for marker in actionable_markers):
        return True

    if any(char.isdigit() for char in text_out) and len(text_out) >= 20:
        return True

    if any(sep in text_out for sep in ("1.", "2.", "3.", "•", "—")):
        return True

    if len(text_out) >= 60 and any(sep in text_out for sep in ("。", "？", "！", "：")):
        return True

    return False


def _build_failure_experience_content(
    scene_id: str,
    granular_goal: str,
    strategy_combo: str,
    failure_type: str,
    failure_code: str,
    user_input: str,
) -> str:
    """把失败信息压成一条可复用的经验记忆。"""
    reason_parts = []
    if failure_code:
        reason_parts.append(f"失败码={failure_code}")
    if failure_type:
        reason_parts.append(f"类型={failure_type}")
    reason_text = "，".join(reason_parts) if reason_parts else "未细分"
    input_preview = (user_input or "").strip().replace("\n", " ")[:40]
    return (
        f"失败经验: 场景={scene_id} | 目标={granular_goal} | 策略={strategy_combo} | {reason_text} | "
        f"触发输入={input_preview}"
    )


def step9_feedback(state: GraphState) -> GraphState:
    """Step 9：输出并记录反馈 + 串联模式推进 + 策略库持久化"""
    context = state["context"]
    user_input = state["user_input"]
    step9_mode = _resolve_step9_mode(state, context)
    memory_write_report: list[dict] = []
    memory_write_count = 0
    experience_write_count = 0
    evolved_write_count = 0
    session_note_written = False
    semantic_extract_called = False
    skipped_writes: list[str] = []

    # 添加系统回复到历史
    context.add_history("system", context.output)
    output_layers = state.get("output_layers")
    if output_layers and context.history and context.history[-1].role == "system":
        context.history[-1].metadata["output_layers"] = output_layers

    # 武器计数衰减（每 3 轮衰减一次，保持武器多样性）
    system_rounds = sum(1 for h in context.history if h.role == "system")
    if system_rounds % 3 == 0:
        context.decay_weapon_counts()

    def _record_memory_event(source: str, result):
        event = {"source": source}
        if isinstance(result, dict):
            event.update(result)
        else:
            event.update({"status": "unknown", "reason": "no_result"})
        memory_write_report.append(event)

    # 串联模式推进逻辑
    _advance_mode_sequence(context)

    # 【Phase 4-D】升维无效回退机制
    current_energy_mode = context.self_state.energy_mode
    energy_mode_val = current_energy_mode.value if hasattr(current_energy_mode, 'value') else str(current_energy_mode)
    feedback_str = context.last_feedback.value if hasattr(context.last_feedback, 'value') else str(context.last_feedback)

    if energy_mode_val == "C" and feedback_str == "negative":
        context.current_strategy.upgrade_failed_count += 1
        if context.current_strategy.upgrade_failed_count >= 2:
            # 连续 2 轮升维无效 → 标记不适合升维
            context.current_strategy.upgrade_eligible = False
            # 强制切换回 Mode A
            from schemas.enums import Mode as ModeEnum
            context.self_state.energy_mode = ModeEnum.A
            context.current_strategy.mode_sequence = []
            context.current_strategy.current_step_index = 0
            context.current_strategy.fallback_count = 0
    elif energy_mode_val == "C" and feedback_str == "positive":
        # 升维有效 → 重置失败计数
        context.current_strategy.upgrade_failed_count = 0
        context.current_strategy.upgrade_eligible = True

    # 动态更新 trust_level（基于反馈）
    _update_trust_level(context)

    session_id = getattr(context, "session_id", "") or state.get("session_id", "")
    material_summary = _build_memory_material_summary(context, user_input, context.output)
    _record_focus_material_trace(context, material_summary)
    round_num = system_rounds
    session_note = _build_session_summary_note(step9_mode, context, user_input, context.output)
    _set_memory_gate_decision(
        context,
        "step9",
        {
            "step9_mode": step9_mode,
            "turn_load_level": getattr(context, "turn_load_level", "standard"),
            "reason": "step9_mode_gate",
        },
    )

    if step9_mode in {"crisis_minimal", "light_minimal"}:
        if session_id and session_note:
            from modules.memory import add_session_note

            write_started_at = time.perf_counter()
            add_session_note(
                session_id=session_id,
                round_num=round_num,
                note_type="closure",
                content=session_note,
                detail={
                    "step9_mode": step9_mode,
                    "turn_load_level": getattr(context, "turn_load_level", "standard"),
                },
            )
            session_note_written = True
            _record_memory_event(
                "session_note",
                {
                    "status": "written",
                    "note_type": "closure",
                    "content_preview": session_note[:40],
                },
            )
            _record_memory_write_trace(
                context,
                stage="step9",
                target="session_note",
                mode=step9_mode,
                chars=_estimate_text_chars(session_note),
                latency_ms=(time.perf_counter() - write_started_at) * 1000,
                reason="memory_write_reason:session_note_continuity",
                pollution_risks=["crisis_content_write_attempt"] if step9_mode == "crisis_minimal" else [],
                extra={"note_type": "closure"},
            )
        if step9_mode == "crisis_minimal":
            skipped_writes.extend([
                "long_term_memory",
                "raw_conversation_memory",
                "semantic_extract",
                "strategy_library",
                "scene_evolution",
                "experience_learning",
                "success_spectrum",
                "failure_experience",
            ])
            _record_memory_skip_reason(context, "step9:crisis_minimal_skips_learning_writes")
        else:
            skipped_writes.extend([
                "long_term_memory",
                "semantic_extract",
                "strategy_library",
                "scene_evolution",
                "experience_learning",
                "success_spectrum",
                "failure_experience",
                "raw_conversation_memory",
            ])
            _record_memory_skip_reason(context, "step9:light_minimal_skips_heavy_writes")
        _refresh_memory_trace_stats(context)
        context.memory_write_report = memory_write_report[-10:]
        if context.history and context.history[-1].role == "system":
            context.history[-1].metadata["memory_write_report"] = context.memory_write_report
        _finalize_step9_trace(
            state,
            context,
            mode=step9_mode,
            memory_write_count=memory_write_count,
            experience_write_count=experience_write_count,
            evolved_write_count=evolved_write_count,
            session_note_written=session_note_written,
            semantic_extract_called=semantic_extract_called,
            skipped_writes=skipped_writes,
        )
        return {**state, "context": context}

    if step9_mode == "standard_limited":
        if session_id and session_note:
            from modules.memory import add_session_note

            write_started_at = time.perf_counter()
            add_session_note(
                session_id=session_id,
                round_num=round_num,
                note_type="closure",
                content=session_note,
                detail={
                    "step9_mode": step9_mode,
                    "turn_load_level": getattr(context, "turn_load_level", "standard"),
                },
            )
            session_note_written = True
            _record_memory_event(
                "session_note",
                {
                    "status": "written",
                    "note_type": "closure",
                    "content_preview": session_note[:40],
                },
            )
            _record_memory_write_trace(
                context,
                stage="step9",
                target="session_note",
                mode=step9_mode,
                chars=_estimate_text_chars(session_note),
                latency_ms=(time.perf_counter() - write_started_at) * 1000,
                reason="memory_write_reason:session_note_continuity",
                extra={"note_type": "closure"},
            )

        block_standard_memory, block_reason = _should_block_standard_long_term_for_crisis(context, step9_mode, user_input)
        standard_memory = None if block_standard_memory else _build_standard_long_term_memory(context, user_input, context.output)
        if standard_memory:
            from modules.memory import store_memory

            content, memory_type, importance = standard_memory
            write_started_at = time.perf_counter()
            result = store_memory(
                user_id=session_id,
                content=content,
                memory_type=memory_type,
                importance=importance,
            )
            memory_write_count += 1
            _record_memory_event("standard_long_term", result)
            _record_memory_write_trace(
                context,
                stage="step9",
                target="standard_long_term_memory",
                mode=step9_mode,
                chars=_estimate_text_chars(content),
                latency_ms=(time.perf_counter() - write_started_at) * 1000,
                reason="standard_high_value_memory",
                duplicate=(result or {}).get("reason") == "duplicate_recent",
                pollution_risks=["duplicate_memory_possible"] if (result or {}).get("reason") == "duplicate_recent" else [],
                extra={"memory_type": memory_type},
            )
            _record_duplicate_skip_if_needed(context, result)
        else:
            skipped_writes.append("standard_long_term_memory")
            skip_reason = block_reason or "step9:standard_long_term_memory_skipped"
            _record_memory_skip_reason(context, skip_reason)
            trace = _get_runtime_trace(state, context)
            trace.setdefault("memory_write_detail", []).append(
                {
                    "stage": "step9",
                    "target": "standard_long_term_memory",
                    "mode": step9_mode,
                    "chars": 0,
                    "latency_ms": 0.0,
                    "reason": skip_reason,
                    "duplicate": False,
                    "action": "skipped",
                    "skip_reason": "crisis_or_recovery_content" if block_reason else "no_high_value_signal",
                }
            )
            _set_runtime_trace(state, context, trace)

        skipped_writes.extend([
            "semantic_extract",
            "raw_conversation_memory",
            "strategy_library",
            "scene_evolution",
            "experience_learning",
            "success_spectrum",
            "failure_experience",
        ])
        _refresh_memory_trace_stats(context)
        context.memory_write_report = memory_write_report[-10:]
        if context.history and context.history[-1].role == "system":
            context.history[-1].metadata["memory_write_report"] = context.memory_write_report
        _finalize_step9_trace(
            state,
            context,
            mode=step9_mode,
            memory_write_count=memory_write_count,
            experience_write_count=experience_write_count,
            evolved_write_count=evolved_write_count,
            session_note_written=session_note_written,
            semantic_extract_called=semantic_extract_called,
            skipped_writes=skipped_writes,
        )
        return {**state, "context": context}

    should_skip_heavy_memory = _should_use_light_feedback_path(context, user_input, context.output)
    should_skip_learning = _should_skip_feedback_learning(context, user_input, context.output)

    # 存储对话记忆（语义提炼 + 原始对话）
    from modules.memory import store_memory, extract_important_facts, retrieve_memory, add_session_note

    # 【阶段三优化】语义提炼：带熔断器的记忆提取
    semantic_input_chars = _estimate_text_chars(user_input) + _estimate_text_chars(context.output)
    _set_semantic_extract_trace(context, input_chars=semantic_input_chars)
    should_run_semantic_extract, semantic_extract_reason = _semantic_extract_reason(
        context,
        user_input,
        context.output,
        step9_mode,
        should_skip_heavy_memory,
    )

    if should_run_semantic_extract and not context._extract_disabled:
        try:
            extract_started_at = time.perf_counter()
            existing = retrieve_memory(context.session_id, user_input, limit=5)
            extracted = extract_important_facts(user_input, context.output, existing)
            semantic_extract_called = True
            extract_latency_ms = (time.perf_counter() - extract_started_at) * 1000
            _set_semantic_extract_trace(
                context,
                latency_ms=extract_latency_ms,
                result_count=1 if extracted else 0,
                stored_count=1 if extracted else 0,
            )
            _record_memory_write_trace(
                context,
                stage="step9",
                target="semantic_extract",
                mode=step9_mode,
                chars=_estimate_text_chars((extracted or {}).get("content", "")),
                latency_ms=extract_latency_ms,
                reason=semantic_extract_reason,
                pollution_risks=["semantic_extract_from_emotion_turn"] if context.primary_scene == "emotion" else [],
                extra={
                    "extracted_count": 1 if extracted else 0,
                    "stored_count": 1 if extracted else 0,
                    "memory_type": (extracted or {}).get("type", ""),
                },
            )
            if extracted:
                store_started_at = time.perf_counter()
                result = store_memory(
                    user_id=context.session_id,
                    content=extracted["content"],
                    memory_type=extracted["type"],
                    importance=extracted["importance"],
                )
                memory_write_count += 1
                _record_memory_event("semantic_extract", result)
                _record_memory_write_trace(
                    context,
                    stage="step9",
                    target="semantic_extract_store",
                    mode=step9_mode,
                    chars=_estimate_text_chars(extracted["content"]),
                    latency_ms=(time.perf_counter() - store_started_at) * 1000,
                    reason=semantic_extract_reason,
                    duplicate=(result or {}).get("reason") == "duplicate_recent",
                    pollution_risks=["duplicate_memory_possible"] if (result or {}).get("reason") == "duplicate_recent" else [],
                    extra={"memory_type": extracted["type"]},
                )
                _record_duplicate_skip_if_needed(context, result)
                context._extract_failure_count = 0  # 成功，重置计数
        except Exception:
            context._extract_failure_count += 1
            if context._extract_failure_count >= 2:
                context._extract_disabled = True  # 熔断：本会话禁用提取
    else:
        skip_reason = "step9:semantic_extract_disabled" if context._extract_disabled else semantic_extract_reason
        _record_memory_skip_reason(context, skip_reason)
        _set_semantic_extract_trace(context, skipped_reason=skip_reason, latency_ms=0.0, result_count=0, stored_count=0)

    # 原始对话（低重要性，仅用于上下文重建）
    # 用户原话尽量保留，系统原话只留真正有动作/推进信息的部分。
    should_store_raw_user, raw_user_reason = _raw_user_memory_reason(context, user_input, context.output, step9_mode)
    if should_store_raw_user:
        user_write_started_at = time.perf_counter()
        user_result = store_memory(
            user_id=context.session_id,
            content=f"用户: {user_input}",
            memory_type="conversation",
            importance=0.3,
        )
        memory_write_count += 1
        _record_memory_event("raw_user", user_result)
        _record_memory_write_trace(
            context,
            stage="step9",
            target="raw_user_memory",
            mode=step9_mode,
            chars=_estimate_text_chars(user_input),
            latency_ms=(time.perf_counter() - user_write_started_at) * 1000,
            reason=raw_user_reason,
            duplicate=(user_result or {}).get("reason") == "duplicate_recent",
            pollution_risks=["raw_user_emotion_may_be_short_term"] if context.primary_scene == "emotion" else (["duplicate_memory_possible"] if (user_result or {}).get("reason") == "duplicate_recent" else []),
            extra={"memory_type": "conversation"},
        )
        _record_duplicate_skip_if_needed(context, user_result)
    else:
        memory_write_report.append({
            "source": "raw_conversation_gate",
            "status": "skipped",
            "reason": raw_user_reason,
        })
        _record_memory_skip_reason(context, raw_user_reason)

    should_store_raw_system, raw_system_reason = _raw_system_memory_reason(context, context.output, step9_mode)
    if not should_skip_heavy_memory and should_store_raw_system:
        system_write_started_at = time.perf_counter()
        system_result = store_memory(
            user_id=context.session_id,
            content=f"系统: {context.output}",
            memory_type="conversation",
            importance=0.2,
        )
        memory_write_count += 1
        _record_memory_event("raw_system", system_result)
        _record_memory_write_trace(
            context,
            stage="step9",
            target="raw_system_memory",
            mode=step9_mode,
            chars=_estimate_text_chars(context.output),
            latency_ms=(time.perf_counter() - system_write_started_at) * 1000,
            reason=raw_system_reason,
            duplicate=(system_result or {}).get("reason") == "duplicate_recent",
            pollution_risks=["raw_system_memory_written"],
            extra={"memory_type": "conversation"},
        )
        _record_duplicate_skip_if_needed(context, system_result)
    else:
        _record_memory_event(
            "raw_system",
            {
                "status": "skipped",
                "reason": raw_system_reason if not should_skip_heavy_memory else "step9:raw_system_memory_skipped_light_feedback_gate",
                "memory_type": "conversation",
                "bucket": "conversation",
                "importance": 0.2,
                "content_preview": f"系统: {(context.output or '')[:20]}",
            },
        )
        _record_memory_skip_reason(
            context,
            "step9:raw_system_memory_skipped_light_feedback_gate" if should_skip_heavy_memory else raw_system_reason,
        )

    # 轻量回复只做最必要的状态推进，不额外沉淀策略库，避免把“顺手接一句”也记成经验
    if not should_skip_learning:
        # 策略库/反例库持久化（新增）
        strategy_started_at = time.perf_counter()
        _record_strategy_to_library(context, user_input)
        evolved_write_count += 1
        _record_memory_write_trace(
            context,
            stage="step9",
            target="strategy_library",
            mode=step9_mode,
            chars=_estimate_text_chars(context.output),
            latency_ms=(time.perf_counter() - strategy_started_at) * 1000,
            reason="memory_write_reason:strategy_library_full_learning_path",
            pollution_risks=["template_like_strategy_write"] if "怎么" not in (user_input or "") and "帮我" not in (user_input or "") else [],
        )

        # 【场景插件】自我进化记录
        evolution_started_at = time.perf_counter()
        _record_scene_evolution(context)
        evolved_write_count += 1
        _record_memory_write_trace(
            context,
            stage="step9",
            target="scene_evolution",
            mode=step9_mode,
            chars=0,
            latency_ms=(time.perf_counter() - evolution_started_at) * 1000,
            reason="memory_write_reason:scene_evolution_full_learning_path",
        )
    else:
        _record_memory_skip_reason(
            context,
            "memory_write_skip:learning_path_skipped_light_or_crisis" if step9_mode in {"light_minimal", "crisis_minimal"} else "memory_write_skip:learning_path_skipped_standard_limited",
        )

    # 【Phase 3 反例库】记录失败策略到反例库
    if not should_skip_learning and feedback_str == "negative":
        scene_id = context.scene_config.scene_id if context.scene_config else ""
        granular_goal = getattr(context.goal, 'granular_goal', None)
        if scene_id and granular_goal:
            # 优先使用 combo_name，回退到 stage
            strategy_combo = context.current_strategy.combo_name if context.current_strategy and context.current_strategy.combo_name else (context.current_strategy.stage if context.current_strategy else "unknown")
            emotion_type = context.user.emotion.type.value if hasattr(context.user.emotion.type, 'value') else str(context.user.emotion.type)
            trust_level = context.user.trust_level.value if hasattr(context.user.trust_level, 'value') else str(context.user.trust_level)
            
            from modules.L5.counter_example_lib import (
                record_failure,
                infer_failure_type,
                infer_failure_code,
            )
            # 推断失败类型
            failure_type = ""
            failure_code = ""
            last_judge = {}
            if context.history:
                for h in reversed(context.history):
                    if h.metadata and "judge_result" in h.metadata:
                        last_judge = h.metadata["judge_result"]
                        break
            if last_judge:
                failure_type = infer_failure_type(last_judge).value
                inferred_code = infer_failure_code(
                    last_judge,
                    context={
                        "scene_id": scene_id,
                        "goal": granular_goal,
                    },
                    output_text=context.output,
                )
                failure_code = inferred_code.value if inferred_code else ""

            attribution = {
                "what_changed": "本轮策略/武器组合执行",
                "expected_improvement": "提升相关性、共情和推进拿捏",
                "observed_metrics": {
                    "judge_result": last_judge,
                    "feedback": feedback_str,
                },
                "inferred_reason": {
                    "failure_type": failure_type,
                    "failure_code": failure_code,
                },
                "decision": "record_failure",
            }
            record_failure(
                scene_id=scene_id,
                goal=granular_goal,
                strategy=strategy_combo,
                context={"emotion": emotion_type, "trust_level": trust_level},
                failure_type=failure_type,
                failure_code=failure_code,
                attribution=attribution,
            )
            experience_write_count += 1
            _record_memory_write_trace(
                context,
                stage="step9",
                target="failure_experience_library",
                mode=step9_mode,
                chars=0,
                latency_ms=0.0,
                reason="memory_write_reason:failure_experience_negative_feedback",
            )
            # 失败经验沉淀到长期记忆，供后续“先别做什么”直接参考
            if failure_type or failure_code:
                failure_memory = _build_failure_experience_content(
                    scene_id=scene_id,
                    granular_goal=granular_goal,
                    strategy_combo=strategy_combo,
                    failure_type=failure_type,
                    failure_code=failure_code,
                    user_input=user_input,
                )
                failure_store_started_at = time.perf_counter()
                failure_memory_result = store_memory(
                    user_id=context.session_id,
                    content=failure_memory,
                    memory_type="failure",
                    importance=0.85,
                )
                memory_write_count += 1
                _record_memory_event("failure_experience", failure_memory_result)
                _record_memory_write_trace(
                    context,
                    stage="step9",
                    target="failure_experience",
                    mode=step9_mode,
                    chars=_estimate_text_chars(failure_memory),
                    latency_ms=(time.perf_counter() - failure_store_started_at) * 1000,
                    reason="memory_write_reason:failure_experience_negative_feedback",
                    duplicate=(failure_memory_result or {}).get("reason") == "duplicate_recent",
                    pollution_risks=["duplicate_memory_possible"] if (failure_memory_result or {}).get("reason") == "duplicate_recent" else [],
                    extra={"memory_type": "failure"},
                )
                _record_duplicate_skip_if_needed(context, failure_memory_result)

    # 【方向C-1】成功策略谱沉淀
    if not should_skip_learning and feedback_str == "positive":
        scene_id = context.scene_config.scene_id if context.scene_config else ""
        granular_goal = getattr(context.goal, 'granular_goal', None)
        if scene_id and granular_goal:
            strategy_combo = context.current_strategy.combo_name if context.current_strategy and context.current_strategy.combo_name else (context.current_strategy.stage if context.current_strategy else "unknown")
            emotion_type = context.user.emotion.type.value if hasattr(context.user.emotion.type, 'value') else str(context.user.emotion.type)
            trust_level = context.user.trust_level.value if hasattr(context.user.trust_level, 'value') else str(context.user.trust_level)
            # 从最近一轮的judge_result取分
            last_score = 0.0
            if context.history:
                for h in reversed(context.history):
                    if h.metadata:
                        jr = h.metadata.get("judge_result", {})
                        if jr:
                            last_score = float(jr.get("overall", 0))
                        if last_score <= 0:
                            last_score = float(h.metadata.get("llm_score", 0))
                    if last_score > 0:
                        break
            
            from modules.L5.counter_example_lib import record_success
            record_success(
                scene_id=scene_id,
                goal=granular_goal,
                strategy=strategy_combo,
                context={"emotion": emotion_type, "trust_level": trust_level},
                score=last_score
            )
            experience_write_count += 1
            _record_memory_write_trace(
                context,
                stage="step9",
                target="success_spectrum",
                mode=step9_mode,
                chars=0,
                latency_ms=0.0,
                reason="memory_write_reason:success_spectrum_positive_feedback",
            )

    # 【Phase 3】策略评估与经验沉淀
    if not should_skip_learning:
        evaluate_started_at = time.perf_counter()
        _evaluate_strategy_experience(context, user_input)
        experience_write_count += 1
        _record_memory_write_trace(
            context,
            stage="step9",
            target="strategy_experience",
            mode=step9_mode,
            chars=0,
            latency_ms=(time.perf_counter() - evaluate_started_at) * 1000,
            reason="memory_write_reason:strategy_experience_full_learning_path",
        )

    # 【Session Memory】提取本轮重要决策为会话笔记
    if not should_skip_learning:
        extract_note_started_at = time.perf_counter()
        _extract_session_notes(context, user_input, system_rounds)
        session_note_written = True
        _record_memory_write_trace(
            context,
            stage="step9",
            target="session_note",
            mode=step9_mode,
            chars=_estimate_text_chars(context.output),
            latency_ms=(time.perf_counter() - extract_note_started_at) * 1000,
            reason="memory_write_reason:session_note_continuity",
            pollution_risks=["session_note_size_growing"],
            extra={"note_type": "structured_session_notes"},
        )

    if not session_note_written and session_id:
        session_note = _build_session_summary_note(step9_mode, context, user_input, context.output)
        if session_note:
            write_started_at = time.perf_counter()
            add_session_note(
                session_id=session_id,
                round_num=round_num,
                note_type="closure",
                content=session_note,
                detail={
                    "step9_mode": step9_mode,
                    "turn_load_level": getattr(context, "turn_load_level", "standard"),
                },
            )
            session_note_written = True
            _record_memory_event(
                "session_note",
                {
                    "status": "written",
                    "note_type": "closure",
                    "content_preview": session_note[:40],
                },
            )
            _record_memory_write_trace(
                context,
                stage="step9",
                target="session_note",
                mode=step9_mode,
                chars=_estimate_text_chars(session_note),
                latency_ms=(time.perf_counter() - write_started_at) * 1000,
                reason="memory_write_reason:session_note_continuity",
                extra={"note_type": "closure"},
            )

    # 统一在函数尾部落盘，确保后续新增事件（如 failure_experience）不丢。
    _refresh_memory_trace_stats(context)
    _record_session_note_size_warnings(context)
    context.memory_write_report = memory_write_report[-10:]
    if context.history and context.history[-1].role == "system":
        context.history[-1].metadata["memory_write_report"] = context.memory_write_report

    _finalize_step9_trace(
        state,
        context,
        mode=step9_mode,
        memory_write_count=memory_write_count,
        experience_write_count=experience_write_count,
        evolved_write_count=evolved_write_count,
        session_note_written=session_note_written,
        semantic_extract_called=semantic_extract_called,
        skipped_writes=skipped_writes,
    )

    return {**state, "context": context}
