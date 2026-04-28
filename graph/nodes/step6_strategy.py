"""
Human-OS Engine - LangGraph 节点实现

对应总控规格的 Step 0-9。
"""

import re

from graph.state import GraphState
from schemas.strategy import StrategyPlan
from modules.L5.knowledge_router import query_knowledge, match_case_detail
from modules.L3.strategy_combinations import select_combo
from modules.L4.expression_dialectics import select_expression_mode
from graph.nodes.strategy_selector import _select_strategy

FAILURE_CODE_AVOID_ACTIONS = {
    "F01": "不要只按表层诉求直接推进，先确认真实目标",
    "F02": "不要推进过早，先确认对方准备度",
    "F03": "不要跳过承接修复，先稳关系再推进",
    "F04": "不要信息不全就给方案，先补一个关键问题",
    "F05": "不要一口气讲太重，先拆短句单点推进",
    "F06": "不要讲得太散，先收成一个明确下一步",
    "F07": "不要带内部术语，先转成用户能懂的话",
    "F08": "不要忽略场景约束，先重选匹配策略",
    "F09": "不要只停在共情，先加一个可执行动作",
    "F10": "不要过度强推，先保关系边界再谈结果",
}


def _append_knowledge_ref(context, ref_name: str) -> None:
    """避免重复写入引用记录。"""
    if ref_name and ref_name not in context.knowledge_refs:
        context.knowledge_refs.append(ref_name)


def _compress_text(value: str, limit: int = 140) -> str:
    text = " ".join((value or "").split())
    return text[:limit]


def _extract_action_steps(content: str) -> list[str]:
    lines = [line.strip() for line in (content or "").splitlines() if line.strip()]
    steps = []

    for line in lines:
        cleaned = re.sub(r"^\d+[\.、]\s*", "", line).strip()
        cleaned = re.sub(r"^[-*]\s*", "", cleaned).strip()
        if cleaned != line or any(token in line for token in ["1.", "2.", "3.", "1、", "2、", "3、"]):
            steps.append(cleaned.rstrip("。"))

    if steps:
        return steps[:3]

    sentences = [
        sentence.strip()
        for sentence in re.split(r"[。！？!?]\s*", content or "")
        if sentence.strip()
    ]
    return sentences[:3]


def _prioritize_action_steps(
    steps: list[str],
    user_input: str,
    goal_type: str,
    emotion_type: str,
) -> list[str]:
    if not steps:
        return []

    text = user_input or ""
    scored_steps = []
    for index, step in enumerate(steps):
        score = 0.0
        lowered_step = step.lower()

        if any(keyword in text for keyword in ["先别", "先停", "先稳", "先收", "先冷静"]):
            if any(keyword in step for keyword in ["停", "稳", "聚焦", "收回", "隔离", "边界"]):
                score += 2.0

        if any(keyword in text for keyword in ["成交", "转化", "签单", "客户", "销售", "推进"]):
            if any(keyword in step for keyword in ["锚定", "从众", "稀缺", "价值", "故事", "路径", "转化", "成交"]):
                score += 1.8

        if any(keyword in text for keyword in ["吵架", "关系", "伴侣", "老婆", "老公", "情绪", "崩溃"]):
            if any(keyword in step for keyword in ["共情", "倾听", "停火", "情绪", "边界", "收回", "修复"]):
                score += 1.8

        if goal_type == "利益价值" and any(keyword in step for keyword in ["结果", "成交", "推进", "转化", "方案"]):
            score += 1.0
        if goal_type == "情绪价值" and any(keyword in step for keyword in ["情绪", "倾听", "共情", "边界", "恢复", "停火"]):
            score += 1.0

        if emotion_type in {"愤怒", "急躁"} and any(keyword in step for keyword in ["停", "稳", "共情", "边界", "聚焦"]):
            score += 1.2
        if emotion_type in {"挫败", "迷茫"} and any(keyword in step for keyword in ["拆", "小目标", "恢复", "聚焦", "价值"]):
            score += 1.0

        for token in re.findall(r"[\u4e00-\u9fff]{2,6}", text):
            if token and token in step:
                score += 0.2

        score -= index * 0.05
        scored_steps.append((score, step))

    scored_steps.sort(key=lambda item: item[0], reverse=True)
    return [step for _, step in scored_steps[:3]]


