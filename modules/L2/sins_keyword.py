"""
Human-OS Engine - L2 识别模块：八宗罪关键词识别

基于 06-八宗罪关键词识别.md 和 03-八宗罪模块.md 的内容。
通过关键词匹配识别用户当前主导欲望，并判断压制/转化关系。

输入：用户输入文本
输出：DesiresResult（欲望权重 + 置信度 + 关系标注）

压制关系：一方过强会抑制另一方 → 激活被压制方恢复平衡
转化关系：情绪变形为另一种表现 → 先处理原始情绪再疏导转化行为
"""

import math
from schemas.user_state import Desires
from schemas.module_io import DesiresResult


# ===== 八宗罪关键词库 =====

SINS_KEYWORDS: dict[str, dict[str, list[str]]] = {
    "fear": {
        "strong": ["崩溃", "绝望", "受够了", "害怕极了", "恐惧", "吓死了", "完了", "死定了", "没救了"],
        "medium": ["害怕", "担心", "焦虑", "紧张", "不安", "恐慌", "畏惧", "退缩", "犹豫", "风险", "失败", "损失", "赔", "亏", "错过", "来不及", "危险", "威胁", "安全感", "保障", "稳定", "确定性", "怂了", "怂", "不敢"],
        "mild": ["不确定", "可能", "万一", "如果", "有点怕", "有点担心", "没把握", "心里没底"],
    },
    "greed": {
        "strong": ["暴富", "一夜暴富", "发大财", "赚翻了", "血赚", "躺赚", "稳赚", "行业第一", "第一名"],
        "medium": ["赚钱", "收入", "回报", "收益", "利润", "价值", "投资", "机会", "增长", "提升", "进步", "成功", "野心", "上进", "顶尖", "领先", "超越", "获得", "拥有", "占有", "更强", "更高", "更快"],
        "mild": ["想要", "希望", "期待", "目标", "梦想", "计划", "更好", "最好的"],
    },
    "sloth": {
        "strong": ["不想动", "懒得做", "太麻烦了", "算了吧", "放弃", "躺平", "摆烂"],
        "medium": ["麻烦", "复杂", "费劲", "累", "懒", "拖延", "不想", "没时间", "忙", "门槛高", "快速", "方便", "省事", "轻松", "无脑", "傻瓜式"],
        "mild": ["能不能简单点", "有没有更简单", "一步到位", "一键", "自动"],
    },
    "envy": {
        "strong": ["凭什么他行我不行", "嫉妒死了", "恨死他了", "别人都在用"],
        "medium": ["嫉妒", "羡慕", "攀比", "比较", "不如别人", "别人有", "差距", "凭什么", "不公平", "为什么他能", "被超越", "对标", "看齐", "主流", "趋势"],
        "mild": ["别人", "人家", "同事", "朋友", "同学", "他们都", "大家都在"],
    },
    "pride": {
        "strong": ["我最牛", "谁都不如我", "看不起", "瞧不上", "拿不出手"],
        "medium": ["面子", "尊严", "尊重", "认可", "身份", "地位", "荣誉", "骄傲", "自豪", "独特", "特别", "格调", "品味", "档次", "逼格", "气质", "优越", "与众不同", "有面儿"],
        "mild": ["我", "我觉得", "我认为", "我的", "自己的"],
    },
    "lust": {
        "strong": ["迷恋", "上瘾", "沉迷", "无法自拔"],
        "medium": ["喜欢", "心动", "吸引", "魅力", "好看", "漂亮", "帅", "美", "享受", "体验", "感觉", "设计感", "审美", "艺术感", "视觉", "沉浸", "性感", "迷人", "诱惑"],
        "mild": ["还行", "不错", "有意思", "挺好的"],
    },
    "gluttony": {
        "strong": ["吃撑了", "买爆", "囤货", "疯狂购物", "停不下来", "一刷就是几个小时"],
        "medium": ["满足", "享受", "丰富", "多样", "够多", "更多", "还要", "囤", "买", "吃", "消费", "沉浸", "过瘾", "爽", "畅快", "刷视频", "信息流", "刷屏", "吃瓜", "追剧", "上瘾"],
        "mild": ["不错", "可以", "还行", "试试"],
    },
    "wrath": {
        "strong": ["气死了", "受不了了", "忍无可忍", "愤怒", "火大", "滚", "操", "傻子", "白痴", "智障", "别废话", "少废话"],
        "medium": ["生气", "烦", "讨厌", "不满", "抱怨", "指责", "批评", "不公平", "过分",
                   "懂什么", "凭什么", "算什么", "做梦", "可笑", "荒唐", "浪费时间", "垃圾",
                   "套路", "画大饼", "low", "逗我", "教我", "就这点", "改变", "打破", "反抗",
                   "不能接受", "必须", "底线", "原则", "坚持", "对抗", "斗争", "痛点", "糟糕"],
        "mild": ["不爽", "有点烦", "不太满意", "还好吧", "无语", "服了", "呵呵"],
    },
}

