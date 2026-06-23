import importlib
import sys
from types import SimpleNamespace

from schemas.context import Context
from schemas.enums import FeedbackType

step9_mod = importlib.import_module("graph.nodes.step9_feedback")


def _disable_side_effect_helpers(monkeypatch):
    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_extract_session_notes", lambda context, user_input, round_num: None)


def test_step9_should_skip_raw_conversation_memory_for_quick_ack(monkeypatch):
    import modules.memory as memory_mod

    _disable_side_effect_helpers(monkeypatch)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        calls.append({"user_id": user_id, "content": content, "memory_type": memory_type, "importance": importance})

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)

    context = Context(session_id="mem_test_quick_ack")
    context.short_utterance = True
    context.output = "收到，我们先稳住节奏。"

    state = {"context": context, "user_input": "好的"}
    step9_mod.step9_feedback(state)

    conversation_calls = [c for c in calls if c["memory_type"] == "conversation"]
    assert conversation_calls == []


def test_step9_should_store_raw_conversation_memory_for_normal_input(monkeypatch):
    import modules.memory as memory_mod

    _disable_side_effect_helpers(monkeypatch)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        calls.append({"user_id": user_id, "content": content, "memory_type": memory_type, "importance": importance})

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)

    context = Context(session_id="mem_test_normal")
    context.output = "我听懂了，我们先把最关键的风险说清，再决定下一步。"

    state = {"context": context, "user_input": "我跟老板聊完了，他担心预算和风险，你觉得我下一步怎么推进？"}
    step9_mod.step9_feedback(state)

    conversation_calls = [c for c in calls if c["memory_type"] == "conversation"]
    assert len(conversation_calls) == 2


def test_step9_should_skip_low_value_system_memory_but_keep_user_memory(monkeypatch):
    import modules.memory as memory_mod

    _disable_side_effect_helpers(monkeypatch)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        calls.append({"user_id": user_id, "content": content, "memory_type": memory_type, "importance": importance})
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)

    context = Context(session_id="mem_test_skip_system")
    context.output = "嗯，我们先这样。"

    state = {"context": context, "user_input": "我想再确认一下刚刚那个节奏安排。"}
    step9_mod.step9_feedback(state)

    conversation_calls = [c for c in calls if c["memory_type"] == "conversation"]
    assert len(conversation_calls) == 1
    assert conversation_calls[0]["content"].startswith("用户:")
    assert any(item.get("source") == "raw_system" and item.get("status") == "skipped" for item in context.memory_write_report)


def test_step9_should_attach_memory_write_report(monkeypatch):
    import modules.memory as memory_mod

    _disable_side_effect_helpers(monkeypatch)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)

    context = Context(session_id="mem_test_report")
    context.output = "我们先把关键目标说清，再推进细节。"

    state = {"context": context, "user_input": "我想先对齐目标，再谈方案。"}
    step9_mod.step9_feedback(state)

    assert len(context.memory_write_report) >= 2
    assert context.memory_write_report[0].get("bucket") == "conversation"
    assert context.history[-1].metadata.get("memory_write_report")


def test_step9_should_record_relationship_state_and_closure_notes(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append(
            {
                "session_id": session_id,
                "round_num": round_num,
                "note_type": note_type,
                "content": content,
                "detail": detail or {},
            }
        )

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)

    context = Context(session_id="mem_test_relationship_closure")
    context.output = "我先把最关键的风险说清，明天我们再把条款对齐。"
    context.last_feedback = FeedbackType.POSITIVE
    context.scene_config = SimpleNamespace(scene_id="negotiation")
    context.goal.granular_goal = "negotiation_followup"
    context.current_strategy.combo_name = "条款对齐"
    context.current_strategy.stage = "推进"
    context.user.relationship_position = "对等-合作"
    context.situation_stage = "推进"

    state = {"context": context, "user_input": "那就按这个思路，明天再对齐一次。"}
    step9_mod.step9_feedback(state)

    note_types = [item["note_type"] for item in calls]
    assert "world_state" in note_types
    assert "action_loop" in note_types
    assert "relationship_state" in note_types
    assert "closure" in note_types

    world_state_note = next(item for item in calls if item["note_type"] == "world_state")
    assert "风险:" in world_state_note["content"]
    assert "动作:" in world_state_note["content"]
    assert world_state_note["detail"].get("progress_state") in {"继续推进", "继续对齐", "继续观察", "回到修复", "先修复", "往收口走", "先观察"}
    assert world_state_note["detail"].get("action_loop_state")

    action_loop_note = next(item for item in calls if item["note_type"] == "action_loop")
    assert "推进" in action_loop_note["content"]
    assert action_loop_note["detail"].get("next_turn_focus")

    closure_note = next(item for item in calls if item["note_type"] == "closure")
    assert "明天" in closure_note["content"]
    assert "对等-合作" in closure_note["content"] or closure_note["detail"].get("relationship_position") == "对等-合作"


