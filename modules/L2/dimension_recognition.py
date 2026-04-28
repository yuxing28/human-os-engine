"""
Human-OS Engine - L2 识别层：七个维度识别

基于 04-七个维度模块.md 的完整内容。
识别用户输入中隐含的七个维度关键词，提供情绪→维度映射，支持正反面识别。

七个维度和八宗罪是并行的双引擎：
- 八宗罪驱动利益价值（Mode B）
- 七个维度驱动情绪价值（Mode C）
"""

from dataclasses import dataclass


@dataclass
class DimensionResult:
    """维度识别结果"""
    dominant_dimension: str  # 主导维度
    dimensions_detected: list[str]  # 检测到的所有维度
    confidence: float  # 置信度 0-1
    suggested_combo: str  # 推荐的升维策略组合
    is_negative: bool = False  # 是否检测到伪价值/反向使用


# ===== 七个维度关键词表（基于 04-七个维度模块.md 4.2 节，完整版） =====

DIMENSION_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "愿景": {
        "strong": ["愿景", "未来方向", "蓝图", "远景规划"],
        "medium": ["未来", "方向", "目标", "梦想", "可能性", "希望", "憧憬", "规划"],
        "mild": ["一起", "共同", "共赢", "前途"],
    },
    "尊严": {
        "strong": ["尊严", "人格独立", "平等尊重"],
        "medium": ["尊重", "平等", "价值", "边界", "人格", "独立", "自主", "认可", "重视"],
        "mild": ["公平", "面子", "被尊重"],
    },
    "卓越": {
        "strong": ["精益求精", "极致追求", "工匠精神"],
        "medium": ["卓越", "极致", "完美", "品质", "标准", "追求", "超越", "最好", "顶级", "专业"],
        "mild": ["不错", "优秀", "努力做到最好"],
    },
    "大爱": {
        "strong": ["大爱", "无私奉献", "社会责任"],
        "medium": ["关怀", "奉献", "责任", "社会", "公益", "帮助", "服务", "贡献", "可持续"],
        "mild": ["环保", "照顾", "关心别人"],
    },
    "革命": {
        "strong": ["革命", "颠覆式创新", "前所未有"],
        "medium": ["变革", "创新", "颠覆", "突破", "挑战", "改变", "引领", "开创", "打破"],
        "mild": ["全新", "不一样", "改变现状"],
    },
    "丰盛": {
        "strong": ["盛宴", "共同繁荣", "里程碑"],
        "medium": ["丰盛", "庆祝", "分享", "喜悦", "成功", "富足", "繁荣", "欢庆", "收获", "成就"],
        "mild": ["开心", "值得庆祝", "一起享受"],
    },
    "宁静": {
        "strong": ["长期主义", "内心平静", "从容淡定"],
        "medium": ["宁静", "平静", "安心", "稳定", "和谐", "安全", "信任", "踏实", "靠谱"],
        "mild": ["放心", "安心", "没问题"],
    },
}

# 伪价值/反向关键词（基于 4.3 节正反面表）
DIMENSION_NEGATIVE_KEYWORDS: dict[str, list[str]] = {
    "愿景": ["画大饼", "空头支票", "假大空", "说得好听", "不切实际"],
    "尊严": ["面子工程", "道德绑架", "被迫尊重", "虚伪客套"],
    "卓越": ["完美主义", "内卷", "无止境要求", "过度追求"],
    "大爱": ["圣母心", "牺牲绑架", "强迫奉献", "道德高地"],
    "革命": ["为变而变", "破坏性", "瞎折腾", "无脑改革"],
    "丰盛": ["炫耀", "浮夸", "形式主义", "铺张浪费"],
    "宁静": ["逃避现实", "消极躺平", "不作为", "得过且过"],
}

# 情绪→维度映射（基于 04-七个维度模块.md 4.4 节）
EMOTION_DIMENSION_MAP: dict[str, list[str]] = {
    "愤怒": ["愿景", "尊严"],      # 愤怒归因于共同目标未实现
    "恐惧": ["革命", "卓越"],      # 恐惧转化为成长契机
    "挫败": ["宁静", "大爱"],      # 赋予经历以意义
    "急躁": ["愿景", "尊严"],
    "焦虑": ["宁静", "卓越"],
    "悲伤": ["宁静", "大爱"],      # 失去的痛苦 → 赋予意义
}

# 维度→组合映射
DIMENSION_COMBO_MAP: dict[str, str] = {
    "愿景": "愿景+尊严",
    "尊严": "愿景+尊严",
    "大爱": "大爱+宁静",
    "宁静": "大爱+宁静",
    "卓越": "卓越+革命",
    "革命": "卓越+革命",
    "丰盛": "愿景+尊严",  # 丰盛与愿景最接近
}


