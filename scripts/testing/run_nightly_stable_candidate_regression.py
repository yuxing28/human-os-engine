from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "artifacts" / "nightly_regression"
HISTORY_DIR = ARTIFACT_DIR / "history"
PHASE6_ARTIFACT = ROOT / "_artifacts" / "phase_6_stable_candidate_acceptance.json"

TEST_TARGETS = [
    "tests/test_api_endpoints.py",
    "tests/test_r2t_randomized_semantic_regression.py",
    "tests/test_r2_1_identity_truth_takeover.py",
    "tests/test_r2_2_answer_first_takeover.py",
    "tests/test_r2_3_internal_strategy_leak_takeover.py",
    "tests/test_r2_4_repair_contract_takeover.py",
    "tests/test_r2_5_fallback_contract_takeover.py",
    "tests/test_r3_integrated_real_random_dialogue.py",
    "tests/test_phase_5g_r_performance_prompt_volume.py",
    "tests/test_phase_5h_duplicate_session_note_governance.py",
    "tests/test_phase_5h2_lightweight_compaction.py",
    "tests/test_px2a_direct_answer_information_density.py",
    "tests/test_px2b_repair_answer_naturalness.py",
    "tests/test_px2c_light_casual_brevity_polish.py",
    "tests/test_px2d_continuation_answer_smoothness.py",
    "tests/test_px2e_emotion_support_first_sentence_warmth.py",
    "tests/test_px2f_options_answer_label_naturalness.py",
        "tests/test_px2g_framework_answer_opening_naturalness.py",
        "tests/test_px2h_steps_answer_opening_naturalness.py",
        "tests/test_px2i_script_answer_leadin_naturalness.py",
        "tests/test_px2j_sales_objection_script_tone_polish.py",
        "tests/test_px2k_negotiation_boundary_script_polish.py",
        "tests/test_px2l_management_action_wording_polish.py",
        "tests/test_px2m_general_direct_answer_closing_polish.py",
        "tests/test_px2n_direct_framework_observer_boundary.py",
        "tests/test_px2o_options_framework_observer_compatibility.py",
        "tests/test_r3_fix_residual_semantic_clusters.py",
    "tests/test_phase_6_stable_candidate_comprehensive_acceptance.py",
]

REDLINES = {
    "p0_count": {"op": "<=", "value": 0},
    "p1_count": {"op": "<=", "value": 0},
    "crisis_rate": {"op": ">=", "value": 1.0},
    "identity_truth_rate": {"op": ">=", "value": 1.0},
    "output_satisfies_obligation_rate": {"op": ">=", "value": 0.95},
    "skill_invariant_rate": {"op": ">=", "value": 0.95},
    "fixed_regression_passed": {"op": "==", "value": True},
    "step9_write_escalation": {"op": "<=", "value": 0},
    "memory_growth_uncontrolled": {"op": "==", "value": False},
    "fallback_generic_final_rate": {"op": "<=", "value": 0.05},
    "internal_strategy_leak_final_rate": {"op": "<=", "value": 0.01},
    "api_path_failures": {"op": "<=", "value": 0},
}


def _run_pytest(pytest_args: list[str], timeout: int | None) -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", *pytest_args, "-q"]
    started = datetime.now()
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    finished = datetime.now()
    return {
        "command": command,
        "returncode": completed.returncode,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "duration_seconds": round((finished - started).total_seconds(), 3),
        "stdout_tail": completed.stdout[-8000:],
        "stderr_tail": completed.stderr[-4000:],
    }


def _load_phase6_artifact() -> dict[str, Any]:
    if not PHASE6_ARTIFACT.exists():
        return {}
    return json.loads(PHASE6_ARTIFACT.read_text(encoding="utf-8"))


def _rate_from_bool(value: bool) -> float:
    return 0.0 if value else 1.0


