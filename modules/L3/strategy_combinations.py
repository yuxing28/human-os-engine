"""
Human-OS Engine - L3 策略工具层：策略组合库

基于 策略组合库.md 的内容。
提供钩子、放大、降门槛、升维、防御等阶段的预定义组合。

输入用户状态，返回推荐的策略方案。
"""

from dataclasses import dataclass, field
from schemas.user_state import UserState
from schemas.strategy import StrategyPlan


@dataclass
class Combo:
    """策略组合定义"""
    name: str
    stage: str  # 钩子/放大/降门槛/升维/防御
    desires: list[str]  # 涉及的欲望（如 ["greed", "fear"]）
    logic: str  # 策略逻辑
    weapons: list[str]  # 推荐武器
    fallback: str  # 备选组合
    suitable_for: list[str]  # 适用场景


# ===== 钩子组合 =====

HOOK_COMBOS: dict[str, Combo] = {
    "贪婪+恐惧": Combo(
        name="贪婪+恐惧",
        stage="钩子",
        desires=["greed", "fear"],
        logic="先激发贪婪（展示机会），再用恐惧（提示风险）推动决策",
        weapons=["给予价值", "制造紧迫感", "描绘共同未来"],
        fallback="好奇+稀缺",
        suitable_for=["C 端犹豫", "感性决策"],
    ),
    "好奇+稀缺": Combo(
        name="好奇+稀缺",
        stage="钩子",
        desires=["greed", "envy"],
        logic="激发好奇（悬念），配合稀缺（限时限量）",
        weapons=["悬念", "制造稀缺感", "播种怀疑"],
        fallback="互惠+懒惰",
        suitable_for=["好奇", "怕风险"],
    ),
    "互惠+懒惰": Combo(
        name="互惠+懒惰",
        stage="钩子",
        desires=["sloth", "greed"],
        logic="先给甜头（互惠），再降低门槛（懒惰）",
        weapons=["给予价值", "制造亏欠感", "直接指令"],
        fallback="贪婪+恐惧",
        suitable_for=["懒惰", "低门槛"],
    ),
    # ===== B2B 专属钩子（理性客户适用） =====
    "权威+案例": Combo(
        name="权威+案例",
        stage="钩子",
        desires=["fear", "pride"],
        logic="用权威背书建立信任，用同行案例消除顾虑（适合 B2B 理性决策者）",
        weapons=["引用权威", "给予价值", "设定框架"],
        fallback="好奇+价值",
        suitable_for=["B2B 理性客户", "CTO", "采购主管", "怕担责"],
    ),
    "好奇+价值": Combo(
        name="好奇+价值",
        stage="钩子",
        desires=["greed", "sloth"],
        logic="用行业洞察激发好奇，用实际价值吸引注意（不催促、不施压）",
        weapons=["好奇", "给予价值", "聚焦式问题"],
        fallback="权威+案例",
        suitable_for=["B2B 理性客户", "价值差异化", "ROI 关注"],
    ),
}

# ===== 放大组合 =====

AMPLIFY_COMBOS: dict[str, Combo] = {
    "傲慢+嫉妒": Combo(
        name="傲慢+嫉妒",
        stage="放大",
        desires=["pride", "envy"],
        logic="满足傲慢（身份认同），激发嫉妒（对标比较）",
        weapons=["赋予身份", "稀缺性赞美", "制造共同敌人"],
        fallback="色欲+暴食",
        suitable_for=["傲慢", "攀比"],
    ),
    "色欲+暴食": Combo(
        name="色欲+暴食",
        stage="放大",
        desires=["lust", "gluttony"],
        logic="感官体验（色欲），丰富满足（暴食）",
        weapons=["描绘共同未来", "给予价值", "赞美"],
        fallback="权威+从众",
        suitable_for=["感官", "体验"],
    ),
    "权威+从众": Combo(
        name="权威+从众",
        stage="放大",
        desires=["fear", "envy"],
        logic="权威背书（信任），从众效应（跟风）",
        weapons=["引用权威", "设定框架", "稀缺性赞美"],
        fallback="傲慢+嫉妒",
        suitable_for=["信任", "跟风"],
    ),
}

