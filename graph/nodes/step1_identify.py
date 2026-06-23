"""
Human-OS Engine - LangGraph 节点实现

对应总控规格的 Step 0-9。
"""

import time

from graph.state import GraphState
from graph.nodes.step0_input import (
    _estimate_text_chars,
    _record_memory_read_trace,
    _record_memory_read_reuse_trace,
    _record_memory_skip_reason,
    _set_memory_gate_decision,
    _set_memory_stats,
)


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _set_runtime_field(context, name: str, value):
    """给 Pydantic Context 挂运行时字段，不改 schema。"""
    object.__setattr__(context, name, value)


def _resolve_turn_load_level(context, user_input: str) -> str:
    """优先使用 Step0 已标记的负载等级，没标记时才回退到旧逻辑。"""
    level = getattr(context, "turn_load_level", "") or ""
    if level in {"crisis", "light", "standard", "deep"}:
        return level

    text = (user_input or "").strip()
    if not text:
        return "light"

    crisis_markers = ("不想活了", "想死", "撑不下去了", "自杀", "伤害自己", "现实危险", "违法", "高风险")
    deep_markers = ("全面审计", "系统审计", "代码修复", "全面扫描", "完整报告", "架构重构", "长文档", "深度分析", "复盘", "方案", "修复计划")
    if any(marker in text for marker in crisis_markers):
        return "crisis"
    if any(marker in text for marker in deep_markers):
        return "deep"

    has_question = any(ch in text for ch in "？?")
    has_action = any(token in text for token in ("怎么办", "怎么做", "怎么说", "如何", "怎么推进", "怎么回", "怎么处理", "下一步", "方案", "计划", "安排", "分析"))
    has_context_anchor = any(token in text for token in ("老板", "项目", "客户", "团队", "关系", "沟通", "结果", "工资", "涨薪", "合作"))
    has_emotion = any(token in text for token in ("烦", "累", "委屈", "难受", "焦虑", "压力", "生气", "郁闷", "怕", "慌", "撑不住"))

    if has_question and not has_action and not has_context_anchor and not has_emotion and len(text) <= 12:
        return "light"
    if has_question and (has_context_anchor or has_action) and len(text) <= 28:
        return "standard"
    if has_action and (has_context_anchor or len(text) >= 10) and len(text) <= 28:
        return "standard"

    from graph.nodes.helpers import _turn_load_level as _legacy_turn_load_level

    scene = getattr(context, "primary_scene", "") or getattr(getattr(context, "scene_config", None), "scene_id", "")
    legacy = _legacy_turn_load_level(context, user_input, scene)
    if legacy == "heavy":
        return "deep"
    if legacy == "medium":
        return "standard"
    return "light"


def _build_world_state_brief(context) -> str:
    """把世界状态压成一句轻量摘要，供后续 Step 使用。"""
    parts: list[str] = []
    scene = getattr(context, "primary_scene", "") or getattr(getattr(context, "scene_config", None), "scene_id", "")
    if scene and scene != "未识别":
        parts.append(f"场景: {scene}")

    world_state = getattr(context, "world_state", None)
    if world_state:
        action_loop_state = getattr(world_state, "action_loop_state", "")
        if action_loop_state:
            for token in ["局面:", "压力:", "判断:", "方向:", "建议:", "风险:", "下一步:", "避免:"]:
                idx = str(action_loop_state).find(token)
                if idx >= 0:
                    excerpt = str(action_loop_state)[idx:idx + 120]
                    parts.append(excerpt)
        for label, attr in [
            ("关系", "relationship_position"),
            ("阶段", "situation_stage"),
            ("信任", "trust_level"),
            ("张力", "tension_level"),
            ("风险", "risk_level"),
            ("推进", "progress_state"),
            ("承诺", "commitment_state"),
            ("下一步焦点", "next_turn_focus"),
        ]:
            value = getattr(world_state, attr, "")
            if value and value != "未识别":
                parts.append(f"{label}: {value}")

    if not parts:
        relationship = getattr(getattr(context, "user", None), "relationship_position", "")
        if relationship:
            parts.append(f"关系: {relationship}")

    return " | ".join(parts[:6])


def _build_next_pickup(context, session_brief: str) -> str:
    """给后续步骤保留一个极短的承接点。"""
    world_state = getattr(context, "world_state", None)
    if world_state:
        next_focus = getattr(world_state, "next_turn_focus", "")
        if next_focus:
            return str(next_focus)[:120]
        recommended_answer = getattr(world_state, "recommended_answer", "")
        if recommended_answer:
            return str(recommended_answer)[:120]
        action_loop_state = getattr(world_state, "action_loop_state", "")
        if action_loop_state and any(token in str(action_loop_state) for token in ["判断:", "建议:", "下一步:"]):
            return str(action_loop_state)[:120]

    dialogue_frame = getattr(context, "dialogue_frame", None)
    if dialogue_frame:
        answer_contract = getattr(dialogue_frame, "answer_contract", "")
        if answer_contract:
            return str(answer_contract)[:120]

    if session_brief:
        for raw_line in reversed(session_brief.splitlines()):
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("【"):
                continue
            if line.startswith("-") or line.startswith("  -"):
                return line.lstrip("- ").strip()[:120]
            return line[:120]

    return ""


def _build_context_brief(
    context,
    memory_mode: str,
    memory_brief: str,
    loaded_memory_count: int,
    unified_context_loaded: bool,
    memory_sources: list[str] | None = None,
    session_brief: str = "",
) -> dict:
    return {
        "memory_brief": memory_brief or "",
        "world_state_brief": _build_world_state_brief(context),
        "next_pickup": _build_next_pickup(context, session_brief or ""),
        "loaded_memory_count": max(0, int(loaded_memory_count or 0)),
        "memory_mode": memory_mode,
        "memory_sources": memory_sources or [],
        "unified_context_loaded": bool(unified_context_loaded),
    }


def _pick_first_hint(text: str, candidates: list[str]) -> str:
    source = str(text or "")
    for candidate in candidates:
        if candidate and candidate in source:
            return candidate
    return ""


def _compact_hint(text: str, limit: int = 80) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    value = value.replace("\r", " ").replace("\n", " ").strip()
    return value[:limit]


