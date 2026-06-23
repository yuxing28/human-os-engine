from types import SimpleNamespace

from graph.nodes.step6_strategy import step6_strategy_generation
from graph.nodes.step8_execution import step8_execution
from schemas.context import Context, GoalItem, WorldState
from schemas.enums import InputType


def test_step6_decision_experience_hints_should_flow_into_step8_generation(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    captured = {}

    def _fake_generate_speech(**kwargs):
        captured["knowledge_content"] = kwargs.get("knowledge_content", "")
        return "先说重点：我们先稳住一个点再推进。"

    monkeypatch.setattr(speech_generator, "generate_speech", _fake_generate_speech)
    monkeypatch.setattr(
        field_quality,
        "assess_field",
        lambda **kwargs: SimpleNamespace(can_apply_field=False),
    )

    ctx = Context(session_id="step6-step8-memory-flow")
    ctx.user.input_type = InputType.CONSULTATION
    ctx.goal.current = GoalItem(description="推进客户成交", type="利益价值")
    ctx.scene_config = SimpleNamespace(scene_id="sales")
    ctx.unified_context = """【用户画像】
职业: 运营
【相关记忆】
偏好记忆: 用户习惯先听结论
决策记忆: 上轮决定先收口再推进
经验记忆: 上次直接强推导致对抗升级
【经验提示】
1. 先对齐目标
2. 再推进动作"""

    # Step8 会重新取 unified_context，这里返回同一份上下文，确保链路稳定。
    monkeypatch.setattr(
        memory_module,
        "get_memory_manager",
        lambda: SimpleNamespace(get_unified_context=lambda **_kwargs: ctx.unified_context),
    )

    step6_state = {
        "context": ctx,
        "user_input": "客户一直拖着不签，我要先怎么推进？",
        "selected_mode": "B",
        "priority": {"priority_type": "none"},
    }
    step6_result = step6_strategy_generation(step6_state)
    strategy_plan = step6_result["strategy_plan"]
    assert strategy_plan is not None
    assert "经验决策提示：" in strategy_plan.description
    assert "决策记忆: 上轮决定先收口再推进" in strategy_plan.description

    step8_state = {
        "context": step6_result["context"],
        "user_input": "客户一直拖着不签，我要先怎么推进？",
        "strategy_plan": strategy_plan,
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }
    result = step8_execution(step8_state)

    assert "先说重点" in result["output"]
    assert "经验决策提示：" in captured["knowledge_content"]
    assert "决策记忆: 上轮决定先收口再推进" in captured["knowledge_content"]


def test_step8_should_receive_session_closure_hint_in_memory_context(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    captured = {}

    def _fake_generate_speech(**kwargs):
        captured["memory_context"] = kwargs.get("memory_context", "")
        return "我记得上轮已经对齐过，这轮就顺着往下走。"

    monkeypatch.setattr(speech_generator, "generate_speech", _fake_generate_speech)
    monkeypatch.setattr(
        field_quality,
        "assess_field",
        lambda **kwargs: SimpleNamespace(can_apply_field=False),
    )

    ctx = Context(session_id="step6-step8-closure-hint")
    ctx.user.input_type = InputType.CONSULTATION
    ctx.goal.current = GoalItem(description="推进客户成交", type="利益价值")
    ctx.scene_config = SimpleNamespace(scene_id="sales")
    ctx.unified_context = """【用户画像】
职业: 运营
【本轮重要决策】
【关系闭环摘要】
- 关系状态: 对等-合作 | 场景: sales | 阶段: 推进
- 闭环结果: 本轮结果: positive | 本轮闭环: 明天我们再把条款对齐。
【下一轮接话点】
- 明天我们再把条款对齐"""

    monkeypatch.setattr(
        memory_module,
        "get_memory_manager",
        lambda: SimpleNamespace(get_unified_context=lambda **_kwargs: ctx.unified_context),
    )

    step6_state = {
        "context": ctx,
        "user_input": "客户已经松动了，下一步怎么接？",
        "selected_mode": "B",
        "priority": {"priority_type": "none"},
    }
    step6_result = step6_strategy_generation(step6_state)

    step8_state = {
        "context": step6_result["context"],
        "user_input": "客户已经松动了，下一步怎么接？",
        "strategy_plan": step6_result["strategy_plan"],
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }
    step8_execution(step8_state)

    assert "【关系闭环摘要】" in captured["memory_context"]
    assert "【下一轮接话点】" in captured["memory_context"]
    assert "明天我们再把条款对齐" in captured["memory_context"]


def test_step2_should_build_state_aware_skill_prompt():
    from graph.nodes.step2_goal import step2_goal_detection

    ctx = Context(session_id="step2-skill-world-state")
    ctx.world_state = WorldState(
        scene_id="sales",
        situation_stage="推进",
        risk_level="medium",
        tension_level="medium",
        progress_state="继续推进",
        commitment_state="已形成跟进",
        next_turn_focus="先对齐预算边界",
    )

    state = {
        "context": ctx,
        "user_input": "客户现在主要卡在预算和合同，我怎么继续推进？",
        "skip_to_end": False,
    }
    result = step2_goal_detection(state)

    assert "【场景原则】" in result["context"].skill_prompt
    assert "【当前局面】" in result["context"].skill_prompt
    assert "焦点=先对齐预算边界" in result["context"].skill_prompt