LEVEL_WEIGHTS = {"strong": 3, "medium": 2, "mild": 1}
SIGMOID_K = 1.1
SIGMOID_CENTER = 2.0


def extract_keywords(user_input: str) -> dict[str, int]:
    """
    从用户输入中提取八宗罪关键词得分（原始得分）

    Returns:
        dict[str, int]: 各欲望的原始得分
    """
    scores: dict[str, int] = {sin: 0 for sin in SINS_KEYWORDS}

    for sin, levels in SINS_KEYWORDS.items():
        for level, keywords in levels.items():
            weight = LEVEL_WEIGHTS[level]
            for keyword in keywords:
                if keyword in user_input:
                    scores[sin] += weight

    return scores


def normalize_scores(raw_scores: dict[str, int]) -> dict[str, float]:
    """
    将原始得分归一化到 0-1 范围

    这里改成 Sigmoid 归一化。
    原因很简单：关键词库越来越大之后，按“全词库理论最大值”去除，会把真实权重压得太低，
    导致上游识别有命中、下游优先级却永远抬不起来。
    """
    return {
        sin: 0.0 if score <= 0 else min(1.0, 1 / (1 + math.exp(-SIGMOID_K * (score - SIGMOID_CENTER))))
        for sin, score in raw_scores.items()
    }


def calculate_confidence(raw_scores: dict[str, int], user_input: str) -> float:
    """
    计算识别置信度

    规则尽量贴原始文档：
    - 基础置信度看“到底命中了多少个真实关键词”
    - 若命中强烈词，额外加分
    - 若某一类欲望得分明显高，说明主导性更强，再加一点
    """
    matched_keyword_count = 0
    has_strong = False

    for sin, levels in SINS_KEYWORDS.items():
        for level, keywords in levels.items():
            matched = sum(1 for kw in keywords if kw in user_input)
            matched_keyword_count += matched
            if level == "strong" and matched > 0:
                has_strong = True

    dominant_score = max(raw_scores.values()) if raw_scores else 0
    base = min(matched_keyword_count / 4.0, 0.7)
    strong_bonus = 0.1 if has_strong else 0.0
    dominant_bonus = 0.1 if dominant_score >= 4 else 0.0

    return min(base + strong_bonus + dominant_bonus, 1.0)


def _build_desires(normalized: dict[str, float]) -> Desires:
    return Desires(
        fear=normalized.get("fear", 0.0),
        greed=normalized.get("greed", 0.0),
        sloth=normalized.get("sloth", 0.0),
        envy=normalized.get("envy", 0.0),
        pride=normalized.get("pride", 0.0),
        lust=normalized.get("lust", 0.0),
        gluttony=normalized.get("gluttony", 0.0),
        wrath=normalized.get("wrath", 0.0),
    )


def identify_desires(user_input: str) -> DesiresResult:
    """
    八宗罪关键词识别主函数

    Args:
        user_input: 用户输入文本

    Returns:
        DesiresResult: 欲望识别结果
    """
    # 1. 提取原始得分
    raw_scores = extract_keywords(user_input)

    # 2. 归一化
    normalized = normalize_scores(raw_scores)

    # 3. 计算置信度
    confidence = calculate_confidence(raw_scores, user_input)

    # 4. 构建 Desires 模型
    desires = _build_desires(normalized)

    # 5. 分析压制/转化关系
    relations = analyze_desire_relations(normalized)

    return DesiresResult(
        desires=desires,
        confidence=confidence,
        raw_scores=raw_scores,
        relations=relations,
    )


# ===== 压制关系 / 转化关系 =====
# 基于 03-八宗罪模块.md 模块 3.3

