"""
Human-OS Engine - L4 执行工具层：五层结构

基于 26-协作温度模块-五层结构与识别算法.md 的内容。
根据用户情绪强度决定层级组合，并为每层选择武器。

这是输出格式化的"骨架"。
"""

from dataclasses import dataclass
from schemas.user_state import UserState
from schemas.enums import EmotionType, MotiveType
from modules.L3.weapon_arsenal import Weapon, select_weapon_for_layer, get_weapon


@dataclass
class LayerConfig:
    """层级配置"""
    layer: int
    name: str
    purpose: str


# 五层定义
LAYERS = {
    1: LayerConfig(1, "即时反应", "情绪共振，让对方知道'你听到了'"),
    2: LayerConfig(2, "理解确认", "确认理解了对方的情况，建立信任"),
    3: LayerConfig(3, "共情支持", "降低焦虑、羞耻感、压力"),
    4: LayerConfig(4, "具体追问", "收集关键信息，聚焦问题"),
    5: LayerConfig(5, "方向引导", "给出可选路径，让用户做选择"),
}


VAGUE_PROBLEM_MARKERS = [
    "这件事", "这个问题", "这种情况", "这个人", "这个客户", "这个项目",
    "这个局面", "这波", "这个关系", "这事", "那边",
]
ASK_FOR_HELP_MARKERS = [
    "怎么办", "怎么弄", "怎么处理", "咋办", "怎么推进", "怎么搞", "怎么做",
]
DETAIL_MARKERS = [
    "因为", "但是", "已经", "一直", "最近", "刚才", "后来", "结果", "对方", "现在",
]


def determine_layer_combination(user: UserState, mode: str = "") -> list[int]:
    """
    根据用户状态决定层级组合

    规则（26-协作温度模块完整映射）：
    - 急躁：只保留 1+5
    - 高情绪（>0.7）：完整五层 1+2+3+4+5
    - 中情绪（0.4-0.7）：省略第3层 1+2+4+5
    - 低情绪（<0.4）：根据动机类型细分
      - 平静+生活期待：1+2+3+5（赞美共享）
      - 平静+灵感兴奋：1+2+4+5（认可推进）
      - 其他：2+4+5
    - Mode C（升维）：1+3+5（即时反应+共情支持+方向引导）

    Args:
        user: 用户状态
        mode: 当前模式（可选，"C" 时使用升维组合）

    Returns:
        list[int]: 层级组合
    """
    # 【Phase 4】Mode C 升维模式：侧重第3层（共情支持）和第5层（方向引导）
    if mode == "C":
        return [1, 3, 5]
    intensity = user.emotion.intensity
    emotion_type = user.emotion.type

    # 急躁用户
    if emotion_type == EmotionType.IMPATIENT:
        return [1, 5]

    # 高情绪
    if intensity > 0.7:
        return [1, 2, 3, 4, 5]

    # 中情绪
    if intensity >= 0.4:
        return [1, 2, 4, 5]

    # 低情绪：根据动机类型细分
    if user.motive == MotiveType.LIFE_EXPECTATION:
        return [1, 2, 3, 5]  # 平静+生活期待 → 赞美共享
    if user.motive == MotiveType.INSPIRATION:
        return [1, 2, 4, 5]  # 平静+灵感兴奋 → 认可推进

    # 默认低情绪
    return [2, 4, 5]


def _is_detailed_enough(user_input: str) -> bool:
    text = (user_input or "").strip()
    punctuation_count = sum(text.count(mark) for mark in ["，", "。", "？", "！", ",", ".", "?", "!"])
    if len(text) >= 32:
        return True
    if punctuation_count >= 2 and len(text) >= 18:
        return True
    if sum(1 for marker in DETAIL_MARKERS if marker in text) >= 2 and len(text) >= 18:
        return True
    return False


