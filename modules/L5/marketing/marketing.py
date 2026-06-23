"""
Human-OS Engine - L5 营销知识库

基于 17-21 人性营销模块的内容。
包含认知偏差、赚钱铁律、人群透镜、情绪操盘、社会原力等子领域。
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


MARKETING_KNOWLEDGE: dict[str, KnowledgeEntry] = {
    # ===== 17-认知偏差 =====
    "conversion_rate": KnowledgeEntry(
        id="conversion_rate",
        title="提高转化率：七大认知偏差",
        category="marketing",
        keywords=["转化", "营销", "销售", "成交", "客户"],
        content="""提高认知转化率的七大认知偏差：

1. 锚定效应：先入为主的价格标尺。在标价旁边放一个划掉的"原价"。
2. 从众效应：大家都在买，一定不会错。展示"xxx人已购买"。
3. 稀缺效应：越少人拥有，价值感越高。"限量发售""仅剩3件"。
4. 损失规避：失去的痛苦 > 得到的快乐。"免费试用7天，到期后将无法享受..."。
5. 框架效应：换个说法，天差地别。"90%脱脂"比"10%脂肪"好。
6. 权威效应：听专家的，总没错。"牙医推荐""诺贝尔奖技术"。
7. 互惠原理：拿人手短，吃人嘴软。免费试吃、送资料。""",
        source_file="17-人性营销模块-七宗罪与认知偏差.md",
    ),
    "cognitive_bias_anchor": KnowledgeEntry(
        id="cognitive_bias_anchor",
        title="锚定效应应用",
        category="marketing",
        keywords=["锚定", "价格", "原价", "对比", "参照"],
        content="""锚定效应：先入为主的价格标尺

应用方法：
1. 在标价旁边放一个划掉的"原价"
2. 先推荐昂贵产品，再推荐目标产品
3. 软件订阅中用"企业版"作为锚点

关键：锚点必须看起来合理，否则会被识破""",
        source_file="17-人性营销模块-七宗罪与认知偏差.md",
    ),
    "cognitive_bias_social_proof": KnowledgeEntry(
        id="cognitive_bias_social_proof",
        title="从众效应与社会证明",
        category="marketing",
        keywords=["从众", "大家都在买", "销量", "好评", "排队"],
        content="""从众效应：大家都在买，一定不会错

应用方法：
1. 展示"xxx人已购买"
2. 展示好评数量和具体内容
3. 制造排队现象

关键：数字要真实可查，虚假数据会反噬信任""",
        source_file="17-人性营销模块-七宗罪与认知偏差.md",
    ),
    "cognitive_bias_scarcity": KnowledgeEntry(
        id="cognitive_bias_scarcity",
        title="稀缺效应与损失规避",
        category="marketing",
        keywords=["稀缺", "限量", "限时", "仅剩", "损失"],
        content="""稀缺效应：越少人拥有，价值感越高
损失规避：失去的痛苦 > 得到的快乐

应用方法：
1. "限量发售""仅剩3件"
2. "免费试用7天，到期后将无法享受..."
3. 强调"将要失去什么"而非"将要得到什么"

关键：稀缺必须真实，否则失去信任""",
        source_file="17-人性营销模块-七宗罪与认知偏差.md",
    ),
    "cognitive_bias_frame": KnowledgeEntry(
        id="cognitive_bias_frame",
        title="框架效应与权威效应",
        category="marketing",
        keywords=["框架", "说法", "权威", "专家", "背书"],
        content="""框架效应：换个说法，天差地别
- "90%脱脂"比"10%脂肪"好
- "每天3元"比"年费1095元"好

权威效应：听专家的，总没错
- 专家背书、资质证明
- "牙医推荐""诺贝尔奖技术"

关键：框架要符合事实，权威要真实可信""",
        source_file="17-人性营销模块-七宗罪与认知偏差.md",
    ),
    "cognitive_bias_reciprocity": KnowledgeEntry(
        id="cognitive_bias_reciprocity",
        title="互惠原理",
        category="marketing",
        keywords=["互惠", "免费", "试吃", "资料", "亏欠"],
        content="""互惠原理：拿人手短，吃人嘴软

应用方法：
1. 免费试吃、送资料
2. 先提供价值，再请求回报
3. 制造亏欠感

