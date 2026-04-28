"""
Human-OS Engine - LangGraph 节点实现

对应总控规格的 Step 0-9。
"""

from graph.state import GraphState
from graph.nodes.helpers import _generate_collapse_output
from schemas.enums import Mode
from utils.logger import warning


def _apply_mode_a_energy(context) -> None:
    context.self_state.energy_mode = Mode.A
    context.self_state.energy_allocation.inner = 0.7
    context.self_state.energy_allocation.outer = 0.2
    context.self_state.energy_allocation.environment = 0.1


def _extract_recent_feedbacks(context) -> list[str]:
    recent_feedbacks = []
    for item in context.history[-8:]:
        feedback = item.metadata.get("feedback")
        if feedback:
            recent_feedbacks.append(feedback)
    return recent_feedbacks


def _extract_recent_emotions(context) -> list[float]:
    recent_emotions = []
    for item in context.history[-8:]:
        if item.role == "user" and "emotion_intensity" in item.metadata:
            recent_emotions.append(float(item.metadata["emotion_intensity"]))
    return recent_emotions


def _count_negative_streak(recent_feedbacks: list[str]) -> int:
    streak = 0
    for feedback in reversed(recent_feedbacks):
        if feedback == "negative":
            streak += 1
        else:
            break
    return streak


def _analyze_self_check_trend(
    recent_emotions: list[float],
    recent_feedbacks: list[str],
    current_intensity: float,
) -> tuple[str, str]:
    """
    判断当前是持续恶化、来回波动，还是开始回稳。
    先做稳定版，只看最近几轮趋势。
    """
    recent_window = recent_emotions[-3:]
    negative_streak = _count_negative_streak(recent_feedbacks)

    if len(recent_window) >= 3:
        deltas = [
            recent_window[i + 1] - recent_window[i]
            for i in range(len(recent_window) - 1)
        ]
        if deltas and all(delta >= 0.08 for delta in deltas) and current_intensity >= 0.72:
            return ("worsening", "最近几轮在持续上冲，先别扩话题，先稳住")
        if max(recent_window) - min(recent_window) >= 0.35 and any(abs(delta) >= 0.18 for delta in deltas):
            return ("swinging", "状态在来回拉扯，先减变量，别同时处理太多事")
        if deltas and all(delta <= -0.08 for delta in deltas) and negative_streak == 0:
            return ("recovering", "状态开始往回落了，可以继续稳着推进")

    if negative_streak >= 2 and current_intensity >= 0.7:
        return ("worsening", "最近几轮越聊越顶，先收缩范围比较稳")
    if current_intensity < 0.45 and negative_streak == 0:
        return ("recovering", "状态相对稳，可以小步往前推")
    return ("stable", "整体还算稳定，继续盯住当前问题")


def _diagnose_collapse_stage(context, pressure: float, negative_count: int, high_emotion_count: int) -> tuple[str, str, list[str]]:
    """
    按 25 模块的三阶段做一个稳定版判断。
    不求玄，先把“现在主要卡在哪层”分清。
    """
    current_intensity = float(context.user.emotion.intensity)
    current_mode = context.self_state.energy_mode.value if hasattr(context.self_state.energy_mode, "value") else str(context.self_state.energy_mode)

    if pressure >= 0.82 or negative_count >= 3 or (current_intensity >= 0.9 and high_emotion_count >= 2):
        return (
            "inner_exhaustion",
            "先保住睡眠、身体和最小秩序",
            [
                "把当前目标缩成一件最小的事",
                "先停掉高消耗输入和额外对外任务",
                "优先恢复睡眠、吃饭和基本行动力",
            ],
        )

    if pressure >= 0.55 or high_emotion_count >= 2 or (current_mode in {"B", "C"} and current_intensity >= 0.75):
        return (
            "outer_damage",
            "先把边界和过滤能力补回来",
            [
                "暂停继续扩张对话范围",
                "只处理一个核心问题，其他先不接",
                "减少解释和讨好，先把边界立住",
            ],
        )

    if pressure >= 0.25 or current_intensity >= 0.6 or context.goal.drift_detected:
        return (
            "attention_hijack",
            "先把注意力从外界收回来",
            [
                "先停掉多余信息和干扰",
                "只聚焦当前最可控的一件事",
                "别急着扩展新目标和新分支",
            ],
        )

    return ("stable", "保持当前节奏", [])


def _calculate_energy_pressure(context, negative_count: int, high_emotion_count: int, emotion_drift: float) -> float:
    pressure = 0.0
    current_mode = context.self_state.energy_mode.value if hasattr(context.self_state.energy_mode, "value") else str(context.self_state.energy_mode)

    pressure += min(negative_count * 0.2, 0.6)
    pressure += min(high_emotion_count * 0.12, 0.36)
    pressure += min(emotion_drift * 0.5, 0.2)

    if context.user.emotion.intensity >= 0.8:
        pressure += 0.15
    elif context.user.emotion.intensity >= 0.6:
        pressure += 0.08

    if context.goal.drift_detected:
        pressure += 0.08

    if current_mode in {"B", "C"}:
        pressure += 0.08

    return min(pressure, 1.0)


