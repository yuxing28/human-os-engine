from __future__ import annotations

import random

from graph.nodes.answer_first_takeover import _minimum_answer
from graph.nodes.fallback_contract_takeover import _minimum_fallback_answer
from graph.nodes.internal_strategy_leak_takeover import _minimum_final_answer
from graph.nodes.repair_contract_takeover import _minimum_repair_answer
from graph.nodes.response_obligation_observer import classify_deliverable_observed
from schemas.context import Context


def _context(seed: int, skill_state: str) -> Context:
    ctx = Context(session_id=f"px2l-management-steps-{seed}")
    ctx.primary_scene = "management"
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


def _assert_management_steps(output: str) -> None:
    assert output.strip()
    assert classify_deliverable_observed(output) == "steps"
    assert "1." in output and "2." in output and "3." in output
    assert "目标压成一句话" in output or "共同目标压成一句话" in output
    assert "负责人和交付物" in output
    assert "复盘时间" in output
    assert "卡点" in output or "阻塞点" in output
    assert "固定检查节奏" not in output
    assert "把责任拆到人" not in output
    assert "你想" not in output
    assert not output.strip().endswith("？")
    assert len(output) <= 210


def test_px2l_random_management_steps_are_actionable_and_less_stiff():
    rng = random.Random(20260510)
    speech_acts = [
        "ask_management_steps",
        "ask_execution_plan",
        "ask_team_action",
        "ask_how_to_execute",
        "ask_next_management_actions",
        "ask_operational_path",
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
                    "expected_deliverable": "steps",
                    "user_goal": "补一个团队执行动作顺序",
                    "observation_basis": {"route_scene": "management"},
                },
            ),
        ),
    ]

    checked = 0
    for idx in range(150):
        case = {
            "seed": 2026051000 + idx,
            "speech_act": rng.choice(speech_acts),
            "tone": rng.choice(tones),
            "skill": rng.choice(skills),
            "path": rng.choice(paths),
            "builder": builders[idx % len(builders)],
        }
        ctx = _context(case["seed"], case["skill"])
        _, build = case["builder"]
        output = build(ctx)
        _assert_management_steps(output)
        checked += 1

    assert checked == 150


def test_px2l_management_steps_polish_does_not_touch_options_or_other_scenes():
    ctx = _context(1, "skills_off")
    ctx.runtime_trace["response_obligation"]["expected_deliverable"] = "options"
    options_output = _minimum_answer(ctx, ctx.runtime_trace)
    assert classify_deliverable_observed(options_output) == "options"
    assert "负责人和交付物" not in options_output

    sales_ctx = Context(session_id="px2l-sales-boundary")
    sales_ctx.primary_scene = "sales"
    object.__setattr__(
        sales_ctx,
        "runtime_trace",
        {
            "response_obligation": {"expected_deliverable": "steps", "answer_first_required": True},
            "final_answer_observed": {"deliverable_observed": "question_only", "output_satisfies_obligation": False},
        },
    )
    sales_steps = _minimum_answer(sales_ctx, sales_ctx.runtime_trace)
    assert classify_deliverable_observed(sales_steps) == "steps"
    assert "负责人和交付物" not in sales_steps