# ===== 降门槛组合 =====

LOWER_COMBOS: dict[str, Combo] = {
    "懒惰+互惠": Combo(
        name="懒惰+互惠",
        stage="降门槛",
        desires=["sloth", "greed"],
        logic="极度简化步骤（懒惰），先给好处（互惠）",
        weapons=["直接指令", "给予价值", "选择权引导"],
        fallback="懒惰+损失规避",
        suitable_for=["懒惰", "复杂"],
    ),
    "懒惰+损失规避": Combo(
        name="懒惰+损失规避",
        stage="降门槛",
        desires=["sloth", "fear"],
        logic="简化步骤（懒惰），强调不做的损失（恐惧）",
        weapons=["直接指令", "威胁", "制造紧迫感"],
        fallback="懒惰+互惠",
        suitable_for=["拖延", "犹豫"],
    ),
}

# ===== 升维组合 =====

UPGRADE_COMBOS: dict[str, Combo] = {
    "愿景+尊严": Combo(
        name="愿景+尊严",
        stage="升维",
        desires=["greed", "pride"],
        logic="描绘愿景（贪婪），赋予尊严（傲慢）",
        weapons=["描绘共同未来", "赋予身份", "授权"],
        fallback="大爱+宁静",
        suitable_for=["Mode C", "长期"],
    ),
    "大爱+宁静": Combo(
        name="大爱+宁静",
        stage="升维",
        desires=["pride", "greed"],
        logic="大爱价值（意义），宁静长期（信任）",
        weapons=["分享", "描绘共同未来", "信任"],
        fallback="愿景+尊严",
        suitable_for=["Mode C", "信任"],
    ),
    "卓越+革命": Combo(
        name="卓越+革命",
        stage="升维",
        desires=["wrath", "pride"],
        logic="追求极致标准（卓越），挑战现有规则（革命），共同定义未来",
        weapons=["引用权威", "描绘共同未来", "赋予身份", "设定框架"],
        fallback="愿景+尊严",
        suitable_for=["Mode C", "创新", "引领"],
    ),
}

# ===== 防御组合 =====

DEFENSE_COMBOS: dict[str, Combo] = {
    "沉默+示弱": Combo(
        name="沉默+示弱",
        stage="防御",
        desires=["fear"],
        logic="沉默施压，示弱降防",
        weapons=["沉默", "示弱", "道歉"],
        fallback="转移话题+原则",
        suitable_for=["高情绪", "攻击"],
    ),
    "转移话题+原则": Combo(
        name="转移话题+原则",
        stage="防御",
        desires=["fear", "pride"],
        logic="转移注意力，搬出原则设立边界",
        weapons=["转移话题", "原则", "设定框架"],
        fallback="沉默+示弱",
        suitable_for=["僵持", "施压"],
    ),
    "反问+贴标签": Combo(
        name="反问+贴标签",
        stage="防御",
        desires=["wrath"],
        logic="反问打破剧本，贴标签定义行为",
        weapons=["反问", "贴标签", "警告"],
        fallback="沉默+示弱",
        suitable_for=["PUA", "贬低"],
    ),
    "纠正+设界": Combo(
        name="纠正+设界",
        stage="防御",
        desires=["wrath", "pride"],
        logic="用反问和原则建立边界，打破攻击节奏，同时提供确定性",
        weapons=["反问", "原则", "战略性无能", "赋予身份"],
        fallback="沉默+示弱",
        suitable_for=["愤怒", "急躁", "攻击", "贬低"],
    ),
    "激活恐惧+满足傲慢": Combo(
        name="激活恐惧+满足傲慢",
        stage="防御",
        desires=["pride"],
        logic="用风险警示激活隐藏恐惧，同时用稀缺性赞美和赋予身份满足傲慢",
        weapons=["反问", "稀缺性赞美", "赋予身份", "设定框架"],
        fallback="沉默+示弱",
        suitable_for=["傲慢", "看不上", "不感兴趣"],
    ),
}

# ===== 注意力管理组合 =====

