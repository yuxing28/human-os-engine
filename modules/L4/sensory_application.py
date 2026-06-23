"""
Human-OS Engine - L4 执行工具层：五感施加系统

基于 22-五感施加系统.md 和 眼耳口鼻舌身逻辑.md 的内容。

三个视角：
1. 设计者视角：如何利用别人的五感（场域设计+施加方法）—— 原有功能
2. 自我执行视角：用户进入线下场景时，指导身体怎么做 —— 新增
3. 自我调节视角：用户情绪差需要稳住时，给出五感调节方法 —— 新增

触发条件：
- 设计者视角：有物理空间控制权 + 涉及线下接触 + 有时间和资源
- 自我执行视角：用户表达了进入线下博弈场景的意图
- 自我调节视角：用户情绪差需要自我安抚/稳住
"""

from dataclasses import dataclass, field


@dataclass
class SensoryAction:
    """单个感官动作"""
    sense: str  # visual/auditory/olfactory/gustatory/tactile
    method: str  # 具体方法
    purpose: str  # 目的
    expected_effect: str  # 预期效果


@dataclass
class FieldSetup:
    """场域设计方案"""
    element: str  # 火/水/土/金/木
    visual: str  # 视觉设计
    audio: str  # 听觉设计
    smell: str  # 嗅觉设计
    touch: str  # 触觉设计
    taste: str  # 味觉设计
    actions: list[SensoryAction] = field(default_factory=list)


@dataclass
class ScenarioGuide:
    """线下场景五感执行指导"""
    scenario: str  # 场景名称
    eye: list[str] = field(default_factory=list)    # 眼：视线/目光
    ear: list[str] = field(default_factory=list)    # 耳：听/声音控制
    body: list[str] = field(default_factory=list)   # 身：姿态/动作/位置
    voice: list[str] = field(default_factory=list)  # 口：语速/语调/表达
    breath: list[str] = field(default_factory=list) # 呼吸：节奏/方法
    caution: list[str] = field(default_factory=list) # 注意事项


@dataclass
class SelfRegulationGuide:
    """自我调节五感指导"""
    emotion_state: str  # 情绪状态
    breath: list[str] = field(default_factory=list)  # 呼吸方法
    tactile: list[str] = field(default_factory=list)  # 触觉锚定
    visual: list[str] = field(default_factory=list)   # 视觉转移
    body: list[str] = field(default_factory=list)     # 身体微动作
    voice: list[str] = field(default_factory=list)    # 声音调节


# ===== 五行属性 → 五感映射 =====

FIVE_ELEMENTS_MAP: dict[str, dict[str, str]] = {
    "火": {
        "scenario": "激发行动、制造冲动、促进消费",
        "visual": "暖光、红橙色、动态元素",
        "audio": "快节奏音乐、鼓点",
        "smell": "辛辣/温暖调香氛",
        "touch": "温暖材质（如暖色灯光照射的桌面）",
        "taste": "辛辣/热饮",
    },
    "水": {
        "scenario": "神秘感、深度思考、激发好奇",
        "visual": "暗光、镜面、蓝黑色",
        "audio": "流水声、低频音乐",
        "smell": "水生调香氛（海洋、雨水）",
        "touch": "光滑/凉爽材质（如玻璃、金属）",
        "taste": "清凉饮品",
    },
    "土": {
        "scenario": "建立信任、安全感、长期规划",
        "visual": "木质、棕黄色、对称布局",
        "audio": "轻柔背景音",
        "smell": "木质/泥土香（檀香、雪松）",
        "touch": "厚重/温暖材质（如实木、皮革）",
        "taste": "醇厚食物（如茶、咖啡）",
    },
    "金": {
        "scenario": "谈判、理性决策",
        "visual": "冷光、金属色、锐利线条",
        "audio": "静音或白噪音",
        "smell": "（金无特定气味，保持中性）",
        "touch": "冷硬/金属材质",
        "taste": "（金无特定味觉，保持中性）",
    },
    "木": {
        "scenario": "创意、放松、降低焦虑",
        "visual": "绿色、自然光、植物",
        "audio": "自然环境音（鸟鸣、风声）",
        "smell": "草木/花香（茉莉、薄荷）",
        "touch": "柔软/织物材质（如棉麻）",
        "taste": "清新食物（如水果、绿茶）",
    },
}


