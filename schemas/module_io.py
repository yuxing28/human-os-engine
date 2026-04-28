"""
Human-OS Engine - 模块间标准输入输出接口

统一定义 L0-L5 各模块的输入输出类型。
"""

from pydantic import BaseModel, Field
from schemas.user_state import Desires


# ===== L2 识别模块 IO =====

class EmotionResult(BaseModel):
    """情绪识别结果 - 27-协作温度识别"""
    type: str = "平静"
    intensity: float = 0.5
    confidence: float = 0.5
    motive: str = "生活期待"


class DesiresResult(BaseModel):
    """欲望识别结果 - 06-八宗罪关键词识别"""
    desires: Desires
    confidence: float = 0.5
    raw_scores: dict[str, int] = Field(default_factory=dict)  # 原始得分（归一化前）
    relations: dict[str, list[dict]] = Field(default_factory=dict)  # 压制/转化关系分析结果


class DualCoreResult(BaseModel):
    """双核状态识别结果"""
    state: str = "同频"
    dominant: str = "理性核"
    confidence: float = 0.5
    evidence: list[str] = Field(default_factory=list)
