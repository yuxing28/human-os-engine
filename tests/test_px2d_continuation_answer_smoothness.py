from __future__ import annotations

import random
from types import SimpleNamespace

from graph.nodes.step8_execution import _polish_continuation_output, step8_execution
from schemas.context import Context


QUESTION_ONLY_OUTPUTS = [
    "你想继续哪部分？",
    "你想往下说哪一块？",
    "那你想继续聊什么？",
    "要继续吗？",
]


def _continuation_context(seed: int, scene: str, skill_state: str, *, with_context: bool = True) -> Context:
    ctx = Context(session_id=f"px2d-continuation-{seed}")
    ctx.primary_scene = scene
    ctx.short_utterance = True
    ctx.short_utterance_reason = "ultra_short"
    object.__setattr__(ctx, "turn_load_level", "light")
    object.__setattr__(ctx, "next_step_policy", "none")
    trace = {
        "response_obligation": {
            "expected_deliverable": "direct_answer" if with_context else "none",
            "source": "inherited_context" if with_context else "current_turn",
            "identity_answer_required": False,
            "repair_required": False,
            "current_task": "继续上一轮结构",
        },
        "route_state": {
            "conversation_phase": "continuation" if with_context else "new",
        },
        "context_brief": {
            "next_pickup": "把第二步继续拆成能执行的小动作" if with_context else "",
        },
        "skill_context_used": skill_state != "skills_off",
        "skill_extension_used": [skill_state] if skill_state not in {"skills_off", "default_scene_skill"} else [],
    }
    object.__setattr__(ctx, "runtime_trace", trace)
    object.__setattr__(ctx, "context_brief", trace["context_brief"])
    object.__setattr__(ctx, "route_state", trace["route_state"])
    return ctx


def test_px2d_random_continuation_polish_with_context_is_not_question_only():
    rng = random.Random(20260430)
    speech_acts = [
        "continuation_light",
        "request_continue_answer",
        "ask_expand_light",
        "inherited_task_followup",
        "short_followup",
        "context_dependent_continue",
    ]
    scenes = ["general", "management", "sales", "negotiation", "emotion"]
    tones = ["neutral", "casual", "impatient", "confused", "vague"]
    skills = ["skills_off", "default_scene_skill", "leijun_on"]
    paths = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]
    inputs = {
        "continuation_light": ["继续", "接着", "往下"],
        "request_continue_answer": ["继续讲", "接着说", "往下说"],
        "ask_expand_light": ["展开一点", "再往下拆", "多说一点"],
        "inherited_task_followup": ["那第二步呢", "后面怎么接", "接上刚才"],
        "short_followup": ["然后呢", "再然后", "下一步"],
        "context_dependent_continue": ["按刚才那个", "顺着那个说", "沿着刚才"],
    }

    cases = []
    for idx in range(150):
        speech_act = rng.choice(speech_acts)
        cases.append(
            {
                "seed": 2026043000 + idx,
                "speech_act": speech_act,
                "scene": rng.choice(scenes),
                "tone": rng.choice(tones),
                "skill": rng.choice(skills),
                "path": rng.choice(paths),
                "user_input": rng.choice(inputs[speech_act]),
                "raw_output": rng.choice(QUESTION_ONLY_OUTPUTS + ["嗯。", "好，我们继续。"]),
            }
        )

    polished_count = 0
    for case in cases:
        ctx = _continuation_context(case["seed"], case["scene"], case["skill"], with_context=True)
        output, used, reason = _polish_continuation_output(ctx, case["user_input"], case["raw_output"])

        assert output.strip()
        assert len(output) <= 48
        assert "你想继续" not in output
        assert "哪部分" not in output
        assert not output.strip().endswith("？")
        assert "刚才" in output or "先看" in output
        assert reason in {"route_state", "response_obligation", "next_pickup"}
        if used:
            polished_count += 1

    assert polished_count >= 145


def test_px2d_without_context_does_not_invent_continuation():
    ctx = _continuation_context(1, "general", "skills_off", with_context=False)
    output, used, reason = _polish_continuation_output(ctx, "继续", "你想继续哪部分？")

    assert output == "你想继续哪部分？"
    assert used is False
    assert reason == "skip_no_context"


def test_px2d_does_not_touch_identity_repair_or_crisis():
    identity = _continuation_context(2, "general", "skills_off", with_context=True)
    identity.runtime_trace["response_obligation"]["expected_deliverable"] = "identity_answer"
    identity.runtime_trace["response_obligation"]["identity_answer_required"] = True
    output, used, reason = _polish_continuation_output(identity, "继续", "你想继续哪部分？")
    assert output == "你想继续哪部分？"
    assert used is False
    assert reason == "skip_identity"

    repair = _continuation_context(3, "general", "skills_off", with_context=True)
    repair.runtime_trace["response_obligation"]["repair_required"] = True
    output, used, reason = _polish_continuation_output(repair, "继续", "你想继续哪部分？")
    assert output == "你想继续哪部分？"
    assert used is False
    assert reason == "skip_repair"

    crisis = _continuation_context(4, "emotion", "skills_off", with_context=True)
    crisis.runtime_trace["route_state"]["risk_level"] = "crisis"
    output, used, reason = _polish_continuation_output(crisis, "我继续不下去", "你想继续哪部分？")
    assert output == "你想继续哪部分？"
    assert used is False
    assert reason == "skip_crisis"


def test_px2d_skip_to_end_integration_keeps_continuation_light(monkeypatch):
    import modules.L4.field_quality as field_quality

    monkeypatch.setattr(
        field_quality,
        "quality_check",
        lambda output, context: SimpleNamespace(passed=True, failed_items=[]),
    )

    ctx = _continuation_context(5, "management", "leijun_on", with_context=True)
    ctx.output = "你想继续哪部分？"

    result = step8_execution(
        {
            "context": ctx,
            "user_input": "接着说",
            "skip_to_end": True,
            "runtime_trace": ctx.runtime_trace,
        }
    )

    output = result["output"]
    trace = result["context"].runtime_trace

    assert "刚才" in output
    assert "你想继续" not in output
    assert len(output) <= 48
    assert trace["continuation_polish_used"] is True
    assert trace.get("repair_contract_takeover_used") is not True
    assert trace.get("fallback_contract_takeover_used") is not True
