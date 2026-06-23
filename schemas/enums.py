"""
Human-OS Engine - 枚举类型定义

对应总控规格中的所有枚举字段。
"""

from enum import Enum


# ===== 用户相关枚举 =====

class EmotionType(str, Enum):
    """情绪类型 - 对应 user.emotion.type"""
    FRUSTRATED = "挫败"
    CONFUSED = "迷茫"
    IMPATIENT = "急躁"
    CALM = "平静"
    ANGRY = "愤怒"


class MotiveType(str, Enum):
    """动机类型 - 对应 user.motive"""
    INSPIRATION = "灵感兴奋"
    LIFE_EXPECTATION = "生活期待"
    FEAR_AVOIDANCE = "回避恐惧"
    STRESS_PASSIVE = "压力被动"


class DualCoreState(str, Enum):
    """双核状态 - 对应 user.dual_core.state"""
    CONFLICT = "对抗"
    SYNERGY = "协同"
    SYNC = "同频"
    RATIONALIZATION = "合理化"


class ResistanceType(str, Enum):
    """阻力类型 - 对应 user.resistance.type"""
    FEAR = "恐惧"
    SLOTH = "懒惰"
    PRIDE = "傲慢"
    ENVY = "嫉妒"
    WRATH = "愤怒"
    GREED = "贪婪"
    NONE = "null"


class InputType(str, Enum):
    """输入类型 - 对应 user.input_type（元控制器输出）"""
    EMOTIONAL = "情绪表达"
    CONSULTATION = "问题咨询"
    SCENARIO = "场景描述"
    MIXED = "混合"


class TrustLevel(str, Enum):
    """信任等级 - 对应 user.trust_level"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AttentionHijacker(str, Enum):
    """注意力劫持源 - 对应 user.attention.hijacked_by"""
    FEAR = "恐惧"
    ANGER = "愤怒"
    PRIDE = "傲慢"
    INFO_OVERLOAD = "信息过载"
    DESIRE = "欲望"
    NONE = "null"


# ===== 目标相关枚举 =====

class GoalType(str, Enum):
    """目标类型 - 对应 goal.current.type"""
    BENEFIT = "利益价值"
    EMOTION = "情绪价值"
    MIXED = "混合"


class GoalSource(str, Enum):
    """目标来源 - 对应 goal.current.source"""
    USER_EXPLICIT = "user_explicit"
    SYSTEM_INFERRED = "system_inferred"


# ===== 策略相关枚举 =====

class Mode(str, Enum):
    """运作模式"""
    A = "A"  # 向内·进化
    B = "B"  # 向外·狩猎
    C = "C"  # 超越·共创


class FeedbackType(str, Enum):
    """反馈类型 - 对应 last_feedback"""
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"


class WeaponType(str, Enum):
    """武器类型"""
    ATTACK = "攻击型"
    DEFENSE = "防御型"
    MILD = "温和型"


class FiveLayer(str, Enum):
    """五层结构层级"""
    L1_IMMEDIATE = "即时反应"
    L2_UNDERSTANDING = "理解确认"
    L3_EMPATHY = "共情支持"
    L4_INQUIRY = "具体追问"
    L5_GUIDANCE = "方向引导"


class StrategyCombo(str, Enum):
    """策略组合名称（类型安全，避免字符串拼写错误）"""
    # 钩子阶段
    GREED_FEAR = "贪婪+恐惧"
    CURIOSITY_SCARCITY = "好奇+稀缺"
    RECIPROCITY_SLOTH = "互惠+懒惰"
    AUTHORITY_BANDWAGON = "权威+从众"
    CURIOSITY_VALUE = "好奇+价值"
    # 放大阶段
    PRIDE_ENVY = "傲慢+嫉妒"
    LUST_GLUTTONY = "色欲+暴食"
    AUTHORITY_CONSENSUS = "权威+共识"
    # 降门槛阶段
    SLOTH_RECIPROCITY = "懒惰+互惠"
    SLOTH_LOSS_AVERSION = "懒惰+损失规避"
    # 升维阶段
    VISION_DIGNITY = "愿景+尊严"
    LOVE_PEACE = "大爱+宁静"
    EXCELLENCE_REVOLUTION = "卓越+革命"
    # 防御阶段
    SILENCE_SUBMISSION = "沉默+示弱"
    TRANSFER_PRINCIPLE = "转移话题+原则"
    COUNTER_LABEL = "反问+贴标签"
    CORRECT_BOUNDARY = "纠正+设界"
    ACTIVATE_FEAR_SATISFY_PRIDE = "激活恐惧+满足傲慢"
    # 注意力管理
    FOCUS_PROTECT = "聚焦+保护"
    GUIDE_ALIGN = "引导+同频"
    # B2B 专属
    AUTHORITY_CASE = "权威+案例"
    CERTAINTY_CASE = "提供确定性+案例证明"


# ===== 自身状态枚举（已移至 schemas/context.py 的 SelfState BaseModel） =====
