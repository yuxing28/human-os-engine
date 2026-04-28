"""
Human-OS Engine - L1 模块：运作模式

基于 05-运作模式模块.md 的内容。
实现总控 Step 5 的模式选择逻辑。

输入：self_stable, UserState, Goal, priority
输出：模式字符串（如 "A", "B", "C", "A+B", "B→C", "attention_first"）
"""

from typing import Any
from schemas.user_state import UserState, EmotionType, DualCoreState, MotiveType, ResistanceType
from schemas.context import Goal


def _priority_type(priority: dict[str, Any] | None) -> str:
    if not priority:
        return "none"
    return str(priority.get("priority_type", "none"))


def select_mode(
    self_stable: bool,
    user: UserState,
    goal: Goal,
    priority: dict[str, Any] | None = None,
    input_type: str | None = None,
    upgrade_eligible: bool = True,
) -> str:
    """
    根据总控 v4.0 Step 5 规则选择模式组合

    Args:
        self_stable: 系统自身是否稳定
        user: 用户状态
        goal: 当前目标
        priority: 优先级结果（可选，用于辅助决策）
        input_type: 输入类型（情绪表达/问题咨询/场景描述/混合）
        upgrade_eligible: 是否允许升维（False 时跳过 Mode C）

    Returns:
        str: 模式字符串
    """
    priority_type = _priority_type(priority)
    trust_value = user.trust_level.value if hasattr(user.trust_level, "value") else str(user.trust_level)
    emotion_value = user.emotion.type.value if hasattr(user.emotion.type, "value") else str(user.emotion.type)

    # 1. 自身不稳定 → 强制 Mode A
    if not self_stable:
        return "A"

    # 1.5 优先级强制接管
    if priority_type in {"self_recovery", "energy_collapse", "attention_hijacked"}:
        return "A"
    if priority_type == "goal_realign":
        return "A"
    if priority_type == "anger_first":
        return "A"
    if priority_type == "pride_first":
        if goal.current.type == "情绪价值" and user.emotion.intensity < 0.6 and upgrade_eligible:
            return "C"
        return "B"

    # 2. 注意力被劫持 → 优先夺回注意力（Mode A 稳定）
    if (user.attention.focus < 0.35 and
        user.attention.hijacked_by is not None and
        user.attention.hijacked_by.value != "null"):
        return "A"

    # 2.5 输入类型辅助决策（新增）
    if (
        input_type == "问题咨询"
        and goal.current.type == "混合"
        and trust_value in {"medium", "high"}
        and user.emotion.intensity < 0.5
        and user.motive != MotiveType.STRESS_PASSIVE
        and upgrade_eligible
    ):
        return "B→C"
    if input_type == "问题咨询" and self_stable and user.emotion.intensity < 0.4:
        # 纯咨询且情绪平稳 → 直接 Mode B
        return "B"
    if input_type == "情绪表达" and user.emotion.intensity > 0.6:
        # 高情绪表达 → 优先 Mode A
        return "A"

    # 3. 阻力类型分支
    # 【修复 P0】情绪价值场景跳过阻力拦截：恐惧/焦虑是情感咨询的核心处理对象，不是阻碍
    if (user.resistance.type is not None and
        user.resistance.type != ResistanceType.NONE and
        goal.current.type != "情绪价值"):  # 情绪价值场景不拦截阻力
        res_type = user.resistance.type.value

        if res_type in ["恐惧", "愤怒"]:
            return "A"
        if res_type in ["懒惰", "贪婪"]:
            return "B"
        if res_type == "傲慢":
            if goal.current.type == "情绪价值" and upgrade_eligible:
                return "C"
            else:
                return "B"

    # 4. 双核对抗或情绪过载 → 先稳定
    # 【修复 P0】情绪价值场景跳过双核拦截：双核对抗是情感咨询的核心处理对象
    if (user.dual_core.state == DualCoreState.CONFLICT and
        goal.current.type != "情绪价值"):
        return "A"
    if user.emotion.intensity > 0.7:
        return "A"

    # 4.5 愤怒/急躁且情绪强度高 → 优先 Mode A 稳定（07-优先级规则）
    # 【修复 P0】情绪价值场景跳过愤怒拦截
    if emotion_value in ("愤怒", "急躁") and user.emotion.intensity > 0.7 and goal.current.type != "情绪价值":
        return "A"

    # 5. 混合场景（优先于单一规则）
    if user.desires.greed > 0.5 and user.desires.pride > 0.5:
        return "A+B"
    if user.desires.greed > 0.5 and goal.current.type == "情绪价值" and upgrade_eligible:
        return "B→C"
    # B+C: 先短期利益，再升维长期价值（商业+意义）
    if user.desires.greed > 0.4 and user.desires.pride > 0.4 and upgrade_eligible and user.emotion.intensity < 0.6:
        return "B→C"
    # A+C: 先稳定自我，再赋予意义（内耗修复+价值共创）
    if user.dual_core.state == DualCoreState.CONFLICT and goal.current.type == "情绪价值" and upgrade_eligible:
        return "A→C"

    # 6. 利益价值且情绪平稳 → Mode B
    if goal.current.type == "利益价值" and user.emotion.intensity < 0.4:
        return "B"

    # 7. 情绪价值或信任低
    if goal.current.type == "情绪价值" or trust_value == "low":
        # 升维条件检查（含资格检查）
        if (user.emotion.intensity < 0.6 and
            user.motive != MotiveType.STRESS_PASSIVE and
            upgrade_eligible):
            return "C"  # 满足升维条件
        else:
            return "A"  # 情绪过载、缺乏反思意愿、或不适合升维

    # 默认：Mode B
    return "B"


