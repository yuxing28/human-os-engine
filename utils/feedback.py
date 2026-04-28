"""
Human-OS Engine - 反馈推断与处理

从 graph/nodes.py 中提取，避免循环导入。
"""

from schemas.context import Context


def infer_feedback(current_input: str, previous_emotion_intensity: float, context: Context) -> str:
    """
    推断反馈类型

    在新一轮用户输入到来时调用，判断上一轮输出的反馈。

    Args:
        current_input: 当前用户输入（下一轮）
        previous_emotion_intensity: 上一轮的情绪强度
        context: 当前上下文

    Returns:
        str: feedback 类型（positive/negative/neutral）
    """
    # 感谢/认可关键词
    POSITIVE_KEYWORDS = ["谢谢", "感谢", "有用", "明白了", "懂了", "好的", "可以", "不错", "很好"]
    # 攻击/拒绝关键词
    NEGATIVE_KEYWORDS = ["没用", "废话", "滚", "无聊", "烦死了", "别说了", "听不懂", "不对"]
    # 放弃/中断关键词
    GIVE_UP_KEYWORDS = ["算了", "不聊了", "结束", "再见"]

    # 【修复2】信任下降直接判定 negative（最高优先级）
    if context.last_feedback_trust_change is not None and context.last_feedback_trust_change < -0.03:
        return "negative"
    if context.last_feedback_trust_change is not None and context.last_feedback_trust_change > 0.03:
        return "positive"

    # 1. 检查负面信号
    if any(kw in current_input for kw in NEGATIVE_KEYWORDS):
        return "negative"

    if any(kw in current_input for kw in GIVE_UP_KEYWORDS):
        return "negative"

    # 2. 检查正面信号
    if any(kw in current_input for kw in POSITIVE_KEYWORDS):
        return "positive"

    # 3. 检查情绪强度变化
    current_intensity = context.user.emotion.intensity
    if current_intensity < previous_emotion_intensity - 0.2:
        return "positive"  # 情绪下降
    if current_intensity > previous_emotion_intensity + 0.2:
        return "negative"  # 情绪上升

    # 4. 默认 neutral
    return "neutral"


def process_feedback(state: dict, user_input: str) -> dict:
    """
    处理反馈（在 Step 0 开始时调用）

    根据新一轮用户输入推断上一轮的反馈类型。
    """
    context = state["context"]

    # 获取上一轮的情绪强度（从历史元数据中恢复）
    previous_intensity = 0.5  # 默认值
    if len(context.history) >= 2:
        # 从历史中找到上一条 system 回复的元数据
        for item in reversed(context.history[:-1]):
            if item.role == "system" and item.metadata.get("emotion_intensity"):
                previous_intensity = item.metadata["emotion_intensity"]
                break
            elif item.role == "user" and item.metadata.get("emotion_intensity"):
                # 如果 system 没有，用上一条 user 的情绪强度
                previous_intensity = item.metadata["emotion_intensity"]
                break

    # 推断反馈
    feedback = infer_feedback(user_input, previous_intensity, context)
    context.last_feedback = feedback

    # 更新历史记录中的反馈元数据
    if context.history:
        context.history[-1].metadata["feedback"] = feedback

    return {**state, "context": context}
