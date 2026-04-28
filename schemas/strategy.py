"""
Human-OS Engine - 策略相关数据结构

对应总控规格中的策略、武器、组合等。
"""

from pydantic import BaseModel


class StrategyPlan(BaseModel):
    """策略方案"""
    mode: str = ""  # 如 "A", "B", "C", "A+B", "A→B→C"
    combo_name: str = ""  # 如 "贪婪+恐惧"
    stage: str = ""  # 如 "钩子", "放大", "降门槛"
    description: str = ""
    fallback: str = ""  # 备选组合
    weapons: list[str] = []  # 动态生成的武器序列
    tone: str = ""  # 语气基调