def _build_action_sequence(steps: list[str]) -> str:
    if not steps:
        return ""
    if len(steps) == 1:
        return f"先{steps[0]}。"
    if len(steps) == 2:
        return f"先{steps[0]}，再{steps[1]}。"
    return f"先{steps[0]}，再{steps[1]}，最后{steps[2]}。"


def _is_progress_intent_input(user_input: str, goal_type: str = "") -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    progress_keywords = [
        "推进", "下一步", "落地", "成交", "签单", "转化",
        "执行", "怎么做", "先做", "卡住", "突破",
    ]
    if any(k in text for k in progress_keywords):
        return True
    return goal_type == "利益价值" and len(text) >= 10


def _extract_failure_codes_from_text(text: str, limit: int = 3) -> list[str]:
    if not text:
        return []
    found: list[str] = []
    for code in re.findall(r"\bF(0[1-9]|10)\b", text):
        full = f"F{code}"
        if full not in found:
            found.append(full)
        if len(found) >= max(1, limit):
            break
    return found


def _inject_failure_avoid_actions(
    avoid_now: list[str],
    unified_context: str,
    limit: int = 2,
) -> tuple[list[str], list[str]]:
    if not unified_context:
        return avoid_now, []
    failure_codes = _extract_failure_codes_from_text(unified_context, limit=max(1, limit))
    if not failure_codes:
        return avoid_now, []

    merged = list(avoid_now)
    for code in failure_codes:
        action = FAILURE_CODE_AVOID_ACTIONS.get(code)
        if action and action not in merged:
            merged.append(action)
    return merged, failure_codes


def _build_alignment_block(context, user_input: str = "", goal_type: str = "") -> str:
    parts = []
    current_goal = getattr(getattr(context, "goal", None), "current", None)
    if current_goal and getattr(current_goal, "description", ""):
        parts.append(f"当前目标：{current_goal.description}")

    latest_metadata = context.history[-1].metadata if context.history else {}
    self_check = getattr(context, "self_check", None)
    has_self_check_signal = bool(
        self_check
        and (
            getattr(self_check, "recovery_focus", "")
            or getattr(self_check, "stability_trend", "stable") != "stable"
            or getattr(self_check, "collapse_stage", "stable") != "stable"
        )
    )

    if has_self_check_signal:
        recovery_focus = getattr(self_check, "recovery_focus", "")
        trend = getattr(self_check, "stability_trend", "")
        collapse_stage = getattr(self_check, "collapse_stage", "")
    else:
        recovery_focus = latest_metadata.get("recovery_focus", "")
        trend = latest_metadata.get("state_trend", "")
        collapse_stage = latest_metadata.get("collapse_stage", "")

    if recovery_focus and collapse_stage not in {"", "stable"}:
        parts.append(f"当前重点：{recovery_focus}")

    caution_map = {
        "worsening": "别一边上头一边扩话题，先把节奏收回来",
        "swinging": "别同时处理太多变量，先盯住一个点",
        "recovering": "别急着一下子拉太满，先稳着往前推",
    }
    caution = caution_map.get(trend)
    if caution:
        parts.append(f"先别做：{caution}")

    unified_context = getattr(context, "unified_context", "")
    if unified_context:
        from modules.memory import (
            extract_structured_memory_hints,
            extract_decision_experience_hints,
            extract_failure_experience_hints,
            extract_experience_digest_hints,
        )

        progress_intent = _is_progress_intent_input(user_input=user_input, goal_type=goal_type)
        failure_experience_hint = extract_failure_experience_hints(
            unified_context,
            limit=3 if progress_intent else 2,
        )
        experience_digest_hint = extract_experience_digest_hints(
            unified_context,
            limit=3 if progress_intent else 2,
        )
        decision_experience_hint = extract_decision_experience_hints(
            unified_context,
            limit=5 if progress_intent else 4,
        )
        memory_hint = extract_structured_memory_hints(
            unified_context,
            limit_per_section=2 if progress_intent else 3,
        )
        if progress_intent and memory_hint:
            memory_lines = [line for line in memory_hint.splitlines() if "对话记忆" not in line]
            memory_hint = "\n".join(memory_lines).strip()

        if failure_experience_hint:
            parts.append(f"失败规避提示：\n{failure_experience_hint}")
        if experience_digest_hint:
            parts.append(f"经验索引提示：\n{experience_digest_hint}")
        if decision_experience_hint:
            parts.append(f"经验决策提示：\n{decision_experience_hint}")
        if memory_hint:
            parts.append(f"记忆提示：\n{memory_hint}")

    # 压制/转化关系提示（来自 Step 1 识别 → Step 4 优先级标注）
    desire_relations = getattr(context, "desire_relations", {})
    if desire_relations:
        for suppression in desire_relations.get("suppressions", []):
            parts.append(f"压制关系：{suppression['dominant']}过度压制{suppression['suppressed']}，{suppression['hint']}")
        for transformation in desire_relations.get("transformations", []):
            parts.append(f"转化关系：{transformation['manifests_as']}是{transformation['source']}转化，{transformation['hint']}")

    return "\n".join(parts)


