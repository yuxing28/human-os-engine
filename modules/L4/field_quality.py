"""
Human-OS Engine - L4 执行工具层：场域判断与质量检查

基于 场域判断与质量检查.md 的内容。
实现场域判断（五行属性选择）和 21 项质量检查清单。
"""

from dataclasses import dataclass, field


@dataclass
class FieldAssessment:
    """场域评估结果"""
    has_physical_control: bool = False
    is_offline: bool = False
    has_resources: bool = False
    can_apply_field: bool = False
    recommended_element: str = ""  # 金/木/水/火/土
    reason: str = ""


@dataclass
class QualityCheckResult:
    """质量检查结果"""
    passed: bool = True
    failed_items: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: float = 100.0  # 百分制


# ===== 场域判断 =====

# 五行属性定义
FIVE_ELEMENTS: dict[str, dict[str, str]] = {
    "金": {
        "scenario": "谈判、理性决策",
        "design": "金属、白色、冷光、锐利线条",
        "expression": "理性风格、简约设计",
    },
    "木": {
        "scenario": "创意、放松、降低焦虑",
        "design": "植物、绿色、自然材质、曲线",
        "expression": "自然风格、舒适环境",
    },
    "水": {
        "scenario": "神秘感、深度思考、激发好奇",
        "design": "流水、蓝黑色、镜面、暗光",
        "expression": "神秘感、沉浸体验",
    },
    "火": {
        "scenario": "激发行动、制造冲动、促进消费",
        "design": "暖光、红橙色、动态元素、高温",
        "expression": "活力氛围、激情设计",
    },
    "土": {
        "scenario": "建立信任、安全感、长期规划",
        "design": "木质、棕黄色、厚重材质、对称",
        "expression": "稳重风格、信任感营造",
    },
}


def assess_field(
    context=None,
    strategy_plan=None,
    scenario: str = "",
) -> FieldAssessment:
    """
    场域判断

    三个条件必须同时满足才使用场域设计：
    1. 有物理空间控制权
    2. 涉及线下接触
    3. 有时间和资源进行环境设计

    快速判断：
    - 自己家/办公室 → 必须
    - 实体店铺 → 必须
    - 网页/App 界面 → 重要
    - 重要谈判/会议 → 重要
    - 日常沟通/纯文字/电话 → 跳过

    Args:
        context: 可选，用于判断场景
        strategy_plan: 可选，用于推断五行属性
        scenario: 场景描述

    Returns:
        FieldAssessment: 场域评估结果
    """
    result = FieldAssessment()

    # 当前系统主要为线上对话，默认不满足线下条件
    # 后续接入线下场景时可扩展
    result.has_physical_control = False
    result.is_offline = False
    result.has_resources = False
    result.can_apply_field = False
    result.reason = "当前为线上对话场景，跳过场域设计"

    # 根据策略推断五行属性（即使不应用，也提供参考）
    if strategy_plan:
        stage = getattr(strategy_plan, "stage", "")
        mode = getattr(strategy_plan, "mode", "")

        if stage == "钩子" or "冲动" in stage:
            result.recommended_element = "火"
        elif stage == "降门槛" or "放松" in stage:
            result.recommended_element = "木"
        elif stage == "升维" or "信任" in stage:
            result.recommended_element = "土"
        elif mode == "C" or "长期" in stage:
            result.recommended_element = "土"
        elif "理性" in stage or "谈判" in stage:
            result.recommended_element = "金"
        elif "神秘" in stage or "好奇" in stage:
            result.recommended_element = "水"
        else:
            result.recommended_element = "土"  # 默认土（信任感）

    return result


# ===== 质量检查清单 =====

# 从统一常量导入
from utils.constants import (
    PRIORITY_1_REPLACEMENTS,
    PRIORITY_2_REPLACEMENTS,
    PRIORITY_3_REPLACEMENTS,
    INTERNAL_TERMS,
    CUSTOMER_SERVICE_WORDS,
    CLINGY_WORDS,
    SELF_REF_WORDS,
)