关键：给予的价值要真诚，否则被视为操控""",
        source_file="17-人性营销模块-七宗罪与认知偏差.md",
    ),
    "marketing_core_mindset": KnowledgeEntry(
        id="marketing_core_mindset",
        title="借势思维、结果导向与认知之争",
        category="marketing",
        keywords=["借势", "认知", "心智", "结果导向", "营销理念"],
        content="""营销的底层不是花样，而是三件事：

1. 借势思维：不要什么都从零硬造，要借用户脑中已有认知、社会情绪、行业趋势和对手能量。
2. 结果导向：所有动作最后都要回到结果，能不能带来咨询、转化、成交。
3. 认知之争：营销不是产品参数之争，而是用户心智占位之争。

适合用在品牌起盘、定位梳理、营销总方向混乱的时候。先把“借什么势、打什么认知、要什么结果”说清楚，再谈动作。""",
        source_file="17-人性营销模块-七宗罪与认知偏差.md",
    ),
    # ===== 18-赚钱铁律 =====
    "money_making_focus": KnowledgeEntry(
        id="money_making_focus",
        title="聚焦：一针捅破天",
        category="marketing",
        keywords=["聚焦", "专注", "一件事", "打穿"],
        content="""赚钱铁律一：聚焦

能量有限，分散等于没有。
问自己：如果只能保留一个业务、一个卖点、一个客户标签，你会是什么？
然后将99%的资源投入其中，直到打穿为止。

外部表达：集中精力做好一件事。""",
        source_file="18-人性营销模块-赚钱铁律与关系构建.md",
    ),
    "money_making_persistence": KnowledgeEntry(
        id="money_making_persistence",
        title="死磕：大力出奇迹",
        category="marketing",
        keywords=["死磕", "坚持", "重复", "90天"],
        content="""赚钱铁律二：死磕

选择一个最小可行性动作，雷打不动重复执行90天。
不问结果，只问执行。

外部表达：每天固定时间做同一件小事，先坚持一个月看看变化。""",
        source_file="18-人性营销模块-赚钱铁律与关系构建.md",
    ),
    "money_making_results": KnowledgeEntry(
        id="money_making_results",
        title="结果导向：会赚钱的才是好营销",
        category="marketing",
        keywords=["结果", "收益", "复盘", "实际"],
        content="""赚钱铁律三：结果导向

以天为单位复盘，用“是否产生实际收益”作为衡量标准。
内容、投流、社群、直播再热闹，最后都要回到成交和结果。""",
        source_file="18-人性营销模块-赚钱铁律与关系构建.md",
    ),
    "relationship_storytelling": KnowledgeEntry(
        id="relationship_storytelling",
        title="故事营销与品牌人格",
        category="marketing",
        keywords=["故事", "品牌", "人格", "IP", "创始人"],
        content="""关系构建方法：

1. 故事营销：品牌故事、产品故事、用户故事。
2. 品牌人格：让品牌有稳定气质、立场和说话方式。
3. 让故事承载价值观，而不只是讲经历。

关键：故事要真实，人格要一致。""",
        source_file="18-人性营销模块-赚钱铁律与关系构建.md",
    ),
    "community_building": KnowledgeEntry(
        id="community_building",
        title="社群构建与归属感",
        category="marketing",
        keywords=["社群", "归属感", "参与感", "用户社区", "我们的人"],
        content="""社群构建的关键，不是把人拉进群，而是让用户感觉“我是这里的人”。

怎么做：
1. 给用户参与感：让用户能提建议、能共创、能被看见。
2. 给用户身份感：设计称呼、黑话、徽章、圈层标签。
3. 给用户连接感：让用户和用户之间发生关系，而不只是用户和品牌单线连接。

真正稳的关系，是把消费者变成“我们的人”。""",
        source_file="18-人性营销模块-赚钱铁律与关系构建.md",
    ),
    "brand_ip": KnowledgeEntry(
        id="brand_ip",
        title="IP化与值钱逻辑",
        category="marketing",
        keywords=["IP", "人格", "值钱", "品牌人格", "稀缺性"],
        content="""IP化不是简单做一个卡通形象，而是让品牌像一个有性格的人。

核心不是“会赚钱”，而是“值钱”：
1. 有清晰人格
2. 有稳定表达
3. 有不可替代性

