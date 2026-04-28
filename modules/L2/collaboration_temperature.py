"""
Human-OS Engine - L2 识别模块：协作温度识别

基于 27-协作温度模块-识别算法与反心理分析.md 的内容。
识别用户的情绪类型、强度和动机类型。

输入：用户输入文本
输出：EmotionResult（情绪类型 + 强度 + 动机）
"""

from schemas.module_io import EmotionResult


EMOTION_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "挫败": {
        "strong": ["救命", "疯了", "崩溃", "绝望", "没救了", "不行了", "完了"],
        "medium": ["挫败", "失败", "不行", "做不到", "学不会", "搞不定", "无力", "沮丧", "失落", "太难了", "受不了", "糟糕", "放弃"],
        "mild": ["有点难", "不太行", "一般般", "还好吧", "有点累", "吃力"],
    },
    "迷茫": {
        "strong": ["彻底迷茫", "完全不知道", "毫无方向", "一头雾水", "迷茫死了"],
        "medium": ["迷茫", "困惑", "不知道", "不清楚", "不明白", "纠结", "犹豫", "选择困难"],
        "mild": ["想想看", "拿不准", "不确定", "有点懵"],
    },
    "急躁": {
        "strong": ["急死了", "等不了", "马上要", "立刻", "别废话", "能不能别", "快点"],
        "medium": ["急", "快", "马上", "赶紧", "等不及", "没时间", "时间紧", "直接告诉我", "少说"],
        "mild": ["尽快", "早点", "能快点吗", "抓紧"],
    },
    "平静": {
        "strong": ["非常平静", "很淡定", "无所谓"],
        "medium": ["还好", "正常", "一般", "普通", "平静", "淡定", "方法", "步骤", "计划", "目标", "具体", "如何"],
        "mild": ["嗯", "好的", "可以", "行", "想"],
    },
    "愤怒": {
        "strong": ["气死了", "忍无可忍", "太过分了", "恶心", "滚", "操"],
        "medium": ["生气", "愤怒", "火大", "烦死了", "受不了", "离谱", "恶心人", "讨厌"],
        "mild": ["不爽", "烦", "无语", "服了", "呵呵"],
    },
}

MOTIVE_KEYWORDS: dict[str, list[str]] = {
    "灵感兴奋": ["好点子", "好想法", "突破", "学会", "掌握", "搞定", "实用", "有意思", "想做", "灵感", "兴奋"],
    "生活期待": ["生日", "婚礼", "旅游", "度假", "买礼物", "奖励自己", "瘦", "好看", "美美的", "期待", "希望", "想要"],
    "回避恐惧": ["不想", "怕", "担心", "丢人", "失望", "丢脸", "失败", "学不会", "害怕", "焦虑", "回避", "逃避", "怎么办", "分手", "丢了"],
    "压力被动": ["不得不", "被逼", "必须", "没办法", "只能", "身不由己", "领导让", "家人让"],
}

LEVEL_WEIGHTS = {"strong": 3, "medium": 2, "mild": 1}


def identify_emotion(user_input: str) -> EmotionResult:
    """
    协作温度识别主函数
    """
    emotion_type, intensity = _detect_emotion(user_input)
    motive = _detect_motive(user_input)
    confidence = _calculate_confidence(user_input, emotion_type, motive)

    return EmotionResult(
        type=emotion_type,
        intensity=intensity,
        confidence=confidence,
        motive=motive,
    )


def _detect_emotion(user_input: str) -> tuple[str, float]:
    """
    识别主导情绪和强度。

    这里不再只看“单个最强词”，而是按同类词累计，更贴近原始文档里
    “多信号叠加判断情绪温度”的意思。
    """
    scores: dict[str, int] = {emotion: 0 for emotion in EMOTION_KEYWORDS}

    for emotion, levels in EMOTION_KEYWORDS.items():
        for level, keywords in levels.items():
            weight = LEVEL_WEIGHTS[level]
            for keyword in keywords:
                if keyword in user_input:
                    scores[emotion] += weight

    dominant = max(scores, key=scores.get)
    dominant_score = scores[dominant]

    if dominant_score == 0:
        return "平静", 0.2

    if dominant == "平静":
        intensity = min(0.1 + dominant_score * 0.05, 0.3)
    else:
        intensity = min(0.5 + dominant_score * 0.15, 0.95)

    return dominant, intensity


def _detect_motive(user_input: str) -> str:
    """
    识别动机类型。

    这里按原始文档的优先顺序来，不走“谁分高就选谁”的纯机械逻辑。
    """
    scores = {
        motive: sum(1 for keyword in keywords if keyword in user_input)
        for motive, keywords in MOTIVE_KEYWORDS.items()
    }

    if scores["生活期待"] > 0:
        return "生活期待"
    if scores["回避恐惧"] > 0:
        return "回避恐惧"
    if scores["灵感兴奋"] > 0:
        return "灵感兴奋"
    if scores["压力被动"] > 0:
        return "压力被动"
    return "压力被动"


def _calculate_confidence(user_input: str, emotion_type: str, motive: str) -> float:
    """
    计算识别置信度。

    原始逻辑更强调“先有稳定底盘，再根据强信号上下浮动”，
    所以这里用高基础分，再根据强烈情绪词和动机线索微调。
    """
    has_strong_emotion = any(
        keyword in user_input
        for keywords in (levels["strong"] for levels in EMOTION_KEYWORDS.values())
        for keyword in keywords
    )
    motive_hits = sum(1 for keyword in MOTIVE_KEYWORDS.get(motive, []) if keyword in user_input)

    confidence = 0.7
    if has_strong_emotion:
        confidence += 0.1
    if motive_hits >= 2:
        confidence += 0.1
    if emotion_type == "平静" and motive == "回避恐惧":
        confidence -= 0.15

    return min(max(confidence, 0.0), 1.0)


if __name__ == "__main__":
    test_cases = [
        "我太难了，学不会，真的快崩溃了",
        "别废话，直接告诉我怎么做，快点",
        "我有点迷茫，不知道接下来该怎么办",
        "我想给自己准备个生日礼物，想要好看一点的",
        "领导逼着我今天必须做完",
    ]

    for text in test_cases:
        result = identify_emotion(text)
        print(f"\n输入: {text}")
        print(f"情绪: {result.type} ({result.intensity:.2f})")
        print(f"动机: {result.motive}")
        print(f"置信度: {result.confidence:.2f}")
