from __future__ import annotations

import random

from graph.nodes.answer_first_takeover import _minimum_answer
from graph.nodes.fallback_contract_takeover import _minimum_fallback_answer
from graph.nodes.internal_strategy_leak_takeover import _minimum_final_answer
from graph.nodes.repair_contract_takeover import _minimum_repair_answer
from graph.nodes.response_obligation_observer import classify_deliverable_observed
from schemas.context import Context


def _context(seed: int, scene: str, skill_state: str) -> Context:
    ctx = Context(session_id=f"px2i-script-{seed}")
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


def _hard_leadin_score(text: str) -> int:
    hard_markers = [
        "可以先这样说",
        "可以这样说",
        "可以直接这样说",
    ]
    return sum(text.count(marker) for marker in hard_markers)


def _assert_natural_script(output: str) -> None:
    assert output.strip()
    assert classify_deliverable_observed(output) == "script"
    assert "：" in output
    assert any(marker in output for marker in ["直接发", "直接说", "轻一点发", "放软一点发", "发给对方"])
    assert _hard_leadin_score(output) == 0
    assert not output.strip().endswith("？")
    assert "你想" not in output
    assert len(output) <= 150


def test_px2i_random_script_leadins_stay_script_and_less_template_like():
    rng = random.Random(20260505)
    speech_acts = [
        "ask_script",
        "ask_how_to_reply",
        "ask_copyable_line",
        "ask_message_draft",
        "ask_sales_reply",
        "ask_relationship_message",
    ]
    scenes = ["general", "management", "sales", "negotiation", "emotion"]
    tones = ["neutral", "casual", "impatient", "confused", "vague"]
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
                },
            ),
        ),
    ]

    checked = 0
    for idx in range(150):
        case = {
            "seed": 2026050500 + idx,
            "speech_act": rng.choice(speech_acts),
            "scene": rng.choice(scenes),
            "tone": rng.choice(tones),
            "skill": rng.choice(skills),
            "path": rng.choice(paths),
            "builder": builders[idx % len(builders)],
        }
        ctx = _context(case["seed"], case["scene"], case["skill"])
        _, build = case["builder"]
        output = build(ctx)
        _assert_natural_script(output)
        checked += 1

    assert checked == 150


def test_px2i_script_boundaries_do_not_touch_other_deliverables():
    ctx = _context(1, "management", "skills_off")
    ctx.runtime_trace["response_obligation"]["expected_deliverable"] = "steps"
    steps_output = _minimum_answer(ctx, ctx.runtime_trace)
    assert classify_deliverable_observed(steps_output) == "steps"
    assert "直接发" not in steps_output
    assert "直接说" not in steps_output

    ctx.runtime_trace["response_obligation"]["expected_deliverable"] = "options"
    options_output = _minimum_fallback_answer(ctx, ctx.runtime_trace)
    assert classify_deliverable_observed(options_output) == "options"
    assert "发给对方" not in options_output