def _normalize_focus_source_text(text: str, limit: int = 90) -> str:
    value = _compact_hint(text, limit * 2)
    if not value:
        return ""
    cleanup_rules = [
        ("用户开启了一个需要理清的议题：", ""),
        ("用户开启了一个需要给做法的议题：", ""),
        ("用户开启了一个需要先接住的议题：", ""),
        ("用户开启了一个需要推进的议题：", ""),
        ("用户开启了一个议题：", ""),
        ("先确认他真正想解决什么。", ""),
        ("先回答问题，再给可执行下一步。", ""),
        ("先回应感受，再轻轻", ""),
        ("先回应感受，再", ""),
        ("先把问题摊开。", ""),
    ]
    for old, new in cleanup_rules:
        value = value.replace(old, new)
    value = value.strip("。；;，, ")
    if "。。" in value:
        value = value.replace("。。", "。")
    if "：" in value and len(value.split("：", 1)[-1]) >= 4:
        value = value.split("：", 1)[-1]
    if "。" in value:
        value = value.split("。", 1)[0]
    return _compact_hint(value, limit)


def _looks_like_generic_focus(text: str) -> bool:
    value = _compact_hint(text, 120)
    if not value:
        return True
    generic_markers = [
        "继续承接上一轮",
        "用户有情绪",
        "需要帮助",
        "处理问题",
        "先确认他真正想解决什么",
        "先回答问题",
        "先回应感受",
        "观察中",
        "未形成",
        "理清这个问题",
    ]
    if len(value) <= 6:
        return True
    return any(marker in value for marker in generic_markers)


def _current_turn_depends_on_context(user_input: str) -> bool:
    text = _compact_hint(user_input, 80)
    if not text:
        return False
    markers = [
        "那我",
        "那如果",
        "如果他",
        "如果对方",
        "这句",
        "这话",
        "还是",
        "接下来",
        "下一步",
        "怎么安排",
        "先批评还是先问情况",
        "守价格还是让一点",
    ]
    return any(marker in text for marker in markers)


def _build_focus_payload(
    *,
    focus_type: str,
    anchor: str,
    decision_bias: str,
    must_use_points: list[str],
    avoid: list[str],
    output_instruction: str,
    next_pickup: str = "",
    world_state_hint: str = "",
    relationship_hint: str = "",
    decision_question: str = "",
    recommended_answer: str = "",
    risk_if_wrong: str = "",
    next_action: str = "",
    first_sentence_bias: str = "",
    source_fields: list[str] | None = None,
) -> dict:
    clean_points = [_compact_hint(point, 30) for point in must_use_points if _compact_hint(point, 30)]
    clean_avoid = [_compact_hint(point, 30) for point in avoid if _compact_hint(point, 30)]
    return {
        "memory_use_required": True,
        "focus_type": focus_type,
        "anchor": _compact_hint(anchor, 70),
        "decision_bias": _compact_hint(decision_bias, 90),
        "must_use_points": clean_points[:4],
        "avoid": clean_avoid[:4],
        "next_pickup": _compact_hint(next_pickup, 70),
        "world_state_hint": _compact_hint(world_state_hint, 90),
        "relationship_hint": _compact_hint(relationship_hint, 90),
        "output_instruction": _compact_hint(output_instruction, 100),
        "decision_question": _compact_hint(decision_question, 80),
        "recommended_answer": _compact_hint(recommended_answer, 90),
        "risk_if_wrong": _compact_hint(risk_if_wrong, 90),
        "next_action": _compact_hint(next_action, 90),
        "first_sentence_bias": _compact_hint(first_sentence_bias, 100),
        "source_fields": list(dict.fromkeys(source_fields or [])),
        "quality_score": 0,
        "disabled_reason": [],
    }


def _score_memory_focus(focus: dict) -> int:
    if not isinstance(focus, dict) or not focus.get("memory_use_required"):
        return 0
    anchor = str(focus.get("anchor", "") or "")
    decision_bias = str(focus.get("decision_bias", "") or "")
    recommended_answer = str(focus.get("recommended_answer", "") or "")
    risk_if_wrong = str(focus.get("risk_if_wrong", "") or "")
    next_action = str(focus.get("next_action", "") or "")
    must_use_points = [item for item in (focus.get("must_use_points") or []) if str(item or "").strip()]
    avoid = [item for item in (focus.get("avoid") or []) if str(item or "").strip()]
    score = 1
    if anchor and not _looks_like_generic_focus(anchor):
        score = max(score, 3)
    if decision_bias or recommended_answer:
        score += 1
    if must_use_points:
        score += 1
    if avoid:
        score += 1
    if risk_if_wrong:
        score += 1
    if next_action:
        score += 1
    return max(0, min(score, 5))


