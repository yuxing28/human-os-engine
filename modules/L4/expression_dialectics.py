"""
Human-OS Engine - L4 执行工具层：表达辩证与群体逻辑

基于 23-五感系统模块-表达辩证与群体逻辑.md 的内容。
实现三大表达模式（逻辑/情绪/人际）的选择和转化，
以及统一思考框架（ORDER）和群体动员逻辑。
"""

from dataclasses import dataclass


@dataclass
class ExpressionMode:
    """表达模式定义"""
    name: str  # 逻辑模式/情绪模式/人际模式
    scenario: str  # 适用场景
    positive: str  # 正面表现
    negative: str  # 负面表现（过度使用）
    layer_emphasis: list[int]  # 强调的五层（1-5）
    layer_weaken: list[int]  # 弱化的五层


# ===== 三大表达模式 =====

EXPRESSION_MODES: dict[str, ExpressionMode] = {
    "逻辑模式": ExpressionMode(
        name="逻辑模式",
        scenario="理性分析、解决问题、数据驱动的对话",
        positive="清晰、客观、建立秩序",
        negative="冷漠、教条、官僚主义",
        layer_emphasis=[2, 5],  # 强调理解确认、方向引导
        layer_weaken=[3],  # 弱化共情支持
    ),
    "情绪模式": ExpressionMode(
        name="情绪模式",
        scenario="建立情感连接、引发共鸣、危机公关",
        positive="真诚、共情、提升士气",
        negative="情绪勒索、歇斯底里、群体恐慌",
        layer_emphasis=[1, 3],  # 强调即时反应、共情支持
        layer_weaken=[4],  # 弱化具体追问
    ),
    "人际模式": ExpressionMode(
        name="人际模式",
        scenario="社交润滑、关系维护、团队协作",
        positive="尊重、得体、包容",
        negative="虚伪、操控、拉帮结派",
        layer_emphasis=[2, 5],  # 强调理解确认、方向引导
        layer_weaken=[],  # 不弱化任何层，但增加礼貌修饰
    ),
}


# ===== 模式选择规则 =====

def select_expression_mode(
    user_state: dict,
    goal_type: str = "利益价值",
    input_type: str = "混合",
) -> str:
    """
    根据用户状态和目标选择表达模式

    Args:
        user_state: 用户状态字典（含 emotion_type, emotion_intensity, dominant_desire 等）
        goal_type: 目标类型（利益价值/情绪价值/混合）
        input_type: 输入类型（情绪表达/问题咨询/场景描述/混合）

    Returns:
        str: 推荐的表达模式名称
    """
    emotion_type = user_state.get("emotion_type", "平静")
    emotion_intensity = user_state.get("emotion_intensity", 0.5)
    dominant_desire = user_state.get("dominant_desire", "")

    # 规则 1：情绪过载 → 情绪模式
    if emotion_intensity > 0.7:
        return "情绪模式"

    # 规则 2：愤怒/挫败 → 情绪模式（先处理情绪）
    if emotion_type in ("愤怒", "挫败"):
        return "情绪模式"

    # 规则 3：问题咨询 → 逻辑模式
    if input_type == "问题咨询":
        return "逻辑模式"

    # 规则 4：场景描述（人际冲突）→ 人际模式
    if input_type == "场景描述":
        return "人际模式"

    # 规则 5：情绪价值目标 → 情绪模式或人际模式
    if goal_type == "情绪价值":
        if emotion_intensity > 0.4:
            return "情绪模式"
        return "人际模式"

    # 规则 6：利益价值目标 + 低情绪 → 逻辑模式
    if goal_type == "利益价值" and emotion_intensity < 0.4:
        return "逻辑模式"

    # 规则 7：混合场景 → 根据主导欲望判断
    if dominant_desire in ("fear", "wrath"):
        return "情绪模式"
    elif dominant_desire in ("pride", "envy"):
        return "人际模式"
    else:
        return "逻辑模式"


# ===== 模式转化规则 =====

