from __future__ import annotations

import random
from types import SimpleNamespace

from graph.nodes.step8_execution import _polish_light_casual_output, step8_execution
from schemas.context import Context


MECHANICAL_OUTPUTS = {"嗯。", "嗯", "没问题。", "没问题", "...", "……"}


def _light_context(seed: int, scene: str, reason: str, skill_state: str) -> Context:
    ctx = Context(session_id=f"px2c-light-{seed}")
    ctx.primary_scene = scene
    ctx.short_utterance = True
    ctx.short_utterance_reason = reason
    object.__setattr__(ctx, "turn_load_level", "light")
    object.__setattr__(ctx, "next_step_policy", "none")
    object.__setattr__(ctx, "runtime_trace", {
        "response_obligation": {
            "expected_deliverable": "none",
            "identity_answer_required": False,
            "repair_required": False,
        },
        "skill_context_used": skill_state != "skills_off",
        "skill_extension_used": [skill_state] if skill_state not in {"skills_off", "default_scene_skill"} else [],
    })
    return ctx


def test_px2c_random_light_casual_polish_keeps_outputs_short_and_natural():
    rng = random.Random(20260429)
    speech_acts = [
        "casual_ack",
        "unclear_short_turn",
        "ask_expand_light",
        "ask_simplify",
        "request_short_answer",
        "confused_light",
        "continuation_light",
    ]
    scenes = ["general", "management", "sales", "negotiation", "emotion"]
    tones = ["neutral", "casual", "impatient", "confused", "vague"]
    skills = ["skills_off", "default_scene_skill", "leijun_on"]
    paths = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]
    reasons = ["quick_ack", "ultra_short", "repeat", ""]
    generated_inputs = {
        "casual_ack": ["嗯", "好", "收到", "行吧"],
        "unclear_short_turn": ["啥", "啊？", "这啥"],
        "ask_expand_light": ["接着", "继续一点", "往下说"],
        "ask_simplify": ["简单点", "直白点", "压短说"],
        "request_short_answer": ["一句话", "短点", "别展开"],
        "confused_light": ["没懂", "有点乱", "啥意思"],
        "continuation_light": ["那继续", "接上面", "嗯继续"],
    }

    cases = []
    for idx in range(150):
        speech_act = rng.choice(speech_acts)
        cases.append(
            {
                "seed": 2026042900 + idx,
                "speech_act": speech_act,
                "scene": rng.choice(scenes),
                "tone": rng.choice(tones),
                "skill": rng.choice(skills),
                "path": rng.choice(paths),
                "reason": rng.choice(reasons),
                "user_input": rng.choice(generated_inputs[speech_act]),
                "raw_output": rng.choice(tuple(MECHANICAL_OUTPUTS)),
            }
        )

    polished_count = 0
    for case in cases:
        ctx = _light_context(case["seed"], case["scene"], case["reason"], case["skill"])
        output, used, reason = _polish_light_casual_output(ctx, case["user_input"], case["raw_output"])

        assert output.strip()
        assert len(output) <= 24
        assert output.strip() not in MECHANICAL_OUTPUTS
        assert "多说一点" not in output
        assert "\n\n" not in output
        assert reason not in {"skip_crisis", "skip_identity", "skip_repair", "skip_not_light"}
        if used:
            polished_count += 1

    assert polished_count >= 145


def test_px2c_polish_does_not_touch_non_light_identity_or_repair():
    standard = Context(session_id="px2c-standard")
    object.__setattr__(standard, "turn_load_level", "standard")
    unchanged, used, reason = _polish_light_casual_output(standard, "说说怎么处理", "嗯。")
    assert unchanged == "嗯。"
    assert used is False
    assert reason == "skip_not_light"

    identity = _light_context(1, "general", "meta_identity", "skills_off")
    identity.runtime_trace["response_obligation"]["expected_deliverable"] = "identity_answer"
    identity.runtime_trace["response_obligation"]["identity_answer_required"] = True
    unchanged, used, reason = _polish_light_casual_output(identity, "你是什么模型", "嗯。")
    assert unchanged == "嗯。"
    assert used is False
    assert reason == "skip_identity"

    repair = _light_context(2, "general", "ultra_short", "skills_off")
    repair.runtime_trace["response_obligation"]["repair_required"] = True
    unchanged, used, reason = _polish_light_casual_output(repair, "啥意思", "嗯。")
    assert unchanged == "嗯。"
    assert used is False
    assert reason == "skip_repair"


def test_px2c_skip_to_end_light_output_gets_one_breath_polish(monkeypatch):
    import modules.L4.field_quality as field_quality

    monkeypatch.setattr(
        field_quality,
        "quality_check",
        lambda output, context: SimpleNamespace(passed=True, failed_items=[]),
    )

    ctx = Context(session_id="px2c-skip-to-end")
    ctx.short_utterance = True
    ctx.short_utterance_reason = "quick_ack"
    object.__setattr__(ctx, "turn_load_level", "light")
    object.__setattr__(ctx, "next_step_policy", "none")
    ctx.output = "嗯，我在。你要是想继续，我们接着说；如果想先停一下，也可以。"

    result = step8_execution(
        {
            "context": ctx,
            "user_input": "嗯",
            "skip_to_end": True,
            "runtime_trace": {
                "response_obligation": {
                    "expected_deliverable": "none",
                    "identity_answer_required": False,
                    "repair_required": False,
                }
            },
        }
    )

    assert result["output"] == "好，我跟着。"
    trace = result["context"].runtime_trace
    assert trace["light_casual_polish_used"] is True
    assert trace["light_casual_polish_reason"] == "quick_ack"
    assert trace.get("answer_first_takeover_used") is not True
    assert trace.get("repair_contract_takeover_used") is not True
    assert trace.get("fallback_contract_takeover_used") is not True


def test_px2c_minimal_path_polishes_placeholder_without_expanding(monkeypatch):
    import llm.nvidia_client as nvidia_client
    import modules.L4.field_quality as field_quality

    monkeypatch.setattr(nvidia_client, "invoke_fast", lambda *args, **kwargs: "嗯。")
    monkeypatch.setattr(
        field_quality,
        "quality_check",
        lambda output, context: SimpleNamespace(passed=True, failed_items=[]),
    )

    ctx = Context(session_id="px2c-minimal")
    ctx.short_utterance = True
    ctx.short_utterance_reason = "ultra_short"
    object.__setattr__(ctx, "turn_load_level", "light")
    object.__setattr__(ctx, "next_step_policy", "none")

    result = step8_execution(
        {
            "context": ctx,
            "user_input": "啥",
            "runtime_trace": {
                "response_obligation": {
                    "expected_deliverable": "none",
                    "identity_answer_required": False,
                    "repair_required": False,
                }
            },
        }
    )

    assert result["output"] == "慢慢说，我听着。"
    assert len(result["output"]) <= 24
    assert result["context"].runtime_trace["light_casual_polish_used"] is True