值钱是因，赚钱是果。真正能沉淀的品牌，一定先把稀缺性做出来。""",
        source_file="18-人性营销模块-赚钱铁律与关系构建.md",
    ),
    "relationship_ritual": KnowledgeEntry(
        id="relationship_ritual",
        title="仪式感与游戏化",
        category="marketing",
        keywords=["仪式感", "游戏化", "积分", "等级", "体验"],
        content="""关系构建方法：

1. 仪式感：把普通行为变成值得记住的体验。
2. 游戏化：积分、等级、勋章、排行榜。

关键：仪式要独特，游戏要有意义。""",
        source_file="18-人性营销模块-赚钱铁律与关系构建.md",
    ),
    "paid_mindset": KnowledgeEntry(
        id="paid_mindset",
        title="付费思维：购买时间与筛选结果",
        category="marketing",
        keywords=["付费", "付费思维", "购买时间", "咨询", "筛选"],
        content="""付费思维的核心，不是花钱，而是少走弯路。

本质上你买的是三样东西：
1. 别人已经筛过的高质量信息
2. 别人试错后的经验
3. 自己节省下来的时间和注意力

免费的内容很多，但最贵的常常也是免费内容，因为它会消耗你大量筛选成本。""",
        source_file="18-人性营销模块-赚钱铁律与关系构建.md",
    ),
    "link_high_value_people": KnowledgeEntry(
        id="link_high_value_people",
        title="链接高人：换圈子比闷头更快",
        category="marketing",
        keywords=["高人", "圈子", "高端社群", "链接", "被看见"],
        content="""链接高人的关键，不是讨好，而是换环境、换视野、换连接方式。

可用做法：
1. 主动付费进入更高质量的圈层
2. 想清楚自己能提供什么价值，再去链接
3. 持续在一个垂直方向输出，让自己被看见

很多人的瓶颈不是努力不够，而是一直待在原来的圈层里。""",
        source_file="18-人性营销模块-赚钱铁律与关系构建.md",
    ),
    # ===== 19-人群透镜 =====
    "demographic_gen_z": KnowledgeEntry(
        id="demographic_gen_z",
        title="Z世代(18-25)消费心理",
        category="marketing",
        keywords=["Z世代", "年轻人", "18-25", "造梗", "颜值"],
        content="""Z世代核心：自我探索与身份构建

主导引擎：虚荣、好奇、从众、懒惰
喜欢：造梗共创、颜值正义、悦己消费、社交货币、瞬时反馈
讨厌：爹味说教、尬聊讨好、虚假伪善、侵犯隐私

策略：Mode B（感官刺激、社交驱动）""",
        source_file="19-人性营销模块-人群透镜与反脆弱.md",
    ),
    "demographic_young_professional": KnowledgeEntry(
        id="demographic_young_professional",
        title="青年奋斗者(25-35)消费心理",
        category="marketing",
        keywords=["青年", "奋斗者", "25-35", "成长", "质价比"],
        content="""青年奋斗者核心：事业起步与家庭建立

主导引擎：恐惧、嫉妒、贪婪、懒惰
喜欢：成长价值、质价比、解决方案式产品、轻奢标签、专业背书
讨厌：画大饼、浪费时间、智商税、不专业服务

策略：Mode B + Mode A（成长价值+效率工具）""",
        source_file="19-人性营销模块-人群透镜与反脆弱.md",
    ),
    "demographic_middle_aged": KnowledgeEntry(
        id="demographic_middle_aged",
        title="社会中坚(35-50)消费心理",
        category="marketing",
        keywords=["社会中坚", "35-50", "品质", "健康", "圈子"],
        content="""社会中坚核心：家庭责任与社会地位稳固

主导引擎：权威、恐惧、虚荣、懒惰
喜欢：品质品牌、健康第一、为家人消费、圈子价值、可靠服务
讨厌：花里胡哨、风险不确定性、被打扰、被轻视专业性

策略：Mode C（信任、安全感）""",
        source_file="19-人性营销模块-人群透镜与反脆弱.md",
    ),
    "antifragile_strategies": KnowledgeEntry(
        id="antifragile_strategies",
        title="反脆弱五大策略",
        category="marketing",
        keywords=["反脆弱", "真实", "共创", "游戏", "惊喜"],
        content="""用户脱敏后的五大反脆弱策略：

