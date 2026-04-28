"""
Human-OS Engine - 流式执行管道

绕过 LangGraph，直接调用各节点函数。

注意：
- Step 8 内部仍可逐 token 生成草稿
- 但对外只返回最终修正后的成品文本
- 不把中间策略、模式、武器和内部状态直接暴露出去
"""

import json
import time
from typing import Callable, Generator
from schemas.context import Context
from graph.nodes.style_adapter import _adapt_output_style, _replace_academic_terms
from utils.logger import info


def _build_strategy_skeleton_hint(context: Context) -> str:
    """把 Step6 生成的策略骨架转成短提示，供 Step8 流式生成使用。"""
    skeleton = getattr(getattr(context, "current_strategy", None), "skeleton", None)
    if not skeleton:
        return ""

    parts = []
    if getattr(skeleton, "do_now", None):
        parts.append(f"先做：{'；'.join(skeleton.do_now[:2])}")
    if getattr(skeleton, "do_later", None):
        parts.append(f"后做：{'；'.join(skeleton.do_later[:2])}")
    if getattr(skeleton, "avoid_now", None):
        parts.append(f"先别做：{'；'.join(skeleton.avoid_now[:2])}")
    if getattr(skeleton, "fallback_move", ""):
        parts.append(f"卡住时：{skeleton.fallback_move}")

    if not parts:
        return ""
    return "【策略骨架】\n" + "\n".join(parts)


def _build_memory_hint_signals(strategy_plan) -> dict:
    """把策略描述里的记忆提示词拆成几个可观测标记。"""
    description = ""
    if strategy_plan is not None:
        description = str(getattr(strategy_plan, "description", "") or "")
    return {
        "failure_avoid_hint": "失败规避提示：" in description,
        "experience_digest_hint": "经验索引提示：" in description,
        "decision_experience_hint": "经验决策提示：" in description,
    }


def _chunk_text(text: str, size: int = 3) -> Generator[str, None, None]:
    """内部轻量分块，避免为了快路径再反向依赖 API 渲染层。"""
    for i in range(0, len(text), size):
        yield text[i:i + size]


def _should_use_fast_speech(
    user_input: str,
    scene: str,
    emotion_intensity: float,
    memory_context: str,
    evidence_content: str,
    guidance_prompt: str,
) -> bool:
    """
    低复杂度输入走快速版话术生成。

    目标不是改变产品逻辑，而是把“短句、轻情绪、无复杂上下文”的等待时间压下去。
    """
    text = (user_input or "").strip()
    if not text:
        return False

    if len(text) > 28:
        return False

    if scene in {"sales", "negotiation"}:
        return False

    if emotion_intensity > 0.45:
        return False

    if evidence_content or guidance_prompt:
        return False

    if memory_context and len(memory_context) > 280:
        return False

    complex_markers = ["怎么办", "为什么", "分析", "策略", "方案", "计划", "复盘", "谈判", "报价", "成交"]
    if any(marker in text for marker in complex_markers):
        return False

    return True


def _should_bypass_stream_llm(context: Context, user_input: str, scene: str) -> bool:
    """真实流式入口的轻承接直出。"""
    from graph.nodes.helpers import _should_take_task_first_fallback

    text = (user_input or "").strip()
    if not text:
        return True

    continuity_focus = getattr(context, "memory_continuity_focus", None)
    if isinstance(continuity_focus, dict):
        focus_type = str(continuity_focus.get("focus_type", "") or "")
        if continuity_focus.get("memory_use_required") and focus_type and focus_type != "none":
            return False

    route_state = getattr(context, "route_state", None) or {}
    if isinstance(route_state, dict):
        conversation_phase = str(route_state.get("conversation_phase", "") or "")
        if conversation_phase in {"followup", "revision", "continuation", "crisis_recovery", "crisis_continuation"}:
            return False

    if _should_take_task_first_fallback(context, text, scene):
        return True

    deep_markers = ["怎么办", "怎么做", "如何", "为什么", "方案", "分析", "下一步", "怎么选", "我该怎么"]
    if any(marker in text for marker in deep_markers):
        return False

    return False


