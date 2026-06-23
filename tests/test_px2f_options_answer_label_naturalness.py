from __future__ import annotations

import random

from graph.nodes.answer_first_takeover import _minimum_answer
from graph.nodes.fallback_contract_takeover import _minimum_fallback_answer
from graph.nodes.internal_strategy_leak_takeover import _minimum_final_answer
from graph.nodes.repair_contract_takeover import _minimum_repair_answer
from graph.nodes.response_obligation_observer import classify_deliverable_observed
from schemas.context import Context


def _context(seed: int, scene: str, skill_state: str) -> Context:
    ctx = Context(session_id=f"px2f-options-{seed}")
    ctx.primary_scene = scene
    trace = {
        "response_obligation": {
            "expected_deliverable": "options",
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


def _option_line_count(text: str) -> int:
    markers = ["稳一点", "推进一点", "保留余地"]
    return sum(1 for marker in markers if marker in text)


def _hard_template_score(text: str) -> int:
    hard_markers = ["选项一", "选项二", "选项三", "1.", "2.", "3."]
    return sum(text.count(marker) for marker in hard_markers)


def _assert_natural_options(output: str) -> None:
    assert output.strip()
    assert classify_deliverable_observed(output) == "options"
    assert _option_line_count(output) >= 3
    assert not output.strip().endswith("？")
    assert "你想" not in output
    assert _hard_template_score(output) == 0
    assert any(marker in output for marker in ["三个选择", "三个方向"])
    assert len(output) <= 140


def test_px2f_random_options_labels_stay_options_and_less_template_like():
    rng = random.Random(20260502)
    speech_acts = [
        "ask_options",
        "ask_alternatives",
        "ask_choice",
        "ask_what_can_do",
        "compare_options",
        "decision_uncertainty",
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
                    "expected_deliverable": "options",
                    "user_goal": "补几个可选方向",
                },
            ),
        ),
    ]

    checked = 0
    for idx in range(150):
        case = {
            "seed": 2026050200 + idx,
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
        _assert_natural_options(output)
        checked += 1

    assert checked == 150


def test_px2f_options_boundaries_do_not_touch_other_deliverables():
    ctx = _context(1, "management", "skills_off")
    ctx.runtime_trace["response_obligation"]["expected_deliverable"] = "direct_answer"
    direct_output = _minimum_answer(ctx, ctx.runtime_trace)
    assert classify_deliverable_observed(direct_output) != "options"

    ctx.runtime_trace["response_obligation"]["expected_deliverable"] = "script"
    script_output = _minimum_fallback_answer(ctx, ctx.runtime_trace)
    assert classify_deliverable_observed(script_output) == "script"
    assert "直接说" in script_output or "直接发" in script_output
    assert "稳一点" not in script_output
    assert "推进一点" not in script_output
    assert "保留余地" not in script_output
