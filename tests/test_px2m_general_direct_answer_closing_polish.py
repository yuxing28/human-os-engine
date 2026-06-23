from __future__ import annotations

import random

from graph.nodes.answer_first_takeover import _minimum_answer
from graph.nodes.fallback_contract_takeover import _minimum_fallback_answer
from graph.nodes.internal_strategy_leak_takeover import _minimum_final_answer
from graph.nodes.response_obligation_observer import classify_deliverable_observed
from schemas.context import Context


def _context(seed: int, scene: str, skill_state: str) -> Context:
    ctx = Context(session_id=f"px2m-general-direct-{seed}")
    ctx.primary_scene = scene
    trace = {
        "response_obligation": {
            "expected_deliverable": "direct_answer",
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


def _assert_general_direct_closing(output: str) -> None:
    assert output.strip()
    assert classify_deliverable_observed(output) in {"direct_answer", "framework"}
    assert output.startswith("直接结论：")
    assert "原因" in output
    assert "现在先" in output
    assert "今天能完成" in output
    assert "做完再" in output
    assert "你想" not in output
    assert not output.strip().endswith("？")
    assert 60 <= len(output) <= 180


def test_px2m_random_general_direct_answer_closing_stays_dense_and_light():
    rng = random.Random(20260511)
    speech_acts = [
        "ask_direct_answer",
        "ask_meaning",
        "ask_simple_judgement",
        "ask_quick_explanation",
        "ask_what_to_do_general",
        "ask_general_take",
    ]
    tones = ["neutral", "casual", "impatient", "confused", "vague", "polite"]
    skills = ["skills_off", "default_scene_skill", "leijun_on"]
    paths = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]
    builders = [
        ("answer_first", lambda ctx: _minimum_answer(ctx, ctx.runtime_trace)),
        ("internal_leak", lambda ctx: _minimum_final_answer(ctx, ctx.runtime_trace)),
        ("fallback", lambda ctx: _minimum_fallback_answer(ctx, ctx.runtime_trace)),
    ]

    checked = 0
    for idx in range(150):
        case = {
            "seed": 2026051100 + idx,
            "speech_act": rng.choice(speech_acts),
            "tone": rng.choice(tones),
            "skill": rng.choice(skills),
            "path": rng.choice(paths),
            "builder": builders[idx % len(builders)],
        }
        ctx = _context(case["seed"], "general", case["skill"])
        _, build = case["builder"]
        output = build(ctx)
        _assert_general_direct_closing(output)
        checked += 1

    assert checked == 150


def test_px2m_general_direct_polish_does_not_touch_scene_specific_direct_answers():
    for scene, expected_marker in [
        ("management", "目标、责任"),
        ("sales", "客户"),
        ("negotiation", "底线"),
        ("emotion", "情绪"),
    ]:
        ctx = _context(1, scene, "skills_off")
        output = _minimum_answer(ctx, ctx.runtime_trace)
        assert output.startswith("直接结论：")
        assert expected_marker in output
        assert "做完再看要不要展开" not in output
