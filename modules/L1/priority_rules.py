"""
Human-OS Engine - L1 模块：优先级规则

基于 07-优先级规则模块.md 的内容。
实现总控 Step 4 的优先级排序逻辑。

输入：UserState, Goal
输出：优先级结果（priority_type + details）
"""

from typing import Any
from schemas.user_state import UserState, EmotionType, AttentionHijacker, ResistanceType
from schemas.context import Goal


def get_priority(
    user: UserState,
    goal: Goal,
    self_stable: bool = True,
    energy_pressure: float = 0.0,
    desire_relations: dict[str, list[dict]] | None = None,
) -> dict[str, Any]:
    """
    按顺序判断当前最高优先级（命中即停止）

    优先级顺序：
    1. 用户能量崩溃（阶段3）
    2. 注意力被劫持（阶段1/2）
    3. 阻力浮现
    4. 恐惧
    5. 愤怒/急躁
    6. 傲慢
    7. 懒惰
    8. 主导欲望（权重最高）

    压制/转化关系会修改上述基础优先级的策略方向：
    - 压制关系：不改变优先级类型，但在 details 中标注应激活被压制方
    - 转化关系：将愤怒/暴食的优先级策略改为"先处理恐惧根源"

    Args:
        user: 用户状态
        goal: 当前目标
        desire_relations: Step 1 识别出的压制/转化关系

    Returns:
        dict: {
            "priority_type": str,   # 优先级类型标识
            "details": Any          # 附加数据
        }
    """
    relations = desire_relations or {}
    suppressions = relations.get("suppressions", [])
    transformations = relations.get("transformations", [])
    # 0. 自身不稳 / 高压回收
    if not self_stable or energy_pressure >= 0.8:
        return {
            "priority_type": "self_recovery",
            "details": {
                "self_stable": self_stable,
                "energy_pressure": energy_pressure,
            },
            "forced_weapon_type": "gentle",
        }

    # 1. 用户能量崩溃（阶段3：内在枯竭）
    if (user.emotion.type == EmotionType.FRUSTRATED and
        user.emotion.intensity > 0.85 and
        user.attention.focus < 0.2):
        return {
            "priority_type": "energy_collapse",
            "details": {
                "intensity": user.emotion.intensity,
                "focus": user.attention.focus
            }
        }

    # 2. 注意力被劫持（阶段1/2）
    if (user.attention.focus < 0.35 and
        user.attention.hijacked_by != AttentionHijacker.NONE):
        return {
            "priority_type": "attention_hijacked",
            "details": {
                "hijacked_by": user.attention.hijacked_by.value,
                "focus": user.attention.focus
            }
        }

    # 2.5 目标漂移：当前更该先拉回目标，而不是继续推进话术
    if goal.drift_detected and user.emotion.intensity < 0.85:
        return {
            "priority_type": "goal_realign",
            "details": {
                "current_goal": goal.current.description,
                "goal_type": goal.current.type,
            },
            "forced_weapon_type": "gentle",
        }

    # 3. 阻力浮现
    if (user.resistance.type is not None and
        user.resistance.type != ResistanceType.NONE):
        return {
            "priority_type": "resistance",
            "details": {
                "resistance_type": user.resistance.type.value,
                "intensity": user.resistance.intensity
            },
            "forced_weapon_type": None
        }

    # 4. 恐惧（fear > 0.55，或恐惧/挫败/迷茫情绪强度 > 0.65）
    # 注意：愤怒/急躁/平静的高情绪不由恐惧捕获，由第5条处理
    emotion_type_val = user.emotion.type.value if hasattr(user.emotion.type, 'value') else str(user.emotion.type)
    is_fear_related = emotion_type_val in ("恐惧", "挫败", "迷茫")
    if user.desires.fear > 0.55 or (is_fear_related and user.emotion.intensity > 0.65):
        result = {
            "priority_type": "fear",
            "details": {
                "fear_weight": user.desires.fear,
                "emotion_intensity": user.emotion.intensity
            },
            "forced_weapon_type": "gentle"
        }
        # 压制关系：恐惧过度 → 标注应激活贪婪恢复平衡
        fear_suppression = [s for s in suppressions if s["dominant"] == "fear"]
        if fear_suppression:
            result["details"]["suppression_hint"] = fear_suppression[0]["hint"]
            result["details"]["suppression_strategy"] = fear_suppression[0]["strategy"]
        return result

    # 5. 愤怒/急躁 → 平等博弈反制（不卑微安抚）
    # 转化关系：若愤怒是恐惧转化而来，策略改为"先处理恐惧根源"
    if (emotion_type_val in ("愤怒", "急躁") or
        user.emotion.type in [EmotionType.ANGRY, EmotionType.IMPATIENT] or
        user.desires.wrath > 0.55):
        result = {
            "priority_type": "anger_first",
            "details": {
                "emotion_type": user.emotion.type.value,
                "emotion_intensity": user.emotion.intensity,
                "wrath_weight": user.desires.wrath,
            },
            "forced_weapon_type": "defensive"
        }
        # 转化关系：愤怒是恐惧转化 → 先处理恐惧根源
        wrath_transform = [t for t in transformations if t["manifests_as"] == "wrath"]
        if wrath_transform:
            result["details"]["transformation_hint"] = wrath_transform[0]["hint"]
            result["details"]["transformation_strategy"] = wrath_transform[0]["strategy"]
            result["details"]["fear_source_weight"] = wrath_transform[0]["source_weight"]
        return result

    # 6. 傲慢：要先处理框架和姿态问题
    if user.desires.pride > 0.55:
        result = {
            "priority_type": "pride_first",
            "details": {
                "pride_weight": user.desires.pride,
                "goal_type": goal.current.type,
            },
            "forced_weapon_type": "defensive"
        }
        # 压制关系：傲慢过度 → 标注应激活恐惧或满足傲慢
        pride_suppression = [s for s in suppressions if s["dominant"] == "pride"]
        if pride_suppression:
            result["details"]["suppression_hint"] = pride_suppression[0]["hint"]
            result["details"]["suppression_strategy"] = pride_suppression[0]["strategy"]
        return result

    # 7. 懒惰（sloth > 0.45，或注意力低+懒惰中高）
    if user.desires.sloth > 0.45 or (user.desires.sloth > 0.35 and user.attention.focus < 0.45):
        result = {
            "priority_type": "sloth",
            "details": {
                "sloth_weight": user.desires.sloth,
                "focus": user.attention.focus,
            },
            "forced_weapon_type": "gentle"
        }
        # 压制关系：懒惰主导 → 标注应激活贪婪+降低门槛
        sloth_suppression = [s for s in suppressions if s["dominant"] == "sloth"]
        if sloth_suppression:
            result["details"]["suppression_hint"] = sloth_suppression[0]["hint"]
            result["details"]["suppression_strategy"] = sloth_suppression[0]["strategy"]
        return result

    # 8. 主导欲望（权重最高的欲望）
    desires_dict = user.desires.model_dump()
    max_desire = max(desires_dict.items(), key=lambda x: x[1])

    if max_desire[1] > 0:
        # 根据主导欲望推荐武器类型
        forced_type = None
        if max_desire[0] in ["pride", "wrath"]:
            forced_type = "defensive"
        elif max_desire[0] in ["fear"]:
            forced_type = "gentle"

        return {
            "priority_type": "dominant_desire",
            "details": {
                "desire": max_desire[0],
                "weight": max_desire[1]
            },
            "forced_weapon_type": forced_type
        }

    # 默认：无特殊优先级
    return {
        "priority_type": "none",
        "details": {},
        "forced_weapon_type": None
    }