# ===== 五感施加方法（设计者视角） =====

VISUAL_METHODS: dict[str, list[SensoryAction]] = {
    "聚焦注意力": [
        SensoryAction("visual", "聚焦灯光照射关键物品", "引导视线", "对方目光被锁定在目标上"),
        SensoryAction("visual", "使用高对比色突出关键信息", "增强视觉冲击", "关键信息被优先注意"),
    ],
    "降低防御": [
        SensoryAction("visual", "使用暖色调（红橙黄）", "营造温暖感", "对方情绪放松"),
        SensoryAction("visual", "柔和灯光，避免直射", "减少压迫感", "对方感觉安全"),
    ],
    "制造冲动": [
        SensoryAction("visual", "动态元素（闪烁、移动）", "吸引注意力", "对方注意力被强制劫持"),
        SensoryAction("visual", "红色/橙色大面积使用", "激发行动欲", "对方产生紧迫感"),
    ],
}

AUDITORY_METHODS: dict[str, list[SensoryAction]] = {
    "放慢节奏": [
        SensoryAction("auditory", "播放慢节奏音乐（60-70 BPM）", "同步对方心跳", "对方放慢脚步，增加浏览时间"),
        SensoryAction("auditory", "降低说话语速", "引导对方节奏", "对方情绪平稳"),
    ],
    "加快节奏": [
        SensoryAction("auditory", "播放快节奏音乐（120+ BPM）", "同步对方心跳", "对方产生紧迫感"),
        SensoryAction("auditory", "提高说话语速和音量", "激发行动欲", "对方加速决策"),
    ],
    "制造神秘": [
        SensoryAction("auditory", "低频音乐或流水声", "激活未知恐惧", "对方产生好奇和探索欲"),
        SensoryAction("auditory", "突然的安静（3-5 秒）", "制造紧张感", "对方注意力高度集中"),
    ],
}

OLFACTORY_METHODS: dict[str, list[SensoryAction]] = {
    "植入尊贵感": [
        SensoryAction("olfactory", "高端酒店大堂香氛（木质调）", "绕过理性直接植入情绪", "对方产生尊贵/放松联想"),
    ],
    "激发食欲": [
        SensoryAction("olfactory", "面包/咖啡香气", "直接攻击奖赏系统", "对方产生购买冲动"),
    ],
    "降低焦虑": [
        SensoryAction("olfactory", "薰衣草/洋甘菊香氛", "激活副交感神经", "对方情绪放松"),
    ],
}

GUSTATORY_METHODS: dict[str, list[SensoryAction]] = {
    "互惠心理": [
        SensoryAction("gustatory", "免费试吃/试饮", "触发互惠原理", "对方降低防御，产生亏欠感"),
    ],
    "奖赏激活": [
        SensoryAction("gustatory", "提供甜食（糖脂混合）", "激活多巴胺奖赏系统", "对方产生愉悦感，降低理性判断"),
    ],
}

TACTILE_METHODS: dict[str, list[SensoryAction]] = {
    "削弱气势": [
        SensoryAction("tactile", "给对方坐软沙发，自己坐硬椅子", "利用身体姿态差异", "对方气势被削弱"),
    ],
    "增强信任": [
        SensoryAction("tactile", "提供温暖饮品（热茶/咖啡）", "触觉温暖传递心理温暖", "对方产生信任感"),
    ],
    "降低戒备": [
        SensoryAction("tactile", "柔软座椅、舒适温度", "激活舒适区沉溺", "对方战斗意志降低"),
    ],
}


# ===== 线下场景五感执行指导（自我执行视角） =====
# 基于 眼耳口鼻舌身逻辑.md 的"输出端"逻辑