1. 激进的真实：展示缺点、幕后、挣扎
2. 价值共鸣：表达功能外价值观，用行动支撑
3. 意义化游戏：游戏化结合成长和社交
4. 用户共创：让用户成为创造者
5. 惊喜与愉悦：标准服务外提供个性化善意""",
        source_file="19-人性营销模块-人群透镜与反脆弱.md",
    ),
    # ===== 20-情绪操盘 =====
    "expectation_gap": KnowledgeEntry(
        id="expectation_gap",
        title="低开高走：预期差模型",
        category="marketing",
        keywords=["低开高走", "预期", "惊喜", "体验"],
        content="""情感冲击力 = 最终体验 - 初始预期

四阶段：
1. 开盘：故意示弱，打破预期
2. 盘中：释放积极信号，扭转判断
3. 拉升：释放核心价值炸弹
4. 收盘：见好就收，锁定高位印象

外部表达：惊喜感营造。""",
        source_file="20-人性营销模块-情绪操盘与顺逆法则.md",
    ),
    "smooth_adverse_rules": KnowledgeEntry(
        id="smooth_adverse_rules",
        title="顺逆二元法则",
        category="marketing",
        keywords=["顺人性", "逆人性", "摩擦力", "忠诚"],
        content="""顺逆二元法则：

顺人性（引力）：利用向下的力量，减少用户能耗
- 适用：获取新用户、转化路径、高频低客单价

逆人性（升力）：施加有价值的摩擦力
- 适用：高端品牌、高粘性社群、延迟满足

顺逆结合：顺人性降低门槛，逆人性拉升高度。""",
        source_file="20-人性营销模块-情绪操盘与顺逆法则.md",
    ),
    "tension_certainty_surprise": KnowledgeEntry(
        id="tension_certainty_surprise",
        title="确定性与惊喜感的平衡",
        category="marketing",
        keywords=["确定性", "不确定性", "惊喜感", "安全感", "预期差"],
        content="""用户一边想要安全感，一边又会被惊喜打动。

真正稳的品牌要做两件事：
1. 核心价值足够确定：品质、服务、交付、承诺可预测
2. 体验触点保留惊喜：内容、互动、细节服务、包装体验有正向预期差

说白了，就是底盘要稳，触点要活。""",
        source_file="20-人性营销模块-情绪操盘与顺逆法则.md",
    ),
    "tension_imitation_authenticity": KnowledgeEntry(
        id="tension_imitation_authenticity",
        title="模仿欲望与真实认同",
        category="marketing",
        keywords=["模仿", "真实", "身份", "认同", "价值共鸣"],
        content="""很多消费一开始来自模仿，后来沉淀下来的忠诚却来自真实认同。

可以分两步走：
1. 先给用户一个向往身份，帮他入场
2. 再给用户一个真实立场，帮他留下

只靠模仿，用户容易追下一波风口；承接住真实认同，关系才会稳。""",
        source_file="20-人性营销模块-情绪操盘与顺逆法则.md",
    ),
    "tension_shortcut_meaning": KnowledgeEntry(
        id="tension_shortcut_meaning",
        title="捷径需求与意义感",
        category="marketing",
        keywords=["捷径", "意义", "省事", "故事", "长期忠诚"],
        content="""用户会被省事吸引，也会被意义留住。

战术上要给捷径：降低理解、决策和行动成本。
战略上要给意义：让消费不只是消费，而是价值表达和身份连接。

只给捷径，用户会用完即走；给了意义，用户才会长期留下。""",
        source_file="20-人性营销模块-情绪操盘与顺逆法则.md",
    ),
    # ===== 21-社会原力 =====
    "social_identity": KnowledgeEntry(
        id="social_identity",
        title="身份认同营销",
        category="marketing",
        keywords=["身份认同", "部落", "我们", "归属感"],
        content="""社会原力一：身份认同

核心逻辑：区分“我们”和“他们”
应用：
1. 创造部落图腾（Logo、口号、黑话）
2. 定义共同敌人
3. 赋予优越感

外部表达：社群运营、用户归属感。""",
        source_file="21-人性营销模块-社会原力与实战工具.md",
    ),
    "social_order": KnowledgeEntry(
        id="social_order",
        title="秩序构建与共同叙事",
        category="marketing",
        keywords=["秩序", "地位", "叙事", "故事", "价值观"],
        content="""社会原力二：秩序构建
- 群体需要内部秩序和层级
- 贩卖地位、设计成长路径、提供确定性

