"""
Human-OS Engine - L3 策略工具层：情绪武器库

基于 14-人性工程师模块-武器库.md 的内容。
包含攻击型、防御型、温和型三类武器。

武器库是策略执行的"肌肉"，为五层结构提供具体内容。
"""

from dataclasses import dataclass
from schemas.enums import WeaponType


@dataclass
class Weapon:
    """武器定义"""
    name: str
    type: WeaponType
    description: str
    example: str  # 示例话术
    suitable_for: list[str]  # 适用场景（如 "高情绪", "傲慢", "恐惧"）


# ===== 攻击型武器（26项）=====

ATTACK_WEAPONS: dict[str, Weapon] = {
    "指责": Weapon("指责", WeaponType.ATTACK, "直接指出问题", "你这个做法有问题", ["愤怒", "傲慢"]),
    "批评": Weapon("批评", WeaponType.ATTACK, "建设性批评", "这个方案需要改进", ["傲慢"]),
    "质问": Weapon("质问", WeaponType.ATTACK, "深度提问", "你这个结论基于什么？", ["傲慢", "防御"]),
    "嘲讽": Weapon("嘲讽", WeaponType.ATTACK, "讽刺挖苦", "呵，你可真行", ["愤怒"]),
    "蔑视": Weapon("蔑视", WeaponType.ATTACK, "表达轻视", "这也叫方案？", ["傲慢"]),
    "讽刺": Weapon("讽刺", WeaponType.ATTACK, "用反话表达不满", "你可真是个大聪明", ["愤怒", "傲慢"]),
    "打断": Weapon("打断", WeaponType.ATTACK, "打断对方", "等一下，你说的不对", ["愤怒"]),
    "催促": Weapon("催促", WeaponType.ATTACK, "制造紧迫感", "时间不多了，赶紧决定", ["犹豫"]),
    "命令": Weapon("命令", WeaponType.ATTACK, "直接下达指令", "你现在就去做", ["权威", "急躁"]),
    "威胁": Weapon("威胁", WeaponType.ATTACK, "风险提示", "如果不做，后果自负", ["犹豫", "傲慢"]),
    "愤怒": Weapon("愤怒", WeaponType.ATTACK, "表达愤怒", "我很失望", ["攻击"]),
    "冷漠": Weapon("冷漠", WeaponType.ATTACK, "冷淡回应", "随便你", ["攻击"]),
    "失望": Weapon("失望", WeaponType.ATTACK, "表达失望", "我对你的回复有点失望", ["推卸"]),
    "质疑": Weapon("质疑", WeaponType.ATTACK, "质疑对方", "你确定吗？", ["傲慢"]),
    "挑衅": Weapon("挑衅", WeaponType.ATTACK, "激将法", "你敢不敢试试？", ["犹豫"]),
    "警告": Weapon("警告", WeaponType.ATTACK, "明确警告", "我建议你三思", ["傲慢"]),
    "羞辱": Weapon("羞辱", WeaponType.ATTACK, "贬低对方", "就这？", ["愤怒"]),
    "嫌弃": Weapon("嫌弃", WeaponType.ATTACK, "表达厌恶", "这味道真难闻", ["愤怒"]),
    "贴标签": Weapon("贴标签", WeaponType.ATTACK, "定义行为", "我发现你很喜欢用开玩笑的方式指出问题", ["PUA"]),
    "制造紧迫感": Weapon("制造紧迫感", WeaponType.ATTACK, "时间压力", "机会只有一次", ["犹豫", "贪婪"]),
    "制造稀缺感": Weapon("制造稀缺感", WeaponType.ATTACK, "稀缺性", "这个名额只剩最后两个了", ["犹豫", "贪婪"]),
    "优越感": Weapon("优越感", WeaponType.ATTACK, "展示优势", "这方面我比你懂", ["傲慢"]),
    "排斥": Weapon("排斥", WeaponType.ATTACK, "排除在外", "这不是你该管的", ["越界"]),
    "侵入空间": Weapon("侵入空间", WeaponType.ATTACK, "缩短物理距离施压", "走近对方，直视眼睛", ["权威"]),
    "死亡凝视": Weapon("死亡凝视", WeaponType.ATTACK, "沉默注视", "（沉默3秒看着对方）", ["攻击"]),
    "播种怀疑": Weapon("播种怀疑", WeaponType.ATTACK, "植入疑虑", "你有没有想过另一种可能？", ["傲慢", "犹豫"]),
    "设立稻草人": Weapon("设立稻草人", WeaponType.ATTACK, "先夸张后否定", "如果全面铺开...不，这太极端了", ["保守"]),
}