SCENARIO_GUIDES: dict[str, ScenarioGuide] = {
    "面试": ScenarioGuide(
        scenario="面试",
        eye=[
            "看对方眉心三角区（两眉之间到鼻梁），既不回避也不直视眼睛，降低压迫感",
            "对方说话时保持目光接触，自己思考时目光可微移到侧上方",
            "不要频繁眨眼或眼神飘忽，会被解读为不自信或说谎",
        ],
        ear=[
            "对方说完后停1秒再回应，不要抢话，显得沉稳",
            "注意听对方语气变化，语速加快=急躁，放慢=在权衡",
        ],
        body=[
            "坐姿前倾约15度，表示专注和兴趣，但不要趴在桌上",
            "双手自然放在桌上或膝上，不要交叉抱胸（防御姿态）",
            "脚平放地面，不要抖腿或频繁换腿",
            "起身时先收腹再站，显得利落",
        ],
        voice=[
            "语速控制在每分钟120-140字，比日常说话慢10%",
            "关键信息（经历/能力）加重语气，辅助信息轻带",
            "句尾降调表示确定，升调表示疑问或不确定",
            "音量让对方刚好听清即可，不要过大显得急切",
        ],
        breath=[
            "进门前做3次4-7-8呼吸（4秒吸-7秒屏-8秒呼），快速降心率",
            "回答难题前先深吸一口气再开口，给自己1.5秒思考时间",
        ],
        caution=[
            "不要碰脸、摸鼻子、揉眼睛——这些是焦虑的微表情",
            "不要频繁看手机或手表——传递不专注信号",
        ],
    ),
    "谈判": ScenarioGuide(
        scenario="谈判",
        eye=[
            "直视对方眼睛，但不是瞪，是稳定的注视",
            "提出关键条件时目光不移，传递坚定",
            "对方犹豫时目光微收，给对方思考空间",
        ],
        ear=[
            "对方沉默时不要急着填补，沉默是施压工具",
            "注意对方语速变化：突然加快=心虚，突然放慢=在编",
        ],
        body=[
            "坐姿端正略后仰，占据空间，传递掌控感",
            "双手放在桌面以上，掌心偶尔朝上（开放姿态）",
            "不要坐软椅——硬椅让你保持警觉，软椅让你放松警惕",
            "站立时双脚与肩同宽，重心居中，不要重心在一只脚上",
        ],
        voice=[
            "语速比对方慢5-10%，掌控节奏",
            "关键数字和条件时放慢+加重，让对方听清且记住",
            "适当停顿2-3秒再回应，不要秒回——秒回=急=弱",
        ],
        breath=[
            "紧张时用腹式呼吸：手放腹部感受起伏，3次即可稳住",
            "对方施压时（最后通牒/威胁），先深呼吸再回应，绝不秒回",
        ],
        caution=[
            "不要先报价——先报价的人往往吃亏",
            "不要在对方说话时摇头或皱眉——微表情会暴露底线",
        ],
    ),
    "演讲": ScenarioGuide(
        scenario="演讲",
        eye=[
            "目光扫射法：把听众分左中右三区，每区停留3-5秒",
            "不要看天花板或PPT——看人，看人的眼睛",
            "讲关键观点时锁定一个人看，讲过渡时扫全场",
        ],
        ear=[
            "注意场下反应：安静=在听，咳嗽/翻手机=走神了该换个节奏",
            "提问环节听问题时身体前倾，传递尊重",
        ],
        body=[
            "站姿：双脚与肩同宽，重心居中，不要来回晃",
            "手势在腰以上肩以下区域活动，不要低于腰（显得没能量）",
            "讲重点时手掌朝下压（确定感），讲故事时手掌朝上（开放感）",
            "不要背对听众——哪怕看PPT也侧身看",
        ],
        voice=[
            "开场前3句话放慢+加重，建立存在感",
            "每讲完一个观点停2秒，让听众消化",
            "故事部分语速加快+音调微升，数据部分放慢+降调",
            "音量比日常说话大20%，但不要喊",
        ],
        breath=[
            "上台前做5次深呼吸，最后一次呼气时开始走上去",
            "紧张到声音发抖时，用腹式呼吸+降低音调，抖感会消失",
        ],
        caution=[
            "不要手插口袋——显得随意不专业",
            "不要频繁说'嗯''那个'——停顿比口头禅好100倍",
        ],
    ),
    "约会": ScenarioGuide(
        scenario="约会",
        eye=[
            "看对方眼睛，但不是盯着——自然地看，偶尔移开再回来",
            "对方说话时目光专注，自己说话时可以偶尔看别处再回来",
            "笑的时候眼睛要跟着动（真笑），不要只有嘴在笑",
        ],
        ear=[
            "认真听，不要急着接话——倾听本身就有吸引力",
            "记住对方提到的细节，后面能引用=你在认真听",
        ],
        body=[
            "身体微微朝向对方，不要侧身或后仰",
            "适当镜像对方动作（对方前倾你也前倾），建立潜意识亲近",
            "不要双臂交叉——这是最明显的防御信号",
        ],
        voice=[
            "语速比日常慢一点，声音低一点——急促+高音=紧张",
            "幽默时语速可以加快，说完后停顿让对方笑",
        ],
        breath=[
            "紧张时不要深呼吸（太明显），用微呼吸：鼻吸口呼，3次",
        ],
        caution=[
            "不要频繁看手机——这是最伤好感的动作",
            "不要过度前倾——太近=压迫，保持一臂距离",
        ],
    ),
    "会议": ScenarioGuide(
        scenario="会议",
        eye=[
            "发言时看决策者（老板/甲方），不是看所有人",
            "别人发言时看对方+偶尔点头，传递尊重",
        ],
        ear=[
            "关键决策点做笔记，哪怕只是关键词——这传递认真",
            "不要在别人说话时和旁边人小声讨论",
        ],
        body=[
            "坐姿端正，手放桌上或拿笔，不要托腮（显得无聊）",
            "发言时身体前倾，不发言时坐直",
        ],
        voice=[
            "发言先说结论再说原因——会议没人想听长推导",
            "语速适中，关键数据重复一遍",
        ],
        breath=[
            "发言前深呼吸一次，不要因为紧张而语速过快",
        ],
        caution=[
            "不要打断别人——等对方说完再接，哪怕你很急",
            "不要在会议中叹气或翻白眼——微表情杀伤力很大",
        ],
    ),
    "汇报": ScenarioGuide(
        scenario="汇报",
        eye=[
            "看决策者的反应：点头=认可，皱眉=有疑虑需要补充解释",
            "讲数据时目光坚定，讲问题时目光诚恳",
        ],
        ear=[
            "被提问时先听完整个问题，不要抢答",
            "注意领导追问的方向——那才是他真正关心的",
        ],
        body=[
            "站姿挺拔，手势配合数据（指屏幕/图表）",
            "不要双手下垂——至少一手拿笔或遥控器，有工具感",
        ],
        voice=[
            "结论先行：'核心结论是X，下面展开'——30秒内让领导知道结果",
            "数据部分放慢，背景部分快带",
        ],
        breath=[
            "汇报前做3次深呼吸，最后一次呼气时开始说话",
        ],
        caution=[
            "不要说'大概''可能'——用具体数字，哪怕是个范围",
            "不要回避坏消息——主动说+带方案，比藏着好10倍",
        ],
    ),
    "冲突": ScenarioGuide(
        scenario="冲突/对峙",
        eye=[
            "看对方眼睛，但不是瞪——是稳定的注视，传递'我不怕但也不想打'",
            "不要看地面或移开目光——会被解读为心虚",
        ],
        ear=[
            "对方情绪激动时不要打断——让他说完，情绪会自然降一点",
            "听内容不听语气——过滤掉攻击性词汇，抓核心诉求",
        ],
        body=[
            "站姿稳，重心居中，不要后退——后退=示弱=对方加码",
            "双手自然垂在身侧或轻握在腹前，不要握拳或叉腰",
            "保持1.5米以上距离——太近=威胁，对方会更激烈",
        ],
        voice=[
            "语速比对方慢，音量比对方低——你急他更急，你稳他跟着稳",
            "用'我理解你的感受'开头，再接'但我们需要解决的是……'",
            "绝对不要提高音量——音量升级=冲突升级",
        ],
        breath=[
            "对方每说一句你深呼吸一次——不是叹气，是给自己降温",
            "感觉要爆发时咬住舌头两侧3秒，痛觉能强制激活理性核",
        ],
        caution=[
            "不要说'你冷静点'——这是最让人不冷静的话",
            "不要翻旧账——只解决眼前这一件事",
        ],
    ),
}

