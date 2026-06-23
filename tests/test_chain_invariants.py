import importlib

from graph.builder import build_graph
from schemas.context import Context

step9_module = importlib.import_module("graph.nodes.step9_feedback")


def test_main_chain_is_linear_and_nonconditional():
    """主链必须固定顺序，且不允许条件跳边。"""
    graph = build_graph().get_graph()
    edges = {(edge.source, edge.target): edge.conditional for edge in graph.edges}

    expected_pairs = {
        ("__start__", "step0"),
        ("step0", "step1"),
        ("step1", "step1_5"),
        ("step1_5", "step2"),
        ("step2", "step3"),
        ("step3", "step4"),
        ("step4", "step5"),
        ("step5", "step6"),
        ("step6", "step7"),
        ("step7", "step8"),
        ("step8", "step9"),
        ("step9", "__end__"),
    }

    assert set(edges.keys()) == expected_pairs
    assert all(not conditional for conditional in edges.values())


def test_step9_persists_output_layers_to_system_history(monkeypatch):
    """Step9 必须把 Step8 的 output_layers 落盘到最后一条 system 历史。"""
    import modules.memory as memory_module

    monkeypatch.setattr(step9_module, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_module, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_module, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_module, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_module, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(step9_module, "_extract_session_notes", lambda context, user_input, system_rounds: None)

    monkeypatch.setattr(memory_module, "store_memory", lambda **kwargs: None)
    monkeypatch.setattr(memory_module, "extract_important_facts", lambda user_input, output, existing: None)
    monkeypatch.setattr(memory_module, "retrieve_memory", lambda session_id, user_input, limit=5: [])

    context = Context(session_id="test-chain-invariants")
    context.add_history("user", "先帮我看下这个问题")
    context.output = "我们先把目标拆成今天能做的一步。"
    output_layers = {
        "user_visible": context.output,
        "debug_info": "模式=A | 武器=['共情'] | 场景=sales",
        "internal": "五感=无 | 压制={}",
    }

    result = step9_module.step9_feedback(
        {
            "context": context,
            "user_input": "先帮我看下这个问题",
            "output_layers": output_layers,
        }
    )

    last_item = result["context"].history[-1]
    assert last_item.role == "system"
    assert last_item.metadata.get("output_layers") == output_layers
