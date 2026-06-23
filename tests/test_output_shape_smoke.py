"""
输出形态实战抽检。

不看内部变量，只看最后给用户的成品感是否符合预期。
"""

from types import SimpleNamespace

from graph.nodes.step8_execution import step8_execution
from schemas.context import Context
from schemas.enums import EmotionType, InputType
from schemas.strategy import StrategyPlan


def _patch_step8_dependencies(monkeypatch, generated_text: str):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: generated_text,
    )
    monkeypatch.setattr(
        field_quality,
        "assess_field",
        lambda **kwargs: SimpleNamespace(can_apply_field=False),
    )
    monkeypatch.setattr(
        memory_module,
        "get_memory_manager",
        lambda: SimpleNamespace(get_unified_context=lambda **kwargs: ""),
    )


def _base_state(ctx: Context, user_input: str, mode: str = "B", stage: str = "混合", description: str = "内部说明"):
    return {
        "context": ctx,
        "user_input": user_input,
        "strategy_plan": StrategyPlan(
            mode=mode,
            combo_name="测试组合",
            stage=stage,
            description=description,
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }


def test_short_ack_should_finish_as_short_single_breath_reply(monkeypatch):
    _patch_step8_dependencies(
        monkeypatch,
        "我知道。先别急。我们先只盯住一个点，把现在最卡的地方说清楚。后面我再陪你展开。",
    )

    ctx = Context(session_id="shape-ack")
    result = step8_execution(_base_state(ctx, "嗯", mode="A"))
    output = result["output"]

    assert len(output) <= 45
    assert "\n\n" not in output
    assert output == "我知道。先别急。"


def test_relationship_repair_should_land_as_two_soft_paragraphs(monkeypatch):
    _patch_step8_dependencies(
        monkeypatch,
        "这一下确实会顶。你先别急着证明谁对。先把火压下来。等情绪掉一点再谈。",
    )

    ctx = Context(session_id="shape-repair")
    ctx.identity_hint = "关系沟通"
    ctx.situation_hint = "稳定情绪"
    ctx.primary_scene = "emotion"
    ctx.user.input_type = InputType.MIXED
    ctx.user.emotion.type = EmotionType.FRUSTRATED
    ctx.user.emotion.intensity = 0.72

    result = step8_execution(
        _base_state(
            ctx,
            "我和伴侣又僵住了，我现在最怕越聊越炸",
            mode="A",
            stage="混合",
        )
    )
    output = result["output"]

    assert "\n\n" in output
    first, second = output.split("\n\n")
    assert first == "这一下确实会顶。你先别急着证明谁对。"
    assert second == "先把火压下来。等情绪掉一点再谈。"


def test_gap_clarify_scene_should_end_on_question_not_fake_solution(monkeypatch):
    _patch_step8_dependencies(
        monkeypatch,
        "这事别急着一下讲死。我先对齐一下你现在最卡的是推进节奏还是价格顾虑？如果只选一个点，你想先说哪个？后面的动作我们再接着定。",
    )

    ctx = Context(session_id="shape-clarify")
    ctx.situation_hint = "推进结果"
    ctx.primary_scene = "sales"
    ctx.guidance_needed = True
    ctx.user.input_type = InputType.CONSULTATION
    ctx.user.emotion.type = EmotionType.CALM
    ctx.user.emotion.intensity = 0.38

    result = step8_execution(
        _base_state(
            ctx,
            "这个事我到底该怎么办",
            mode="B",
            stage="知识",
        )
    )
    output = result["output"]

    assert "？" in output
    assert "后面的动作我们再接着定" not in output


def test_direct_push_scene_should_stay_compact_and_result_oriented(monkeypatch):
    _patch_step8_dependencies(
        monkeypatch,
        "先别绕。你这轮就做两件事：先把价格锚定重新立住，再补一个真实案例。今天先把开场话术改掉，明天直接推进。",
    )

    ctx = Context(session_id="shape-action")
    ctx.situation_hint = "推进结果"
    ctx.primary_scene = "sales"
    ctx.user.input_type = InputType.CONSULTATION
    ctx.user.emotion.type = EmotionType.CALM
    ctx.user.emotion.intensity = 0.24
    ctx.goal.current.description = "推进客户成交"

    result = step8_execution(
        _base_state(
            ctx,
            "给我推进模板",
            mode="B",
            stage="知识",
        )
    )
    output = result["output"]

    assert "\n\n" not in output
    assert output.startswith("先别绕。")
    assert "今天先把开场话术改掉" in output
