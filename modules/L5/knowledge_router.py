"""
Human-OS Engine - L5 知识路由

基于总控 v4.0 Step 6 路径 B/C 的规则。
根据输入类型、主题领域和当前场景，返回更贴近的 L5 模块内容。
"""

from dataclasses import dataclass

from modules.L5.loader import (
    search_knowledge,
    search_cases,
    CASE_DATABASE,
)


@dataclass
class KnowledgeResult:
    """知识查询结果"""
    module_name: str
    content: str
    confidence: float
    title: str = ""


@dataclass
class CaseMatchResult:
    """案例匹配结果"""
    title: str
    content: str
    confidence: float
    source_file: str
    core_purpose: str = ""
    tactical_sequence: list[str] | None = None
    emergency_plan: str = ""
    quick_principle: str = ""
    continuation_hints: list[str] | None = None  # 方向B: 多轮延续提示


INPUT_TYPE_MODULES: dict[str, list[str]] = {
    "问题咨询": ["11-人生方法论模块-内核层", "12-人生方法论模块-交互层", "13-人生方法论模块-规则层"],
    "情绪表达": ["11-人生方法论模块-内核层", "25-能量系统模块-崩溃模型与修复路径"],
    "场景描述": ["15-人性工程师模块-实战案例-上", "16-人性工程师模块-实战案例-下"],
    "混合": [],
}

DOMAIN_HINTS: dict[str, dict[str, list[str]]] = {
    "life": {
        "keywords": ["情绪", "焦虑", "愤怒", "控制", "认知", "关系", "成长", "长期", "坚持", "拖延", "习惯", "价值", "人生"],
        "modules": ["11-人生方法论模块-内核层", "12-人生方法论模块-交互层", "13-人生方法论模块-规则层"],
    },
    "energy": {
        "keywords": ["崩溃", "耗竭", "撑不住", "失眠", "恢复", "疲惫", "精力", "能量", "扛不住", "burnout", "刷手机", "停不下来", "边界", "不敢拒绝", "破防", "老好人", "透支", "没行动力"],
        "modules": ["24-能量系统模块-注意力分配与模式策略", "25-能量系统模块-崩溃模型与修复路径"],
    },
    "marketing": {
        "keywords": ["转化", "营销", "销售", "成交", "客户", "获客", "ROI", "流量", "品牌", "定价", "谈判", "预算", "价格"],
        "modules": [
            "17-人性营销模块-七宗罪与认知偏差",
            "18-人性营销模块-赚钱铁律与关系构建",
            "19-人性营销模块-人群透镜与反脆弱",
            "20-人性营销模块-情绪操盘与仪式感设计",
            "21-人性营销模块-社会原力与实战工具",
        ],
    },
}

EMOTION_CASE_HINTS = {
    "利益价值": ["老板", "领导", "客户", "价格", "预算", "谈判", "下属", "员工"],
    "情绪价值": ["伴侣", "老公", "老婆", "朋友", "借钱", "PUA", "贬低", "吵架", "关系"],
}


def _detect_domains(user_input: str, input_type: str, goal_type: str = "", scene_id: str = "") -> list[str]:
    text = user_input.lower()
    scores = {domain: 0 for domain in DOMAIN_HINTS}

    if input_type == "问题咨询":
        scores["life"] += 1
    if input_type == "情绪表达":
        scores["energy"] += 1
    if scene_id in {"sales", "management", "negotiation"}:
        scores["marketing"] += 2
    if goal_type == "情绪价值":
        scores["life"] += 1
    if goal_type == "利益价值":
        scores["marketing"] += 1

    for domain, meta in DOMAIN_HINTS.items():
        scores[domain] += sum(1 for kw in meta["keywords"] if kw in text)

    ranked = [domain for domain, score in sorted(scores.items(), key=lambda item: item[1], reverse=True) if score > 0]
    return ranked[:2]


