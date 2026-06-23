from __future__ import annotations

import random

from graph.nodes.answer_first_takeover import _minimum_answer
from graph.nodes.fallback_contract_takeover import _minimum_fallback_answer
from graph.nodes.internal_strategy_leak_takeover import _minimum_final_answer
from graph.nodes.repair_contract_takeover import _minimum_repair_answer
from graph.nodes.response_obligation_observer import classify_deliverable_observed
from schemas.context import Context


def _context(seed: int, skill_state: str) -> Context:
    ctx = Context(session_id=f"px2j-sales-script-{seed}")
    ctx.primary_scene = "sales"
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


def _hard_sales_script_score(text: str) -> int:
    hard_markers = [
        "你觉得贵",
        "谈价格",
        "压价格",
        "这笔钱换来的具体结果",
        "哪个方案更适合你",
    ]
    return sum(text.count(marker) for marker in hard_markers)


def _assert_sales_script_polished(output: str) -> None:
    assert output.strip()
    assert classify_deliverable_observed(output) == "script"
    assert "这句可以" in output
    assert "担心价格" in output
    assert "压价" in output
    assert "对应的结果" in output
    assert "推进版本" in output
    assert _hard_sales_script_score(output) == 0
    assert "我理解" not in output
    assert "我在乎" not in output
    assert "可选方案" not in output
    assert not output.strip().endswith("？")
    assert "你想" not in output
    assert len(output) <= 150


def test_px2j_random_sales_objection_scripts_stay_script_and_sound_less_stiff():
    rng = random.Random(20260508)
    speech_acts = [
        "ask_sales_reply",
        "ask_objection_script",
        "ask_price_objection_reply",
        "ask_copyable_line",
        "ask_client_says_expensive",
        "ask_how_to_reply_sales",
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
                    "user_goal": "补一个客户说贵时能直接发的话术",
                    "observation_basis": {"route_scene": "sales"},
                },
            ),
        ),
    ]

    checked = 0
    for idx in range(150):
        case = {
            "seed": 2026050800 + idx,
            "speech_act": rng.choice(speech_acts),
            "tone": rng.choice(tones),
            "skill": rng.choice(skills),
            "path": rng.choice(paths),
            "builder": builders[idx % len(builders)],
        }
        ctx = _context(case["seed"], case["skill"])
        _, build = case["builder"]
        output = build(ctx)
        _assert_sales_script_polished(output)
        checked += 1

    assert checked == 150


def test_px2j_sales_script_polish_does_not_touch_other_deliverables_or_scenes():
    ctx = _context(1, "skills_off")
    ctx.runtime_trace["response_obligation"]["expected_deliverable"] = "options"
    options_output = _minimum_answer(ctx, ctx.runtime_trace)
    assert classify_deliverable_observed(options_output) == "options"
    assert "推进版本" not in options_output

    ctx.runtime_trace["response_obligation"]["expected_deliverable"] = "framework"
    framework_output = _minimum_fallback_answer(ctx, ctx.runtime_trace)
    assert classify_deliverable_observed(framework_output) == "framework"
    assert "担心价格" not in framework_output

    emotion_ctx = Context(session_id="px2j-emotion-boundary")
    emotion_ctx.primary_scene = "emotion"
    object.__setattr__(
        emotion_ctx,
        "runtime_trace",
        {
            "response_obligation": {"expected_deliverable": "script", "answer_first_required": True},
            "final_answer_observed": {"deliverable_observed": "question_only", "output_satisfies_obligation": False},
        },
    )
    emotion_script = _minimum_answer(emotion_ctx, emotion_ctx.runtime_trace)
    assert classify_deliverable_observed(emotion_script) == "script"
    assert "担心价格" not in emotion_script
    assert "推进版本" not in emotion_script
