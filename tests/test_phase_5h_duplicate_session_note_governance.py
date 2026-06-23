import statistics
from pathlib import Path

import pytest

import modules.memory as memory_mod
from graph.nodes.step9_feedback import step9_feedback
from modules.memory import MemoryManager, SessionMemory, get_memory_manager, get_session_context, get_session_memory, get_session_note_stats
from schemas.context import Context


class SceneStub:
    def __init__(self, scene_id: str):
        self.scene_id = scene_id


@pytest.fixture
def isolated_memory(tmp_path, monkeypatch):
    session_store = SessionMemory(str(tmp_path / "sessions"))
    memory_store = MemoryManager(str(tmp_path / "memory"))
    monkeypatch.setattr(memory_mod, "_session_memory", session_store)
    monkeypatch.setattr(memory_mod, "_memory_manager", memory_store)
    return session_store, memory_store


def _run_step9_turn(
    session_id: str,
    *,
    user_input: str,
    output: str,
    scene: str = "sales",
    turn_load_level: str = "standard",
    step8_mode: str = "full",
    runtime_trace: dict | None = None,
):
    context = Context(session_id=session_id)
    context.scene_config = SceneStub(scene)
    context.primary_scene = scene
    context.output = output
    state = {
        "context": context,
        "user_input": user_input,
        "system_rounds": max(1, len(context.history) + 1),
        "runtime_trace": {
            "turn_load_level": turn_load_level,
            "step8_mode": step8_mode,
            **(runtime_trace or {}),
        },
    }
    result = step9_feedback(state)
    return result["context"], getattr(result["context"], "runtime_trace", {}) or {}


def test_5h_preference_duplicate_write_governance(isolated_memory):
    session_id = "5h-pref"
    variants = [
        "以后直接一点，先给结论。",
        "别绕，默认先说结论。",
        "少铺垫，直接给可执行步骤。",
        "不要总反问，先把答案给我。",
        "以后都短一点，先说重点。",
    ]
    for index in range(30):
        user_input = variants[index % len(variants)]
        output = "结论先说：先给结果，再补两步执行法，别反问。"
        context, trace = _run_step9_turn(
            session_id,
            user_input=user_input,
            output=output,
            scene="management",
            turn_load_level="standard",
        )
    stats = get_session_note_stats(session_id)
    session_context = get_session_context(session_id, limit=5)
    memories = get_memory_manager()._memories.get(session_id, [])
    preference_memories = [m for m in memories if m.memory_type == "preference"]

    assert stats["count"] <= 8
    assert stats["duplicate_score"] <= 0.35
    assert stats["compaction_needed"] is False
    assert len(preference_memories) <= 2
    assert len(session_context) < 900
    assert trace.get("session_note_duplicate_score", 0) <= 0.35


def test_5h_project_state_latest_wins_and_next_pickup_not_repeated(isolated_memory):
    session = get_session_memory()
    session_id = "5h-state"
    first = session.add_note(
        session_id,
        1,
        "world_state",
        "场景: sales | 局面: 客户压价 | 判断: 先守价格 | 下一轮: 先守价格",
        {
            "scene_id": "sales",
            "situation_stage": "压价",
            "progress_state": "继续推进",
            "commitment_state": "已形成方向",
            "next_turn_focus": "先守价格",
        },
    )
    second = session.add_note(
        session_id,
        2,
        "world_state",
        "场景: sales | 局面: 可以让一点 | 判断: 但不能超过5% | 下一轮: 先谈服务交换",
        {
            "scene_id": "sales",
            "situation_stage": "修正策略",
            "progress_state": "继续推进",
            "commitment_state": "已修正",
            "next_turn_focus": "先谈服务交换",
        },
    )
    session.add_note(
        session_id,
        2,
        "action_loop",
        "动作闭环: 推进: 继续推进 | 承诺: 已修正 | 下一轮: 先谈服务交换",
        {
            "scene_id": "sales",
            "progress_state": "继续推进",
            "commitment_state": "已修正",
            "next_turn_focus": "先谈服务交换",
            "active_goal": "守住价格",
        },
    )

    stats = get_session_note_stats(session_id)
    session_context = get_session_context(session_id, limit=8)

    assert first["status"] == "written"
    assert second["status"] == "merged"
    assert stats["count"] <= 2
    assert "先谈服务交换" in session_context
    assert "先守价格" not in session_context.split("【下一轮接话点】")[-1]
    assert stats["next_pickup_actionable"] is True
    assert stats["next_pickup_duplicate_with_world_state"] is True