# 场景关键词 → 场景类型映射
SCENARIO_KEYWORDS: dict[str, list[str]] = {
    "面试": ["面试", "面谈", "应聘", "入职面", "复试", "终面", "HR面"],
    "谈判": ["谈判", "谈条件", "谈价格", "砍价", "商务谈", "合同谈", "议价", "报价", "还价"],
    "演讲": ["演讲", "上台", "路演", "分享会", "公开讲", "宣讲", "致辞", "发言", "presentation"],
    "约会": ["约会", "见面", "相亲", "告白", "表白", "约会穿", "约会聊"],
    "会议": ["开会", "会议", "讨论会", "评审会", "周会", "例会", "standup"],
    "汇报": ["汇报", "述职", "报告", "复盘会", "总结会", "review"],
    "冲突": ["冲突", "吵架", "对峙", "争执", "争论", "撕逼", "翻脸", "闹翻"],
}


# ===== 自我调节五感指导（自我调节视角） =====

SELF_REGULATION_GUIDES: dict[str, SelfRegulationGuide] = {
    "紧张": SelfRegulationGuide(
        emotion_state="紧张",
        breath=[
            "4-7-8呼吸法：4秒吸气→7秒屏气→8秒呼气，3轮即可显著降心率",
            "如果4-7-8太难，用箱式呼吸：4秒吸→4秒屏→4秒呼→4秒屏，更简单",
        ],
        tactile=[
            "右手握住椅子扶手或桌沿，用力握3秒再松开——触觉锚定，把注意力拉回身体",
            "脚趾在鞋里抓地——别人看不见，但能激活本体感，稳住身体",
        ],
        visual=[
            "不要看对方的眼睛（太有压迫感），看眉心或额头",
            "找一个固定物体（桌角/花瓶）短暂注视1-2秒，给大脑一个视觉锚点",
        ],
        body=[
            "肩膀向后转一圈再放下——紧张时肩膀会不自觉耸起，这个动作强制松开",
            "微微收腹挺胸——不是挺得夸张，是让脊柱回到中立位",
        ],
        voice=[
            "开口前先咽一下口水+深吸一口气，声音会更稳",
            "第一句话刻意放慢到平时的70%，后面会自然回到正常速度",
        ],
    ),
    "焦虑": SelfRegulationGuide(
        emotion_state="焦虑",
        breath=[
            "延长呼气呼吸：吸气4秒→呼气6秒，呼气比吸气长能激活副交感神经",
            "焦虑时呼吸会变浅变快，先意识到这一点，再刻意放慢",
        ],
        tactile=[
            "双手掌心相对搓热，然后捂在眼睛上10秒——温热感+触觉+闭眼三重放松",
            "摸一下身边有质感的物体（衣服布料/桌面），把注意力从脑中拉回身体",
        ],
        visual=[
            "焦虑时视线会内收（盯着虚空），强制自己看远处一个物体5秒",
            "5-4-3-2-1接地法：看5个东西→听4个声音→摸3个物体→闻2个气味→尝1个味道",
        ],
        body=[
            "做一次肩颈拉伸：头侧向左5秒→右5秒→低头5秒→抬头5秒",
            "站起来走几步——焦虑时身体想动，压抑它反而更焦虑",
        ],
        voice=[],
    ),
    "愤怒": SelfRegulationGuide(
        emotion_state="愤怒",
        breath=[
            "强制深呼吸：鼻吸4秒→口呼8秒，呼气时想象把热气吐出去",
            "愤怒时呼吸会变短促，先意识到'我在短促呼吸'，再拉长",
        ],
        tactile=[
            "双手用力握拳5秒→松开→再握→松开，重复3次——把攻击冲动通过握拳释放",
            "右手用力按住左胸口10秒——触觉+身体觉知，强制把注意力从'对方'拉回'自己'",
        ],
        visual=[
            "不要看对方——愤怒时看对方只会更气，先移开目光3秒",
            "看一个中性物体（墙/天花板/窗外），给理性核3秒启动时间",
        ],
        body=[
            "双手从拳变掌，掌心朝下压桌面——从'攻击姿态'转成'压制姿态'",
            "如果坐着，把脚从交叉/前伸收回到平放——身体从攻击模式回到中立模式",
        ],
        voice=[
            "开口前强制停顿3秒——愤怒时前3秒说的话90%会后悔",
            "如果必须回应，用比平时低半度的音调——降调=降攻击性",
        ],
    ),
    "低落": SelfRegulationGuide(
        emotion_state="低落",
        breath=[
            "完整呼吸：先腹式吸气→再胸式吸气→缓慢呼气，让整个肺部参与",
            "低落时呼吸会变浅，刻意深呼吸能轻微提升血氧和警觉度",
        ],
        tactile=[
            "双手抱住自己（蝴蝶拥抱）：右手拍左肩→左手拍右肩，交替慢拍30秒",
            "喝一杯温水——温热液体从口腔到胃的触觉通路，能轻微激活奖赏系统",
        ],
        visual=[
            "看自然光或窗外——低落时视线会内收下垂，强制看远处+看光能轻微提升情绪",
            "看一个让你有正面联想的物体（照片/植物/书）",
        ],
        body=[
            "不要躺着——低落+躺=更低，坐起来或站起来",
            "做5次开合跳或原地踏步30秒——身体动起来，情绪会跟着动一点",
        ],
        voice=[],
    ),
    "慌乱": SelfRegulationGuide(
        emotion_state="慌乱",
        breath=[
            "箱式呼吸：4秒吸→4秒屏→4秒呼→4秒屏，最简单的节奏呼吸",
            "慌乱=呼吸乱，先花10秒只做呼吸，其他什么都不想",
        ],
        tactile=[
            "双手按住桌面或膝盖，感受手掌的压力——触觉锚定，把注意力从'乱'拉回'此刻'",
            "右手拇指按住食指根部（虎口），用力按10秒——穴位按压，有轻微镇静效果",
        ],
        visual=[
            "找一个固定点盯着看5秒——慌乱时视线乱飘，固定视线=固定注意力",
        ],
        body=[
            "先停下来——慌乱时最差的选择是继续乱动，先站定/坐定3秒",
            "双脚用力踩地3秒——本体感输入，告诉大脑'我在这里，是稳的'",
        ],
        voice=[
            "如果必须说话，先说'让我想一下'——买3秒时间，比乱说强100倍",
        ],
    ),
}

