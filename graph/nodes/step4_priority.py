"""
Human-OS Engine - LangGraph 节点实现

对应总控规格的 Step 0-9。
"""

from graph.state import GraphState


def step4_priority(state: GraphState) -> GraphState:
    """Step 4：优先级排序"""
    context = state["context"]
    if state.get("skip_to_end", False):
        return {**state, "context": context}

    from modules.L1.priority_rules import get_priority

    # 调用优先级规则模块
    energy_pressure = 0.0
    for item in reversed(context.history):
        if "energy_pressure" in item.metadata:
            energy_pressure = float(item.metadata["energy_pressure"])
            break

    priority = get_priority(
        context.user,
        context.goal,
        self_stable=context.self_state.is_stable,
        energy_pressure=energy_pressure,
        desire_relations=context.desire_relations,
    )

    return {**state, "context": context, "priority": priority}
