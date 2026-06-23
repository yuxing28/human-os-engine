import json
import random
from collections import Counter
from pathlib import Path

from schemas.context import Context
from tests.test_phase_5g_r_performance_prompt_volume import _build_case, _run_perf_turn, _seed_previous_history


ARTIFACT_PATH = Path("_artifacts/r3_fix_residual_semantic_clusters.json")
R3_FIX_SEED = 2026042805
BACKLOG_MAPPING = {
    2026042811: ("ask_options", "llm_normal", "ask_options_residual"),
    2026042905: ("ask_options", "llm_normal", "ask_options_residual"),
    2026043510: ("ask_options", "question_only", "question_only_residual"),
    2026044111: ("negative_feedback", "meta_strategy", "negative_feedback_residual"),
    2026044306: ("ask_options", "llm_normal", "ask_options_residual"),
    2026044609: ("repair_request", "llm_normal", "repair_request_residual"),
    2026045104: ("ask_options", "question_only", "question_only_residual"),
    2026045109: ("ask_how_to", "question_only", "question_only_residual"),
    2026045408: ("ask_options", "fallback_question", "fallback_question_residual"),
}


def _record_artifact(section: str, payload):
    data = {}
    if ARTIFACT_PATH.exists():
        data = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    data[section] = payload
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _skill_variants():
    return ["skills_off", "default_scene_skill", "leijun_on"]


def _path_variants():
    return ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]


def _scene_variants():
    return ["management", "sales", "negotiation", "emotion", "general"]


def _tone_variants():
    return ["polite", "casual", "impatient", "confused", "annoyed"]


def _cluster_root_cause(seed: int, row: dict) -> str:
    if seed in {2026044306, 2026045408}:
        return "expected_deliverable_misclassified"
    if seed == 2026045109:
        return "expected_deliverable_misclassified"
    if seed in {2026042811, 2026042905}:
        return "takeover_condition_too_narrow"
    if seed in {2026043510, 2026045104}:
        return "takeover_condition_too_narrow"
    if seed == 2026044111:
        return "takeover_order_gap"
    if seed == 2026044609:
        return "minimum_answer_builder_insufficient" if (row["final_answer_observed"] or {}).get("output_satisfies_obligation") is not True else "takeover_condition_too_narrow"
    return "observation_gap"


def _seed_row(seed: int, rng: random.Random) -> dict:
    speech_act, output_mode, cluster = BACKLOG_MAPPING[seed]
    case = _build_case(
        rng,
        seed,
        force={
            "speech_act": speech_act,
            "scene": rng.choice(["management", "sales", "emotion"]),
            "context_state": "previous_output_generic",
            "skill_state": rng.choice(_skill_variants()),
            "path": rng.choice(_path_variants()),
        },
    )
    context = Context(session_id=f"r3-fix-seed-{seed}")
    _seed_previous_history(context, case.context_state, case.scene)
    row = _run_perf_turn(context, case, output_mode=output_mode, session_id=context.session_id)
    obligation = row["response_obligation"] or {}
    final_obs = row["final_answer_observed"] or {}
    takeovers = [
        name for name in [
            "identity_truth_takeover_used",
            "answer_first_takeover_used",
            "internal_strategy_leak_takeover_used",
            "repair_contract_takeover_used",
            "fallback_contract_takeover_used",
        ]
        if row.get(name)
    ]
    takeover_skipped_reason = []
    if not row.get("answer_first_takeover_used") and obligation.get("answer_first_required"):
        takeover_skipped_reason.extend(row.get("answer_first_violation_reason", []))
    if not row.get("repair_contract_takeover_used") and obligation.get("repair_required"):
        takeover_skipped_reason.extend(row.get("repair_contract_reason", []))
    if row.get("fallback_count", 0) > 0 and not row.get("fallback_contract_takeover_used"):
        takeover_skipped_reason.extend(row.get("fallback_contract_reason", []))
    return {
        "seed": seed,
        "speech_act": speech_act,
        "scene": case.scene,
        "tone": case.tone,
        "context_state": case.context_state,
        "output_path": row["output_path"],
        "expected_deliverable": obligation.get("expected_deliverable"),
        "answer_first_required": obligation.get("answer_first_required"),
        "clarification_allowed": obligation.get("clarification_allowed"),
        "final_answer_observed.deliverable_observed": final_obs.get("deliverable_observed"),
        "output_satisfies_obligation": final_obs.get("output_satisfies_obligation"),
        "takeover_triggered": takeovers,
        "takeover_skipped_reason": takeover_skipped_reason,
        "failure_cluster": cluster,
        "root_cause_type": _cluster_root_cause(seed, row),
        "generated_input": case.generated_input,
    }