def run_step0(user_input: str, context: Context) -> tuple[Context, dict]:
    """Step 0: 输入处理"""
    from graph.nodes import step0_receive_input
    state = {"context": context, "user_input": user_input}
    result = step0_receive_input(state)
    return result.get("context", context), result


def run_step1(context: Context, user_input: str) -> tuple[Context, dict]:
    """Step 1: 识别"""
    from graph.nodes import step1_identify
    state = {"context": context, "user_input": user_input}
    result = step1_identify(state)
    return result.get("context", context), result


def run_step1_5(context: Context, user_input: str) -> tuple[Context, dict]:
    """Step 1.5: 元控制器"""
    from graph.nodes import step1_5_meta_controller
    state = {"context": context, "user_input": user_input}
    result = step1_5_meta_controller(state)
    return result.get("context", context), result


def run_step1_7(context: Context, user_input: str) -> tuple[Context, dict]:
    """Step 1.7: 主任务判断"""
    from graph.nodes import step1_7_dialogue_task
    state = {"context": context, "user_input": user_input}
    result = step1_7_dialogue_task(state)
    return result.get("context", context), result


def run_step2(context: Context, user_input: str) -> tuple[Context, dict]:
    """Step 2: 目标检测"""
    from graph.nodes import step2_goal_detection
    state = {"context": context, "user_input": user_input}
    result = step2_goal_detection(state)
    return result.get("context", context), result


def run_step3(context: Context, user_input: str) -> tuple[Context, dict]:
    """Step 3: 自检"""
    from graph.nodes import step3_self_check
    state = {"context": context, "user_input": user_input}
    result = step3_self_check(state)
    return result.get("context", context), result


def run_step4(context: Context, user_input: str) -> tuple[Context, dict]:
    """Step 4: 优先级"""
    from graph.nodes import step4_priority
    state = {"context": context, "user_input": user_input}
    result = step4_priority(state)
    return result.get("context", context), result


def run_step5(context: Context, user_input: str) -> tuple[Context, dict]:
    """Step 5: 模式选择"""
    from graph.nodes import step5_mode_selection
    state = {"context": context, "user_input": user_input}
    result = step5_mode_selection(state)
    return result.get("context", context), result


def run_step6(context: Context, user_input: str) -> tuple[Context, dict]:
    """Step 6: 策略生成"""
    from graph.nodes import step6_strategy_generation
    state = {"context": context, "user_input": user_input}
    result = step6_strategy_generation(state)
    return result.get("context", context), result


def run_step7(context: Context, user_input: str) -> tuple[Context, dict]:
    """Step 7: 武器选择"""
    from graph.nodes import step7_weapon_selection
    state = {"context": context, "user_input": user_input}
    result = step7_weapon_selection(state)
    return result.get("context", context), result


def run_step9(context: Context, user_input: str, output: str) -> Context:
    """Step 9: 反馈（在流式输出完成后调用）"""
    from graph.nodes import step9_feedback
    state = {"context": context, "user_input": user_input, "output": output}
    result = step9_feedback(state)
    return result.get("context", context)


def _record_step_timing(step_timings: dict[str, float], step_name: str, started_at: float) -> None:
    step_timings[step_name] = round(time.perf_counter() - started_at, 3)


