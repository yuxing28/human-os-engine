from __future__ import annotations

import random

from graph.nodes.answer_first_takeover import _minimum_answer
from graph.nodes.fallback_contract_takeover import _minimum_fallback_answer
from graph.nodes.internal_strategy_leak_takeover import _minimum_final_answer
from graph.nodes.response_obligation_observer import classify_deliverable_observed, observe_final_output
from schemas.context import Context


def _context(seed: int, expected: str, scene: str = "general") -> Context:
    ctx = Context(session_id=f"px2n-observer-boundary-{seed}")
    ctx.primary_scene = scene
    trace = {
        "response_obligation": {
            "expected_deliverable": expected,
            "answer_first_required": True,
            "identity_answer_required": False,
            "repair_required": False,
        }
    }
    object.__setattr__(ctx, "runtime_trace", trace)
    return ctx


def test_px2n_direct_answer_marker_wins_over_framework_words():
    rng = random.Random(20260512)
    builders = [
        lambda ctx: _minimum_answer(ctx, ctx.runtime_trace),
        lambda ctx: _minimum_final_answer(ctx, ctx.runtime_trace),
        lambda ctx: _minimum_fallback_answer(ctx, ctx.runtime_trace),
    ]
    scenes = ["general", "management", "sales", "negotiation", "emotion"]
    tones = ["neutral", "casual", "impatient", "confused", "vague"]
    paths = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]

    checked = 0
    for idx in range(150):
        case = {
            "seed": 2026051200 + idx,
            "scene": rng.choice(scenes),
            "tone": rng.choice(tones),
            "path": rng.choice(paths),
            "builder": builders[idx % len(builders)],
        }
        ctx = _context(case["seed"], "direct_answer", case["scene"])
        output = case["builder"](ctx)
        assert output.startswith("直接结论：")
        assert classify_deliverable_observed(output) == "direct_answer"
        observed = observe_final_output({"runtime_trace": ctx.runtime_trace}, ctx, output, fallback_used=False)
        assert observed["deliverable_observed"] == "direct_answer"
        assert observed["output_satisfies_obligation"] is True
        checked += 1

    assert checked == 150


def test_px2n_framework_outputs_still_observe_as_framework():
    for scene in ["general", "management", "sales", "negotiation", "emotion"]:
        ctx = _context(1, "framework", scene)
        output = _minimum_answer(ctx, ctx.runtime_trace)
        assert not output.startswith("直接结论：")
        assert classify_deliverable_observed(output) == "framework"


def test_px2n_script_and_options_boundaries_do_not_regress():
    script_output = "这句可以直接说：价格可以谈，但范围要对应交付。"
    options_output = "可以按三个方向看。\n- 稳一点的做法：先确认现状。\n- 推进一点的做法：直接给方案。\n- 保守一点的做法：先留余地。"

    assert classify_deliverable_observed(script_output) == "script"
    assert classify_deliverable_observed(options_output) == "options"
