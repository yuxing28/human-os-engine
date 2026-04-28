"""
Human-OS Engine - L5 能量系统知识库

基于 24-能量系统模块 和 25-能量系统模块 的内容。
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


ENERGY_KNOWLEDGE: dict[str, KnowledgeEntry] = {
    "energy_management": KnowledgeEntry(
        id="energy_management",
        title="注意力分配与能量系统",
        category="energy",
        keywords=["能量", "疲惫", "累", "精力", "恢复", "注意力"],
        content="""能量系统看三层：

1. 内在：身体、情绪、认知、意志
2. 外层：表现力、拒绝能力、边界感
3. 外在：环境、变数、信息流、人际反馈

核心原则只有一句：注意力是最稀缺的能源，流到哪里，哪里就变大。""",
        source_file="24-能量系统模块-注意力分配与模式策略.md",
    ),
    "mode_a_recovery": KnowledgeEntry(
        id="mode_a_recovery",
        title="向内恢复阶段",
        category="energy",
        keywords=["恢复", "学习", "备考", "调整", "向内", "专注"],
        content="""当你需要恢复、学习、调整、重新站稳时，就该进入向内恢复阶段。

精力安排建议：
1. 大头放在身心恢复和基本秩序
2. 外界连接先降下来
3. 环境只保留最必要的监测

说白了，就是先把自己养回来，再谈扩张。""",
        source_file="24-能量系统模块-注意力分配与模式策略.md",
    ),
    "mode_b_hunting": KnowledgeEntry(
        id="mode_b_hunting",
        title="对外拓展阶段",
        category="energy",
        keywords=["销售", "谈判", "推广", "机会", "拓展", "短期目标"],
        content="""当你要成交、谈判、抢窗口、推项目时，就是对外拓展阶段。

这个阶段的重点不是拼命燃烧，而是：
1. 保持基本状态别崩
2. 把表现力和行动力拉起来
3. 更主动地感知外部机会

但不能长期停在这里，不然很容易耗竭。""",
        source_file="24-能量系统模块-注意力分配与模式策略.md",
    ),
    "mode_c_cocreation": KnowledgeEntry(
        id="mode_c_cocreation",
        title="深度合作阶段",
        category="energy",
        keywords=["合作", "团队", "伙伴", "亲密关系", "共创", "长期关系"],
        content="""当你要做长期协作、深度关系、共同创造时，就该进入深度合作阶段。

关键不是一味付出，而是：
1. 自己的核心不能丢
2. 外层连接要更真诚也更稳定
3. 双方要有价值对齐，不然很快失衡

深度合作不是讨好，而是有边界的连接。""",
        source_file="24-能量系统模块-注意力分配与模式策略.md",
    ),
    "mode_switching": KnowledgeEntry(
        id="mode_switching",
        title="模式切换原则",
        category="energy",
        keywords=["切换", "模式", "阶段", "节奏", "安排"],
        content="""模式切换别靠感觉乱切，先看目标，再看状态。

原则：
1. 有恢复需求，先回向内恢复阶段
2. 有明确窗口和短期目标，再进对外拓展阶段
3. 要长期合作，先确认价值对齐，再进深度合作阶段
4. 对外拓展不能常驻，定期必须回到向内恢复阶段""",
        source_file="24-能量系统模块-注意力分配与模式策略.md",
    ),
    "burnout_recovery": KnowledgeEntry(
        id="burnout_recovery",
        title="崩溃修复总路线",
        category="energy",
        keywords=["崩溃", "burnout", "耗竭", "倦怠", "恢复"],
        content="""崩溃不是一下子发生的，通常是三步走：

1. 注意力被劫持：一直刷、一直焦虑、一直被外界带着跑
2. 外层破损：不会拒绝、边界变薄、别人一句话就扎进来
3. 内在枯竭：失眠、崩溃、没行动力、开始自我攻击

修复顺序也别反：
先收回注意力，再修边界，最后养内在。""",
        source_file="25-能量系统模块-崩溃模型与修复路径.md",
    ),
    "attention_hijack": KnowledgeEntry(
        id="attention_hijack",
        title="注意力被劫持",
        category="energy",
        keywords=["刷手机", "分心", "焦虑", "讨好", "停不下来", "注意力被劫持"],
        content="""如果你总在刷屏、担心别人怎么看、一直盯着外部反馈，那大概率不是懒，是注意力已经被外界劫持了。

