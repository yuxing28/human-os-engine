import importlib

from schemas.context import Context
import modules.memory as memory_mod


step9_mod = importlib.import_module("graph.nodes.step9_feedback")


def _disable_step9_side_effects(monkeypatch):
    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_extract_session_notes", lambda context, user_input, round_num: None)


def test_step9_deduplicates_repeated_raw_conversation_memory(tmp_path, monkeypatch):
    _disable_step9_side_effects(monkeypatch)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    monkeypatch.setattr(memory_mod, "_memory_manager", manager)

    context = Context(session_id="integration-mem-dedupe")
    context.output = "我听到了，我们先把预算风险拆开，一个个确认。"
    state = {
        "context": context,
        "user_input": "老板担心预算和风险，我现在怎么推进？",
    }

    step9_mod.step9_feedback(state)
    step9_mod.step9_feedback(state)

    memories = [
        m
        for m in manager.get_recent_memories("integration-mem-dedupe", limit=10)
        if m.memory_type == "conversation"
    ]
    contents = [m.content for m in memories]

    assert len(memories) == 2
    assert contents.count("用户: 老板担心预算和风险，我现在怎么推进？") == 1
    assert contents.count("系统: 我听到了，我们先把预算风险拆开，一个个确认。") == 1