def test_step9_should_record_state_evolution_when_previous_world_state_exists(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append(
            {
                "session_id": session_id,
                "round_num": round_num,
                "note_type": note_type,
                "content": content,
                "detail": detail or {},
            }
        )

    class _FakeSessionMemory:
        def get_recent_notes(self, session_id, limit=10):
            return [
                SimpleNamespace(
                    note_type="world_state",
                    detail={
                        "scene_id": "negotiation",
                        "relationship_position": "对等-合作",
                        "situation_stage": "观察",
                        "trust_level": "medium",
                        "tension_level": "low",
                        "risk_level": "low",
                        "pressure_level": "low",
                        "progress_state": "继续观察",
                        "commitment_state": "未形成",
                        "active_goal": "谈判推进",
                        "next_turn_focus": "先对齐目标",
                    },
                ),
                SimpleNamespace(
                    note_type="world_state",
                    detail={
                        "scene_id": "negotiation",
                        "relationship_position": "对等-合作",
                        "situation_stage": "推进",
                        "trust_level": "high",
                        "tension_level": "medium",
                        "risk_level": "low",
                        "pressure_level": "medium",
                        "progress_state": "继续推进",
                        "commitment_state": "已形成跟进",
                        "active_goal": "谈判推进",
                        "next_turn_focus": "明天再对齐",
                    },
                ),
            ]

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)
    monkeypatch.setattr(memory_mod, "get_session_memory", lambda: _FakeSessionMemory())

    context = Context(session_id="mem_test_state_evolution")
    context.output = "我先把最关键的风险说清，明天我们再把条款对齐。"
    context.last_feedback = FeedbackType.POSITIVE
    context.scene_config = SimpleNamespace(scene_id="negotiation")
    context.goal.granular_goal = "negotiation_followup"
    context.current_strategy.combo_name = "条款对齐"
    context.current_strategy.stage = "推进"
    context.user.relationship_position = "对等-合作"
    context.situation_stage = "推进"

    state = {"context": context, "user_input": "那就按这个思路，明天再对齐一次。"}
    step9_mod.step9_feedback(state)

    note_types = [item["note_type"] for item in calls]
    assert "world_state" in note_types
    assert "state_evolution" in note_types
    state_evolution_note = next(item for item in calls if item["note_type"] == "state_evolution")
    assert "信任" in state_evolution_note["content"] or "阶段" in state_evolution_note["content"]


def test_step9_should_push_progress_forward_when_stage_has_goal(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append(
            {
                "session_id": session_id,
                "round_num": round_num,
                "note_type": note_type,
                "content": content,
                "detail": detail or {},
            }
        )

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)

    context = Context(session_id="mem_test_progress_forward")
    context.output = "我们可以先把目标对齐，然后继续推进。"
    context.last_feedback = FeedbackType.NEUTRAL
    context.scene_config = SimpleNamespace(scene_id="sales")
    context.goal.granular_goal = "sales_followup"
    context.goal.current.description = "继续推进成交"
    context.current_strategy.combo_name = "价值推进"
    context.current_strategy.stage = "推进"
    context.user.relationship_position = "对等-合作"
    context.situation_stage = "推进"

    state = {"context": context, "user_input": "我想先对齐目标，再往下走。"}
    step9_mod.step9_feedback(state)

    world_state_note = next(item for item in calls if item["note_type"] == "world_state")
    assert world_state_note["detail"].get("progress_state") in {"继续推进", "继续对齐"}
    assert world_state_note["detail"].get("action_loop_state")


def test_step9_should_keep_negotiation_exploration_moving_when_goal_exists(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append(
            {
                "session_id": session_id,
                "round_num": round_num,
                "note_type": note_type,
                "content": content,
                "detail": detail or {},
            }
        )

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)

    context = Context(session_id="mem_test_negotiation_explore")
    context.output = "我先不急着压价格，先把对方最在意的交换条件摸清。"
    context.last_feedback = FeedbackType.NEUTRAL
    context.scene_config = SimpleNamespace(scene_id="negotiation")
    context.goal.granular_goal = "negotiation.interest_probing"
    context.current_strategy.combo_name = "利益试探"
    context.current_strategy.stage = "探索"
    context.user.relationship_position = "对等-合作"
    context.situation_stage = "探索"
    context.self_check.interaction_tension = "medium"
    context.self_check.push_risk = "low"

    state = {"context": context, "user_input": "我想先听听对方到底最在意什么，再决定怎么谈。"}
    step9_mod.step9_feedback(state)

    world_state_note = next(item for item in calls if item["note_type"] == "world_state")
    assert world_state_note["detail"].get("progress_state") in {"继续对齐", "继续推进"}


