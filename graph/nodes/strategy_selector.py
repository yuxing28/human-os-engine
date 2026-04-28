"""策略选择器：统一策略路由。"""

from schemas.context import Context
from schemas.strategy import StrategyPlan


def _select_strategy(context: Context, selected_mode: str, stage: str, priority: dict) -> StrategyPlan:
    """
    统一策略选择逻辑。

    顺序：
    1. 场景强制策略
    2. 阻力映射策略
    3. 场景偏好策略（含反例惩罚）
    4. 全局回退
    """
    from modules.L3.strategy_combinations import get_combo, select_combo
    from modules.L5.counter_example_lib import get_strategy_penalties, get_strategy_bonuses
    import random

    if context.scene_config and getattr(context.goal, "granular_goal", None):
        for g in context.scene_config.goal_taxonomy:
            if g.granular_goal == context.goal.granular_goal:
                forced_combo = getattr(g, "forced_combo", None)
                if forced_combo:
                    combo = get_combo(forced_combo)
                    if combo:
                        return StrategyPlan(
                            mode=selected_mode,
                            combo_name=combo.name,
                            stage=combo.stage,
                            description=combo.logic,
                            fallback=combo.fallback,
                        )
                break

    res_val = context.user.resistance.type.value if hasattr(context.user.resistance.type, "value") else str(context.user.resistance.type)
    if res_val != "null":
        resistance_combo_map = {
            "恐惧": "提供确定性+案例证明",
            "懒惰": "懒惰+互惠",
            "傲慢": "反问+贴标签",
            "嫉妒": "权威+从众",
            "愤怒": "纠正+设界",
            "贪婪": "贪婪+恐惧",
        }
        combo_name = resistance_combo_map.get(res_val)
        if combo_name:
            combo = get_combo(combo_name)
            if combo:
                return StrategyPlan(
                    mode=selected_mode,
                    combo_name=combo.name,
                    stage=combo.stage if combo.stage != stage else stage,
                    description=combo.logic,
                    fallback=combo.fallback,
                )

    if context.scene_config and getattr(context.goal, "granular_goal", None):
        granular_goal = context.goal.granular_goal
        scene_id = context.scene_config.scene_id

        emotion_type = context.user.emotion.type.value if hasattr(context.user.emotion.type, "value") else str(context.user.emotion.type)
        penalties = get_strategy_penalties(scene_id, granular_goal, {"emotion": emotion_type})
        bonuses = get_strategy_bonuses(scene_id, granular_goal, {"emotion": emotion_type})

        for g in context.scene_config.goal_taxonomy:
            if g.granular_goal == granular_goal:
                banned = getattr(g, "banned_combos", [])
                prefs = [p for p in g.strategy_preferences if p.get("combo") not in banned]
                if prefs:
                    scored_prefs = []
                    for p in prefs:
                        combo_name = p.get("combo", "")
                        base_weight = p.get("weight", 0)
                        penalty = penalties.get(combo_name, 1.0)
                        bonus = bonuses.get(combo_name, 1.0)
                        if penalty == 0.0:
                            continue

                        emotion_factor = 1.0
                        trust_factor = 1.0
                        stage_factor = 1.0
                        position_factor = 1.0

                        if context.user.emotion.type in ["愤怒", "急躁"]:
                            if "共情" in combo_name or "重塑" in combo_name or "正常化" in combo_name:
                                emotion_factor = 1.5

                        trust_val = context.user.trust_level.value if hasattr(context.user.trust_level, "value") else str(context.user.trust_level)
                        if trust_val == "low":
                            if "信任" in combo_name or "共情" in combo_name or "正常化" in combo_name:
                                trust_factor = 1.3

                        # 方向A-1: 情境阶段感知 — 不同阶段偏好不同策略类型
                        situation_stage = getattr(context, "situation_stage", "未识别")
                        if situation_stage == "破冰":
                            if "钩子" in combo_name or "好奇" in combo_name or "提问" in combo_name:
                                stage_factor = 1.4  # 破冰优先钩子类
                        elif situation_stage == "推进":
                            if "放大" in combo_name or "升维" in combo_name or "数据" in combo_name:
                                stage_factor = 1.3  # 推进优先放大/升维类
                        elif situation_stage == "修复":
                            if "防御" in combo_name or "共情" in combo_name or "正常化" in combo_name:
                                stage_factor = 1.5  # 修复优先防御/共情类
                        elif situation_stage == "僵持":
                            if "换路径" in combo_name or "降门槛" in combo_name or "互惠" in combo_name:
                                stage_factor = 1.4  # 僵持优先换路径/降门槛
                        elif situation_stage == "收口":
                            if "逼单" in combo_name or "承诺" in combo_name or "行动" in combo_name:
                                stage_factor = 1.3  # 收口优先逼单/行动类

                        # 方向A-2: 关系位置感知 — 不同关系位置偏好不同策略风格
                        rel_pos = getattr(context.user, "relationship_position", "未识别")
                        if rel_pos == "服务-客户":
                            if "专业" in combo_name or "数据" in combo_name or "案例" in combo_name:
                                position_factor = 1.3  # 客户关系优先专业/数据类
                        elif rel_pos == "亲密-依赖":
                            if "共情" in combo_name or "接纳" in combo_name or "正常化" in combo_name:
                                position_factor = 1.4  # 亲密关系优先共情/接纳类
                        elif rel_pos == "对等-竞争":
                            if "设界" in combo_name or "反问" in combo_name or "权威" in combo_name:
                                position_factor = 1.3  # 竞争关系优先设界/权威类
                        elif rel_pos == "上级-下级":
                            if "引导" in combo_name or "行动" in combo_name or "承诺" in combo_name:
                                position_factor = 1.3  # 管理关系优先引导/行动类
                        elif rel_pos == "下级-上级":
                            if "尊重" in combo_name or "汇报" in combo_name or "数据" in combo_name:
                                position_factor = 1.3  # 向上管理优先尊重/数据类

                        # 定向优化: 躺平型/低能量下属 → 降门槛+互惠+微小承诺优先
                        if rel_pos == "上级-下级" and str(context.user.emotion.type) in ["挫败", "平静", "疲惫"]:
                            if "降门槛" in combo_name or "互惠" in combo_name or "接纳" in combo_name or "正常化" in combo_name:
                                position_factor = max(position_factor, 1.5)  # 覆盖之前的position_factor

                        # 定向优化: 愤怒型修复阶段 → 沉默+共情+物理隔离优先
                        if str(context.user.emotion.type) in ["愤怒", "急躁"] and situation_stage == "修复":
                            if "共情" in combo_name or "正常化" in combo_name or "接纳" in combo_name:
                                stage_factor = max(stage_factor, 1.6)  # 修复阶段强共情

                        # 定向优化: 疲惫型 → 保留选择权+互惠+降门槛优先
                        if str(context.user.emotion.type) in ["疲惫", "挫败"]:
                            if "保留选择权" in combo_name or "互惠" in combo_name or "降门槛" in combo_name or "接纳" in combo_name:
                                emotion_factor = max(emotion_factor, 1.5)

                        final_score = base_weight * emotion_factor * trust_factor * stage_factor * position_factor * penalty * bonus
                        scored_prefs.append((final_score, p))

                    if scored_prefs:
                        # 短句模式：从 top-N 高分策略做加权采样，保持动态性而不失控
                        if getattr(context, "short_utterance", False):
                            ranked = sorted(scored_prefs, key=lambda x: x[0], reverse=True)[:3]
                            if len(ranked) == 1:
                                _, best_pref = ranked[0]
                            else:
                                weights = [max(score, 0.01) for score, _ in ranked]
                                total = sum(weights)
                                pointer = random.random() * total
                                acc = 0.0
                                best_pref = ranked[0][1]
                                for weight, (_, pref) in zip(weights, ranked):
                                    acc += weight
                                    if pointer <= acc:
                                        best_pref = pref
                                        break
                        else:
                            _, best_pref = max(scored_prefs, key=lambda x: x[0])
                        combo_name = best_pref.get("combo")
                        combo = get_combo(combo_name)
                        if combo:
                            return StrategyPlan(
                                mode=selected_mode,
                                combo_name=combo.name,
                                stage=combo.stage if combo.stage != stage else stage,
                                description=combo.logic,
                                fallback=combo.fallback,
                            )
                break

    return select_combo(context.user, selected_mode, stage)