def test_r3_fix_backlog_seed_replay_and_attribution():
    rng = random.Random(R3_FIX_SEED)
    rows = [_seed_row(seed, rng) for seed in BACKLOG_MAPPING]
    _record_artifact("backlog_seed_rows", rows)
    satisfied = sum(1 for row in rows if row["output_satisfies_obligation"] is True)
    assert satisfied >= 8
    assert next(row for row in rows if row["seed"] == 2026045109)["expected_deliverable"] in {"framework", "steps"}


def test_r3_fix_ask_options_residual_fuzz():
    rng = random.Random(R3_FIX_SEED + 1)
    rows = []
    modes = ["llm_normal", "question_only", "fallback_question", "meta_strategy"]
    for index in range(150):
        case = _build_case(
            rng,
            R3_FIX_SEED + 1000 + index,
            force={
                "speech_act": "ask_options",
                "scene": rng.choice(_scene_variants()),
                "tone": rng.choice(_tone_variants()),
                "context_state": rng.choice(["no_previous_task", "previous_output_generic", "previous_output_question_first"]),
                "skill_state": rng.choice(_skill_variants()),
                "path": rng.choice(_path_variants()),
            },
        )
        context = Context(session_id=f"r3-fix-options-{index}")
        _seed_previous_history(context, case.context_state, case.scene)
        row = _run_perf_turn(context, case, output_mode=modes[index % len(modes)], session_id=context.session_id)
        rows.append(row)
    _record_artifact("ask_options_residual_fuzz", rows[:20])
    passed = [
        row for row in rows
        if (row["response_obligation"] or {}).get("expected_deliverable") == "options"
        and (row["final_answer_observed"] or {}).get("output_satisfies_obligation") is True
        and (row["final_answer_observed"] or {}).get("deliverable_observed") == "options"
    ]
    assert len(passed) / len(rows) >= 0.90


def test_r3_fix_question_only_and_fallback_question_residual_fuzz():
    rng = random.Random(R3_FIX_SEED + 2)
    rows = []
    for index in range(120):
        speech_act = rng.choice(["ask_how_to", "ask_framework", "ask_options", "request_continue_answer", "emotional_help"])
        case = _build_case(
            rng,
            R3_FIX_SEED + 3000 + index,
            force={
                "speech_act": speech_act,
                "scene": rng.choice(_scene_variants()),
                "context_state": rng.choice(["no_previous_task", "previous_output_generic", "previous_output_question_first"]),
                "skill_state": rng.choice(_skill_variants()),
                "path": rng.choice(_path_variants()),
            },
        )
        context = Context(session_id=f"r3-fix-question-{index}")
        _seed_previous_history(context, case.context_state, case.scene)
        row = _run_perf_turn(context, case, output_mode="question_only", session_id=context.session_id)
        rows.append(row)

    fallback_rows = []
    for index in range(100):
        case = _build_case(
            rng,
            R3_FIX_SEED + 4000 + index,
            force={
                "speech_act": "ask_options",
                "scene": rng.choice(_scene_variants()),
                "context_state": rng.choice(["no_previous_task", "previous_output_generic", "previous_fallback"]),
                "skill_state": rng.choice(_skill_variants()),
                "path": rng.choice(_path_variants()),
            },
        )
        context = Context(session_id=f"r3-fix-fallback-{index}")
        _seed_previous_history(context, case.context_state, case.scene)
        row = _run_perf_turn(context, case, output_mode="fallback_question", session_id=context.session_id)
        fallback_rows.append(row)

    _record_artifact("question_only_residual_fuzz", rows[:20])
    _record_artifact("fallback_question_residual_fuzz", fallback_rows[:20])

    question_rate = sum(
        1
        for row in rows
        if (row["response_obligation"] or {}).get("clarification_allowed") != "before_answer"
        and (row["final_answer_observed"] or {}).get("deliverable_observed") != "question_only"
    ) / len(rows)
    fallback_rate = sum(
        1
        for row in fallback_rows
        if (
            row.get("fallback_contract_takeover_used") is True
            or row.get("answer_first_takeover_used") is True
        )
        and (row["final_answer_observed"] or {}).get("deliverable_observed") != "question_only"
    ) / len(fallback_rows)
    assert question_rate >= 0.90
    assert fallback_rate >= 0.90


