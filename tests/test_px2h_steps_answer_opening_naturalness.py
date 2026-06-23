from __future__ import annotations

import random

from graph.nodes.answer_first_takeover import _minimum_answer
from graph.nodes.fallback_contract_takeover import _minimum_fallback_answer
from graph.nodes.internal_strategy_leak_takeover import _minimum_final_answer
from graph.nodes.repair_contract_takeover import _minimum_repair_answer
from graph.nodes.response_obligation_observer import classify_deliverable_observed
from schemas.context import Context


def _context(seed: int, scene: str, skill_state: str) -> Context:
    ctx = Context(session_id=f"px2h-steps-{seed}")
    ctx.primary_scene = scene
    trace = {
        "response_obligation": {
            "expected_deliverable": "steps",
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


def _step_count(text: str) -> int:
    markers = ["1.", "2.", "3."]
    return sum(1 for marker in markers if marker in text)


def _hard_opening_score(text: str) -> int:
    hard_markers = [
        "先给一组可执行步骤",
        "可以这样做",
        "可以先按这几步做",
        "先按这几步落地",
    ]
    return sum(text.count(marker) for marker in hard_markers)


def _assert_natural_steps(output: str) -> None:
    assert output.strip()
    assert classify_deliverable_observed(output) == "steps"
    assert _step_count(output) >= 3
    assert not output.strip().endswith("？")
    assert "你想" not in output
    assert _hard_opening_score(output) == 0
    assert "三个选择" not in output
    assert "三个方向" not in output
    assert len(output) <= 190


def test_px2h_random_steps_openings_stay_steps_and_less_template_like():
    rng = random.Random(20260504)
    speech_acts = [
        "ask_steps",
        "ask_action_plan",
        "ask_how_to_execute",
        "ask_next_steps",
        "ask_process",
        "ask_operational_path",
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
                    "expected_deliverable": "steps",
                },
            ),
        ),
    ]

    checked = 0
    for idx in range(150):
        case = {
            "seed": 2026050400 + idx,
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
        _assert_natural_steps(output)
        checked += 1

    assert checked == 150


def test_px2h_steps_boundaries_do_not_touch_other_deliverables():
    ctx = _context(1, "management", "skills_off")
    ctx.runtime_trace["response_obligation"]["expected_deliverable"] = "framework"
    framework_output = _minimum_answer(ctx, ctx.runtime_trace)
    assert classify_deliverable_observed(framework_output) == "framework"
    assert "别先铺太开" not in framework_output

    ctx.runtime_trace["response_obligation"]["expected_deliverable"] = "options"
    options_output = _minimum_answer(ctx, ctx.runtime_trace)
    assert classify_deliverable_observed(options_output) == "options"
    assert "稳一点" in options_output
    assert "别先铺太开" not in options_output
