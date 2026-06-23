from __future__ import annotations

import random

from graph.nodes.answer_first_takeover import _minimum_answer
from graph.nodes.fallback_contract_takeover import _minimum_fallback_answer
from graph.nodes.internal_strategy_leak_takeover import _minimum_final_answer
from graph.nodes.repair_contract_takeover import _minimum_repair_answer
from graph.nodes.response_obligation_observer import classify_deliverable_observed, observe_final_output
from schemas.context import Context


def _context(seed: int, expected: str, scene: str) -> Context:
    ctx = Context(session_id=f"px2o-options-framework-{seed}")
    ctx.primary_scene = scene
    trace = {
        "response_obligation": {
            "expected_deliverable": expected,
            "answer_first_required": True,
            "identity_answer_required": False,
            "repair_required": False,
        },
        "final_answer_observed": {
            "deliverable_observed": "question_only",
            "output_satisfies_obligation": False,
        },
    }
    object.__setattr__(ctx, "runtime_trace", trace)
    return ctx


def _builders(expected: str):
    if expected == "framework":
        repair_target = {"expected_deliverable": "framework"}
    else:
        repair_target = {"expected_deliverable": "options", "user_goal": "补几个可选方向"}
    return [
        lambda ctx: _minimum_answer(ctx, ctx.runtime_trace),
        lambda ctx: _minimum_final_answer(ctx, ctx.runtime_trace),
        lambda ctx: _minimum_fallback_answer(ctx, ctx.runtime_trace),
        lambda ctx: _minimum_repair_answer(ctx, repair_target),
    ]


def test_px2o_natural_options_do_not_collapse_into_framework_or_direct_answer():
    rng = random.Random(20260513)
    scenes = ["general", "management", "sales", "negotiation", "emotion"]
    tones = ["neutral", "casual", "impatient", "confused", "vague"]
    paths = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]
    builders = _builders("options")

    checked = 0
    for idx in range(150):
        case = {
            "seed": 2026051300 + idx,
            "scene": rng.choice(scenes),
            "tone": rng.choice(tones),
            "path": rng.choice(paths),
            "builder": builders[idx % len(builders)],
        }
        ctx = _context(case["seed"], "options", case["scene"])
        output = case["builder"](ctx)
        observed = classify_deliverable_observed(output)
        assert observed == "options"
        assert observed not in {"direct_answer", "framework", "question_only"}
        final_obs = observe_final_output({"runtime_trace": ctx.runtime_trace}, ctx, output, fallback_used=False)
        assert final_obs["deliverable_observed"] == "options"
        assert final_obs["output_satisfies_obligation"] is True
        assert any(marker in output for marker in ["三个选择", "三个方向"])
        checked += 1

    assert checked == 150


def test_px2o_natural_framework_does_not_collapse_into_options_or_direct_answer():
    rng = random.Random(20260514)
    scenes = ["general", "management", "sales", "negotiation", "emotion"]
    tones = ["neutral", "casual", "impatient", "confused", "vague"]
    paths = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]
    builders = _builders("framework")

    checked = 0
    for idx in range(150):
        case = {
            "seed": 2026051400 + idx,
            "scene": rng.choice(scenes),
            "tone": rng.choice(tones),
            "path": rng.choice(paths),
            "builder": builders[idx % len(builders)],
        }
        ctx = _context(case["seed"], "framework", case["scene"])
        output = case["builder"](ctx)
        observed = classify_deliverable_observed(output)
        assert observed == "framework"
        assert observed not in {"direct_answer", "options", "question_only", "meta_strategy"}
        final_obs = observe_final_output({"runtime_trace": ctx.runtime_trace}, ctx, output, fallback_used=False)
        assert final_obs["deliverable_observed"] == "framework"
        assert final_obs["output_satisfies_obligation"] is True
        assert output.count("- ") >= 4
        checked += 1

    assert checked == 150


def test_px2o_observer_boundary_keeps_direct_answer_marker_priority():
    direct_output = (
        "直接结论：先定主判断，再补最小下一步。"
        "原因是信息不完整时，先有判断才能推动反馈。"
        "现在先把结论写成一句话，再定一个今天能完成的小动作，做完再看要不要展开。"
    )
    assert classify_deliverable_observed(direct_output) == "direct_answer"
