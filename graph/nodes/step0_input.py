"""
Human-OS Engine - LangGraph 节点实现

对应总控规格的 Step 0-9。
"""

import time

from graph.state import GraphState
from graph.nodes.helpers import _generate_history_summary, _is_light_turn, _turn_load_level as _legacy_turn_load_level


_CRISIS_MARKERS = (
    "不想活了",
    "不想活",
    "想死",
    "撑不下去了",
    "撑不住",
    "撑不下去",
    "扛不住",
    "扛不下去",
    "不想扛了",
    "别让我再扛了",
    "没法继续",
    "继续不下去",
    "很绝望",
    "已经绝望",
    "太绝望了",
    "自杀",
    "伤害自己",
    "想伤害自己",
    "活不下去",
    "不想存在",
    "消失算了",
    "结束算了",
    "现实危险",
    "违法",
    "高风险",
)

_CRISIS_CONTINUATION_MARKERS = (
    "我先坐一会儿",
    "我先缓一下",
    "我现在很乱",
    "我不知道怎么办",
    "我身边没人",
    "没人能说",
    "别讲大道理",
    "先别说那么多",
    "我想安静一下",
    "我还是很难受",
    "我还没缓过来",
)

_CRISIS_RECOVERY_MARKERS = (
    "我现在安全了",
    "我没事了",
    "我已经联系到人了",
    "我现在有人陪",
    "我已经稳定一点了",
    "不用担心安全了",
)

_DEEP_MARKERS = (
    "全面审计",
    "系统审计",
    "代码修复",
    "全面扫描",
    "完整报告",
    "架构重构",
    "长文档",
    "深度分析",
    "复盘",
    "方案",
    "修复计划",
    "patch plan",
    "完整修复路线图",
    "所有运行报告",
    "回归评估报告",
    "系统级修复",
    "代码级 patch plan",
    "多报告综合",
    "全量扫描",
    "把这套系统从入口到输出完整过一遍",
    "多份文档一起看",
    "总路线",
    "修复顺序",
)

_STANDARD_MARKERS = (
    "客户",
    "价格",
    "太贵",
    "压价",
    "底线",
    "谈判",
    "对方",
    "账期",
    "条件",
    "签约",
    "合作边界",
    "不回消息",
    "跟进",
    "催单",
    "效果",
    "值不值",
    "怀疑",
    "预算不足",
    "团队",
    "执行力",
    "员工",
    "下属",
    "跨部门",
    "绩效",
    "甩锅",
    "不配合",
    "跑题",
    "拖着",
    "卡住",
    "不交结果",
    "沟通卡住",
    "开口",
    "批评",
    "怎么回",
    "怎么说",
    "怎么做",
    "守住",
    "守底线",
    "话术",
    "销售",
    "管理",
    "情绪支持",
)

_EMOTION_MARKERS = (
    "烦",
    "累",
    "委屈",
    "难受",
    "焦虑",
    "压力",
    "情绪",
    "生气",
    "郁闷",
    "怕",
    "慌",
    "撑不住",
)

_LIGHT_HINT_MARKERS = (
    "别展开",
    "直接讲重点",
    "短回答",
    "不想分析",
    "不想说太多",
    "不想聊太细",
    "先不想聊",
    "先别分析",
    "简单说",
    "简单点",
    "少说",
    "讲重点",
    "别细说",
    "先别展开",
)

_LIGHT_SUPPORT_MARKERS = (
    "有点懵",
    "有点烦",
    "有点乱",
    "有点怕",
    "有点累",
    "今天很累",
    "不想分析",
    "不想说太多",
    "不想聊太细",
    "先不想聊",
    "先别分析",
    "被误解",
    "误解",
    "委屈",
    "心里堵",
    "有点难受",
    "有点慌",
    "怕自己做不好",
    "状态很低",
    "怕伤关系",
)

_RELATIONSHIP_CONCERN_MARKERS = (
    "怕伤关系",
    "不想直接骂人",
    "不想太硬",
    "怕说重了",
    "担心对方接受不了",
    "员工状态很低",
    "状态很低",
    "压力很大",
    "最近压力很大",
    "他最近压力很大",
    "如果他说自己最近压力很大",
)

_ATTITUDE_ONLY_MARKERS = (
    "对方态度很强硬",
    "态度很强硬",
    "对方很强硬",
    "他们语气很硬",
    "语气很硬",
    "签约总拖着不往前走",
    "签约总拖着",
    "不往前走",
    "对方一直拖着",
    "一直拖着",
    "局面有点僵",
    "合作现在有点别扭",
)

_MANAGEMENT_BLOCKER_MARKERS = (
    "下属总拖着不交结果",
    "绩效沟通卡住",
    "这个项目大家都在甩锅",
    "跨部门一直不配合",
    "拖着不交结果",
    "绩效沟通卡住了",
    "甩锅",
    "不配合",
    "卡住",
    "不交结果",
)

_NEGOTIATION_BOUNDARY_MARKERS = (
    "签约总拖着",
    "不往前走",
    "拖签",
    "拖着不签",
    "拖着",
    "对方态度很强硬",
    "态度很强硬",
    "对方很强硬",
    "语气很硬",
    "一直压价",
    "压价",
    "降价",
    "让一步",
    "让步",
    "怕吃亏",
    "吃亏",
    "不想亏",
    "底线",
    "边界",
    "边界不清",
    "合作边界",
    "服务范围",
    "交付范围",
    "账期",
    "拉长",
    "回款",
    "付款",
    "条件",
    "加条件",
    "临时加",
    "变更条件",
    "服务",
)

_EXPLICIT_ACTION_MARKERS = (
    "怎么办",
    "怎么做",
    "怎么说",
    "怎么接",
    "怎么跟进",
    "怎么开口",
    "该怎么接",
    "该怎么做",
    "该怎么说",
    "如何",
    "怎么推进",
    "怎么回",
    "怎么处理",
    "下一步",
    "要不要催",
    "催一下",
    "催一催",
    "写一句",
    "发一段",
    "给我一段",
    "帮我写",
    "话术",
    "能直接发出去",
    "守底线",
    "守住",
    "催单",
    "跟进",
    "还能不能谈",
    "谈不谈",
)

_CONTEXTUAL_FOLLOWUP_MARKERS = (
    "那如果",
    "如果他",
    "如果对方",
    "如果他们",
    "如果说",
    "如果再",
    "如果还是",
    "如果聊着聊着",
    "那怎么办",
    "那我怎么",
    "会不会太重",
    "能不能软一点",
    "太硬",
    "太冲",
    "软一点",
    "稳一点",
    "换个说法",
    "直接点",
    "别那么重",
    "再考虑",
    "怕谈崩",
    "一直忍着",
    "怕做不好",
    "压力很大",
    "我又怕",
    "情绪又上来了",
    "别讲大道理",
    "没人能说",
)

_ACK_MARKERS = {"好的", "好", "嗯", "嗯嗯", "收到", "谢谢", "行", "可以", "ok", "OK"}


def _set_runtime_field(context, name: str, value):
    """给 Pydantic Context 挂运行时字段，避免改 schema。"""
    object.__setattr__(context, name, value)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


_POLICY_PATCH_REASONS = {
    "legacy_fallback": "policy_patch_migration:legacy_fallback_used",
    "softening": "policy_patch_migration:softening_from_policy_state",
    "revision": "policy_patch_migration:revision_from_policy_state",
    "relationship_risk": "policy_patch_migration:relationship_risk_from_policy_state",
    "attitude_description": "policy_patch_migration:attitude_description_from_policy_state",
    "script": "policy_patch_migration:script_from_policy_state",
    "script_legacy": "policy_patch_migration:script_legacy_fallback_used",
    "action": "policy_patch_migration:action_from_policy_state",
    "action_legacy": "policy_patch_migration:action_legacy_fallback_used",
    "soft_protection_preserved": "policy_patch_migration:soft_protection_preserved",
}

_POLICY_BOUNDARY_REASONS = {
    "short_softening_soft": "policy_boundary_fix:short_softening=>soft",
    "attitude_only_soft": "policy_boundary_fix:attitude_only=>soft",
    "relationship_block_explicit": "policy_boundary_fix:relationship_risk_block_explicit",
    "relationship_block_deep": "policy_boundary_fix:relationship_risk_block_deep",
    "legacy_fallback_preserved": "policy_boundary_fix:legacy_fallback_preserved",
}

_ROUTE_STATE_REASONS = {
    "block_deep_attitude_relationship": "route_state:block_deep_for_attitude_or_relationship",
    "short_attitude_soft_guard": "route_state:short_attitude_soft_load_guard",
    "fallback_legacy_load": "route_state:fallback_legacy_load",
}

_SOFT_PROTECTION_REASONS = {
    "revision": "soft_protection:revision",
    "relationship_concern": "soft_protection:relationship_concern",
    "attitude_only": "soft_protection:attitude_only",
    "business_emotion_mixed": "soft_protection:business_emotion_mixed",
}