def test_step9_should_keep_management_exploration_out_of_passive_observe_when_goal_exists(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append(
            {
                "session_id": session_id,
                "round_num": round_num,
                "note_type": note_type,
                "content": content,
                "detail": detail or {},
            }
        )

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)

    context = Context(session_id="mem_test_management_explore")
    context.output = "先把最卡的那一件事对齐，不急着一下把所有问题都压上来。"
    context.last_feedback = FeedbackType.NEUTRAL
    context.scene_config = SimpleNamespace(scene_id="management")
    context.goal.granular_goal = "task_acceptance"
    context.goal.current.description = "先对齐最卡的一件事"
    context.current_strategy.combo_name = "任务对齐"
    context.current_strategy.stage = "探索"
    context.user.relationship_position = "上下级"
    context.situation_stage = "探索"
    context.self_check.interaction_tension = "medium"
    context.self_check.push_risk = "low"

    state = {"context": context, "user_input": "我们先把最卡的任务说清，再决定后面怎么分。"}
    step9_mod.step9_feedback(state)

    world_state_note = next(item for item in calls if item["note_type"] == "world_state")
    assert world_state_note["detail"].get("progress_state") in {"继续对齐", "继续推进"}


def test_step9_should_fill_negotiation_focus_when_progress_moves_without_explicit_commitment(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append({"note_type": note_type, "content": content, "detail": detail or {}})

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)

    context = Context(session_id="mem_test_negotiation_focus_fill")
    context.output = "我先不急着压价，先把交换条件摆清楚。"
    context.last_feedback = FeedbackType.NEUTRAL
    context.scene_config = SimpleNamespace(scene_id="negotiation")
    context.goal.granular_goal = "negotiation.interest_probing"
    context.current_strategy.combo_name = "条件对齐"
    context.current_strategy.stage = "探索"
    context.user.relationship_position = "对等-合作"
    context.situation_stage = "探索"
    context.self_check.interaction_tension = "low"
    context.self_check.push_risk = "low"

    state = {"context": context, "user_input": "我想先摸清对方真正要什么，再决定怎么继续谈。"}
    step9_mod.step9_feedback(state)

    world_state_note = next(item for item in calls if item["note_type"] == "world_state")
    assert world_state_note["detail"].get("progress_state") == "继续对齐"
    assert world_state_note["detail"].get("commitment_state") == "已形成方向"
    assert world_state_note["detail"].get("next_turn_focus")


def test_step9_should_fill_management_focus_when_progress_moves_without_explicit_commitment(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append({"note_type": note_type, "content": content, "detail": detail or {}})

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)

    context = Context(session_id="mem_test_management_focus_fill")
    context.output = "我们先把最卡的那一步说清，再决定后面谁来接。"
    context.last_feedback = FeedbackType.NEUTRAL
    context.scene_config = SimpleNamespace(scene_id="management")
    context.goal.granular_goal = "task_acceptance"
    context.current_strategy.combo_name = "任务拆解"
    context.current_strategy.stage = "探索"
    context.user.relationship_position = "上下级"
    context.situation_stage = "探索"
    context.self_check.interaction_tension = "low"
    context.self_check.push_risk = "low"

    state = {"context": context, "user_input": "先把最卡的一步说清，再看谁来接。"}
    step9_mod.step9_feedback(state)

    world_state_note = next(item for item in calls if item["note_type"] == "world_state")
    assert world_state_note["detail"].get("progress_state") == "继续对齐"
    assert world_state_note["detail"].get("commitment_state") == "已形成方向"
    assert world_state_note["detail"].get("next_turn_focus")


def test_step9_should_keep_negotiation_direction_when_stage_is_unclear(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append({"note_type": note_type, "content": content, "detail": detail or {}})

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)

    context = Context(session_id="mem_test_negotiation_unclear_stage")
    context.output = "我们先聊聊情况。"
    context.last_feedback = FeedbackType.NEUTRAL
    context.scene_config = SimpleNamespace(scene_id="negotiation")
    context.goal.granular_goal = "negotiation.interest_probing"
    context.current_strategy.combo_name = "条件对齐"
    context.current_strategy.stage = ""
    context.user.relationship_position = "对等-合作"
    context.situation_stage = ""
    context.self_check.interaction_tension = "low"
    context.self_check.push_risk = "low"

    state = {"context": context, "user_input": "先聊聊对方在意什么。"}
    step9_mod.step9_feedback(state)

    world_state_note = next(item for item in calls if item["note_type"] == "world_state")
    assert world_state_note["detail"].get("progress_state") in {"继续对齐", "继续推进"}
    assert world_state_note["detail"].get("next_turn_focus")