# ===== 测试入口 =====

if __name__ == "__main__":
    from schemas.user_state import Emotion, Desires, Attention, Resistance, DualCore
    from schemas.context import Goal, GoalItem

    test_cases = [
        {
            "name": "自身不稳定",
            "self_stable": False,
            "user": UserState(),
            "goal": Goal(),
        },
        {
            "name": "注意力被劫持",
            "self_stable": True,
            "user": UserState(
                attention=Attention(focus=0.2, hijacked_by=AttentionHijacker.FEAR),
            ),
            "goal": Goal(),
        },
        {
            "name": "阻力-恐惧",
            "self_stable": True,
            "user": UserState(
                resistance=Resistance(type=ResistanceType.FEAR, intensity=0.8),
            ),
            "goal": Goal(),
        },
        {
            "name": "双核对抗",
            "self_stable": True,
            "user": UserState(
                dual_core=DualCore(state=DualCoreState.CONFLICT),
            ),
            "goal": Goal(),
        },
        {
            "name": "情绪过载",
            "self_stable": True,
            "user": UserState(
                emotion=Emotion(type=EmotionType.ANGRY, intensity=0.8),
            ),
            "goal": Goal(),
        },
        {
            "name": "利益价值+情绪平稳",
            "self_stable": True,
            "user": UserState(
                emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
            ),
            "goal": Goal(current=GoalItem(type="利益价值")),
        },
        {
            "name": "情绪价值+升维条件满足",
            "self_stable": True,
            "user": UserState(
                emotion=Emotion(type=EmotionType.CALM, intensity=0.4),
                motive=MotiveType.LIFE_EXPECTATION,
            ),
            "goal": Goal(current=GoalItem(type="情绪价值")),
        },
        {
            "name": "贪婪+傲慢混合",
            "self_stable": True,
            "user": UserState(
                emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
                desires=Desires(greed=0.7, pride=0.6),
            ),
            "goal": Goal(),
        },
    ]

    for case in test_cases:
        mode = select_mode(case["self_stable"], case["user"], case["goal"])
        print(f"{case['name']}: {mode}")