# 情绪关键词 → 调节类型映射
EMOTION_REGULATION_KEYWORDS: dict[str, list[str]] = {
    "紧张": ["紧张", "发抖", "手抖", "声音抖", "心跳快", "出汗", "手心出汗", "腿软"],
    "焦虑": ["焦虑", "不安", "烦躁", "心慌", "坐不住", "胡思乱想", "停不下来想"],
    "愤怒": ["气死", "愤怒", "火大", "暴怒", "想打人", "忍不了", "忍无可忍", "气炸了"],
    "低落": ["低落", "丧", "没劲", "不想动", "没动力", "灰心", "丧气", "消沉", "抑郁"],
    "慌乱": ["慌", "乱", "懵了", "脑子一片空白", "不知道怎么办", "手足无措", "六神无主"],
}


# ===== 触发识别 =====

def detect_scenario_intent(user_input: str) -> str | None:
    """
    检测用户输入是否包含进入线下博弈场景的意图。

    Returns:
        str | None: 匹配到的场景类型，或 None
    """
    for scenario, keywords in SCENARIO_KEYWORDS.items():
        for kw in keywords:
            if kw in user_input:
                return scenario
    return None


def detect_regulation_need(emotion_type: str, emotion_intensity: float, user_input: str = "") -> str | None:
    """
    检测用户是否需要五感自我调节。

    Args:
        emotion_type: 情绪类型（中文）
        emotion_intensity: 情绪强度 0-1
        user_input: 用户输入文本

    Returns:
        str | None: 匹配到的调节类型，或 None
    """
    # 情绪强度够高时，根据情绪类型匹配
    emotion_to_regulation = {
        "急躁": "紧张",
        "愤怒": "愤怒",
        "挫败": "低落",
        "迷茫": "焦虑",
    }

    if emotion_intensity >= 0.6:
        regulation = emotion_to_regulation.get(emotion_type)
        if regulation:
            return regulation

    # 从用户输入中匹配关键词
    for regulation_type, keywords in EMOTION_REGULATION_KEYWORDS.items():
        for kw in keywords:
            if kw in user_input:
                return regulation_type

    return None