def test_step9_should_keep_management_direction_when_stage_is_unclear(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append({"note_type": note_type, "content": content, "detail": detail or {}})

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)

    context = Context(session_id="mem_test_management_unclear_stage")
    context.output = "我们先看看情况。"
    context.last_feedback = FeedbackType.NEUTRAL
    context.scene_config = SimpleNamespace(scene_id="management")
    context.goal.granular_goal = "task_acceptance"
    context.current_strategy.combo_name = "任务拆解"
    context.current_strategy.stage = ""
    context.user.relationship_position = "上下级"
    context.situation_stage = ""
    context.self_check.interaction_tension = "low"
    context.self_check.push_risk = "low"

    state = {"context": context, "user_input": "先看看最卡的是哪一步。"}
    step9_mod.step9_feedback(state)

    world_state_note = next(item for item in calls if item["note_type"] == "world_state")
    assert world_state_note["detail"].get("progress_state") in {"继续对齐", "继续推进"}
    assert world_state_note["detail"].get("next_turn_focus")


def test_step9_should_keep_sales_direction_when_stage_is_unclear(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append({"note_type": note_type, "content": content, "detail": detail or {}})

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)

    context = Context(session_id="mem_test_sales_unclear_stage")
    context.output = "我们先把对方最在意的点摸清。"
    context.last_feedback = FeedbackType.NEUTRAL
    context.scene_config = SimpleNamespace(scene_id="sales")
    context.goal.granular_goal = "value_differentiation"
    context.current_strategy.combo_name = "价值对齐"
    context.current_strategy.stage = ""
    context.user.relationship_position = "对等-合作"
    context.situation_stage = ""
    context.self_check.interaction_tension = "low"
    context.self_check.push_risk = "low"

    state = {"context": context, "user_input": "先看看对方最在意哪一点，再决定怎么接。"}
    step9_mod.step9_feedback(state)

    world_state_note = next(item for item in calls if item["note_type"] == "world_state")
    assert world_state_note["detail"].get("progress_state") in {"继续对齐", "继续推进"}
    assert world_state_note["detail"].get("next_turn_focus")


def test_step9_should_fill_sales_focus_when_progress_moves_without_explicit_commitment(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append({"note_type": note_type, "content": content, "detail": detail or {}})

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)

    context = Context(session_id="mem_test_sales_focus_fill")
    context.output = "价值和风险需要讲透。"
    context.last_feedback = FeedbackType.NEUTRAL
    context.scene_config = SimpleNamespace(scene_id="sales")
    context.goal.granular_goal = "prove_roi"
    context.current_strategy.combo_name = "价值对齐"
    context.current_strategy.stage = "推进"
    context.user.relationship_position = "对等-合作"
    context.situation_stage = "推进"
    context.self_check.interaction_tension = "low"
    context.self_check.push_risk = "low"

    state = {"context": context, "user_input": "这个方向可以，你往下展开。"}
    step9_mod.step9_feedback(state)

    world_state_note = next(item for item in calls if item["note_type"] == "world_state")
    assert world_state_note["detail"].get("progress_state") == "继续推进"
    assert world_state_note["detail"].get("commitment_state") == "已形成方向"
    assert "总账算清" in world_state_note["detail"].get("next_turn_focus", "")


def test_step9_should_keep_emotion_direction_when_stage_is_unclear(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append({"note_type": note_type, "content": content, "detail": detail or {}})

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)

    context = Context(session_id="mem_test_emotion_unclear_stage")
    context.output = "我们先把最难受的那一块接住。"
    context.last_feedback = FeedbackType.NEUTRAL
    context.scene_config = SimpleNamespace(scene_id="emotion")
    context.goal.granular_goal = "emotion.validate_feeling"
    context.current_strategy.combo_name = "情绪承接"
    context.current_strategy.stage = ""
    context.user.relationship_position = "亲密-支持"
    context.situation_stage = ""
    context.self_check.interaction_tension = "low"
    context.self_check.push_risk = "low"

    state = {"context": context, "user_input": "我现在还乱，但想继续说。"}
    step9_mod.step9_feedback(state)

    world_state_note = next(item for item in calls if item["note_type"] == "world_state")
    assert world_state_note["detail"].get("progress_state") in {"继续对齐", "继续推进"}
    assert world_state_note["detail"].get("next_turn_focus")