这个阶段的核心问题不是能力差，而是：
1. 精力全漏到外面去了
2. 当下做不了事
3. 越焦虑越想抓外界信息，越抓越乱

第一步别急着鸡自己，先把注意力往回收。""",
        source_file="25-能量系统模块-崩溃模型与修复路径.md",
    ),
    "outer_damage": KnowledgeEntry(
        id="outer_damage",
        title="外层破损与边界失守",
        category="energy",
        keywords=["不敢拒绝", "边界", "老好人", "玻璃心", "破防", "讨好"],
        content="""外层破损的典型表现是：
1. 明明不想答应，却还是答应
2. 别人一句话就能把你带跑
3. 总在接别人的情绪和要求

这时候不是去逼自己更坚强，而是先修边界：
学会拒绝、学会过滤、学会把不属于自己的东西还回去。""",
        source_file="25-能量系统模块-崩溃模型与修复路径.md",
    ),
    "inner_exhaustion": KnowledgeEntry(
        id="inner_exhaustion",
        title="内在枯竭与慢恢复",
        category="energy",
        keywords=["失眠", "抑郁", "崩溃", "枯竭", "没行动力", "身心疲惫"],
        content="""如果已经长期失眠、身体出问题、完全没行动力，那就不是简单累了，而是内在已经透支。

这个阶段最忌讳两件事：
1. 继续硬撑
2. 还要求自己像正常状态那样高效

真正有效的做法，是把目标降到最小，先保睡眠、保身体、保基本秩序，再慢慢恢复。""",
        source_file="25-能量系统模块-崩溃模型与修复路径.md",
    ),
    "attention_recovery": KnowledgeEntry(
        id="attention_recovery",
        title="收回注意力",
        category="energy",
        keywords=["收回注意力", "删app", "关通知", "安静空间", "可控", "隔离"],
        content="""收回注意力，不是喊口号，是先做这三件事：

1. 物理隔离：限制社交媒体、关通知、设无手机时间
2. 认知分流：写下哪些你能控制，哪些你控制不了
3. 环境减噪：换到更安静、更整洁、更少刺激的空间

先把信息洪水关小，脑子才有机会重新安静下来。""",
        source_file="25-能量系统模块-崩溃模型与修复路径.md",
    ),
    "shield_rebuild": KnowledgeEntry(
        id="shield_rebuild",
        title="修复外层与边界感",
        category="energy",
        keywords=["拒绝", "过滤", "边界感", "底线", "保护自己"],
        content="""修边界不是变冷漠，而是把你的精力守住。

可做三件事：
1. 练习简单说不，不解释太多
2. 不是所有评价都接，不是所有消息都回
3. 提前写清楚自己的底线和优先级

边界感一旦稳起来，情绪就不会老被别人牵着走。""",
        source_file="25-能量系统模块-崩溃模型与修复路径.md",
    ),
    "inner_nourishment": KnowledgeEntry(
        id="inner_nourishment",
        title="滋养内在与重启系统",
        category="energy",
        keywords=["睡眠", "运动", "饮食", "小目标", "恢复行动力", "滋养"],
        content="""当最乱的阶段过去后，真正的恢复要回到身体、情绪和秩序上。

基础动作：
1. 睡眠先稳住
2. 规律运动和吃饭
3. 允许情绪存在，不压死自己
4. 目标缩小到今天就能完成的一步

恢复不是突然满血，而是每天把系统慢慢重启。""",
        source_file="25-能量系统模块-崩溃模型与修复路径.md",
    ),
    "energy_diagnosis": KnowledgeEntry(
        id="energy_diagnosis",
        title="能量自诊三问",
        category="energy",
        keywords=["诊断", "自查", "三问", "能量状态", "现在怎么样"],
        content="""快速看自己现在在哪一段，只问三件事：

1. 注意力主要在内在，还是全跑到外面了？
2. 你现在还能拒绝、过滤、守边界吗？
3. 你睡眠、精力、行动力还稳吗？

如果三项都在掉，就别再逼自己往前冲了，先进入修复流程。""",
        source_file="25-能量系统模块-崩溃模型与修复路径.md",
    ),
}