def _build_memory_continuity_focus(context, user_input: str, context_brief: dict) -> dict:
    route_state = getattr(context, "route_state", None) or {}
    if not isinstance(route_state, dict):
        route_state = {}
    policy_state = route_state.get("policy_state", {})
    if not isinstance(policy_state, dict):
        policy_state = {}

    previous_focus = getattr(context, "memory_continuity_focus", None)
    if not isinstance(previous_focus, dict):
        previous_focus = {}

    memory_brief = _normalize_focus_source_text(context_brief.get("memory_brief", ""), 120)
    world_state_brief = _normalize_focus_source_text(context_brief.get("world_state_brief", ""), 120)
    next_pickup = _normalize_focus_source_text(context_brief.get("next_pickup", ""), 120)
    conversation_phase = str(route_state.get("conversation_phase", "") or "")
    previous_scene = str(route_state.get("previous_scene", "") or "")
    main_scene = str(route_state.get("main_scene", "") or "")
    should_inherit_scene = bool(route_state.get("should_inherit_scene", False))
    risk_level = str(route_state.get("risk_level", "") or "")
    current_input = _compact_hint(user_input, 90)
    raw_text = " | ".join(part for part in [memory_brief, world_state_brief, next_pickup, current_input] if part)
    source_fields: list[str] = []
    disabled_reason: list[str] = []
    current_turn_depends = _current_turn_depends_on_context(user_input)

    focus = {
        "memory_use_required": False,
        "focus_type": "none",
        "anchor": "",
        "decision_bias": "",
        "must_use_points": [],
        "avoid": [],
        "next_pickup": next_pickup,
        "world_state_hint": world_state_brief,
        "relationship_hint": "",
        "output_instruction": "",
        "source_fields": [],
        "quality_score": 0,
        "disabled_reason": [],
    }

    preference_anchor = _pick_first_hint(
        raw_text,
        ["直接一点", "先给结论", "不要绕", "少铺垫", "直接说重点"],
    )
    if not preference_anchor and str(previous_focus.get("focus_type", "") or "") == "preference":
        if any(token in current_input for token in ["建议", "分析", "怎么回", "怎么说", "怎么做"]):
            preference_anchor = str(previous_focus.get("anchor", "") or "直接一点")
            source_fields.extend(["previous_focus", "user_input"])
    if preference_anchor:
        preference_instruction = "本轮第一句必须先给明确结论。"
        if any(token in current_input for token in ["分析", "建议"]):
            preference_instruction = "本轮第一句先给一句结论式方向，不要先追问。"
        focus = _build_focus_payload(
            focus_type="preference",
            anchor="用户偏好直接、先结论、少铺垫",
            decision_bias="回答先给结论，再给理由，不要先铺背景。",
            must_use_points=["先给结论", "少铺垫", "不绕"],
            avoid=["不要先解释背景", "不要先追问一堆信息"],
            output_instruction=preference_instruction,
            next_pickup=next_pickup,
            world_state_hint=world_state_brief,
            decision_question="下一轮第一句先给结论，还是先铺背景。",
            recommended_answer="先给结论，再给理由。",
            risk_if_wrong="先铺垫或先追问，会让回答显得拖。",
            next_action="第一句先给明确结论，再补一句理由。",
            first_sentence_bias="下一轮第一句倾向：先给结论，再给理由，不要铺垫。",
            source_fields=(source_fields or []) + ["memory_brief", "next_pickup"],
        )
        focus["quality_score"] = _score_memory_focus(focus)
        return focus

    project_markers = [marker for marker in ["这周必须收口", "客户压价", "守住价格", "不再继续让步", "下周三之前必须回复", "先处理客户压价"] if marker in raw_text]
    if (not project_markers) and str(previous_focus.get("focus_type", "") or "") == "project_state":
        if any(token in current_input for token in ["下一步", "怎么安排", "今天要做什么", "压价", "让步", "守住价格"]):
            project_markers = [str(previous_focus.get("anchor", "") or "客户压价")]
            source_fields.extend(["previous_focus", "user_input"])
    if project_markers:
        anchor = "项目这周要收口；当前重点是客户压价；策略是守住价格，不继续无条件让步"
        project_instruction = "本轮建议必须围绕收口、压价、守价三个点。"
        if "下一步" in current_input or "安排" in current_input:
            project_instruction = "本轮第一段先按收口节奏给下一步安排，不要先追问背景。"
        elif "压价" in current_input:
            project_instruction = "本轮第一段先回答对方继续压价时怎么守价，不要先泛问。"
        elif "今天要做什么" in current_input:
            project_instruction = "本轮先把今天最该做的动作排出来，围绕收口、压价、守价。"
        focus = _build_focus_payload(
            focus_type="project_state",
            anchor=anchor,
            decision_bias="先处理客户压价，守住价格底线，不继续无条件让步。",
            must_use_points=["这周收口", "客户压价", "守住价格"],
            avoid=["不要给泛泛计划", "不要重新问项目背景"],
            output_instruction=project_instruction,
            next_pickup=next_pickup,
            world_state_hint=anchor,
            decision_question="下一轮先判断今天围绕收口先做哪几步。",
            recommended_answer="今天先处理压价并推动收口，先守价格，再发跟进，再设回看时间。",
            risk_if_wrong="继续泛整理会拖延收口，还可能被对方继续压价。",
            next_action="今天先定价格底线、发跟进信息、约一个回看时间。",
            first_sentence_bias="下一轮第一句倾向：今天先做三件事，先定底线、发跟进、约回看。",
            source_fields=(source_fields or []) + ["memory_brief", "next_pickup", "world_state_brief"],
        )
        focus["quality_score"] = _score_memory_focus(focus)
        return focus

    sales_anchor = _pick_first_hint(
        raw_text,
        ["太贵", "再考虑", "竞品更便宜", "守价格", "压价", "账期", "跟进", "底线"],
    )
    if (
        previous_scene in {"sales", "negotiation"}
        or main_scene in {"sales", "negotiation"}
        or should_inherit_scene
        or current_turn_depends
    ) and sales_anchor:
        focus_type = "sales_context" if (previous_scene or main_scene) == "sales" else "negotiation_context"
        sales_instruction = "本轮第一段必须先回答守还是让，并给条件式让步策略。"
        if "守价格还是让一点" in current_input:
            sales_instruction = "本轮第一段必须明确回答：先守价格，不直接让价，只保留条件式让步。"
        elif "再考虑" in current_input:
            sales_instruction = "本轮第一段先回答怎么接‘再考虑’，不要先追问背景。"
        focus = _build_focus_payload(
            focus_type=focus_type,
            anchor="客户已连续提出贵、再考虑、竞品更便宜等压价信号",
            decision_bias="先守价格，不建议直接让价，把让步绑定到条件上。",
            must_use_points=["客户压价", "竞品更便宜", "先守价格", "条件式让步"],
            avoid=["不要先追问背景", "不要泛泛说看情况", "不要直接建议降价"],
            output_instruction=sales_instruction,
            next_pickup=next_pickup or sales_anchor,
            world_state_hint=world_state_brief or sales_anchor,
            decision_question="下一轮先判断守价格还是让一点。",
            recommended_answer="先守价格，不直接让；只有对方确认时间、数量、付款等条件时，才条件式让步。",
            risk_if_wrong="直接让价会把底线打薄，还会让对方继续试探。",
            next_action="先回应价值和边界，再抛条件式交换。",
            first_sentence_bias="下一轮第一句倾向：先守价格，不直接让；如果要让，也必须绑定明确条件。",
            source_fields=["previous_scene", "main_scene", "next_pickup", "user_input"],
        )
        focus["quality_score"] = _score_memory_focus(focus)
        return focus

    relationship_anchor = _pick_first_hint(
        raw_text,
        ["执行力差", "事情总是拖", "我有点火", "不想直接骂人", "不想伤关系", "压力很大", "先批评还是先问情况"],
    )
    if (
        previous_scene == "management"
        or main_scene == "management"
        or policy_state.get("has_relationship_risk")
        or any(token in current_input for token in ["先批评还是先问情况", "压力很大", "开口", "太重"])
    ):
        if not relationship_anchor:
            relation_bits = [bit for bit in ["执行力差", "事情拖", "我有火", "不想伤关系", "对方压力大"] if bit in raw_text or bit in current_input]
            if relation_bits:
                relationship_anchor = "；".join(relation_bits[:4])
        if relationship_anchor:
            management_instruction = "本轮必须先判断先问情况还是先批评，并保留关系风险。"
            if "先批评还是先问情况" in current_input:
                management_instruction = "本轮第一段必须明确回答：先问情况，再收标准，不要先反问。"
            elif "压力很大" in current_input:
                management_instruction = "本轮先承接对方可能压力大，再给怎么接的话。"
            focus = _build_focus_payload(
                focus_type="management_relation",
                anchor="团队执行力差、事情拖；用户有火，但不想伤关系；对方可能有压力",
                decision_bias="先问情况，再收标准，不要一上来批评。",
                must_use_points=["执行力差", "用户有火", "不想伤关系", "对方可能压力大"],
                avoid=["不要直接强硬批评", "不要泛泛管理建议", "不要跑成上级压用户"],
                output_instruction=management_instruction,
                next_pickup=next_pickup or relationship_anchor,
                world_state_hint=world_state_brief,
                relationship_hint=relationship_anchor,
                decision_question="下一轮先问情况还是先批评。",
                recommended_answer="先问情况，再收标准。",
                risk_if_wrong="一上来批评会让关系顶僵，后面更难推进。",
                next_action="用低冲突开场先问卡点，再把交付时间和标准收紧。",
                first_sentence_bias="下一轮第一句倾向：先问情况，再收标准，不要一上来批评。",
                source_fields=["previous_scene", "policy_state", "next_pickup", "user_input"],
            )
            focus["quality_score"] = _score_memory_focus(focus)
            return focus

    crisis_anchor = _pick_first_hint(
        raw_text,
        ["现在安全了", "刚缓过来了", "还是有点怕", "没有现实危险", "先缓一缓", "先坐一会儿"],
    )
    if (
        risk_level == "crisis"
        or conversation_phase in {"crisis_continuation", "crisis_recovery"}
        or policy_state.get("is_safety_or_crisis")
        or policy_state.get("is_crisis_recovery")
    ):
        if not crisis_anchor and str(previous_focus.get("focus_type", "") or "") == "crisis_recovery":
            if any(token in current_input for token in ["有点怕", "安全了", "没有现实危险", "缓过来"]):
                crisis_anchor = str(previous_focus.get("anchor", "") or "刚缓过来")
                source_fields.extend(["previous_focus", "user_input"])
        if crisis_anchor:
            crisis_instruction = "本轮第一段必须承接刚从高风险状态缓下来。"
            if "没有现实危险" in current_input or "有点怕" in current_input:
                crisis_instruction = "本轮第一段必须承接刚缓过来、现在没有现实危险但仍有点怕。"
            focus = _build_focus_payload(
                focus_type="crisis_recovery",
                anchor="用户刚从高风险情绪中缓下来，现在没有现实危险但仍害怕",
                decision_bias="先稳住安全感，不分析问题，不转业务。",
                must_use_points=["刚缓过来", "没有现实危险", "仍然害怕", "继续保持安全"],
                avoid=["不要转项目", "不要泛泛安慰", "不要解释成普通问题"],
                output_instruction=crisis_instruction,
                next_pickup=next_pickup or crisis_anchor,
                world_state_hint=world_state_brief or crisis_anchor,
                decision_question="下一轮先判断如何继续稳住安全感，而不是分析问题。",
                recommended_answer="先确认现在没有现实危险，再做一个很小的稳定动作，不转业务。",
                risk_if_wrong="过早分析或转业务会让压力重新上来。",
                next_action="陪用户继续待在安全位置，必要时联系现实支持。",
                first_sentence_bias="下一轮第一句倾向：你刚刚才缓下来，现在怕是正常的；先继续保持安全。",
                source_fields=(source_fields or []) + ["conversation_phase", "policy_state", "next_pickup", "user_input"],
            )
            focus["quality_score"] = _score_memory_focus(focus)
            return focus

    if next_pickup and conversation_phase in {"followup", "revision", "continuation"} and current_turn_depends:
        if _looks_like_generic_focus(next_pickup):
            disabled_reason.append("memory_focus:disabled_too_generic")
        else:
            focus = _build_focus_payload(
                focus_type="followup",
                anchor=next_pickup[:50],
                decision_bias="顺着上一轮接话点继续，不要重新开题。",
                must_use_points=[next_pickup[:24]],
                avoid=["不要像新问题一样从零回答"],
                output_instruction="本轮先顺着上一轮接话点回应，再决定要不要往下推进。",
                next_pickup=next_pickup,
                world_state_hint=world_state_brief,
                first_sentence_bias=next_pickup,
                source_fields=["next_pickup", "conversation_phase", "user_input"],
            )
            focus["quality_score"] = _score_memory_focus(focus)
            return focus

    if current_turn_depends:
        disabled_reason.append("memory_focus:enabled_current_turn_depends_on_context")
    disabled_reason.append("memory_focus:disabled_too_generic")
    focus["disabled_reason"] = list(dict.fromkeys(disabled_reason))
    focus["source_fields"] = list(dict.fromkeys(source_fields))
    return focus