# ===== 生成函数 =====

def generate_scenario_guide(scenario: str, emotion_type: str = "", emotion_intensity: float = 0.0) -> ScenarioGuide | None:
    """
    根据场景类型生成五感执行指导。

    Args:
        scenario: 场景类型（面试/谈判/演讲/约会/会议/汇报/冲突）
        emotion_type: 当前情绪类型
        emotion_intensity: 当前情绪强度

    Returns:
        ScenarioGuide | None: 场景指导，或 None（场景不存在时）
    """
    guide = SCENARIO_GUIDES.get(scenario)
    if not guide:
        return None

    # 高情绪时追加呼吸和注意事项
    if emotion_intensity >= 0.6:
        extra_caution = "你现在情绪偏高，先做2次深呼吸再进入场景，比带着情绪进去效果好很多"
        if extra_caution not in guide.caution:
            guide.caution.insert(0, extra_caution)

    return guide


def generate_regulation_guide(regulation_type: str) -> SelfRegulationGuide | None:
    """
    根据情绪状态生成五感自我调节指导。

    Args:
        regulation_type: 调节类型（紧张/焦虑/愤怒/低落/慌乱）

    Returns:
        SelfRegulationGuide | None: 调节指导，或 None
    """
    return SELF_REGULATION_GUIDES.get(regulation_type)


