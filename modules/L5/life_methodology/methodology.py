"""
Human-OS Engine - L5 人生方法论知识库

基于 11-人生方法论模块（内核层）、12-人生方法论模块（交互层）、13-人生方法论模块（规则层）的内容。
"""

from dataclasses import dataclass


@dataclass
class KnowledgeEntry:
    """知识条目"""
    id: str
    title: str
    category: str
    keywords: list[str]
    content: str
    source_file: str
    # 方向B: 可执行映射
    trigger_conditions: dict = None  # 什么时候调: {"emotion_types": [...], "desires": [...], "situation_stages": [...], "relationship_positions": [...]}
    action_mapping: str = ""         # 调了怎么变成策略指令: 描述性文本，供Step6策略生成参考
    priority_scenes: list[str] = None  # 优先场景: ["emotion", "management", ...]


METHODOLOGY_KNOWLEDGE: dict[str, KnowledgeEntry] = {
    "emotion_management": KnowledgeEntry(
        id="emotion_management",
        title="情绪管理",
        category="life_methodology",
        keywords=["情绪", "管理", "控制", "愤怒", "焦虑", "生气", "发火"],
        content="""情绪管理的核心方法：

1. 情绪暂停与命名
当强烈情绪涌起时，训练自己第一时间启动"暂停"机制。可以是一个深呼吸，或者在心里默数三秒。紧接着，给这个情绪命名："哦，我注意到，'愤怒'来了。"

2. 事实与叙事剥离
情绪100%来源于"叙事"，而非"事实"。事实是像摄像头一样记录下来的、不带任何感情色彩的客观情况。叙事是我们基于事实，结合自己的信念、经验和偏见，在大脑里编造的故事。

3. 解读情绪的信使功能
愤怒→边界被侵犯；焦虑→准备不足；嫉妒→揭示欲望；羞耻→接纳需求。每种情绪都在告诉你一些信息，学会倾听。""",
        source_file="11-人生方法论模块-内核层.md",
        trigger_conditions={"emotion_types": ["愤怒", "焦虑", "急躁", "挫败"], "desires": ["fear", "wrath"], "situation_stages": ["修复", "僵持"]},
        action_mapping="先命名情绪→再剥离事实和叙事→最后解读信使功能。策略上：先共情接纳，再引导看事实，最后给行动建议",
        priority_scenes=["emotion", "management"],
    ),

    "desire_management": KnowledgeEntry(
        id="desire_management",
        title="欲望管理",
        category="life_methodology",
        keywords=["欲望", "控制", "贪婪", "想要", "渴望"],
        content="""欲望管理的核心方法：

1. 欲望的觉察与承认
坦然承认自己所有欲望的合理性，不进行道德上的自我批判。

2. 欲望的溯源与降噪
当一个强烈的欲望产生时，暂停一下，问自己：这个欲望是从哪里来的？满足这个欲望，我真正想获得的是什么感觉？有没有其他成本更低的方式可以获得同样的感觉？

        3. 建立欲望的金字塔结构
为自己的人生设定一个核心的、长期的、有巨大价值的目标。这个"顶层欲望"会自然地吸附和整合所有底层的、琐碎的欲望。""",
        source_file="11-人生方法论模块-内核层.md",
    ),

    "desire_noise_reduction": KnowledgeEntry(
        id="desire_noise_reduction",
        title="欲望降噪",
        category="life_methodology",
        keywords=["欲望", "降噪", "冲动消费", "种草", "广告", "社交媒体", "比较", "刺激"],
        content="""欲望降噪的核心不是硬压，而是先看清来源。

先问三件事：
1. 这个念头是我真想要，还是被广告、算法、朋友圈刺激出来的？
2. 我真正想买的，是东西本身，还是它代表的安全感、优越感、被看见？
3. 有没有更便宜、更健康的方式拿到同样的感觉？

重点不是立刻戒掉所有欲望，而是先把外界噪音和真实需求分开。""",
        source_file="11-人生方法论模块-内核层.md",
        trigger_conditions={"desires": ["greed", "gluttony"], "situation_stages": ["推进", "僵持"]},
        action_mapping="先帮用户分清'真想要'vs'被刺激'→再追问深层需求→最后给替代方案。策略上：用提问引导自省，不直接否定欲望",
        priority_scenes=["sales", "negotiation"],
    ),

    "cognitive_bias_life": KnowledgeEntry(
        id="cognitive_bias_life",
        title="认知偏误对抗",
        category="life_methodology",
        keywords=["认知", "偏误", "错误", "思维", "判断"],
        content="""四种核心认知偏误及对抗方法：

1. 确认偏误：只找支持自己观点的证据
对抗：元认知——思考你的思考。主动寻找反面证据。

2. 损失厌恶：害怕失去远大于渴望获得
对抗：反向思考——问自己"如果我从未拥有过这个，我现在愿意花多少钱买它？"

3. 幸存者偏差：只看到成功案例
对抗：决策日记——记录并复盘每个决策的过程和结果。

4. "应该"的暴政：僵化规则导致痛苦
对抗：概率思维——用"大概率/小概率"代替"一定/肯定"。""",
        source_file="11-人生方法论模块-内核层.md",
    ),

    "emotion_false_alarm": KnowledgeEntry(
        id="emotion_false_alarm",
        title="情绪误报与事实剥离",
        category="life_methodology",
        keywords=["情绪误报", "误报", "事实", "叙事", "邮件", "批评", "被针对", "失控"],
        content="""很多情绪不是事实太危险，而是大脑把现代刺激按原始威胁在处理。

像一封批评邮件、一次公开发言、一次价格波动，都可能被身体误判成真正的危险。

处理方法：
1. 先停一下，别急着跟着情绪跑
2. 只写事实，不写脑补
3. 再把你心里的故事单独拎出来看

事实和脑补一分开，情绪就没那么容易失控。""",
        source_file="11-人生方法论模块-内核层.md",
        trigger_conditions={"emotion_types": ["焦虑", "恐惧", "愤怒"], "situation_stages": ["修复", "僵持"]},
        action_mapping="先帮用户停下来→再引导只写事实不写脑补→最后把故事拎出来看。策略上：先接住情绪，再引导事实剥离，不急着讲道理",
        priority_scenes=["emotion", "management"],
    ),

    "emotion_contagion": KnowledgeEntry(
        id="emotion_contagion",
        title="情绪传染与自我隔离",
        category="life_methodology",
        keywords=["情绪传染", "被带节奏", "被影响", "办公室", "抱怨", "社交媒体", "焦虑", "宿主"],
        content="""你有时候并不是在感受自己的情绪，而是在接别人的情绪。

办公室的抱怨、群里的焦虑、社交媒体上的戾气，都会慢慢变成你的背景噪音。

处理方法：
1. 先分清这是我的情绪，还是我被带进去了
2. 暂时远离高污染环境
3. 用更稳定的人和内容，替换掉持续消耗你的输入源

先把情绪源头隔离，很多问题就会自己降下来。""",
        source_file="11-人生方法论模块-内核层.md",
    ),

    "metacognition": KnowledgeEntry(
        id="metacognition",
        title="元认知自检",
        category="life_methodology",
        keywords=["元认知", "自检", "我为什么这么想", "旁观自己", "观察自己", "思考过程"],
        content="""元认知说白了，就是从脑子里退半步，看自己在怎么想。

你可以常问自己：
1. 我为什么会这么想？
2. 我现在抓住的证据，够不够？
3. 有没有我故意不想看的另一面？

一旦你能看见自己的思路，很多偏见就没那么容易把你带走。""",
        source_file="11-人生方法论模块-内核层.md",
    ),

    "reverse_thinking": KnowledgeEntry(
        id="reverse_thinking",
        title="反向思考",
        category="life_methodology",
        keywords=["反向思考", "证伪", "反面证据", "如果我错了", "恶魔代言人", "反驳"],
        content="""当你越觉得自己对，越要逼自己找反面证据。

可以直接问：
1. 如果我现在这个判断是错的，最可能错在哪？
2. 有没有哪个事实，是我一直不愿意看？
3. 如果站在反方，我会怎么攻击我现在的想法？

这不是自我否定，而是防止自己在错误的路上越走越笃定。""",
        source_file="11-人生方法论模块-内核层.md",
    ),

    "decision_journal": KnowledgeEntry(
        id="decision_journal",
        title="决策日记",
        category="life_methodology",
        keywords=["决策日记", "复盘", "记录决策", "判断依据", "当时怎么想", "过程"],
        content="""重要决策别只看结果，要把当时怎么想记下来。

最少记四件事：
1. 当时的情境
2. 你做判断的依据
3. 你预期会发生什么
4. 事后对照看看，究竟是判断错了，还是运气不好

这样你复盘的就不是情绪，而是真正的决策能力。""",
        source_file="11-人生方法论模块-内核层.md",
    ),

    "procrastination": KnowledgeEntry(
        id="procrastination",
        title="克服拖延",
        category="life_methodology",
        keywords=["拖延", "懒", "不想做", "坚持", "动力"],
        content="""克服拖延的核心方法：

1. 从小处着手，单点突破
不要试图一夜之间改变所有。只选择一个概念，用一个月的时间刻意实践。

2. 建立系统和习惯
不要指望靠"毅力"去坚持。将行为系统化和习惯化，使其成为生活中近乎自动的部分。

3. 两分钟法则
如果一件事能在两分钟内完成，立刻做。不要让它进入你的待办清单。

4. 环境设计
改变环境比改变意志力容易。想多喝水？把水杯放在桌面上。想少刷手机？把手机放在另一个房间。""",
        source_file="13-人生方法论模块-规则层.md",
    ),

    "personal_value": KnowledgeEntry(
        id="personal_value",
        title="个人价值提升",
        category="life_methodology",
        keywords=["价值", "提升", "能力", "成长", "赚钱"],
        content="""个人价值公式：

个人价值 ≈ (解决问题的难度 × 解决问题的广度) / 解决方案的可替代性

三种价值幻觉：
1. 努力幻觉：市场只为结果付费，不为过程买单
2. 证书幻觉：证书只是门票，不是价值本身
3. 自我中心幻觉：应从市场需求出发，而非自我视角

提升价值的方法：
1. 成为"问题猎手"：主动寻找高价值问题去解决
2. 构建T型能力结构：一专多能
3. 价值的"产品化"与"品牌化"：让价值可复制、可传播""",
        source_file="12-人生方法论模块-交互层.md",
    ),

    "value_illusion": KnowledgeEntry(
        id="value_illusion",
        title="价值幻觉识别",
        category="life_methodology",
        keywords=["努力幻觉", "证书幻觉", "自我中心幻觉", "价值幻觉", "证书", "头衔", "辛苦"],
        content="""很多人卡住，不是没努力，而是把努力、证书、头衔误当成价值本身。

常见误区有三个：
1. 努力幻觉：以为辛苦就该有高回报
2. 证书幻觉：以为拿到证、进过大厂就等于有持续价值
3. 自我中心幻觉：老从自己想做什么出发，不看别人真正需要什么

市场最后只认一件事：你现在能不能解决真实问题。""",
        source_file="12-人生方法论模块-交互层.md",
    ),

    "rules_adaptation": KnowledgeEntry(
        id="rules_adaptation",
        title="明规则与潜在惯例",
        category="life_methodology",
        keywords=["规则", "潜规则", "不成文", "惯例", "新公司", "组织文化", "学生思维", "职场"],
        content="""一个地方怎么运转，通常不只有明文规定，还有一套大家默认遵守的惯例。

稳的做法是三步：
1. 先守住明面规则，别踩线
2. 再观察谁真正拍板、信息怎么流、资源怎么分
3. 最后在不违规的前提下，用更顺这个环境的方式推进事情

别只盯制度，也别只玩关系。成熟做法是两套都看。""",
        source_file="12-人生方法论模块-交互层.md",
    ),

    "relationship_management": KnowledgeEntry(
        id="relationship_management",
        title="人际关系管理",
        category="life_methodology",
        keywords=["关系", "人际", "社交", "朋友", "同事"],
        content="""关系管理（双账户模型）：

任何一段稳定、健康的关系，都可以被解构为两个核心账户：
1. 价值账户：记录功利性、可交换的价值（资源、信息、技能、机会）
2. 情感账户：记录信任、喜爱、安全感、归属感

关系定律：短期看价值，长期看情感。

方法论：
1. 成为"主动存款人"：先付出，后收获
2. 关系组合的差异化管理：核心圈、支持圈、外围圈
3. 学会清晰而温和地设立边界
4. 投资于提供"情绪价值"：共情、认可、陪伴""",
        source_file="12-人生方法论模块-交互层.md",
    ),

    "boundary_setting": KnowledgeEntry(
        id="boundary_setting",
        title="边界设立",
        category="life_methodology",
        keywords=["边界", "拒绝", "不好意思拒绝", "越界", "透支", "讨好", "说不"],
        content="""边界不是翻脸，而是清楚地告诉别人，你的时间、精力和底线到哪里。

好用的做法是：
1. 先说明现实限制
2. 再明确你的边界
3. 如果合适，再给一个替代方案

不设边界，看起来是好相处，最后往往会变成被持续透支。""",
        source_file="12-人生方法论模块-交互层.md",
        trigger_conditions={"desires": ["fear"], "relationship_positions": ["亲密-依赖", "下级-上级"], "situation_stages": ["僵持", "修复"]},
        action_mapping="先说明现实限制→再明确边界→最后给替代方案。策略上：用'三明治'结构（肯定+边界+替代），语气温和但立场清晰",
        priority_scenes=["emotion", "management"],
    ),

    "emotional_value": KnowledgeEntry(
        id="emotional_value",
        title="情绪价值",
        category="life_methodology",
        keywords=["情绪价值", "被理解", "被认可", "陪伴", "信任", "安全感", "关系维护"],
        content="""很多关系最后拼的，不是谁更会讲道理，而是谁更能让人感到被理解、被认可、被尊重。

情绪价值不复杂，核心就几件事：
1. 认真听
2. 关键处给认可
3. 情绪高的时候先接住，不急着讲道理
4. 在对方需要时给稳定感

这类东西成本不一定高，但杠杆往往很大。""",
        source_file="12-人生方法论模块-交互层.md",
    ),

    "compound_interest": KnowledgeEntry(
        id="compound_interest",
        title="复利法则",
        category="life_methodology",
        keywords=["复利", "坚持", "积累", "长期", "习惯"],
        content="""复利法则：

核心公式：y = a(1+x)^n

人性障碍：
1. 追求暴利（贪婪）→频繁切换赛道，n无法积累
2. 无法忍受平坦期（急躁）→放弃
3. 负复利（坏习惯）→日积月累侵蚀成果

方法论：
1. 投资三大复利资产（知识、健康、关系）
2. 建立反馈-修正循环（确保x>0）
3. 用系统和习惯对抗意志力消耗
4. 对负复利进行无情地止损

外部表达："只要每天进步一点点，时间长了会有巨大变化"
不要说："复利法则"（太学术）""",
        source_file="13-人生方法论模块-规则层.md",
    ),

    "entropy_increase": KnowledgeEntry(
        id="entropy_increase",
        title="熵增定律与主动整理",
        category="life_methodology",
        keywords=["熵增", "混乱", "整理", "秩序", "负熵"],
        content="""熵增定律：孤立系统总是趋向混乱

方法论：
1. 主动引入负熵流（新知识/新能量/新秩序）
2. 系统化/习惯化
3. 定期复盘和清理

外部表达："如果不主动整理，生活和工作会越来越乱"
不要说："熵增定律"（太学术）""",
        source_file="13-人生方法论模块-规则层.md",
    ),

    "antifragile": KnowledgeEntry(
        id="antifragile",
        title="不确定性与反脆弱",
        category="life_methodology",
        keywords=["不确定", "反脆弱", "黑天鹅", "风险", "决策", "变化", "不稳定"],
        content="""世界本来就充满变数，真正稳的人，不是把一切都算死，而是让自己在变化里也不容易崩。

核心思路：
1. 别迷信绝对控制
2. 别只用结果判断一次决策对不对
3. 给自己留弹性，不把所有筹码押在一个答案上

比起追求完美预测，更重要的是让自己扛得住波动，甚至能从波动里获益。""",
        source_file="13-人生方法论模块-规则层.md",
        trigger_conditions={"emotion_types": ["焦虑", "恐惧"], "desires": ["fear"], "situation_stages": ["僵持", "推进"]},
        action_mapping="先承认不确定性→再引导留弹性→最后给杠铃策略建议。策略上：不追求完美方案，引导用户接受波动、保留选择权",
        priority_scenes=["negotiation", "management"],
    ),

    "barbell_strategy": KnowledgeEntry(
        id="barbell_strategy",
        title="杠铃策略",
        category="life_methodology",
        keywords=["杠铃策略", "安全", "高风险", "高回报", "资源分配", "尝试", "试错"],
        content="""更稳的做法，不是把所有资源放在中间，而是大部分放稳，小部分去试。

简单说就是：
1. 大部分时间、钱、精力放在稳定盘上
2. 小部分拿去做高弹性的尝试

这样最差也不至于伤筋动骨，但一旦试对一次，回报会很可观。""",
        source_file="13-人生方法论模块-规则层.md",
    ),

    "optionality": KnowledgeEntry(
        id="optionality",
        title="保留选择权",
        category="life_methodology",
        keywords=["选择权", "可选性", "保留余地", "不可逆", "先试", "灵活", "决策"],
        content="""遇到重大决策时，优先选那个能给你留下更多余地的方案。

你可以理解成：
1. 先别把自己一次性锁死
2. 先用小成本试
3. 让未来还有转身空间

很多人不是输在选错，而是太早把门关死了。""",
        source_file="13-人生方法论模块-规则层.md",
        trigger_conditions={"desires": ["greed", "fear"], "situation_stages": ["推进", "收口"]},
        action_mapping="先问'这个决定可逆吗'→再引导小成本试→最后确保留转身空间。策略上：用提问代替建议，帮用户自己看到锁死风险",
        priority_scenes=["negotiation", "sales"],
    ),

    "knowledge_action": KnowledgeEntry(
        id="knowledge_action",
        title="知行合一",
        category="life_methodology",
        keywords=["知行合一", "行动", "实践", "做到"],
        content="""知行合一路径：

1. 小处着手，单点突破
2. 迭代复盘
3. 从知到行再到是（让原则内化为习惯）
4. 拥抱旅程

外部表达："光知道没用，关键是去做"
不要说："知行合一"（太学术）""",
        source_file="13-人生方法论模块-规则层.md",
    ),
}