def identify_dimensions(user_input: str) -> DimensionResult:
    """
    识别用户输入中的七个维度（完整版：支持强弱词+反向检测）

    Args:
        user_input: 用户输入文本

    Returns:
        DimensionResult: 识别结果
    """
    scores: dict[str, float] = {dim: 0.0 for dim in DIMENSION_KEYWORDS}

    # 1. 正向关键词评分（strong=3, medium=2, mild=1）
    for dimension, tiers in DIMENSION_KEYWORDS.items():
        for kw in tiers.get("strong", []):
            if kw in user_input:
                scores[dimension] += 3
        for kw in tiers.get("medium", []):
            if kw in user_input:
                scores[dimension] += 2
        for kw in tiers.get("mild", []):
            if kw in user_input:
                scores[dimension] += 1

    # 2. 反向关键词检测
    is_negative = False
    for dimension, neg_keywords in DIMENSION_NEGATIVE_KEYWORDS.items():
        for kw in neg_keywords:
            if kw in user_input:
                is_negative = True
                scores[dimension] -= 2  # 反向使用扣分

    # 3. 排序
    sorted_dims = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    total_score = sum(max(0, s) for s in scores.values())

    # 4. 提取检测到的维度（分数 > 0）
    detected = [dim for dim, score in sorted_dims if score > 0]

    if not detected:
        return DimensionResult(
            dominant_dimension="",
            dimensions_detected=[],
            confidence=0.0,
            suggested_combo="",
            is_negative=is_negative,
        )

    dominant = detected[0]
    confidence = min(total_score / 10.0, 1.0)

    combo = DIMENSION_COMBO_MAP.get(dominant, "愿景+尊严")

    return DimensionResult(
        dominant_dimension=dominant,
        dimensions_detected=detected,
        confidence=confidence,
        suggested_combo=combo,
        is_negative=is_negative,
    )


def get_emotion_dimensions(emotion_type: str) -> list[str]:
    """
    根据情绪类型返回推荐的升维维度（基于 4.4 节情绪场景升维策略表）

    Args:
        emotion_type: 情绪类型

    Returns:
        list[str]: 推荐维度列表
    """
    return EMOTION_DIMENSION_MAP.get(emotion_type, ["愿景", "尊严"])


def get_upgrade_combo(emotion_type: str, detected_dimensions: list[str]) -> str:
    """
    综合情绪和检测到的维度，推荐升维策略组合

    Args:
        emotion_type: 情绪类型
        detected_dimensions: 检测到的维度列表

    Returns:
        str: 推荐的策略组合名称
    """
    if detected_dimensions:
        return DIMENSION_COMBO_MAP.get(detected_dimensions[0], "愿景+尊严")

    emotion_dims = get_emotion_dimensions(emotion_type)
    if emotion_dims:
        return DIMENSION_COMBO_MAP.get(emotion_dims[0], "愿景+尊严")

    return "愿景+尊严"


def get_upgrade_speech_template(emotion_type: str) -> str:
    """
    获取情绪场景的升维话术模板（基于 4.4 节示例话术）

    Args:
        emotion_type: 情绪类型

    Returns:
        str: 升维话术模板
    """
    templates = {
        "愤怒": "我理解你的愤怒，因为我们都希望这件事做到最好。让我们一起来找出问题，让它真正达到我们期待的样子。",
        "恐惧": "面对不确定，很多人都会怕。但正是这种挑战，让我们有机会突破自己，做出真正了不起的事。",
        "挫败": "失去的痛苦，说明我们曾经真正拥有过。这份记忆会成为我们继续前行的力量。",
        "悲伤": "失去的痛苦，说明我们曾经真正拥有过。这份记忆会成为我们继续前行的力量。",
        "急躁": "我知道你着急，因为你在乎结果。我们聚焦最关键的一件事，把它做扎实，其他的自然会跟上。",
        "焦虑": "焦虑说明你在认真对待。我们把担心的事列出来，看看哪些是真实的，哪些是想象的。",
    }
    return templates.get(emotion_type, "我们回到最初的目标，看看怎么一起解决这个问题。")


# ===== 测试入口 =====

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    test_cases = [
        ("我希望这个项目有个明确的方向", "愿景"),
        ("你根本不尊重我", "尊严"),
        ("我们要做到极致", "卓越"),
        ("这件事让我很愤怒", "情绪→愿景/尊严"),
        ("我害怕失败", "情绪→革命/卓越"),
        ("算了吧随便你", "情绪→宁静/大爱"),
        ("他就是在画大饼", "反向愿景"),
        ("别搞形式主义那一套", "反向丰盛"),
        ("追求完美不是内卷", "反向卓越"),
    ]

    for case, expected in test_cases:
        result = identify_dimensions(case)
        print(f"\n输入: {case}")
        print(f"  期望: {expected}")
        print(f"  主导: {result.dominant_dimension}")
        print(f"  检测: {result.dimensions_detected}")
        print(f"  置信度: {result.confidence:.2f}")
        print(f"  反向: {result.is_negative}")
        print(f"  组合: {result.suggested_combo}")