def should_trigger_layer1(
    user: UserState,
    user_input: str,
    input_type: str = "",
    scene: str = "",
    identity_hint: str = "",
    situation_hint: str = "",
    mode: str = "",
    guidance_needed: bool = False,
    short_utterance: bool = False,
    goal_description: str = "",
) -> bool:
    """
    第1层即时反应的 v1 触发规则。

    核心思路：
    - 大多数局面都保留“先接一下”
    - 只有在低情绪、很直接、目标很清楚的动作型问题里，才允许第1层让位
    """
    text = (user_input or "").strip()
    input_type = input_type or ""
    scene = scene or ""
    identity_hint = identity_hint or ""
    situation_hint = situation_hint or ""

    if mode == "C":
        return True

    if guidance_needed:
        return True

    if short_utterance:
        return user.emotion.intensity >= 0.5

    if identity_hint == "关系沟通" or situation_hint == "稳定情绪":
        return True

    if scene == "emotion" or input_type in {"情绪表达", "混合"}:
        return True

    if user.emotion.intensity >= 0.42:
        return True

    if input_type == "问题咨询" and scene in {"sales", "management", "negotiation"} and user.emotion.intensity < 0.4:
        if goal_description not in {"", "未明确"} and any(keyword in text for keyword in ["方案", "步骤", "推进", "成交", "话术", "模板", "直接", "动作"]):
            return False

    if len(text) >= 18 and any(keyword in text for keyword in ["其实", "但", "但是", "又怕", "又想", "难受", "委屈", "卡住"]):
        return True

    if len(text) <= 10 and user.emotion.intensity < 0.35:
        return False

    return True


def should_trigger_layer4(
    user: UserState,
    user_input: str,
    input_type: str = "",
    mode: str = "",
    guidance_needed: bool = False,
    short_utterance: bool = False,
    goal_description: str = "",
) -> bool:
    """
    第4层具体追问的 v1 触发规则。

    核心思路：
    - 不是默认跟着套餐走
    - 只在“信息确实不够，直接给方案风险高”时触发
    - 高情绪、急躁、短承接时，尽量先别追问
    """
    text = (user_input or "").strip()
    input_type = input_type or ""

    if mode == "C":
        return False
    if short_utterance:
        return False
    if user.emotion.type == EmotionType.IMPATIENT:
        return False
    if user.emotion.intensity >= 0.82:
        return False

    if guidance_needed:
        return True

    if goal_description in {"", "未明确"} and input_type in {"问题咨询", "场景描述", "混合"}:
        return True

    if input_type not in {"问题咨询", "场景描述", "混合"}:
        return False

    if _is_detailed_enough(text):
        return False

    if any(marker in text for marker in VAGUE_PROBLEM_MARKERS):
        return True

    if any(marker in text for marker in ASK_FOR_HELP_MARKERS) and len(text) <= 18:
        return True

    if len(text) <= 12 and any(marker in text for marker in ["怎么", "如何", "哪步", "哪里", "为啥"]):
        return True

    return False