def _estimate_attention_state(
    user_input: str,
    emotion_type: str,
    emotion_intensity: float,
    dominant_desire: str,
    desire_weight: float,
    recent_user_inputs: list[str] | None = None,
) -> tuple[float, str]:
    """
    粗估注意力聚焦度和劫持源。

    目标不是做成复杂模型，而是把原始逻辑里“短、乱、急、重复、过载”
    这些明显信号收进来，别只靠长度做判断。
    """
    from schemas.enums import AttentionHijacker

    text = user_input.strip()
    focus = 0.78
    overload_markers = ["好多", "太多", "信息量", "有点乱", "看不懂", "一下子", "懵了"]
    shift_markers = ["但是", "又", "一会儿", "然后", "算了", "换个", "另一个"]
    logic_markers = ["怎么", "如何", "步骤", "方案", "具体", "因为", "所以", "计划"]

    if len(text) <= 4:
        focus = min(focus, 0.35)
    elif len(text) <= 10:
        focus -= 0.15
    elif len(text) >= 180:
        focus -= 0.15

    if emotion_intensity >= 0.85:
        focus -= 0.25
    elif emotion_intensity >= 0.65:
        focus -= 0.15

    if sum(1 for marker in overload_markers if marker in text) >= 2 or len(text) >= 260:
        focus -= 0.2

    if sum(1 for marker in shift_markers if marker in text) >= 2:
        focus -= 0.12

    if sum(1 for marker in logic_markers if marker in text) >= 2:
        focus += 0.1

    if dominant_desire in {"fear", "wrath"} and desire_weight >= 0.6:
        focus -= 0.08

    if recent_user_inputs and len(recent_user_inputs) >= 2 and recent_user_inputs[-1] == recent_user_inputs[-2]:
        focus = min(focus, 0.3)

    focus = _clamp(focus, 0.15, 0.95)

    if len(text) >= 260 or sum(1 for marker in overload_markers if marker in text) >= 2:
        hijacker = AttentionHijacker.INFO_OVERLOAD.value
    elif emotion_type == "愤怒" or (dominant_desire == "wrath" and desire_weight >= 0.5):
        hijacker = AttentionHijacker.ANGER.value
    elif dominant_desire == "fear" and desire_weight >= 0.45:
        hijacker = AttentionHijacker.FEAR.value
    elif dominant_desire == "pride" and desire_weight >= 0.5:
        hijacker = AttentionHijacker.PRIDE.value
    elif dominant_desire in {"greed", "lust", "gluttony"} and desire_weight >= 0.5:
        hijacker = AttentionHijacker.DESIRE.value
    else:
        hijacker = AttentionHijacker.NONE.value

    return focus, hijacker