def _reset_runtime_trace(context: Context) -> dict:
    """每轮都重新初始化一份运行轨迹，避免串轮污染。"""
    from graph.nodes.step0_input import _init_runtime_trace, _set_runtime_field

    trace = _init_runtime_trace(context)
    trace.update(
        {
            "turn_load_level": getattr(context, "turn_load_level", "standard"),
            "next_step_policy": getattr(context, "next_step_policy", "soft"),
            "llm_call_count": 0,
            "memory_mode": "minimal",
            "memory_read_count": 0,
            "memory_write_count": 0,
            "skill_loaded_count": 0,
            "prompt_blocks": [],
            "prompt_chars_estimate": 0,
            "step8_mode": "full",
            "step9_mode": "full",
            "unified_context_loaded": False,
            "route_state": {},
            "route_state_alignment": {},
            "policy_state": {},
            "policy_state_prefer": {"none": False, "soft": False, "explicit": False},
            "policy_state_alignment": {},
            "policy_state_observed_alignment": False,
            "policy_state_actual_takeover": False,
            "policy_state_takeover_type": "none",
            "policy_state_metric_reason": [],
            "policy_state_used_for_expected_policy": False,
            "policy_state_expected_policy_reason": [],
            "policy_state_fields_used": [],
            "policy_patch_migration_used": False,
            "policy_patch_migration_fields": [],
            "policy_patch_migration_reason": [],
            "load_decision_source": "legacy_fallback",
            "legacy_turn_load_level": "standard",
            "route_state_expected_load": "standard",
            "route_state_used_for_load": False,
            "route_state_load_reason": [],
            "policy_decision_source": "legacy_fallback",
            "legacy_next_step_policy": "soft",
            "route_state_expected_policy": "soft",
            "route_state_used_for_policy": False,
            "route_state_policy_reason": [],
            "crisis_continuation_source": "none",
            "latency_ms": {},
            "llm_call_detail": [],
            "llm_call_success_count": 0,
            "llm_call_fail_count": 0,
            "llm_fallback_count": 0,
            "llm_provider": "unknown",
            "llm_model": "",
            "llm_endpoint_configured": False,
            "llm_error_type": [],
            "llm_error_stage": [],
            "llm_retry_count": 0,
            "llm_fast_path_disabled": False,
            "llm_normal_path_used": False,
            "memory_continuity_constraint_used": False,
            "memory_continuity_constraint_type": "none",
            "memory_continuity_constraint_position": "none",
            "memory_focus_reflected_in_first_paragraph": "unknown",
            "memory_focus_generic_opening_detected": False,
            "memory_focus_quality_score": 0,
            "memory_focus_has_decision_bias": False,
            "memory_focus_has_must_use_points": False,
            "memory_focus_disabled_reason": [],
            "memory_focus_source_fields": [],
            "session_note_quality_score": 0,
            "next_pickup_quality_score": 0,
            "world_state_quality_score": 0,
            "focus_source_quality": {},
        "focus_material_has_decision_point": False,
        "focus_material_has_recommended_bias": False,
        "focus_material_too_generic": False,
        "memory_material_has_recommended_answer": False,
        "memory_material_has_risk_if_wrong": False,
        "memory_material_has_next_action": False,
        "next_pickup_first_sentence_ready": False,
        "world_state_decision_card_ready": False,
            "output_path": "fallback",
        }
    )
    _set_runtime_field(context, "runtime_trace", trace)
    return trace