def should_trigger_layer2(
    user: UserState,
    user_input: str,
    input_type: str = "",
    scene: str = "",
    identity_hint: str = "",
    situation_hint: str = "",
    mode: str = "",
    guidance_needed: bool = False,
    short_utterance: bool = False,
    goal_description: str = "",
) -> bool:
    """
    第2层理解确认的 v1 触发规则。

    核心思路：
    - 只有在需要先对齐理解、先稳住关系、先确认局面时才上
    - 很短、很直、很明确的推进问题，不默认带第2层
    """
    text = (user_input or "").strip()
    input_type = input_type or ""
    scene = scene or ""
    identity_hint = identity_hint or ""
    situation_hint = situation_hint or ""

    if short_utterance and user.emotion.intensity < 0.65:
        return False

    if user.emotion.type == EmotionType.IMPATIENT and user.emotion.intensity >= 0.58:
        return False

    if guidance_needed:
        return True

    if identity_hint == "关系沟通":
        return True

    if situation_hint in {"稳定情绪", "协商分歧"}:
        return True

    if input_type in {"混合", "场景描述"}:
        return True

    if goal_description in {"", "未明确"} and input_type in {"问题咨询", "混合", "场景描述"}:
        return True

    if scene in {"emotion", "negotiation"} and user.emotion.intensity >= 0.38:
        return True

    if user.emotion.intensity >= 0.68:
        return True

    if len(text) >= 18 and any(keyword in text for keyword in ["其实", "但", "但是", "可是", "一边", "又怕", "又想", "既想", "同时"]):
        return True

    if _is_detailed_enough(text) and any(keyword in text for keyword in ["对方", "关系", "边界", "节奏", "误会", "推进"]):
        return True

    if input_type == "问题咨询" and scene in {"sales", "management"} and user.emotion.intensity < 0.45:
        if any(keyword in text for keyword in ["方案", "步骤", "推进", "成交", "话术", "模板", "直接"]) and goal_description not in {"", "未明确"}:
            return False

    if len(text) <= 10:
        return False

    return False


def should_trigger_layer3(
    user: UserState,
    user_input: str,
    input_type: str = "",
    scene: str = "",
    identity_hint: str = "",
    situation_hint: str = "",
    mode: str = "",
    short_utterance: bool = False,
) -> bool:
    """
    第3层共情支持的 v1 触发规则。

    核心思路：
    - 只有真的需要“先接住、先降压、先修复”时才上
    - 纯理性咨询、低情绪推进场景，不默认带第3层
    """
    text = (user_input or "").strip()
    input_type = input_type or ""
    scene = scene or ""
    identity_hint = identity_hint or ""
    situation_hint = situation_hint or ""

    if short_utterance and user.emotion.intensity < 0.55:
        return False

    if mode == "C":
        return True

    if situation_hint == "稳定情绪":
        return True

    if scene == "emotion" or identity_hint == "关系沟通":
        if user.emotion.intensity >= 0.45:
            return True

    if user.emotion.type in {EmotionType.ANGRY, EmotionType.FRUSTRATED} and user.emotion.intensity >= 0.55:
        return True

    if user.emotion.type == EmotionType.CONFUSED and user.emotion.intensity >= 0.62:
        return True

    if any(keyword in text for keyword in ["委屈", "难受", "崩溃", "撑不住", "想哭", "吵架", "翻旧账", "冷战"]):
        return True

    if input_type == "情绪表达" and user.emotion.intensity >= 0.45:
        return True

    if input_type == "问题咨询" and user.emotion.intensity < 0.5 and scene in {"sales", "negotiation", "management"}:
        return False

    if input_type == "问题咨询" and any(keyword in text for keyword in ["怎么做", "方案", "步骤", "推进", "成交"]) and user.emotion.intensity < 0.58:
        return False

    return False


def should_trigger_layer5(
    user: UserState,
    user_input: str,
    input_type: str = "",
    scene: str = "",
    identity_hint: str = "",
    situation_hint: str = "",
    mode: str = "",
    short_utterance: bool = False,
    guidance_needed: bool = False,
    goal_description: str = "",
    layer4_needed: bool = False,
) -> bool:
    """
    第5层方向引导的 v1 触发规则。

    核心思路：
    - 只有在“现在适合推进、适合收口”时才上
    - 信息还不够、情绪还太高时，不急着给方向
    """
    text = (user_input or "").strip()
    input_type = input_type or ""
    scene = scene or ""
    situation_hint = situation_hint or ""

    if mode == "C":
        return True
    if short_utterance:
        return False
    if guidance_needed or layer4_needed:
        return False
    if goal_description in {"", "未明确"}:
        return False
    if situation_hint == "稳定情绪" and user.emotion.intensity >= 0.65:
        return False
    if user.emotion.intensity >= 0.88:
        return False

    if situation_hint in {"推进结果", "协商分歧"}:
        return True

    if input_type == "问题咨询" and any(keyword in text for keyword in ["怎么办", "怎么做", "方案", "步骤", "推进", "成交", "怎么推进"]):
        return True

    if scene in {"sales", "negotiation", "management"} and user.emotion.intensity < 0.7:
        return True

    if input_type == "场景描述" and user.emotion.intensity < 0.55 and any(keyword in text for keyword in ["怎么回", "怎么说", "怎么谈", "怎么处理"]):
        return True

    if identity_hint == "关系沟通" and user.emotion.intensity < 0.45 and any(keyword in text for keyword in ["接下来", "下一步", "怎么修复", "怎么聊"]):
        return True

    return False