ATTENTION_COMBOS: dict[str, Combo] = {
    "聚焦+保护": Combo(
        name="聚焦+保护",
        stage="注意力",
        desires=["sloth", "fear"],
        logic="关闭干扰（聚焦），保护注意力（保护）",
        weapons=["设定框架", "直接指令", "选择权引导"],
        fallback="沉默+示弱",
        suitable_for=["注意力涣散", "信息过载"],
    ),
    "引导+同频": Combo(
        name="引导+同频",
        stage="注意力",
        desires=["greed", "envy"],
        logic="引导注意力焦点（引导），与用户同频（同频）",
        weapons=["好奇心激发", "镜像模仿", "悬念"],
        fallback="聚焦+保护",
        suitable_for=["走神", "兴趣丧失"],
    ),
}

# ===== 销售场景专用组合 =====

SALES_COMBOS: dict[str, Combo] = {
    "共情+正常化": Combo(
        name="共情+正常化",
        stage="钩子",
        desires=["fear", "sloth"],
        logic="先共情对方的挫折感，再正常化这种感受（'94%的人都会经历'），降低心理防御",
        weapons=["共情", "正常化", "赋予身份"],
        fallback="互惠+懒惰",
        suitable_for=["拒绝敏感", "新手焦虑", "挫败"],
    ),
    "提供确定性+案例证明": Combo(
        name="提供确定性+案例证明",
        stage="降门槛",
        desires=["fear", "greed"],
        logic="用具体案例证明可行性（消除恐惧），用确定性承诺推动决策",
        weapons=["引用权威", "给予价值", "设定框架"],
        fallback="懒惰+互惠",
        suitable_for=["怕出错", "维持现状", "犹豫不决"],
    ),
    "价值锚定+社交证明": Combo(
        name="价值锚定+社交证明",
        stage="放大",
        desires=["greed", "envy"],
        logic="锚定核心价值（你能得到什么），用社交证明增强信任（别人也在用）",
        weapons=["给予价值", "设定框架", "稀缺性赞美"],
        fallback="好奇+稀缺",
        suitable_for=["确认价值", "比价", "信任建立"],
    ),
}

# ===== 情感场景专属组合 =====

EMOTION_COMBOS: dict[str, Combo] = {
    "探索+倾听": Combo(
        name="探索+倾听",
        stage="钩子",
        desires=["fear", "sloth"],
        logic="先探索用户真实需求（不是表面诉求），用深度倾听建立安全感（ESC 模型 Exploration 阶段）",
        weapons=["共情", "倾听", "好奇", "正常化"],
        fallback="共情+正常化",
        suitable_for=["感受验证", "未满足需求识别", "愧疚转责任"],
    ),
    "洞察+重评": Combo(
        name="洞察+重评",
        stage="放大",
        desires=["fear", "pride"],
        logic="引导用户看到情绪背后的认知扭曲，用多维度视角重新解读事件（ESC 模型 Insight 阶段）",
        weapons=["好奇", "设定框架", "赋予身份", "正常化"],
        fallback="探索+倾听",
        suitable_for=["认知重评引导", "愧疚转责任", "未满足需求识别"],
    ),
    "行动+引导": Combo(
        name="行动+引导",
        stage="降门槛",
        desires=["sloth", "greed"],
        logic="提供具体、可执行的小步骤（54321 放松法、呼吸练习、NVC 模板），降低行动门槛（ESC 模型 Action 阶段）",
        weapons=["直接指令", "给予价值", "选择权引导", "设定框架"],
        fallback="互惠+懒惰",
        suitable_for=["生理自愈引导", "修复尝试指导", "边界表达辅助", "认知资源调度"],
    ),
    "安全+降级": Combo(
        name="安全+降级",
        stage="防御",
        desires=["fear"],
        logic="识别安全红线（C-SSRS 标准），强制暂停对话，推送专业救助资源，绝不尝试自行处理危机",
        weapons=["沉默", "共情", "设定框架", "转移话题"],
        fallback="共情+正常化",
        suitable_for=["安全红线筛查", "冲突降级", "生理自愈引导"],
    ),
    "边界+原则": Combo(
        name="边界+原则",
        stage="防御",
        desires=["pride", "wrath"],
        logic="帮助用户清晰表达个人边界，同时拦截线上去抑制行为（攻击性、虚假亲密），引导回归理性",
        weapons=["原则", "设定框架", "反问", "纠正"],
        fallback="沉默+示弱",
        suitable_for=["边界表达辅助", "去抑制行为审计", "信任修复协议"],
    ),
    "修复+连接": Combo(
        name="修复+连接",
        stage="降门槛",
        desires=["fear", "greed"],
        logic="引导用户发起微小修复尝试（道歉、幽默、肢体语言建议），重建关系连接（Gottman 修复尝试理论）",
        weapons=["共情", "正常化", "给予价值", "选择权引导"],
        fallback="互惠+懒惰",
        suitable_for=["修复尝试指导", "信任修复协议", "感受验证"],
    ),
}

