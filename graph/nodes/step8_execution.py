"""
Human-OS Engine - LangGraph 节点实现

对应总控规格的 Step 0-9。
"""

import hashlib
import difflib
import re

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import time

from graph.state import GraphState
from utils.logger import info
from utils.logger import warning
from graph.nodes.style_adapter import (
    _adapt_output_style,
    _build_narrative_profile,
    _build_output_profile,
    _is_scene_output_concrete_enough,
    _replace_academic_terms,
    _shape_output_rhythm,
    _soften_internal_scaffolding,
    _smart_compress,
    _trim_to_output_profile,
)
from graph.nodes.persona_checker import (
    _check_persona_consistency,
    _rewrite_for_persona,
)
from graph.nodes.helpers import (
    _generate_upgrade_speech,
    _fallback_generate_speech,
    _is_light_turn,
    _turn_behavior_profile,
    _should_take_task_first_fallback,
)
from graph.nodes.step0_input import (
    _estimate_text_chars,
    _record_memory_prompt_blocks,
    _record_memory_read_trace,
    _set_memory_gate_decision,
)


def _ensure_final_visible_output(final_output: str, user_input: str) -> str:
    """兜底保证：用户最终看到的一定是一句能见人的话。"""
    cleaned = (final_output or "").strip()
    if cleaned:
        return cleaned

    fallback = _fallback_generate_speech(
        layers=[{"layer": 1, "weapon": "共情"}, {"layer": 5, "weapon": "选择权引导"}],
        user_input=user_input,
        weapons_used=[],
        context=None,
    )
    return fallback.strip() or "我先说重点：我们先抓住一个最关键的问题。"


def _should_preserve_final_output(context, user_input: str, final_output: str) -> bool:
    """如果输出已经够具体，就少做二次改写。"""
    scene = context.primary_scene or (context.scene_config.scene_id if context.scene_config else "")
    if not scene:
        return False
    if getattr(context, "short_utterance", False):
        return False
    if getattr(context, "guidance_needed", False):
        return False
    if not final_output or len(final_output.strip()) < 24:
        return False
    return _is_scene_output_concrete_enough(final_output, scene)


def _should_minimize_post_processing(context, user_input: str) -> bool:
    """中档或更轻的轮次，尽量别做太多后处理。"""
    scene = context.primary_scene or (context.scene_config.scene_id if context.scene_config else "")
    return _turn_behavior_profile(context, user_input, scene)["minimize_post_processing"]


def _should_apply_soft_repair(context, user_input: str, final_output: str) -> bool:
    """只在输出还明显偏空、偏短、偏虚的时候做轻修。"""
    text = (final_output or "").strip()
    if not text:
        return False

    scene = context.primary_scene or (context.scene_config.scene_id if context.scene_config else "")
    profile = _turn_behavior_profile(context, user_input, scene)
    if profile["level"] == "light":
        return False

    if getattr(context, "guidance_needed", False):
        return True

    if len(text) < 18:
        return True

    if scene in {"emotion", "management"} and len(text) < 28:
        return True

    return False


def _should_use_fast_speech_generation(context) -> bool:
    """普通轮次优先走快模型，深度轮次再保留重生成。"""
    session_id = str(getattr(context, "session_id", "") or "")
    if session_id.startswith("sandbox-mt-"):
        return True
    return getattr(context, "response_mode", "ordinary") != "deep"


def _build_light_memory_context(context) -> str:
    """
    普通模式下只带轻量上下文，避免每轮都去拉重记忆。
    """
    parts: list[str] = []
    unified = (getattr(context, "unified_context", "") or "").strip()
    if unified:
        parts.append(unified[:500])

    notes = (getattr(context, "session_notes_context", "") or "").strip()
    if notes and notes not in unified:
        parts.append(notes[:300])

    long_term = (getattr(context, "long_term_memory", "") or "").strip()
    if not parts and long_term:
        parts.append(long_term[:300])

    return "\n".join(part for part in parts if part).strip()


def _resolve_memory_continuity_focus(state, context) -> dict:
    focus = state.get("memory_continuity_focus")
    if not isinstance(focus, dict):
        focus = getattr(context, "memory_continuity_focus", None)
    if not isinstance(focus, dict):
        focus = {}
    return focus


def _should_use_memory_continuity_focus(step8_mode: str, context, focus: dict) -> bool:
    if not isinstance(focus, dict):
        return False
    if not focus.get("memory_use_required"):
        return False
    focus_type = str(focus.get("focus_type", "") or "")
    if not focus_type or focus_type == "none":
        return False
    if step8_mode in {"crisis", "minimal"}:
        return focus_type in {"crisis_recovery", "preference", "followup"} or bool(focus.get("next_pickup"))
    route_state = getattr(context, "route_state", None) or {}
    if not isinstance(route_state, dict):
        route_state = {}
    conversation_phase = str(route_state.get("conversation_phase", "") or "")
    if conversation_phase in {"followup", "revision", "continuation", "crisis_recovery", "crisis_continuation"}:
        return True
    return focus_type in {"preference", "project_state", "sales_context", "negotiation_context", "management_relation", "crisis_recovery"}


def _estimate_continuity_focus_chars(focus: dict) -> int:
    if not isinstance(focus, dict):
        return 0
    compact = {
        "focus_type": focus.get("focus_type", ""),
        "anchor": focus.get("anchor", ""),
        "decision_bias": focus.get("decision_bias", ""),
        "must_use_points": focus.get("must_use_points", []),
        "avoid": focus.get("avoid", []),
        "next_pickup": focus.get("next_pickup", ""),
        "world_state_hint": focus.get("world_state_hint", ""),
        "relationship_hint": focus.get("relationship_hint", ""),
        "output_instruction": focus.get("output_instruction", ""),
    }
    return _estimate_text_chars(compact)


def _fallback_memory_focus_reason(focus: dict) -> str:
    focus_type = str((focus or {}).get("focus_type", "") or "none")
    mapping = {
        "preference": "memory_use:fallback_preference_first_sentence",
        "project_state": "memory_use:fallback_project_state_first_sentence",
        "sales_context": "memory_use:fallback_sales_context_first_sentence",
        "negotiation_context": "memory_use:fallback_negotiation_context_first_sentence",
        "management_relation": "memory_use:fallback_management_relation_first_sentence",
        "crisis_recovery": "memory_use:fallback_crisis_recovery_first_sentence",
    }
    return mapping.get(focus_type, "memory_use:fallback_generic_preserved_no_focus")


def _looks_like_stream_default_fallback(text: str) -> bool:
    lowered = str(text or "").strip()
    if not lowered:
        return False
    markers = [
        "[流式生成失败，使用默认回复]",
        "可以先这样做：先给一个默认动作。",
    ]
    return any(marker in lowered for marker in markers)


def _observe_memory_focus_usage(final_output: str, focus: dict) -> tuple[str, list[str]]:
    if not isinstance(focus, dict) or not focus.get("memory_use_required"):
        return "no", ["memory_use:no_relevant_memory"]

    text = str(final_output or "").strip()
    if not text:
        return "unknown", ["memory_use:memory_loaded_but_not_applied"]

    focus_type = str(focus.get("focus_type", "") or "none")
    reasons: list[str] = []
    lower_hit = False
    anchor = str(focus.get("anchor", "") or "")
    world_state_hint = str(focus.get("world_state_hint", "") or "")
    next_pickup = str(focus.get("next_pickup", "") or "")
    relationship_hint = str(focus.get("relationship_hint", "") or "")

    for signal in [anchor, world_state_hint, next_pickup, relationship_hint]:
        signal = str(signal or "").strip()
        if signal and signal[:8] in text:
            lower_hit = True
            break

    if focus_type == "preference":
        if len(text) <= 120 and "先" in text and any(marker in text for marker in ["可以", "先做", "先回", "先说"]):
            reasons.append("memory_use:preference_style_applied")
            return "yes", reasons
        return "unknown", ["memory_use:memory_loaded_but_not_applied"]

    mapping = {
        "project_state": ("memory_use:project_state_applied", ["这周", "压价", "守价格", "让步", "收口"]),
        "sales_context": ("memory_use:sales_context_applied", ["太贵", "再考虑", "竞品", "压价", "守价格"]),
        "negotiation_context": ("memory_use:negotiation_context_applied", ["条件", "边界", "账期", "让步", "竞品"]),
        "management_relation": ("memory_use:management_relation_applied", ["关系", "压力", "先问", "别太重", "执行力", "拖"]),
        "crisis_recovery": ("memory_use:crisis_recovery_applied", ["安全", "先缓", "慢一点", "不用急", "稳住"]),
        "followup": ("memory_use:followup_applied", ["继续", "接着", "先这样", "下一步"]),
    }
    reason, markers = mapping.get(focus_type, ("memory_use:memory_loaded_but_not_applied", []))
    if lower_hit or any(marker in text for marker in markers):
        return "yes", [reason]
    return "unknown", ["memory_use:memory_loaded_but_not_applied"]


def _first_paragraph(text: str) -> str:
    content = str(text or "").strip()
    if not content:
        return ""
    parts = re.split(r"\n\s*\n|(?<=[。！？!?])", content, maxsplit=1)
    return str(parts[0] or "").strip()


def _detect_generic_opening(text: str) -> bool:
    opening = _first_paragraph(text)
    if not opening:
        return False
    generic_markers = [
        "这个要看具体情况",
        "你可以先想一想",
        "建议你先梳理一下",
        "可以先这样做",
        "我理解你的感受",
        "你可以先补充一下背景",
        "这件事可以分几步",
        "它大概是在说这里提到的这个内容",
    ]
    return any(marker in opening for marker in generic_markers)


def _observe_memory_constraint_effect(final_output: str, focus: dict) -> tuple[str, bool, list[str]]:
    if not isinstance(focus, dict) or not focus.get("memory_use_required"):
        return "unknown", False, ["memory_use:focus_irrelevant_to_current_turn"]

    focus_type = str(focus.get("focus_type", "") or "none")
    opening = _first_paragraph(final_output)
    generic_opening = _detect_generic_opening(opening)
    reasons: list[str] = []

    if not opening:
        return "unknown", generic_opening, ["memory_use:focus_not_reflected_in_first_paragraph"]

    type_mapping = {
        "preference": (
            "memory_use:llm_preference_main_constraint",
            ["结论", "先", "重点", "直接"],
        ),
        "project_state": (
            "memory_use:llm_project_state_main_constraint",
            ["这周", "收口", "压价", "守住价格", "让步"],
        ),
        "sales_context": (
            "memory_use:llm_sales_context_main_constraint",
            ["守价格", "让价", "压价", "竞品", "再考虑", "条件"],
        ),
        "negotiation_context": (
            "memory_use:llm_negotiation_context_main_constraint",
            ["守边界", "条件", "让步", "竞品", "账期"],
        ),
        "management_relation": (
            "memory_use:llm_management_relation_main_constraint",
            ["先问情况", "先问", "收标准", "关系", "压力", "卡点"],
        ),
        "crisis_recovery": (
            "memory_use:llm_crisis_recovery_main_constraint",
            ["刚刚", "缓下来", "还有点怕", "安全", "别谈项目", "先稳住"],
        ),
    }
    reason, markers = type_mapping.get(focus_type, ("memory_use:focus_irrelevant_to_current_turn", []))
    reflected = any(marker in opening for marker in markers)

    if reflected:
        reasons.append(reason)
    else:
        reasons.append("memory_use:focus_not_reflected_in_first_paragraph")

    if generic_opening:
        reasons.append("memory_use:focus_present_but_generic_opening")

    return ("yes" if reflected else "no"), generic_opening, reasons


def _apply_memory_continuity_focus_to_output(output: str, focus: dict, user_input: str, next_step_policy: str) -> str:
    if not isinstance(focus, dict) or not focus.get("memory_use_required"):
        return output

    text = str(output or "").strip()
    if not text:
        return text

    focus_type = str(focus.get("focus_type", "") or "none")
    anchor = str(focus.get("anchor", "") or "").strip()
    next_pickup = str(focus.get("next_pickup", "") or "").strip()
    world_state_hint = str(focus.get("world_state_hint", "") or "").strip()
    relationship_hint = str(focus.get("relationship_hint", "") or "").strip()

    if focus_type == "preference":
        if text.startswith("[流式生成失败") or "可以先这样做：先给一个默认动作。" in text:
            return f"先说结论：{text.replace('[流式生成失败，使用默认回复]', '').strip() or '你先别绕，直接抓最关键的一步。'}"
        return text

    if focus_type == "project_state":
        if anchor and anchor not in text:
            return f"先扣住你现在的重点：{anchor}。{text}"
        return text

    if focus_type in {"sales_context", "negotiation_context"}:
        scene_anchor = anchor or next_pickup or world_state_hint
        if scene_anchor and scene_anchor[:8] not in text:
            return f"顺着你前面这条线看，先别重新开题。现在卡点还是“{scene_anchor}”，所以别急着让步。{text}"
        return text

    if focus_type == "management_relation":
        relation_anchor = relationship_hint or anchor or next_pickup
        if relation_anchor and relation_anchor[:8] not in text:
            return f"这轮先别只看对错，关系和承受度要一起保住。你前面卡住的点还是“{relation_anchor}”。{text}"
        return text

    if focus_type == "crisis_recovery":
        if "安全" not in text and "慢一点" not in text and "不用急" not in text:
            return "你现在最重要的不是马上解决什么，而是先把自己稳住。既然已经从最危险的时候缓下来，这一轮就先放慢一点，只做让你更安心的下一小步。"
        return text

    if focus_type == "followup":
        if next_pickup and next_pickup[:8] not in text and next_step_policy != "none":
            return f"顺着刚才那一步往下接，现在先抓“{next_pickup}”。{text}"
        return text

    return text


def _record_memory_constraint_trace(trace: dict, final_output: str, focus: dict, *, position: str = "none") -> None:
    if not isinstance(trace, dict):
        return
    focus_used = bool(isinstance(focus, dict) and focus.get("memory_use_required") and str(focus.get("focus_type", "") or "") not in {"", "none"})
    focus_type = str((focus or {}).get("focus_type", "none") or "none")
    trace["memory_continuity_constraint_used"] = focus_used
    trace["memory_continuity_constraint_type"] = focus_type if focus_used else "none"
    trace["memory_continuity_constraint_position"] = position if focus_used else "none"
    reflected, generic_opening, reasons = _observe_memory_constraint_effect(final_output, focus if focus_used else {})
    trace["memory_focus_reflected_in_first_paragraph"] = reflected
    trace["memory_focus_generic_opening_detected"] = bool(generic_opening)
    existing = list(trace.get("memory_used_in_output_reason", []) or [])
    for reason in reasons:
        if reason not in existing:
            existing.append(reason)
    trace["memory_used_in_output_reason"] = existing


def _run_fast_speech_with_timeout(*, timeout_seconds: float, **kwargs) -> str:
    """
    普通模式输出的本地保险丝：快模型一旦卡住，就直接超时降级。
    """
    from prompts.speech_generator import generate_speech_fast

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(generate_speech_fast, **kwargs)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError as exc:
        future.cancel()
        executor.shutdown(wait=False, cancel_futures=True)
        raise TimeoutError(f"fast_speech_timeout>{timeout_seconds}s") from exc
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _should_bypass_llm_for_ordinary_turn(context, user_input: str) -> bool:
    """
    短承接轮直接本地生成，不再调用模型。
    """
    scene = getattr(context, "primary_scene", "") or (context.scene_config.scene_id if context.scene_config else "")
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
    return _is_light_turn(context, user_input, scene)