def _build_knowledge_block(
    knowledge,
    context=None,
    user_input: str = "",
    goal_type: str = "",
    emotion_type: str = "",
) -> str:
    if not knowledge:
        return ""

    steps = _extract_action_steps(knowledge.content)
    steps = _prioritize_action_steps(
        steps=steps,
        user_input=user_input,
        goal_type=goal_type,
        emotion_type=emotion_type,
    )
    summary = _compress_text(knowledge.content, 180)
    action_sequence = _build_action_sequence(steps)

    parts = []
    alignment_block = _build_alignment_block(
        context,
        user_input=user_input,
        goal_type=goal_type,
    ) if context else ""
    if alignment_block:
        parts.append(alignment_block)
    parts.append(f"知识参考《{knowledge.title or knowledge.module_name}》：{summary}")
    if steps:
        parts.append(f"当前更适合的做法：{action_sequence}")
    return "\n".join(parts)


def _build_case_playbook(case_result, context=None, user_input: str = "", goal_type: str = "") -> str:
    if not case_result:
        return ""

    parts = []
    alignment_block = _build_alignment_block(
        context,
        user_input=user_input,
        goal_type=goal_type,
    ) if context else ""
    if alignment_block:
        parts.append(alignment_block)
    parts.append(f"案例参考《{case_result.title}》")
    if case_result.core_purpose:
        parts.append(f"核心目的：{case_result.core_purpose}")
    if case_result.tactical_sequence:
        parts.append(f"连招主线：{' -> '.join(case_result.tactical_sequence)}")
    if case_result.quick_principle:
        parts.append(f"速用原则：{case_result.quick_principle}")
    if case_result.emergency_plan:
        parts.append(f"应急预案：{case_result.emergency_plan}")
    if case_result.content:
        parts.append(f"案例底稿：{_compress_text(case_result.content, 220)}")
    return "\n".join(parts)