def resolve_layer_sequence(
    active_layers: list[int],
    user: UserState,
    scene: str = "",
    identity_hint: str = "",
    situation_hint: str = "",
    mode: str = "",
    layer4_needed: bool = False,
) -> list[int]:
    """
    把已触发的层收成更像真人说话的顺序。
    """
    remaining = list(dict.fromkeys(active_layers))
    ordered: list[int] = []

    def take(layer: int) -> None:
        if layer in remaining and layer not in ordered:
            ordered.append(layer)

    relationship_repair = scene == "emotion" or identity_hint == "关系沟通"
    need_stabilize_first = situation_hint == "稳定情绪" or (
        relationship_repair and user.emotion.intensity >= 0.6
    )
    direct_push = (
        scene in {"sales", "management", "negotiation"}
        and user.emotion.intensity < 0.4
        and not layer4_needed
    )

    if mode == "C":
        for layer in [1, 3, 2, 5, 4]:
            take(layer)
        return ordered

    take(1)

    if need_stabilize_first:
        for layer in [3, 2, 4, 5]:
            take(layer)
        return ordered

    if layer4_needed:
        for layer in [2, 3, 4, 5]:
            take(layer)
        return ordered

    if direct_push:
        for layer in [5, 2, 3, 4]:
            take(layer)
        return ordered

    for layer in [2, 3, 4, 5]:
        take(layer)

    return ordered