def step1_identify(state: GraphState) -> GraphState:
    """Step 1：并行识别用户状态"""
    context = state["context"]
    user_input = state["user_input"]
    short_mode = getattr(context, "short_utterance", False)

    # L2 模块识别
    from modules.L2.sins_keyword import identify_desires
    from modules.L2.collaboration_temperature import identify_emotion
    from modules.L2.dual_core_recognition import identify_dual_core
    from modules.L2.dimension_recognition import identify_dimensions, DimensionResult
    from schemas.enums import EmotionType, MotiveType, DualCoreState
    from concurrent.futures import ThreadPoolExecutor

    # 0. 按 turn_load_level 分级读取记忆
    turn_load_level = _resolve_turn_load_level(context, user_input)
    _set_runtime_field(context, "turn_load_level", turn_load_level)
    memory_mode = "none"
    memory_sources: list[str] = []
    loaded_memory_count = 0
    unified_context_loaded = False
    memory_brief = ""
    session_brief = getattr(context, "session_notes_context", "") or ""
    preloaded_session_context = getattr(context, "preloaded_session_context", "") or ""
    preloaded_session_notes_meta = getattr(context, "preloaded_session_notes_meta", {}) or {}
    step1_reused_session_brief = False
    step1_actual_read_actions = 0

    if turn_load_level in {"crisis", "light"}:
        from modules.memory import get_session_context, get_session_note_stats, load_session_notes

        note_stats = {
            "count": int(preloaded_session_notes_meta.get("count", 0) or 0),
            "chars": int(preloaded_session_notes_meta.get("chars", 0) or 0),
        }
        if preloaded_session_context:
            session_brief = preloaded_session_context or session_brief
            step1_reused_session_brief = True
            _record_memory_read_reuse_trace(
                context,
                stage="step1",
                source="session_brief_reused_from_step0",
                reused_from="step0:session_notes",
                chars=_estimate_text_chars(session_brief),
                count=note_stats.get("count", 0),
                extra={
                    "has_next_pickup": "【下一轮接话点】" in session_brief,
                    "has_world_state_brief": "【局面状态】" in session_brief or "【状态演化】" in session_brief,
                },
            )
            _record_memory_skip_reason(context, "memory_read_reuse:step1_session_brief_from_step0")
            _record_memory_skip_reason(context, "memory_read_reuse:skip_step1_session_reload")
        else:
            read_started_at = time.perf_counter()
            load_session_notes(context.session_id)
            session_brief = get_session_context(context.session_id, limit=1) or session_brief
            note_stats = get_session_note_stats(context.session_id)
            step1_actual_read_actions += 1
            _record_memory_read_trace(
                context,
                stage="step1",
                source="session_brief",
                mode="minimal",
                chars=_estimate_text_chars(session_brief or ""),
                count=note_stats.get("count", 0),
                latency_ms=(time.perf_counter() - read_started_at) * 1000,
                extra={
                    "has_next_pickup": "【下一轮接话点】" in session_brief,
                    "has_world_state_brief": "【局面状态】" in session_brief or "【状态演化】" in session_brief,
                },
            )
            _record_memory_skip_reason(context, "memory_read_reuse:no_preloaded_session_context")
        memory_mode = "minimal"
        memory_brief = session_brief or ""
        memory_sources = ["session_context"] if session_brief else []
        context.long_term_memory = ""
        context.unified_context = session_brief or ""
        context.session_notes_context = session_brief or context.session_notes_context or ""
        _set_memory_gate_decision(
            context,
            "step1",
            {
                "memory_mode": "minimal",
                "load_level": turn_load_level,
                "unified_context_loaded": False,
                "reason": "memory_read_gate:crisis_minimal_reuse" if turn_load_level == "crisis" and step1_reused_session_brief else "memory_read_gate:light_minimal_reuse" if step1_reused_session_brief else "light_or_crisis_minimal_session_brief",
                "reuse_preloaded_session": step1_reused_session_brief,
            },
        )
        _set_memory_stats(
            context,
            session_note_size=note_stats.get("chars", 0),
            session_note_count=note_stats.get("count", 0),
        )
    elif turn_load_level == "standard":
        from modules.memory import get_memory_manager, get_long_term_memory_stats, get_session_note_stats, load_session_notes

        read_started_at = time.perf_counter()
        load_session_notes(context.session_id)
        memory_mgr = get_memory_manager()
        memory_brief, memory_meta = memory_mgr.get_unified_context(
            user_id=context.session_id,
            current_input=user_input,
            context=context,
            related_limit=3,
            recent_limit=0,
            include_experience=False,
            return_meta=True,
        )
        memory_mode = "relevant"
        step1_actual_read_actions += 1
        loaded_memory_count = int(memory_meta.get("loaded_memory_count", 0) or 0)
        memory_sources = list(memory_meta.get("memory_sources", []))
        unified_context_loaded = bool(memory_meta.get("unified_context_loaded", False))
        context.long_term_memory = memory_brief or ""
        context.unified_context = memory_brief or ""
        note_stats = get_session_note_stats(context.session_id)
        long_term_stats = get_long_term_memory_stats(context.session_id)
        _record_memory_read_trace(
            context,
            stage="step1",
            source="unified_context_standard",
            mode="relevant",
            chars=int(memory_meta.get("unified_context_chars", 0) or _estimate_text_chars(memory_brief)),
            count=loaded_memory_count,
            latency_ms=(time.perf_counter() - read_started_at) * 1000,
            extra={
                "related_count": int(memory_meta.get("related_count", 0) or 0),
                "recent_count": int(memory_meta.get("recent_count", 0) or 0),
                "session_note_count": int(memory_meta.get("session_note_count", 0) or note_stats.get("count", 0)),
                "includes_session_notes": True,
                "preloaded_session_context_available": bool(preloaded_session_context),
            },
        )
        _set_memory_gate_decision(
            context,
            "step1",
            {
                "memory_mode": "relevant",
                "load_level": "standard",
                "related": 3,
                "recent": 0,
                "include_experience": False,
                "reuse_preloaded_session": False,
                "reason": "memory_read_gate:standard_requires_unified_context",
            },
        )
        _set_memory_stats(
            context,
            session_note_size=note_stats.get("chars", 0),
            session_note_count=note_stats.get("count", 0),
            long_term_memory_size=long_term_stats.get("chars", 0),
            long_term_memory_count=long_term_stats.get("count", 0),
        )
    else:  # deep
        from modules.memory import get_memory_manager, get_long_term_memory_stats, get_session_note_stats, load_session_notes

        read_started_at = time.perf_counter()
        load_session_notes(context.session_id)
        memory_mgr = get_memory_manager()
        memory_brief, memory_meta = memory_mgr.get_unified_context(
            user_id=context.session_id,
            current_input=user_input,
            context=context,
            related_limit=5,
            recent_limit=3,
            include_experience=True,
            return_meta=True,
        )
        memory_mode = "full"
        step1_actual_read_actions += 1
        loaded_memory_count = int(memory_meta.get("loaded_memory_count", 0) or 0)
        memory_sources = list(memory_meta.get("memory_sources", []))
        unified_context_loaded = bool(memory_meta.get("unified_context_loaded", True))
        context.long_term_memory = memory_brief or ""
        context.unified_context = memory_brief or ""
        note_stats = get_session_note_stats(context.session_id)
        long_term_stats = get_long_term_memory_stats(context.session_id)
        _record_memory_read_trace(
            context,
            stage="step1",
            source="unified_context_deep",
            mode="full",
            chars=int(memory_meta.get("unified_context_chars", 0) or _estimate_text_chars(memory_brief)),
            count=loaded_memory_count,
            latency_ms=(time.perf_counter() - read_started_at) * 1000,
            extra={
                "related_count": int(memory_meta.get("related_count", 0) or 0),
                "recent_count": int(memory_meta.get("recent_count", 0) or 0),
                "experience_digest_count": int(memory_meta.get("experience_digest_count", 0) or 0),
                "include_experience": True,
                "includes_session_notes": True,
                "preloaded_session_context_available": bool(preloaded_session_context),
            },
        )
        _set_memory_gate_decision(
            context,
            "step1",
            {
                "memory_mode": "full",
                "load_level": "deep",
                "related": 5,
                "recent": 3,
                "include_experience": True,
                "reuse_preloaded_session": False,
                "reason": "memory_read_gate:deep_requires_unified_context",
            },
        )
        _set_memory_stats(
            context,
            session_note_size=note_stats.get("chars", 0),
            session_note_count=note_stats.get("count", 0),
            long_term_memory_size=long_term_stats.get("chars", 0),
            long_term_memory_count=long_term_stats.get("count", 0),
        )

    context_brief = _build_context_brief(
        context=context,
        memory_mode=memory_mode,
        memory_brief=memory_brief,
        loaded_memory_count=loaded_memory_count,
        unified_context_loaded=unified_context_loaded,
        memory_sources=memory_sources,
        session_brief=session_brief,
    )
    _set_runtime_field(context, "context_brief", context_brief)
    state["context_brief"] = context_brief
    memory_continuity_focus = _build_memory_continuity_focus(context, user_input, context_brief)
    _set_runtime_field(context, "memory_continuity_focus", memory_continuity_focus)
    state["memory_continuity_focus"] = memory_continuity_focus
    runtime_trace = getattr(context, "runtime_trace", None)
    if not isinstance(runtime_trace, dict):
        runtime_trace = {
            "turn_load_level": turn_load_level,
            "next_step_policy": getattr(context, "next_step_policy", "soft"),
            "llm_call_count": 0,
            "memory_read_count": 0,
            "memory_read_count_effective": 0,
            "memory_read_count_saved_by_reuse": 0,
            "memory_write_count": 0,
            "skill_loaded_count": 0,
            "prompt_blocks": [],
            "prompt_chars_estimate": 0,
            "step8_mode": "full",
            "step9_mode": "full",
            "latency_ms": {},
            "memory_continuity_focus": {},
            "memory_continuity_focus_used": False,
            "memory_continuity_focus_type": "none",
            "memory_continuity_focus_chars": 0,
            "memory_used_in_output_observed": "unknown",
            "memory_used_in_output_reason": [],
            "memory_focus_quality_score": 0,
            "memory_focus_has_decision_bias": False,
            "memory_focus_has_must_use_points": False,
            "memory_focus_disabled_reason": [],
            "memory_focus_source_fields": [],
        }
        _set_runtime_field(context, "runtime_trace", runtime_trace)
    step0_read_happened = 1 if any(
        isinstance(detail, dict) and detail.get("stage") == "step0" and detail.get("source") == "session_notes"
        for detail in runtime_trace.get("memory_read_detail", [])
    ) else 0
    if turn_load_level in {"crisis", "light"}:
        runtime_trace["memory_read_count"] = max(int(runtime_trace.get("memory_read_count", 0) or 0), 1 if session_brief else 0)
    else:
        runtime_trace["memory_read_count"] = loaded_memory_count
    runtime_trace["memory_read_count_effective"] = step0_read_happened + step1_actual_read_actions
    runtime_trace["memory_read_count_saved_by_reuse"] = int(runtime_trace.get("memory_read_count_saved_by_reuse", 0) or 0) + (1 if step1_reused_session_brief else 0)
    runtime_trace["memory_mode"] = memory_mode
    runtime_trace["memory_sources"] = memory_sources
    runtime_trace["unified_context_loaded"] = unified_context_loaded
    runtime_trace["memory_continuity_focus"] = {
        "memory_use_required": bool(memory_continuity_focus.get("memory_use_required", False)),
        "focus_type": str(memory_continuity_focus.get("focus_type", "none") or "none"),
        "anchor": _compact_hint(memory_continuity_focus.get("anchor", ""), 40),
        "decision_bias": _compact_hint(memory_continuity_focus.get("decision_bias", ""), 50),
        "must_use_points": [ _compact_hint(item, 20) for item in (memory_continuity_focus.get("must_use_points", []) or [])[:3] ],
        "next_pickup": _compact_hint(memory_continuity_focus.get("next_pickup", ""), 40),
        "world_state_hint": _compact_hint(memory_continuity_focus.get("world_state_hint", ""), 40),
        "relationship_hint": _compact_hint(memory_continuity_focus.get("relationship_hint", ""), 40),
    }
    runtime_trace["memory_continuity_focus_type"] = str(memory_continuity_focus.get("focus_type", "none") or "none")
    runtime_trace["memory_continuity_focus_chars"] = _estimate_text_chars(memory_continuity_focus)
    runtime_trace["memory_focus_quality_score"] = int(memory_continuity_focus.get("quality_score", 0) or 0)
    runtime_trace["memory_focus_has_decision_bias"] = bool(memory_continuity_focus.get("decision_bias"))
    runtime_trace["memory_focus_has_must_use_points"] = bool(memory_continuity_focus.get("must_use_points"))
    runtime_trace["memory_focus_disabled_reason"] = list(memory_continuity_focus.get("disabled_reason", []) or [])
    runtime_trace["memory_focus_source_fields"] = list(memory_continuity_focus.get("source_fields", []) or [])
    runtime_trace.setdefault("memory_continuity_focus_used", False)
    runtime_trace.setdefault("memory_used_in_output_observed", "unknown")
    runtime_trace.setdefault("memory_used_in_output_reason", [])
    state["runtime_trace"] = runtime_trace
    state["turn_load_level"] = turn_load_level

    # 1-3. 并行识别：八宗罪 / 协作温度 / 双核 / 七维度
    worker_count = 3 if short_mode else 4
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        desires_future = executor.submit(identify_desires, user_input)
        emotion_future = executor.submit(identify_emotion, user_input)
        dual_core_future = executor.submit(identify_dual_core, user_input)
        dimension_future = executor.submit(identify_dimensions, user_input) if not short_mode else None

        desires_result = desires_future.result()
        emotion_result = emotion_future.result()
        dual_core_result = dual_core_future.result()
        if dimension_future is not None:
            dimension_result = dimension_future.result()
        else:
            dimension_result = DimensionResult(
                dominant_dimension="",
                dimensions_detected=[],
                confidence=0.0,
                suggested_combo="",
                is_negative=False,
            )

    # 八宗罪关键词识别 → user.desires
    context.user.desires = desires_result.desires

    # 欲望压制/转化关系 → context.desire_relations（供 Step 4/6 使用）
    context.desire_relations = desires_result.relations

    # 将字符串转换为枚举类型
    emotion_type_map = {
        "挫败": EmotionType.FRUSTRATED,
        "迷茫": EmotionType.CONFUSED,
        "急躁": EmotionType.IMPATIENT,
        "平静": EmotionType.CALM,
        "愤怒": EmotionType.ANGRY,
    }
    motive_type_map = {
        "灵感兴奋": MotiveType.INSPIRATION,
        "生活期待": MotiveType.LIFE_EXPECTATION,
        "回避恐惧": MotiveType.FEAR_AVOIDANCE,
        "压力被动": MotiveType.STRESS_PASSIVE,
    }

    context.user.emotion.type = emotion_type_map.get(emotion_result.type, EmotionType.CALM)
    context.user.emotion.intensity = emotion_result.intensity
    context.user.emotion.confidence = emotion_result.confidence
    context.user.motive = motive_type_map.get(emotion_result.motive, MotiveType.LIFE_EXPECTATION)

    # 短句场景：优先继承上下文情绪，避免“同词同回复”的机械化表现
    if short_mode and len(context.history) >= 2:
        prev_emotion_intensity = None
        prev_emotion_type = None
        for h in reversed(context.history[:-1]):
            if h.role == "user" and "emotion_intensity" in h.metadata:
                prev_emotion_intensity = h.metadata.get("emotion_intensity")
                prev_emotion_type = h.metadata.get("emotion_type")
                break
        if prev_emotion_type and prev_emotion_type in emotion_type_map:
            context.user.emotion.type = emotion_type_map[prev_emotion_type]
        if prev_emotion_intensity is not None:
            inherited = max(0.0, min(1.0, float(prev_emotion_intensity)))
            context.user.emotion.intensity = inherited * 0.8 + context.user.emotion.intensity * 0.2
        # 短句依赖上下文时，提高置信度下限，避免触发模板化低置信度回退
        context.user.emotion.confidence = max(context.user.emotion.confidence, 0.65)

    # 2.5 情绪延续：上轮高情绪+本轮平静 → 继承上轮情绪（带衰减）
    if len(context.history) >= 2:
        prev_emotion_intensity = 0.0
        prev_emotion_type = None
        for h in reversed(context.history[:-1]):
            if h.role == "user" and "emotion_intensity" in h.metadata:
                prev_emotion_intensity = h.metadata["emotion_intensity"]
                prev_emotion_type = h.metadata.get("emotion_type")
                break
        # 上轮高情绪(>=0.5) + 本轮平静 → 继承上轮情绪（衰减 20%）
        if (prev_emotion_intensity >= 0.5 and
            context.user.emotion.type == EmotionType.CALM and
            context.user.emotion.intensity <= 0.6):
            context.user.emotion.intensity = max(prev_emotion_intensity * 0.8, 0.5)
            # 继承上轮情绪类型
            if prev_emotion_type and prev_emotion_type in emotion_type_map:
                context.user.emotion.type = emotion_type_map[prev_emotion_type]

    # 记录本轮情绪到历史 metadata（供下轮延续使用）
    for h in reversed(context.history):
        if h.role == "user":
            h.metadata["emotion_intensity"] = context.user.emotion.intensity
            h.metadata["emotion_type"] = emotion_result.type
            break

    # 3. 双核状态识别 → user.dual_core
    dual_core_map = {
        "对抗": DualCoreState.CONFLICT,
        "协同": DualCoreState.SYNERGY,
        "同频": DualCoreState.SYNC,
        "合理化": DualCoreState.RATIONALIZATION,
    }
    context.user.dual_core.state = dual_core_map.get(dual_core_result.state, DualCoreState.SYNC)
    context.user.dual_core.confidence = dual_core_result.confidence

    # 3.1 七个维度识别（并行结果，供 Step 6 升维使用）
    # 存入 context 供 Step 6 使用
    context._dimension_result = dimension_result

    # 3.2 防伪装机制：交叉验证三个识别模块（06-关键词 + 27-情绪 + 双核状态）
    # 矛盾信号 → 降低综合置信度，偏向触发确认协议
    confidence_adjustment = 0.0
    dominant_desire_check, desire_weight_check = context.user.desires.get_dominant()

    # 规则1：情绪平静但八宗罪权重异常高 → 可能伪装
    if emotion_result.type == "平静" and desire_weight_check > 0.7:
        confidence_adjustment -= 0.15

    # 规则2：双核协同但情绪强度高 → 矛盾
    if dual_core_result.state == "协同" and emotion_result.intensity > 0.6:
        confidence_adjustment -= 0.15

    # 规则3：挫败但恐惧权重低 → 可能隐藏恐惧（文档要求）
    if emotion_result.type == "挫败" and context.user.desires.fear < 0.3:
        confidence_adjustment -= 0.1

    # 规则4：急躁但愤怒权重低 → 可能隐藏愤怒
    if emotion_result.type == "急躁" and context.user.desires.wrath < 0.3:
        confidence_adjustment -= 0.1

    # 正向交叉验证：多模块互相印证时，置信度往上提一点
    if emotion_result.type == "挫败" and (context.user.desires.fear >= 0.35 or context.user.desires.wrath >= 0.35):
        confidence_adjustment += 0.1
    if emotion_result.type == "迷茫" and context.user.desires.sloth >= 0.35:
        confidence_adjustment += 0.1
    if emotion_result.type == "急躁" and (context.user.desires.wrath >= 0.35 or context.user.desires.fear >= 0.35):
        confidence_adjustment += 0.1

    context.user.emotion.confidence = _clamp(
        context.user.emotion.confidence + confidence_adjustment,
        0.1,
        1.0,
    )

    # 4. 注意力识别（改进版：长度 + 情绪 + 逻辑度 + 重复度 + 过载信号）
    from schemas.enums import AttentionHijacker
    dominant_desire, desire_weight = context.user.desires.get_dominant()
    recent_user_inputs = [
        item.content for item in context.history[-4:]
        if item.role == "user"
    ]
    focus, hijacker = _estimate_attention_state(
        user_input=user_input,
        emotion_type=emotion_result.type,
        emotion_intensity=context.user.emotion.intensity,
        dominant_desire=dominant_desire,
        desire_weight=desire_weight,
        recent_user_inputs=recent_user_inputs,
    )
    context.user.attention.focus = focus

    hijacker_map = {
        AttentionHijacker.ANGER.value: AttentionHijacker.ANGER,
        AttentionHijacker.FEAR.value: AttentionHijacker.FEAR,
        AttentionHijacker.PRIDE.value: AttentionHijacker.PRIDE,
        AttentionHijacker.DESIRE.value: AttentionHijacker.DESIRE,
        AttentionHijacker.INFO_OVERLOAD.value: AttentionHijacker.INFO_OVERLOAD,
        AttentionHijacker.NONE.value: AttentionHijacker.NONE,
    }
    context.user.attention.hijacked_by = hijacker_map.get(hijacker, AttentionHijacker.NONE)

    # 5. 更新用户画像的情绪/欲望模式（新增）
    from modules.memory import get_memory_manager
    memory_mgr = get_memory_manager()
    emotion_type_str = emotion_result.type
    memory_mgr.update_emotion_pattern(context.session_id, emotion_type_str, emotion_result.intensity)
    dominant, weight = desires_result.desires.get_dominant()
    if weight > 0.3:
        memory_mgr.update_desire_pattern(context.session_id, dominant, weight)

    # 5.5 标记高情绪（供 Step 2 纠正权检测使用）
    if context.user.emotion.intensity > 0.8:
        for h in reversed(context.history):
            if h.role == "user":
                h.metadata["high_emotion"] = True
                break

    # 6. 低置信度确认协议
    emotion_confidence = context.user.emotion.confidence  # 使用惩罚后的置信度
    desires_confidence = desires_result.confidence
    dual_core_confidence = dual_core_result.confidence

    any_low_confidence = (
        emotion_confidence < 0.6 or
        desires_confidence < 0.6 or
        dual_core_confidence < 0.6
    )

    # 仅对真正模糊的输入触发低置信度（极短输入、无情绪词）
    is_truly_ambiguous = (
        len(user_input.strip()) <= 3
        and emotion_result.type == "平静"
        and any_low_confidence
    )

    # 已被 Step 0 标记为短句时，不在 Step 1 走模板化低置信度回退；
    # 后续交给元控制器 + 目标/策略链路做更贴上下文的动态处理。
    if is_truly_ambiguous and not short_mode:
        # 极低置信度：进入完整澄清模式
        context.output = "我没太明白你的意思。能再说详细一点吗？你想解决的是实际问题，还是想聊聊感受？"
        return {**state, "context": context, "output": context.output, "skip_to_end": True, "low_confidence": True}
    elif any_low_confidence and emotion_result.type == "平静" and len(user_input.strip()) <= 5 and not short_mode:
        # 中等低置信度：不再粗暴截断主链，而是标记为需要轻补位
        context.guidance_needed = True
        context.guidance_focus = "both"
        context.guidance_prompt = "你可以顺手补一句，是更想说当下心情，还是更想把事情理清。"
        return {**state, "context": context, "low_confidence": True}

    # P1-5: 推断关系位置（身份轴补充）
    _infer_relationship_position(context, user_input)

    return {**state, "context": context, "low_confidence": False}


def _infer_relationship_position(context, user_input: str) -> None:
    """根据场景+输入关键词推断关系位置"""
    scene = context.primary_scene or ""
    input_lower = user_input.lower()
    
    # 场景直接映射
    scene_position_map = {
        "sales": "服务-客户",
        "negotiation": "对等-竞争",
        "management": "上级-下级",
        "emotion": "亲密-依赖",
    }
    if scene in scene_position_map:
        context.user.relationship_position = scene_position_map[scene]
    
    # 关键词覆盖
    if any(kw in input_lower for kw in ["老板", "领导", "上级", "汇报"]):
        context.user.relationship_position = "下级-上级"
    elif any(kw in input_lower for kw in ["下属", "团队", "员工", "管理"]):
        context.user.relationship_position = "上级-下级"
    elif any(kw in input_lower for kw in ["合作", "一起", "咱们", "共同"]):
        context.user.relationship_position = "对等-合作"
    elif any(kw in input_lower for kw in ["竞争", "对手", "别家", "竞品"]):
        context.user.relationship_position = "对等-竞争"
    elif any(kw in input_lower for kw in ["爱你", "分手", "纪念日", "活不下去"]):
        context.user.relationship_position = "亲密-依赖"