def query_knowledge(
    user_input: str,
    input_type: str = "问题咨询",
    goal_type: str = "",
    scene_id: str = "",
    context=None,
) -> KnowledgeResult | None:
    """
    查询知识库。

    规则：
    1. 先按输入类型给基础倾向
    2. 再按具体主题词做领域矫正
    3. 最后在候选结果里选最贴近的条目
    4. 方向B: trigger_conditions和priority_scenes加分
    """
    results = search_knowledge(user_input, limit=8)
    if not results:
        return None

    detected_domains = _detect_domains(user_input, input_type, goal_type=goal_type, scene_id=scene_id)

    preferred_modules = []
    if detected_domains:
        primary_domain = detected_domains[0]
        preferred_modules.extend(DOMAIN_HINTS[primary_domain]["modules"])

    for module_name in INPUT_TYPE_MODULES.get(input_type, []):
        if module_name not in preferred_modules:
            preferred_modules.append(module_name)

    for domain in detected_domains:
        for module_name in DOMAIN_HINTS[domain]["modules"]:
            if module_name not in preferred_modules:
                preferred_modules.append(module_name)

    # 方向B: 从context提取当前状态用于trigger匹配
    current_emotion = ""
    current_desires = []
    current_stage = ""
    current_position = ""
    if context:
        current_emotion = context.user.emotion.type.value if hasattr(context.user.emotion.type, "value") else str(context.user.emotion.type)
        dom_desire, _ = context.user.desires.get_dominant()
        current_desires = [dom_desire] if dom_desire else []
        current_stage = getattr(context, "situation_stage", "")
        current_position = getattr(context.user, "relationship_position", "")

    best_entry = None
    best_score = -1.0

    for entry in results:
        score = 0.0
        if any(module in entry.source_file for module in preferred_modules):
            score += 3.0
        for index, domain in enumerate(detected_domains):
            if any(module in entry.source_file for module in DOMAIN_HINTS[domain]["modules"]):
                score += 2.5 if index == 0 else 1.5
        score += sum(1 for kw in entry.keywords if kw in user_input.lower())

        # 方向B: trigger_conditions加分
        tc = getattr(entry, "trigger_conditions", None)
        if tc and context:
            if current_emotion and current_emotion in tc.get("emotion_types", []):
                score += 2.0
            if any(d in tc.get("desires", []) for d in current_desires):
                score += 1.5
            if current_stage and current_stage in tc.get("situation_stages", []):
                score += 1.5
            if current_position and current_position in tc.get("relationship_positions", []):
                score += 1.5

        # 方向B: priority_scenes加分
        ps = getattr(entry, "priority_scenes", None)
        if ps and scene_id and scene_id in ps:
            score += 2.0

        if score > best_score:
            best_score = score
            best_entry = entry

    if not best_entry:
        best_entry = results[0]

    confidence = 0.75
    if best_score >= 5:
        confidence = 0.92
    elif best_score >= 3:
        confidence = 0.85

    # 方向B: 如果有action_mapping，附加到content末尾
    content = best_entry.content
    am = getattr(best_entry, "action_mapping", "")
    if am:
        content = f"{content}\n\n[策略指引] {am}"

    # 方向C-2: 注入避坑提示
    if context and scene_id:
        try:
            from modules.L5.counter_example_lib import get_failure_hints
            goal_str = getattr(context.goal, "granular_goal", "") if hasattr(context, "goal") else ""
            hints = get_failure_hints(scene_id, goal_str)
            if hints:
                content = f"{content}\n\n" + "\n".join(hints)
        except Exception:
            pass

    return KnowledgeResult(
        module_name=best_entry.source_file.replace(".md", ""),
        title=best_entry.title,
        content=content,
        confidence=confidence,
    )


