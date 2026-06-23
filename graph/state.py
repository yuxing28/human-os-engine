"""
Human-OS Engine - LangGraph 图状态定义

扩展 Context 为 LangGraph 的图状态。
"""

from typing import TypedDict, Any, NotRequired
from schemas.context import Context
from schemas.strategy import StrategyPlan


class GraphState(TypedDict):
    """
    LangGraph 图状态

    节点间传递的数据结构。
    """
    context: Context  # 全局 Context
    user_input: str  # 当前用户输入
    output: str  # 系统输出
    priority: dict[str, Any] | None  # Step 4 优先级结果
    selected_mode: str | None  # Step 5 选中的模式
    strategy_plan: Any | None  # Step 6 策略方案
    weapons_used: list[dict] | None  # Step 7 武器列表
    skip_to_end: bool  # Step 3 崩溃时跳过后续步骤
    low_confidence: bool  # Step 1 低置信度标记
    output_layers: NotRequired[dict[str, Any]]  # Step 8 输出分层元数据，供 Step 9 落盘
    step_timings_ms: NotRequired[dict[str, int]]  # Step2/6/8 等关键节点耗时（毫秒）