def _build_strategy_skeleton(context, user_input: str, input_type: str, goal_type: str, emotion_type: str) -> dict:
    """生成轻量策略骨架：现在先做稳定版，供 Step8 排表达顺序。"""
    do_now: list[str] = []
    do_later: list[str] = []
    avoid_now: list[str] = []
    fallback_move = ""

    self_check = getattr(context, "self_check", None)
    push_risk = getattr(self_check, "push_risk", "low") if self_check else "low"
    repair_need = getattr(self_check, "repair_need", False) if self_check else False
    emotion_intensity = float(getattr(context.user.emotion, "intensity", 0.5))

    if push_risk == "high" or emotion_intensity >= 0.8:
        do_now = [
            "先接住情绪，再把话题收成一个点",
            "先确认对方现在能接受的节奏",
        ]
        do_later = [
            "等状态回稳后再推进具体方案",
        ]
        avoid_now = [
            "不要直接下结论",
            "不要连续追问多个问题",
        ]
        fallback_move = "如果对方继续对抗，先停火并改成单点确认，再约下一步。"
    elif repair_need:
        do_now = [
            "先修关系和节奏，再谈推进",
            "先把误解点说清楚",
        ]
        do_later = [
            "关系回稳后再收行动承诺",
        ]
        avoid_now = [
            "不要强推结果",
        ]
        fallback_move = "若修复失败，先保留连接感，降低目标颗粒度。"
    elif input_type == "问题咨询":
        do_now = [
            "先确认当前最卡的一步",
            "先给一条最小可执行动作",
        ]
        do_later = [
            "执行后再补第二步和复盘点",
        ]
        avoid_now = [
            "不要一次给太多方案",
        ]
        fallback_move = "如果信息不足，先补一个关键问题再给建议。"
    elif input_type == "场景描述":
        do_now = [
            "先复盘当下场景里的关键冲突点",
            "先对齐这轮要达成的单一目标",
        ]
        do_later = [
            "再补完整连招和备选动作",
        ]
        avoid_now = [
            "不要跳过场景约束直接套模板",
        ]
        fallback_move = "若场景信息太少，先补足角色、时间、约束三要素。"
    else:
        # 情绪表达 / 混合的默认骨架
        if goal_type == "利益价值":
            do_now = ["先稳住对话，再切到一个可推进的结果点"]
            do_later = ["对方给到信号后再收口行动"]
            avoid_now = ["不要上来就压成交"]
            fallback_move = "若推进受阻，先回到顾虑确认再推进。"
        else:
            do_now = ["先接住，再确认，再小步引导"]
            do_later = ["情绪回稳后再进入方案层"]
            avoid_now = ["不要说教，不要贴标签"]
            fallback_move = "如果情绪再次上冲，回到短承接和单问题引导。"

    # 针对愤怒/急躁额外约束
    if emotion_type in {"愤怒", "急躁"} and "不要强推结果" not in avoid_now:
        avoid_now.append("不要强推结果")

    unified_context = getattr(context, "unified_context", "")
    progress_intent = _is_progress_intent_input(user_input=user_input, goal_type=goal_type)
    avoid_now, failure_avoid_codes = _inject_failure_avoid_actions(
        avoid_now=avoid_now,
        unified_context=unified_context,
        limit=3 if progress_intent else 2,
    )

    return {
        "do_now": do_now,
        "do_later": do_later,
        "avoid_now": avoid_now,
        "fallback_move": fallback_move,
        "failure_avoid_codes": failure_avoid_codes,
    }