def format_scenario_guide(guide: ScenarioGuide) -> str:
    """将场景指导格式化为可读文本（供 Step 8 输出使用）"""
    parts = [f"【{guide.scenario}场景·身体执行指导】"]

    if guide.breath:
        parts.append("呼吸：" + "；".join(guide.breath))
    if guide.eye:
        parts.append("目光：" + "；".join(guide.eye))
    if guide.body:
        parts.append("身体：" + "；".join(guide.body))
    if guide.voice:
        parts.append("声音：" + "；".join(guide.voice))
    if guide.ear:
        parts.append("倾听：" + "；".join(guide.ear))
    if guide.caution:
        parts.append("注意：" + "；".join(guide.caution))

    return "\n".join(parts)


def format_regulation_guide(guide: SelfRegulationGuide) -> str:
    """将调节指导格式化为可读文本（供 Step 8 输出使用）"""
    parts = [f"【{guide.emotion_state}时·自我调节方法】"]

    if guide.breath:
        parts.append("呼吸：" + "；".join(guide.breath))
    if guide.tactile:
        parts.append("触觉锚定：" + "；".join(guide.tactile))
    if guide.visual:
        parts.append("视觉转移：" + "；".join(guide.visual))
    if guide.body:
        parts.append("身体动作：" + "；".join(guide.body))
    if guide.voice:
        parts.append("声音调节：" + "；".join(guide.voice))

    return "\n".join(parts)


# ===== 原有设计者视角函数（保持不变） =====