# ===== 防御型武器（23项）=====

DEFENSE_WEAPONS: dict[str, Weapon] = {
    "沉默": Weapon("沉默", WeaponType.DEFENSE, "不说话", "（沉默）", ["高情绪", "攻击"]),
    "示弱": Weapon("示弱", WeaponType.DEFENSE, "承认不足", "我确实不成熟，需要您指导", ["防御"]),
    "装傻": Weapon("装傻", WeaponType.DEFENSE, "假装不懂", "我不太明白您的意思", ["攻击"]),
    "附和": Weapon("附和", WeaponType.DEFENSE, "部分同意", "你说的有道理", ["攻击"]),
    "妥协": Weapon("妥协", WeaponType.DEFENSE, "让步", "好吧，我再想想", ["僵持"]),
    "道歉": Weapon("道歉", WeaponType.DEFENSE, "对情绪道歉", "对不起，我刚才太激动了", ["情绪"]),
    "回避": Weapon("回避", WeaponType.DEFENSE, "转移话题", "这个我们先放一放", ["敏感"]),
    "转移话题": Weapon("转移话题", WeaponType.DEFENSE, "换话题", "对了，我想起另一件事", ["僵持"]),
    "拖延": Weapon("拖延", WeaponType.DEFENSE, "争取时间", "我需要时间考虑", ["压力"]),
    "诉苦": Weapon("诉苦", WeaponType.DEFENSE, "表达困难", "我这边也很紧张", ["施压"]),
    "自责": Weapon("自责", WeaponType.DEFENSE, "自我批评降低对方攻击欲", "确实是我的问题", ["攻击", "施压"]),
    "困惑": Weapon("困惑", WeaponType.DEFENSE, "表达不理解", "我不太明白您的意思", ["攻击"]),
    "谦虚": Weapon("谦虚", WeaponType.DEFENSE, "降低姿态", "我还有很多要学的", ["傲慢"]),
    "最小化": Weapon("最小化", WeaponType.DEFENSE, "淡化重要性", "这只是其中一方面", ["攻击"]),
    "原则": Weapon("原则", WeaponType.DEFENSE, "搬出原则", "这是我们公司的规定", ["施压"]),
    "过载": Weapon("过载", WeaponType.DEFENSE, "用大量信息淹没对方", "让我给你详细解释一下（长篇大论）", ["施压", "攻击"]),
    "受害者姿态": Weapon("受害者姿态", WeaponType.DEFENSE, "示弱博同情", "我也是被逼的", ["施压"]),
    "反问": Weapon("反问", WeaponType.DEFENSE, "反问对方", "你是想测试我还是真有需求？", ["攻击", "傲慢"]),
    "物理隔离": Weapon("物理隔离", WeaponType.DEFENSE, "离开现场", "我们都冷静一下", ["高情绪"]),
    "引用权威": Weapon("引用权威", WeaponType.DEFENSE, "借助权威", "专家是这么说的", ["质疑"]),
    "战略性无能": Weapon("战略性无能", WeaponType.DEFENSE, "承认能力边界", "这个我真的做不了", ["施压"]),
    "断开连接": Weapon("断开连接", WeaponType.DEFENSE, "暂时退出", "我先去喝口水", ["高情绪"]),
    "保持距离": Weapon("保持距离", WeaponType.DEFENSE, "维持边界", "我们先保持专业关系", ["越界"]),
}

# ===== 温和型武器（26项）=====