def step6_strategy_generation(state: GraphState) -> GraphState:
    """Step 6：策略生成（重构：统一策略选择逻辑）"""
    context = state["context"]
    if state.get("skip_to_end", False):
        return {**state, "context": context}
    user_input = state["user_input"]
    selected_mode = state.get("selected_mode", "B")
    priority = state.get("priority", {})

    input_type = context.user.input_type.value if hasattr(context.user.input_type, 'value') else str(context.user.input_type)
    goal_type = context.goal.current.type if context.goal and context.goal.current else ""
    scene_id = getattr(context.scene_config, "scene_id", "") if context.scene_config else ""
    emotion_type = context.user.emotion.type.value if hasattr(context.user.emotion.type, 'value') else str(context.user.emotion.type)

    if input_type == "问题咨询":
        # 路径 B：知识咨询
        knowledge = query_knowledge(
            user_input,
            input_type=input_type,
            goal_type=goal_type,
            scene_id=scene_id,
        )
        if knowledge:
            _append_knowledge_ref(context, knowledge.module_name)
            user_state_dict = {
                "emotion_type": context.user.emotion.type.value if hasattr(context.user.emotion.type, 'value') else str(context.user.emotion.type),
                "emotion_intensity": context.user.emotion.intensity,
                "dominant_desire": context.user.desires.get_dominant()[0],
            }
            expression_mode = select_expression_mode(user_state_dict, input_type=input_type)
            strategy_plan = StrategyPlan(
                mode=selected_mode,
                combo_name="知识咨询",
                stage="知识",
                description=f"表达模式：{expression_mode}。\n{_build_knowledge_block(knowledge, context=context, user_input=user_input, goal_type=goal_type, emotion_type=emotion_type)}",
                fallback="",
            )
        else:
            strategy_plan = _select_strategy(context, selected_mode, "钩子", priority)

    elif input_type == "场景描述":
        # 路径 C：场景案例
        case_result = match_case_detail(user_input, context=context)
        if case_result:
            _append_knowledge_ref(context, case_result.title)
            strategy_plan = StrategyPlan(
                mode=selected_mode,
                combo_name=case_result.title,
                stage="案例",
                description=_build_case_playbook(
                    case_result,
                    context=context,
                    user_input=user_input,
                    goal_type=goal_type,
                ),
                fallback="",
            )
        else:
            strategy_plan = _select_strategy(context, selected_mode, "钩子", priority)

    elif input_type == "混合":
        # 路径 D：混合（先处理情绪，再走对应路径）
        priority_type = priority.get("priority_type", "none")
        if priority_type in ["self_recovery", "energy_collapse", "attention_hijacked", "goal_realign"]:
            stage = "防御"
        elif priority_type in ["anger_first", "pride_first"]:
            stage = "防御"
        elif priority_type == "fear":
            stage = "钩子"
        elif priority_type == "resistance":
            stage = "降门槛"
        else:
            stage = "钩子"

        emotion_plan = select_combo(context.user, "A", stage)
        knowledge = query_knowledge(
            user_input,
            input_type=input_type,
            goal_type=goal_type,
            scene_id=scene_id,
        )
        case_result = match_case_detail(user_input, context=context)

        if knowledge:
            _append_knowledge_ref(context, knowledge.module_name)
        if case_result:
            _append_knowledge_ref(context, case_result.title)

        mixed_blocks = [emotion_plan.description]
        if knowledge:
            mixed_blocks.append(_build_knowledge_block(knowledge, context=context, user_input=user_input, goal_type=goal_type, emotion_type=emotion_type))
        if case_result:
            mixed_blocks.append(
                _build_case_playbook(
                    case_result,
                    context=context,
                    user_input=user_input,
                    goal_type=goal_type,
                )
            )

        if knowledge or case_result:
            strategy_plan = StrategyPlan(
                mode=selected_mode,
                combo_name=emotion_plan.combo_name,
                stage="混合",
                description="\n\n".join(block for block in mixed_blocks if block),
                fallback=emotion_plan.fallback,
            )
        else:
            strategy_plan = emotion_plan

    else:
        # 路径 A：情绪表达（实时博弈）
        # Phase 2: 尝试动态策略引擎生成
        strategy_plan = None
        if context.goal.granular_goal:
            try:
                from modules.L3.dynamic_strategy_engine import DynamicStrategyEngine
                engine = DynamicStrategyEngine()
                history_summary = ""
                if context.history:
                    history_summary = " | ".join([f"{h.role}: {h.content[:30]}" for h in context.history[-4:]])
                
                strategy_plan = engine.generate(
                    goal_id=context.goal.granular_goal,
                    goal_desc=context.goal.display_name or "",
                    emotion_type=context.user.emotion.type.value if hasattr(context.user.emotion.type, 'value') else str(context.user.emotion.type),
                    emotion_intensity=context.user.emotion.intensity,
                    trust_level=context.user.trust_level.value if hasattr(context.user.trust_level, 'value') else str(context.user.trust_level),
                    history_summary=history_summary
                )
            except Exception as e:
                pass  # LLM 失败时静默回退到静态逻辑
        
        # Fallback 到静态逻辑
        if not strategy_plan:
            priority_type = priority.get("priority_type", "none")
            if priority_type in ["self_recovery", "energy_collapse", "attention_hijacked", "goal_realign"]:
                stage = "防御"
            elif priority_type in ["anger_first", "pride_first"]:
                stage = "防御"
            elif priority_type == "fear":
                stage = "钩子"
            elif priority_type == "resistance":
                stage = "降门槛"
            elif selected_mode == "C":
                stage = "升维"
            else:
                stage = ""
            strategy_plan = _select_strategy(context, selected_mode, stage, priority)

        # 路径 A 知识路由：情绪表达也查询 L5 模块（人生方法论/实战案例）
        if input_type == "情绪表达" or (context.goal.granular_goal and context.goal.granular_goal.startswith("emotion.")):
            knowledge = query_knowledge(
                user_input,
                input_type="情绪表达",
                goal_type=goal_type,
                scene_id=scene_id,
            )
            case_result = match_case_detail(user_input, context=context)
            
            extra_info = ""
            if knowledge:
                _append_knowledge_ref(context, knowledge.module_name)
                extra_info += f"\n\n知识参考《{knowledge.title or knowledge.module_name}》：{knowledge.content[:200]}"
            if case_result:
                _append_knowledge_ref(context, case_result.title)
                extra_info += f"\n\n案例参考《{case_result.title}》：{case_result.content[:200]}"
            
            if extra_info and strategy_plan:
                strategy_plan.description += extra_info

    # 场景插件全局策略覆盖
    if context.scene_config and getattr(context.goal, 'granular_goal', None):
        if strategy_plan is None or not strategy_plan.combo_name:
            for g in context.scene_config.goal_taxonomy:
                if g.granular_goal == context.goal.granular_goal and g.strategy_preferences:
                    from modules.L3.strategy_combinations import get_combo
                    best_pref = max(g.strategy_preferences, key=lambda x: x.get('weight', 0))
                    combo_name = best_pref.get("combo")
                    combo = get_combo(combo_name)
                    if combo:
                        strategy_plan = StrategyPlan(
                            mode=selected_mode,
                            combo_name=combo.name,
                            stage=combo.stage,
                            description=combo.logic,
                            fallback=combo.fallback,
                        )
                    break

    # 存储到 state
    if strategy_plan:
        context.current_strategy.combo_name = strategy_plan.combo_name
        context.current_strategy.stage = strategy_plan.stage

    skeleton = _build_strategy_skeleton(
        context=context,
        user_input=user_input,
        input_type=input_type,
        goal_type=goal_type,
        emotion_type=emotion_type,
    )
    context.current_strategy.skeleton.do_now = skeleton["do_now"]
    context.current_strategy.skeleton.do_later = skeleton["do_later"]
    context.current_strategy.skeleton.avoid_now = skeleton["avoid_now"]
    context.current_strategy.skeleton.fallback_move = skeleton["fallback_move"]
    
    # P1-6: 推断情境阶段
    _infer_situation_stage(context)
    
    return {**state, "context": context, "strategy_plan": strategy_plan, "strategy_skeleton": skeleton}


def _infer_situation_stage(context) -> None:
    """根据轮次+信任+情绪推断情境阶段"""
    round_num = len(context.history) // 2  # 近似轮次（每轮2条history）
    trust = 0.5
    if hasattr(context.user.trust_level, 'value'):
        trust_map = {"high": 0.8, "medium": 0.5, "low": 0.2}
        trust = trust_map.get(context.user.trust_level.value, 0.5)
    emotion_intensity = context.user.emotion.intensity
    
    if round_num <= 1:
        context.situation_stage = "破冰"
    elif emotion_intensity >= 0.7 and trust < 0.4:
        context.situation_stage = "修复"
    elif trust >= 0.6 and round_num >= 3:
        context.situation_stage = "收口"
    elif trust < 0.3 and round_num >= 3:
        context.situation_stage = "僵持"
    elif round_num <= 2:
        context.situation_stage = "探索"
    else:
        context.situation_stage = "推进"