# ===== 全部组合 =====

ALL_COMBOS: dict[str, Combo] = {
    **HOOK_COMBOS,
    **AMPLIFY_COMBOS,
    **LOWER_COMBOS,
    **UPGRADE_COMBOS,
    **DEFENSE_COMBOS,
    **ATTENTION_COMBOS,
    **SALES_COMBOS,
    **EMOTION_COMBOS,
}


def select_combo(user: UserState, mode: str, stage: str = "") -> StrategyPlan:
    """
    根据用户状态选择策略组合

    Args:
        user: 用户状态
        mode: 当前模式（A/B/C）
        stage: 当前阶段（钩子/放大/降门槛/升维/防御）

    Returns:
        StrategyPlan: 策略方案
    """
    # 获取主导欲望
    dominant, weight = user.desires.get_dominant()

    # 确定阶段
    if not stage:
        stage = _determine_stage(user, mode)

    # 获取该阶段的组合
    stage_combos = {
        "钩子": HOOK_COMBOS,
        "放大": AMPLIFY_COMBOS,
        "降门槛": LOWER_COMBOS,
        "升维": UPGRADE_COMBOS,
        "防御": DEFENSE_COMBOS,
        "注意力": ATTENTION_COMBOS,
    }.get(stage, HOOK_COMBOS)

    # 选择最匹配的组合
    best_combo = _find_best_combo(user, dominant, stage_combos)

    return StrategyPlan(
        mode=mode,
        combo_name=best_combo.name,
        stage=best_combo.stage,
        description=best_combo.logic,
        fallback=best_combo.fallback,
    )


def _determine_stage(user: UserState, mode: str) -> str:
    """
    确定当前阶段（基于文档规格）

    维度：
    1. 情绪强度 > 0.7 → 防御
    2. 双核对抗 → 防御
    3. 阻力类型 → 恐惧→钩子，懒惰→降门槛，傲慢→放大/升维
    4. Mode A 正向（稳定、保护）→ 钩子
    5. Mode B 反向（激进、推动）→ 放大
    6. Mode C → 升维
    """
    # 1. 高情绪 → 防御
    if user.emotion.intensity > 0.7:
        return "防御"

    # 2. 注意力被劫持 → 注意力管理
    from schemas.enums import AttentionHijacker
    if user.attention.focus < 0.3 and user.attention.hijacked_by != AttentionHijacker.NONE:
        return "注意力"

    # 3. 双核对抗 → 防御
    from schemas.enums import DualCoreState
    if user.dual_core.state == DualCoreState.CONFLICT:
        return "防御"

    # 3. 阻力类型决定阶段
    from schemas.enums import ResistanceType
    if user.resistance.type and user.resistance.type != ResistanceType.NONE:
        res_val = user.resistance.type.value if hasattr(user.resistance.type, 'value') else str(user.resistance.type)
        if res_val in ("恐惧", "fear"):
            return "钩子"  # 用钩子消除恐惧
        elif res_val in ("懒惰", "sloth"):
            return "降门槛"  # 用降门槛消除懒惰
        elif res_val in ("傲慢", "pride"):
            if mode == "C":
                return "升维"
            return "放大"  # 用放大满足傲慢

    # 4-5. Mode 区分（正反向）
    if mode == "A":
        return "钩子"  # Mode A 正向：用钩子建立基础（稳定、保护）
    elif mode == "B":
        return "放大"  # Mode B 反向：用放大激发欲望（激进、推动）
    elif mode == "C":
        return "升维"

    return "钩子"