MILD_WEAPONS: dict[str, Weapon] = {
    "赞美": Weapon("赞美", WeaponType.MILD, "肯定对方", "你做得很好", ["建立信任"]),
    "倾听": Weapon("倾听", WeaponType.MILD, "认真听", "嗯，我听着", ["倾诉"]),
    "幽默": Weapon("幽默", WeaponType.MILD, "轻松化解", "哈哈，确实有意思", ["紧张"]),
    "自嘲": Weapon("自嘲", WeaponType.MILD, "自我调侃", "看来是我的面子还不够大", ["拒绝"]),
    "共情": Weapon("共情", WeaponType.MILD, "理解感受", "这压力确实大", ["高情绪"]),
    "好奇": Weapon("好奇", WeaponType.MILD, "表达兴趣", "能具体说说吗？", ["模糊"]),
    "鼓励": Weapon("鼓励", WeaponType.MILD, "给予信心", "你可以的", ["挫败"]),
    "肯定": Weapon("肯定", WeaponType.MILD, "认可价值", "你的想法很有道理", ["迷茫"]),
    "耐心": Weapon("耐心", WeaponType.MILD, "不催促", "不急，慢慢说", ["急躁"]),
    "热情": Weapon("热情", WeaponType.MILD, "积极回应", "太好了！", ["期待"]),
    "分享": Weapon("分享", WeaponType.MILD, "提供信息", "我之前也遇到过类似情况", ["建立信任"]),
    "求助": Weapon("求助", WeaponType.MILD, "请求帮助", "能帮我看一下吗？", ["建立关系"]),
    "信任": Weapon("信任", WeaponType.MILD, "表达信任", "我相信你的判断", ["建立信任"]),
    "期待": Weapon("期待", WeaponType.MILD, "表达期待", "我很期待你的成果", ["激励"]),
    "安慰": Weapon("安慰", WeaponType.MILD, "安抚情绪", "没事的，都会过去的", ["高情绪"]),
    "设定框架": Weapon("设定框架", WeaponType.MILD, "重新定义", "我们先聚焦一个问题", ["混乱"]),
    "给予价值": Weapon("给予价值", WeaponType.MILD, "提供帮助", "我帮你看看", ["建立关系"]),
    "制造亏欠感": Weapon("制造亏欠感", WeaponType.MILD, "先付出", "正好买了咖啡，给你也带了一杯", ["建立关系"]),
    "描绘共同未来": Weapon("描绘共同未来", WeaponType.MILD, "愿景引导", "搞定了这个，后面就顺了", ["犹豫"]),
    "悬念": Weapon("悬念", WeaponType.MILD, "留下悬念", "下次再跟你说个更有意思的", ["结束对话"]),
    "授权": Weapon("授权", WeaponType.MILD, "给选择权", "你觉得哪个更适合你？", ["决策"]),
    "镜像模仿": Weapon("镜像模仿", WeaponType.MILD, "重复关键词", "所以你是说...", ["理解"]),
    "点头认同": Weapon("点头认同", WeaponType.MILD, "肢体认同", "（点头）嗯", ["倾听"]),
    "制造共同敌人": Weapon("制造共同敌人", WeaponType.MILD, "外部压力", "我们的对手是...", ["建立联盟"]),
    "赋予身份": Weapon("赋予身份", WeaponType.MILD, "角色定位", "你比大多数人看得早", ["挫败", "傲慢"]),
    "稀缺性赞美": Weapon("稀缺性赞美", WeaponType.MILD, "独特认可", "这个问题只有你能解决", ["傲慢"]),
    "正常化": Weapon("正常化", WeaponType.MILD, "去特殊化", "换谁都会这样", ["高情绪"]),
    "去责备化": Weapon("去责备化", WeaponType.MILD, "消除自责", "这不是你的错", ["恐惧", "挫败"]),
    "选择权引导": Weapon("选择权引导", WeaponType.MILD, "给选项", "你是想A还是B？", ["决策"]),
    "直接指令": Weapon("直接指令", WeaponType.MILD, "直接给方案", "没问题，直接给您方案", ["急躁"]),
    "第一人称反应": Weapon("第一人称反应", WeaponType.MILD, "真实反应", "这确实...", ["所有"]),
}


# ===== 武器库统一接口 =====

ALL_WEAPONS: dict[str, Weapon] = {
    **ATTACK_WEAPONS,
    **DEFENSE_WEAPONS,
    **MILD_WEAPONS,
}


def get_weapon(name: str) -> Weapon | None:
    """获取武器"""
    return ALL_WEAPONS.get(name)


def get_weapons_by_type(weapon_type: WeaponType) -> list[Weapon]:
    """按类型获取武器列表"""
    return [w for w in ALL_WEAPONS.values() if w.type == weapon_type]


def get_weapons_by_scene(scene: str) -> list[Weapon]:
    """按场景获取适用武器"""
    return [w for w in ALL_WEAPONS.values() if scene in w.suitable_for]