社会原力三：共同叙事
- 群体因共同相信的故事而凝聚
- 成为意义提供者，创造创始神话，将用户写进故事""",
        source_file="21-人性营销模块-社会原力与实战工具.md",
    ),
    "social_resources": KnowledgeEntry(
        id="social_resources",
        title="资源分配与存续扩张",
        category="marketing",
        keywords=["资源", "公平", "公益", "领导者", "生态"],
        content="""社会原力四：资源分配
- 群体对公平正义敏感
- 行善式营销、诉诸价格公平、拥抱社会议题

社会原力五：存续与扩张
- 群体追求活下去和变强
- 彰显领导者地位、构建生态系统、贩卖未来感""",
        source_file="21-人性营销模块-社会原力与实战工具.md",
    ),
    "price_fairness": KnowledgeEntry(
        id="price_fairness",
        title="价格公平与资源分配叙事",
        category="marketing",
        keywords=["价格公平", "公平", "割韭菜", "资源分配", "价格透明"],
        content="""很多用户不怕花钱，怕的是觉得自己被坑了、被割了、被不公平对待了。

价格公平叙事要解决三件事：
1. 价格为什么是这个价格
2. 用户到底为哪些价值付费
3. 品牌有没有利用信息差赚不该赚的钱

把定价逻辑讲清楚，用户的防备感才会降下来。""",
        source_file="21-人性营销模块-社会原力与实战工具.md",
    ),
    "ecosystem_future": KnowledgeEntry(
        id="ecosystem_future",
        title="生态系统与未来感",
        category="marketing",
        keywords=["生态", "未来感", "扩张", "体系", "长期布局"],
        content="""存续与扩张，不只是做大销量，更是让用户感觉你有未来。

常见做法：
1. 构建生态：从单点产品变成整套解决方案
2. 强化连接：不同产品互相带动
3. 贩卖未来感：让用户觉得你代表下一阶段

当用户感觉自己加入的是一个会持续扩张的体系，品牌的长期信任就更容易建立。""",
        source_file="21-人性营销模块-社会原力与实战工具.md",
    ),
    "aida_map": KnowledgeEntry(
        id="aida_map",
        title="用户决策路径植入地图",
        category="marketing",
        keywords=["AIDA", "决策路径", "认知", "兴趣", "欲望", "行动"],
        content="""AIDA 不是理论摆设，而是把用户从“看到”一路带到“行动”的路径图。

四步可以这样理解：
1. 认知 Awareness：先让用户知道你，常用权威、从众、曝光
2. 兴趣 Interest：让用户愿意继续看，常用好奇、故事、反差
3. 欲望 Desire：让用户从“还行”变成“我想要”，常用稀缺、锚定、身份感
4. 行动 Action：临门一脚，常用损失规避、互惠、限时推动

如果转化总掉在中间，就去看是哪一段武器没植进去。""",
        source_file="21-人性营销模块-社会原力与实战工具.md",
    ),
    "launch_checklist": KnowledgeEntry(
        id="launch_checklist",
        title="营销上线前自查清单",
        category="marketing",
        keywords=["自查", "上线前", "清单", "转化路径", "风险"],
        content="""营销上线前，至少过三遍这张清单：

1. 人性洞察有没有打准：核心信息有没有刺进用户真正驱动力
2. 转化路径够不够顺：流程麻不麻烦，犹豫点有没有推动设计
3. 风险和道德有没有踩线：是不是在透支信任，是不是承诺了做不到的事

很多活动不是死在创意不够，而是死在上线前没做最后一次冷静检查。""",
        source_file="21-人性营销模块-社会原力与实战工具.md",
    ),
    "practical_tools": KnowledgeEntry(
        id="practical_tools",
        title="三个实战工具",
        category="marketing",
        keywords=["工具", "AIDA", "自查", "决策路径"],
        content="""三个实战工具：

1. 产品-人性驱动力匹配工作表
   产品核心功能 -> 匹配的八宗罪 -> 原因解释

2. 用户决策路径植入地图 (AIDA)
   认知->权威/从众 | 兴趣->好奇/故事 | 欲望->稀缺/嫉妒/锚定 | 行动->损失规避/互惠

3. 营销活动上线前自查清单
   人性洞察：核心信息刺入驱动力？第一秒情绪？定价利用锚定/损失规避？
   转化路径：流程够“懒”？犹豫环节有推动力？有从众信号？
   风险与道德：激发欲望 vs 操纵焦虑？承诺100%兑现？""",
        source_file="21-人性营销模块-社会原力与实战工具.md",
    ),
}