def test_r3_fix_repair_negative_feedback_and_skill_invariants():
    rng = random.Random(R3_FIX_SEED + 3)
    rows = []
    for index in range(120):
        speech_act = "repair_request" if index % 2 == 0 else "negative_feedback"
        case = _build_case(
            rng,
            R3_FIX_SEED + 5000 + index,
            force={
                "speech_act": speech_act,
                "scene": rng.choice(_scene_variants()),
                "context_state": rng.choice(["previous_task_unsatisfied", "previous_output_generic", "previous_output_meta_strategy", "previous_output_question_first"]),
                "skill_state": rng.choice(_skill_variants()),
                "path": rng.choice(_path_variants()),
            },
        )
        context = Context(session_id=f"r3-fix-repair-{index}")
        _seed_previous_history(context, case.context_state, case.scene)
        row = _run_perf_turn(context, case, output_mode="llm_normal" if speech_act == "repair_request" else "meta_strategy", session_id=context.session_id)
        rows.append(row)

    invariant_rows = []
    for index in range(60):
        base_seed = R3_FIX_SEED + 7000 + index
        base_speech_act = rng.choice(["ask_options", "ask_how_to", "repair_request", "negative_feedback"])
        base_scene = rng.choice(["management", "sales", "emotion"])
        base_path = rng.choice(_path_variants())
        skill_results = []
        for skill_state in _skill_variants():
            case = _build_case(
                rng,
                base_seed,
                force={
                    "speech_act": base_speech_act,
                    "scene": base_scene,
                    "context_state": "previous_output_generic",
                    "skill_state": skill_state,
                    "path": base_path,
                },
            )
            context = Context(session_id=f"r3-fix-invariant-{index}-{skill_state}")
            _seed_previous_history(context, case.context_state, case.scene)
            row = _run_perf_turn(context, case, output_mode="question_only" if case.speech_act in {"ask_options", "ask_how_to"} else "meta_strategy", session_id=context.session_id)
            skill_results.append(row)
        invariant_rows.append(skill_results)

    _record_artifact("repair_negative_feedback_residual_fuzz", rows[:20])

    repair_rate = sum(
        1
        for row in rows
        if row.get("repair_contract_takeover_used") is True
        and (row["final_answer_observed"] or {}).get("output_satisfies_obligation") is True
    ) / len(rows)

    invariant_pass = 0
    invariant_total = 0
    for group in invariant_rows:
        baseline = group[0]["response_obligation"] or {}
        for row in group[1:]:
            obligation = row["response_obligation"] or {}
            invariant_total += 1
            if (
                obligation.get("expected_deliverable") == baseline.get("expected_deliverable")
                and obligation.get("answer_first_required") == baseline.get("answer_first_required")
                and obligation.get("repair_required") == baseline.get("repair_required")
            ):
                invariant_pass += 1
    _record_artifact(
        "skill_metamorphic",
        {
            "repair_rows_sample": rows[:10],
            "invariant_rate": invariant_pass / invariant_total if invariant_total else 1.0,
            "takeover_counts": dict(Counter(row.get("repair_contract_takeover_used") for row in rows)),
        },
    )

    assert repair_rate >= 0.90
    assert invariant_pass / invariant_total >= 0.95