def get_mode_transition(current_mode: str, feedback: str) -> str:
    """
    根据反馈决定表达模式转换

    Args:
        current_mode: 当前表达模式
        feedback: 反馈类型（positive/negative/neutral）

    Returns:
        str: 下一个表达模式
    """
    if feedback == "negative":
        # 负面反馈：切换到更温和的模式
        mode_order = ["逻辑模式", "人际模式", "情绪模式"]
        current_idx = mode_order.index(current_mode) if current_mode in mode_order else 0
        if current_idx < len(mode_order) - 1:
            return mode_order[current_idx + 1]
        return current_mode

    if feedback == "positive":
        # 正面反馈：可以向更理性的模式过渡
        mode_order = ["情绪模式", "人际模式", "逻辑模式"]
        current_idx = mode_order.index(current_mode) if current_mode in mode_order else 0
        if current_idx < len(mode_order) - 1:
            return mode_order[current_idx + 1]
        return current_mode

    return current_mode


# ===== 五层结构影响 =====

def get_layer_adjustment(mode_name: str) -> dict:
    """
    获取表达模式对五层结构的影响

    Returns:
        dict: { "emphasis": [层号], "weaken": [层号], "modifiers": [修饰语] }
    """
    mode = EXPRESSION_MODES.get(mode_name)
    if not mode:
        return {"emphasis": [], "weaken": [], "modifiers": []}

    modifiers = []
    if mode_name == "人际模式":
        modifiers = ["增加礼貌修饰语", "使用'我们'代替'你'", "增加肯定性表达"]

    return {
        "emphasis": mode.layer_emphasis,
        "weaken": mode.layer_weaken,
        "modifiers": modifiers,
    }


# ===== 统一思考框架（ORDER）=====

def build_order_framework(
    goal: str = "",
    shared_interest: str = "",
    rules: str = "",
    vision: str = "",
) -> str:
    """
    构建 ORDER 统一思考框架

    混沌 → 四步统一 → 激光束

    1. 统一目标（定方向）
    2. 统一利益（绑战车·贪婪驱动）
    3. 统一规则（立规矩·恐惧约束）
    4. 统一思想（铸灵魂·愿景牵引）

    Args:
        goal: 共同目标
        shared_interest: 共同利益
        rules: 规则/约束
        vision: 愿景/意义

    Returns:
        str: 框架描述文本
    """
    parts = []

    if goal:
        parts.append(f"我们的共同目标是：{goal}")
    if shared_interest:
        parts.append(f"这对我们都有好处：{shared_interest}")
    if rules:
        parts.append(f"我们需要遵守的规则：{rules}")
    if vision:
        parts.append(f"我们的长远愿景：{vision}")

    if not parts:
        return ""

    return "，".join(parts)


# ===== 群体动员逻辑 =====

def build_group_mobilization(
    mode_name: str,
    audience_size: str = "small",  # small/medium/large
) -> dict:
    """
    根据表达模式和受众规模，生成群体动员策略

    Args:
        mode_name: 表达模式
        audience_size: 受众规模

    Returns:
        dict: 动员策略
    """
    strategies = {
        "small": {
            "focus": "个体连接",
            "method": "一对一深度对话",
            "sensory": "视觉符号 + 触觉反馈",
        },
        "medium": {
            "focus": "群体认同",
            "method": "小组讨论 + 共同决策",
            "sensory": "视觉符号 + 听觉口号",
        },
        "large": {
            "focus": "集体行动",
            "method": "演讲 + 仪式",
            "sensory": "视觉符号 + 听觉口号 + 身体仪式",
        },
    }

    base = strategies.get(audience_size, strategies["small"])

    if mode_name == "情绪模式":
        base["tone"] = "感染力、共情、故事化"
    elif mode_name == "逻辑模式":
        base["tone"] = "数据驱动、逻辑清晰、步骤明确"
    else:
        base["tone"] = "尊重、包容、建立共识"

    return base
