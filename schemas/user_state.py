"""
Human-OS Engine - 用户状态相关数据结构

对应总控规格第二章中的 user 对象。
"""

from pydantic import BaseModel, Field
from schemas.enums import (
    EmotionType,
    MotiveType,
    DualCoreState,
    ResistanceType,
    InputType,
    TrustLevel,
    AttentionHijacker,
)


class Emotion(BaseModel):
    """用户情绪状态 - user.emotion"""
    type: EmotionType = EmotionType.CALM
    intensity: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class Desires(BaseModel):
    """八宗罪欲望权重 - user.desires（归一化后 0-1）"""
    fear: float = Field(default=0.0, ge=0.0, le=1.0)
    greed: float = Field(default=0.0, ge=0.0, le=1.0)
    sloth: float = Field(default=0.0, ge=0.0, le=1.0)
    envy: float = Field(default=0.0, ge=0.0, le=1.0)
    pride: float = Field(default=0.0, ge=0.0, le=1.0)
    lust: float = Field(default=0.0, ge=0.0, le=1.0)
    gluttony: float = Field(default=0.0, ge=0.0, le=1.0)
    wrath: float = Field(default=0.0, ge=0.0, le=1.0)

    def get_dominant(self) -> tuple[str, float]:
        """获取主导欲望"""
        desires_dict = self.model_dump()
        max_key = max(desires_dict, key=desires_dict.get)
        return max_key, desires_dict[max_key]


class DualCore(BaseModel):
    """双核状态 - user.dual_core"""
    state: DualCoreState = DualCoreState.SYNC
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class Attention(BaseModel):
    """注意力状态 - user.attention"""
    focus: float = Field(default=0.7, ge=0.0, le=1.0)
    hijacked_by: AttentionHijacker = AttentionHijacker.NONE


class Resistance(BaseModel):
    """阻力状态 - user.resistance"""
    type: ResistanceType = ResistanceType.NONE
    intensity: float = Field(default=0.0, ge=0.0, le=1.0)
    original_goal: str | None = None


class UserState(BaseModel):
    """完整用户状态"""
    emotion: Emotion = Field(default_factory=Emotion)
    motive: MotiveType = MotiveType.LIFE_EXPECTATION
    desires: Desires = Field(default_factory=Desires)
    dual_core: DualCore = Field(default_factory=DualCore)
    attention: Attention = Field(default_factory=Attention)
    resistance: Resistance = Field(default_factory=Resistance)
    input_type: InputType = InputType.EMOTIONAL
    trust_level: TrustLevel = TrustLevel.MEDIUM
    # P1-5: 身份轴 — 关系位置
    relationship_position: str = "未识别"  # 上级-下级 / 对等-竞争 / 服务-客户 / 亲密-依赖 / 陌生-试探 / 对等-合作
