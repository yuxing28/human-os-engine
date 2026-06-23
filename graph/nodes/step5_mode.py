"""
Human-OS Engine - LangGraph 节点实现

对应总控规格的 Step 0-9。
"""

from graph.state import GraphState
from schemas.enums import Mode


def step5_mode_selection(state: GraphState) -> GraphState:
    """Step 5：模式选择"""
    context = state["context"]
    if state.get("skip_to_end", False):
        return {**state, "context": context}
    priority = state.get("priority")

    from modules.L1.operation_modes import select_mode

    # 调用模式选择模块
    selected = select_mode(
        context.self_state.is_stable, 
        context.user, 
        context.goal, 
        priority, 
        context.user.input_type.value if hasattr(context.user.input_type, 'value') else str(context.user.input_type)
    )

    dialogue_task = getattr(context, "dialogue_task", "clarify")
    if dialogue_task == "contain":
        selected = "A"
    elif dialogue_task == "reflect" and selected == "A":
        selected = "B"
    elif dialogue_task == "advance" and selected == "A":
        selected = "A→B"

    lead_mode = selected.split("→")[0].split("+")[0]

    # 更新 context 中的 current_strategy
    if "→" in selected:
        # 串联模式：解析为序列
        mode_strs = selected.split("→")
        context.current_strategy.mode_sequence = [Mode(m) for m in mode_strs]
        context.current_strategy.current_step_index = 0
    else:
        # 单一或并行模式
        context.current_strategy.mode_sequence = []
        context.current_strategy.current_step_index = 0

    context.current_strategy.stage = ""
    context.self_state.energy_mode = Mode(lead_mode)

    # 更新能量分配
    context.update_energy_allocation(lead_mode)

    return {**state, "context": context, "selected_mode": selected}
