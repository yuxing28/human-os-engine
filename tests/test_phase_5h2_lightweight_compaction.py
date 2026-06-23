import statistics

import pytest

import modules.memory as memory_mod
from graph.nodes.step9_feedback import step9_feedback
from modules.memory import MemoryManager, SessionMemory, get_session_context, get_session_memory, get_session_note_stats
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
        "system_rounds": 1,
        "runtime_trace": {
            "turn_load_level": turn_load_level,
            "step8_mode": step8_mode,
            **(runtime_trace or {}),
        },
    }
    result = step9_feedback(state)
    return result["context"], getattr(result["context"], "runtime_trace", {}) or {}


def test_5h2_long_session_50_turn_compaction_bounds_context(isolated_memory):
    session_id = "5h2-long-50"
    prompt_sizes = []
    note_sizes = []
    compaction_seen = False

    for turn in range(50):
        scene = ["sales", "management", "negotiation", "emotion"][turn % 4]
        if turn == 0:
            user_input = "我现在安全了，但刚才情绪很危险，后面普通任务别被这个污染。"
            output = "先保留安全恢复这条线，后面普通任务只按当前问题推进。"
        elif turn % 11 == 0:
            user_input = "情况修正一下，价格不动，服务可以换，但不能超过5%。"
            output = "最新状态按价格不动、服务可交换来走，下一步先拉回价值。"
        elif turn % 7 == 0:
            user_input = "刚才没答到点上，接上个任务补一个具体做法。"
            output = "刚才那版没有接住重点，我补到上个任务：先定目标，再拆动作，再卡回看。"
        else:
            user_input = f"客户压价或团队推进卡住了，第{turn}轮今天先做什么？"
            output = f"第{turn}轮先定底线，再给一个可交换条件，最后约下一次确认。"

        _, trace = _run_step9_turn(
            session_id,
            user_input=user_input,
            output=output,
            scene=scene,
            turn_load_level="deep" if turn % 5 == 0 else "standard",
        )
        stats = get_session_note_stats(session_id)
        prompt_sizes.append(len(get_session_context(session_id, limit=8)))
        note_sizes.append(stats["chars"])
        compaction_seen = compaction_seen or bool(trace.get("session_note_compaction_used"))

    stats = get_session_note_stats(session_id)
    context_text = get_session_context(session_id, limit=12)

    assert compaction_seen is True
    assert stats["count"] <= 12
    assert stats["chars"] <= 1800
    assert stats["compaction_needed"] is False
    assert "安全" in context_text or "恢复" in context_text
    assert "下一步" in context_text or "先" in context_text
    assert max(note_sizes[-10:]) <= max(note_sizes[:10]) + 900
    assert statistics.mean(prompt_sizes[-10:]) <= statistics.mean(prompt_sizes[:10]) + 500


def test_5h2_compaction_preserves_key_information(isolated_memory):
    session = get_session_memory()
    session_id = "5h2-preserve"
    preserved_inputs = [
        ("closure", "偏好: 以后先给结论，不要总反问。", {"source": "preference"}),
        ("world_state", "场景: sales | 局面: 客户压价 | 判断: 先守价格", {"scene_id": "sales", "next_turn_focus": "先守价格"}),
        ("world_state", "场景: sales | 局面: 已修正 | 判断: 价格不动，服务可换，不能超过5%", {"scene_id": "sales", "next_turn_focus": "先谈服务交换"}),
        ("closure", "repair target: 上一轮未完成，要补管理步骤。", {"repair_target": "management_steps"}),
        ("closure", "crisis recovery: 用户已安全，保留安全恢复连续性。", {"step9_mode": "crisis_minimal"}),
    ]
    for index, (note_type, content, detail) in enumerate(preserved_inputs, start=1):
        session.add_note(session_id, index, note_type, content, detail)
    for index in range(6, 28):
        session.add_note(
            session_id,
            index,
            "closure",
            f"普通闭环第{index}轮：客户压价，下一步先确认边界。",
            {"source": "loop", "next_turn_focus": "先确认边界"},
        )

    stats = get_session_note_stats(session_id)
    context_text = get_session_context(session_id, limit=12)

    assert stats["session_note_compaction_used"] is True
    assert "先给结论" in context_text or "不要总反问" in context_text
    assert "服务" in context_text or "不能超过5%" in context_text
    assert "repair" in context_text or "未完成" in context_text
    assert "安全" in context_text or "crisis recovery" in context_text
    assert stats["next_pickup_actionable"] is True


def test_5h2_performance_volume_does_not_increase(isolated_memory):
    session = get_session_memory()
    session_id = "5h2-volume"
    pre_compact_p95 = 0
    post_compact_sizes = []

    for turn in range(20):
        result = session.add_note(
            session_id,
            turn + 1,
            "closure",
            f"第{turn}轮客户压价，团队也卡住，需要先确认边界再推进。",
            {"source": "volume", "next_turn_focus": f"第{turn}轮先确认边界"},
        )
        stats = get_session_note_stats(session_id)
        compaction = result.get("compaction", {}) if isinstance(result, dict) else {}
        if compaction.get("size_before"):
            pre_compact_p95 = max(pre_compact_p95, int(compaction.get("size_before") or 0))
        post_compact_sizes.append(stats["chars"])

    stats = get_session_note_stats(session_id)
    assert stats["session_note_compaction_used"] is True
    assert stats["session_note_size_after"] <= stats["session_note_size_before"]
    assert max(post_compact_sizes[-5:]) <= max(pre_compact_p95, 1)
    assert len(get_session_context(session_id, limit=8)) <= 1400


def test_5h2_crisis_and_repair_not_lost_after_compaction(isolated_memory):
    session = get_session_memory()
    session_id = "5h2-crisis-repair"
    session.add_note(
        session_id,
        1,
        "closure",
        "crisis recovery: 用户刚才不想活了，现在安全一点，保留安全恢复连续性。",
        {"step9_mode": "crisis_minimal"},
    )
    session.add_note(
        session_id,
        2,
        "closure",
        "repair target: 刚才没答到点上，要补团队执行步骤。",
        {"repair_target": "team_steps"},
    )
    for turn in range(16):
        session.add_note(
            session_id,
            turn + 3,
            "closure",
            f"第{turn}轮销售跟进：先确认边界，再给对方选择，最后约确认。",
            {"source": "loop", "next_turn_focus": f"第{turn}轮先确认边界"},
        )

    text = get_session_context(session_id, limit=12)
    stats = get_session_note_stats(session_id)
    assert stats["session_note_compaction_used"] is True
    assert "安全" in text or "恢复" in text
    assert "没答到" in text or "补到" in text or "团队执行" in text