def test_5h_long_session_growth_stays_bounded(isolated_memory):
    session_id = "5h-long"
    prompt_sizes = []
    note_counts = []
    for turn in range(50):
        scene = "sales" if turn % 2 == 0 else "management"
        user_input = (
            "客户一直压价，这周要收口，今天先做什么？"
            if scene == "sales"
            else "团队执行力差，先别绕，给我一个更直接的推进方法。"
        )
        output = (
            "先定底线、发跟进、约回看。不要直接让价。"
            if scene == "sales"
            else "先收目标，再定责任，再卡节奏，最后只盯一件最关键的动作。"
        )
        _run_step9_turn(
            session_id,
            user_input=user_input,
            output=output,
            scene=scene,
            turn_load_level="deep",
        )
        stats = get_session_note_stats(session_id)
        prompt_sizes.append(len(get_session_context(session_id, limit=5)))
        note_counts.append(stats["count"])

    front_avg = statistics.mean(prompt_sizes[:10])
    middle_avg = statistics.mean(prompt_sizes[20:30])
    back_avg = statistics.mean(prompt_sizes[-10:])
    final_stats = get_session_note_stats(session_id)

    assert final_stats["count"] <= 18
    assert final_stats["chars"] <= 2600
    assert final_stats["compaction_needed"] is False
    assert back_avg - front_avg < 450
    assert max(note_counts) <= 18
    assert middle_avg >= front_avg * 0.8


def test_5h_crisis_session_note_isolation(isolated_memory):
    session_id = "5h-crisis"
    _, crisis_trace = _run_step9_turn(
        session_id,
        user_input="我现在真的想自杀",
        output="你现在先不要一个人待着，去有人的地方，联系现实里能陪你的人。",
        scene="emotion",
        turn_load_level="crisis",
        step8_mode="crisis",
    )
    _, normal_trace = _run_step9_turn(
        session_id,
        user_input="现在安全一点了，那我今天先做什么？",
        output="先别一下子切回复杂任务，今天只做一个很小的恢复动作，再决定要不要继续推进工作。",
        scene="emotion",
        turn_load_level="light",
        step8_mode="minimal",
    )

    stats = get_session_note_stats(session_id)
    session_context = get_session_context(session_id, limit=2)
    long_term_memories = get_memory_manager()._memories.get(session_id, [])

    assert crisis_trace.get("step9_mode") == "crisis_minimal"
    assert crisis_trace.get("memory_write_count", 0) == 0
    assert crisis_trace.get("semantic_extract_called") is False
    assert len(long_term_memories) == 0
    assert stats["count"] <= 2
    assert "自杀" not in session_context or len(session_context) < 200
    assert normal_trace.get("step9_mode") == "light_minimal"


def test_5h_takeover_trace_does_not_pollute_memory(isolated_memory):
    session_id = "5h-takeover"
    _, trace = _run_step9_turn(
        session_id,
        user_input="你是哪个模型",
        output="我是当前系统配置的对话助手，具体底层模型以当前系统配置为准。",
        scene="general",
        turn_load_level="standard",
        runtime_trace={
            "identity_truth_takeover_used": True,
            "response_obligation": {"expected_deliverable": "identity_answer"},
            "final_answer_observed": {"deliverable_observed": "identity_answer"},
        },
    )

    session_context = get_session_context(session_id, limit=5)
    long_term_memories = get_memory_manager()._memories.get(session_id, [])
    conversation_memories = [m for m in long_term_memories if m.memory_type == "conversation"]

    assert trace.get("memory_write_count", 0) == 0
    assert "response_obligation" not in session_context
    assert "final_answer_observed" not in session_context
    assert "identity_truth_takeover_used" not in session_context
    assert len(conversation_memories) == 0