# ===== 测试入口 =====

if __name__ == "__main__":
    from schemas.user_state import Emotion, Desires, Attention, Resistance, DualCore

    test_cases = [
        {
            "name": "能量崩溃",
            "user": UserState(
                emotion=Emotion(type=EmotionType.FRUSTRATED, intensity=0.9),
                attention=Attention(focus=0.1),
            ),
        },
        {
            "name": "注意力被劫持",
            "user": UserState(
                emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
                attention=Attention(focus=0.2, hijacked_by=AttentionHijacker.FEAR),
            ),
        },
        {
            "name": "恐惧主导",
            "user": UserState(
                emotion=Emotion(type=EmotionType.CALM, intensity=0.5),
                desires=Desires(fear=0.8),
            ),
        },
        {
            "name": "愤怒",
            "user": UserState(
                emotion=Emotion(type=EmotionType.ANGRY, intensity=0.7),
            ),
        },
        {
            "name": "懒惰",
            "user": UserState(
                emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
                desires=Desires(sloth=0.7),
            ),
        },
        {
            "name": "贪婪主导",
            "user": UserState(
                emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
                desires=Desires(greed=0.8),
            ),
        },
    ]

    goal = Goal()

    for case in test_cases:
        result = get_priority(case["user"], goal)
        print(f"\n{case['name']}: {result['priority_type']}")
        print(f"  详情: {result['details']}")
