"""
Human-OS Engine 3.0 — 场景配置数据模型

定义场景配置文件的 Pydantic Schema，确保配置格式正确、类型安全。
"""

from pydantic import BaseModel, Field, validator
from typing import Optional

class GranularGoal(BaseModel):
    """细粒度目标定义"""
    granular_goal: str = Field(..., description="目标唯一标识，如 'overcome_rejection'")
    display_name: str = Field(..., description="目标显示名称，如 '克服拒绝'")
    description: str = Field("", description="目标详细描述")
    keywords: list[str] = Field(default_factory=list, description="识别关键词列表")
    emotion_hints: list[str] = Field(default_factory=list, description="情绪辅助信号")
    default_mode: str = Field(..., description="默认模式，如 'A', 'B', 'A→B'")
    strategy_preferences: list[dict] = Field(default_factory=list, description="策略偏好列表 [{'combo': '...', 'weight': 0.8}]")
    forbidden_weapons: list[str] = Field(default_factory=list, description="武器黑名单")
    success_criteria: dict = Field(default_factory=dict, description="成功标准")

class SceneConfig(BaseModel):
    """场景基础配置"""
    scene_id: str = Field(..., description="场景唯一标识，如 'sales'")
    version: str = Field(..., description="配置版本号")
    description: str = Field("", description="场景描述")
    goal_taxonomy: list[GranularGoal] = Field(default_factory=list, description="目标分类体系")
    default_strategy_weights: dict = Field(default_factory=dict, description="默认策略权重")
    weapon_blacklist: dict = Field(default_factory=dict, description="武器黑名单 {condition: [weapons]}")
    eval_weights: dict = Field(default_factory=dict, description="评估指标权重")

class EvolvedConfig(BaseModel):
    """场景进化数据"""
    base_version: str = Field(..., description="对应的基础配置版本")
    evolved_at: str = Field(..., description="进化时间")
    iterations: int = Field(0, description="训练迭代次数")
    strategy_weights: dict = Field(default_factory=dict, description="进化后的策略权重")
    weapon_blacklist_additions: dict = Field(default_factory=dict, description="新增的武器黑名单")
    performance_metrics: dict = Field(default_factory=dict, description="性能指标")
