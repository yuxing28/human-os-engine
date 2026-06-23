from __future__ import annotations

import random

from graph.nodes.answer_first_takeover import _minimum_answer
from graph.nodes.fallback_contract_takeover import _minimum_fallback_answer
from graph.nodes.internal_strategy_leak_takeover import _minimum_final_answer
from graph.nodes.repair_contract_takeover import _minimum_repair_answer
from graph.nodes.response_obligation_observer import classify_deliverable_observed
from schemas.context import Context


def _context(seed: int, scene: str, skill_state: str) -> Context:
    ctx = Context(session_id=f"px2g-framework-{seed}")
    ctx.primary_scene = scene
    trace = {
        "response_obligation": {
            "expected_deliverable": "framework",
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


def _framework_point_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip().startswith("- "))


def _hard_opening_score(text: str) -> int:
    hard_markers = [
        "可以从以下几个方面来看",
        "这个问题可以分成三层",
        "我们可以建立一个框架",
        "先给你一个简短框架",
        "先给你一个最小框架",
        "可以按这几块看",
        "用这几个点把事情收住",
    ]
    return sum(text.count(marker) for marker in hard_markers)


def _assert_natural_framework(output: str) -> None:
    assert output.strip()
    assert classify_deliverable_observed(output) == "framework"
    assert _framework_point_count(output) >= 4
    assert not output.strip().endswith("？")
    assert "你想" not in output
    assert _hard_opening_score(output) == 0
    assert not any(marker in output for marker in ["三个选择", "三个方向", "选项一", "选项二", "选项三"])
    assert len(output) <= 170


def test_px2g_random_framework_openings_stay_framework_and_less_template_like():
    rng = random.Random(20260503)
    speech_acts = [
        "ask_framework",
        "ask_analysis_structure",
        "ask_how_to_think",
        "ask_judgement_logic",
        "ask_sort_out",
        "complex_question",
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
                    "expected_deliverable": "framework",
                },
            ),
        ),
    ]

    checked = 0
    for idx in range(150):
        case = {
            "seed": 2026050300 + idx,
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
        _assert_natural_framework(output)
        checked += 1

    assert checked == 150


def test_px2g_framework_boundaries_do_not_touch_other_deliverables():
    ctx = _context(1, "management", "skills_off")
    ctx.runtime_trace["response_obligation"]["expected_deliverable"] = "direct_answer"
    direct_output = _minimum_answer(ctx, ctx.runtime_trace)
    assert "先把判断主线压清楚" not in direct_output
    assert "这里先别散开想" not in direct_output

    ctx.runtime_trace["response_obligation"]["expected_deliverable"] = "options"
    options_output = _minimum_answer(ctx, ctx.runtime_trace)
    assert classify_deliverable_observed(options_output) == "options"
    assert "稳一点" in options_output
    assert "先把判断顺序压清楚" not in options_output
