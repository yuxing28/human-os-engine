"""
Step 3 自检层定向测试。
"""

from graph.nodes.step3_self_check import step3_self_check
from schemas.context import Context
from schemas.enums import Mode


def _state(ctx: Context):
    return {
        "context": ctx,
        "user_input": "测试输入",
    }


def _append_user_turn(ctx: Context, content: str, emotion_intensity: float | None = None, feedback: str | None = None):
    ctx.add_history("user", content)
    if emotion_intensity is not None:
        ctx.history[-1].metadata["emotion_intensity"] = emotion_intensity
    if feedback is not None:
        ctx.history[-1].metadata["feedback"] = feedback


def test_step3_should_force_mode_a_when_recent_high_emotion_persists():
    ctx = Context(session_id="step3-high-emotion")
    ctx.self_state.energy_mode = Mode.B
    ctx.user.emotion.intensity = 0.86

    _append_user_turn(ctx, "我快崩溃了", emotion_intensity=0.82)
    _append_user_turn(ctx, "我真的撑不住了", emotion_intensity=0.88)

    result = step3_self_check(_state(ctx))

    assert result["skip_to_end"] is False
    assert result["context"].self_state.energy_mode == Mode.A
    assert result["context"].history[-1].metadata["forced_mode_a"] is True


def test_step3_should_mark_unstable_after_three_negative_feedbacks():
    ctx = Context(session_id="step3-negative")
    ctx.self_state.energy_mode = Mode.C
    ctx.user.emotion.intensity = 0.72

    _append_user_turn(ctx, "不对", emotion_intensity=0.7, feedback="negative")
    _append_user_turn(ctx, "还是不对", emotion_intensity=0.75, feedback="negative")
    _append_user_turn(ctx, "完全没用", emotion_intensity=0.78, feedback="negative")

    result = step3_self_check(_state(ctx))

    assert result["skip_to_end"] is True
    assert result["context"].self_state.is_stable is False
    assert result["context"].self_state.energy_mode == Mode.A
    assert result["output"] == result["context"].output


def test_step3_should_record_emotion_drift_and_energy_pressure():
    ctx = Context(session_id="step3-drift")
    ctx.self_state.energy_mode = Mode.B
    ctx.user.emotion.intensity = 0.64

    _append_user_turn(ctx, "一开始还好", emotion_intensity=0.2)
    _append_user_turn(ctx, "现在越来越烦", emotion_intensity=0.68)

    result = step3_self_check(_state(ctx))

    assert result["skip_to_end"] is False
    assert result["context"].history[-1].metadata["emotion_drift_detected"] is True
    assert result["context"].history[-1].metadata["energy_pressure"] > 0


def test_step3_should_classify_attention_hijack_before_full_collapse():
    ctx = Context(session_id="step3-attention")
    ctx.self_state.energy_mode = Mode.B
    ctx.user.emotion.intensity = 0.66

    _append_user_turn(ctx, "我最近一直刷手机，根本停不下来", emotion_intensity=0.62)

    result = step3_self_check(_state(ctx))

    assert result["skip_to_end"] is False
    assert result["context"].history[-1].metadata["collapse_stage"] == "attention_hijack"
    assert "注意力" in result["context"].history[-1].metadata["recovery_focus"]


def test_step3_should_mark_inner_exhaustion_when_pressure_is_extreme():
    ctx = Context(session_id="step3-inner-exhaustion")
    ctx.self_state.energy_mode = Mode.C
    ctx.user.emotion.intensity = 0.95

    _append_user_turn(ctx, "我真的快不行了", emotion_intensity=0.92, feedback="negative")
    _append_user_turn(ctx, "我昨晚又一夜没睡", emotion_intensity=0.94, feedback="negative")
    _append_user_turn(ctx, "现在连最小的事都做不了", emotion_intensity=0.96, feedback="negative")

    result = step3_self_check(_state(ctx))

    assert result["skip_to_end"] is True
    assert result["context"].history[-1].metadata["collapse_stage"] == "inner_exhaustion"
    assert "最小目标" in result["output"] or "状态稳住" in result["output"]


def test_step3_should_record_worsening_trend_before_full_collapse():
    ctx = Context(session_id="step3-worsening-trend")
    ctx.self_state.energy_mode = Mode.B
    ctx.user.emotion.intensity = 0.78

    _append_user_turn(ctx, "刚开始只是烦", emotion_intensity=0.5, feedback="neutral")
    _append_user_turn(ctx, "现在越来越顶", emotion_intensity=0.64, feedback="negative")
    _append_user_turn(ctx, "再聊下去我真要炸了", emotion_intensity=0.78, feedback="negative")

    result = step3_self_check(_state(ctx))

    assert result["skip_to_end"] is False
    assert result["context"].history[-1].metadata["state_trend"] == "worsening"
    assert "持续上冲" in result["context"].history[-1].metadata["trend_focus"] or "越聊越顶" in result["context"].history[-1].metadata["trend_focus"]
    assert result["context"].history[-1].metadata["negative_streak"] == 2
    assert result["context"].self_state.energy_mode == Mode.A


def test_step3_should_sync_standard_self_check_fields():
    ctx = Context(session_id="step3-self-check-standard")
    ctx.self_state.energy_mode = Mode.B
    ctx.user.emotion.intensity = 0.76

    _append_user_turn(ctx, "有点烦", emotion_intensity=0.58, feedback="neutral")
    _append_user_turn(ctx, "越来越顶", emotion_intensity=0.7, feedback="negative")
    _append_user_turn(ctx, "我现在快压不住了", emotion_intensity=0.8, feedback="negative")

    result = step3_self_check(_state(ctx))
    self_check = result["context"].self_check

    assert self_check.stability_trend in {"worsening", "swinging", "stable", "recovering"}
    assert self_check.interaction_tension in {"high", "medium", "low"}
    assert self_check.push_risk in {"high", "medium", "low"}
    assert isinstance(self_check.repair_need, bool)
    assert self_check.energy_pressure >= 0
    assert self_check.negative_streak >= 0


def test_step3_should_keep_metadata_and_standard_fields_consistent():
    ctx = Context(session_id="step3-self-check-consistent")
    ctx.self_state.energy_mode = Mode.B
    ctx.user.emotion.intensity = 0.66
    _append_user_turn(ctx, "状态不稳", emotion_intensity=0.62, feedback="negative")

    result = step3_self_check(_state(ctx))

    meta = result["context"].history[-1].metadata
    self_check = result["context"].self_check

    assert meta["state_trend"] == self_check.stability_trend
    assert meta["collapse_stage"] == self_check.collapse_stage
    assert meta["recovery_focus"] == self_check.recovery_focus