def _finalize_runtime_trace(context: Context, step_timings: dict[str, float]) -> dict:
    """把本轮的步耗时压成一份短 trace，并只输出一次。"""
    from graph.nodes.step0_input import _build_route_state_alignment

    trace = getattr(context, "runtime_trace", None)
    if not isinstance(trace, dict):
        trace = _reset_runtime_trace(context)

    latency_ms = {
        "step0_input": step_timings.get("step0_input", 0),
        "step1_identify": step_timings.get("step1_identify", 0),
        "step8_execution": step_timings.get("step8_output", 0),
        "step9_feedback": step_timings.get("step9_feedback", 0),
        "total": round(sum(step_timings.values()), 3),
    }
    trace["turn_load_level"] = getattr(context, "turn_load_level", trace.get("turn_load_level", "standard"))
    trace["next_step_policy"] = getattr(context, "next_step_policy", trace.get("next_step_policy", "soft"))
    trace["latency_ms"] = latency_ms
    route_state = trace.get("route_state")
    if not isinstance(route_state, dict):
        route_state = getattr(context, "route_state", None)
        if isinstance(route_state, dict):
            trace["route_state"] = route_state
    if isinstance(route_state, dict):
        current_outputs = route_state.setdefault("current_outputs", {})
        current_outputs["turn_load_level"] = trace.get("turn_load_level", current_outputs.get("turn_load_level", "standard"))
        current_outputs["next_step_policy"] = trace.get("next_step_policy", current_outputs.get("next_step_policy", "soft"))
        current_outputs["step8_mode"] = trace.get("step8_mode", current_outputs.get("step8_mode", "pending"))
        current_outputs["step9_mode"] = trace.get("step9_mode", current_outputs.get("step9_mode", "pending"))
        route_state["alignment"] = _build_route_state_alignment(route_state)
        trace["route_state_alignment"] = route_state.get("alignment", {})
        trace["route_state_confidence"] = route_state.get("confidence", trace.get("route_state_confidence", 0.0))
        trace["route_state_intent"] = route_state.get("input_intent", trace.get("route_state_intent", "unknown"))
        trace["route_state_phase"] = route_state.get("conversation_phase", trace.get("route_state_phase", "new"))
        trace["route_state_scene"] = route_state.get("main_scene", trace.get("route_state_scene", "general"))
        trace["route_state_secondary_scene"] = route_state.get("secondary_scene", trace.get("route_state_secondary_scene", []))
        try:
            setattr(context, "route_state", route_state)
        except Exception:
            pass
    load_meta = getattr(context, "_route_state_load_meta", None)
    if isinstance(load_meta, dict):
        trace["load_decision_source"] = load_meta.get("load_decision_source", trace.get("load_decision_source", "legacy_fallback"))
        trace["legacy_turn_load_level"] = load_meta.get("legacy_turn_load_level", trace.get("legacy_turn_load_level", trace.get("turn_load_level", "standard")))
        trace["route_state_expected_load"] = load_meta.get("route_state_expected_load", trace.get("route_state_expected_load", trace.get("turn_load_level", "standard")))
        trace["route_state_used_for_load"] = load_meta.get("route_state_used_for_load", trace.get("route_state_used_for_load", False))
        trace["route_state_load_reason"] = load_meta.get("route_state_load_reason", trace.get("route_state_load_reason", []))
    policy_meta = getattr(context, "_route_state_policy_meta", None)
    if isinstance(policy_meta, dict):
        trace["policy_decision_source"] = policy_meta.get("policy_decision_source", trace.get("policy_decision_source", "legacy_fallback"))
        trace["legacy_next_step_policy"] = policy_meta.get("legacy_next_step_policy", trace.get("legacy_next_step_policy", trace.get("next_step_policy", "soft")))
        trace["route_state_expected_policy"] = policy_meta.get("route_state_expected_policy", trace.get("route_state_expected_policy", trace.get("next_step_policy", "soft")))
        trace["route_state_used_for_policy"] = policy_meta.get("route_state_used_for_policy", trace.get("route_state_used_for_policy", False))
        trace["route_state_policy_reason"] = policy_meta.get("route_state_policy_reason", trace.get("route_state_policy_reason", []))
        trace["policy_state_observed_alignment"] = policy_meta.get("policy_state_observed_alignment", trace.get("policy_state_observed_alignment", False))
        trace["policy_state_actual_takeover"] = policy_meta.get("policy_state_actual_takeover", trace.get("policy_state_actual_takeover", False))
        trace["policy_state_takeover_type"] = policy_meta.get("policy_state_takeover_type", trace.get("policy_state_takeover_type", "none"))
        trace["policy_state_metric_reason"] = policy_meta.get("policy_state_metric_reason", trace.get("policy_state_metric_reason", []))
        trace["policy_state_used_for_expected_policy"] = policy_meta.get("policy_state_used_for_expected_policy", trace.get("policy_state_used_for_expected_policy", False))
        trace["policy_state_expected_policy_reason"] = policy_meta.get("policy_state_expected_policy_reason", trace.get("policy_state_expected_policy_reason", []))
        trace["policy_state_fields_used"] = policy_meta.get("policy_state_fields_used", trace.get("policy_state_fields_used", []))
        trace["policy_patch_migration_used"] = policy_meta.get("policy_patch_migration_used", trace.get("policy_patch_migration_used", False))
        trace["policy_patch_migration_fields"] = policy_meta.get("policy_patch_migration_fields", trace.get("policy_patch_migration_fields", []))
        trace["policy_patch_migration_reason"] = policy_meta.get("policy_patch_migration_reason", trace.get("policy_patch_migration_reason", []))
        trace["crisis_continuation_source"] = policy_meta.get("crisis_continuation_source", trace.get("crisis_continuation_source", "none"))
    info(
        "执行耗时",
        load=trace["turn_load_level"],
        next_step=trace["next_step_policy"],
        steps=latency_ms,
        total=latency_ms["total"],
    )
    return trace