def test_step9_should_fill_emotion_focus_when_progress_moves_without_explicit_commitment(monkeypatch):
    import modules.memory as memory_mod

    monkeypatch.setattr(step9_mod, "_advance_mode_sequence", lambda context: None)
    monkeypatch.setattr(step9_mod, "_update_trust_level", lambda context: None)
    monkeypatch.setattr(step9_mod, "_record_strategy_to_library", lambda context, user_input: None)
    monkeypatch.setattr(step9_mod, "_record_scene_evolution", lambda context: None)
    monkeypatch.setattr(step9_mod, "_evaluate_strategy_experience", lambda context, user_input: None)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    def fake_add_session_note(session_id, round_num, note_type, content, detail=None):
        calls.append({"note_type": note_type, "content": content, "detail": detail or {}})

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)
    monkeypatch.setattr(memory_mod, "add_session_note", fake_add_session_note)

    context = Context(session_id="mem_test_emotion_focus_fill")
    context.output = "我先不急着解释，先把最难受的那块接住。"
    context.last_feedback = FeedbackType.NEUTRAL
    context.scene_config = SimpleNamespace(scene_id="emotion")
    context.goal.granular_goal = "emotion.validate_feeling"
    context.current_strategy.combo_name = "情绪承接"
    context.current_strategy.stage = "推进"
    context.user.relationship_position = "亲密-支持"
    context.situation_stage = "推进"
    context.self_check.interaction_tension = "low"
    context.self_check.push_risk = "low"

    state = {"context": context, "user_input": "我现在就是很难受，但还能继续说。"}
    step9_mod.step9_feedback(state)

    world_state_note = next(item for item in calls if item["note_type"] == "world_state")
    assert world_state_note["detail"].get("progress_state") == "继续推进"
    assert world_state_note["detail"].get("commitment_state") == "已形成方向"
    assert any(
        marker in world_state_note["detail"].get("next_turn_focus", "")
        for marker in ["最难受", "先顾", "先稳住"]
    )


def test_step9_should_store_failure_experience_memory_when_negative(monkeypatch):
    import modules.memory as memory_mod

    _disable_side_effect_helpers(monkeypatch)
    monkeypatch.setattr(memory_mod, "retrieve_memory", lambda user_id, query, limit=5: [])
    monkeypatch.setattr(memory_mod, "extract_important_facts", lambda user_input, system_output, existing_memories=None: None)

    calls = []

    def fake_store_memory(user_id, content, memory_type="conversation", importance=0.5):
        calls.append({
            "user_id": user_id,
            "content": content,
            "memory_type": memory_type,
            "importance": importance,
        })
        return {
            "status": "stored",
            "reason": "ok",
            "memory_type": memory_type,
            "bucket": "failure" if memory_type == "failure" else "conversation",
            "importance": importance,
            "content_preview": content[:20],
        }

    monkeypatch.setattr(memory_mod, "store_memory", fake_store_memory)

    monkeypatch.setitem(
        sys.modules,
        "modules.L5.counter_example_lib",
        SimpleNamespace(
            record_failure=lambda **kwargs: None,
            infer_failure_type=lambda *_args, **_kwargs: SimpleNamespace(value="timing_error"),
            infer_failure_code=lambda *_args, **_kwargs: SimpleNamespace(value="F03"),
            record_success=lambda **kwargs: None,
        ),
    )

    context = Context(session_id="mem_test_failure_experience")
    context.output = "我先收住，不强推。"
    context.last_feedback = FeedbackType.NEGATIVE
    context.scene_config = SimpleNamespace(scene_id="sales")
    context.goal.granular_goal = "sales_followup"
    context.current_strategy.combo_name = "价格异议收口"
    context.current_strategy.stage = "知识"

    context.add_history("system", "上一轮输出")
    context.history[-1].metadata["judge_result"] = {"relevance": 4, "guidance": 3, "overall": 4}

    state = {"context": context, "user_input": "客户说太贵，还要再对比竞品。"}
    step9_mod.step9_feedback(state)

    failure_calls = [c for c in calls if c["memory_type"] == "failure"]
    assert len(failure_calls) == 1
    assert "失败经验" in failure_calls[0]["content"]
    assert "失败码=F03" in failure_calls[0]["content"]
    assert any(item.get("source") == "failure_experience" for item in context.memory_write_report)