# 压制关系：一方过强会抑制另一方，策略是激活被压制方恢复平衡
SUPPRESSION_RELATIONS: list[dict[str, str]] = [
    {"dominant": "fear",    "suppressed": "greed",  "strategy": "activate_greed",   "hint": "展示机会、可视化收益，激活扩张动力"},
    {"dominant": "greed",   "suppressed": "fear",   "strategy": "activate_fear",    "hint": "提示风险、损失警示，防止冲动冒险"},
    {"dominant": "sloth",   "suppressed": "greed",  "strategy": "activate_greed",   "hint": "可视化收益+降低门槛，激活行动欲"},
    {"dominant": "envy",    "suppressed": "pride",  "strategy": "satisfy_pride",    "hint": "提供独特性、身份认同，满足傲慢"},
    {"dominant": "pride",   "suppressed": "fear",   "strategy": "activate_fear",    "hint": "风险警示，或认可价值后温和提醒"},
]

# 转化关系：情绪变形为另一种表现，策略是先处理原始情绪再疏导转化行为
TRANSFORMATION_RELATIONS: list[dict[str, str]] = [
    {"source": "fear", "manifests_as": "gluttony", "strategy": "treat_fear_first", "hint": "先处理恐惧根源（提供确定性），再引导理性（展示后果）"},
    {"source": "fear", "manifests_as": "wrath",    "strategy": "treat_fear_first", "hint": "先处理恐惧根源（提供确定性），再引导理性（分析原因）"},
]

# 压制关系触发阈值：主导欲望权重需超过此值才判定为"过度"
SUPPRESSION_THRESHOLD = 0.55
# 转化关系触发阈值：原始情绪需有一定权重，且表现形态权重也需超过此值
TRANSFORMATION_SOURCE_THRESHOLD = 0.35
TRANSFORMATION_MANIFEST_THRESHOLD = 0.45


def analyze_desire_relations(normalized: dict[str, float]) -> dict[str, list[dict]]:
    """
    分析当前欲望权重中的压制关系和转化关系。

    Args:
        normalized: 归一化后的欲望权重

    Returns:
        dict: {
            "suppressions": [激活被压制方的策略列表],
            "transformations": [先处理原始情绪的策略列表],
        }
    """
    suppressions = []
    transformations = []

    # 1. 检查压制关系
    for rel in SUPPRESSION_RELATIONS:
        dominant_weight = normalized.get(rel["dominant"], 0.0)
        suppressed_weight = normalized.get(rel["suppressed"], 0.0)
        if dominant_weight >= SUPPRESSION_THRESHOLD and dominant_weight > suppressed_weight * 1.5:
            suppressions.append({
                "type": "suppression",
                "dominant": rel["dominant"],
                "suppressed": rel["suppressed"],
                "strategy": rel["strategy"],
                "hint": rel["hint"],
                "dominant_weight": round(dominant_weight, 3),
                "suppressed_weight": round(suppressed_weight, 3),
            })

    # 2. 检查转化关系
    for rel in TRANSFORMATION_RELATIONS:
        source_weight = normalized.get(rel["source"], 0.0)
        manifest_weight = normalized.get(rel["manifests_as"], 0.0)
        if (source_weight >= TRANSFORMATION_SOURCE_THRESHOLD and
            manifest_weight >= TRANSFORMATION_MANIFEST_THRESHOLD):
            transformations.append({
                "type": "transformation",
                "source": rel["source"],
                "manifests_as": rel["manifests_as"],
                "strategy": rel["strategy"],
                "hint": rel["hint"],
                "source_weight": round(source_weight, 3),
                "manifest_weight": round(manifest_weight, 3),
            })

    return {
        "suppressions": suppressions,
        "transformations": transformations,
    }


# ===== 测试入口 =====

if __name__ == "__main__":
    test_cases = [
        "我好害怕失败，担心会损失很多钱",
        "我想赚钱，有什么好机会吗",
        "太麻烦了，不想做",
        "凭什么他能成功我不行",
        "我要最好的，最独特的",
        "好烦啊，气死我了",
        "随便吧，无所谓",
    ]

    for text in test_cases:
        result = identify_desires(text)
        dominant, score = result.desires.get_dominant()
        print(f"\n输入: {text}")
        print(f"主导欲望: {dominant} ({score:.2f})")
        print(f"置信度: {result.confidence:.2f}")
        print(f"原始得分: {result.raw_scores}")