def _append_unique(items: list[str], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _estimate_text_chars(text) -> int:
    return len(str(text or ""))


def _ensure_memory_trace_defaults(trace: dict) -> dict:
    trace.setdefault("memory_read_sources", [])
    trace.setdefault("memory_write_targets", [])
    trace.setdefault("memory_chars_loaded", 0)
    trace.setdefault("memory_chars_in_prompt", 0)
    trace.setdefault("memory_read_count_effective", 0)
    trace.setdefault("memory_read_count_saved_by_reuse", 0)
    trace.setdefault("memory_gate_decision", {})
    trace.setdefault("memory_skipped_reason", [])
    trace.setdefault("memory_write_reason", [])
    trace.setdefault("memory_read_latency_ms", {})
    trace.setdefault("memory_write_latency_ms", {})
    trace.setdefault("memory_read_detail", [])
    trace.setdefault("memory_write_detail", [])
    trace.setdefault("session_note_size", 0)
    trace.setdefault("session_note_count", 0)
    trace.setdefault("long_term_memory_size", 0)
    trace.setdefault("long_term_memory_count", 0)
    trace.setdefault("memory_duplicate_detected", False)
    trace.setdefault("memory_pollution_risk", [])
    trace.setdefault("memory_prompt_blocks", [])
    trace.setdefault("memory_used_in_output_observed", "unknown")
    trace.setdefault("semantic_extract_skipped_reason", [])
    trace.setdefault("semantic_extract_input_chars", 0)
    trace.setdefault("semantic_extract_result_count", 0)
    trace.setdefault("semantic_extract_stored_count", 0)
    trace.setdefault("semantic_extract_latency_ms", 0.0)
    return trace


def _get_runtime_trace(context) -> dict:
    trace = getattr(context, "runtime_trace", None)
    if not isinstance(trace, dict):
        trace = _init_runtime_trace(context)
    return _ensure_memory_trace_defaults(trace)


def _set_memory_gate_decision(context, stage: str, decision: dict) -> None:
    trace = _get_runtime_trace(context)
    gate = trace.setdefault("memory_gate_decision", {})
    gate[stage] = decision
    _set_runtime_field(context, "runtime_trace", trace)


def _record_memory_skip_reason(context, reason: str) -> None:
    if not reason:
        return
    trace = _get_runtime_trace(context)
    _append_unique(trace.setdefault("memory_skipped_reason", []), reason)
    _set_runtime_field(context, "runtime_trace", trace)


def _record_memory_read_trace(
    context,
    *,
    stage: str,
    source: str,
    mode: str = "",
    chars: int = 0,
    count: int = 0,
    latency_ms: float = 0.0,
    extra: dict | None = None,
) -> None:
    trace = _get_runtime_trace(context)
    full_source = f"{stage}:{source}"
    _append_unique(trace.setdefault("memory_read_sources", []), full_source)
    trace["memory_chars_loaded"] = int(trace.get("memory_chars_loaded", 0) or 0) + max(0, int(chars or 0))
    read_latency = trace.setdefault("memory_read_latency_ms", {})
    read_latency[full_source] = round(float(read_latency.get(full_source, 0.0) or 0.0) + float(latency_ms or 0.0), 3)
    detail = {
        "stage": stage,
        "source": source,
        "mode": mode or "",
        "chars": max(0, int(chars or 0)),
        "count": max(0, int(count or 0)),
        "latency_ms": round(float(latency_ms or 0.0), 3),
    }
    if extra:
        detail.update(extra)
    trace.setdefault("memory_read_detail", []).append(detail)
    _set_runtime_field(context, "runtime_trace", trace)


def _record_memory_read_reuse_trace(
    context,
    *,
    stage: str,
    source: str,
    reused_from: str,
    chars: int = 0,
    count: int = 0,
    saved_reads: int = 1,
    extra: dict | None = None,
) -> None:
    trace = _get_runtime_trace(context)
    full_source = f"{stage}:{source}"
    _append_unique(trace.setdefault("memory_read_sources", []), full_source)
    detail = {
        "stage": stage,
        "source": source,
        "mode": "reused",
        "chars": max(0, int(chars or 0)),
        "count": max(0, int(count or 0)),
        "latency_ms": 0.0,
        "reused": True,
        "reused_from": reused_from,
    }
    if extra:
        detail.update(extra)
    trace.setdefault("memory_read_detail", []).append(detail)
    trace["memory_read_count_saved_by_reuse"] = int(trace.get("memory_read_count_saved_by_reuse", 0) or 0) + max(0, int(saved_reads or 0))
    _set_runtime_field(context, "runtime_trace", trace)


def _record_memory_write_trace(
    context,
    *,
    stage: str,
    target: str,
    mode: str = "",
    chars: int = 0,
    latency_ms: float = 0.0,
    reason: str = "",
    duplicate: bool = False,
    pollution_risks: list[str] | None = None,
    extra: dict | None = None,
) -> None:
    trace = _get_runtime_trace(context)
    full_target = f"{stage}:{target}"
    _append_unique(trace.setdefault("memory_write_targets", []), full_target)
    if reason:
        _append_unique(trace.setdefault("memory_write_reason", []), reason)
    if duplicate:
        trace["memory_duplicate_detected"] = True
    for risk in pollution_risks or []:
        _append_unique(trace.setdefault("memory_pollution_risk", []), risk)
    write_latency = trace.setdefault("memory_write_latency_ms", {})
    write_latency[full_target] = round(float(write_latency.get(full_target, 0.0) or 0.0) + float(latency_ms or 0.0), 3)
    detail = {
        "stage": stage,
        "target": target,
        "mode": mode or "",
        "chars": max(0, int(chars or 0)),
        "latency_ms": round(float(latency_ms or 0.0), 3),
        "reason": reason or "",
        "duplicate": bool(duplicate),
    }
    if extra:
        detail.update(extra)
    trace.setdefault("memory_write_detail", []).append(detail)
    _set_runtime_field(context, "runtime_trace", trace)


def _set_memory_stats(
    context,
    *,
    session_note_size: int | None = None,
    session_note_count: int | None = None,
    long_term_memory_size: int | None = None,
    long_term_memory_count: int | None = None,
) -> None:
    trace = _get_runtime_trace(context)
    if session_note_size is not None:
        trace["session_note_size"] = max(0, int(session_note_size))
    if session_note_count is not None:
        trace["session_note_count"] = max(0, int(session_note_count))
    if long_term_memory_size is not None:
        trace["long_term_memory_size"] = max(0, int(long_term_memory_size))
    if long_term_memory_count is not None:
        trace["long_term_memory_count"] = max(0, int(long_term_memory_count))
    _set_runtime_field(context, "runtime_trace", trace)


def _record_memory_prompt_blocks(context, blocks: list[dict]) -> None:
    trace = _get_runtime_trace(context)
    normalized: list[dict] = []
    total_chars = 0
    for block in blocks or []:
        if not isinstance(block, dict):
            continue
        name = str(block.get("block", "") or "").strip()
        chars = max(0, int(block.get("chars", 0) or 0))
        if not name:
            continue
        normalized.append({"block": name, "chars": chars})
        total_chars += chars
    trace["memory_prompt_blocks"] = normalized
    trace["memory_chars_in_prompt"] = total_chars
    _set_runtime_field(context, "runtime_trace", trace)


def _get_route_features(route_state: dict) -> dict:
    features = route_state.get("features", {}) if isinstance(route_state, dict) else {}
    return features if isinstance(features, dict) else {}


def _feature_flag(route_state: dict, field: str) -> bool:
    return bool(_get_route_features(route_state).get(field))


def _get_policy_state(route_state: dict) -> dict:
    policy_state = route_state.get("policy_state", {}) if isinstance(route_state, dict) else {}
    return policy_state if isinstance(policy_state, dict) else {}


def _policy_state_flag(route_state: dict, field: str) -> bool:
    return bool(_get_policy_state(route_state).get(field))


def _has_deep_combo_request(text: str) -> bool:
    lowered = text.lower()
    combo_rules = (
        ("这套系统", "从入口到输出"),
        ("多份文档", "总路线"),
        ("所有运行报告", "修复顺序"),
        ("系统代码", "审计"),
        ("代码级", "修复方案"),
        ("完整", "路线图"),
        ("全面", "审计"),
        ("全量", "扫描"),
        ("完整修复路线图", ""),
        ("基于所有运行报告", ""),
    )
    for left, right in combo_rules:
        if left and left not in lowered:
            continue
        if right and right not in lowered:
            continue
        return True
    return False


def _looks_like_light_turn_request(text: str) -> bool:
    return _contains_any(text, _LIGHT_HINT_MARKERS)


def _looks_like_light_support_turn(text: str) -> bool:
    return _contains_any(text, _LIGHT_SUPPORT_MARKERS)


def _looks_like_relationship_concern_turn(text: str) -> bool:
    return _contains_any(text, _RELATIONSHIP_CONCERN_MARKERS)


def _looks_like_attitude_only_turn(text: str) -> bool:
    if not _contains_any(text, _ATTITUDE_ONLY_MARKERS):
        return False
    if _contains_any(text, _EXPLICIT_ACTION_MARKERS) or _contains_any(text, ("帮我写", "发我一段", "给我一段", "话术")):
        return False
    return True


def _get_policy_patch_migration_meta(route_state: dict) -> dict:
    if not isinstance(route_state, dict):
        return {"used": False, "fields": [], "reasons": []}

    meta = route_state.get("_policy_patch_migration_meta")
    if not isinstance(meta, dict):
        meta = {"used": False, "fields": [], "reasons": []}
        route_state["_policy_patch_migration_meta"] = meta
    meta.setdefault("used", False)
    meta.setdefault("fields", [])
    meta.setdefault("reasons", [])
    return meta


def _record_policy_patch_migration(route_state: dict, field: str, reason: str, used_policy_state: bool) -> None:
    meta = _get_policy_patch_migration_meta(route_state)
    _append_unique(meta["fields"], field)
    _append_unique(meta["reasons"], reason)
    if used_policy_state:
        meta["used"] = True


def _resolve_policy_patch_signal(
    route_state: dict,
    *,
    field: str,
    policy_value: bool,
    legacy_value: bool,
    policy_reason: str,
    legacy_reason: str = _POLICY_PATCH_REASONS["legacy_fallback"],
) -> bool:
    if policy_value:
        _record_policy_patch_migration(route_state, field, policy_reason, True)
        return True
    if legacy_value:
        _record_policy_patch_migration(route_state, field, legacy_reason, False)
        return True
    return False


def _looks_like_management_blocker_turn(text: str) -> bool:
    return _contains_any(text, _MANAGEMENT_BLOCKER_MARKERS)


def _looks_like_negotiation_boundary_turn(text: str) -> bool:
    return _contains_any(text, _NEGOTIATION_BOUNDARY_MARKERS)


def _looks_like_negotiation_soft_exception(text: str) -> bool:
    """纯态度/纯拖延，先别强行推到 explicit。"""
    soft_patterns = (
        "对方态度很强硬",
        "态度很强硬",
        "对方很强硬",
        "语气很硬",
        "签约总拖着",
        "不往前走",
        "一直拖着",
        "一直拖签",
        "没动静",
    )
    if not _contains_any(text, soft_patterns):
        return False
    if _contains_any(text, _EXPLICIT_ACTION_MARKERS):
        return False
    if _contains_any(text, ("怎么回", "怎么说", "怎么做", "怎么推进", "怎么处理", "给我一段", "帮我写", "发一段", "话术")):
        return False
    return True


def _infer_scene_from_history(context) -> str:
    history = list(getattr(context, "history", []) or [])
    if not history:
        return ""

    recent_texts: list[str] = []
    for item in reversed(history[-6:]):
        role = getattr(item, "role", None)
        if role not in {"user", "assistant", "ai"}:
            continue
        content = getattr(item, "content", "") or ""
        if isinstance(content, list):
            content = "".join(str(part) for part in content if part)
        text = str(content).strip()
        if text:
            recent_texts.append(text)
    if not recent_texts:
        return ""

    joined = " ".join(recent_texts[:4])
    scene_rules = [
        ("crisis", ("不想活", "想死", "撑不住", "撑不下去", "扛不住", "绝望", "自杀", "伤害自己")),
        ("negotiation", ("压价", "账期", "条件", "签约", "底线", "让步", "合作边界", "服务范围", "交付范围", "拖签")),
        ("sales", ("客户", "价格", "太贵", "竞品", "报价", "跟进", "催单", "成交", "预算")),
        ("management", ("团队", "下属", "员工", "绩效", "跨部门", "执行力", "甩锅", "不配合", "会议", "项目")),
        ("emotion", ("烦", "累", "委屈", "难受", "焦虑", "压力", "被误解", "心里堵", "有点怕", "有点慌")),
    ]
    for scene_id, markers in scene_rules:
        if any(marker in joined for marker in markers):
            return scene_id
    return ""


def _get_scene_context(context) -> set[str]:
    scenes: set[str] = set()
    primary_scene = getattr(context, "primary_scene", "") or getattr(getattr(context, "scene_config", None), "scene_id", "")
    if primary_scene:
        scenes.add(str(primary_scene))
    for item in getattr(context, "secondary_scenes", []) or []:
        if item:
            scenes.add(str(item))
    if not scenes:
        inferred_scene = _infer_scene_from_history(context)
        if inferred_scene:
            scenes.add(inferred_scene)
    return scenes


def _recent_history_texts(context, limit: int = 6) -> list[str]:
    history = list(getattr(context, "history", []) or [])
    if not history:
        return []
    recent_texts: list[str] = []
    for item in reversed(history[-limit:]):
        role = getattr(item, "role", None)
        if role not in {"user", "assistant", "ai"}:
            continue
        content = getattr(item, "content", "") or ""
        if isinstance(content, list):
            content = "".join(str(part) for part in content if part)
        text = str(content).strip()
        if text:
            recent_texts.append(text)
    return recent_texts


def _history_has_recent_crisis_signal(context) -> bool:
    recent_texts = _recent_history_texts(context, limit=6)
    if not recent_texts:
        return False
    joined = " ".join(recent_texts[:4])
    if _contains_any(joined, _CRISIS_MARKERS):
        return True
    return _contains_any(
        joined,
        (
            "不想活",
            "想死",
            "撑不住",
            "撑不下去",
            "扛不住",
            "绝望",
            "自杀",
            "伤害自己",
        ),
    )


def _looks_like_crisis_recovery_turn(text: str) -> bool:
    return _contains_any(text, _CRISIS_RECOVERY_MARKERS)


def _looks_like_crisis_continuation_turn(context, text: str) -> bool:
    if _looks_like_crisis_recovery_turn(text):
        return False
    if _contains_any(text, _CRISIS_CONTINUATION_MARKERS):
        return True
    if not _history_has_recent_crisis_signal(context):
        return False
    if _looks_like_light_support_turn(text):
        return True
    if _contains_any(text, _CONTEXTUAL_FOLLOWUP_MARKERS):
        return True
    return len(text) <= 12


def _looks_like_contextual_followup_turn(context, text: str) -> bool:
    scene_context = _get_scene_context(context)
    if not scene_context.intersection({"sales", "management", "negotiation", "emotion", "multi_scene", "crisis"}):
        return False
    if _looks_like_light_support_turn(text):
        return True
    return _contains_any(text, _CONTEXTUAL_FOLLOWUP_MARKERS)


def _looks_like_explicit_sales_or_negotiation_request(text: str) -> bool:
    sales_markers = (
        "客户",
        "价格",
        "太贵",
        "预算",
        "竞品",
        "效果",
        "值不值",
        "不回消息",
        "考虑考虑",
        "跟进",
        "催单",
        "成交",
        "报价",
    )
    negotiation_markers = (
        "对方",
        "压价",
        "账期",
        "条件",
        "签约",
        "底线",
        "让步",
        "服务",
        "合作边界",
        "态度很强硬",
        "态度强硬",
    )
    request_markers = (
        "怎么回",
        "怎么说",
        "怎么接",
        "怎么开口",
        "怎么跟进",
        "怎么做",
        "怎么推进",
        "怎么处理",
        "该怎么接",
        "该怎么做",
        "该怎么说",
        "帮我写",
        "写一句",
        "发一段",
        "给我一段",
        "话术",
        "能直接发出去",
        "守底线",
        "守住",
        "催单",
        "跟进",
        "还能不能谈",
        "还能不能再谈",
        "能不能再谈",
        "谈不谈",
        "问一句",
        "值不值",
    )
    has_scene = _contains_any(text, sales_markers) or _contains_any(text, negotiation_markers)
    has_request = _contains_any(text, request_markers)
    has_action = _contains_any(text, ("催单", "跟进", "守底线", "守住", "压价", "让步"))
    if has_scene and has_request:
        return True
    if has_scene and has_action:
        return True
    return False


def _classify_turn_load_level(context, user_input: str) -> tuple[str, str]:
    """基于现有轻重判断，映射出本阶段需要的四档负载。"""
    text = (user_input or "").strip()
    if not text:
        return "light", "empty_input"

    if any(marker in text for marker in _CRISIS_MARKERS):
        return "crisis", "crisis_marker"

    if _looks_like_crisis_recovery_turn(text):
        if _looks_like_light_turn_request(text) or _looks_like_light_support_turn(text) or len(text) <= 24:
            return "light", "crisis_recovery_light"
        return "standard", "crisis_recovery_standard"

    if _looks_like_crisis_continuation_turn(context, text):
        return "crisis", "crisis_continuation"

    if _has_deep_combo_request(text) or any(marker in text.lower() for marker in _DEEP_MARKERS):
        return "deep", "explicit_deep_request"

    has_emotion = any(token in text for token in _EMOTION_MARKERS)
    has_action = any(token in text for token in _EXPLICIT_ACTION_MARKERS)
    has_context_anchor = any(token in text for token in ["老板", "项目", "客户", "团队", "关系", "沟通", "结果", "工资", "涨薪", "合作"])
    if _looks_like_light_turn_request(text):
        if not _contains_any(text, ("审计", "修复", "路线图", "系统代码", "完整", "全量", "多份文档", "报告")):
            return "light", "explicit_light_request"

    if _looks_like_light_support_turn(text):
        if _looks_like_contextual_followup_turn(context, text):
            scene_context = _get_scene_context(context)
            if "crisis" in scene_context:
                return "crisis", "crisis_context_followup"
            return "standard", "contextual_followup_support"
        if _looks_like_negotiation_boundary_turn(text) or _contains_any(text, ("压价", "账期", "条件", "签约", "底线", "让步", "服务范围", "交付范围", "合作边界")):
            return "standard", "negotiation_support_boundary"
        if _looks_like_management_blocker_turn(text) or _contains_any(text, ("员工", "下属", "团队", "跨部门", "绩效", "项目", "会议", "沟通", "关系", "管理")):
            return "standard", "management_light_support"
        return "light", "supportive_light_turn"

    if _looks_like_management_blocker_turn(text):
        return "standard", "management_boundary_request"

    if _looks_like_negotiation_boundary_turn(text):
        return "standard", "negotiation_boundary_request"

    if _looks_like_contextual_followup_turn(context, text):
        scene_context = _get_scene_context(context)
        if "crisis" in scene_context:
            return "crisis", "crisis_context_followup"
        if scene_context.intersection({"sales", "negotiation"}):
            return "standard", "sales_negotiation_context_followup"
        if scene_context.intersection({"management", "emotion", "multi_scene"}):
            return "standard", "contextual_followup_standard"

    if has_emotion and len(text) <= 14 and not has_action and not has_context_anchor and not _contains_any(text, ("审计", "修复", "路线图", "系统代码", "完整", "全量", "多份文档", "报告")):
        return "light", "short_emotion_turn"

    if any(marker in text for marker in _STANDARD_MARKERS):
        return "standard", "explicit_standard_scene"

    if _contains_any(text, ("批评", "伤关系", "甩锅", "跑题", "拖着", "绩效沟通", "员工状态", "开会", "沟通卡住")):
        return "standard", "management_boundary_request"

    scene = getattr(context, "primary_scene", "") or getattr(getattr(context, "scene_config", None), "scene_id", "")
    has_question = any(ch in text for ch in "？?")
    has_action = any(token in text for token in _EXPLICIT_ACTION_MARKERS)
    has_context_anchor = any(token in text for token in ["老板", "项目", "客户", "团队", "关系", "沟通", "结果", "工资", "涨薪", "合作"])
    has_emotion = any(token in text for token in _EMOTION_MARKERS)

    if has_question and not has_action and not has_context_anchor and not has_emotion and len(text) <= 12:
        return "light", "simple_question"

    if has_question and (has_context_anchor or has_action) and len(text) <= 28:
        return "standard", "scene_question"

    if has_action and (has_context_anchor or len(text) >= 10) and len(text) <= 28:
        return "standard", "action_request"

    # 先复用项目里已有的轻路径判断，尽量不自己再发明一套分类器。
    if _is_light_turn(context, text, scene):
        return "light", "legacy_light_turn"

    legacy_level = _legacy_turn_load_level(context, text, scene)
    if legacy_level == "heavy":
        return "deep", "legacy_heavy_turn"
    if legacy_level == "medium":
        return "standard", "legacy_medium_turn"
    return "light", "legacy_light_turn"


def _classify_next_step_policy(context, user_input: str, turn_load_level: str) -> tuple[str, str]:
    """先只做标记，不参与本轮实际收口控制。"""
    text = (user_input or "").strip()
    if turn_load_level == "crisis":
        return "none", "crisis_safety"
    if turn_load_level == "deep":
        return "explicit", "deep_request"

    if not text:
        return "none", "empty_input"

    if text in _ACK_MARKERS:
        return "none", "acknowledge"

    if "继续" in text and len(text) <= 8:
        return "none", "continue_short"

    if _looks_like_light_support_turn(text):
        if _looks_like_contextual_followup_turn(context, text):
            scene_context = _get_scene_context(context)
            if "crisis" in scene_context:
                return "none", "crisis_context_support"
            if scene_context.intersection({"sales", "negotiation"}):
                if _contains_any(text, ("如果", "那如果", "还是", "再考虑", "怎么回", "怎么说", "怎么做", "怎么处理", "怎么推进", "话术", "发我一段", "帮我写", "给我一段", "守底线", "压价", "账期", "条件", "签约", "让步", "服务", "边界")):
                    return "explicit", "contextual_sales_negotiation_followup"
                return "soft", "contextual_sales_negotiation_support"
            if _looks_like_negotiation_boundary_turn(text) or _contains_any(text, ("压价", "账期", "条件", "签约", "底线", "让步", "服务范围", "交付范围", "合作边界")):
                return "soft", "negotiation_support_boundary"
            if scene_context.intersection({"management"}):
                return "soft", "contextual_management_support"
            if scene_context.intersection({"emotion", "multi_scene"}):
                return "soft", "contextual_emotion_support"
        if _looks_like_negotiation_boundary_turn(text) or _contains_any(text, ("压价", "账期", "条件", "签约", "底线", "让步", "服务范围", "交付范围", "合作边界")):
            return "soft", "negotiation_support_boundary"
        if _looks_like_management_blocker_turn(text) or _contains_any(text, ("员工", "下属", "团队", "跨部门", "绩效", "项目", "会议", "沟通", "关系", "管理")):
            return "soft", "management_soft_support"
        return "soft", "light_support"

    if _looks_like_contextual_followup_turn(context, text):
        scene_context = _get_scene_context(context)
        if "crisis" in scene_context:
            return "none", "crisis_context_followup"
        if scene_context.intersection({"sales", "negotiation"}):
            if _contains_any(text, ("如果", "那如果", "还是", "再考虑", "怎么回", "怎么说", "怎么做", "怎么处理", "怎么推进", "话术", "发我一段", "帮我写", "给我一段", "守底线", "压价", "账期", "条件", "签约", "让步", "服务", "边界")):
                return "explicit", "contextual_sales_negotiation_followup"
            return "soft", "contextual_sales_negotiation_support"
        if scene_context.intersection({"management"}):
            return "soft", "contextual_management_support"
        if scene_context.intersection({"emotion", "multi_scene"}):
            return "soft", "contextual_emotion_support"

    if _looks_like_management_blocker_turn(text):
        return "explicit", "management_blocker"

    if _looks_like_negotiation_boundary_turn(text):
        if _looks_like_negotiation_soft_exception(text):
            return "soft", "negotiation_soft_boundary"
        if _contains_any(text, _EXPLICIT_ACTION_MARKERS) or _looks_like_explicit_sales_or_negotiation_request(text):
            return "explicit", "negotiation_explicit_request"
        return "explicit", "negotiation_boundary_request"

    if any(marker in text for marker in _EMOTION_MARKERS):
        return "soft", "emotion_support"

    if _contains_any(text, ("怎么回", "怎么说", "怎么做", "怎么推进", "怎么处理", "给我一段", "帮我写", "发一段", "话术")) and _contains_any(text, ("压价", "账期", "条件", "签约", "底线", "让步", "服务", "合作边界", "交付范围", "服务范围")):
        return "explicit", "negotiation_explicit_request"

    if any(marker in text for marker in _EXPLICIT_ACTION_MARKERS):
        return "explicit", "action_request"

    if _looks_like_explicit_sales_or_negotiation_request(text):
        return "explicit", "sales_negotiation_request"

    if turn_load_level == "light":
        return "none", "light_turn"

    return "soft", "standard_default"


def _route_state_expected_load(route_state: dict) -> set[str]:
    risk_level = str(route_state.get("risk_level", "none") or "none")
    intent = str(route_state.get("input_intent", "unknown") or "unknown")
    needs_action = bool(route_state.get("needs_action"))
    needs_script = bool(route_state.get("needs_script"))
    needs_deep = bool(route_state.get("needs_deep"))
    needs_soft_support = bool(route_state.get("needs_soft_support"))

    if risk_level == "crisis":
        return {"crisis"}
    if needs_deep or intent == "deep_analysis":
        return {"deep"}
    if needs_action or needs_script or intent in {"ask_action", "ask_script", "ask_plan"}:
        return {"standard", "deep"}
    if needs_soft_support or intent in {"emotion_support", "chat"}:
        return {"light", "standard"}
    if intent == "explain":
        return {"light", "standard"}
    return {"light", "standard"}


def _route_state_expected_load_value(route_state: dict) -> str:
    """给 Phase 4C 用的单值预期负载，只作为观测/选择候选，不改别的逻辑。"""
    risk_level = str(route_state.get("risk_level", "none") or "none")
    intent = str(route_state.get("input_intent", "unknown") or "unknown")
    conversation_phase = str(route_state.get("conversation_phase", "new") or "new")
    main_scene = str(route_state.get("main_scene", "general") or "general")
    previous_scene = str(route_state.get("previous_scene", "") or "")
    should_inherit_scene = bool(route_state.get("should_inherit_scene"))
    needs_action = bool(route_state.get("needs_action"))
    needs_script = bool(route_state.get("needs_script"))
    needs_deep = bool(route_state.get("needs_deep"))
    needs_soft_support = bool(route_state.get("needs_soft_support"))
    secondary_scene = set(route_state.get("secondary_scene", []) or [])
    policy_state = _get_policy_state(route_state)
    has_relationship_risk = bool(policy_state.get("has_relationship_risk"))
    is_business_emotion_mixed = bool(policy_state.get("is_business_emotion_mixed"))
    is_attitude_description = bool(policy_state.get("is_attitude_description"))
    has_emotion_secondary = any(item in {"emotion", "pressure", "relationship"} for item in secondary_scene)
    is_business_scene = main_scene in {"sales", "management", "negotiation"}
    business_context_emotion_followup = (
        conversation_phase in {"followup", "revision", "objection", "continuation"}
        and previous_scene in {"sales", "management", "negotiation"}
        and (has_emotion_secondary or main_scene == "emotion" or needs_soft_support)
    )

    if risk_level == "crisis" or conversation_phase == "crisis_continuation":
        return "crisis"

    if needs_deep or intent == "deep_analysis":
        return "deep"

    if (
        is_business_scene
        and (has_emotion_secondary or is_business_emotion_mixed or has_relationship_risk)
        and risk_level != "crisis"
        and intent != "deep_analysis"
    ):
        return "standard"

    if (
        (main_scene == "management" or previous_scene == "management" or has_relationship_risk)
        and has_relationship_risk
        and risk_level != "crisis"
        and intent != "deep_analysis"
    ):
        return "standard"

    if business_context_emotion_followup and risk_level != "crisis" and intent != "deep_analysis":
        return "standard"

    if (
        (is_attitude_description or has_relationship_risk)
        and risk_level != "crisis"
        and intent != "deep_analysis"
        and not needs_deep
    ):
        return "standard"

    if (
        previous_scene in {"", "general", "unknown"}
        and main_scene == "emotion"
        and conversation_phase in {"followup", "continuation"}
        and needs_soft_support
        and not needs_action
        and not needs_script
        and not needs_deep
    ):
        return "standard"

    if needs_action or needs_script or intent in {"ask_action", "ask_script", "ask_plan"}:
        return "standard"

    if should_inherit_scene and previous_scene in {"sales", "management", "negotiation", "emotion"}:
        return "standard"

    if main_scene in {"sales", "management", "negotiation"} and conversation_phase in {"followup", "revision", "objection", "continuation"}:
        return "standard"

    if conversation_phase in {"followup", "revision", "objection", "continuation"} and previous_scene and previous_scene not in {"general", "system", "unknown"}:
        return "standard"

    if intent in {"explain", "chat", "emotion_support"} and conversation_phase == "new" and not should_inherit_scene and not needs_deep and not needs_action and not needs_script:
        return "light"

    if needs_soft_support and conversation_phase == "new" and not should_inherit_scene:
        return "light"

    if main_scene == "emotion" and conversation_phase == "new" and not should_inherit_scene and not needs_action and not needs_script and not needs_deep:
        return "light"

    return "light"


def _should_use_route_state_for_load(route_state: dict, legacy_load: str) -> tuple[bool, list[str]]:
    """只在高置信、强信号时，让 route_state 真的改掉本轮负载。"""
    reasons: list[str] = []
    confidence = float(route_state.get("confidence", 0.0) or 0.0)
    expected_load = _route_state_expected_load_value(route_state)
    risk_level = str(route_state.get("risk_level", "none") or "none")
    intent = str(route_state.get("input_intent", "unknown") or "unknown")
    conversation_phase = str(route_state.get("conversation_phase", "new") or "new")
    should_inherit_scene = bool(route_state.get("should_inherit_scene"))
    previous_scene = str(route_state.get("previous_scene", "") or "")
    needs_deep = bool(route_state.get("needs_deep"))
    needs_action = bool(route_state.get("needs_action"))
    needs_script = bool(route_state.get("needs_script"))
    main_scene = str(route_state.get("main_scene", "general") or "general")
    secondary_scene = set(route_state.get("secondary_scene", []) or [])
    needs_soft_support = bool(route_state.get("needs_soft_support"))
    policy_state = _get_policy_state(route_state)
    has_relationship_risk = bool(policy_state.get("has_relationship_risk"))
    is_business_emotion_mixed = bool(policy_state.get("is_business_emotion_mixed"))
    is_attitude_description = bool(policy_state.get("is_attitude_description"))
    has_emotion_secondary = any(item in {"emotion", "pressure", "relationship"} for item in secondary_scene)
    is_business_scene = main_scene in {"sales", "management", "negotiation"}
    is_mixed_business_emotion = is_business_scene and (
        has_emotion_secondary or is_business_emotion_mixed or has_relationship_risk
    )
    business_context_emotion_followup = (
        conversation_phase in {"followup", "revision", "objection", "continuation"}
        and previous_scene in {"sales", "management", "negotiation"}
        and (has_emotion_secondary or main_scene == "emotion" or needs_soft_support)
    )
    current_outputs = route_state.get("current_outputs", {}) if isinstance(route_state, dict) else {}
    current_policy = str(current_outputs.get("next_step_policy", "") or "").strip().lower()

    if not expected_load:
        reasons.append("expected_load_empty")
        return False, reasons

    if legacy_load == "crisis":
        reasons.append("legacy_crisis_kept")
        return False, reasons

    if risk_level == "crisis" or conversation_phase == "crisis_continuation":
        reasons.append("crisis_high_priority")
        return True, reasons

    if legacy_load == "deep" and (has_relationship_risk or is_attitude_description) and not needs_deep:
        reasons.append("route_state:relationship_concern=>standard")
        reasons.append(_ROUTE_STATE_REASONS["block_deep_attitude_relationship"])
        if has_relationship_risk:
            reasons.append(_POLICY_BOUNDARY_REASONS["relationship_block_deep"])
        if is_attitude_description:
            reasons.append(_ROUTE_STATE_REASONS["short_attitude_soft_guard"])
        return True, reasons

    if confidence < 0.75:
        reasons.append("low_confidence")
        return False, reasons

    if (
        route_state.get("risk_level") in {"low", "medium", "high", "crisis"}
        or intent in {"ask_script", "ask_action", "ask_plan", "deep_analysis", "emotion_support", "chat", "explain"}
        or conversation_phase in {"followup", "revision", "objection", "continuation", "crisis_continuation"}
        or should_inherit_scene
        or is_mixed_business_emotion
        or has_relationship_risk
        or business_context_emotion_followup
    ):
        reasons.append("strong_signal")
    else:
        reasons.append("weak_signal")
        return False, reasons

    if expected_load == "deep":
        if intent == "deep_analysis" and confidence >= 0.8:
            reasons.append("deep_analysis_high_confidence")
            return True, reasons
        reasons.append("deep_not_strong_enough")
        return False, reasons

    if expected_load == "standard":
        if legacy_load == "light" and is_mixed_business_emotion:
            reasons.append("route_state:mixed_business_emotion=>standard")
            reasons.append("route_state:block_light_for_mixed_scene")
            return True, reasons
        if legacy_load == "deep" and has_relationship_risk and not needs_deep:
            reasons.append("route_state:relationship_concern=>standard")
            reasons.append(_ROUTE_STATE_REASONS["block_deep_attitude_relationship"])
            reasons.append(_POLICY_BOUNDARY_REASONS["relationship_block_deep"])
            return True, reasons
        if legacy_load == "deep" and is_attitude_description and not needs_deep:
            reasons.append("route_state:relationship_concern=>standard")
            reasons.append(_ROUTE_STATE_REASONS["block_deep_attitude_relationship"])
            reasons.append(_ROUTE_STATE_REASONS["short_attitude_soft_guard"])
            return True, reasons
        if legacy_load == "deep" and business_context_emotion_followup and not needs_deep:
            reasons.append("route_state:business_context_emotion_followup=>standard")
            return True, reasons
        if (
            legacy_load == "deep"
            and main_scene == "emotion"
            and conversation_phase in {"followup", "continuation"}
            and needs_soft_support
            and not needs_action
            and not needs_script
            and not needs_deep
        ):
            reasons.append("route_state:business_context_emotion_followup=>standard")
            return True, reasons
        if legacy_load == "light" and (
            needs_action
            or needs_script
            or should_inherit_scene
            or conversation_phase in {"followup", "revision", "objection", "continuation"}
            or previous_scene in {"sales", "management", "negotiation", "emotion"}
            or intent in {"ask_action", "ask_script", "ask_plan"}
        ):
            reasons.append("light_to_standard_followup")
            return True, reasons
        if legacy_load in {"standard", "deep"}:
            reasons.append("standard_compatible")
            return False, reasons
        if current_policy == "explicit" and legacy_load == "light":
            reasons.append("explicit_request_promotes_standard")
            return True, reasons
        reasons.append("standard_not_strong_enough")
        return False, reasons

    if expected_load == "light":
        if is_mixed_business_emotion or has_relationship_risk or business_context_emotion_followup:
            reasons.append(_ROUTE_STATE_REASONS["fallback_legacy_load"])
            return False, reasons
        if legacy_load == "standard" and intent in {"explain", "chat", "emotion_support"} and conversation_phase == "new" and not should_inherit_scene and not needs_action and not needs_script and not needs_deep:
            reasons.append("standard_to_light_simple_turn")
            return True, reasons
        reasons.append("light_default_or_keep_legacy")
        return False, reasons

    reasons.append("no_route_override")
    return False, reasons


def _route_state_expected_policy(route_state: dict) -> set[str]:
    risk_level = str(route_state.get("risk_level", "none") or "none")
    intent = str(route_state.get("input_intent", "unknown") or "unknown")
    needs_action = bool(route_state.get("needs_action"))
    needs_script = bool(route_state.get("needs_script"))
    needs_deep = bool(route_state.get("needs_deep"))
    needs_soft_support = bool(route_state.get("needs_soft_support"))
    conversation_phase = str(route_state.get("conversation_phase", "new") or "new")

    if risk_level == "crisis":
        return {"none"}
    if needs_deep or intent == "deep_analysis":
        return {"explicit"}
    if needs_action or needs_script or intent in {"ask_action", "ask_script", "ask_plan"}:
        return {"explicit"}
    if needs_soft_support or conversation_phase in {"followup", "continuation", "crisis_continuation"}:
        return {"soft", "none"}
    if intent in {"chat", "explain"}:
        return {"none", "soft"}
    return {"soft", "none"}


def _route_state_expected_policy_value(route_state: dict) -> str:
    """给 Phase 4D 用的单值预期收口，只做观测和保守接管。"""
    policy_state_expected, _, _, policy_state_used = _policy_state_expected_policy(route_state)
    if policy_state_used and policy_state_expected:
        return policy_state_expected

    risk_level = str(route_state.get("risk_level", "none") or "none")
    intent = str(route_state.get("input_intent", "unknown") or "unknown")
    conversation_phase = str(route_state.get("conversation_phase", "new") or "new")
    main_scene = str(route_state.get("main_scene", "general") or "general")
    previous_scene = str(route_state.get("previous_scene", "") or "")
    previous_risk_level = str(route_state.get("previous_risk_level", "none") or "none")
    should_inherit_scene = bool(route_state.get("should_inherit_scene"))
    should_exit_crisis = bool(route_state.get("should_exit_crisis"))
    needs_action = bool(route_state.get("needs_action"))
    needs_script = bool(route_state.get("needs_script"))
    needs_deep = bool(route_state.get("needs_deep"))
    needs_soft_support = bool(route_state.get("needs_soft_support"))
    features = _get_route_features(route_state)
    policy_state = _get_policy_state(route_state)
    has_followup_markers = bool(features.get("has_followup_markers"))
    has_emotion_terms = bool(features.get("has_emotion_terms"))
    has_management_blocker = bool(features.get("has_management_blocker"))
    has_negotiation_boundary = bool(features.get("has_negotiation_boundary"))
    has_scene_switch_terms = bool(features.get("has_scene_switch_terms"))
    has_revision_markers = _resolve_policy_patch_signal(
        route_state,
        field="is_revision_turn",
        policy_value=bool(policy_state.get("is_revision_turn")),
        legacy_value=bool(features.get("has_revision_markers")),
        policy_reason=_POLICY_PATCH_REASONS["revision"],
    )
    has_relationship_concern = _resolve_policy_patch_signal(
        route_state,
        field="has_relationship_risk",
        policy_value=bool(policy_state.get("has_relationship_risk")),
        legacy_value=bool(features.get("has_relationship_concern")),
        policy_reason=_POLICY_PATCH_REASONS["relationship_risk"],
    )
    has_attitude_only = _resolve_policy_patch_signal(
        route_state,
        field="is_attitude_description",
        policy_value=bool(policy_state.get("is_attitude_description")),
        legacy_value=bool(features.get("has_attitude_only")),
        policy_reason=_POLICY_PATCH_REASONS["attitude_description"],
    )
    has_business_emotion_mixed = bool(features.get("has_business_emotion_mixed"))

    soft_protection_reason = _route_state_soft_protection_reason(route_state)

    if risk_level == "crisis" or conversation_phase == "crisis_continuation" or intent == "safety_support":
        return "none"

    if should_exit_crisis and previous_risk_level == "crisis" and intent in {"emotion_support", "chat", "unknown"}:
        return "soft"

    if needs_deep or intent == "deep_analysis":
        return "explicit"

    if soft_protection_reason:
        return "soft"

    if needs_action or needs_script or intent in {"ask_action", "ask_script", "ask_plan"}:
        return "explicit"

    if main_scene == "management":
        if has_management_blocker and not (has_relationship_concern or has_emotion_terms or has_revision_markers):
            return "explicit"
        if has_relationship_concern or has_emotion_terms or has_revision_markers:
            return "soft"

    if main_scene in {"sales", "negotiation"}:
        if has_revision_markers and not (needs_action or needs_script):
            return "soft"
        if has_attitude_only:
            return "soft"
        if (has_negotiation_boundary or has_scene_switch_terms) and not (has_business_emotion_mixed or has_emotion_terms):
            return "explicit"
        if has_business_emotion_mixed:
            return "soft"

    if has_scene_switch_terms and not (has_business_emotion_mixed or has_relationship_concern or has_attitude_only):
        return "explicit"

    if should_inherit_scene and previous_scene in {"sales", "management", "negotiation", "emotion"}:
        if soft_protection_reason or has_emotion_terms or needs_soft_support or has_revision_markers:
            return "soft"
        if needs_action or needs_script or has_followup_markers:
            return "explicit"

    if main_scene in {"sales", "management", "negotiation"} and conversation_phase in {"followup", "revision", "objection", "continuation"}:
        if soft_protection_reason or has_emotion_terms or needs_soft_support or has_revision_markers:
            return "soft"
        if needs_action or needs_script or has_followup_markers:
            return "explicit"
        if intent in {"emotion_support", "chat"} or needs_soft_support:
            return "soft"
        return "explicit"

    if intent in {"emotion_support", "chat"} or needs_soft_support:
        return "soft"

    if intent in {"emotion_support", "chat"} or needs_soft_support:
        return "soft"

    if intent == "explain":
        if conversation_phase in {"closure", "continuation"} and not should_inherit_scene:
            return "none"
        if not needs_action and not needs_script and not needs_deep:
            return "none"

    if conversation_phase == "closure":
        return "none"

    if conversation_phase == "continuation" and not should_inherit_scene and not needs_action and not needs_script and not needs_deep:
        return "none"

    return "soft"


def _route_state_soft_protection_reason(route_state: dict) -> str | None:
    features = _get_route_features(route_state)
    policy_state = _get_policy_state(route_state)

    conversation_phase = str(route_state.get("conversation_phase", "new") or "new")
    main_scene = str(route_state.get("main_scene", "general") or "general")
    intent = str(route_state.get("input_intent", "unknown") or "unknown")
    needs_action = bool(route_state.get("needs_action"))
    needs_script = bool(route_state.get("needs_script"))
    needs_soft_support = bool(route_state.get("needs_soft_support"))

    has_revision_markers = bool(features.get("has_revision_markers"))
    has_relationship_concern = _resolve_policy_patch_signal(
        route_state,
        field="has_relationship_risk",
        policy_value=bool(policy_state.get("has_relationship_risk")),
        legacy_value=bool(features.get("has_relationship_concern")),
        policy_reason=_POLICY_PATCH_REASONS["relationship_risk"],
    )
    has_attitude_only = _resolve_policy_patch_signal(
        route_state,
        field="is_attitude_description",
        policy_value=bool(policy_state.get("is_attitude_description")),
        legacy_value=bool(features.get("has_attitude_only")),
        policy_reason=_POLICY_PATCH_REASONS["attitude_description"],
    )
    has_business_emotion_mixed = bool(features.get("has_business_emotion_mixed"))
    has_emotion_terms = bool(features.get("has_emotion_terms"))
    wants_softening = _resolve_policy_patch_signal(
        route_state,
        field="wants_softening",
        policy_value=bool(policy_state.get("wants_softening")),
        legacy_value=conversation_phase == "revision" or has_revision_markers,
        policy_reason=_POLICY_PATCH_REASONS["softening"],
    )
    is_revision_turn = _resolve_policy_patch_signal(
        route_state,
        field="is_revision_turn",
        policy_value=bool(policy_state.get("is_revision_turn")),
        legacy_value=conversation_phase == "revision" or has_revision_markers,
        policy_reason=_POLICY_PATCH_REASONS["revision"],
    )

    if is_revision_turn or wants_softening:
        return _SOFT_PROTECTION_REASONS["revision"]
    if has_relationship_concern:
        return _SOFT_PROTECTION_REASONS["relationship_concern"]
    if has_attitude_only:
        return _SOFT_PROTECTION_REASONS["attitude_only"]
    if has_business_emotion_mixed and main_scene in {"sales", "management", "negotiation"}:
        if intent not in {"ask_script"} and not needs_script and not (needs_action and not needs_soft_support):
            return _SOFT_PROTECTION_REASONS["business_emotion_mixed"]
    if main_scene == "management" and has_emotion_terms and intent not in {"ask_script"} and not needs_script:
        return _SOFT_PROTECTION_REASONS["relationship_concern"]
    return None


def _build_policy_state(route_state: dict) -> dict:
    features = route_state.get("features", {}) if isinstance(route_state, dict) else {}
    if not isinstance(features, dict):
        features = {}

    intent = str(route_state.get("input_intent", "unknown") or "unknown")
    phase = str(route_state.get("conversation_phase", "new") or "new")
    risk_level = str(route_state.get("risk_level", "none") or "none")
    needs_action = bool(route_state.get("needs_action"))
    needs_script = bool(route_state.get("needs_script"))
    needs_deep = bool(route_state.get("needs_deep"))
    needs_soft_support = bool(route_state.get("needs_soft_support"))
    should_exit_crisis = bool(route_state.get("should_exit_crisis"))

    wants_script = needs_script or intent == "ask_script" or bool(features.get("has_script_request"))
    wants_action = needs_action or intent == "ask_action" or bool(features.get("has_action_request"))
    wants_plan = needs_deep or intent in {"ask_plan", "deep_analysis"} or bool(features.get("has_deep_analysis_terms"))
    wants_softening = phase == "revision" or bool(features.get("has_revision_markers"))
    has_relationship_risk = bool(features.get("has_relationship_concern"))
    is_attitude_description = bool(features.get("has_attitude_only"))
    is_business_emotion_mixed = bool(features.get("has_business_emotion_mixed"))
    is_revision_turn = phase == "revision" or bool(features.get("has_revision_markers"))
    is_scene_switch_question = bool(features.get("has_scene_switch_terms"))
    is_contextual_followup = phase in {"followup", "revision", "objection", "continuation", "crisis_continuation"} or bool(features.get("has_followup_markers"))
    is_safety_or_crisis = risk_level == "crisis" or intent == "safety_support" or phase == "crisis_continuation"
    is_crisis_recovery = should_exit_crisis

    should_prefer_none = (
        not is_safety_or_crisis
        and intent in {"explain", "unknown"}
        and phase in {"new", "closure"}
        and not wants_script
        and not wants_action
        and not wants_plan
        and not needs_soft_support
    )

    should_prefer_soft = any(
        (
            wants_softening,
            has_relationship_risk,
            is_attitude_description,
            is_business_emotion_mixed,
            intent in {"emotion_support", "chat"},
            needs_soft_support,
            is_crisis_recovery,
        )
    )

    soft_guard = any(
        (
            wants_softening,
            has_relationship_risk,
            is_attitude_description,
            is_business_emotion_mixed and not wants_action and not wants_script,
        )
    )
    should_prefer_explicit = (
        not is_safety_or_crisis
        and not soft_guard
        and (
            wants_script
            or wants_action
            or wants_plan
            or intent in {"ask_script", "ask_action", "ask_plan", "deep_analysis"}
        )
    )

    if is_safety_or_crisis:
        should_prefer_none = True
        should_prefer_soft = False
        should_prefer_explicit = False
    elif is_crisis_recovery:
        should_prefer_none = False
        should_prefer_soft = True
        should_prefer_explicit = False

    return {
        "wants_push": wants_action or wants_plan,
        "wants_script": wants_script,
        "wants_action": wants_action,
        "wants_plan": wants_plan,
        "wants_softening": wants_softening,
        "has_relationship_risk": has_relationship_risk,
        "is_attitude_description": is_attitude_description,
        "is_business_emotion_mixed": is_business_emotion_mixed,
        "is_revision_turn": is_revision_turn,
        "is_scene_switch_question": is_scene_switch_question,
        "is_contextual_followup": is_contextual_followup,
        "is_safety_or_crisis": is_safety_or_crisis,
        "is_crisis_recovery": is_crisis_recovery,
        "should_prefer_none": should_prefer_none,
        "should_prefer_soft": should_prefer_soft,
        "should_prefer_explicit": should_prefer_explicit,
    }


def _build_policy_state_alignment(route_state: dict) -> dict:
    current_outputs = route_state.get("current_outputs", {}) if isinstance(route_state, dict) else {}
    actual_policy = str(current_outputs.get("next_step_policy", "") or "").strip().lower()
    policy_state = route_state.get("policy_state", {}) if isinstance(route_state, dict) else {}

    prefers_none = bool(policy_state.get("should_prefer_none"))
    prefers_soft = bool(policy_state.get("should_prefer_soft"))
    prefers_explicit = bool(policy_state.get("should_prefer_explicit"))
    notes: list[str] = []

    if prefers_soft and prefers_explicit:
        notes.append("policy_state_conflict_soft_and_explicit")
    if prefers_none and actual_policy not in {"none", ""}:
        notes.append(f"policy_state_prefers_none_but_current_{actual_policy}")
    if prefers_soft and actual_policy == "explicit":
        notes.append("policy_state_prefers_soft_but_current_explicit")
    if prefers_explicit and actual_policy == "soft":
        notes.append("policy_state_prefers_explicit_but_current_soft")
    if prefers_explicit and actual_policy == "none":
        notes.append("policy_state_prefers_explicit_but_current_none")
    if bool(policy_state.get("is_business_emotion_mixed")) and actual_policy == "explicit":
        notes.append("policy_state_business_emotion_mixed_current_explicit")

    preferred = []
    if prefers_none:
        preferred.append("none")
    if prefers_soft:
        preferred.append("soft")
    if prefers_explicit:
        preferred.append("explicit")

    return {
        "policy_state_matches_current_policy": actual_policy in preferred if preferred else True,
        "notes": notes,
    }


def _policy_state_expected_policy(route_state: dict) -> tuple[str | None, list[str], list[str], bool]:
    policy_state = _get_policy_state(route_state)
    features = _get_route_features(route_state)
    intent = str(route_state.get("input_intent", "unknown") or "unknown")
    needs_action = bool(route_state.get("needs_action"))
    needs_script = bool(route_state.get("needs_script"))
    needs_deep = bool(route_state.get("needs_deep"))

    is_safety_or_crisis = bool(policy_state.get("is_safety_or_crisis"))
    is_crisis_recovery = bool(policy_state.get("is_crisis_recovery"))
    wants_script = _resolve_policy_patch_signal(
        route_state,
        field="wants_script",
        policy_value=bool(policy_state.get("wants_script")),
        legacy_value=needs_script or intent == "ask_script" or bool(features.get("has_script_request")),
        policy_reason=_POLICY_PATCH_REASONS["script"],
        legacy_reason=_POLICY_PATCH_REASONS["script_legacy"],
    )
    wants_action = _resolve_policy_patch_signal(
        route_state,
        field="wants_action",
        policy_value=bool(policy_state.get("wants_action")),
        legacy_value=needs_action or intent == "ask_action" or bool(features.get("has_action_request")),
        policy_reason=_POLICY_PATCH_REASONS["action"],
        legacy_reason=_POLICY_PATCH_REASONS["action_legacy"],
    )
    wants_plan = bool(policy_state.get("wants_plan"))
    wants_softening = bool(policy_state.get("wants_softening"))
    has_relationship_risk = bool(policy_state.get("has_relationship_risk"))
    is_attitude_description = bool(policy_state.get("is_attitude_description"))
    is_business_emotion_mixed = bool(policy_state.get("is_business_emotion_mixed"))
    is_revision_turn = bool(policy_state.get("is_revision_turn"))

    fields_used: list[str] = []
    reasons: list[str] = []
    used_policy_state = False

    if is_safety_or_crisis:
        fields_used.append("is_safety_or_crisis")
        reasons.append("policy_state:safety_or_crisis=>none")
        return "none", reasons, fields_used, True

    if is_crisis_recovery:
        fields_used.append("is_crisis_recovery")
        reasons.append("policy_state:crisis_recovery=>soft")
        return "soft", reasons, fields_used, True

    soft_protection = []
    if wants_softening:
        soft_protection.append(("wants_softening", "policy_state:soft_signal_observed_fallback_legacy"))
    if has_relationship_risk:
        soft_protection.append(("has_relationship_risk", "policy_state:soft_signal_observed_fallback_legacy"))
    if is_attitude_description:
        soft_protection.append(("is_attitude_description", "policy_state:soft_signal_observed_fallback_legacy"))
    if is_business_emotion_mixed:
        soft_protection.append(("is_business_emotion_mixed", "policy_state:soft_signal_observed_fallback_legacy"))
    if is_revision_turn:
        soft_protection.append(("is_revision_turn", "policy_state:soft_signal_observed_fallback_legacy"))

    strong_explicit_fields = []
    if wants_script:
        strong_explicit_fields.append(("wants_script", "policy_state:strong_signal_script=>explicit"))
    if wants_action:
        strong_explicit_fields.append(("wants_action", "policy_state:strong_signal_action=>explicit"))
    if wants_plan:
        strong_explicit_fields.append(("wants_plan", "policy_state:strong_signal_plan=>explicit"))

    if strong_explicit_fields:
        if soft_protection and not wants_plan:
            field, reason = soft_protection[0]
            fields_used.append(field)
            reasons.append(reason)
            reasons.append(_POLICY_PATCH_REASONS["soft_protection_preserved"])
            return None, reasons, fields_used, False
        field, reason = strong_explicit_fields[0]
        fields_used.append(field)
        reasons.append(reason)
        return "explicit", reasons, fields_used, True

    if soft_protection:
        field, reason = soft_protection[0]
        fields_used.append(field)
        reasons.append(reason)
        return None, reasons, fields_used, False

    return None, ["policy_state:fallback_to_legacy"], fields_used, used_policy_state


def _split_policy_state_metric(
    *,
    legacy_policy: str,
    policy_state_expected_policy: str | None,
    final_policy: str,
    policy_decision_source: str,
    route_state_used_for_policy: bool,
    route_state: dict,
    policy_state_expected_policy_reason: list[str] | None,
) -> tuple[bool, bool, str, list[str], bool]:
    """把“观察一致”和“真正接管”拆开记，只影响 trace 统计。"""
    reasons = list(policy_state_expected_policy_reason or [])
    risk_level = str(route_state.get("risk_level", "none") or "none") if isinstance(route_state, dict) else "none"
    phase = str(route_state.get("conversation_phase", "new") or "new") if isinstance(route_state, dict) else "new"

    observed_alignment = False
    actual_takeover = False
    takeover_type = "none"
    metric_reasons: list[str] = []

    if (
        policy_state_expected_policy is not None
        and legacy_policy == policy_state_expected_policy == final_policy
        and policy_decision_source == "legacy_fallback"
        and not route_state_used_for_policy
    ):
        observed_alignment = True
        takeover_type = "alignment"
        metric_reasons.append("policy_state:observed_alignment_with_legacy")
        return observed_alignment, actual_takeover, takeover_type, metric_reasons, False

    is_safety_context = risk_level == "crisis" or phase == "crisis_continuation"
    if is_safety_context and route_state_used_for_policy and final_policy == "none":
        actual_takeover = True
        takeover_type = "safety"
        metric_reasons.append("policy_state:safety_actual_takeover")
        return observed_alignment, actual_takeover, takeover_type, metric_reasons, True

    if any("crisis_recovery" in reason for reason in reasons) and route_state_used_for_policy and final_policy == "soft":
        actual_takeover = True
        takeover_type = "crisis_recovery"
        metric_reasons.append("policy_state:crisis_recovery_actual_takeover")
        return observed_alignment, actual_takeover, takeover_type, metric_reasons, True

    if any("soft_protection" in reason for reason in reasons) and legacy_policy == "explicit" and final_policy == "soft":
        actual_takeover = True
        takeover_type = "soft_protection"
        metric_reasons.append("policy_state:soft_protection_actual_takeover")
        return observed_alignment, actual_takeover, takeover_type, metric_reasons, True

    if (
        policy_state_expected_policy is not None
        and legacy_policy != policy_state_expected_policy
        and route_state_used_for_policy
        and final_policy == policy_state_expected_policy
    ):
        actual_takeover = True
        takeover_type = "actual"
        metric_reasons.append("policy_state:actual_takeover")
        return observed_alignment, actual_takeover, takeover_type, metric_reasons, True

    metric_reasons.append("policy_state:no_metric_takeover")
    return observed_alignment, actual_takeover, takeover_type, metric_reasons, False


def _should_use_route_state_for_policy(route_state: dict, legacy_policy: str) -> tuple[bool, list[str]]:
    """只在高置信、强信号时，让 route_state 真的改掉本轮收口。"""
    reasons: list[str] = []
    confidence = float(route_state.get("confidence", 0.0) or 0.0)
    expected_policy = _route_state_expected_policy_value(route_state)
    policy_state = route_state.get("policy_state", {}) if isinstance(route_state, dict) else {}
    if not isinstance(policy_state, dict):
        policy_state = {}
    risk_level = str(route_state.get("risk_level", "none") or "none")
    intent = str(route_state.get("input_intent", "unknown") or "unknown")
    conversation_phase = str(route_state.get("conversation_phase", "new") or "new")
    should_inherit_scene = bool(route_state.get("should_inherit_scene"))
    should_exit_crisis = bool(route_state.get("should_exit_crisis"))
    previous_scene = str(route_state.get("previous_scene", "") or "")
    needs_action = bool(route_state.get("needs_action"))
    needs_script = bool(route_state.get("needs_script"))
    needs_deep = bool(route_state.get("needs_deep"))
    needs_soft_support = bool(route_state.get("needs_soft_support"))
    has_revision_markers = bool((route_state.get("features", {}) if isinstance(route_state, dict) else {}).get("has_revision_markers"))
    current_outputs = route_state.get("current_outputs", {}) if isinstance(route_state, dict) else {}
    current_policy = str(current_outputs.get("next_step_policy", "") or "").strip().lower()
    soft_protection_reason = _route_state_soft_protection_reason(route_state)
    alignment_notes = []
    alignment = route_state.get("alignment", {})
    if isinstance(alignment, dict):
        alignment_notes = list(alignment.get("notes", []) or [])

    if not expected_policy:
        reasons.append("expected_policy_empty")
        return False, reasons

    if risk_level == "crisis" or conversation_phase == "crisis_continuation":
        reasons.append("crisis_priority")
        return True, reasons

    if should_exit_crisis and previous_scene:
        reasons.append("crisis_recovery")
        return True, reasons

    if bool(policy_state.get("is_safety_or_crisis")):
        reasons.append("policy_state_safety_or_crisis")
        return True, reasons

    if bool(policy_state.get("is_crisis_recovery")):
        reasons.append("policy_state_crisis_recovery")
        return True, reasons

    policy_state_expected, policy_state_reasons, policy_state_fields_used, policy_state_used = _policy_state_expected_policy(route_state)
    wants_softening = bool(policy_state.get("wants_softening"))
    is_revision_turn = bool(policy_state.get("is_revision_turn"))
    has_relationship_risk = bool(policy_state.get("has_relationship_risk"))
    is_attitude_description = bool(policy_state.get("is_attitude_description"))
    explicit_signal = any(
        (
            bool(policy_state.get("wants_script")),
            bool(policy_state.get("wants_action")),
            bool(policy_state.get("wants_plan")),
        )
    )
    soft_signal = any(
        (
            wants_softening,
            has_relationship_risk,
            is_attitude_description,
            bool(policy_state.get("is_business_emotion_mixed")),
            is_revision_turn,
            bool(policy_state.get("is_crisis_recovery")),
        )
    )
    short_softening_guard = (
        expected_policy == "soft"
        and not explicit_signal
        and not needs_action
        and not needs_script
        and not needs_deep
        and risk_level != "crisis"
        and (
            wants_softening
            or is_revision_turn
            or has_relationship_risk
            or is_attitude_description
        )
    )

    if any(
        note in alignment_notes
        for note in ("ask_script_but_policy_not_explicit", "ask_action_but_policy_not_explicit", "deep_analysis_but_policy_not_explicit")
    ):
        reasons.append("alignment_mismatch_override")
        return True, reasons

    if short_softening_guard and legacy_policy == "none":
        if wants_softening or is_revision_turn:
            reasons.append("policy_boundary_fix:short_softening=>soft")
        elif is_attitude_description:
            reasons.append("policy_boundary_fix:attitude_only=>soft")
        elif has_relationship_risk:
            reasons.append("policy_boundary_fix:relationship_risk_block_explicit")
        return True, reasons

    if short_softening_guard and legacy_policy == "explicit":
        if wants_softening or is_revision_turn:
            reasons.append("policy_boundary_fix:short_softening=>soft")
        elif is_attitude_description:
            reasons.append("policy_boundary_fix:attitude_only=>soft")
        elif has_relationship_risk:
            reasons.append("policy_boundary_fix:relationship_risk_block_explicit")
        return True, reasons

    if confidence < 0.75:
        reasons.append("low_confidence")
        return False, reasons

    if expected_policy == legacy_policy:
        reasons.append("already_aligned")
        return False, reasons

    if policy_state_used and soft_signal and not explicit_signal and expected_policy == "soft" and legacy_policy == "none":
        reasons.extend(policy_state_reasons)
        reasons.append("policy_state_soft_support_upgrade")
        return True, reasons

    if soft_protection_reason:
        if expected_policy == "explicit" and legacy_policy in {"soft", "none"}:
            reasons.append("policy_state:weak_signal_fallback_legacy")
            reasons.append(soft_protection_reason)
            reasons.append("policy_block_upgrade:soft_to_explicit")
            return False, reasons
        if legacy_policy == "explicit" and expected_policy == "soft":
            reasons.append("policy_state:soft_protection_downgrade_explicit_to_soft")
            reasons.append(soft_protection_reason)
            reasons.append("policy_downgrade:explicit_to_soft")
            return True, reasons

    if expected_policy == "explicit":
        if policy_state_used and not explicit_signal:
            reasons.extend(policy_state_reasons)
            reasons.append("policy_state_explicit_not_strong_enough")
            return False, reasons
        if intent in {"deep_analysis", "ask_action", "ask_script", "ask_plan"}:
            reasons.append(f"intent_{intent}")
            return True, reasons
        if needs_action or needs_script or needs_deep:
            reasons.append("needs_action_script_deep")
            return True, reasons
        if should_inherit_scene and previous_scene in {"sales", "management", "negotiation", "emotion"}:
            reasons.append("inherited_followup")
            return True, reasons
        if conversation_phase in {"followup", "revision", "objection", "continuation"} and route_state.get("main_scene") in {"sales", "management", "negotiation"}:
            reasons.append("business_followup")
            return True, reasons
        if current_policy in {"none", "soft"}:
            reasons.append("upgrade_to_explicit")
            return True, reasons
        reasons.append("explicit_not_strong_enough")
        return False, reasons

    if expected_policy == "soft":
        if policy_state_used and soft_signal:
            reasons.extend(policy_state_reasons)
        if legacy_policy == "none" and (intent in {"emotion_support", "chat"} or needs_soft_support or should_exit_crisis):
            reasons.append("none_to_soft_support")
            return True, reasons
        if legacy_policy == "explicit" and (intent in {"emotion_support", "chat"} or needs_soft_support or has_revision_markers or should_exit_crisis):
            reasons.append("explicit_downgrade_to_soft")
            return True, reasons
        if current_policy == "none" and (intent in {"emotion_support", "chat"} or needs_soft_support or has_revision_markers):
            reasons.append("none_to_soft_current")
            return True, reasons
        reasons.append("soft_not_strong_enough")
        return False, reasons

    if expected_policy == "none":
        if legacy_policy != "none" and (
            risk_level == "crisis"
            or conversation_phase == "crisis_continuation"
            or intent in {"safety_support", "explain"}
            or (conversation_phase == "closure" and not should_inherit_scene)
        ):
            reasons.append("safety_or_closure_none")
            return True, reasons
        if legacy_policy != "none" and current_policy in {"soft", "explicit"} and intent in {"explain", "chat"} and not should_inherit_scene and not needs_action and not needs_script and not needs_deep:
            reasons.append("short_answer_none")
            return True, reasons
        reasons.append("none_not_strong_enough")
        return False, reasons

    reasons.append("no_policy_override")
    return False, reasons


def _build_route_state_alignment(route_state: dict) -> dict:
    current_outputs = route_state.get("current_outputs", {}) if isinstance(route_state, dict) else {}
    actual_load = str(current_outputs.get("turn_load_level", "") or "").strip().lower()
    actual_policy = str(current_outputs.get("next_step_policy", "") or "").strip().lower()
    risk_level = str(route_state.get("risk_level", "none") or "none")

    expected_load = _route_state_expected_load(route_state)
    expected_policy = _route_state_expected_policy(route_state)

    notes: list[str] = []
    load_matches_intent = actual_load in expected_load if actual_load else False
    next_policy_matches_intent = actual_policy in expected_policy if actual_policy else False
    crisis_matches_risk = True

    if risk_level == "crisis":
        crisis_matches_risk = actual_load == "crisis" and actual_policy == "none"
        if not crisis_matches_risk:
            notes.append("risk_crisis_but_actual_not_crisis_path")
    elif actual_load == "crisis":
        crisis_matches_risk = False
        notes.append("actual_crisis_but_risk_not_crisis")

    if not load_matches_intent:
        notes.append(f"load_expected={sorted(expected_load)}")
    if not next_policy_matches_intent:
        notes.append(f"policy_expected={sorted(expected_policy)}")
    intent = str(route_state.get("input_intent", "unknown") or "unknown")
    if intent == "ask_script" and actual_policy != "explicit":
        notes.append("ask_script_but_policy_not_explicit")
    if intent == "ask_action" and actual_policy != "explicit":
        notes.append("ask_action_but_policy_not_explicit")
    if intent == "deep_analysis" and actual_policy != "explicit":
        notes.append("deep_analysis_but_policy_not_explicit")

    phase = str(route_state.get("conversation_phase", "new") or "new")
    previous_scene = str(route_state.get("previous_scene", "") or "")
    if phase in {"followup", "revision", "continuation"} and previous_scene and actual_load == "light":
        notes.append("followup_with_previous_scene_but_actual_light")
    if phase == "crisis_continuation" and actual_load != "crisis":
        notes.append("crisis_continuation_but_actual_not_crisis")
    if phase == "crisis_continuation" and actual_policy != "none":
        notes.append("crisis_continuation_but_policy_not_none")
    if phase in {"followup", "revision", "continuation"} and previous_scene and actual_policy == "none":
        notes.append("followup_with_previous_scene_but_actual_none")

    return {
        "load_matches_intent": load_matches_intent,
        "next_policy_matches_intent": next_policy_matches_intent,
        "crisis_matches_risk": crisis_matches_risk,
        "notes": notes,
    }


def build_route_state(user_input, context=None, runtime_trace=None, current_outputs=None):
    """把现有路由判断整理成一份结构化快照，只观察，不参与决策。"""
    text = (user_input or "").strip()
    current_outputs = dict(current_outputs or {})
    runtime_trace = runtime_trace if isinstance(runtime_trace, dict) else {}

    scene_context = _get_scene_context(context) if context is not None else set()
    previous_scene = ""
    if context is not None:
        previous_scene = (
            getattr(context, "primary_scene", "")
            or getattr(getattr(context, "scene_config", None), "scene_id", "")
            or _infer_scene_from_history(context)
            or ""
        )

    previous_risk_level = "crisis" if context is not None and _history_has_recent_crisis_signal(context) else "none"
    has_crisis_terms = any(marker in text for marker in _CRISIS_MARKERS)
    has_crisis_continuation_markers = _contains_any(text, _CRISIS_CONTINUATION_MARKERS)
    has_crisis_recovery_markers = _looks_like_crisis_recovery_turn(text)
    has_followup_markers = _contains_any(text, _CONTEXTUAL_FOLLOWUP_MARKERS)
    if context is not None and _looks_like_contextual_followup_turn(context, text):
        has_followup_markers = True
    revision_markers = (
        "太硬",
        "太冲",
        "会不会太重",
        "会不会太硬",
        "软一点",
        "稳一点",
        "换个说法",
        "别那么重",
        "别那么硬",
        "更自然",
        "更短",
        "别太长",
        "别太啰嗦",
        "改一下",
        "调整一下",
    )
    has_revision_markers = _contains_any(text, revision_markers)
    has_action_request = _contains_any(text, _EXPLICIT_ACTION_MARKERS)
    has_script_request = _contains_any(text, ("帮我写", "写一句", "发一段", "给我一段", "话术", "能直接发出去"))
    has_deep_analysis_terms = _has_deep_combo_request(text) or any(marker in text.lower() for marker in _DEEP_MARKERS)
    has_light_request = _looks_like_light_turn_request(text)
    has_emotion_terms = _contains_any(text, _EMOTION_MARKERS) or _looks_like_light_support_turn(text)

    sales_terms = ("客户", "价格", "太贵", "竞品", "报价", "跟进", "催单", "成交", "预算", "不回消息")
    management_terms = ("团队", "下属", "员工", "绩效", "跨部门", "执行力", "甩锅", "不配合", "会议", "项目")
    negotiation_terms = ("压价", "账期", "条件", "签约", "底线", "让步", "服务范围", "交付范围", "合作边界", "拖签", "拉长")
    system_terms = ("系统", "代码", "审计", "报告", "路线图", "全量", "文档", "修复", "入口到输出")

    has_sales_terms = _contains_any(text, sales_terms)
    has_management_terms = _contains_any(text, management_terms) or _looks_like_management_blocker_turn(text)
    has_negotiation_terms = _contains_any(text, negotiation_terms) or _looks_like_negotiation_boundary_turn(text)
    has_system_terms = _contains_any(text, system_terms)
    has_management_blocker = _looks_like_management_blocker_turn(text) or _contains_any(text, ("拖着", "不交", "卡住", "甩锅", "不配合", "跑题", "执行力差", "执行力很差", "总是拖", "沟通卡住", "结果交不出来"))
    has_negotiation_boundary = _looks_like_negotiation_boundary_turn(text) or _contains_any(text, ("压价", "账期", "条件", "签约", "底线", "让步", "服务范围", "交付范围", "合作边界"))
    has_scene_switch_terms = _contains_any(text, ("更像", "不只是", "不是销售", "不是谈判", "而是", "这是不是")) and _contains_any(text, ("销售", "谈判", "管理", "情绪", "客户", "团队", "下属", "员工", "项目"))
    has_relationship_concern = _looks_like_relationship_concern_turn(text)
    has_attitude_only = _looks_like_attitude_only_turn(text)
    has_business_emotion_mixed = (
        (has_sales_terms or has_management_terms or has_negotiation_terms)
        and has_emotion_terms
        and not has_crisis_terms
    )

    if has_crisis_terms:
        risk_level = "crisis"
    elif previous_risk_level == "crisis" and not has_crisis_recovery_markers:
        risk_level = "crisis"
    elif has_deep_analysis_terms:
        risk_level = "high"
    elif has_emotion_terms:
        risk_level = "medium" if len(text) >= 12 else "low"
    elif has_action_request or has_script_request:
        risk_level = "medium"
    else:
        risk_level = "none"

    if risk_level == "crisis" and has_crisis_recovery_markers:
        should_exit_crisis = True
    else:
        should_exit_crisis = has_crisis_recovery_markers

    if risk_level == "crisis":
        conversation_phase = "crisis_continuation"
    elif has_revision_markers:
        conversation_phase = "revision"
    elif has_followup_markers:
        conversation_phase = "followup"
    elif _contains_any(text, tuple(_ACK_MARKERS)) or (text and len(text) <= 8 and "继续" in text):
        conversation_phase = "continuation"
    elif text in {"谢谢", "好的", "好", "行", "可以", "收到"}:
        conversation_phase = "closure"
    else:
        conversation_phase = "new"

    input_intent = "unknown"
    if risk_level == "crisis" or has_crisis_terms or has_crisis_continuation_markers:
        input_intent = "safety_support"
    elif has_deep_analysis_terms:
        input_intent = "deep_analysis"
    elif has_script_request:
        input_intent = "ask_script"
    elif has_action_request:
        input_intent = "ask_action"
    elif _contains_any(text, ("路线图", "计划", "安排", "方案", "修复顺序")):
        input_intent = "ask_plan"
    elif has_emotion_terms:
        input_intent = "emotion_support"
    elif _contains_any(text, ("什么意思", "怎么理解", "简单说", "讲重点", "这是什么意思")):
        input_intent = "explain"
    elif _contains_any(text, tuple(_ACK_MARKERS)) or "继续" in text:
        input_intent = "chat"
    elif has_light_request:
        input_intent = "chat"

    main_scene = "general"
    secondary_scene: list[str] = []
    if risk_level == "crisis" or has_crisis_terms or has_crisis_continuation_markers:
        main_scene = "system"
        secondary_scene.extend(["emotion", "pressure"])
    elif has_system_terms or has_deep_analysis_terms:
        main_scene = "system"
    elif has_negotiation_terms:
        main_scene = "negotiation"
    elif has_sales_terms:
        main_scene = "sales"
    elif has_management_terms:
        main_scene = "management"
    elif has_emotion_terms:
        main_scene = "emotion"

    if main_scene in {"sales", "negotiation"} and has_emotion_terms:
        secondary_scene.append("emotion")
        secondary_scene.append("pressure")
    if main_scene == "management" and has_emotion_terms:
        secondary_scene.append("emotion")
        secondary_scene.append("relationship")
    if main_scene == "emotion" and (has_action_request or has_script_request):
        secondary_scene.append("pressure")
    if has_followup_markers and previous_scene and previous_scene not in {"general", "system", "unknown"}:
        should_inherit_scene = True
        if main_scene in {"general", "unknown"}:
            main_scene = previous_scene
    else:
        should_inherit_scene = False

    if not previous_scene:
        previous_scene = _infer_scene_from_history(context) if context is not None else ""

    needs_deep = input_intent == "deep_analysis" or has_deep_analysis_terms
    needs_action = input_intent in {"ask_action", "ask_plan"} or has_action_request
    needs_script = input_intent == "ask_script" or has_script_request
    needs_soft_support = input_intent in {"emotion_support", "chat"} or has_emotion_terms
    needs_memory = conversation_phase in {"followup", "revision", "continuation", "crisis_continuation"} or needs_deep or needs_action or needs_script

    if not secondary_scene and previous_scene and should_inherit_scene:
        if previous_scene != main_scene:
            secondary_scene.append(previous_scene)

    # 去重但保留顺序感
    dedup_secondary: list[str] = []
    for item in secondary_scene:
        if item and item not in dedup_secondary and item != main_scene:
            dedup_secondary.append(item)
    secondary_scene = dedup_secondary

    confidence = 0.4
    if risk_level == "crisis":
        confidence = 0.95 if has_crisis_terms or has_crisis_continuation_markers else 0.9
    elif needs_deep:
        confidence = 0.9
    elif needs_action or needs_script:
        confidence = 0.8
    elif should_inherit_scene or has_followup_markers:
        confidence = 0.75
    elif main_scene != "general":
        confidence = 0.65
    elif needs_soft_support:
        confidence = 0.6

    scene_terms_count = sum(bool(flag) for flag in [has_sales_terms, has_management_terms, has_negotiation_terms, has_emotion_terms, has_system_terms])
    if scene_terms_count > 1:
        confidence = max(0.45, confidence - 0.08 * (scene_terms_count - 1))

    if has_crisis_recovery_markers:
        confidence = max(confidence, 0.82)
    if has_light_request:
        confidence = min(confidence + 0.03, 0.98)
    if main_scene == "emotion" and needs_soft_support and conversation_phase == "new" and not should_inherit_scene:
        confidence = max(confidence, 0.78 if len(text) <= 16 else 0.72)
    if main_scene == "management" and has_management_blocker:
        confidence = max(confidence, 0.83)
    if has_scene_switch_terms:
        confidence = max(confidence, 0.8)
    if main_scene in {"sales", "negotiation"} and (has_negotiation_boundary or has_scene_switch_terms or (has_sales_terms and has_negotiation_terms)):
        confidence = max(confidence, 0.8)
    if main_scene in {"sales", "negotiation"} and has_emotion_terms and (has_negotiation_boundary or has_followup_markers or should_inherit_scene):
        confidence = max(confidence, 0.78)
    if main_scene == "management" and has_emotion_terms and not has_management_blocker:
        confidence = max(confidence, 0.78)
    if has_relationship_concern:
        confidence = max(confidence, 0.8)
    if has_followup_markers:
        followup_floor = 0.75
        if should_inherit_scene or previous_scene or main_scene in {"sales", "management", "negotiation", "emotion"}:
            followup_floor = 0.8
        confidence = max(confidence, followup_floor)
    if main_scene in {"sales", "management", "negotiation"} and (
        has_action_request
        or has_script_request
        or has_revision_markers
        or has_followup_markers
    ):
        confidence = max(confidence, 0.8)

    confidence = max(0.35, min(confidence, 0.98))

    features = {
        "has_crisis_terms": has_crisis_terms,
        "has_crisis_continuation_markers": has_crisis_continuation_markers,
        "has_crisis_recovery_markers": has_crisis_recovery_markers,
        "has_followup_markers": has_followup_markers,
        "has_revision_markers": has_revision_markers,
        "has_action_request": has_action_request,
        "has_script_request": has_script_request,
        "has_deep_analysis_terms": has_deep_analysis_terms,
        "has_light_request": has_light_request,
        "has_emotion_terms": has_emotion_terms,
        "has_sales_terms": has_sales_terms,
        "has_management_terms": has_management_terms,
        "has_negotiation_terms": has_negotiation_terms,
        "has_system_terms": has_system_terms,
        "has_management_blocker": has_management_blocker,
        "has_negotiation_boundary": has_negotiation_boundary,
        "has_scene_switch_terms": has_scene_switch_terms,
        "has_relationship_concern": has_relationship_concern,
        "has_attitude_only": has_attitude_only,
        "has_business_emotion_mixed": has_business_emotion_mixed,
    }

    route_state = {
        "risk_level": risk_level,
        "input_intent": input_intent,
        "conversation_phase": conversation_phase,
        "main_scene": main_scene,
        "secondary_scene": secondary_scene,
        "previous_scene": previous_scene or None,
        "previous_risk_level": previous_risk_level or None,
        "needs_memory": needs_memory,
        "needs_action": needs_action,
        "needs_script": needs_script,
        "needs_deep": needs_deep,
        "needs_soft_support": needs_soft_support,
        "should_inherit_scene": should_inherit_scene,
        "should_exit_crisis": should_exit_crisis,
        "confidence": confidence,
        "features": features,
        "current_outputs": {
            "turn_load_level": str(current_outputs.get("turn_load_level") or getattr(context, "turn_load_level", "standard") or "standard"),
            "next_step_policy": str(current_outputs.get("next_step_policy") or getattr(context, "next_step_policy", "soft") or "soft"),
            "step8_mode": str(current_outputs.get("step8_mode") or runtime_trace.get("step8_mode") or "pending"),
            "step9_mode": str(current_outputs.get("step9_mode") or runtime_trace.get("step9_mode") or "pending"),
        },
        "explanation": [],
    }
    route_state["policy_state"] = _build_policy_state(route_state)

    explanation: list[str] = []
    if has_crisis_terms:
        explanation.append("risk:crisis_terms")
    if has_crisis_continuation_markers:
        explanation.append("risk:crisis_continuation_markers")
    if has_crisis_recovery_markers:
        explanation.append("risk:crisis_recovery_markers")
    if has_followup_markers:
        explanation.append("phase:followup_marker")
    if has_revision_markers:
        explanation.append("phase:revision_marker")
    if should_inherit_scene:
        explanation.append("scene:inherit_previous")
    if has_action_request:
        explanation.append("intent:ask_action")
    if has_script_request:
        explanation.append("intent:ask_script")
    if has_deep_analysis_terms:
        explanation.append("intent:deep_analysis")
    if has_emotion_terms:
        explanation.append("intent:emotion_support")
    if has_light_request:
        explanation.append("intent:light_request")
    if main_scene != "general":
        explanation.append(f"scene:{main_scene}")
    if secondary_scene:
        explanation.append(f"scene_secondary:{'+'.join(secondary_scene[:3])}")
    if needs_memory or needs_action or needs_script or needs_deep or needs_soft_support:
        need_parts = []
        if needs_memory:
            need_parts.append("memory")
        if needs_action:
            need_parts.append("action")
        if needs_script:
            need_parts.append("script")
        if needs_deep:
            need_parts.append("deep")
        if needs_soft_support:
            need_parts.append("soft_support")
        explanation.append(f"needs:{'+'.join(need_parts)}")
    if should_exit_crisis:
        explanation.append("crisis:exit_candidate")
    route_state["explanation"] = explanation

    alignment = _build_route_state_alignment(route_state)
    route_state["alignment"] = alignment
    route_state["policy_state_alignment"] = _build_policy_state_alignment(route_state)
    return route_state


def _init_runtime_trace(context, turn_load_level: str = "standard", next_step_policy: str = "soft") -> dict:
    """只初始化仪表盘，不改任何业务流程。"""
    trace = getattr(context, "runtime_trace", None)
    if not isinstance(trace, dict):
        trace = {
            "turn_load_level": turn_load_level,
            "next_step_policy": next_step_policy,
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
            "memory_read_sources": [],
            "memory_write_targets": [],
            "memory_chars_loaded": 0,
            "memory_chars_in_prompt": 0,
            "memory_gate_decision": {},
            "memory_skipped_reason": [],
            "memory_write_reason": [],
            "memory_read_latency_ms": {},
            "memory_write_latency_ms": {},
            "memory_read_detail": [],
            "memory_write_detail": [],
            "session_note_size": 0,
            "session_note_count": 0,
            "long_term_memory_size": 0,
            "long_term_memory_count": 0,
            "memory_duplicate_detected": False,
            "memory_pollution_risk": [],
            "memory_prompt_blocks": [],
            "memory_used_in_output_observed": "unknown",
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
            "semantic_extract_skipped_reason": [],
            "semantic_extract_input_chars": 0,
            "semantic_extract_result_count": 0,
            "semantic_extract_stored_count": 0,
            "semantic_extract_latency_ms": 0.0,
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
            "output_path": "fallback",
        }
        _set_runtime_field(context, "runtime_trace", trace)
        return trace

    trace.setdefault("turn_load_level", turn_load_level)
    trace.setdefault("next_step_policy", next_step_policy)
    trace.setdefault("llm_call_count", 0)
    trace.setdefault("memory_mode", "minimal")
    trace.setdefault("memory_read_count", 0)
    trace.setdefault("memory_write_count", 0)
    trace.setdefault("skill_loaded_count", 0)
    trace.setdefault("prompt_blocks", [])
    trace.setdefault("prompt_chars_estimate", 0)
    trace.setdefault("step8_mode", "full")
    trace.setdefault("step9_mode", "full")
    trace.setdefault("unified_context_loaded", False)
    trace.setdefault("route_state", {})
    trace.setdefault("route_state_alignment", {})
    trace.setdefault("policy_state", {})
    trace.setdefault("policy_state_prefer", {"none": False, "soft": False, "explicit": False})
    trace.setdefault("policy_state_alignment", {})
    trace.setdefault("policy_state_observed_alignment", False)
    trace.setdefault("policy_state_actual_takeover", False)
    trace.setdefault("policy_state_takeover_type", "none")
    trace.setdefault("policy_state_metric_reason", [])
    trace.setdefault("policy_state_used_for_expected_policy", False)
    trace.setdefault("policy_state_expected_policy_reason", [])
    trace.setdefault("policy_state_fields_used", [])
    trace.setdefault("load_decision_source", "legacy_fallback")
    trace.setdefault("legacy_turn_load_level", "standard")
    trace.setdefault("route_state_expected_load", "standard")
    trace.setdefault("route_state_used_for_load", False)
    trace.setdefault("route_state_load_reason", [])
    trace.setdefault("policy_decision_source", "legacy_fallback")
    trace.setdefault("legacy_next_step_policy", "soft")
    trace.setdefault("route_state_expected_policy", "soft")
    trace.setdefault("route_state_used_for_policy", False)
    trace.setdefault("route_state_policy_reason", [])
    trace.setdefault("crisis_continuation_source", "none")
    trace.setdefault("memory_read_sources", [])
    trace.setdefault("memory_write_targets", [])
    trace.setdefault("memory_chars_loaded", 0)
    trace.setdefault("memory_chars_in_prompt", 0)
    trace.setdefault("memory_gate_decision", {})
    trace.setdefault("memory_skipped_reason", [])
    trace.setdefault("memory_write_reason", [])
    trace.setdefault("memory_read_latency_ms", {})
    trace.setdefault("memory_write_latency_ms", {})
    trace.setdefault("memory_read_detail", [])
    trace.setdefault("memory_write_detail", [])
    trace.setdefault("session_note_size", 0)
    trace.setdefault("session_note_count", 0)
    trace.setdefault("long_term_memory_size", 0)
    trace.setdefault("long_term_memory_count", 0)
    trace.setdefault("memory_duplicate_detected", False)
    trace.setdefault("memory_pollution_risk", [])
    trace.setdefault("memory_prompt_blocks", [])
    trace.setdefault("memory_used_in_output_observed", "unknown")
    trace.setdefault("memory_continuity_constraint_used", False)
    trace.setdefault("memory_continuity_constraint_type", "none")
    trace.setdefault("memory_continuity_constraint_position", "none")
    trace.setdefault("memory_focus_reflected_in_first_paragraph", "unknown")
    trace.setdefault("memory_focus_generic_opening_detected", False)
    trace.setdefault("memory_focus_quality_score", 0)
    trace.setdefault("memory_focus_has_decision_bias", False)
    trace.setdefault("memory_focus_has_must_use_points", False)
    trace.setdefault("memory_focus_disabled_reason", [])
    trace.setdefault("memory_focus_source_fields", [])
    trace.setdefault("session_note_quality_score", 0)
    trace.setdefault("next_pickup_quality_score", 0)
    trace.setdefault("world_state_quality_score", 0)
    trace.setdefault("focus_source_quality", {})
    trace.setdefault("focus_material_has_decision_point", False)
    trace.setdefault("focus_material_has_recommended_bias", False)
    trace.setdefault("focus_material_too_generic", False)
    trace.setdefault("memory_material_has_recommended_answer", False)
    trace.setdefault("memory_material_has_risk_if_wrong", False)
    trace.setdefault("memory_material_has_next_action", False)
    trace.setdefault("next_pickup_first_sentence_ready", False)
    trace.setdefault("world_state_decision_card_ready", False)
    trace.setdefault("semantic_extract_skipped_reason", [])
    trace.setdefault("semantic_extract_input_chars", 0)
    trace.setdefault("semantic_extract_result_count", 0)
    trace.setdefault("semantic_extract_stored_count", 0)
    trace.setdefault("semantic_extract_latency_ms", 0.0)
    trace.setdefault("latency_ms", {})
    trace.setdefault("llm_call_detail", [])
    trace.setdefault("llm_call_success_count", 0)
    trace.setdefault("llm_call_fail_count", 0)
    trace.setdefault("llm_fallback_count", 0)
    trace.setdefault("llm_provider", "unknown")
    trace.setdefault("llm_model", "")
    trace.setdefault("llm_endpoint_configured", False)
    trace.setdefault("llm_error_type", [])
    trace.setdefault("llm_error_stage", [])
    trace.setdefault("llm_retry_count", 0)
    trace.setdefault("llm_fast_path_disabled", False)
    trace.setdefault("llm_normal_path_used", False)
    trace.setdefault("output_path", "fallback")
    return trace


def _detect_response_mode(context, user_input: str) -> tuple[str, str]:
    """
    默认普通模式，只有明显复杂时才升级深度模式。
    """
    text = (user_input or "").strip()
    if not text:
        return "ordinary", "empty_input"

    if getattr(context, "short_utterance", False):
        return "ordinary", "short_utterance"

    user_rounds = sum(1 for item in context.history if item.role == "user")

    deep_markers = [
        "怎么办", "怎么做", "如何", "为什么", "怎么选", "帮我分析", "给我方案",
        "拆一下", "下一步", "该不该", "要不要", "我该怎么", "怎么推进",
    ]
    scene_markers = [
        "客户", "报价", "成交", "竞品", "预算", "底线", "条款", "让步", "协商",
        "老板", "团队", "下属", "汇报", "跨部门", "执行",
    ]

    # 第一轮先轻承接，别一上来就把最重深链全开。
    # 只有明显高价值业务问题，才允许首轮直接进深度模式。
    if user_rounds == 0:
        hard_deep_markers = [
            "帮我分析", "给我方案", "拆一下", "如何", "为什么", "怎么选",
            "复盘", "总结", "真正想", "核心是", "问题是",
        ]
        if any(marker in text for marker in scene_markers) and any(marker in text for marker in hard_deep_markers):
            return "deep", "first_turn_high_value_scene"
        return "ordinary", "first_turn_light_first"

    if len(text) >= 24 and any(marker in text for marker in deep_markers):
        return "deep", "explicit_analysis_request"
    if any(marker in text for marker in scene_markers) and any(marker in text for marker in deep_markers):
        return "deep", "high_value_scene_request"

    if len(text) >= 40:
        return "deep", "long_complex_input"

    if user_rounds >= 4 and any(marker in text for marker in ["还是", "一直", "反复", "卡住", "拿不定", "想不清"]):
        return "deep", "multi_turn_stuck"

    return "ordinary", "default_light_path"


def step0_receive_input(state: GraphState) -> GraphState:
    """Step 0：接收用户输入"""
    context = state["context"]
    user_input = state["user_input"]
    runtime_trace = _init_runtime_trace(context)

    # 每轮重置短句标记
    context.short_utterance = False
    context.info_density_low = False
    context.short_utterance_reason = ""
    context.guidance_needed = False
    context.guidance_focus = ""
    context.guidance_prompt = ""
    context.response_mode = "ordinary"
    context.response_mode_reason = ""
    context.dialogue_task = "clarify"
    context.dialogue_task_reason = ""

    # 引导冷却：避免连续多轮都在补问身份/情境
    if getattr(context, "guidance_cooldown", 0) > 0:
        context.guidance_cooldown -= 1

    stripped = user_input.strip()
    QUICK_RESPONSES = {"好的", "收到", "谢谢", "嗯", "OK", "ok", "行", "可以", "好", "嗯嗯"}
    if stripped in QUICK_RESPONSES:
        context.short_utterance = True
        context.info_density_low = True
        context.short_utterance_reason = "quick_ack"
        context.output = "嗯，我在。你要是想继续，我们接着说；如果想先停一下，也可以。"
    elif _is_meta_identity_question(stripped):
        context.short_utterance = True
        context.info_density_low = True
        context.short_utterance_reason = "meta_identity"
        context.output = "我是基于GPT-4架构的对话模型。你如果愿意，可以直接告诉我你现在想解决什么。"
    else:
        # 极短输入（≤3 字且无情绪词）
        EMOTION_WORDS = {"烦", "气", "急", "怕", "恨", "累", "烦", "怒", "哭", "愁", "难", "惨"}
        if len(stripped) <= 3 and not any(w in stripped for w in EMOTION_WORDS):
            context.short_utterance = True
            context.info_density_low = True
            context.short_utterance_reason = "ultra_short"
            context.output = "我在。你可以再多说一点，我帮你接住。"

    # 重复输入检测
    if len(context.history) >= 2:
        last_user_input = None
        for item in reversed(context.history[:-1]):
            if item.role == "user":
                last_user_input = item.content
                break
        if last_user_input and stripped == last_user_input.strip():
            context.short_utterance = True
            context.info_density_low = True
            context.short_utterance_reason = "repeat"

    # 处理上一轮反馈（如果不是第一轮）
    if len(context.history) > 0:
        from utils.feedback import process_feedback
        state = process_feedback(state, user_input)

    user_rounds = sum(1 for item in context.history if item.role == "user")

    # 没有历史时，先别急着读整套会话笔记，省掉新会话第一句的冷启动开销
    if not context.short_utterance and user_rounds > 0:
        from modules.memory import load_session_notes, get_session_context, get_session_note_stats

        read_started_at = time.perf_counter()
        load_session_notes(context.session_id)
        context.session_notes_context = get_session_context(context.session_id, limit=1)
        note_stats = get_session_note_stats(context.session_id)
        preloaded_session_meta = {
            "source": "step0",
            "chars": _estimate_text_chars(context.session_notes_context),
            "count": int(note_stats.get("count", 0) or 0),
            "timestamp": time.time(),
        }
        _set_runtime_field(context, "preloaded_session_context", context.session_notes_context or "")
        _set_runtime_field(context, "preloaded_session_notes_meta", preloaded_session_meta)
        _record_memory_read_trace(
            context,
            stage="step0",
            source="session_notes",
            mode="preload",
            chars=_estimate_text_chars(context.session_notes_context),
            count=note_stats.get("count", 0),
            latency_ms=(time.perf_counter() - read_started_at) * 1000,
        )
        _set_memory_stats(
            context,
            session_note_size=note_stats.get("chars", 0),
            session_note_count=note_stats.get("count", 0),
        )
        runtime_trace["memory_read_count"] = int(runtime_trace.get("memory_read_count", 0) or 0) + 1
        runtime_trace["memory_read_count_effective"] = int(runtime_trace.get("memory_read_count_effective", 0) or 0) + 1
    else:
        _set_runtime_field(context, "preloaded_session_context", "")
        _set_runtime_field(context, "preloaded_session_notes_meta", {})
        _record_memory_skip_reason(context, "step0:session_notes_skipped_short_or_first_turn")

    context.response_mode, context.response_mode_reason = _detect_response_mode(context, user_input)

    legacy_turn_load_level, turn_load_reason = _classify_turn_load_level(context, user_input)
    legacy_next_step_policy, next_step_reason = _classify_next_step_policy(context, user_input, legacy_turn_load_level)
    _set_runtime_field(context, "turn_load_level", legacy_turn_load_level)
    _set_runtime_field(context, "next_step_policy", legacy_next_step_policy)
    if legacy_turn_load_level in {"light", "crisis"}:
        runtime_trace["memory_mode"] = "minimal"
        runtime_trace["unified_context_loaded"] = False
        runtime_trace["memory_read_count"] = int(runtime_trace.get("memory_read_count", 0) or 0)
    runtime_trace["legacy_turn_load_level"] = legacy_turn_load_level
    runtime_trace["legacy_next_step_policy"] = legacy_next_step_policy
    runtime_trace["next_step_policy"] = legacy_next_step_policy
    route_state = build_route_state(
        user_input,
        context=context,
        runtime_trace=runtime_trace,
        current_outputs={
            "turn_load_level": legacy_turn_load_level,
            "next_step_policy": legacy_next_step_policy,
            "step8_mode": runtime_trace.get("step8_mode", "pending"),
            "step9_mode": runtime_trace.get("step9_mode", "pending"),
        },
    )
    route_state_expected_load = _route_state_expected_load_value(route_state)
    use_route_state_for_load, route_state_load_reason = _should_use_route_state_for_load(route_state, legacy_turn_load_level)
    final_turn_load_level = route_state_expected_load if use_route_state_for_load else legacy_turn_load_level
    if legacy_turn_load_level == "crisis":
        final_turn_load_level = "crisis"
        use_route_state_for_load = False
        route_state_load_reason = ["legacy_crisis_kept"]
    elif final_turn_load_level == "crisis":
        # 危机是硬安全闸，单独记路径，不把它算进 route_state 常规接管比例里。
        use_route_state_for_load = False
        if not route_state_load_reason:
            route_state_load_reason = ["crisis_hard_gate"]
        elif "crisis_hard_gate" not in route_state_load_reason:
            route_state_load_reason = list(route_state_load_reason) + ["crisis_hard_gate"]
    elif final_turn_load_level == "light" and legacy_turn_load_level != "light":
        # 轻路径本来就是保守兜底，route_state 只是帮忙确认，不计入“接管”比例。
        use_route_state_for_load = False
        if not route_state_load_reason:
            route_state_load_reason = ["light_soft_path"]
        elif "light_soft_path" not in route_state_load_reason:
            route_state_load_reason = list(route_state_load_reason) + ["light_soft_path"]

    policy_state_expected_policy, policy_state_expected_policy_reason, policy_state_fields_used, policy_state_used_for_expected_policy = _policy_state_expected_policy(route_state)
    route_state_expected_policy = _route_state_expected_policy_value(route_state)
    use_route_state_for_policy, route_state_policy_reason = _should_use_route_state_for_policy(route_state, legacy_next_step_policy)
    final_next_step_policy = route_state_expected_policy if use_route_state_for_policy else legacy_next_step_policy
    if legacy_turn_load_level == "crisis" or route_state.get("risk_level") == "crisis" or route_state.get("conversation_phase") == "crisis_continuation":
        final_next_step_policy = "none"
        use_route_state_for_policy = True
        if "crisis_priority" not in route_state_policy_reason:
            route_state_policy_reason = list(route_state_policy_reason) + ["crisis_priority"]
    elif final_next_step_policy == "none" and legacy_next_step_policy != "none" and route_state.get("input_intent") in {"explain", "chat"}:
        use_route_state_for_policy = False if not use_route_state_for_policy else use_route_state_for_policy

    if final_turn_load_level == "crisis" and final_next_step_policy != "none":
        final_next_step_policy = "none"
        if "crisis_hard_gate" not in route_state_policy_reason:
            route_state_policy_reason = list(route_state_policy_reason) + ["crisis_hard_gate"]

    policy_decision_source = "route_state" if use_route_state_for_policy else "legacy_fallback"
    (
        policy_state_observed_alignment,
        policy_state_actual_takeover,
        policy_state_takeover_type,
        policy_state_metric_reason,
        policy_state_used_for_expected_policy,
    ) = _split_policy_state_metric(
        legacy_policy=legacy_next_step_policy,
        policy_state_expected_policy=policy_state_expected_policy,
        final_policy=final_next_step_policy,
        policy_decision_source=policy_decision_source,
        route_state_used_for_policy=use_route_state_for_policy,
        route_state=route_state,
        policy_state_expected_policy_reason=policy_state_expected_policy_reason,
    )

    route_state.setdefault("current_outputs", {})
    route_state["current_outputs"]["turn_load_level"] = final_turn_load_level
    route_state["current_outputs"]["next_step_policy"] = final_next_step_policy
    route_state["alignment"] = _build_route_state_alignment(route_state)
    route_state["policy_state"] = _build_policy_state(route_state)
    route_state["policy_state_alignment"] = _build_policy_state_alignment(route_state)
    patch_migration_meta = _get_policy_patch_migration_meta(route_state)
    policy_patch_migration_used = bool(patch_migration_meta.get("used"))
    policy_patch_migration_fields = list(patch_migration_meta.get("fields", []) or [])
    policy_patch_migration_reason = list(patch_migration_meta.get("reasons", []) or [])

    runtime_trace["turn_load_level"] = final_turn_load_level
    runtime_trace["load_decision_source"] = "route_state" if use_route_state_for_load else "legacy_fallback"
    runtime_trace["route_state_expected_load"] = route_state_expected_load
    runtime_trace["route_state_used_for_load"] = use_route_state_for_load
    runtime_trace["route_state_load_reason"] = route_state_load_reason
    runtime_trace["policy_decision_source"] = policy_decision_source
    runtime_trace["route_state_expected_policy"] = route_state_expected_policy
    runtime_trace["route_state_used_for_policy"] = use_route_state_for_policy
    runtime_trace["route_state_policy_reason"] = route_state_policy_reason
    runtime_trace["policy_state_observed_alignment"] = policy_state_observed_alignment
    runtime_trace["policy_state_actual_takeover"] = policy_state_actual_takeover
    runtime_trace["policy_state_takeover_type"] = policy_state_takeover_type
    runtime_trace["policy_state_metric_reason"] = policy_state_metric_reason
    runtime_trace["policy_state_used_for_expected_policy"] = policy_state_used_for_expected_policy
    runtime_trace["policy_state_expected_policy_reason"] = policy_state_expected_policy_reason
    runtime_trace["policy_state_fields_used"] = policy_state_fields_used
    runtime_trace["policy_patch_migration_used"] = policy_patch_migration_used
    runtime_trace["policy_patch_migration_fields"] = policy_patch_migration_fields
    runtime_trace["policy_patch_migration_reason"] = policy_patch_migration_reason
    runtime_trace["crisis_continuation_source"] = (
        "route_state"
        if route_state.get("risk_level") == "crisis" or route_state.get("conversation_phase") == "crisis_continuation"
        else "legacy"
        if legacy_turn_load_level == "crisis"
        else "none"
    )
    runtime_trace["next_step_policy"] = final_next_step_policy
    load_meta = {
        "load_decision_source": runtime_trace["load_decision_source"],
        "legacy_turn_load_level": legacy_turn_load_level,
        "route_state_expected_load": route_state_expected_load,
        "route_state_used_for_load": use_route_state_for_load,
        "route_state_load_reason": route_state_load_reason,
    }
    policy_meta = {
        "policy_decision_source": runtime_trace["policy_decision_source"],
        "legacy_next_step_policy": legacy_next_step_policy,
        "route_state_expected_policy": route_state_expected_policy,
        "route_state_used_for_policy": use_route_state_for_policy,
        "route_state_policy_reason": route_state_policy_reason,
        "policy_state_observed_alignment": policy_state_observed_alignment,
        "policy_state_actual_takeover": policy_state_actual_takeover,
        "policy_state_takeover_type": policy_state_takeover_type,
        "policy_state_metric_reason": policy_state_metric_reason,
        "policy_state_used_for_expected_policy": policy_state_used_for_expected_policy,
        "policy_state_expected_policy_reason": policy_state_expected_policy_reason,
        "policy_state_fields_used": policy_state_fields_used,
        "policy_patch_migration_used": policy_patch_migration_used,
        "policy_patch_migration_fields": policy_patch_migration_fields,
        "policy_patch_migration_reason": policy_patch_migration_reason,
        "crisis_continuation_source": runtime_trace["crisis_continuation_source"],
    }
    runtime_trace["_route_state_load_meta"] = load_meta
    runtime_trace["_route_state_policy_meta"] = policy_meta
    runtime_trace["route_state"] = route_state
    runtime_trace["route_state_alignment"] = route_state.get("alignment", {})
    runtime_trace["policy_state"] = route_state.get("policy_state", {})
    runtime_trace["policy_state_prefer"] = {
        "none": bool(route_state.get("policy_state", {}).get("should_prefer_none")),
        "soft": bool(route_state.get("policy_state", {}).get("should_prefer_soft")),
        "explicit": bool(route_state.get("policy_state", {}).get("should_prefer_explicit")),
    }
    runtime_trace["policy_state_alignment"] = route_state.get("policy_state_alignment", {})
    runtime_trace["route_state_confidence"] = route_state.get("confidence", 0.0)
    runtime_trace["route_state_intent"] = route_state.get("input_intent", "unknown")
    runtime_trace["route_state_phase"] = route_state.get("conversation_phase", "new")
    runtime_trace["route_state_scene"] = route_state.get("main_scene", "general")
    runtime_trace["route_state_secondary_scene"] = route_state.get("secondary_scene", [])
    state["turn_load_level"] = final_turn_load_level
    state["next_step_policy"] = final_next_step_policy
    state["route_state"] = route_state
    state["runtime_trace"] = runtime_trace
    state["_route_state_load_meta"] = load_meta
    state["_route_state_policy_meta"] = policy_meta
    _set_runtime_field(context, "route_state", route_state)
    _set_runtime_field(context, "turn_load_level", final_turn_load_level)
    _set_runtime_field(context, "next_step_policy", final_next_step_policy)
    _set_runtime_field(context, "_route_state_load_meta", load_meta)
    _set_runtime_field(context, "_route_state_policy_meta", policy_meta)

    # 添加到历史
    context.add_history("user", user_input)

    # 【阶段二优化】History 超 50 条时触发摘要压缩
    if len(context.history) >= 50 and not context.history_summary:
        context.history_summary = _generate_history_summary(context)
        # 压缩 history：保留前 3 条 + 最近 20 条
        context.history = context.history[:3] + context.history[-20:]

    return {
        **state,
        "context": context,
        "skip_to_end": context.short_utterance_reason in {"quick_ack", "ultra_short", "meta_identity"},
    }


def _is_meta_identity_question(text: str) -> bool:
    """很轻的自我介绍/能力边界询问，直接短路，不进重链。"""
    if not text:
        return False
    if "模型" in text and ("你是" in text or "你是什么" in text):
        return True
    if "你是谁" in text or "你能做什么" in text or "你的能力" in text:
        return True
    if "基于什么" in text and "你" in text:
        return True
    return False