def generate_five_layer_output(
    user: UserState,
    strategy_weapons: list[str],
    weapon_usage: dict[str, int],
    mode: str = "",
    user_input: str = "",
    input_type: str = "",
    scene: str = "",
    identity_hint: str = "",
    situation_hint: str = "",
    guidance_needed: bool = False,
    short_utterance: bool = False,
    goal_description: str = "",
) -> list[dict]:
    """
    生成五层结构输出

    Args:
        user: 用户状态
        strategy_weapons: 策略推荐的武器列表
        weapon_usage: 武器使用计数
        mode: 当前模式（可选，"C" 时使用升维组合）
        user_input: 当前用户输入
        input_type: 输入类型
        scene: 当前主场景
        identity_hint: 当前身份提示
        situation_hint: 当前情境提示
        guidance_needed: 是否需要补充关键信息
        short_utterance: 是否为短承接输入
        goal_description: 当前目标描述

    Returns:
        list[dict]: 每层的配置（layer, name, weapon, purpose）
    """
    combination = determine_layer_combination(user, mode)
    layer1_needed = should_trigger_layer1(
        user=user,
        user_input=user_input,
        input_type=input_type,
        scene=scene,
        identity_hint=identity_hint,
        situation_hint=situation_hint,
        mode=mode,
        guidance_needed=guidance_needed,
        short_utterance=short_utterance,
        goal_description=goal_description,
    )
    layer2_needed = should_trigger_layer2(
        user=user,
        user_input=user_input,
        input_type=input_type,
        scene=scene,
        identity_hint=identity_hint,
        situation_hint=situation_hint,
        mode=mode,
        guidance_needed=guidance_needed,
        short_utterance=short_utterance,
        goal_description=goal_description,
    )
    layer3_needed = should_trigger_layer3(
        user=user,
        user_input=user_input,
        input_type=input_type,
        scene=scene,
        identity_hint=identity_hint,
        situation_hint=situation_hint,
        mode=mode,
        short_utterance=short_utterance,
    )
    layer4_needed = should_trigger_layer4(
        user=user,
        user_input=user_input,
        input_type=input_type,
        mode=mode,
        guidance_needed=guidance_needed,
        short_utterance=short_utterance,
        goal_description=goal_description,
    )
    layer5_needed = should_trigger_layer5(
        user=user,
        user_input=user_input,
        input_type=input_type,
        scene=scene,
        identity_hint=identity_hint,
        situation_hint=situation_hint,
        mode=mode,
        short_utterance=short_utterance,
        guidance_needed=guidance_needed,
        goal_description=goal_description,
        layer4_needed=layer4_needed,
    )
    if layer1_needed and 1 not in combination:
        combination.append(1)
    if not layer1_needed and 1 in combination:
        combination = [layer for layer in combination if layer != 1]
    if layer2_needed and 2 not in combination:
        combination.append(2)
    if not layer2_needed and 2 in combination:
        combination = [layer for layer in combination if layer != 2]
    if layer3_needed and 3 not in combination:
        combination.append(3)
    if not layer3_needed and 3 in combination:
        combination = [layer for layer in combination if layer != 3]
    if layer4_needed and 4 not in combination:
        combination.append(4)
    if not layer4_needed and 4 in combination:
        combination = [layer for layer in combination if layer != 4]
    if layer5_needed and 5 not in combination:
        combination.append(5)
    if not layer5_needed and 5 in combination:
        combination = [layer for layer in combination if layer != 5]
    combination = resolve_layer_sequence(
        active_layers=combination,
        user=user,
        scene=scene,
        identity_hint=identity_hint,
        situation_hint=situation_hint,
        mode=mode,
        layer4_needed=layer4_needed,
    )

    user_state_dict = {
        "emotion_type": user.emotion.type.value if hasattr(user.emotion.type, 'value') else user.emotion.type,
        "emotion_intensity": user.emotion.intensity,
    }

    layers_output = []

    for layer_num in combination:
        layer_config = LAYERS[layer_num]

        # 选择武器：优先使用策略推荐的武器，否则从武器库选择
        weapon = None

        # 尝试从策略武器中选一个适合该层的
        for w_name in strategy_weapons:
            w = get_weapon(w_name)
            if w and weapon_usage.get(w_name, 0) < 2:
                weapon = w
                break

        # 如果没有合适的，从武器库选择
        if not weapon:
            weapon = select_weapon_for_layer(layer_num, user_state_dict, weapon_usage)

        layers_output.append({
            "layer": layer_num,
            "name": layer_config.name,
            "purpose": layer_config.purpose,
            "weapon": weapon.name if weapon else "共情",
            "weapon_type": weapon.type.value if weapon else "温和型",
        })

    return layers_output


# ===== 测试入口 =====

if __name__ == "__main__":
    from schemas.user_state import Emotion, Desires
    from schemas.enums import EmotionType

    test_cases = [
        {"name": "高情绪", "user": UserState(emotion=Emotion(type=EmotionType.FRUSTRATED, intensity=0.8))},
        {"name": "中情绪", "user": UserState(emotion=Emotion(type=EmotionType.CONFUSED, intensity=0.5))},
        {"name": "低情绪", "user": UserState(emotion=Emotion(type=EmotionType.CALM, intensity=0.3))},
        {"name": "急躁", "user": UserState(emotion=Emotion(type=EmotionType.IMPATIENT, intensity=0.6))},
    ]

    for case in test_cases:
        combo = determine_layer_combination(case["user"])
        print(f"\n{case['name']}: {combo}")

        output = generate_five_layer_output(case["user"], [], {})
        for layer in output:
            print(f"  第{layer['layer']}层 {layer['name']}: {layer['weapon']}")
