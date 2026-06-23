from __future__ import annotations

import random

from graph.nodes.answer_first_takeover import _minimum_answer
from graph.nodes.fallback_contract_takeover import _minimum_fallback_answer
from graph.nodes.internal_strategy_leak_takeover import _minimum_final_answer
from graph.nodes.repair_contract_takeover import _minimum_repair_answer
from graph.nodes.response_obligation_observer import classify_deliverable_observed
from schemas.context import Context


def _context(seed: int, scene: str, skill_state: str) -> Context:
    ctx = Context(session_id=f"px2k-negotiation-script-{seed}")
    ctx.primary_scene = scene
    trace = {
        "response_obligation": {
            "expected_deliverable": "script",
            "answer_first_required": True,
            "identity_answer_required": False,
            "repair_required": False,
        },
        "final_answer_observed": {
            "deliverable_observed": "question_only",
            "output_satisfies_obligation": False,
        },
        "skill_context_used": skill_state != "skills_off",
        "skill_extension_used": [skill_state] if skill_state not in {"skills_off", "default_scene_skill"} else [],
    }
    object.__setattr__(ctx, "runtime_trace", trace)
    return ctx


def _assert_negotiation_script(output: str) -> None:
    assert output.strip()
    assert classify_deliverable_observed(output) == "script"
    assert "这句可以直接说" in output or "这句可以直接发给对方" in output
    assert "配合" in output
    assert "单向让步" in output
    assert "调整范围或时间" in output
    assert "对应的承诺" in output
    assert "我理解" not in output
    assert "我在乎" not in output
    assert "可选方案" not in output
    assert "你想" not in output
    assert not output.strip().endswith("？")
    assert len(output) <= 150


def test_px2k_random_negotiation_boundary_scripts_stay_script_and_clear():
    rng = random.Random(20260509)
    speech_acts = [
        "ask_negotiation_script",
        "ask_boundary_phrase",
        "ask_condition_reply",
        "ask_counteroffer_line",
        "ask_how_to_refuse_softly",
        "ask_how_to_trade_terms",
    ]
    tones = ["neutral", "casual", "impatient", "confused", "vague", "annoyed"]
    skills = ["skills_off", "default_scene_skill", "leijun_on"]
    paths = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]
    builders = [
        ("answer_first", lambda ctx: _minimum_answer(ctx, ctx.runtime_trace)),
        ("internal_leak", lambda ctx: _minimum_final_answer(ctx, ctx.runtime_trace)),
        ("fallback", lambda ctx: _minimum_fallback_answer(ctx, ctx.runtime_trace)),
        (
            "repair",
            lambda ctx: _minimum_repair_answer(
                ctx,
                {
                    "expected_deliverable": "script",
                    "user_goal": "补一个谈判边界话术",
                    "observation_basis": {"route_scene": "negotiation"},
                },
            ),
        ),
    ]

    checked = 0
    for idx in range(150):
        case = {
            "seed": 2026050900 + idx,
            "speech_act": rng.choice(speech_acts),
            "tone": rng.choice(tones),
            "skill": rng.choice(skills),
            "path": rng.choice(paths),
            "builder": builders[idx % len(builders)],
        }
        ctx = _context(case["seed"], "negotiation", case["skill"])
        _, build = case["builder"]
        output = build(ctx)
        _assert_negotiation_script(output)
        checked += 1

    assert checked == 150


def test_px2k_negotiation_polish_keeps_other_scene_scripts_separate():
    sales_ctx = _context(1, "sales", "skills_off")
    sales_output = _minimum_answer(sales_ctx, sales_ctx.runtime_trace)
    assert classify_deliverable_observed(sales_output) == "script"
    assert "担心价格" in sales_output
    assert "单向让步" not in sales_output

    emotion_ctx = _context(2, "emotion", "skills_off")
    emotion_output = _minimum_fallback_answer(emotion_ctx, emotion_ctx.runtime_trace)
    assert classify_deliverable_observed(emotion_output) == "script"
    assert "认真听你说真实感受" in emotion_output
    assert "对应的承诺" not in emotion_output

    negotiation_ctx = _context(3, "negotiation", "skills_off")
    negotiation_ctx.runtime_trace["response_obligation"]["expected_deliverable"] = "framework"
    framework_output = _minimum_answer(negotiation_ctx, negotiation_ctx.runtime_trace)
    assert classify_deliverable_observed(framework_output) == "framework"
    assert "单向让步" not in framework_output