def execute_streaming_response(
    context: Context,
    user_input: str,
    on_token: Callable[[str], None] | None = None,
) -> tuple[Context, str, dict[str, float]]:
    """
    在内部完整执行流式链路，但只返回最终修正后的成品输出。

    设计意图：
    - 内部仍然走 Step0~Step9 的完整逻辑
    - 不把模式/策略/武器/中间草稿 token 暴露给外部
    - 对外只展示最终经过后处理的人话版本
    """
    state: dict = {}
    step_timings: dict[str, float] = {}
    _reset_runtime_trace(context)

    started_at = time.perf_counter()
    context, state = run_step0(user_input, context)
    _record_step_timing(step_timings, "step0_input", started_at)
    if state.get("skip_to_end"):
        final_output = context.output or "好的。"
        context.output = final_output
        _finalize_runtime_trace(context, step_timings)
        return context, final_output, step_timings

    started_at = time.perf_counter()
    context, state = run_step1(context, user_input)
    _record_step_timing(step_timings, "step1_identify", started_at)
    if state.get("skip_to_end"):
        final_output = context.output or "能再说详细一点吗？"
        context.output = final_output
        _finalize_runtime_trace(context, step_timings)
        return context, final_output, step_timings

    started_at = time.perf_counter()
    context, state = run_step1_5(context, user_input)
    _record_step_timing(step_timings, "step1_5_meta", started_at)

    started_at = time.perf_counter()
    context, state = run_step1_7(context, user_input)
    _record_step_timing(step_timings, "step1_7_task", started_at)

    started_at = time.perf_counter()
    context, state = run_step2(context, user_input)
    _record_step_timing(step_timings, "step2_goal", started_at)

    started_at = time.perf_counter()
    context, state = run_step3(context, user_input)
    _record_step_timing(step_timings, "step3_self_check", started_at)
    if state.get("skip_to_end"):
        final_output = context.output or ""
        started_at = time.perf_counter()
        context = run_step9(context, user_input, final_output)
        _record_step_timing(step_timings, "step9_feedback", started_at)
        context.output = final_output
        _finalize_runtime_trace(context, step_timings)
        return context, final_output, step_timings

    started_at = time.perf_counter()
    context, state = run_step4(context, user_input)
    _record_step_timing(step_timings, "step4_priority", started_at)

    started_at = time.perf_counter()
    context, state = run_step5(context, user_input)
    _record_step_timing(step_timings, "step5_mode", started_at)

    started_at = time.perf_counter()
    context, state = run_step6(context, user_input)
    _record_step_timing(step_timings, "step6_strategy", started_at)

    started_at = time.perf_counter()
    context, state = run_step7(context, user_input)
    _record_step_timing(step_timings, "step7_weapon", started_at)

    raw_output_parts: list[str] = []
    started_at = time.perf_counter()
    for token in stream_step8(context, user_input, state):
        raw_output_parts.append(token)
        if on_token:
            on_token(token)
    _record_step_timing(step_timings, "step8_output", started_at)

    raw_output = "".join(raw_output_parts)
    final_output = context.output or raw_output
    started_at = time.perf_counter()
    context = run_step9(context, user_input, final_output)
    _record_step_timing(step_timings, "step9_feedback", started_at)
    context.output = final_output
    _finalize_runtime_trace(context, step_timings)
    return context, final_output, step_timings