def select_weapon_for_layer(
    layer: int,
    user_state: dict,
    weapon_usage: dict[str, int],
    max_usage: int = 2,
) -> Weapon | None:
    """
    为指定层级选择武器（基于 Step 8 道次2 武器选择参考表）

    Args:
        layer: 层级（1-5）
        user_state: 用户状态摘要
        weapon_usage: 武器使用计数
        max_usage: 同一武器最大使用次数

    Returns:
        Weapon: 选中的武器
    """
    emotion = user_state.get("emotion_type", "平静")
    intensity = user_state.get("emotion_intensity", 0.5)
    is_high_emotion = intensity > 0.7
    resistance = user_state.get("resistance_type")

    # ===== 按层级×用户状态动态选择候选武器 =====

    candidates = _get_candidates_for_layer(layer, emotion, intensity, resistance)

    # 过滤已达到使用上限的武器
    available = [name for name in candidates if weapon_usage.get(name, 0) < max_usage]
    if not available:
        available = candidates

    # ===== 按用户状态调整优先级 =====

    # 第1层：情绪类型决定武器选择
    if layer == 1:
        if emotion == "愤怒":
            # 愤怒 → 沉默或反问（反制施压），不共情
            for w in ["沉默", "反问", "第一人称反应"]:
                if w in available:
                    return get_weapon(w)
        elif emotion == "挫败":
            # 挫败 → 真实共情
            for w in ["真实共情", "第一人称反应", "共情"]:
                if w in available:
                    return get_weapon(w)
        elif emotion == "急躁":
            # 急躁 → 直接指令或沉默
            for w in ["直接指令", "沉默"]:
                if w in available:
                    return get_weapon(w)
        elif is_high_emotion:
            # 其他高情绪 → 共情或第一人称反应
            for w in ["真实共情", "第一人称反应"]:
                if w in available:
                    return get_weapon(w)

    # 第4层：傲慢/防御 → 反问
    if layer == 4 and resistance in ("傲慢", "防御"):
        if "反问" in available:
            return get_weapon("反问")

    # 默认：随机选一个可用武器（保证多样性）
    import random
    return get_weapon(random.choice(available)) if available else None


def _get_candidates_for_layer(
    layer: int,
    emotion: str,
    intensity: float,
    resistance: str | None,
) -> list[str]:
    """
    根据层级和用户状态生成候选武器列表
    基于 Step 8 道次2 武器选择参考表
    """
    is_high = intensity > 0.7

    if layer == 1:
        # 第1层 即时反应
        if emotion == "愤怒":
            return ["沉默", "反问", "第一人称反应", "直接指令"]
        elif emotion == "挫败":
            return ["真实共情", "第一人称反应", "共情", "幽默"]
        elif emotion == "急躁":
            return ["直接指令", "沉默", "明白", "第一人称反应"]
        elif emotion == "平静":
            return ["第一人称反应", "幽默", "真实共情", "直接指令"]
        elif is_high:
            return ["真实共情", "第一人称反应", "沉默", "共情"]
        else:
            return ["第一人称反应", "真实共情", "幽默", "直接指令"]

    elif layer == 2:
        # 第2层 理解确认
        if resistance in ("傲慢", "防御"):
            return ["镜像模仿", "复述", "好奇"]
        else:
            return ["镜像模仿", "复述", "好奇", "反问"]

    elif layer == 3:
        # 第3层 共情支持
        if emotion == "挫败":
            return ["正常化", "去责备化", "赋予身份", "安慰"]
        elif emotion in ("愤怒", "急躁"):
            return ["赋予身份", "设定框架", "去责备化"]
        elif emotion == "平静":
            return ["鼓励", "赋予身份", "正常化", "安慰"]
        elif is_high:
            return ["正常化", "去责备化", "安慰", "赋予身份"]
        else:
            return ["正常化", "赋予身份", "鼓励", "安慰"]

    elif layer == 4:
        # 第4层 具体追问
        if resistance in ("傲慢", "防御"):
            return ["反问", "设定框架", "聚焦式问题"]
        elif emotion in ("愤怒", "急躁"):
            return ["反问", "设定框架"]
        else:
            return ["好奇", "聚焦式问题", "反问", "设定框架"]

    elif layer == 5:
        # 第5层 方向引导
        if emotion in ("愤怒", "急躁"):
            return ["选择权引导", "给予价值", "授权"]
        elif intensity < 0.4:
            return ["给予价值", "选择权引导", "描绘共同未来", "授权"]
        else:
            return ["给予价值", "选择权引导", "描绘共同未来"]

    return ["共情"]


# ===== 测试入口 =====

if __name__ == "__main__":
    print(f"武器总数: {len(ALL_WEAPONS)}")
    print(f"攻击型: {len(ATTACK_WEAPONS)}")
    print(f"防御型: {len(DEFENSE_WEAPONS)}")
    print(f"温和型: {len(MILD_WEAPONS)}")

    # 测试武器选择
    print("\n--- 测试武器选择 ---")
    user_state = {"emotion_type": "挫败", "emotion_intensity": 0.8}
    usage = {}

    for layer in range(1, 6):
        weapon = select_weapon_for_layer(layer, user_state, usage)
        print(f"第{layer}层: {weapon.name if weapon else 'None'}")