def match_case_detail(user_input: str, context=None) -> CaseMatchResult | None:
    """
    匹配案例，并返回真正可用的案例内容。
    """
    if context is None:
        results = search_cases(user_input, limit=1)
        if results:
            entry = results[0]
            return CaseMatchResult(
                title=entry.title,
                content=entry.content,
                confidence=0.7,
                source_file=entry.source_file,
                core_purpose=getattr(entry, "core_purpose", ""),
                tactical_sequence=getattr(entry, "tactical_sequence", []),
                emergency_plan=getattr(entry, "emergency_plan", ""),
                quick_principle=getattr(entry, "quick_principle", ""),
            )
        return None

    user_emotion = context.user.emotion.type.value if hasattr(context.user.emotion.type, "value") else str(context.user.emotion.type)
    dominant_desire, _ = context.user.desires.get_dominant()
    resistance_type = context.user.resistance.type.value if hasattr(context.user.resistance.type, "value") else str(context.user.resistance.type)
    goal_type = context.goal.current.type

    best_score = 0.0
    best_entry = None

    for entry in CASE_DATABASE.values():
        score = 0.0
        matched_fields = 0

        if user_emotion in entry.emotion_types:
            matched_fields += 1
            score += 1.5

        if dominant_desire in entry.desires:
            matched_fields += 1
            score += 1.0

        if resistance_type != "null" and resistance_type != "ResistanceType.NONE":
            resistance_to_desire = {
                "恐惧": "恐惧",
                "懒惰": "懒惰",
                "傲慢": "傲慢",
                "愤怒": "愤怒",
                "贪婪": "贪婪",
            }
            if resistance_to_desire.get(resistance_type, "") in entry.desires:
                matched_fields += 1
                score += 1.0

        target_goal_keywords = EMOTION_CASE_HINTS.get(goal_type, [])
        if any(keyword in entry.scenario_keywords for keyword in target_goal_keywords):
            matched_fields += 1
            score += 1.0

        if goal_type and getattr(entry, "goal_types", None) and goal_type in entry.goal_types:
            matched_fields += 1
            score += 0.8

        keyword_hits = sum(1 for kw in entry.scenario_keywords if kw in user_input)
        score += keyword_hits * 0.8

        # 方向B: applicable_scenes加分
        applicable_scenes = getattr(entry, "applicable_scenes", [])
        if applicable_scenes:
            scene_id = getattr(context, "primary_scene", "")
            if scene_id and scene_id in applicable_scenes:
                score += 2.0
                matched_fields += 1

        # 方向B: relationship_positions加分
        rel_positions = getattr(entry, "relationship_positions", [])
        if rel_positions:
            current_pos = getattr(context.user, "relationship_position", "")
            if current_pos and current_pos in rel_positions:
                score += 1.5
                matched_fields += 1

        if matched_fields >= 3:
            score += 1.0

        if score > best_score:
            best_score = score
            best_entry = entry

    if best_entry and best_score >= 2.5:
        confidence = 0.9 if best_score >= 4.0 else 0.78
        content = best_entry.content
        quick_parts = []
        if getattr(best_entry, "core_purpose", ""):
            quick_parts.append(f"核心目的：{best_entry.core_purpose}")
        if getattr(best_entry, "quick_principle", ""):
            quick_parts.append(f"速用原则：{best_entry.quick_principle}")
        tactical_sequence = getattr(best_entry, "tactical_sequence", [])
        if tactical_sequence:
            quick_parts.append(f"连招主线：{' -> '.join(tactical_sequence)}")
        if getattr(best_entry, "emergency_plan", ""):
            quick_parts.append(f"应急预案：{best_entry.emergency_plan}")
        if quick_parts:
            content = f"{content}\n\n" + "\n".join(quick_parts)
        return CaseMatchResult(
            title=best_entry.title,
            content=content,
            confidence=confidence,
            source_file=best_entry.source_file,
            core_purpose=getattr(best_entry, "core_purpose", ""),
            tactical_sequence=getattr(best_entry, "tactical_sequence", []),
            emergency_plan=getattr(best_entry, "emergency_plan", ""),
            quick_principle=getattr(best_entry, "quick_principle", ""),
            continuation_hints=getattr(best_entry, "continuation_hints", None),
        )

    results = search_cases(user_input, limit=1)
    if results:
        entry = results[0]
        return CaseMatchResult(
            title=entry.title,
            content=entry.content,
            confidence=0.65,
            source_file=entry.source_file,
            core_purpose=getattr(entry, "core_purpose", ""),
            tactical_sequence=getattr(entry, "tactical_sequence", []),
            emergency_plan=getattr(entry, "emergency_plan", ""),
            quick_principle=getattr(entry, "quick_principle", ""),
        )

    return None


def match_case(user_input: str, context=None) -> str | None:
    result = match_case_detail(user_input, context=context)
    return result.title if result else None


if __name__ == "__main__":
    test_cases = [
        "我总是控制不住情绪，一生气就失控",
        "怎么才能坚持学习，不拖延？",
        "如何提高转化率？",
        "我老板让我加班，我很烦",
        "朋友借钱不想借，怎么办？",
        "和老婆吵架了，怎么处理？",
    ]

    for text in test_cases:
        print(f"\n输入: {text}")
        knowledge = query_knowledge(text)
        if knowledge:
            print(f"知识: {knowledge.module_name} / {knowledge.title}")
        case = match_case_detail(text)
        if case:
            print(f"案例: {case.title}")
