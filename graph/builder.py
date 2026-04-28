"""
Human-OS Engine - LangGraph 图构建器

构建总控大脑的 9 步执行流程。
"""

import time

from langgraph.graph import StateGraph, END
from graph.state import GraphState


def _timed_node(step_name: str, node_fn):
    """给关键节点包一层耗时记录，写入 step_timings_ms。"""
    def _wrapped(state: GraphState):
        started = time.time()
        result = node_fn(state)
        elapsed_ms = int((time.time() - started) * 1000)

        prior = state.get("step_timings_ms", {}) or {}
        merged = dict(prior)
        merged[step_name] = elapsed_ms

        if isinstance(result, dict):
            result_prior = result.get("step_timings_ms", {}) or {}
            if isinstance(result_prior, dict):
                merged.update(result_prior)
            result["step_timings_ms"] = merged
        return result

    return _wrapped


def build_graph() -> StateGraph:
    """
    构建 Human-OS Engine 的 LangGraph 工作流

    对应总控规格的 Step 0-9 流程。
    """
    from graph.nodes import (
        step0_receive_input,
        step1_identify,
        step1_5_meta_controller,
        step2_goal_detection,
        step3_self_check,
        step4_priority,
        step5_mode_selection,
        step6_strategy_generation,
        step7_weapon_selection,
        step8_execution,
        step9_feedback,
    )

    # 创建图
    graph = StateGraph(GraphState)

    # 添加节点
    graph.add_node("step0", step0_receive_input)
    graph.add_node("step1", step1_identify)
    graph.add_node("step1_5", step1_5_meta_controller)
    graph.add_node("step2", _timed_node("step2", step2_goal_detection))
    graph.add_node("step3", step3_self_check)
    graph.add_node("step4", step4_priority)
    graph.add_node("step5", step5_mode_selection)
    graph.add_node("step6", _timed_node("step6", step6_strategy_generation))
    graph.add_node("step7", step7_weapon_selection)
    graph.add_node("step8", _timed_node("step8", step8_execution))
    graph.add_node("step9", step9_feedback)

    # 添加入口点
    graph.set_entry_point("step0")

    # 主链固定顺序：Step 0-9 不跳步
    graph.add_edge("step0", "step1")
    graph.add_edge("step1_5", "step2")
    graph.add_edge("step2", "step3")
    graph.add_edge("step1", "step1_5")
    graph.add_edge("step3", "step4")
    graph.add_edge("step4", "step5")
    graph.add_edge("step5", "step6")
    graph.add_edge("step6", "step7")
    graph.add_edge("step7", "step8")
    graph.add_edge("step8", "step9")
    graph.add_edge("step9", END)

    # 编译图
    return graph.compile()