def stream_step8(
    context: Context,
    user_input: str,
    state: dict,
) -> Generator[str, None, None]:
    """
    Step 8: 流式话术生成

    内部先逐 token 生成草稿，再在结束后做后处理。

    这层 token 流是内部执行细节，不等于对外直接展示这些原始 token。
    """
    from prompts.speech_generator import generate_speech_fast, generate_speech_stream
    from modules.L5.evidence_injector import detect_objection_type, generate_evidence
    from modules.memory import get_memory_manager
    from modules.L4.conversion_rules import convert_to_output
    from graph.nodes.helpers import _fallback_generate_speech
    from graph.nodes.step8_execution import (
        _apply_next_step_policy_gate,
        _classify_closing_type,
        _ensure_explicit_action_first,
        _finalize_closing_trace,
        _resolve_next_step_policy,
        _resolve_step8_mode,
        _run_step8_minimal_execution,
    )

    # 获取策略和武器
    strategy_plan = state.get("strategy_plan")
    weapons_used = state.get("weapons_used", [])
    priority = state.get("priority", {})
    
    # 构建 layers（从 strategy_plan 和 weapons_used）
    layers = []
    if weapons_used:
        for i, w in enumerate(weapons_used):
            weapon_name = w.get("name", "") if isinstance(w, dict) else str(w)
            layers.append({
                "layer": i + 1,
                "weapon": weapon_name,
                "logic": w.get("logic", "") if isinstance(w, dict) else "",
            })
    
    if not layers:
        layers = [{"layer": 1, "weapon": "共情", "logic": ""}]

    # 风格参数
    input_type = context.user.input_type
    emotion_intensity = context.user.emotion.intensity
    style_params = _adapt_output_style(input_type, emotion_intensity)

    # forced_weapon_type
    forced_weapon_type = priority.get("forced_weapon_type")
    user_emotion = context.user.emotion.type.value if hasattr(context.user.emotion.type, 'value') else str(context.user.emotion.type)
    if user_emotion in ["愤怒", "急躁"] or context.user.desires.pride > 0.5:
        forced_weapon_type = "defensive"

    # 证据注入（仅销售场景）
    evidence_content = ""
    scene_id = context.scene_config.scene_id if context.scene_config else ""
    if scene_id == "sales":
        objection_type = detect_objection_type(user_input)
        evidence_content = generate_evidence(objection_type)

    # 统一上下文
    memory_context = get_memory_manager().get_unified_context(
        user_id=context.session_id,
        current_input=user_input,
        context=context,
    )
    if not memory_context:
        memory_context = context.long_term_memory
        if context.session_notes_context:
            memory_context = memory_context + "\n" + context.session_notes_context if memory_context else context.session_notes_context
    context.unified_context = memory_context or context.unified_context

    # 策略字典
    strategy_dict = {}
    if strategy_plan:
        strategy_dict = {
            "combo_name": getattr(strategy_plan, 'combo_name', ''),
            "description": getattr(strategy_plan, 'description', ''),
        }

    # 用户状态
    user_state = {
        "emotion": user_emotion,
        "emotion_type": user_emotion,
        "emotion_intensity": emotion_intensity,
        "trust_level": context.user.trust_level.value if hasattr(context.user.trust_level, 'value') else str(context.user.trust_level),
        "relationship_position": getattr(context.user, "relationship_position", ""),
    }

    # 【叙事驱动话术引擎】动态计算叙事约束
    narrative_rules = ""
    scene = context.primary_scene or (context.scene_config.scene_id if context.scene_config else "")
    intensity = context.user.emotion.intensity
    trust = context.user.trust_level.value if hasattr(context.user.trust_level, 'value') else str(context.user.trust_level)

    trace = getattr(context, "runtime_trace", None)
    if not isinstance(trace, dict):
        trace = state.get("runtime_trace", {}) if isinstance(state, dict) else {}
    if not isinstance(trace, dict):
        trace = {}
    turn_load_level = str(trace.get("turn_load_level") or getattr(context, "turn_load_level", "standard") or "standard").strip().lower()
    next_step_policy = _resolve_next_step_policy(state, context)
    step8_mode = _resolve_step8_mode(state, context)
    if step8_mode in {"minimal", "crisis"}:
        minimal_result = _run_step8_minimal_execution(state, step8_mode=step8_mode)
        final_output = minimal_result.get("output", "") or ""
        for token in _chunk_text(final_output):
            yield token
        context = minimal_result.get("context", context)
        context.output = final_output
        context.output_layers = minimal_result.get("output_layers", {})
        return

    if scene == "emotion":
        if intensity > 0.6 or trust == "low":
            narrative_rules = "【叙事约束】用户情绪脆弱。仅允许使用'精准共鸣+复述痛点'。绝对禁止使用反差、悬念、说教或一次性给建议。结尾必须用开放式提问引导倾诉。"
        else:
            narrative_rules = "【叙事约束】用户情绪平稳。允许使用'开放式提问+温和悬念'引导对话。禁止强反差和制造焦虑。"
    elif scene in ["sales", "negotiation"]:
        narrative_rules = "【叙事约束】允许使用'痛点共鸣+反差开场+悬念引导'。禁止过度共情和软弱妥协。开场必须直击痛点或反常识，结尾必须留钩子（开放式问题或行动暗示）。"
    elif scene == "management":
        narrative_rules = "【叙事约束】保持专业、直接。允许结构化悬念和认知反差。禁止情绪化表达和戏剧化反转。"

    # 内部流式生成草稿，供后续收口处理使用
    raw_output = ""
    raw_output_parts: list[str] = []
    skill_prompt = getattr(context, 'skill_prompt', '')
    guidance_prompt = context.guidance_prompt if getattr(context, "guidance_needed", False) else ""
    dialogue_frame = getattr(context, "dialogue_frame", None)
    frame_contract = getattr(dialogue_frame, "answer_contract", "") if dialogue_frame else ""
    if frame_contract:
        frame_hint = (
            "【对话框架】\n"
            f"当前议题：{getattr(dialogue_frame, 'active_topic', '')}\n"
            f"用户动作：{getattr(dialogue_frame, 'user_act', '')}\n"
            f"本轮契约：{frame_contract}\n"
            "要求：优先履行本轮契约，不要因为场景标签或模板把议题改写。"
        )
        guidance_prompt = f"{guidance_prompt}\n\n{frame_hint}".strip()
    strategy_skeleton_hint = _build_strategy_skeleton_hint(context)
    speech_kwargs = dict(
        layers=layers,
        user_state=user_state,
        strategy_plan=strategy_dict,
        weapons_used=weapons_used,
        memory_context=memory_context,
        knowledge_content=(
            f"{strategy_skeleton_hint}\n\n{strategy_plan.description}".strip()
            if strategy_plan and strategy_skeleton_hint
            else (strategy_plan.description if strategy_plan else strategy_skeleton_hint)
        ),
        style_params=style_params,
        user_input=user_input,
        forced_weapon_type=forced_weapon_type,
        evidence_content=evidence_content,
        skill_prompt=skill_prompt,
        secondary_scene_strategy=context.secondary_scene_strategy if hasattr(context, 'secondary_scene_strategy') and context.secondary_scene_strategy else "",
        narrative_rules=narrative_rules,
        guidance_prompt=guidance_prompt,
        next_step_policy=next_step_policy,
    )

    use_fast_path = _should_use_fast_speech(
        user_input=user_input,
        scene=scene,
        emotion_intensity=emotion_intensity,
        memory_context=memory_context,
        evidence_content=evidence_content,
        guidance_prompt=guidance_prompt,
    )
    bypass_llm = _should_bypass_stream_llm(context, user_input, scene)

    runtime_trace = trace if isinstance(trace, dict) else {}
    runtime_trace["step8_mode"] = "full"
    runtime_trace["prompt_blocks"] = [
        "user_input",
        "layers",
        "user_state",
        "strategy_plan",
        "weapons",
        "memory_context",
        "knowledge_content",
        "skill_prompt",
        "secondary_scene_strategy",
        "narrative_rules",
        "guidance_prompt",
        "postprocess",
    ]
    runtime_trace["prompt_chars_estimate"] = 1800 + sum(
        len(part or "")
        for part in [
            user_input,
            memory_context,
            speech_kwargs.get("knowledge_content", ""),
            skill_prompt,
            speech_kwargs.get("secondary_scene_strategy", ""),
            narrative_rules,
            guidance_prompt,
            scene,
            getattr(context, "identity_hint", ""),
            getattr(context, "situation_hint", ""),
            getattr(context, "dialogue_task", "clarify"),
        ]
    ) + len(layers) * 120 + len(weapons_used) * 30
    from graph.nodes.step0_input import _set_runtime_field

    _set_runtime_field(context, "runtime_trace", runtime_trace)
    if isinstance(state, dict):
        state["runtime_trace"] = runtime_trace

    if bypass_llm:
        raw_output = _fallback_generate_speech(
            layers,
            user_input,
            weapons_used,
            context=context,
        )
        runtime_trace["output_path"] = "fallback"
        for token in _chunk_text(raw_output):
            yield token
    elif use_fast_path:
        raw_output = generate_speech_fast(
            identity_hint=getattr(context, "identity_hint", ""),
            situation_hint=getattr(context, "situation_hint", ""),
            dialogue_task=getattr(context, "dialogue_task", "clarify"),
            scene=scene,
            runtime_trace=runtime_trace,
            llm_stage="step8_minimal" if _is_light_turn(context, user_input, scene) else "step8_full_fast",
            **speech_kwargs,
        )
        for token in _chunk_text(raw_output):
            yield token
    else:
        for token in generate_speech_stream(
            identity_hint=getattr(context, "identity_hint", ""),
            situation_hint=getattr(context, "situation_hint", ""),
            dialogue_task=getattr(context, "dialogue_task", "clarify"),
            scene=scene,
            runtime_trace=runtime_trace,
            llm_stage="step8_stream",
            **speech_kwargs,
        ):
            raw_output_parts.append(token)
            # 这里是内部 token 流，外层接口不会直接把这份草稿吐给用户
            yield token

        raw_output = "".join(raw_output_parts)

    # 后处理：转换规则 + 术语替换 + 防御模式过滤
    # 注意：后处理在流式完成后执行，用于更新 context 和记录
    final_output, passed = convert_to_output(raw_output)
    final_output = _replace_academic_terms(final_output)

    # 防御模式质量门控
    if forced_weapon_type == "defensive":
        final_output = _apply_defensive_filter(final_output)

    # 与主链路保持一致：流式完成后仍执行人设与质量校验
    from graph.nodes.persona_checker import _check_persona_consistency, _rewrite_for_persona
    from modules.L4.field_quality import quality_check

    persona_ok, reason = _check_persona_consistency(final_output, context)
    if not persona_ok:
        final_output = _rewrite_for_persona(final_output, reason)

    final_output = _ensure_explicit_action_first(final_output, scene, next_step_policy)
    final_output, final_closing_type, closing_blocks_removed, closing_dedup_applied = _apply_next_step_policy_gate(
        final_output,
        next_step_policy,
        scene,
    )
    if next_step_policy == "explicit":
        final_output = _ensure_explicit_action_first(final_output, scene, next_step_policy)
        final_closing_type = _classify_closing_type(final_output)

    quality_check(final_output, context)

    # 更新 context
    context.output = final_output
    runtime_trace.setdefault("output_path", "llm")
    _finalize_closing_trace(
        state,
        context,
        step8_mode="full",
        next_step_policy=next_step_policy,
        final_closing_type=final_closing_type if final_output else "none",
        closing_blocks_removed=closing_blocks_removed,
        closing_dedup_applied=closing_dedup_applied,
    )
    from types import SimpleNamespace
    output_layers = {
        "user_visible": final_output,
        "debug_info": f"模式={context.response_mode} | 武器={[w['name'] for w in weapons_used]} | 场景={scene}",
        "internal": f"策略={getattr(strategy_plan, 'combo_name', '') if strategy_plan else ''} | 提示={getattr(strategy_plan, 'description', '') if strategy_plan else ''}",
        "order_source": "stream",
        "failure_avoid_codes": [],
        "memory_hint_signals": _build_memory_hint_signals(
            SimpleNamespace(description=(strategy_plan.get("description", "") if isinstance(strategy_plan, dict) else ""))
        ),
    }
    context.output_layers = output_layers
    for w in weapons_used:
        context.increment_weapon(w["name"] if isinstance(w, dict) else str(w))


def _apply_defensive_filter(text: str) -> str:
    """防御模式质量过滤：替换紧迫感/销售词汇"""
    replacements = {
        "机会": "可能性",
        "错过": "没赶上",
        "抓紧": "尽快",
        "翻倍": "提升",
        "赚": "获得",
        "稀缺": "有限",
        "最后": "剩下",
        "限时": "时间",
        "紧迫": "重要",
        "窗口期": "阶段",
    }
    for word, replacement in replacements.items():
        text = text.replace(word, replacement)
    return text