def _contains_crisis_intent(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    crisis_keywords = [
        "活不下去", "不想活", "想死", "去死", "轻生", "自杀",
        "结束生命", "不如死", "活着没意义", "药都准备", "跳楼", "割腕",
    ]
    return any(kw in text for kw in crisis_keywords)


def _soften_harsh_tone(output: str) -> str:
    """把容易刺人的表达压平一点，避免同一句里出现逼迫感。"""
    text = output or ""
    replacements = {
        "你打算让现在的状况再拖多久": "你更希望什么时候开始推进",
        "你到底是要还是不要": "你更倾向继续推进还是先观察一下",
        "你想清楚到底是要还是不要": "我们先把你的真实顾虑理清，再决定节奏",
        "这两个态度矛盾": "这两种想法有点冲突",
        "只能到此为止": "我们可以先停在这里，等你准备好再继续",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _guard_optional_product_extension_output(output: str, user_input: str, skill_prompt: str) -> str:
    """可选产品扩展的轻量安全网：不让扩展把未知事实编成卖点。"""
    if "【雷军产品扩展禁区】" not in (skill_prompt or ""):
        return output

    text = (output or "").strip()
    source = user_input or ""
    if not text:
        return text

    unsupported_markers = [
        "7x24", "24小时", "专属技术顾问", "专属顾问", "行业里", "行业内",
        "已有", "上百", "原价", "现价", "限量", "限时", "仅剩", "客户案例",
    ]
    has_unsupported_marker = any(marker in text and marker not in source for marker in unsupported_markers)
    if not has_unsupported_marker:
        return output

    return (
        "这件事别先争“贵不贵”，先把价值讲实。可以这样说："
        "价格先放一边，我们先看三件事：你最在意的结果是什么、"
        "我们真实能帮你减少哪类麻烦、这个价值是不是值得长期付费。"
        "如果这三点说不清，就不要硬讲贵；如果说得清，价格就不是单独的一串数字。"
    )


def _is_ack_like_input(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    if len(text) > 22:
        return False
    markers = [
        "嗯", "好的", "好", "继续说", "接着说", "你继续", "听起来不错",
        "我明白了", "继续",
    ]
    return any(m in text for m in markers)


def _is_continue_signal(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    continue_markers = ["继续说", "接着说", "继续讲", "你继续", "听起来不错"]
    return any(m in text for m in continue_markers)


def _is_affirmation_signal(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    affirmation_markers = ["有道理", "确实", "明白了", "我明白", "你说得对", "是这样", "没错"]
    return any(m in text for m in affirmation_markers)


def _is_next_step_signal(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    next_step_markers = [
        "接下来呢",
        "下一步呢",
        "那接下来",
        "下一步怎么走",
        "接下来怎么做",
        "给我一个动作",
        "给我一个本周能落地的动作",
        "本周能落地的动作",
        "给我一个能落地的动作",
        "直接给动作",
        "直接说动作",
        "别讲大道理",
    ]
    return any(m in text for m in next_step_markers)


def _looks_like_emotional_accusation(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    accusation_markers = [
        "你根本就不爱我",
        "你根本不爱我",
        "你是不是不爱我",
        "你是不是不在乎我",
        "你根本不在乎",
        "怎么可能忘了",
        "忘了纪念日",
        "不太相信",
        "像套路",
        "你在敷衍我",
        "我觉得你在敷衍我",
        "被忽视",
        "不被放在心上",
    ]
    return any(m in text for m in accusation_markers)


def _pick_variant(tag: str, context, user_input: str, scene: str, variants: list[str]) -> str:
    """在固定模板池里轮换，减少同一句式反复出现。"""
    if not variants:
        return ""
    session_id = str(getattr(context, "session_id", "") or "")
    history_len = len(getattr(context, "history", []) or [])
    key = f"{tag}|{session_id}|{scene}|{history_len}|{(user_input or '').strip()}"
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return variants[digest[0] % len(variants)]


def _normalize_visible_text(text: str) -> str:
    cleaned = re.sub(r"\s+", "", text or "")
    return re.sub(r"[，。！？；：、“”\"'（）()\-—,.!?;:]", "", cleaned)


def _recent_assistant_texts(context, limit: int = 3) -> list[str]:
    history = list(getattr(context, "history", []) or [])
    texts: list[str] = []
    for message in reversed(history):
        role = getattr(message, "role", None)
        if role not in {"assistant", "ai"}:
            continue
        content = getattr(message, "content", "") or ""
        if isinstance(content, list):
            content = "".join(str(part) for part in content if part)
        text = str(content).strip()
        if not text:
            continue
        texts.append(text)
        if len(texts) >= limit:
            break
    return texts


def _is_too_similar_to_recent_output(output: str, context) -> bool:
    normalized = _normalize_visible_text(output)
    if len(normalized) < 12:
        return False
    for previous in _recent_assistant_texts(context):
        previous_normalized = _normalize_visible_text(previous)
        if len(previous_normalized) < 12:
            continue
        ratio = difflib.SequenceMatcher(None, normalized, previous_normalized).ratio()
        if ratio >= 0.72:
            return True
    return False


def _needs_next_step_rescue(output: str, scene: str, context) -> bool:
    text = (output or "").strip()
    if not text:
        return True
    generic_markers = [
        "你先说说",
        "先谈价格",
        "往下收",
        "往下谈",
        "推进哪一步",
        "继续推进",
    ]
    scene_anchors = {
        "sales": ["结果", "风险", "顾虑", "节奏", "对比"],
        "management": ["小动作", "回看", "负责", "推进", "今天"],
        "negotiation": ["条件", "边界", "区间", "让步", "一致"],
        "emotion": ["最痛", "最难受", "争对错", "输赢"],
    }
    if len(text) < 24:
        return True
    if any(marker in text for marker in generic_markers):
        return True
    if _is_too_similar_to_recent_output(text, context):
        return True
    anchors = scene_anchors.get(scene, [])
    if anchors and not any(anchor in text for anchor in anchors):
        return True
    return False


def _needs_followup_rescue(output: str, scene: str, context) -> bool:
    text = (output or "").strip()
    if not text:
        return True
    pushy_markers = [
        "关键不在我这儿",
        "你到底",
        "再拖多久",
        "先不想",
        "顺着往下谈",
        "什么时候开始推进",
        "继续推进还是先观察一下",
    ]
    if len(text) < 20:
        return True
    if any(marker in text for marker in pushy_markers):
        return True
    scene_anchors = {
        "sales": ["结果", "成本", "节奏", "风险", "对比", "汇报", "30 秒", "10 分钟", "7 天"],
        "management": ["小动作", "回看", "负责人", "今天", "卡的一件事"],
        "negotiation": ["条件", "边界", "区间", "让步", "拍板人", "确认窗口"],
        "emotion": ["最刺痛", "最难受", "不舒服", "先不急着争对错", "身体", "小止损"],
    }
    anchors = scene_anchors.get(scene, [])
    if len(text) >= 30 and anchors and any(anchor in text for anchor in anchors):
        return False
    if _is_too_similar_to_recent_output(text, context):
        return True
    return False


def _needs_emotion_boundary_rescue(output: str, context, anchors: list[str], min_len: int = 28) -> bool:
    text = (output or "").strip()
    if not text:
        return True
    if len(text) < min_len:
        return True
    if anchors and any(anchor in text for anchor in anchors):
        return False
    if _is_too_similar_to_recent_output(text, context):
        return True
    return True


def _needs_sales_boundary_rescue(output: str, context, anchors: list[str], min_len: int = 28) -> bool:
    text = (output or "").strip()
    if not text:
        return True
    if len(text) < min_len:
        return True
    if anchors and any(anchor in text for anchor in anchors):
        return False
    if _is_too_similar_to_recent_output(text, context):
        return True
    return True


def _needs_management_boundary_rescue(output: str, context, anchors: list[str], min_len: int = 28) -> bool:
    text = (output or "").strip()
    if not text:
        return True
    if len(text) < min_len:
        return True
    if anchors and any(anchor in text for anchor in anchors):
        return False
    if _is_too_similar_to_recent_output(text, context):
        return True
    return True


def _needs_management_next_step_rescue(output: str, context) -> bool:
    text = (output or "").strip()
    if not text:
        return True
    if _is_too_similar_to_recent_output(text, context):
        return True
    action_markers = ["负责人", "回看", "今天", "本周", "明天", "20分钟", "20 分钟", "30分钟", "30 分钟", "一小时", "检查点", "同步", "小动作"]
    if any(marker in text for marker in action_markers):
        return False
    if len(text) < 26:
        return True
    if "？" in text or "?" in text:
        return True
    return True


def _needs_negotiation_close_rescue(output: str, context) -> bool:
    text = (output or "").strip()
    if not text:
        return True
    if "可执行的下一步" in text:
        return False
    concrete_markers = [
        "最容易达成一致的点",
        "交换条件",
        "拍板人",
        "确认窗口",
        "条款",
        "区间",
        "让步",
        "交付边界",
    ]
    if len(text) >= 30 and any(marker in text for marker in concrete_markers):
        return False
    if _is_too_similar_to_recent_output(text, context):
        return True
    return True


def _is_scene_output_concrete_enough(output: str, scene: str) -> bool:
    """判断当前成品是不是已经够具体了，够具体就别再被后置修补反复接管。"""
    text = (output or "").strip()
    if not text:
        return False

    scene_anchors = {
        "sales": ["结果", "成本", "节奏", "风险", "对比", "30 秒", "10 分钟", "7 天", "最担心点", "明天"],
        "management": ["小动作", "回看", "负责人", "今天", "本周", "每天", "20 分钟", "30 分钟", "一小时", "卡的一件事", "最占你精力"],
        "negotiation": ["条件", "边界", "区间", "让步", "拍板人", "确认窗口", "交付边界", "最容易谈拢"],
        "emotion": ["最刺痛", "最难受", "不舒服", "先不急着争对错", "身体", "小止损", "没被认真看见"],
    }
    anchors = scene_anchors.get(scene, [])
    if scene == "management" and "负责人" in text and "回看" in text:
        return True
    if scene == "management" and "本周" in text and any(marker in text for marker in ["每天", "20 分钟", "30 分钟", "一小时", "三个明确"]):
        return True
    if scene == "negotiation" and "可执行的下一步" in text:
        return True
    if scene == "emotion" and "最刺痛" in text and any(marker in text for marker in ["不舒服", "最难受", "先不急着争对错"]):
        return True
    if len(text) < 28:
        return False
    hit_count = sum(1 for anchor in anchors if anchor in text)
    return hit_count >= 2


def _should_skip_scene_specific_repair(output: str, scene: str, context) -> bool:
    """给后置场景修补加一个总闸门：输出已经够具体，就别再层层接管。"""
    text = (output or "").strip()
    if not text:
        return False
    if _is_too_similar_to_recent_output(text, context):
        return False
    return _is_scene_output_concrete_enough(text, scene)


def _should_skip_skeleton_order_injection(output: str, user_input: str, scene: str, context) -> bool:
    """给顺序补救再加一道闸：输出已经够具体时，就别再硬补结构壳。"""
    text = (output or "").strip()
    if not text:
        return False
    if not _looks_like_progress_request(user_input):
        return True
    if _has_explicit_order_markers(text):
        return True
    return _is_scene_output_concrete_enough(text, scene) and not _is_too_similar_to_recent_output(text, context)


def _get_management_sub_intent(context, user_input: str, scene: str) -> str:
    intent = (getattr(context, "management_sub_intent", "") or "").strip()
    if intent:
        return intent
    text = (user_input or "").strip()
    if not text:
        return ""
    if any(marker in text for marker in ["ROI", "roi", "回报率", "投入产出", "预算", "财务总监", "CFO"]):
        return "roi_justification"
    if any(marker in text for marker in ["又是新工具", "消停会", "变革", "改革", "学不动了", "倦怠", "消极抵抗", "24/7"]):
        return "change_fatigue"
    if any(marker in text for marker in ["研发", "市场", "跨部门", "甩锅", "移交", "各说各话", "争夺", "冷战"]):
        return "cross_team_alignment"
    if any(marker in text for marker in ["本周", "落地", "动作", "怎么推进", "直接给", "别讲大道理", "先做什么", "下一步"]):
        return "action_request"
    if any(marker in text for marker in ["领导", "CEO", "老板", "拍板", "汇报", "技术债", "转型进度", "不满"]):
        return "upward_report"
    return "diagnose"


def _should_apply_management_route(context, user_input: str, scene: str, target_intent: str = "") -> bool:
    intent = _get_management_sub_intent(context, user_input, scene)
    confidence = float(getattr(context, "management_sub_intent_confidence", 0.0) or 0.0)
    sales_intent = (getattr(context, "sales_sub_intent", "") or "").strip()
    sales_confidence = float(getattr(context, "sales_sub_intent_confidence", 0.0) or 0.0)
    negotiation_intent = (getattr(context, "negotiation_sub_intent", "") or "").strip()
    negotiation_confidence = float(getattr(context, "negotiation_sub_intent_confidence", 0.0) or 0.0)
    if target_intent and intent and intent != target_intent:
        return False
    if scene == "management" and sales_intent and sales_confidence >= 0.8:
        return False
    if scene == "management" and negotiation_intent and negotiation_confidence >= 0.8:
        return False
    if scene == "management":
        return bool(intent or target_intent)
    if scene == "emotion" and intent and confidence >= 0.8:
        return True
    return False


def _get_sales_sub_intent(context, user_input: str, scene: str) -> str:
    intent = (getattr(context, "sales_sub_intent", "") or "").strip()
    if intent:
        return intent
    text = (user_input or "").strip()
    if not text:
        return ""
    if any(marker in text for marker in ["跟老板汇报", "让我等消息", "回去汇报", "等我消息", "我再看看"]):
        return "delay_followup"
    if scene != "sales":
        return ""
    has_price_signal = any(marker in text for marker in ["太贵", "价格高", "贵了", "便宜", "降价"])
    has_competitor_signal = any(marker in text for marker in ["竞品", "同行", "其他家", "别家"])
    if has_price_signal and has_competitor_signal:
        return "price_objection"
    if any(marker in text for marker in ["现在用的系统", "现在系统", "现有系统", "现在这套"]) and any(marker in text for marker in ["为什么要换", "为啥要换", "为什么换", "没必要换"]):
        return "switch_defense"
    if "有道理" in text and any(marker in text for marker in ["确实是这样想", "我确实是这样想", "确实这样想"]):
        return "soft_agreement"
    return "diagnose"


def _should_apply_sales_route(context, user_input: str, scene: str, target_intent: str = "") -> bool:
    intent = _get_sales_sub_intent(context, user_input, scene)
    confidence = float(getattr(context, "sales_sub_intent_confidence", 0.0) or 0.0)
    if target_intent and intent and intent != target_intent:
        return False
    if scene == "sales":
        return bool(intent or target_intent)
    if scene == "management" and intent and confidence >= 0.8:
        return True
    return False


def _get_negotiation_sub_intent(context, user_input: str, scene: str) -> str:
    intent = (getattr(context, "negotiation_sub_intent", "") or "").strip()
    if intent:
        return intent
    if scene != "negotiation":
        return ""
    text = (user_input or "").strip()
    if not text:
        return ""
    if any(marker in text for marker in ["账期", "90 天", "90天", "天账期"]) and any(marker in text for marker in ["否则不签", "不签", "签不了"]):
        return "payment_term"
    if any(marker in text for marker in ["接下来呢", "下一步呢", "那接下来", "下一步怎么走", "接下来怎么做"]):
        return "next_step_close"
    if any(marker in text for marker in ["有道理", "确实", "明白了", "你说得对"]):
        return "soft_agreement"
    return "diagnose"


def _should_apply_negotiation_route(context, user_input: str, scene: str, target_intent: str = "") -> bool:
    intent = _get_negotiation_sub_intent(context, user_input, scene)
    if target_intent and intent and intent != target_intent:
        return False
    return scene == "negotiation" and bool(intent or target_intent)


def _get_emotion_sub_intent(context, user_input: str, scene: str) -> str:
    intent = (getattr(context, "emotion_sub_intent", "") or "").strip()
    if intent:
        return intent
    if scene != "emotion":
        return ""
    text = (user_input or "").strip()
    if not text:
        return ""
    if any(marker in text for marker in ["你根本就不爱我", "你根本不爱我", "你是不是不爱我", "你是不是不在乎我", "忘了纪念日", "你在敷衍我", "不被放在心上"]):
        return "accusation_repair"
    if any(marker in text for marker in ["看着电脑就想吐", "一看电脑就想吐", "没法辞职", "不能辞职", "又不能辞职"]):
        return "somatic_relief"
    if any(marker in text for marker in ["没精力想这么多", "不想想这么多", "太累了", "不想再想了", "脑子转不动", "现在只想躺着"]):
        return "low_energy_support"
    if any(marker in text for marker in ["如果失败了怎么办", "要是失败怎么办", "万一失败了怎么办", "失败了怎么办"]):
        return "failure_containment"
    return "diagnose"


def _should_apply_emotion_route(context, user_input: str, scene: str, target_intent: str = "") -> bool:
    intent = _get_emotion_sub_intent(context, user_input, scene)
    if target_intent and intent and intent != target_intent:
        return False
    return scene == "emotion" and bool(intent or target_intent)


def _apply_scene_specific_stabilizers(
    output: str,
    user_input: str,
    scene: str,
    context,
    next_step_policy: str = "soft",
) -> str:
    """把场景级修补收成一层，方便统一做总闸门。"""
    template_scene = _resolve_template_scene(context, user_input, scene)
    allow_soft_closing = next_step_policy in {"soft", "explicit"}
    allow_explicit_closing = next_step_policy == "explicit"
    if allow_explicit_closing:
        output = _stabilize_next_step_prompt(output, user_input, template_scene, context)
        output = _stabilize_negotiation_next_step_closing(output, user_input, template_scene, context)
    if allow_soft_closing:
        output = _stabilize_sales_delay_followup(output, user_input, scene, context)
    output = _stabilize_sales_price_objection(output, user_input, scene, context)
    output = _stabilize_sales_switch_defense(output, user_input, scene, context)
    output = _stabilize_sales_soft_agreement(output, user_input, scene, context)
    output = _stabilize_negotiation_long_payment_term(output, user_input, scene, context)
    output = _stabilize_management_atmosphere_decline(output, user_input, scene, context)
    if allow_explicit_closing:
        output = _stabilize_management_next_step_execution(output, user_input, scene, context)
    output = _stabilize_management_roi_pressure(output, user_input, scene, context)
    output = _stabilize_management_upward_expectation(output, user_input, scene, context)
    output = _stabilize_management_change_fatigue(output, user_input, scene, context)
    output = _stabilize_management_cross_team_alignment(output, user_input, scene, context)
    output = _stabilize_failure_anxiety(output, user_input, scene, context)
    output = _stabilize_emotion_accusation(output, user_input, scene, context)
    output = _stabilize_low_energy_emotion(output, user_input, scene, context)
    output = _stabilize_somatic_work_stress(output, user_input, scene, context)
    output = _stabilize_management_overload(output, user_input, scene, context)
    output = _stabilize_management_self_doubt(output, user_input, scene, context)
    return output


def _stabilize_next_step_prompt(output: str, user_input: str, scene: str, context) -> str:
    """用户明确要下一步时，优先给动作，不把球重新抛回去。"""
    if not _is_next_step_signal(user_input):
        return output
    if scene == "negotiation":
        return output
    if _has_explicit_order_markers(output):
        return output

    templates = {
        "sales": [
            "你这句“接下来呢”很关键，说明你不是随口应付，而是真的在认真看。那我们先别把信息一下铺满，先把结果、顾虑和决定点放到一块儿，接下来就按这三项直接往前看。",
            "你现在是在认真往前看，不是在随口应付。那我们先把话收一收，先看结果、顾虑和决定点，后面就按这三项直接判断下一步。",
            "你不是只想听个说法，是想把这步看明白。那我们就先把结果、顾虑和决定点摆在一块儿，接下来直接按这个顺序往前推。",
            "明白，你是想把这步看清楚再往前走。那我们就先把结果、顾虑和决定点摆在一块儿，后面直接按这三项往前推。",
        ],
        "management": [
            "你愿意继续往前，这就很重要。那就直接落下一步：先定一个24小时内能推进的小动作，再把谁负责、什么时候回看定下来，不要一口气铺太大。",
            "既然你已经想往前走，我们就别空转了：先落一个24小时内能完成的小动作，再把责任人和回看时间定住，别一下把盘子铺太大。",
            "好，那我们就收一个很实在的动作：今天先挑一件能推进的小事，别一下铺太多。谁负责、什么时候回看，先定下来就行。",
            "行，那就别再停在想法上了。今天先挑一件能推进的小事，别一下铺太多；谁负责、什么时候回看，先定下来就行。",
        ],
        "negotiation": [
            "你愿意继续往下谈，说明这轮已经有松动了。那我们顺着收：先锁一个最容易谈拢的点，把口径对齐；再进价格或条件，把让步一项一项换出来；最后定一个回看时间，别又回到空转。",
            "你已经在往成交口子上靠了，我们就顺着收：先锁最容易谈拢的点，把口径对齐；再往价格或条件里换让步；最后定一个回看时间，免得又回到空转。",
            "你已经有一点松动了，那我们就继续往前推：先把最容易谈拢的点对齐，再慢慢交换条件。回看时间先定住，免得又回到空转。",
            "这轮已经有点松动了，我们就顺着往前推：先把最容易谈拢的点对齐，再慢慢交换条件。回看时间先定住，免得又回到空转。",
        ],
        "emotion": [
            "那我们先不把事情一下谈大，先做一步最稳的：把你现在最痛的那个点说清楚，别急着争输赢。",
            "我们先别把这件事一下放到最大，先抓住你现在最痛的那一块。你把那个点说清楚，我们再慢慢往下走，不用急着分输赢。",
            "先不用把事情放大，我们先抓住你现在最难受的那一块。把那个点说清楚就行，先别急着分输赢。",
            "别一下把事摊太大，我们先只抓住你最痛的那一块。那个点说出来就行，先别忙着分输赢。",
            "先别把事一下放大，我们就抓住你现在最难受的那一块。那个点说出来就行，先别急着分输赢。",
        ],
    }
    if not _needs_next_step_rescue(output, scene, context):
        return output
    return _pick_variant("next_step", context, user_input, scene, templates.get(scene, [output]))


def _resolve_template_scene(context, user_input: str, scene: str) -> str:
    """
    模板场景小修正：
    在“下一步”语义里，如果主场景被 sales 抢占，但底层场景配置是 negotiation，
    优先使用谈判模板，降低收口语气漂移。
    """
    if not _is_next_step_signal(user_input):
        return scene

    if scene != "sales":
        return scene

    scene_cfg = getattr(context, "scene_config", None)
    config_scene = getattr(scene_cfg, "scene_id", "")
    secondary_scenes = set(getattr(context, "secondary_scenes", []) or [])

    if "negotiation" in secondary_scenes:
        return "negotiation"
    if config_scene == "negotiation":
        return "negotiation"
    return scene


def _stabilize_negotiation_next_step_closing(output: str, user_input: str, scene: str, context) -> str:
    """谈判“下一步”专用收口：更短、更可执行，减少空泛感。"""
    if not _should_apply_negotiation_route(context, user_input, scene, "next_step_close"):
        return output
    if _get_negotiation_sub_intent(context, user_input, scene) != "next_step_close" and not _is_next_step_signal(user_input):
        return output
    if not _needs_negotiation_close_rescue(output, context):
        return output

    variants = [
        "好，我们就收成一个可执行的下一步。先挑一个最容易达成一致的点，只谈一个变量。接着交换条件：你先给可接受区间，我给对应让步。今天把口径对齐并拉齐拍板人，明天固定确认窗口，别让这轮回到空转。",
        "我们把这轮收成一个可执行的下一步：先锁最容易达成一致的点，只谈一个变量；再交换条件，你先给可接受区间，我给对应让步；今天把口径对齐并拉齐拍板人，明天固定确认窗口，不会回到空转。",
        "那就别再往下散聊了，我们直接收一个可执行的下一步动作：先锁一个最容易达成一致的点，再把让步条件一项一项交换。今天把口径对齐并拉齐拍板人，明天固定确认窗口，这样就不会回到空转。",
    ]
    return _pick_variant("negotiation_next_step_close", context, user_input, scene, variants)


def _soften_ack_followup(output: str, user_input: str, scene: str, context) -> str:
    """“继续说”这类输入直接走稳定续讲模板，避免模型随机跑偏。"""
    # 下一步语义优先走 next-step 系列模板，避免被续讲模板覆盖。
    if _is_next_step_signal(user_input):
        return output
    if scene not in {"sales", "management", "negotiation", "emotion"}:
        return output
    if not _is_continue_signal(user_input):
        if not (scene == "negotiation" and _is_affirmation_signal(user_input)):
            return output
    templates = {
        "sales": [
            "收到，你愿意继续往前聊，说明你在认真比较。我先不催你下结论，我们先把一个关键点讲透：你现在更想先确认结果、成本，还是落地节奏？",
            "我接住了，你不是随便聊聊，是在认真比较。我们先别急着下结论，只把一个关键点讲透：你现在更想先确认结果、成本，还是落地节奏？",
            "明白，你是想把这件事看清楚再往前走。那我们先别急着收结论，先把一个关键点讲透：你现在更在意结果、成本，还是落地节奏？",
        ],
        "management": [
            "好，我们继续。你愿意接着聊，本身就不容易。先不谈大改变，只做一步：把现在最卡的一件事写下来，再定一个今天10分钟能完成的小动作。你把这一步发我，我们一起把它走完。",
            "行，我们继续。你愿意接着聊，我先接住。先不谈大改变，只做一步：把现在最卡的一件事写下来，再定一个今天10分钟能完成的小动作。你把这一步发我，我们一起把它走完。",
            "可以，我们顺着往下聊。你愿意继续说，说明这事对你真的很重要。先别急着一下改很多，只做一步：把现在最卡的一件事写下来，再定一个今天10分钟能完成的小动作。",
        ],
        "negotiation": [
            "你这句认可很重要，说明这轮已经有松动了。我们就顺着往下谈：先别一下铺开，先锁一个最容易谈拢的点，把价格、交付或者风险边界一个个对齐。",
            "你这句认可很重要，说明这轮已经有松动了。那我们就顺着往下谈：先别把东西一下铺开，先锁最容易谈拢的点，把价格、交付或者风险边界一个个对齐。",
            "这个认可很重要，已经够我们往前走一步了。先别急着摊满，挑一个最容易谈拢的点，把价格、交付或风险边界先对齐，再往下展开。",
            "好，既然你已经认可了一部分，那我们就继续往前推一点：先锁最容易谈拢的点，把价格、交付或者风险边界一个个对齐。",
        ],
        "emotion": [
            "好，我继续，但我们先不急着下结论。你刚才那句话里，最刺痛你的那个点是什么？",
            "行，我继续。先不急着下结论，我们先把刚才最刺痛你的那个点拎出来。",
            "可以，我们先慢一点，不急着下结论。你刚才最刺痛你的那个点，是事情本身，还是那种被顶回去的感觉？",
            "行，我们先接着说，不急着下结论。你刚才最难受的那一块，是事情本身，还是那种被忽略的感觉？",
        ],
    }
    if not _needs_followup_rescue(output, scene, context):
        return output
    return _pick_variant("ack_followup", context, user_input, scene, templates.get(scene, [output]))


def _stabilize_emotion_accusation(output: str, user_input: str, scene: str, context) -> str:
    """情绪指责先接住受伤感，再补一个轻问题，避免直接反推。"""
    if not _should_apply_emotion_route(context, user_input, scene, "accusation_repair"):
        return output
    if _get_emotion_sub_intent(context, user_input, scene) != "accusation_repair" and not _looks_like_emotional_accusation(user_input):
        return output
    anchors = ["不舒服", "被晾在一边", "不被放在心上", "没被认真看见", "争对错", "接住"]
    if not _needs_emotion_boundary_rescue(output, context, anchors, min_len=30):
        return output

    variants = [
        (
            "听得出来，这件事让你很难受，也让你很难再相信。"
            "先别急着争对错，我们先把你真正卡住的那一下说清楚。"
            "你更难受的是这件事本身，还是那种被晾在一边的感觉？"
        ),
        (
            "你会这么说，说明这件事真的碰到你了。"
            "我先不跟你争道理，先把你这口气接住。"
            "你现在最难受的，是事情本身，还是那种不被放在心上的感觉？"
        ),
        (
            "我听到了，你不是在闹情绪，是这件事真的让你不舒服。"
            "先别急着定谁对谁错，我们先把那一下伤到你的地方说透。"
            "你最卡的是他做了什么，还是你当时感受到的那个落差？"
        ),
        (
            "我听到了，这件事真的让你不舒服，我先不跟你争道理，先接住你这个感觉。"
            "先不急着争对错，我们先把真正刺到你的那一下说清楚。"
            "你更难受的是事情本身，还是那种没被认真看见的感觉？"
        ),
    ]
    return _pick_variant("emotion_accusation", context, user_input, scene, variants)


def _looks_like_low_energy_input(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    markers = [
        "没精力想这么多",
        "不想想这么多",
        "太累了",
        "不想再想了",
        "脑子转不动",
        "现在只想躺着",
    ]
    return any(m in text for m in markers)


def _looks_like_sales_delay_signal(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    markers = [
        "跟老板汇报",
        "让我等消息",
        "回去汇报",
        "等我消息",
        "我再看看",
    ]
    return any(m in text for m in markers)


def _stabilize_sales_delay_followup(output: str, user_input: str, scene: str, context) -> str:
    """销售里遇到“回去汇报/等消息”，先降压，再给一个低门槛动作。"""
    if not _should_apply_sales_route(context, user_input, scene, "delay_followup"):
        return output
    sales_sub_intent = _get_sales_sub_intent(context, user_input, scene)
    if sales_sub_intent != "delay_followup" and not _looks_like_sales_delay_signal(user_input):
        return output
    anchors = ["汇报", "三个点", "30 秒", "下一步最小动作", "结论"]
    if sales_sub_intent == "delay_followup" and scene != "sales":
        hit_count = sum(1 for anchor in anchors if anchor in (output or ""))
        if hit_count >= 3 and not _is_too_similar_to_recent_output(output, context):
            return output
    elif not _needs_sales_boundary_rescue(output, context, anchors, min_len=30):
        return output

    variants = [
        "你先去汇报、让我等消息，这个节奏我能理解，本来就是正常流程。你先不用急着给我结论，我们先把这次汇报变得轻一点：只带三个点去说，为什么现在要动、最担心的风险怎么兜、下一步最小动作是什么。如果你愿意，我可以先帮你把这三点压成一版 30 秒就能讲完的话。",
        "先去汇报、先等消息，这个节奏很正常。你先不用急着给我结论，我们把这次汇报压到最简单：只带三个点去说，为什么现在要动、最担心的风险怎么兜、下一步最小动作是什么。我可以先帮你整理成一版 30 秒就能讲完的话。",
        "你先回去说一圈也可以，先等消息也可以，这都正常。我们先不用急着给我结论，就把这次汇报收成三个点：为什么要动、最担心什么、下一步先做什么。我先帮你压成一版 30 秒就能讲完的话。",
    ]
    return _pick_variant("sales_delay", context, user_input, scene, variants)


def _looks_like_sales_price_objection(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    has_price_signal = any(m in text for m in ["太贵", "价格高", "贵了", "便宜", "降价"])
    has_competitor_signal = any(m in text for m in ["竞品", "同行", "其他家", "别家"])
    return has_price_signal and has_competitor_signal


def _stabilize_sales_price_objection(output: str, user_input: str, scene: str, context) -> str:
    """销售价格异议：先承认价差，再把比较口径从单价拉到总成本和风险。"""
    if not _should_apply_sales_route(context, user_input, scene, "price_objection"):
        return output
    if _get_sales_sub_intent(context, user_input, scene) != "price_objection" and not _looks_like_sales_price_objection(user_input):
        return output
    anchors = ["总账算清", "10 分钟对比", "总成本", "故障损失", "响应时效", "后续运维"]
    if not _needs_sales_boundary_rescue(output, context, anchors, min_len=34):
        return output

    variants = [
        "你提到竞品便宜 30%，这个差价很实在，我完全理解你会先卡在这里。我们先不急着比采购单价，先把总账算清：上线风险、故障损失、响应时效、后续运维这几项，通常比单价差更影响一年总成本。如果你愿意，我们就按你们当前数据做一版 10 分钟对比，把“省下的”和“可能多出的”摆在一张表上，再决定值不值。",
        "竞品便宜 30% 这个点，我理解你为什么会先卡住。我们先不急着比采购单价，先把总账算清：上线风险、故障损失、响应时效、后续运维这些，往往比单价差更影响一年总成本。你愿意的话，我们按你们当前数据做一版 10 分钟对比，把“省下的”和“可能多出的”放到一张表里再看值不值。",
        "你说竞品便宜 30%，这个提醒很真实。我们先不急着只看采购单价，先把总账算清，再把整年总成本摊开看：上线风险、故障损失、响应时效、后续运维。要是你愿意，我们做一版 10 分钟对比，把这笔账讲得更直白一点，再判断值不值。",
    ]
    return _pick_variant("sales_price", context, user_input, scene, variants)


def _looks_like_sales_switch_defense(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    has_current_system_signal = any(m in text for m in ["现在用的系统", "现在系统", "现有系统", "现在这套"])
    has_why_switch_signal = any(m in text for m in ["为什么要换", "为啥要换", "为什么换", "没必要换"])
    return has_current_system_signal and has_why_switch_signal


def _stabilize_sales_switch_defense(output: str, user_input: str, scene: str, context) -> str:
    """销售“为什么要换”防御开局：先承认现状，再给低风险验证动作。"""
    if not _should_apply_sales_route(context, user_input, scene, "switch_defense"):
        return output
    if _get_sales_sub_intent(context, user_input, scene) != "switch_defense" and not _looks_like_sales_switch_defense(user_input):
        return output
    anchors = ["7 天并行对比", "处理时长", "返工率", "响应时效", "低风险验证"]
    if not _needs_sales_boundary_rescue(output, context, anchors, min_len=34):
        return output

    variants = [
        "你现在这套系统能用，这个判断很理性，我先认同你这个出发点。我们先不谈“全面替换”，只做一个低风险验证：挑一个最卡流程，做 7 天并行对比。只看三项硬指标：处理时长、返工率、响应时效。如果没有明显提升，就按你原方案走；如果有提升，我们再谈下一步，避免你承担不必要风险。",
        "现有系统能跑，这个判断很理性，我先认同。我们先不谈“全面替换”，只做一个低风险验证：挑最卡的流程做 7 天并行对比，只看处理时长、返工率、响应时效。没明显提升就按原方案走；有提升再谈下一步，免得你承担不必要风险。",
        "你担心贸然替换会出问题，这个顾虑很正常。我们先不谈“全面替换”，先拿最卡的流程做 7 天并行对比，盯住处理时长、返工率、响应时效这三项。结果不变就继续按原路走，真有提升再往下谈。",
    ]
    return _pick_variant("sales_switch", context, user_input, scene, variants)


def _looks_like_sales_soft_agreement(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    return (
        "有道理" in text
        and ("确实是这样想" in text or "我确实是这样想" in text or "确实这样想" in text)
    )


def _stabilize_sales_soft_agreement(output: str, user_input: str, scene: str, context) -> str:
    """销售松动确认句：别散聊，直接收一个可执行下一步。"""
    if not _should_apply_sales_route(context, user_input, scene, "soft_agreement"):
        return output
    if _get_sales_sub_intent(context, user_input, scene) != "soft_agreement" and not _looks_like_sales_soft_agreement(user_input):
        return output
    anchors = ["最担心点", "最想看到的结果", "最小对比方案", "明天这个时间"]
    if not _needs_sales_boundary_rescue(output, context, anchors, min_len=30):
        return output

    variants = [
        "方向已经对上了，也已经有共识了。我们就收成一步可执行动作：你先给我 1 个最担心点和 1 个最想看到的结果，我按这两点给你做一版最小对比方案，你明天这个时间直接判断要不要推进。",
        "既然已经对齐，也已经有共识了，那就别再往下散聊了。你先给我 1 个最担心点和 1 个最想看到的结果，我按这两点做一版最小对比方案，你明天这个时间直接判断要不要推进。",
        "现在已经差不多对上了，也算是有共识了，我们就收成一个小动作：你先给我 1 个最担心点和 1 个最想看到的结果，我按这两点先做个最小对比方案，你明天这个时间再看要不要推进。",
    ]
    return _pick_variant("sales_soft_agreement", context, user_input, scene, variants)


def _looks_like_negotiation_long_payment_term(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    has_term_signal = any(m in text for m in ["账期", "天账期", "90 天", "90天"])
    has_signing_pressure = any(m in text for m in ["否则不签", "不签", "签不了"])
    return has_term_signal and has_signing_pressure


def _stabilize_negotiation_long_payment_term(output: str, user_input: str, scene: str, context) -> str:
    """谈判账期要价：从单点对抗改为条件交换，防止僵持。"""
    if not _should_apply_negotiation_route(context, user_input, scene, "payment_term"):
        return output
    if _get_negotiation_sub_intent(context, user_input, scene) != "payment_term" and not _looks_like_negotiation_long_payment_term(user_input):
        return output

    variants = [
        "你们卡 90 天账期这点我听清了，我们不硬顶，直接用交换式谈法。如果坚持 90 天，我们就同步对齐首批量、预付款比例和回款节点；如果账期能回到 60 天，我们在价格或交付上给对应让步。先选一个你更可接受的区间，我们今天把条款草案对齐，明天确认签约窗口。",
        "90 天账期这个点我听清了，我们不硬顶，直接用交换式谈法。坚持 90 天的话，就同步对齐首批量、预付款比例和回款节点；如果账期回到 60 天，我们在价格或交付上给对应让步。先选一个你更可接受的区间，今天把条款草案对齐，明天确认签约窗口。",
        "90 天账期这件事我听明白了，我们先不硬碰，还是走交换式谈法：账期尽量往 60 天靠，首批量、预付款比例、回款节点一起对齐。你先选一个更能接受的区间，我们今天把条款草案对齐，明天确认签约窗口。",
    ]
    return _pick_variant("negotiation_payment", context, user_input, scene, variants)


def _looks_like_failure_anxiety(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    markers = [
        "如果失败了怎么办",
        "要是失败怎么办",
        "万一失败了怎么办",
        "失败了怎么办",
    ]
    return any(m in text for m in markers)


def _stabilize_failure_anxiety(output: str, user_input: str, scene: str, context) -> str:
    """灾难化担心先收住“后果感”，再拆成一个可处理的小格子。"""
    if not _should_apply_emotion_route(context, user_input, scene, "failure_containment"):
        return output
    if _get_emotion_sub_intent(context, user_input, scene) != "failure_containment" and not _looks_like_failure_anxiety(user_input):
        return output
    anchors = ["后面整串", "先拆眼前这一格", "最先让你难受", "怎么兜", "失败"]
    if not _needs_emotion_boundary_rescue(output, context, anchors, min_len=30):
        return output

    variants = [
        "你现在怕的不是一个结果本身，而是怕一旦失败，后面整串事都会压过来。我们先别一下想到最后，只先拆眼前这一格：如果这件事没有按你想的走，最先让你难受的会是哪一部分？你怕一旦失败，我懂，我们先把那一格说清，再看怎么兜。你怕一旦失败，这个担心本身就已经很重了。",
        "你担心的不是单个结果，而是怕失败之后后面一串都压上来。我们先别把场景拉太远，只拆眼前这一格：如果事情没有按你想的走，最先让你难受的会是哪一部分？先把那一格说清，再看怎么兜。你怕一旦失败，这个担心本身也会很重。",
    ]
    return _pick_variant("failure_anxiety", context, user_input, scene, variants)


def _stabilize_low_energy_emotion(output: str, user_input: str, scene: str, context) -> str:
    """低能量状态先减负，再给极轻的问题，避免把人重新拉进消耗。"""
    if not _should_apply_emotion_route(context, user_input, scene, "low_energy_support"):
        return output
    if _get_emotion_sub_intent(context, user_input, scene) != "low_energy_support" and not _looks_like_low_energy_input(user_input):
        return output
    anchors = ["不用逼自己立刻想清楚", "累、烦", "心里堵", "整个人都发紧", "眼前这一点"]
    if not _needs_emotion_boundary_rescue(output, context, anchors, min_len=24):
        return output

    variants = [
        "行，那我们先不把事情想大，你现在不用逼自己立刻想清楚。我们先只看眼前这一点：你此刻更像是累、烦，还是心里堵得慌？",
        "好，先别把事想大，你不用逼自己立刻想清楚。我们只看眼前这一点：你现在更像是累、烦，还是心里堵得慌？",
        "可以，先别逼自己把整件事想明白。我们只看眼前这一口气：你现在更像是累、烦，还是整个人都发紧？",
    ]
    return _pick_variant("low_energy", context, user_input, scene, variants)


def _looks_like_somatic_work_stress(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    markers = [
        "看着电脑就想吐",
        "一看电脑就想吐",
        "没法辞职",
        "不能辞职",
        "又不能辞职",
    ]
    return any(m in text for m in markers)


def _stabilize_somatic_work_stress(output: str, user_input: str, scene: str, context) -> str:
    """生理排斥+工作困住场景：先减负，再给超小动作。"""
    if not _should_apply_emotion_route(context, user_input, scene, "somatic_relief"):
        return output
    if _get_emotion_sub_intent(context, user_input, scene) != "somatic_relief" and not _looks_like_somatic_work_stress(user_input):
        return output
    anchors = ["身体已经在拉警报", "先不谈辞职", "小止损", "盯屏", "离开屏幕"]
    if not _needs_emotion_boundary_rescue(output, context, anchors, min_len=28):
        return output

    variants = [
        "你这不是矫情，是身体已经在拉警报了。先不谈辞职这种大决定，我们先做一个今天就能做的小止损：把连续盯屏切成短段，每段结束让眼睛和身体离开屏幕一会儿。如果你愿意，我可以按你现在的节奏给你排一个最轻的版本。",
        "这不是矫情，是身体已经在拉警报。先不谈辞职这种大决定，我们先做一个今天就能做的小止损：把连续盯屏切成短段，每段结束让眼睛和身体离开屏幕一会儿。我可以按你现在的节奏帮你排一个最轻的版本。",
        "这更像是身体在提醒你已经撑太久了。先不谈辞职这种大决定，我们先做一个今天就能做的小止损：把连续盯屏切成短段，段和段之间让眼睛和身体缓一缓。我可以按你现在的节奏给你排一个最轻的版本。",
    ]
    return _pick_variant("somatic_work", context, user_input, scene, variants)


def _looks_like_work_self_doubt(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    markers = [
        "不适合这份工作",
        "我不适合这份工作",
        "不适合现在这份工作",
        "我不适合现在这份工作",
    ]
    return any(m in text for m in markers)


def _looks_like_management_overload_complaint(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    markers = [
        "总是给我安排这么多任务",
        "任务太多",
        "安排这么多",
        "活太多",
        "忙不过来",
        "为什么总是给我",
    ]
    return any(m in text for m in markers)


def _stabilize_management_overload(output: str, user_input: str, scene: str, context) -> str:
    """管理场景“任务过载”先接住压力，再给一个可执行分流动作。"""
    if scene != "management" or not _looks_like_management_overload_complaint(user_input):
        return output
    anchors = ["最占你精力", "必须今天做", "可以后放", "回看的时间"]
    if not _needs_management_boundary_rescue(output, context, anchors, min_len=30):
        return output

    variants = [
        "这不是在找借口，是压力已经超线了，我先接住你。先不争对错，咱们把事情摊开看：现在最占你精力的三件事是什么。先把“必须今天做”和“可以后放”的边界划一下，再约个回看的时间，别一个人硬扛。",
        "压力已经超线了，这个我听见了。先不争对错，先把任务摊开：眼下最占你精力的三件事是什么。今天先把“必须今天做”和“可以后放”的边界分一下，再定一个回看时间。",
        "我知道你不是想躲，是真的被压住了。先别急着解释，咱们先看现在最占你力气的三件事，把“先做”和“后放”划开，再留一个回看的时间。",
    ]
    return _pick_variant("management_overload", context, user_input, scene, variants)


def _stabilize_management_self_doubt(output: str, user_input: str, scene: str, context) -> str:
    """管理场景自我否定：先接住价值感，再落到可执行的小动作。"""
    if scene not in {"management", "emotion"} or not _looks_like_work_self_doubt(user_input):
        return output
    anchors = ["不适合", "最卡的一件事", "岗位", "节奏", "方法"]
    if not _needs_management_boundary_rescue(output, context, anchors, min_len=30):
        return output

    variants = [
        "你会这么说，说明你最近真的扛得很吃力，不是你不努力。先别急着给自己下“适不适合”的总判决，先把最卡的一件事拎出来。只要把这一件推进一点点，你就能更清楚问题是岗位不匹配，还是节奏和方法出了偏差。",
        "你这么想，说明你最近真的扛得很吃力，不是不努力。先别急着给自己下“适不适合”的总判决，先把最卡的一件事拎出来。哪怕只往前挪一点，也能看清是岗位不对，还是方法和节奏该换一换。",
        "你现在会这么想，我更愿意理解成你真的累了，不是你不行。先别急着把自己一口气判成“不适合”，先抓住那件最卡的事，往前挪一点，我们再看是岗位、节奏还是方法出了偏差。",
    ]
    return _pick_variant("management_self_doubt", context, user_input, scene, variants)


def _looks_like_management_atmosphere_decline(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    markers = [
        "团队氛围越来越差",
        "团队氛围变差",
        "氛围越来越差",
        "团队氛围不好",
        "团队气氛越来越差",
    ]
    return any(m in text for m in markers)


def _stabilize_management_atmosphere_decline(output: str, user_input: str, scene: str, context) -> str:
    """管理场景“氛围变差”：先把抽象抱怨落到可执行事实和动作。"""
    if scene != "management" or not _looks_like_management_atmosphere_decline(user_input):
        return output
    anchors = ["最近一周", "发生了什么", "影响了谁", "今天就能去对齐"]
    if not _needs_management_boundary_rescue(output, context, anchors, min_len=30):
        return output

    variants = [
        "你能把这句话说出来很重要，说明你确实在认真看团队状态。先别一下子泛谈“氛围”，我们先抓最近一周里最典型的一次协作。把它拆成三块：发生了什么、影响了谁、你希望下次怎么做。你给我这三点，我帮你压成一版今天就能去对齐的话术。",
        "能说出“氛围变差”这件事，本身就说明你已经在观察团队了。先别讲太大，我们先抓一个具体场景：最近一周里哪一次协作最让你不舒服。把这件事拆成三块：发生了什么、影响了谁、你想要怎样的变化。我来帮你整理成今天就能去对齐的话。",
        "你能察觉到氛围在往下走，这其实已经很重要了。先别把它说成一个很大的问题，先抓最近一周里最典型的一次协作，把发生了什么、影响了谁、你希望怎么变拆清楚，我们今天就能去对齐。",
    ]
    return _pick_variant("management_atmosphere", context, user_input, scene, variants)


def _stabilize_management_next_step_execution(output: str, user_input: str, scene: str, context) -> str:
    """管理场景下一步：给明确时间锚点，减少“听懂了但不落地”。"""
    management_sub_intent = _get_management_sub_intent(context, user_input, scene)
    if not _should_apply_management_route(context, user_input, scene, "action_request"):
        return output
    if management_sub_intent not in {"action_request"} and not _is_next_step_signal(user_input):
        return output
    if not _needs_management_next_step_rescue(output, context):
        return output
    anchors = ["30 分钟", "回看时间", "做了什么", "卡在哪", "下一步谁负责"]
    if not _needs_management_boundary_rescue(output, context, anchors, min_len=30):
        return output

    variants = [
        "好，我们直接落下一步，不再空转。先别把它想太大，今天就挑一件最卡的事，做一个 30 分钟可完成的小动作。明天固定一个回看时间，只复盘做了什么、卡在哪、下一步谁负责。",
        "行，那就直接落下一步，先把事情往前推一点。今天先定一个最卡的问题，做一个 30 分钟可完成的小动作；明天固定一个回看时间，只看做了什么、卡在哪、下一步谁负责。",
        "那我们就别停在理解上了，直接落下一步。今天先把最卡的一件事变成一个 30 分钟可完成的小动作，明天固定一个回看时间，复盘做了什么、卡在哪、下一步谁负责。先走一小步，后面再看要不要拆得更细。",
    ]
    return _pick_variant("management_next_step", context, user_input, scene, variants)


def _looks_like_management_roi_pressure(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    markers = [
        "ROI",
        "roi",
        "预算",
        "财务总监",
        "证明 AI 投入",
        "证明投入",
        "投入产出",
        "回报率",
    ]
    return any(m in text for m in markers)


def _stabilize_management_roi_pressure(output: str, user_input: str, scene: str, context) -> str:
    """管理场景 ROI 压力：别再泛问，直接落到能汇报的证据框架。"""
    management_sub_intent = _get_management_sub_intent(context, user_input, scene)
    if not _should_apply_management_route(context, user_input, scene, "roi_justification"):
        return output
    if management_sub_intent != "roi_justification" and not _looks_like_management_roi_pressure(user_input):
        return output
    anchors = ["基线", "节省", "一页", "时间", "成本", "对比"]
    if not _needs_management_boundary_rescue(output, context, anchors, min_len=28):
        return output

    variants = [
        "这时候别先跟财务讲一堆大词，先交一版能看懂的账。先抓三件事：现在人工要花多少时间、上了 AI 后能省多少时间、这部分节省大概折成多少成本。先做一页对比，不求完美，但要让他一眼看懂“现在是什么、变化是什么、值不值”。",
        "ROI 这件事别先算得太花，先把最硬的三块拿出来：现在的人力时间、引入 AI 后省下来的时间、这部分大概能换回多少成本或效率。先整理成一页表，左边写现状，右边写变化，中间只放最关键的差值。",
        "财务要的不是热情，是一版能落到数字的说明。你先别急着证明一切，先拿一个最典型的流程做基线：现在花多久、上 AI 后能省多久、这部分一年大概能省多少钱。先把这一条打透，比一次讲十条更有说服力。",
    ]
    return _pick_variant("management_roi_pressure", context, user_input, scene, variants)


def _looks_like_management_upward_expectation(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    leader_markers = ["领导", "CEO", "老板", "财务总监"]
    pressure_markers = ["进度不满", "要求", "不符合实际", "技术债", "三个月内", "转型"]
    return any(m in text for m in leader_markers) and any(m in text for m in pressure_markers)


def _stabilize_management_upward_expectation(output: str, user_input: str, scene: str, context) -> str:
    """向上预期管理：别停在共情，直接给一版能拿去汇报的结构。"""
    management_sub_intent = _get_management_sub_intent(context, user_input, scene)
    if not _should_apply_management_route(context, user_input, scene, "upward_report"):
        return output
    if management_sub_intent != "upward_report" and not _looks_like_management_upward_expectation(user_input):
        return output
    anchors = ["现状", "风险", "节点", "取舍", "资源", "一页"]
    if not _needs_management_boundary_rescue(output, context, anchors, min_len=30):
        return output

    variants = [
        "这种时候别先跟领导硬顶，也别只讲困难。你先准备一版一页纸，只讲四件事：现状卡在哪、如果继续硬推会冒什么风险、接下来两到三个可交付节点、你需要领导拍板的取舍是什么。这样他看到的就不是“你在解释”，而是“你在控盘”。",
        "向上汇报这类问题，关键不是把委屈讲满，而是把盘面讲清。你先拿一页结构出来：现状、主要风险、接下来能交付的节点、需要上面支持或拍板的取舍。这样领导会更容易从“催进度”切到“帮你做选择”。",
        "别先急着证明不是你的问题，先把局面摆平。你可以按四块去汇报：现在真实进度到哪、技术债卡住了什么、接下来两步能交什么、哪些资源或取舍需要领导拍板。先让他看到路线，再谈压力。",
    ]
    return _pick_variant("management_upward_expectation", context, user_input, scene, variants)


def _stabilize_management_change_fatigue(output: str, user_input: str, scene: str, context) -> str:
    """变革疲劳：先减负，再保留一个最小动作，不继续加码。"""
    management_sub_intent = _get_management_sub_intent(context, user_input, scene)
    if not _should_apply_management_route(context, user_input, scene, "change_fatigue") or management_sub_intent != "change_fatigue":
        return output
    anchors = ["暂停", "保留", "一件", "减负", "本周", "先停"]
    if not _needs_management_boundary_rescue(output, context, anchors, min_len=24):
        return output

    variants = [
        "这时候先别再往团队头上加新东西了。你本周先做一件事：把所有新增动作摊开，只保留一项最影响结果的，其他先暂停。先让团队从“被推着跑”变回“知道现在只要守住哪一件事”。",
        "变革疲劳最怕继续加码。你先别急着推新工具，本周先做减法：把当前要求列出来，只留一件最关键的动作，其余先停。先让大家喘口气，再谈下一步。",
        "先别再补新动作了，这时候更需要减负。你先把所有变化摊平，只保留一个最关键动作，其余先暂停一周。先稳住节奏，再决定哪些真的值得继续推。",
    ]
    return _pick_variant("management_change_fatigue", context, user_input, scene, variants)


def _stabilize_management_cross_team_alignment(output: str, user_input: str, scene: str, context) -> str:
    """跨部门协同：先收口问题，再给一个对齐动作。"""
    management_sub_intent = _get_management_sub_intent(context, user_input, scene)
    if not _should_apply_management_route(context, user_input, scene, "cross_team_alignment") or management_sub_intent != "cross_team_alignment":
        return output
    anchors = ["拉到一起", "同一张纸", "争议点", "负责人", "会后", "统一口径"]
    if not _needs_management_boundary_rescue(output, context, anchors, min_len=26):
        return output

    variants = [
        "这种时候别让两边继续各说各话。你先把研发和市场拉到同一张纸上，只做三件事：这次到底在争什么、各自最怕什么、会后谁来收一个统一口径。先把争议点写实，再谈谁改动作。",
        "跨部门卡住时，先别忙着评对错。你先组织一个短会，把双方争议点、各自底线、最后谁负责收口定下来。先让大家看到的是同一个问题，而不是各自的情绪。",
        "先别让两边继续拉扯。你先把人拉到一起，对齐三件事：争议点是什么、各自不能退的边界是什么、会后谁负责收一个统一版本。先把口径合上，再往下推进。",
    ]
    return _pick_variant("management_cross_team_alignment", context, user_input, scene, variants)


def _enforce_minimum_response(output: str, scene: str, short_utterance: bool) -> str:
    """避免出现只有一两句口头禅的过短输出（短句模式除外）。"""
    text = (output or "").strip()
    if not text or short_utterance:
        return text
    compact = text.replace("\n", "").replace(" ", "")
    if len(compact) >= 12:
        return text
    return text


def _apply_crisis_guard(output: str, user_input: str, scene: str) -> str:
    """情绪场景遇到高危表达时，补一层明确的安全提醒。"""
    if scene != "emotion" or not _contains_crisis_intent(user_input):
        return output

    text = (output or "").strip()
    already_guarded = any(k in text for k in ["110", "120", "伤害自己", "现在是一个人"])
    if already_guarded:
        return text

    guard = "我会认真对待你这句话。你现在是一个人吗？如果你有马上伤害自己的冲动，请先联系当地紧急援助（110/120）或让身边可信任的人陪着你。"
    if len(text) < 30:
        return f"我听见你现在很难受，这句话我会认真对待。\n\n{guard}"
    return f"{text}\n\n{guard}"


def _build_strategy_skeleton_hint(context) -> str:
    """把 Step6 策略骨架转成简短提示，供成品层控制表达顺序。"""
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


def _looks_like_progress_request(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    if _is_next_step_signal(text):
        return True
    markers = ["推进", "先做", "怎么做", "怎么走", "动作", "下一步"]
    return any(m in text for m in markers)


def _has_explicit_order_markers(output: str) -> bool:
    text = (output or "").strip()
    if not text:
        return False
    return bool(
        re.search(r"(第一步|第二步|先.{0,18}(再|然后)|先做|后做|最后|就做一件事|今天先|本周就做一件事|先定一个)", text)
    )


def _inject_skeleton_order_if_missing(output: str, user_input: str, context) -> str:
    """
    目标 D 补强：当用户明确要“下一步/推进”且成品里没有顺序表达时，
    用 Step6 骨架补一段可执行先后顺序，降低随机漂移。
    """
    text = (output or "").strip()
    if not text:
        return text
    if not _looks_like_progress_request(user_input):
        return text
    if _has_explicit_order_markers(text):
        return text

    skeleton = getattr(getattr(context, "current_strategy", None), "skeleton", None)
    if not skeleton:
        return text

    do_now = list(getattr(skeleton, "do_now", []) or [])
    do_later = list(getattr(skeleton, "do_later", []) or [])
    avoid_now = list(getattr(skeleton, "avoid_now", []) or [])
    if not do_now:
        return text

    def _clean_instruction_head(content: str) -> str:
        cleaned = (content or "").strip().rstrip("。")
        for prefix in ("先把", "先", "再", "后面", "之后", "不要", "别", "先别"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        return cleaned or (content or "").strip().rstrip("。")

    order_lines = [f"这轮先把{_clean_instruction_head(do_now[0])}。"]
    if do_later:
        order_lines.append(f"等这步稳住，再补{_clean_instruction_head(do_later[0])}。")
    if avoid_now:
        order_lines.append(f"先别急着{_clean_instruction_head(avoid_now[0])}。")
    return f"{text}\n\n{' '.join(order_lines)}"


def _resolve_order_source(user_input: str, before_output: str, after_output: str) -> str:
    """
    顺序来源标记（仅内部可观测）。
    """
    if not _looks_like_progress_request(user_input):
        return "not_progress_request"
    if _has_explicit_order_markers(before_output):
        return "model_explicit_order"
    if (after_output or "").strip() != (before_output or "").strip():
        return "skeleton_injected"
    if _has_explicit_order_markers(after_output):
        return "postprocess_order"
    return "no_order_marker"


def _build_memory_hint_signals(strategy_plan) -> dict:
    """提取 Step6 记忆提示命中信号，供评测可观测汇总使用。"""
    description = ""
    if strategy_plan is not None:
        description = str(getattr(strategy_plan, "description", "") or "")
    return {
        "failure_avoid_hint": "失败规避提示：" in description,
        "experience_digest_hint": "经验索引提示：" in description,
        "decision_experience_hint": "经验决策提示：" in description,
    }


def _get_state_value(state, key: str, default=None):
    if isinstance(state, dict):
        return state.get(key, default)
    if hasattr(state, "get"):
        try:
            return state.get(key, default)
        except Exception:
            pass
    return getattr(state, key, default)


def _set_state_value(state, context, key: str, value):
    if hasattr(state, "__setitem__"):
        try:
            state[key] = value
        except Exception:
            pass
    if context is not None:
        try:
            object.__setattr__(context, key, value)
        except Exception:
            try:
                setattr(context, key, value)
            except Exception:
                pass


def _ensure_runtime_trace(state, context) -> dict:
    trace = _get_state_value(state, "runtime_trace", None)
    context_trace = getattr(context, "runtime_trace", None)
    if not isinstance(trace, dict):
        trace = context_trace if isinstance(context_trace, dict) else {}
    elif isinstance(context_trace, dict) and context_trace is not trace:
        merged = dict(trace)
        merged.update(context_trace)
        trace = merged
    trace.setdefault("turn_load_level", getattr(context, "turn_load_level", "standard"))
    trace.setdefault("next_step_policy", getattr(context, "next_step_policy", "soft"))
    trace.setdefault("memory_mode", "minimal")
    trace.setdefault("memory_read_count", 0)
    trace.setdefault("unified_context_loaded", False)
    _set_state_value(state, context, "runtime_trace", trace)
    return trace


def _resolve_step8_mode(state, context) -> str:
    trace = _get_state_value(state, "runtime_trace", None)
    if not isinstance(trace, dict):
        trace = getattr(context, "runtime_trace", None)
    trace_level = ""
    if isinstance(trace, dict):
        trace_level = str(trace.get("turn_load_level", "") or "")
    level = str(
        trace_level
        or _get_state_value(state, "turn_load_level", getattr(context, "turn_load_level", "standard"))
        or "standard"
    ).strip().lower()
    if level == "crisis":
        return "crisis"
    if level == "light":
        return "minimal"
    return "full"


def _resolve_next_step_policy(state, context) -> str:
    trace = _get_state_value(state, "runtime_trace", None)
    if not isinstance(trace, dict):
        trace = getattr(context, "runtime_trace", None)
    trace_policy = ""
    if isinstance(trace, dict):
        trace_policy = str(trace.get("next_step_policy", "") or "")
    policy = str(
        trace_policy
        or _get_state_value(state, "next_step_policy", getattr(context, "next_step_policy", "soft"))
        or "soft"
    ).strip().lower()
    return policy if policy in {"none", "soft", "explicit"} else "soft"


def _policy_closing_blocks(policy: str) -> list[str]:
    if policy == "none":
        return []
    if policy == "soft":
        return ["natural_end", "soft_continuation"]
    return ["natural_end", "soft_continuation", "explicit_next_step"]


def _split_visible_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?])", (text or "").strip())
    return [part.strip() for part in parts if part and part.strip()]


def _classify_closing_type(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "natural_end"
    explicit_markers = (
        "下一步",
        "接下来",
        "继续推进",
        "往前推",
        "先做",
        "先定",
        "你更想",
        "你愿意",
        "如果你愿意",
        "如果你愿意的话",
        "要不要",
        "我可以先",
        "你可以先",
        "先把",
        "先挑",
    )
    soft_markers = (
        "如果你愿意",
        "愿意的话",
        "可以先",
        "你可以先",
        "我们可以先",
        "先别急着",
        "先不用急着",
        "如果需要",
        "有需要的话",
        "先留",
        "轻轻",
    )
    if _has_explicit_order_markers(cleaned) or any(marker in cleaned for marker in explicit_markers):
        return "explicit_next_step"
    if any(marker in cleaned for marker in soft_markers) or cleaned.endswith(("？", "?")):
        return "soft_continuation"
    return "natural_end"


def _looks_like_question_first(text: str) -> bool:
    first = (text or "").strip()
    if not first:
        return False
    if "？" in first or "?" in first:
        return True
    question_starts = (
        "你之前",
        "你想",
        "你要",
        "你是不是",
        "是不是",
        "要不要",
        "能不能",
        "可不可以",
        "会不会",
        "怎么",
        "为什么",
        "如果",
        "那如果",
        "要是",
        "该怎么",
    )
    return any(first.startswith(marker) for marker in question_starts) and not any(
        marker in first for marker in ("可以先", "先给", "先做", "先说", "先回", "先落", "先定")
    )


def _starts_with_action_first(text: str) -> bool:
    first = (text or "").strip()
    if not first:
        return False
    first = re.sub(r"^[“\"'‘’\s]*(?:行|好|嗯|可以|那我|那就|我来|这样)[，,、\s]+", "", first)
    if _has_explicit_order_markers(first):
        return True
    action_starts = (
        "可以先",
        "先给",
        "先做",
        "先说",
        "先回",
        "先接",
        "先守",
        "先点",
        "先承接",
        "先把",
        "先定",
        "先挑",
        "先落",
        "先处理",
        "先确认",
        "我先给",
        "我先做",
        "我先说",
        "我先回",
        "我先接",
        "我先守",
        "我先点",
        "我先承接",
        "我先把",
        "我先定",
        "我直接给",
        "我直接回",
        "我直接说",
        "你可以这样说",
        "你可以这样回",
        "你可以先",
        "可以这样说",
        "可以这样回",
        "建议先",
        "我建议先",
        "我建议",
        "建议",
        "推荐先",
        "最好先",
        "先做这几步",
    )
    return any(first.startswith(marker) for marker in action_starts)


def _build_explicit_action_prefix(scene: str) -> str:
    prefix_map = {
        "sales": "可以先这样回：先承接对方顾虑，再把价值讲清。",
        "management": "可以先这样说：先点出事实，再约一个明确回看时间。",
        "negotiation": "可以先这样回：先守住底线，再给一个可谈区间。",
        "emotion": "可以先这样接：先承认当下感受，再留一句很轻的继续空间。",
    }
    return prefix_map.get(scene, "可以先这样做：先给一个默认动作。")


def _ensure_explicit_action_first(output: str, scene: str, next_step_policy: str) -> str:
    """explicit 先给动作，再补追问，避免开头先把球抛回去。"""
    if next_step_policy != "explicit":
        return output
    text = (output or "").strip()
    if not text:
        return text

    sentences = _split_visible_sentences(text)
    first_sentence = sentences[0] if sentences else text
    if _starts_with_action_first(first_sentence):
        return text

    prefix = _build_explicit_action_prefix(scene)
    if text.startswith(prefix):
        return text
    return f"{prefix}{text}"


def _apply_next_step_policy_gate(output: str, next_step_policy: str, scene: str = "") -> tuple[str, str, list[str], bool]:
    text = (output or "").strip()
    if not text:
        return text, "natural_end", _policy_closing_blocks(next_step_policy), False

    if next_step_policy == "explicit":
        sentences = _split_visible_sentences(text)
        first_sentence = sentences[0] if sentences else text
        if not _starts_with_action_first(first_sentence):
            prefix = _build_explicit_action_prefix(scene)
            if not text.startswith(prefix):
                text = f"{prefix}{text}"

    sentences = _split_visible_sentences(text)
    if not sentences:
        return text, "natural_end", _policy_closing_blocks(next_step_policy), False

    closing_start = len(sentences)
    for index in range(len(sentences) - 1, -1, -1):
        if _classify_closing_type(sentences[index]) == "natural_end":
            break
        closing_start = index

    body = sentences[:closing_start]
    tail = sentences[closing_start:]
    removed_blocks: list[str] = []
    dedup_applied = False

    if next_step_policy == "none":
        removed_blocks.extend(_classify_closing_type(item) for item in tail)
        final_sentences = body or [sentences[0]]
        if not body:
            removed_blocks.append("postprocess_closing_trim")
    elif next_step_policy == "soft":
        soft_tail = [item for item in tail if _classify_closing_type(item) == "soft_continuation"]
        explicit_tail = [item for item in tail if _classify_closing_type(item) == "explicit_next_step"]
        if explicit_tail:
            removed_blocks.extend(["explicit_next_step"] * len(explicit_tail))
        if len(soft_tail) > 1:
            removed_blocks.extend(["soft_continuation"] * (len(soft_tail) - 1))
            dedup_applied = True
        final_sentences = body + (soft_tail[-1:] if soft_tail else [])
        if not final_sentences:
            final_sentences = [sentences[0]]
            removed_blocks.append("postprocess_closing_trim")
    else:
        explicit_tail = [item for item in tail if _classify_closing_type(item) == "explicit_next_step"]
        soft_tail = [item for item in tail if _classify_closing_type(item) == "soft_continuation"]
        if len(explicit_tail) > 1:
            removed_blocks.extend(["explicit_next_step"] * (len(explicit_tail) - 1))
            dedup_applied = True
        if len(soft_tail) > 1:
            removed_blocks.extend(["soft_continuation"] * (len(soft_tail) - 1))
            dedup_applied = True
        if explicit_tail:
            final_sentences = body + [explicit_tail[-1]]
        elif soft_tail:
            final_sentences = body + [soft_tail[-1]]
        else:
            final_sentences = body
        if not final_sentences:
            final_sentences = [sentences[0]]
            removed_blocks.append("postprocess_closing_trim")

    final_output = "".join(final_sentences).strip()
    if next_step_policy == "none" and _classify_closing_type(final_output) != "natural_end":
        if any(marker in final_output for marker in ("是什么意思", "什么内容", "指的", "什么", "怎么理解")):
            final_output = "它大概是在说这里提到的这个内容。"
        elif "继续" in final_output:
            final_output = "好，我们继续。"
        else:
            final_output = re.sub(r"[？?]+$", "", final_output).rstrip("呢吗吧") + "。"
    final_closing_type = _classify_closing_type(final_output if final_output else (final_sentences[-1] if final_sentences else ""))
    if final_output != text and "postprocess_closing_trim" not in removed_blocks:
        removed_blocks.append("postprocess_closing_trim")
    return final_output, final_closing_type, removed_blocks, dedup_applied


def _finalize_closing_trace(
    state,
    context,
    *,
    step8_mode: str,
    next_step_policy: str,
    final_closing_type: str,
    closing_blocks_removed: list[str],
    closing_dedup_applied: bool,
) -> None:
    trace = _ensure_runtime_trace(state, context)
    trace["step8_mode"] = step8_mode
    trace["next_step_policy_applied"] = next_step_policy
    trace["closing_blocks_allowed"] = _policy_closing_blocks(next_step_policy)
    trace["closing_blocks_removed"] = closing_blocks_removed
    trace["final_closing_type"] = final_closing_type
    trace["closing_dedup_applied"] = closing_dedup_applied
    _set_state_value(state, context, "runtime_trace", trace)


def _build_minimal_user_state(context) -> dict:
    user = getattr(context, "user", None)
    emotion = getattr(user, "emotion", None)
    emotion_type = getattr(getattr(emotion, "type", None), "value", None)
    if not emotion_type:
        emotion_type = str(getattr(emotion, "type", "平静"))
    intensity = getattr(emotion, "intensity", 0.5)
    motive = str(getattr(user, "motive", "生活期待"))

    dominant_desire = "无"
    dominant_weight = 0
    desires = getattr(user, "desires", None)
    if desires and hasattr(desires, "get_dominant"):
        try:
            dominant_desire, dominant_weight = desires.get_dominant()
        except Exception:
            dominant_desire, dominant_weight = "无", 0

    dual_core = getattr(getattr(user, "dual_core", None), "state", None)
    dual_core_state = getattr(dual_core, "value", None) or str(dual_core or "同频")

    return {
        "emotion_type": emotion_type or "平静",
        "emotion_intensity": intensity,
        "motive": motive,
        "dominant_desire": dominant_desire,
        "dominant_weight": dominant_weight,
        "dual_core_state": dual_core_state,
        "relationship_position": getattr(user, "relationship_position", ""),
    }


def _estimate_full_prompt_chars(
    *,
    user_input: str,
    memory_context: str,
    knowledge_content: str,
    skill_prompt: str,
    secondary_scene_strategy: str,
    narrative_rules: str,
    guidance_prompt: str,
    scene: str,
    identity_hint: str,
    situation_hint: str,
    dialogue_task: str,
    layers_count: int,
    weapons_count: int,
) -> int:
    return 1800 + sum(
        len(part or "")
        for part in [
            user_input,
            memory_context,
            knowledge_content,
            skill_prompt,
            secondary_scene_strategy,
            narrative_rules,
            guidance_prompt,
            scene,
            identity_hint,
            situation_hint,
            dialogue_task,
        ]
    ) + layers_count * 120 + weapons_count * 30


def _run_step8_minimal_execution(state: GraphState, *, step8_mode: str) -> GraphState:
    context = state["context"]
    user_input = state["user_input"]
    scene = context.primary_scene or (context.scene_config.scene_id if context.scene_config else "")
    context_brief = _get_state_value(state, "context_brief", None)
    if not isinstance(context_brief, dict):
        context_brief = getattr(context, "context_brief", None)
    if not isinstance(context_brief, dict):
        context_brief = {
            "memory_brief": "",
            "world_state_brief": "",
            "next_pickup": "",
        }
    continuity_focus = _resolve_memory_continuity_focus(state, context)
    continuity_focus_used = _should_use_memory_continuity_focus(step8_mode, context, continuity_focus)
    next_step_policy = _resolve_next_step_policy(state, context)
    continuity_focus = _resolve_memory_continuity_focus(state, context)
    fallback_focus_applied = False

    from prompts.speech_generator import build_speech_prompt
    from llm.nvidia_client import invoke_fast
    from modules.L4.conversion_rules import convert_to_output
    from modules.L4.field_quality import quality_check

    system_prompt, user_prompt = build_speech_prompt(
        layers=[],
        user_state=_build_minimal_user_state(context),
        strategy_plan={"mode": "light", "stage": "", "description": ""},
        weapons_used=[],
        memory_context="",
        knowledge_content="",
        identity_hint=getattr(context, "identity_hint", ""),
        situation_hint=getattr(context, "situation_hint", ""),
        dialogue_task=getattr(context, "dialogue_task", "clarify"),
        scene=scene,
        user_input=user_input,
        minimal_mode=True,
        context_brief=context_brief,
        continuity_focus=continuity_focus if continuity_focus_used else None,
        next_step_policy=next_step_policy,
        step8_mode=step8_mode,
    )

    runtime_trace = _ensure_runtime_trace(state, context)
    try:
        raw_output = invoke_fast(
            user_prompt,
            system_prompt,
            runtime_trace=runtime_trace,
            stage="step8_minimal",
        )
    except Exception as exc:
        warning(f"Step8 轻量生成失败，改用 fallback: {exc}")
        raw_output = _fallback_generate_speech(
            layers=[{"layer": 1, "weapon": "共情"}, {"layer": 5, "weapon": "选择权引导"}],
            user_input=user_input,
            weapons_used=[],
            context=context,
            continuity_focus=continuity_focus if continuity_focus_used else None,
            next_step_policy=next_step_policy,
        )
        fallback_focus_applied = bool(continuity_focus_used)
        runtime_trace["output_path"] = "fallback"

    final_output, _ = convert_to_output(raw_output)
    final_output = _apply_memory_continuity_focus_to_output(
        final_output,
        continuity_focus if continuity_focus_used else {},
        user_input,
        next_step_policy,
    )
    final_output = _replace_academic_terms(final_output)
    final_output = _soften_internal_scaffolding(final_output)
    if step8_mode == "crisis" or _contains_crisis_intent(user_input):
        final_output = _apply_crisis_guard(final_output, user_input, scene)
    final_output = _ensure_explicit_action_first(final_output, scene, next_step_policy)
    final_output, final_closing_type, closing_blocks_removed, closing_dedup_applied = _apply_next_step_policy_gate(
        final_output,
        next_step_policy,
        scene,
    )
    final_output = _ensure_final_visible_output(final_output, user_input)
    qc_result = quality_check(final_output, context)
    if not qc_result.passed:
        for item in qc_result.failed_items:
            warning(f"质量检查失败: {item}")

    prompt_chars_estimate = len(system_prompt) + len(user_prompt)
    prompt_blocks = ["user_input", "context_brief", "next_step_policy", "minimal_style_rules", "safety_minimal"]
    if step8_mode == "crisis":
        prompt_blocks.append("crisis_support")
    memory_prompt_blocks = [
        {"block": "context_brief", "chars": _estimate_text_chars(context_brief)},
        {"block": "memory_brief", "chars": _estimate_text_chars(context_brief.get("memory_brief", ""))},
        {"block": "world_state_brief", "chars": _estimate_text_chars(context_brief.get("world_state_brief", ""))},
        {"block": "next_pickup", "chars": _estimate_text_chars(context_brief.get("next_pickup", ""))},
    ]
    if continuity_focus_used:
        memory_prompt_blocks.append({"block": "continuity_focus", "chars": _estimate_continuity_focus_chars(continuity_focus)})
    _record_memory_read_trace(
        context,
        stage="step8",
        source="context_brief_only",
        mode=step8_mode,
        chars=sum(block["chars"] for block in memory_prompt_blocks),
        count=1 if any(block["chars"] for block in memory_prompt_blocks) else 0,
        latency_ms=0.0,
        extra={"full_memory_loaded": False},
    )
    _set_memory_gate_decision(
        context,
        "step8",
        {
            "step8_mode": step8_mode,
            "full_memory_loaded": False,
            "reason": "minimal_uses_context_brief_only",
        },
    )
    _record_memory_prompt_blocks(context, memory_prompt_blocks)

    _finalize_closing_trace(
        state,
        context,
        step8_mode=step8_mode,
        next_step_policy=next_step_policy,
        final_closing_type=final_closing_type if final_output else "none",
        closing_blocks_removed=closing_blocks_removed,
        closing_dedup_applied=closing_dedup_applied,
    )
    trace = _ensure_runtime_trace(state, context)
    trace.setdefault("output_path", "llm" if not fallback_focus_applied else "fallback")
    trace["prompt_blocks"] = prompt_blocks
    trace["prompt_chars_estimate"] = prompt_chars_estimate
    trace["memory_continuity_focus_used"] = continuity_focus_used
    trace["memory_continuity_focus_type"] = str((continuity_focus or {}).get("focus_type", "none") or "none")
    trace["memory_continuity_focus_chars"] = _estimate_continuity_focus_chars(continuity_focus if continuity_focus_used else {})
    observed, observed_reason = _observe_memory_focus_usage(final_output, continuity_focus if continuity_focus_used else {})
    trace["memory_used_in_output_observed"] = observed
    trace["memory_used_in_output_reason"] = observed_reason
    trace["fallback_continuity_focus_used"] = fallback_focus_applied
    trace["fallback_continuity_focus_type"] = "none"
    trace["fallback_first_sentence_source"] = "generic"
    if fallback_focus_applied:
        trace["fallback_continuity_focus_used"] = True
        trace["fallback_continuity_focus_type"] = str((continuity_focus or {}).get("focus_type", "none") or "none")
        trace["fallback_first_sentence_source"] = trace["fallback_continuity_focus_type"]
        trace["memory_used_in_output_observed"] = "yes"
        trace["memory_used_in_output_reason"] = [_fallback_memory_focus_reason(continuity_focus)]
    _record_memory_constraint_trace(
        trace,
        final_output,
        continuity_focus if continuity_focus_used else {},
        position="early" if continuity_focus_used and not fallback_focus_applied else "none",
    )
    _set_state_value(state, context, "runtime_trace", trace)

    context.output = final_output
    output_layers = {
        "user_visible": final_output,
        "debug_info": f"模式={step8_mode} | 武器=[] | 场景={context.primary_scene}",
        "internal": f"轻量路径 | 上下文={getattr(context, 'context_brief', {})}",
        "order_source": f"minimal:{next_step_policy}",
        "failure_avoid_codes": [],
        "memory_hint_signals": {},
    }
    return {
        **state,
        "context": context,
        "output": final_output,
        "output_layers": output_layers,
    }


def step8_execution(state: GraphState) -> GraphState:
    """Step 8：执行转换与输出"""
    context = state["context"]
    user_input = state["user_input"]
    strategy_plan = state.get("strategy_plan")
    weapons_used = state.get("weapons_used", [])
    priority = state.get("priority", {})
    strategy_skeleton = state.get("strategy_skeleton", {}) or {}
    failure_avoid_codes = strategy_skeleton.get("failure_avoid_codes", []) if isinstance(strategy_skeleton, dict) else []
    next_step_policy = _resolve_next_step_policy(state, context)
    continuity_focus = _resolve_memory_continuity_focus(state, context)
    fallback_focus_applied = False

    # 快速路径：Step 0 已生成简化输出，仅做质量检查后返回
    if state.get("skip_to_end", False) and context.output:
        from modules.L4.conversion_rules import convert_to_output
        from modules.L4.field_quality import quality_check
        current_mode = context.self_state.energy_mode.value if hasattr(context.self_state.energy_mode, "value") else str(context.self_state.energy_mode)
        final_output = context.output
        final_output, _ = convert_to_output(final_output)
        scene = context.primary_scene or (context.scene_config.scene_id if context.scene_config else "")
        short_utterance = getattr(context, "short_utterance", False)
        template_scene = _resolve_template_scene(context, user_input, scene)
        preserve_output = _should_preserve_final_output(context, user_input, final_output)
        minimize_post = _should_minimize_post_processing(context, user_input)
        if not preserve_output:
            persona_ok, reason = _check_persona_consistency(final_output, context)
            if not persona_ok:
                final_output = _rewrite_for_persona(final_output, reason)
            if not minimize_post:
                final_output = _soften_internal_scaffolding(final_output)
                final_output = _soften_harsh_tone(final_output)
                if next_step_policy != "none":
                    final_output = _soften_ack_followup(final_output, user_input, scene, context)
                    if not _should_skip_scene_specific_repair(final_output, scene, context):
                        final_output = _apply_scene_specific_stabilizers(
                            final_output,
                            user_input,
                            scene,
                            context,
                            next_step_policy=next_step_policy,
                        )
                    final_before_order_patch = final_output
                    if next_step_policy == "explicit" and not _should_skip_skeleton_order_injection(final_output, user_input, scene, context):
                        final_output = _inject_skeleton_order_if_missing(final_output, user_input, context)
                    order_source = _resolve_order_source(user_input, final_before_order_patch, final_output)
                else:
                    final_before_order_patch = final_output
                    order_source = "policy_none"
                final_output = _soften_internal_scaffolding(final_output)
            else:
                if _should_apply_soft_repair(context, user_input, final_output):
                    final_output = _soften_harsh_tone(final_output)
                    if next_step_policy != "none":
                        final_output = _soften_ack_followup(final_output, user_input, scene, context)
                order_source = "minimized"
        else:
            order_source = "preserved"
        continuity_focus_used = _should_use_memory_continuity_focus("full", context, continuity_focus)
        final_output = _apply_memory_continuity_focus_to_output(
            final_output,
            continuity_focus if continuity_focus_used else {},
            user_input,
            next_step_policy,
        )
        final_output = _ensure_explicit_action_first(final_output, scene, next_step_policy)
        final_output, final_closing_type, closing_blocks_removed, closing_dedup_applied = _apply_next_step_policy_gate(
            final_output,
            next_step_policy,
            scene,
        )
        final_output = _ensure_final_visible_output(final_output, user_input)
        final_output = _apply_crisis_guard(final_output, user_input, scene)
        final_output = _enforce_minimum_response(final_output, scene, short_utterance)
        qc_result = quality_check(final_output, context)
        if not qc_result.passed:
            for item in qc_result.failed_items:
                warning(f"质量检查失败: {item}")
        _finalize_closing_trace(
            state,
            context,
            step8_mode=_resolve_step8_mode(state, context),
            next_step_policy=next_step_policy,
            final_closing_type=final_closing_type if final_output else "none",
            closing_blocks_removed=["skip_to_end"] + closing_blocks_removed,
            closing_dedup_applied=closing_dedup_applied,
        )
        runtime_trace = _ensure_runtime_trace(state, context)
        runtime_trace["prompt_blocks"] = ["skip_to_end", "quality_check", "minimal_cleanup"]
        runtime_trace["prompt_chars_estimate"] = len(final_output or "")
        observed, observed_reason = _observe_memory_focus_usage(final_output, continuity_focus if continuity_focus_used else {})
        runtime_trace["memory_continuity_focus_used"] = continuity_focus_used
        runtime_trace["memory_continuity_focus_type"] = str((continuity_focus or {}).get("focus_type", "none") or "none")
        runtime_trace["memory_continuity_focus_chars"] = _estimate_continuity_focus_chars(continuity_focus if continuity_focus_used else {})
        runtime_trace["memory_used_in_output_observed"] = observed
        runtime_trace["memory_used_in_output_reason"] = observed_reason
        runtime_trace["fallback_continuity_focus_used"] = continuity_focus_used
        runtime_trace["fallback_continuity_focus_type"] = (
            str((continuity_focus or {}).get("focus_type", "none") or "none")
            if continuity_focus_used else "none"
        )
        runtime_trace["fallback_first_sentence_source"] = (
            runtime_trace["fallback_continuity_focus_type"] if continuity_focus_used else "generic"
        )
        if continuity_focus_used:
            runtime_trace["memory_used_in_output_observed"] = "yes"
            runtime_trace["memory_used_in_output_reason"] = [_fallback_memory_focus_reason(continuity_focus)]
        _record_memory_constraint_trace(
            runtime_trace,
            final_output,
            continuity_focus if continuity_focus_used else {},
            position="none",
        )
        _set_state_value(state, context, "runtime_trace", runtime_trace)
        context.output = final_output
        output_layers = {
            "user_visible": final_output,
            "debug_info": f"模式={current_mode} | 武器={[w['name'] for w in weapons_used]} | 场景={context.primary_scene}",
            "internal": f"五感=快速路径无新增 | 压制={getattr(context, 'desire_relations', {})}",
            "order_source": order_source,
            "failure_avoid_codes": failure_avoid_codes,
            "memory_hint_signals": _build_memory_hint_signals(strategy_plan),
        }
        return {
            **state,
            "context": context,
            "output": final_output,
            "output_layers": output_layers,
        }

    step8_mode = _resolve_step8_mode(state, context)
    if step8_mode in {"crisis", "minimal"}:
        return _run_step8_minimal_execution(state, step8_mode=step8_mode)

    from modules.L4.five_layer_structure import generate_five_layer_output
    from modules.L4.conversion_rules import convert_to_output

    # 道次 1：生成五层结构骨架
    current_mode = strategy_plan.mode if strategy_plan else ""
    layers = generate_five_layer_output(
        user=context.user,
        strategy_weapons=[w["name"] for w in weapons_used],
        weapon_usage=context.weapon_usage_count,
        mode=current_mode,
        user_input=user_input,
        input_type=context.user.input_type.value if hasattr(context.user.input_type, "value") else str(context.user.input_type),
        scene=context.primary_scene or (context.scene_config.scene_id if context.scene_config else ""),
        identity_hint=getattr(context, "identity_hint", ""),
        situation_hint=getattr(context, "situation_hint", ""),
        guidance_needed=getattr(context, "guidance_needed", False),
        short_utterance=getattr(context, "short_utterance", False),
        goal_description=context.goal.current.description if context.goal and context.goal.current else "",
    )

    # 构建用户状态字典
    emotion_type_str = context.user.emotion.type.value if hasattr(context.user.emotion.type, 'value') else str(context.user.emotion.type)
    dominant, weight = context.user.desires.get_dominant()
    dual_core_str = context.user.dual_core.state.value if hasattr(context.user.dual_core.state, 'value') else str(context.user.dual_core.state)

    user_state = {
        "emotion_type": emotion_type_str,
        "emotion_intensity": context.user.emotion.intensity,
        "motive": str(context.user.motive),
        "dominant_desire": dominant,
        "dominant_weight": weight,
        "dual_core_state": dual_core_str,
        "relationship_position": getattr(context.user, "relationship_position", ""),
    }

    # 构建策略字典
    strategy_dict = {
        "mode": strategy_plan.mode if strategy_plan else "B",
        "stage": strategy_plan.stage if strategy_plan else "",
        "description": strategy_plan.description if strategy_plan else "",
    }

    # 道次 2：调用 LLM 生成话术
    # 【Phase 4】升维模式走专用 LLM prompt（维度识别 + 升维话术）
    bypass_llm = _should_bypass_llm_for_ordinary_turn(context, user_input)
    info(
        "Step8 route",
        response_mode=getattr(context, "response_mode", "ordinary"),
        bypass_llm=bypass_llm,
        short_utterance=bool(getattr(context, "short_utterance", False)),
        input_len=len((user_input or "").strip()),
    )
    step8_trace: dict[str, float] = {}
    generate_started = time.perf_counter()

    if bypass_llm:
        raw_output = _fallback_generate_speech(layers, user_input, weapons_used, context=context)
    elif (
        strategy_plan
        and strategy_plan.stage == "升维"
        and getattr(context, "response_mode", "ordinary") == "deep"
    ):
        try:
            from prompts.speech_generator import generate_upgrade_speech
            from modules.L2.dimension_recognition import get_emotion_dimensions

            emotion_type_str = context.user.emotion.type.value if hasattr(context.user.emotion.type, 'value') else str(context.user.emotion.type)

            # 使用 Step 1 中缓存的维度识别结果（避免重复调用）
            dim_result = getattr(context, "_dimension_result", None)
            if dim_result and dim_result.dominant_dimension:
                dimension = dim_result.dominant_dimension
            else:
                emotion_dims = get_emotion_dimensions(emotion_type_str)
                dimension = emotion_dims[0] if emotion_dims else "愿景"

            raw_output = generate_upgrade_speech(
                user_input=user_input,
                emotion_type=emotion_type_str,
                emotion_intensity=context.user.emotion.intensity,
                dimension=dimension,
                combo_name=strategy_plan.combo_name if strategy_plan else "愿景+尊严",
                combo_description=strategy_plan.description if strategy_plan else "",
                weapons_used=weapons_used,
            )
        except Exception as e:
            warning(f"升维 LLM 生成失败，使用 Fallback: {e}")
            raw_output = _generate_upgrade_speech(user_input, context)
    else:
        try:
            from prompts.speech_generator import generate_speech, generate_speech_fast
            from modules.L5.evidence_injector import detect_objection_type, generate_evidence
            import random
            # 【异议处理专项】仅销售场景注入证据，情感场景跳过
            evidence_content = ""
            scene_id = context.scene_config.scene_id if context.scene_config else ""
            if scene_id == "sales":
                objection_type = detect_objection_type(user_input)
                evidence_content = generate_evidence(objection_type)

            # 【Skills 系统】获取技能专属 Prompt
            skill_prompt = getattr(context, "skill_prompt", "")
            guidance_prompt = context.guidance_prompt if getattr(context, "guidance_needed", False) else ""
            strategy_skeleton_hint = _build_strategy_skeleton_hint(context)
            narrative_profile = {}

            # 【叙事驱动话术引擎】动态计算叙事约束
            scene = context.primary_scene or (context.scene_config.scene_id if context.scene_config else "")
            intensity = context.user.emotion.intensity
            trust = context.user.trust_level.value if hasattr(context.user.trust_level, "value") else str(context.user.trust_level)
            input_type = context.user.input_type
            input_type_str = input_type.value if hasattr(input_type, "value") else str(input_type)
            narrative_profile = _build_narrative_profile(
                user_input=user_input,
                input_type=input_type_str,
                emotion_intensity=intensity,
                scene=scene,
                identity_hint=getattr(context, "identity_hint", ""),
                situation_hint=getattr(context, "situation_hint", ""),
                strategy_stage=strategy_plan.stage if strategy_plan else "",
                layers=layers,
            )
            narrative_rules = ""

            if scene == "emotion":
                if intensity > 0.6 or trust == "low":
                    narrative_rules = "【叙事约束】用户情绪脆弱。仅允许使用'精准共鸣+复述痛点'。绝对禁止使用反差、悬念、说教或一次性给建议。结尾优先开放式承接，不要硬收成动作。"
                else:
                    narrative_rules = "【叙事约束】用户情绪平稳。允许使用'开放式提问+温和悬念'引导对话。禁止强反差和制造焦虑。结尾先保留呼吸感，别急着收死。"
            elif scene in ["sales", "negotiation"]:
                narrative_rules = "【叙事约束】允许使用'痛点共鸣+反差开场+悬念引导'。禁止过度共情和软弱妥协。开场必须直击痛点或反常识，结尾优先保留开放点；只有用户明确要推进时，再自然收成动作或选择。"
            elif scene == "management":
                narrative_rules = "【叙事约束】保持专业、直接。允许结构化悬念和认知反差。禁止情绪化表达和戏剧化反转。结尾先留一点余地，只有用户已经明确要推进时，再自然收成动作。"

            # 计算风格参数（情绪适配器）
            style_params = _adapt_output_style(input_type, context.user.emotion.intensity)
            output_profile = _build_output_profile(
                user_input=user_input,
                input_type=input_type_str,
                emotion_intensity=context.user.emotion.intensity,
                strategy_stage=strategy_plan.stage if strategy_plan else "",
                scene=scene,
            )

            # 【修复4】确定 forced_weapon_type 并传递给 LLM
            user_emotion = context.user.emotion.type.value if hasattr(context.user.emotion.type, "value") else str(context.user.emotion.type)
            forced_weapon_type = priority.get("forced_weapon_type")
            if user_emotion in ["愤怒", "急躁"] or context.user.desires.pride > 0.5:
                forced_weapon_type = "defensive"

            # 【修复4】质量门控重试机制（最多2次）
            DEFENSIVE_FORBIDDEN = ["机会", "错过", "抓紧", "翻倍", "赚", "稀缺", "最后", "限时", "紧迫", "窗口期"]
            DEFENSIVE_REPLACEMENTS = {
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
            DEFENSIVE_FALLBACKS = [
                "行，那你说说具体怎么回事。",
                "这件事我们换个角度看看。",
                "如果你愿意，我们可以先聚焦一个点。",
                "我们一步步来，先理清你最在意的是什么。",
                "你现在的感受我听到了。你想让我怎么回应？",
            ]

            raw_output = None
            retry_count = 0
            max_retries = 2
            fast_output_mode = _should_use_fast_speech_generation(context)

            while retry_count <= max_retries:
                step8_memory_extra: dict = {}
                if fast_output_mode:
                    memory_context = _build_light_memory_context(context)
                    step8_memory_extra = {
                        "full_memory_loaded": False,
                        "fast_output_mode": True,
                        "duplicate_with": "",
                    }
                    _record_memory_read_trace(
                        context,
                        stage="step8",
                        source="context_brief_only",
                        mode="full_fast",
                        chars=_estimate_text_chars(memory_context),
                        count=1 if memory_context else 0,
                        latency_ms=0.0,
                        extra=step8_memory_extra,
                    )
                    _set_memory_gate_decision(
                        context,
                        "step8",
                        {
                            "step8_mode": "full",
                            "full_memory_loaded": False,
                            "reason": "full_fast_uses_light_memory_context",
                        },
                    )
                else:
                    # 【阶段一优化】使用统一上下文（打通 5 套存储）
                    from modules.memory import get_memory_manager
                    step8_memory_started_at = time.perf_counter()
                    memory_context, memory_meta = get_memory_manager().get_unified_context(
                        user_id=context.session_id,
                        current_input=user_input,
                        context=context,
                        return_meta=True,
                    )
                    # Fallback: 如果统一上下文为空，使用旧的 long_term_memory
                    if not memory_context:
                        memory_context = context.long_term_memory
                        if context.session_notes_context:
                            memory_context = memory_context + "\n" + context.session_notes_context if memory_context else context.session_notes_context
                    context.unified_context = memory_context or context.unified_context
                    step8_memory_extra = {
                        "full_memory_loaded": True,
                        "fast_output_mode": False,
                        "duplicate_with": "step1:unified_context" if getattr(context, "turn_load_level", "") in {"standard", "deep"} else "",
                        "related_count": int(memory_meta.get("related_count", 0) or 0),
                        "recent_count": int(memory_meta.get("recent_count", 0) or 0),
                        "experience_digest_count": int(memory_meta.get("experience_digest_count", 0) or 0),
                        "session_note_count": int(memory_meta.get("session_note_count", 0) or 0),
                        "long_term_fallback_chars": _estimate_text_chars(context.long_term_memory),
                        "session_notes_fallback_chars": _estimate_text_chars(context.session_notes_context),
                    }
                    _record_memory_read_trace(
                        context,
                        stage="step8",
                        source="unified_context_full",
                        mode="full",
                        chars=int(memory_meta.get("unified_context_chars", 0) or _estimate_text_chars(memory_context)),
                        count=int(memory_meta.get("loaded_memory_count", 0) or 0),
                        latency_ms=(time.perf_counter() - step8_memory_started_at) * 1000,
                        extra=step8_memory_extra,
                    )
                    _set_memory_gate_decision(
                        context,
                        "step8",
                        {
                            "step8_mode": "full",
                            "full_memory_loaded": True,
                            "reason": "full_step8_memory_context",
                        },
                    )
                    trace_for_duplicate = _ensure_runtime_trace(state, context)
                    if step8_memory_extra.get("duplicate_with"):
                        trace_for_duplicate["memory_duplicate_detected"] = True
                        _set_state_value(state, context, "runtime_trace", trace_for_duplicate)

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
                    output_profile=output_profile,
                    narrative_profile=narrative_profile,
                    identity_hint=getattr(context, "identity_hint", ""),
                    situation_hint=getattr(context, "situation_hint", ""),
                    dialogue_task=getattr(context, "dialogue_task", "clarify"),
                    scene=scene,
                    user_input=user_input,
                    forced_weapon_type=forced_weapon_type,
                    evidence_content=evidence_content,
                    skill_prompt=skill_prompt,
                    secondary_scene_strategy=context.secondary_scene_strategy if hasattr(context, "secondary_scene_strategy") and context.secondary_scene_strategy else "",
                    narrative_rules=narrative_rules,
                    guidance_prompt=guidance_prompt,
                    continuity_focus=continuity_focus if _should_use_memory_continuity_focus("full", context, continuity_focus) else None,
                    next_step_policy=next_step_policy,
                    runtime_trace=_ensure_runtime_trace(state, context),
                    llm_stage="step8_full",
                )

                if fast_output_mode:
                    raw_output = _run_fast_speech_with_timeout(
                        timeout_seconds=8.0,
                        **speech_kwargs,
                    )
                else:
                    raw_output = generate_speech(**speech_kwargs)
                if _looks_like_stream_default_fallback(raw_output) and speech_kwargs.get("continuity_focus"):
                    raw_output = _fallback_generate_speech(
                        layers,
                        user_input,
                        weapons_used,
                        context=context,
                        continuity_focus=speech_kwargs.get("continuity_focus"),
                        next_step_policy=next_step_policy,
                    )
                    fallback_focus_applied = True
                    runtime_trace = _ensure_runtime_trace(state, context)
                    runtime_trace["output_path"] = "fallback"
                raw_output = _apply_memory_continuity_focus_to_output(
                    raw_output,
                    speech_kwargs.get("continuity_focus", {}) or {},
                    user_input,
                    next_step_policy,
                )

                runtime_trace = _ensure_runtime_trace(state, context)
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
                    "continuity_focus",
                    "postprocess",
                ]
                runtime_trace["prompt_chars_estimate"] = _estimate_full_prompt_chars(
                    user_input=user_input,
                    memory_context=speech_kwargs.get("memory_context", ""),
                    knowledge_content=speech_kwargs.get("knowledge_content", ""),
                    skill_prompt=speech_kwargs.get("skill_prompt", ""),
                    secondary_scene_strategy=speech_kwargs.get("secondary_scene_strategy", ""),
                    narrative_rules=speech_kwargs.get("narrative_rules", ""),
                    guidance_prompt=speech_kwargs.get("guidance_prompt", ""),
                    scene=scene,
                    identity_hint=getattr(context, "identity_hint", ""),
                    situation_hint=getattr(context, "situation_hint", ""),
                    dialogue_task=getattr(context, "dialogue_task", "clarify"),
                    layers_count=len(layers),
                    weapons_count=len(weapons_used),
                )
                _record_memory_prompt_blocks(
                    context,
                    [
                        {"block": "memory_context", "chars": _estimate_text_chars(speech_kwargs.get("memory_context", ""))},
                        {"block": "knowledge_content", "chars": _estimate_text_chars(speech_kwargs.get("knowledge_content", ""))},
                        {"block": "secondary_scene_strategy", "chars": _estimate_text_chars(speech_kwargs.get("secondary_scene_strategy", ""))},
                        {"block": "guidance_prompt", "chars": _estimate_text_chars(speech_kwargs.get("guidance_prompt", ""))},
                        {"block": "continuity_focus", "chars": _estimate_continuity_focus_chars(speech_kwargs.get("continuity_focus", {}))},
                    ],
                )
                observed, observed_reason = _observe_memory_focus_usage(
                    raw_output,
                    speech_kwargs.get("continuity_focus", {}) or {},
                )
                runtime_trace["memory_continuity_focus_used"] = bool(speech_kwargs.get("continuity_focus"))
                runtime_trace["memory_continuity_focus_type"] = str(((speech_kwargs.get("continuity_focus") or {}).get("focus_type", "none")) or "none")
                runtime_trace["memory_continuity_focus_chars"] = _estimate_continuity_focus_chars(speech_kwargs.get("continuity_focus", {}))
                runtime_trace["memory_used_in_output_observed"] = observed
                runtime_trace["memory_used_in_output_reason"] = observed_reason
                runtime_trace["fallback_continuity_focus_used"] = fallback_focus_applied
                runtime_trace["fallback_continuity_focus_type"] = (
                    str(((speech_kwargs.get("continuity_focus") or {}).get("focus_type", "none")) or "none")
                    if fallback_focus_applied else "none"
                )
                runtime_trace["fallback_first_sentence_source"] = (
                    runtime_trace["fallback_continuity_focus_type"] if fallback_focus_applied else "generic"
                )
                if fallback_focus_applied:
                    runtime_trace["memory_used_in_output_observed"] = "yes"
                    runtime_trace["memory_used_in_output_reason"] = [_fallback_memory_focus_reason(speech_kwargs.get("continuity_focus", {}) or {})]
                _record_memory_constraint_trace(
                    runtime_trace,
                    raw_output,
                    speech_kwargs.get("continuity_focus", {}) or {},
                    position="early" if speech_kwargs.get("continuity_focus") and not fallback_focus_applied else "none",
                )
                _set_state_value(state, context, "runtime_trace", runtime_trace)

                # 【修复4B+C】智能替换 + 质量门控
                if fast_output_mode:
                    break
                if forced_weapon_type == "defensive":
                    # 智能替换（避免空洞）
                    for word, replacement in DEFENSIVE_REPLACEMENTS.items():
                        raw_output = raw_output.replace(word, replacement)

                    # 检查是否仍包含禁止词
                    if any(w in raw_output for w in DEFENSIVE_FORBIDDEN):
                        retry_count += 1
                        if retry_count > max_retries:
                            # 2次重试后仍失败，使用 fallback
                            raw_output = random.choice(DEFENSIVE_FALLBACKS)
                        continue
                    else:
                        # 通过质量门控
                        break
                else:
                    # 非防御模式，无需检查
                    break

        except Exception as e:
            import traceback
            error_detail = traceback.format_exc()
            warning(f"LLM 话术生成失败，使用 Fallback: {e}")
            print(f"详细错误:\n{error_detail}")
            # Fallback：使用硬编码模板
            raw_output = _fallback_generate_speech(
                layers,
                user_input,
                weapons_used,
                context=context,
                continuity_focus=continuity_focus if _should_use_memory_continuity_focus("full", context, continuity_focus) else None,
                next_step_policy=next_step_policy,
            )
            fallback_focus_applied = bool(_should_use_memory_continuity_focus("full", context, continuity_focus))
            runtime_trace = _ensure_runtime_trace(state, context)
            runtime_trace["output_path"] = "fallback"
    step8_trace["generate"] = round(time.perf_counter() - generate_started, 3)

    runtime_trace = _ensure_runtime_trace(state, context)
    runtime_trace.setdefault("step8_mode", "full")
    runtime_trace.setdefault("output_path", "llm" if not fallback_focus_applied else "fallback")
    continuity_focus_used_final = _should_use_memory_continuity_focus("full", context, continuity_focus)
    continuity_focus_final = continuity_focus if continuity_focus_used_final else {}
    observed, observed_reason = _observe_memory_focus_usage(final_output, continuity_focus_final)
    runtime_trace["memory_continuity_focus_used"] = continuity_focus_used_final
    runtime_trace["memory_continuity_focus_type"] = str((continuity_focus_final or {}).get("focus_type", "none") or "none")
    runtime_trace["memory_continuity_focus_chars"] = _estimate_continuity_focus_chars(continuity_focus_final)
    runtime_trace["memory_used_in_output_observed"] = observed
    runtime_trace["memory_used_in_output_reason"] = observed_reason
    runtime_trace["fallback_continuity_focus_used"] = bool(fallback_focus_applied)
    runtime_trace["fallback_continuity_focus_type"] = (
        str((continuity_focus_final or {}).get("focus_type", "none") or "none")
        if runtime_trace["fallback_continuity_focus_used"] else "none"
    )
    runtime_trace["fallback_first_sentence_source"] = (
        runtime_trace["fallback_continuity_focus_type"]
        if runtime_trace["fallback_continuity_focus_used"] else "generic"
    )
    if runtime_trace["fallback_continuity_focus_used"]:
        runtime_trace["memory_used_in_output_observed"] = "yes"
        runtime_trace["memory_used_in_output_reason"] = [_fallback_memory_focus_reason(continuity_focus_final)]
    _record_memory_constraint_trace(
        runtime_trace,
        final_output,
        continuity_focus_final,
        position="early" if continuity_focus_used_final and not runtime_trace["fallback_continuity_focus_used"] else "none",
    )
    if not runtime_trace.get("prompt_blocks"):
        current_scene = context.primary_scene or (context.scene_config.scene_id if context.scene_config else "")
        if bypass_llm:
            runtime_trace["prompt_blocks"] = ["user_input", "fallback_generation", "postprocess"]
            runtime_trace["prompt_chars_estimate"] = len(user_input or "") + 800
        elif (
            strategy_plan
            and strategy_plan.stage == "升维"
            and getattr(context, "response_mode", "ordinary") == "deep"
        ):
            runtime_trace["prompt_blocks"] = ["user_input", "upgrade_prompt", "postprocess"]
            runtime_trace["prompt_chars_estimate"] = len(user_input or "") + len(getattr(strategy_plan, "description", "") or "") + 700
        else:
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
            runtime_trace["prompt_chars_estimate"] = _estimate_full_prompt_chars(
                user_input=user_input,
                memory_context=str(locals().get("memory_context", "") or ""),
                knowledge_content=str(locals().get("knowledge_content", "") or ""),
                skill_prompt=str(locals().get("skill_prompt", "") or ""),
                secondary_scene_strategy=str(locals().get("secondary_scene_strategy", "") or ""),
                narrative_rules=str(locals().get("narrative_rules", "") or ""),
                guidance_prompt=str(locals().get("guidance_prompt", "") or ""),
                scene=current_scene,
                identity_hint=getattr(context, "identity_hint", ""),
                situation_hint=getattr(context, "situation_hint", ""),
                dialogue_task=getattr(context, "dialogue_task", "clarify"),
                layers_count=len(locals().get("layers", []) or []),
                weapons_count=len(weapons_used),
            )
        _set_state_value(state, context, "runtime_trace", runtime_trace)

    if "raw_output" not in locals() or not raw_output:
        raw_output = _fallback_generate_speech(
            layers,
            user_input,
            weapons_used,
            context=context,
            continuity_focus=continuity_focus if _should_use_memory_continuity_focus("full", context, continuity_focus) else None,
            next_step_policy=next_step_policy,
        )
    if "narrative_profile" not in locals():
        narrative_profile = {}

    # 道次 3：禁用词汇替换 + 框架泄露检查
    convert_started = time.perf_counter()
    final_output, passed = convert_to_output(raw_output)

    # 道次 3.5：术语替换（独立执行，不管长度）
    final_output = _replace_academic_terms(final_output)
    final_output = _soften_internal_scaffolding(final_output)
    final_output = _guard_optional_product_extension_output(
        final_output,
        user_input=user_input,
        skill_prompt=getattr(context, "skill_prompt", ""),
    )
    step8_trace["convert_clean"] = round(time.perf_counter() - convert_started, 3)

    # 道次 4：话痨拦截器（智能压缩）
    profile_started = time.perf_counter()
    input_type = context.user.input_type.value if hasattr(context.user.input_type, "value") else str(context.user.input_type)
    scene = context.primary_scene or (context.scene_config.scene_id if context.scene_config else "")
    output_profile = _build_output_profile(
        user_input=user_input,
        input_type=input_type,
        emotion_intensity=context.user.emotion.intensity,
        strategy_stage=strategy_plan.stage if strategy_plan else "",
        scene=scene,
    )
    
    # 方向A-3: 情境阶段感知输出节奏
    situation_stage = getattr(context, "situation_stage", "未识别")
    if situation_stage == "破冰":
        # 破冰：短轻，不超过150字
        output_profile["max_chars"] = min(output_profile.get("max_chars", 300), 150)
    elif situation_stage == "修复":
        # 修复：慢稳，允许稍长但节奏要缓
        output_profile["max_chars"] = min(output_profile.get("max_chars", 300), 200)
    elif situation_stage == "推进":
        # 推进：切重点，可以稍长
        output_profile["max_chars"] = max(output_profile.get("max_chars", 200), 250)
    elif situation_stage == "僵持":
        # 僵持：换角度，短且不同
        output_profile["max_chars"] = min(output_profile.get("max_chars", 300), 180)
    
    # 定向优化: 疲惫型极短输出+资源保护
    emotion_type = str(context.user.emotion.type.value) if hasattr(context.user.emotion.type, "value") else str(context.user.emotion.type)
    if emotion_type in ["疲惫", "挫败"]:
        output_profile["max_chars"] = min(output_profile.get("max_chars", 300), 120)
        output_profile["tone"] = "极简温和"
    
    if len(final_output) > output_profile["max_chars"]:
        final_output = _smart_compress(final_output, max_length=output_profile["max_chars"])
    final_output = _trim_to_output_profile(final_output, output_profile)
    final_output = _shape_output_rhythm(final_output, output_profile, narrative_profile)
    final_output = _trim_to_output_profile(final_output, output_profile)
    step8_trace["profile_trim"] = round(time.perf_counter() - profile_started, 3)

    # 道次 5：人设一致性检查（规则版）
    finalize_started = time.perf_counter()
    scene = context.primary_scene or (context.scene_config.scene_id if context.scene_config else "")
    short_utterance = getattr(context, "short_utterance", False)
    template_scene = _resolve_template_scene(context, user_input, scene)
    preserve_output = _should_preserve_final_output(context, user_input, final_output)
    minimize_post = _should_minimize_post_processing(context, user_input)
    if not preserve_output:
        persona_ok, reason = _check_persona_consistency(final_output, context)
        if not persona_ok:
            # 人设不一致，尝试重写
            final_output = _rewrite_for_persona(final_output, reason)
        if not minimize_post:
            final_output = _soften_harsh_tone(final_output)
            final_output = _soften_ack_followup(final_output, user_input, scene, context)
            if not _should_skip_scene_specific_repair(final_output, scene, context):
                final_output = _apply_scene_specific_stabilizers(final_output, user_input, scene, context)
            final_before_order_patch = final_output
            if not _should_skip_skeleton_order_injection(final_output, user_input, scene, context):
                final_output = _inject_skeleton_order_if_missing(final_output, user_input, context)
            order_source = _resolve_order_source(user_input, final_before_order_patch, final_output)
            final_output = _soften_internal_scaffolding(final_output)
        else:
            if _should_apply_soft_repair(context, user_input, final_output):
                final_output = _soften_harsh_tone(final_output)
                final_output = _soften_ack_followup(final_output, user_input, scene, context)
            order_source = "minimized"
    else:
        order_source = "preserved"
    final_output = _ensure_final_visible_output(final_output, user_input)
    final_output = _apply_crisis_guard(final_output, user_input, scene)
    final_output = _enforce_minimum_response(final_output, scene, short_utterance)
    step8_trace["repair_finalize"] = round(time.perf_counter() - finalize_started, 3)

    # 道次 5.5：场域判断与质量检查（新增）
    from modules.L4.field_quality import quality_check, assess_field
    qc_result = quality_check(final_output, context)
    if not qc_result.passed:
        # 记录警告但不阻断输出（避免无限循环）
        for item in qc_result.failed_items:
            warning(f"质量检查失败: {item}")

    # 道次 5.6：五感施加检查（可选）
    field_assessment = assess_field(context=context, strategy_plan=strategy_plan)
    if field_assessment.can_apply_field:
        # 线下场景且有控制权 → 内部记录环境布置建议，但不直接展示给用户
        from modules.L4.sensory_application import apply_sensory_strategy
        sensory_actions = apply_sensory_strategy(
            context=context,
            goal=strategy_plan.description if strategy_plan else "",
        )
        if sensory_actions:
            if context.history:
                context.history[-1].metadata["sensory_actions"] = [
                    {"sense": a.sense, "method": a.method} for a in sensory_actions
                ]

    # 道次 5.7：五感自我执行/自我调节（用户进入线下场景或需要情绪调节时）
    from modules.L4.sensory_application import (
        detect_scenario_intent, detect_regulation_need,
        generate_scenario_guide, generate_regulation_guide,
        format_scenario_guide, format_regulation_guide,
    )

    sensory_guide_text = ""

    # 优先级1：用户主动要求更细致的指导
    user_wants_detail = any(kw in user_input for kw in ["细致", "具体怎么做", "操作步骤", "更细", "详细指导", "身体怎么做", "怎么动"])
    # 优先级2：系统识别到线下场景意图
    scenario_match = detect_scenario_intent(user_input)
    # 优先级3：情绪需要自我调节
    emotion_type_str = context.user.emotion.type.value if hasattr(context.user.emotion.type, 'value') else str(context.user.emotion.type)
    regulation_need = detect_regulation_need(emotion_type_str, context.user.emotion.intensity, user_input)

    emotion_sub_intent = _get_emotion_sub_intent(context, user_input, scene)

    # 不触发的条件：纯线上问题、信息缺口还很大、情绪宣泄型不需要方案
    skip_sensory = (
        context.guidance_needed or  # 信息不足该先补问
        context.short_utterance     # 短承接不需要展开
    )

    if not skip_sensory:
        # 场景指导（自我执行视角）
        if scenario_match and (user_wants_detail or context.user.emotion.intensity >= 0.5):
            guide = generate_scenario_guide(scenario_match, emotion_type_str, context.user.emotion.intensity)
            if guide:
                sensory_guide_text = format_scenario_guide(guide)
        # 调节指导（自我调节视角）——只在情绪场景里开放，避免 sales / negotiation 被情绪工具段污染
        if (
            not sensory_guide_text
            and regulation_need
            and context.user.emotion.intensity >= 0.55
            and scene == "emotion"
            and getattr(context, "identity_hint", "") != "关系沟通"
            and (user_wants_detail or emotion_sub_intent not in {"failure_containment", "low_energy_support", "accusation_repair"})
        ):
            reg_guide = generate_regulation_guide(regulation_need)
            if reg_guide:
                sensory_guide_text = format_regulation_guide(reg_guide)

    # 将五感指导追加到输出末尾
    if sensory_guide_text:
        final_output = final_output.rstrip() + "\n\n" + sensory_guide_text
        # 五感指导是后追加内容，需要再过一次术语清洗，避免内部词回流到用户侧。
        final_output, _ = convert_to_output(final_output)
        final_output = _replace_academic_terms(final_output)
        final_output = _soften_internal_scaffolding(final_output)
    step8_trace["sensory_tail"] = round(
        max(0.0, time.perf_counter() - generate_started - sum(step8_trace.values())),
        3,
    )
    final_output = _ensure_explicit_action_first(final_output, context.primary_scene or (context.scene_config.scene_id if context.scene_config else ""), next_step_policy)
    final_output, final_closing_type, closing_blocks_removed, closing_dedup_applied = _apply_next_step_policy_gate(
        final_output,
        next_step_policy,
        context.primary_scene or (context.scene_config.scene_id if context.scene_config else ""),
    )
    final_output = _ensure_final_visible_output(final_output, user_input)
    _finalize_closing_trace(
        state,
        context,
        step8_mode="full",
        next_step_policy=next_step_policy,
        final_closing_type=final_closing_type if final_output else "none",
        closing_blocks_removed=closing_blocks_removed,
        closing_dedup_applied=closing_dedup_applied,
    )
    info("Step8 trace", trace=step8_trace, response_mode=getattr(context, "response_mode", "ordinary"))

    # 更新 context
    context.output = final_output

    # P0-2: 输出显式分层标记 — 记录用户可见/调试/内部三层
    output_layers = {
        "user_visible": final_output,
        "debug_info": f"模式={current_mode} | 武器={[w['name'] for w in weapons_used]} | 场景={context.primary_scene}",
        "internal": f"五感={sensory_guide_text[:80] if sensory_guide_text else '无'} | 压制={getattr(context, 'desire_relations', {})}",
        "order_source": order_source,
        "failure_avoid_codes": failure_avoid_codes,
        "memory_hint_signals": _build_memory_hint_signals(strategy_plan),
    }
    # Step 9 才会写入 system 历史，这里先挂到 state 里，避免写错到 user 历史

    # 更新武器使用计数（仅在此处统一计数一次，基于 Step 7 的选择）
    for w in weapons_used:
        context.increment_weapon(w["name"])

    return {
        **state,
        "context": context,
        "output": final_output,
        "output_layers": output_layers,
    }