def _find_best_combo(user: UserState, dominant: str, combos: dict[str, Combo]) -> Combo:
    """
    找到最匹配的组合（多维度评分）

    评分维度（基于 07-优先级规则模块）：
    1. 主导欲望匹配 (+3)
    2. 次要欲望匹配 (each > 0.3: +1)
    3. 懒惰考量 - 懒惰"永远要考虑"，若组合包含懒惰且用户懒惰>0.3，额外+2
    4. 情绪强度 - 高情绪(>0.7)偏好防御型组合 (+2)
    5. 多欲望同时高验证 - 组合中所有欲望都 > 0.3 才算完整匹配 (+1)
    """
    scores: list[tuple[str, int]] = []

    for name, combo in combos.items():
        score = 0

        # 1. 主导欲望匹配
        if dominant in combo.desires:
            score += 3

        # 2. 次要欲望匹配
        for desire in combo.desires:
            val = getattr(user.desires, desire, 0)
            if val > 0.5:
                score += 2  # 强匹配
            elif val > 0.3:
                score += 1  # 弱匹配

        # 3. 懒惰考量（永远要考虑，07-优先级规则）
        if "sloth" in combo.desires and user.desires.sloth > 0.3:
            score += 2

        # 4. 情绪强度权重（高情绪偏好防御型组合）
        if user.emotion.intensity > 0.7 and combo.stage == "防御":
            score += 2

        # 5. 多欲望同时高验证
        all_desires_high = all(
            getattr(user.desires, d, 0) > 0.3 for d in combo.desires
        )
        if all_desires_high and len(combo.desires) >= 2:
            score += 1

        scores.append((name, score))

    # 取最高分，平分时选第一个（按文档：若权重相近，选最先出现的）
    if scores:
        scores.sort(key=lambda x: x[1], reverse=True)
        return combos[scores[0][0]]

    # 默认返回第一个
    return list(combos.values())[0]


def get_combo(combo_name: str) -> Combo | None:
    """获取组合对象"""
    return ALL_COMBOS.get(combo_name)


def get_combo_weapons(combo_name: str) -> list[str]:
    """获取组合的推荐武器"""
    combo = ALL_COMBOS.get(combo_name)
    return combo.weapons if combo else []


# ===== 测试入口 =====

if __name__ == "__main__":
    from schemas.user_state import Emotion, Desires, DualCore

    test_cases = [
        {
            "name": "恐惧主导",
            "user": UserState(
                emotion=Emotion(type=EmotionType.FRUSTRATED, intensity=0.6),
                desires=Desires(fear=0.8, greed=0.3),
            ),
            "mode": "A",
        },
        {
            "name": "贪婪主导",
            "user": UserState(
                emotion=Emotion(type="平静", intensity=0.3),
                desires=Desires(greed=0.8, sloth=0.3),
            ),
            "mode": "B",
        },
        {
            "name": "傲慢主导",
            "user": UserState(
                emotion=Emotion(type=EmotionType.CALM, intensity=0.4),
                desires=Desires(pride=0.8),
            ),
        },
        {
            "name": "急躁",
            "user": UserState(
                emotion=Emotion(type=EmotionType.IMPATIENT, intensity=0.7),
            ),
        },
        {
            "name": "急躁",
            "user": UserState(
                emotion=Emotion(type=EmotionType.IMPATIENT, intensity=0.7),
            ),
            "mode": "A",
        },
    ]

    for case in test_cases:
        plan = select_combo(case["user"], case["mode"])
        print(f"\n{case['name']}:")
        print(f"  组合: {plan.combo_name}")
        print(f"  阶段: {plan.stage}")
        print(f"  逻辑: {plan.description}")
        print(f"  备选: {plan.fallback}")