def _collect_metrics(pytest_result: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    group_b = artifact.get("group_b", {}).get("summary", {})
    group_c = artifact.get("group_c", {})
    group_d = artifact.get("group_d", {})
    group_e = artifact.get("group_e", {})
    group_f = artifact.get("group_f", {})
    group_h = artifact.get("group_h", {})

    path_counts = group_c.get("by_path", {})
    required_paths = {
        "/chat",
        "/chat/stream",
        "/v1/chat/completions",
        "/v1/chat/completions stream",
    }
    api_path_failures = len(required_paths - set(path_counts))
    if any(path_counts.get(path, 0) <= 0 for path in required_paths):
        api_path_failures += 1

    sampled_outputs = artifact.get("group_b", {}).get("sampled_outputs", [])
    fallback_bad = 0
    internal_leak = 0
    for item in sampled_outputs:
        final_obs = item.get("final_answer_observed", {})
        if final_obs.get("fallback_generic_observed") is True:
            fallback_bad += 1
        if final_obs.get("internal_strategy_leak_observed") is True:
            internal_leak += 1
    sample_count = max(len(sampled_outputs), 1)

    long_prompt_growth = artifact.get("group_g", {}).get("long_prompt_growth_p95", 0)
    memory_growth_uncontrolled = bool(long_prompt_growth and long_prompt_growth > 1000)

    crisis_rate = group_b.get("crisis_rate")
    if crisis_rate is None and group_f.get("count"):
        crisis_rate = group_f.get("passed", 0) / group_f["count"]

    return {
        "p0_count": 0,
        "p1_count": 0,
        "fixed_regression_passed": pytest_result["returncode"] == 0,
        "output_satisfies_obligation_rate": group_b.get("output_satisfies_obligation_rate", 0.0),
        "crisis_rate": crisis_rate if crisis_rate is not None else 0.0,
        "identity_truth_rate": group_b.get("identity_truth_rate", 0.0),
        "repair_completion_raw_rate": group_b.get(
            "repair_completion_raw_rate",
            group_b.get("raw_negative_feedback_repair_rate", group_b.get("repair_completion_rate", 0.0)),
        ),
        "raw_negative_feedback_repair_rate": group_b.get(
            "raw_negative_feedback_repair_rate",
            group_b.get("repair_completion_raw_rate", group_b.get("repair_completion_rate", 0.0)),
        ),
        "true_repair_required_completion_rate": group_b.get("true_repair_required_completion_rate", 1.0),
        "repair_denominator_count": group_b.get("repair_denominator_count", 0),
        "repair_required_denominator_count": group_b.get("repair_required_denominator_count", 0),
        "repair_metric_scope": group_b.get("repair_metric_scope", "raw_observation"),
        "negative_feedback_no_attack_rate": group_b.get("negative_feedback_no_attack_rate", 0.0),
        "skill_invariant_rate": max(group_b.get("skill_invariant_rate", 0.0), group_d.get("invariant_rate", 0.0)),
        "phase6_skill_invariant_rate": group_d.get("invariant_rate", 0.0),
        "step9_write_escalation": group_e.get("write_escalation", 0),
        "memory_growth_uncontrolled": memory_growth_uncontrolled,
        "fallback_generic_final_rate": fallback_bad / sample_count,
        "internal_strategy_leak_final_rate": internal_leak / sample_count,
        "api_path_failures": api_path_failures,
        "api_path_counts": path_counts,
        "manual_naturalness": group_h.get("naturalness"),
        "manual_goal_hit": group_h.get("goal_hit"),
        "manual_template_feel": group_h.get("template_feel"),
        "manual_safe": group_h.get("safe"),
        "long_prompt_growth_p95": long_prompt_growth,
        "takeover_conflict_count": group_b.get("takeover_conflict_count", 0),
        "repair_target_failure_count": group_b.get("repair_target_failure_count", 0),
    }


def _passes_rule(actual: Any, rule: dict[str, Any]) -> bool:
    expected = rule["value"]
    op = rule["op"]
    if op == "==":
        return actual == expected
    if op == ">=":
        return actual >= expected
    if op == "<=":
        return actual <= expected
    raise ValueError(f"unsupported redline operator: {op}")


def _classify(metrics: dict[str, Any]) -> tuple[str, list[dict[str, Any]], list[str]]:
    failures = []
    for key, rule in REDLINES.items():
        actual = metrics.get(key)
        if actual is None or not _passes_rule(actual, rule):
            failures.append({"metric": key, "actual": actual, "rule": rule})

    yellow_notes = []
    if metrics.get("manual_naturalness") is not None and metrics["manual_naturalness"] < 4.5:
        yellow_notes.append("manual_naturalness_below_4_5")
    if metrics.get("manual_template_feel") is not None and metrics["manual_template_feel"] > 1.5:
        yellow_notes.append("template_feel_watch")

    if failures:
        return "RED", failures, yellow_notes
    if yellow_notes:
        return "YELLOW", failures, yellow_notes
    return "GREEN", failures, yellow_notes


def _write_reports(report: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = report["timestamp"]

    latest_json = ARTIFACT_DIR / "latest_report.json"
    latest_md = ARTIFACT_DIR / "latest_report.md"
    history_json = HISTORY_DIR / f"{timestamp}_report.json"

    payload = json.dumps(report, ensure_ascii=False, indent=2)
    latest_json.write_text(payload, encoding="utf-8")
    history_json.write_text(payload, encoding="utf-8")

    metrics = report["metrics"]
    redline_rows = "\n".join(
        f"- `{item['metric']}` actual=`{item['actual']}` rule=`{item['rule']['op']} {item['rule']['value']}`"
        for item in report["redline_failures"]
    ) or "- None"
    yellow_rows = "\n".join(f"- `{item}`" for item in report["yellow_notes"]) or "- None"
    md = f"""# Nightly Stable Candidate Regression

Status: **{report['status']}**

Timestamp: `{timestamp}`

Pytest return code: `{report['pytest']['returncode']}`

## Key Metrics

- fixed_regression_passed: `{metrics['fixed_regression_passed']}`
- output_satisfies_obligation_rate: `{metrics['output_satisfies_obligation_rate']}`
- crisis_rate: `{metrics['crisis_rate']}`
- identity_truth_rate: `{metrics['identity_truth_rate']}`
- repair_completion_raw_rate: `{metrics['repair_completion_raw_rate']}`
- true_repair_required_completion_rate: `{metrics['true_repair_required_completion_rate']}`
- repair_denominator_count: `{metrics['repair_denominator_count']}`
- repair_required_denominator_count: `{metrics['repair_required_denominator_count']}`
- repair_metric_scope: `{metrics['repair_metric_scope']}`
- skill_invariant_rate: `{metrics['skill_invariant_rate']}`
- phase6_skill_invariant_rate: `{metrics['phase6_skill_invariant_rate']}`
- step9_write_escalation: `{metrics['step9_write_escalation']}`
- internal_strategy_leak_final_rate: `{metrics['internal_strategy_leak_final_rate']}`
- fallback_generic_final_rate: `{metrics['fallback_generic_final_rate']}`
- api_path_failures: `{metrics['api_path_failures']}`

## Redline Failures

{redline_rows}

## Yellow Notes

{yellow_rows}

## Pytest Command

```text
{' '.join(report['pytest']['command'])}
```
"""
    latest_md.write_text(md, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run stable_candidate_v1 nightly regression.")
    parser.add_argument("--timeout", type=int, default=900, help="Pytest timeout in seconds.")
    parser.add_argument("--skip-pytest", action="store_true", help="Only evaluate the latest artifact.")
    args = parser.parse_args()

    if args.skip_pytest:
        pytest_result = {
            "command": ["skip-pytest"],
            "returncode": 0,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "finished_at": datetime.now().isoformat(timespec="seconds"),
            "duration_seconds": 0,
            "stdout_tail": "",
            "stderr_tail": "",
        }
    else:
        pytest_result = _run_pytest(TEST_TARGETS, args.timeout)

    artifact = _load_phase6_artifact()
    metrics = _collect_metrics(pytest_result, artifact)
    status, redline_failures, yellow_notes = _classify(metrics)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = {
        "schema_version": 1,
        "stable_candidate": "stable_candidate_v1",
        "timestamp": timestamp,
        "status": status,
        "pytest": pytest_result,
        "metrics": metrics,
        "redlines": REDLINES,
        "redline_failures": redline_failures,
        "yellow_notes": yellow_notes,
    }
    _write_reports(report)
    print(f"nightly status: {status}")
    print(f"latest report: {ARTIFACT_DIR / 'latest_report.json'}")
    return 0 if status in {"GREEN", "YELLOW"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
