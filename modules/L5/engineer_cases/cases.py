"""
Human-OS Engine - L5 工程师实战案例

基于 15-人性工程师模块-实战案例-上.md 和 16-人性工程师模块-实战案例-下.md 的内容。
"""

from dataclasses import dataclass, field


@dataclass
class CaseEntry:
    """案例条目"""
    id: str
    title: str
    category: str
    scenario_keywords: list[str]
    emotion_types: list[str]
    desires: list[str]
    content: str
    source_file: str
    goal_types: list[str] = field(default_factory=list)
    core_purpose: str = ""
    tactical_sequence: list[str] = field(default_factory=list)
    emergency_plan: str = ""
    quick_principle: str = ""
    # 方向B: 场景路由和多轮延续
    applicable_scenes: list[str] = field(default_factory=list)  # 适用场景: ["management", "negotiation", ...]
    relationship_positions: list[str] = field(default_factory=list)  # 适用关系位置: ["上级-下级", "对等-竞争", ...]
    continuation_hints: list[str] = field(default_factory=list)  # 多轮延续提示: 每轮后如果用户还在，下一步往哪走


ENGINEER_CASES: dict[str, CaseEntry] = {
    "case_upward_management": CaseEntry(
        id="case_upward_management",
        title="向上管理：说服保守型领导",
        category="engineer_cases",
        scenario_keywords=["老板", "领导", "上级", "汇报", "申请", "预算", "项目", "试点"],
        emotion_types=["平静", "焦虑"],
        desires=["恐惧", "贪婪"],
        goal_types=["利益价值"],
        core_purpose="让保守型领导先批准一个小范围试点，而不是一上来否掉整个项目。",
        tactical_sequence=["引用权威", "镜像模仿", "倾听", "稀缺性赞美", "赋予身份", "描绘共同未来", "选择权引导"],
        emergency_plan="若领导强烈抵触，就切到附和+请教；若领导拖延，就补时间成本和外部变化带来的压力。",
        quick_principle="别硬说服，先让对方觉得风险可控、功劳可见、决定权还在他手里。",
        content="""场景：你有一个需要额外预算的创新项目，但直属领导风格保守、厌恶风险。

核心目的：让领导批准项目的初步预算，同意先做小范围试点。

连招序列：
1. 引用权威，让话题先站到更大的行业背景里
2. 镜像模仿+倾听，先降对方防御
3. 稀缺性赞美+赋予身份，让对方从审批者变成指导者
4. 描绘共同未来，把项目收益和对方功劳绑在一起
5. 选择权引导，别让结尾停在“要不要做”，而是停在“先怎么做”

关键：不要试图正面说服，而是让他觉得这是一个风险可控、对他也有好处的决定。""",
        source_file="15-人性工程师模块-实战案例-上.md",
        applicable_scenes=["management", "negotiation"],
        relationship_positions=["下级-上级"],
        continuation_hints=["领导犹豫→补时间成本和外部压力", "领导松动→立刻推试点方案细节", "领导否决→退回请教模式，留下次机会"],
    ),

    "case_downward_management": CaseEntry(
        id="case_downward_management",
        title="向下管理：批评敏感型下属",
        category="engineer_cases",
        scenario_keywords=["下属", "员工", "团队", "批评", "反馈", "犯错", "管理"],
        emotion_types=["挫败", "焦虑"],
        desires=["恐惧", "傲慢"],
        goal_types=["情绪价值", "利益价值"],
        core_purpose="让对方既看见问题严重性，又不因为羞愧直接垮掉。",
        tactical_sequence=["物理隔离", "肯定", "共情", "事实陈述", "质问", "沉默", "赋予身份", "鼓励"],
        emergency_plan="若对方情绪崩溃就先安抚再谈问题；若开始甩锅，就拉回到具体行为和责任。",
        quick_principle="先保住对方的安全感，再谈问题本身，不然只会得到防御和逃避。",
        content="""场景：下属工作努力但内心敏感，近期犯了严重错误。需要严肃指出问题但不打击信心。

核心目的：让下属清晰认识错误，并主动承诺改进措施，同时保住积极性。

连招序列：
1. 物理隔离，别在公开场合处理
2. 先肯定，再共情，先给安全感
3. 客观说事实，再让对方自己说出问题根因
4. 用沉默给压力，但别变成人身否定
5. 最后赋予身份和鼓励，把人从“犯错的人”拉回“还能成长的人”

关键：先处理情绪，再处理问题。让对方感到被支持，而不是被打翻。""",
        source_file="15-人性工程师模块-实战案例-上.md",
        applicable_scenes=["management"],
        relationship_positions=["上级-下级"],
        continuation_hints=["下属崩溃→先安抚再谈问题", "下属甩锅→拉回具体行为和责任", "下属接受→立刻给改进方案和鼓励"],
    ),

    "case_horizontal_collaboration": CaseEntry(
        id="case_horizontal_collaboration",
        title="横向协作：推动老油条同事配合",
        category="engineer_cases",
        scenario_keywords=["同事", "协作", "配合", "跨部门", "推进", "老油条", "推诿", "合作"],
        emotion_types=["平静", "焦虑"],
        desires=["傲慢", "贪婪"],
        goal_types=["利益价值"],
        core_purpose="让对方愿意配合，而且不是被逼着做，而是觉得帮你也对他有好处。",
        tactical_sequence=["求助", "稀缺性赞美", "给予价值", "制造亏欠感", "描绘共同未来", "公开场合积极贴标签"],
        emergency_plan="若对方当场打太极，就先收住不硬顶；若事后拖延，再用示弱式催促把他拉回承诺。",
        quick_principle="先满足对方的面子和利益，再谈配合，不要一上来就拿流程和道理压人。",
        content="""场景：你需要一位同级别、经验丰富但以不配合著称的同事帮助你推进重要项目。

核心目的：让他愿意提供必要支持，并按时完成。

连招序列：
1. 先用求助姿态切入，不要命令
2. 稀缺性赞美，满足对方“只有你懂”的虚荣
3. 预先给予一点价值，制造不好直接拒绝你的心理门槛
4. 绑定共同利益，让他感觉这不是只帮你
5. 初步答应后，找机会在公开场合给他贴积极标签，断他后路

关键：横向协作不是比谁有理，而是让对方觉得配合你这件事，面子上舒服，利益上也不亏。""",
        source_file="15-人性工程师模块-实战案例-上.md",
        applicable_scenes=["management", "negotiation"],
        relationship_positions=["对等-竞争", "对等-合作"],
        continuation_hints=["对方打太极→先收住不硬顶", "对方拖延→示弱式催促拉回承诺", "对方答应→公开贴积极标签锁住"],
    ),

    "case_negotiation": CaseEntry(
        id="case_negotiation",
        title="商业谈判：扭转劣势",
        category="engineer_cases",
        scenario_keywords=["谈判", "客户", "价格", "太贵", "优惠", "采购", "条件", "供应商"],
        emotion_types=["平静", "焦虑"],
        desires=["贪婪", "傲慢"],
        goal_types=["利益价值"],
        core_purpose="打破对方的心理优势，把对话从‘你接不接受这个价格’改成‘我们怎么重新定义交易价值’。",
        tactical_sequence=["附和", "最小化", "沉默", "转移话题", "锚定", "好奇", "选择权引导"],
        emergency_plan="若对方真准备离场，就先缓和重回诚意；若对方开始诉苦，就共情处境但守住原则。",
        quick_principle="别在对方框架里死磕价格，要重塑维度、重塑比较基准、重塑决定条件。",
        content="""场景：对方态度强势，开出的条件远超底线，暗示“不愁买家”。我方处于劣势。

核心目的：压低价格到可接受范围，并争取额外条款。

连招序列：
1. 先附和+最小化，卸掉对方第一波压力
2. 用沉默打断他的节奏
3. 转移话题，不在对方最强的框架里跟他玩
4. 重新锚定参照点，再用好奇摸清对方真正看重什么
5. 最后给两个可接受方案，让对方在你给的边界里选

关键：不要在对方的框架里玩，要重新定义谈判的维度。""",
        source_file="15-人性工程师模块-实战案例-上.md",
        applicable_scenes=["negotiation", "sales"],
        relationship_positions=["对等-竞争", "服务-客户"],
        continuation_hints=["对方强硬→沉默打断节奏再转框架", "对方松动→立刻给两个可选方案", "对方离场→先缓和重回诚意"],
    ),

    "case_social_breakthrough": CaseEntry(
        id="case_social_breakthrough",
        title="社交破局：快速融入高价值圈子",
        category="engineer_cases",
        scenario_keywords=["社交", "圈子", "融入", "人脉", "聚会", "陌生", "高价值", "破局"],
        emotion_types=["焦虑", "平静"],
        desires=["傲慢", "贪婪"],
        goal_types=["情绪价值", "利益价值"],
        core_purpose="不是刷存在感，而是在短时间里和关键人物建立一两个有效链接。",
        tactical_sequence=["倾听", "保持距离", "好奇", "稀缺性赞美", "给予价值", "求助", "悬念"],
        emergency_plan="若对方反应冷淡，就体面撤退换目标；若被质疑身份，就自信但谦和地报出自己的来路。",
        quick_principle="先观察，再精准切入；先给价值，再留钩子；别急着表现自己。",
        content="""场景：你参加了一场高价值圈子的聚会，大家彼此熟识，而你像个闯入者。

核心目的：和1到2位核心人物建立有效链接，并留下初步好印象。

连招序列：
1. 先观察，不急着冲进聊天中心
2. 选准对象后，用好奇切入，而不是上来就推自己
3. 送出稀缺性赞美，说明你真的听懂了对方
4. 在对话里给一点真正有价值的内容
5. 气氛最好时主动结束，并留一个后续话题

关键：社交破局靠的不是热闹，而是精准、克制和让人愿意下次继续跟你聊。""",
        source_file="15-人性工程师模块-实战案例-上.md",
        applicable_scenes=["emotion", "sales"],
        relationship_positions=["陌生-试探"],
        continuation_hints=["对方冷淡→体面撤退换目标", "对方回应→送稀缺性赞美+给价值", "聊到最好→主动结束留悬念"],
    ),

    "case_intimate_conflict": CaseEntry(
        id="case_intimate_conflict",
        title="亲密关系：终止争吵",
        category="engineer_cases",
        scenario_keywords=["伴侣", "老公", "老婆", "吵架", "冲突", "翻旧账", "关系"],
        emotion_types=["愤怒", "挫败"],
        desires=["愤怒", "恐惧"],
        goal_types=["情绪价值"],
        core_purpose="先停掉争吵升级，再把双方拉回到‘一起解决问题’的框架。",
        tactical_sequence=["物理隔离", "对情绪道歉", "共情", "重塑框架", "共同构建"],
        emergency_plan="若对方继续升级，就先拉长冷静时间；若对方开始沉默封闭，就先确认感受而不是继续追问。",
        quick_principle="争吵里先处理情绪，再谈是非；先停火，再解决。",
        content="""场景：和伴侣因小事陷入激烈争吵，双方都在翻旧账，问题本身已被遗忘。

核心目的：让争吵停下来，并重回合作处理。

连招序列：
1. 先物理隔离，打断继续升级
2. 对情绪道歉，不急着对观点认输
3. 共情，让对方先感觉被听见
4. 重塑框架，把“对打”改成“解决问题”
5. 共同构建下一步怎么做

关键：争吵的本质不是问题本身，是情绪没有被听到。先处理情绪，再处理问题。""",
        source_file="16-人性工程师模块-实战案例-下.md",
        applicable_scenes=["emotion"],
        relationship_positions=["亲密-依赖"],
        continuation_hints=["对方继续升级→拉长冷静时间", "对方沉默封闭→先确认感受不追问", "情绪降下来→重塑框架共同构建"],
    ),

    "case_family_boundary": CaseEntry(
        id="case_family_boundary",
        title="家庭伦理：拒绝道德绑架",
        category="engineer_cases",
        scenario_keywords=["家里", "父母", "长辈", "道德绑架", "亲戚", "不合理要求", "孝顺", "家庭"],
        emotion_types=["焦虑", "挫败"],
        desires=["恐惧", "傲慢"],
        goal_types=["情绪价值", "利益价值"],
        core_purpose="既拒绝不合理要求，又尽量不把关系直接推到撕裂。",
        tactical_sequence=["倾听", "共情", "肯定动机", "原则", "示弱", "价值补偿", "转移话题"],
        emergency_plan="若对方持续施压，就重复原则不进入情绪拉扯；若现场气氛失控，就先结束话题，换时间再谈。",
        quick_principle="先承认对方的情感诉求，再把行为边界说清，不要一上来硬碰硬。",
        content="""场景：面对长辈或家庭成员的不合理要求，你既不想妥协，也不想被道德绑架拖进去。

核心目的：温和但清楚地拒绝，同时守住关系底线。

连招序列：
1. 先倾听和共情，别一上来对冲
2. 肯定对方动机，把“爱你”与“这个要求合理”分开
3. 搬出原则和现实限制，说明你不是针对谁
4. 如果可以，给一点价值补偿或替代方案
5. 及时转移话题，不让对话陷入反复拉扯

关键：要拒绝的是具体要求，不是这段关系本身。""",
        source_file="16-人性工程师模块-实战案例-下.md",
        applicable_scenes=["emotion"],
        relationship_positions=["亲密-依赖"],
        continuation_hints=["对方持续施压→重复原则不进情绪拉扯", "气氛失控→先结束话题换时间再谈", "对方接受→给价值补偿修复关系"],
    ),

    "case_money_lending": CaseEntry(
        id="case_money_lending",
        title="朋友借钱：拒绝但不伤感情",
        category="engineer_cases",
        scenario_keywords=["朋友", "借钱", "不想借", "拒绝", "还不上", "周转"],
        emotion_types=["焦虑", "平静"],
        desires=["恐惧", "傲慢"],
        goal_types=["情绪价值", "利益价值"],
        core_purpose="把拒绝落在‘钱这件事’上，而不是落在‘你这个人不值得帮’上。",
        tactical_sequence=["热情倾听", "肯定友谊", "原则", "替代帮助", "留后路"],
        emergency_plan="若对方因此疏远，先尊重情绪，过后再正常联系；若对方指责你不够朋友，就重复原则，不陷入自证。",
        quick_principle="拒绝要趁早、要干净、要把感情和金钱分开处理。",
        content="""场景：关系不错的朋友借一大笔钱，但还款能力存疑，你不想借。

核心目的：拒绝借钱，同时尽量保住关系。

连招序列：
1. 先热情倾听，让对方把话说完
2. 肯定交情，别让拒绝显得像否定关系
3. 搬出适用于所有人的原则
4. 给替代性帮助，而不是只剩一句“不借”
5. 留后路，让关系还能继续

关键：拒绝的是“借钱这件事”，不是“这段关系”。让对方感受到你仍然在乎他。""",
        source_file="16-人性工程师模块-实战案例-下.md",
        applicable_scenes=["emotion"],
        relationship_positions=["亲密-依赖"],
        continuation_hints=["对方疏远→先尊重情绪过后再联系", "对方指责→重复原则不陷入自证", "对方理解→给替代帮助巩固关系"],
    ),

    "case_public_speaking": CaseEntry(
        id="case_public_speaking",
        title="公众表达：化解刁钻提问",
        category="engineer_cases",
        scenario_keywords=["演讲", "提问", "刁钻", "质疑", "公开场合", "汇报", "Q&A", "难堪"],
        emotion_types=["焦虑", "平静"],
        desires=["傲慢", "恐惧"],
        goal_types=["情绪价值", "利益价值"],
        core_purpose="把带攻击性的问题转成你的阐述机会，而不是现场被牵着鼻子走。",
        tactical_sequence=["赞美", "点头认同", "重构问题", "贴标签", "引用权威", "给予价值", "幽默", "转移话题"],
        emergency_plan="若问题超出范围，就坦诚示弱并约到会后；若对方继续纠缠，就用流程原则结束当前轮次。",
        quick_principle="先吸收攻击，再重构问题，再把回答权重新拿回来。",
        content="""场景：你在公开演讲或汇报中，遇到一个尖锐、带挑战性的问题，对方明显想让你难堪。

核心目的：稳住场面，化解攻击，顺势展现专业度。

连招序列：
1. 先赞美提问，别第一反应就防守
2. 用自己的话重构问题，把议题拉回你能掌控的表述里
3. 用权威、数据或案例给出有价值的回答
4. 回答完后用轻一点的收尾，马上切回场控节奏

关键：不要被对方的问题结构困住，你要把问题改写成你更有利的版本。""",
        source_file="16-人性工程师模块-实战案例-下.md",
        applicable_scenes=["management", "negotiation"],
        relationship_positions=["对等-竞争", "下级-上级"],
        continuation_hints=["问题超出范围→坦诚示弱约会后", "对方纠缠→用流程原则结束当前轮次", "回答完→轻收尾切回场控节奏"],
    ),

    "case_pua_defense": CaseEntry(
        id="case_pua_defense",
        title="自我防御：反击PUA式贬低",
        category="engineer_cases",
        scenario_keywords=["PUA", "贬低", "打压", "嘲讽", "被欺负", "阴阳怪气", "边界"],
        emotion_types=["愤怒", "挫败"],
        desires=["愤怒", "傲慢"],
        goal_types=["情绪价值"],
        core_purpose="停掉对方的模糊打压，重新把边界和定义权拿回来。",
        tactical_sequence=["沉默", "死亡凝视", "反问", "贴标签", "原则", "警告"],
        emergency_plan="若对方反说你开不起玩笑，就承认风格不同但不后退；若不适合当场回击，就事后单独设边界。",
        quick_principle="不要急着解释自己，先让对方解释他的话，再把边界说清楚。",
        content="""场景：某人习惯性通过“开玩笑”或“为你好”来贬低你，打击你的自信。

核心目的：识别并中止对方的贬低行为，维护自尊，同时避免直接撕破脸。

连招序列：
1. 先沉默，不接剧本
2. 用反问逼对方落到具体事实
3. 平静贴标签，点出对方到底在做什么
4. 用原则和边界把后续规则说清楚

关键：PUA的本质是通过模糊边界来控制。你需要做的就是让边界变得清晰。""",
        source_file="16-人性工程师模块-实战案例-下.md",
        applicable_scenes=["emotion", "management"],
        relationship_positions=["对等-竞争", "上级-下级", "亲密-依赖"],
        continuation_hints=["对方说开不起玩笑→承认风格不同但不后退", "不适合当场回击→事后单独设边界", "对方收敛→立刻正常化关系不记仇"],
    ),
}