# 禁用词汇（特别检查）
FORBIDDEN_WORDS: dict[str, list[str]] = {
    "priority_1": list(PRIORITY_1_REPLACEMENTS.keys()),
    "priority_2": list(PRIORITY_2_REPLACEMENTS.keys()),
    "priority_3": list(PRIORITY_3_REPLACEMENTS.keys()),
}

# AI 新造词（禁止使用）
AI_NEOLOGISMS: list[str] = [
    "注意力黑洞", "最小可执行单元学习法", "学习成果展示墙",
    "同频者", "能量管理系统", "认知重构", "心智模型",
    "底层逻辑", "颗粒度", "抓手", "赋能", "链路",
]


def quality_check(output: str, context=None) -> QualityCheckResult:
    """
    21 项质量检查清单

    检查维度：
    1. 识别准确性
    2. 策略完整性
    3. 表达规范性
    4. 特别检查（禁用词汇）
    5. 逻辑自洽性
    6. 可执行性
    7. 人设一致性

    Args:
        output: 待检查的输出文本
        context: 可选，用于上下文相关检查

    Returns:
        QualityCheckResult: 检查结果
    """
    result = QualityCheckResult()
    score = 100.0

    # ===== 维度 1：识别准确性 =====
    # （需要 context 数据，此处跳过，由调用方评估）

    # ===== 维度 2：策略完整性 =====
    # （需要 context 数据，此处跳过）

    # ===== 维度 3：表达规范性 =====

    # 检查客服词汇
    customer_service_words = ["亲", "小助手", "AI助手", "为您服务"]
    for word in customer_service_words:
        if word in output:
            result.failed_items.append(f"包含客服词汇: {word}")
            score -= 10

    # 检查肉麻表达
    clingy_words = ["宝贝", "亲爱的", "爱你", "么么哒"]
    for word in clingy_words:
        if word in output:
            result.failed_items.append(f"包含肉麻表达: {word}")
            score -= 10

    # ===== 维度 4：特别检查（禁用词汇）=====

    for priority, words in FORBIDDEN_WORDS.items():
        for word in words:
            if word in output:
                result.failed_items.append(f"包含禁用词（{priority}）: {word}")
                if priority == "priority_1":
                    score -= 20
                elif priority == "priority_2":
                    score -= 15
                else:
                    score -= 10

    # 检查 AI 新造词
    for word in AI_NEOLOGISMS:
        if word in output:
            result.warnings.append(f"包含 AI 新造词: {word}")
            score -= 5

    # 检查内部术语（框架泄露）
    for term in INTERNAL_TERMS:
        if term in output:
            result.failed_items.append(f"框架泄露（内部术语）: {term}")
            score -= 15

    # ===== 维度 5：逻辑自洽性 =====
    # （需要 context 数据，此处跳过）

    # ===== 维度 6：可执行性 =====

    # 检查输出是否为空
    if not output or not output.strip():
        result.failed_items.append("输出为空")
        score -= 50

    # 检查输出长度
    if len(output) > 300:
        result.warnings.append(f"输出过长（{len(output)} 字），超过 300 字限制")
        score -= 5

    # ===== 维度 7：人设一致性 =====

    # 检查自称
    self_ref_words = ["我是AI", "我是人工智能", "我是助手", "作为AI", "作为助手"]
    for word in self_ref_words:
        if word in output:
            result.failed_items.append(f"包含不当自称: {word}")
            score -= 15

    # 检查客服辞令
    apology_words = ["抱歉", "对不起", "不好意思", "打扰了"]
    for word in apology_words:
        if word in output:
            result.warnings.append(f"包含客服辞令: {word}")
            score -= 3

    # 规范化分数
    result.score = max(0.0, min(100.0, score))
    result.passed = len(result.failed_items) == 0

    return result