def apply_sensory_strategy(
    context=None,
    field_setup: FieldSetup | None = None,
    goal: str = "",
) -> list[SensoryAction]:
    """
    根据目标或场域设计，生成五感施加方案（设计者视角）

    Args:
        context: 可选，用于判断场景
        field_setup: 可选，预设的场域设计
        goal: 目标描述（如"激发行动"、"建立信任"、"降低防御"）

    Returns:
        list[SensoryAction]: 推荐的感觉施加动作列表
    """
    actions = []

    # 如果有预设场域设计，直接使用
    if field_setup:
        if field_setup.visual:
            actions.append(SensoryAction("visual", field_setup.visual, "场域设计", ""))
        if field_setup.audio:
            actions.append(SensoryAction("auditory", field_setup.audio, "场域设计", ""))
        if field_setup.smell:
            actions.append(SensoryAction("olfactory", field_setup.smell, "场域设计", ""))
        if field_setup.touch:
            actions.append(SensoryAction("tactile", field_setup.touch, "场域设计", ""))
        if field_setup.taste:
            actions.append(SensoryAction("gustatory", field_setup.taste, "场域设计", ""))
        return actions

    # 根据目标推荐
    # 视觉
    if "冲动" in goal or "行动" in goal or "激发" in goal:
        actions.extend(VISUAL_METHODS.get("制造冲动", []))
    elif "防御" in goal or "放松" in goal or "信任" in goal:
        actions.extend(VISUAL_METHODS.get("降低防御", []))
    else:
        actions.extend(VISUAL_METHODS.get("聚焦注意力", []))

    # 听觉
    if "放慢" in goal or "信任" in goal:
        actions.extend(AUDITORY_METHODS.get("放慢节奏", []))
    elif "加快" in goal or "紧迫" in goal:
        actions.extend(AUDITORY_METHODS.get("加快节奏", []))
    elif "神秘" in goal or "好奇" in goal:
        actions.extend(AUDITORY_METHODS.get("制造神秘", []))

    # 嗅觉
    if "尊贵" in goal or "高端" in goal:
        actions.extend(OLFACTORY_METHODS.get("植入尊贵感", []))
    elif "焦虑" in goal or "放松" in goal:
        actions.extend(OLFACTORY_METHODS.get("降低焦虑", []))

    # 味觉
    if "互惠" in goal or "试" in goal:
        actions.extend(GUSTATORY_METHODS.get("互惠心理", []))

    # 触觉
    if "信任" in goal or "放松" in goal:
        actions.extend(TACTILE_METHODS.get("增强信任", []))
    elif "谈判" in goal or "博弈" in goal:
        actions.extend(TACTILE_METHODS.get("削弱气势", []))

    return actions


def get_field_setup_by_element(element: str) -> FieldSetup:
    """
    根据五行属性获取场域设计方案

    Args:
        element: 五行属性（火/水/土/金/木）

    Returns:
        FieldSetup: 场域设计方案
    """
    config = FIVE_ELEMENTS_MAP.get(element, FIVE_ELEMENTS_MAP["土"])

    return FieldSetup(
        element=element,
        visual=config["visual"],
        audio=config["audio"],
        smell=config["smell"],
        touch=config["touch"],
        taste=config["taste"],
    )


def check_sensory_prerequisites(context=None) -> dict[str, bool]:
    """
    检查五感施加的前提条件（设计者视角）

    三个条件必须同时满足：
    1. 有物理空间控制权
    2. 涉及线下接触
    3. 有时间和资源进行环境设计

    注意：自我执行/自我调节视角不需要满足这些前提，
    因为用户自己进入场景或需要调节时，不需要场域控制权。

    Returns:
        dict: 各前提条件的检查结果
    """
    # 当前系统主要为线上对话，默认不满足线下条件
    # 后续接入线下场景时可扩展
    return {
        "has_physical_control": False,
        "is_offline": False,
        "has_time_and_resources": False,
        "can_apply": False,  # 三者同时满足才为 True
    }