def _update_energy_allocation_for_pressure(context, pressure: float) -> None:
    """
    压力越高，越把能量往内收。
    这块先做成稳定版，不追求花哨。
    """
    if pressure >= 0.75:
        context.self_state.energy_allocation.inner = 0.82
        context.self_state.energy_allocation.outer = 0.12
        context.self_state.energy_allocation.environment = 0.06
    elif pressure >= 0.5:
        context.self_state.energy_allocation.inner = 0.75
        context.self_state.energy_allocation.outer = 0.17
        context.self_state.energy_allocation.environment = 0.08
    elif pressure >= 0.3:
        context.self_state.energy_allocation.inner = 0.68
        context.self_state.energy_allocation.outer = 0.22
        context.self_state.energy_allocation.environment = 0.10


def _derive_tension_and_risk(
    trend: str,
    energy_pressure: float,
    high_emotion_count: int,
    collapse_stage: str,
) -> tuple[str, str, bool]:
    interaction_tension = "low"
    push_risk = "low"
    repair_need = False

    if collapse_stage in {"inner_exhaustion", "outer_damage"} or energy_pressure >= 0.75:
        interaction_tension = "high"
        push_risk = "high"
        repair_need = True
        return interaction_tension, push_risk, repair_need

    if trend in {"worsening", "swinging"} or high_emotion_count >= 2 or energy_pressure >= 0.45:
        interaction_tension = "medium"
        push_risk = "medium"
        repair_need = True
        return interaction_tension, push_risk, repair_need

    if trend == "recovering":
        interaction_tension = "low"
        push_risk = "low"
        repair_need = False
        return interaction_tension, push_risk, repair_need

    if collapse_stage == "attention_hijack":
        interaction_tension = "medium"
        push_risk = "medium"
        repair_need = True

    return interaction_tension, push_risk, repair_need


def step3_self_check(state: GraphState) -> GraphState:
    """Step 3：自身状态检查"""
    context = state["context"]
    if state.get("skip_to_end", False):
        return {**state, "context": context, "skip_to_end": True}

    recent_feedbacks = _extract_recent_feedbacks(context)
    negative_count = recent_feedbacks.count("negative")
    negative_streak = _count_negative_streak(recent_feedbacks)
    recent_emotions = _extract_recent_emotions(context)
    high_emotion_count = sum(1 for intensity in recent_emotions[-3:] if intensity >= 0.8)
    trend, trend_focus = _analyze_self_check_trend(
        recent_emotions=recent_emotions,
        recent_feedbacks=recent_feedbacks,
        current_intensity=float(context.user.emotion.intensity),
    )

    emotion_drift = 0.0
    if len(recent_emotions) >= 2:
        emotion_drift = abs(recent_emotions[-1] - recent_emotions[0])
        if emotion_drift > 0.3 and context.history:
            warning(f"自检警告：检测到剧烈情绪波动 ({emotion_drift:.2f})，建议重新识别用户状态")
            context.history[-1].metadata["emotion_drift_detected"] = True

    energy_pressure = _calculate_energy_pressure(
        context=context,
        negative_count=negative_count,
        high_emotion_count=high_emotion_count,
        emotion_drift=emotion_drift,
    )
    collapse_stage, recovery_focus, recovery_actions = _diagnose_collapse_stage(
        context=context,
        pressure=energy_pressure,
        negative_count=negative_count,
        high_emotion_count=high_emotion_count,
    )
    interaction_tension, push_risk, repair_need = _derive_tension_and_risk(
        trend=trend,
        energy_pressure=energy_pressure,
        high_emotion_count=high_emotion_count,
        collapse_stage=collapse_stage,
    )

    # 标准字段：给后续节点统一读取，不再只依赖 history metadata
    context.self_check.stability_trend = trend
    context.self_check.interaction_tension = interaction_tension
    context.self_check.push_risk = push_risk
    context.self_check.repair_need = repair_need
    context.self_check.trend_focus = trend_focus
    context.self_check.collapse_stage = collapse_stage
    context.self_check.recovery_focus = recovery_focus
    context.self_check.recovery_actions = recovery_actions or []
    context.self_check.energy_pressure = round(energy_pressure, 3)
    context.self_check.negative_streak = negative_streak

    if context.history:
        context.history[-1].metadata["energy_pressure"] = round(energy_pressure, 3)
        context.history[-1].metadata["negative_streak"] = negative_streak
        context.history[-1].metadata["state_trend"] = trend
        context.history[-1].metadata["trend_focus"] = trend_focus
        context.history[-1].metadata["collapse_stage"] = collapse_stage
        context.history[-1].metadata["recovery_focus"] = recovery_focus
        if recovery_actions:
            context.history[-1].metadata["recovery_actions"] = recovery_actions

    # 先做“回收能量”，不急着直接判死。
    _update_energy_allocation_for_pressure(context, energy_pressure)

    should_force_mode_a = (
        high_emotion_count >= 2
        or energy_pressure >= 0.5
        or context.goal.drift_detected
        or (trend == "worsening" and energy_pressure >= 0.4)
    )
    if should_force_mode_a:
        context.self_state.energy_mode = Mode.A
        if context.history:
            context.history[-1].metadata["forced_mode_a"] = True

    # 连续失败 + 高压，才进入真正的不稳定。
    if collapse_stage == "inner_exhaustion" or negative_count >= 3 or (negative_count >= 2 and energy_pressure >= 0.75):
        context.self_state.is_stable = False

    if not context.self_state.is_stable:
        _apply_mode_a_energy(context)
        collapse_output = _generate_collapse_output(context)
        context.output = collapse_output
        return {**state, "context": context, "output": collapse_output, "skip_to_end": True}

    return {**state, "context": context, "skip_to_end": False}
