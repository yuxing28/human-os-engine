import time
from pathlib import Path

from scripts.run_merge_gate import evaluate_observability_report, resolve_existing_path


def _base_report() -> dict:
    return {
        "timestamp": time.time(),
        "repeats": 3,
        "sample_size": 8,
        "avg_strategy_delta": 0.5,
        "avg_delivery_delta": 0.4,
        "regressions": [],
        "failure_code_distribution": {},
        "scene_process_summary": {
            "sales": {
                "entries": 6,
                "avg_strategy_delta": 0.5,
                "avg_delivery_delta": 0.4,
                "avg_repeats": 3.0,
                "entries_with_failure_runs": 0,
                "degraded_entries": 0,
                "regression_entries": 0,
            }
        },
    }


def test_evaluate_observability_report_should_pass_on_healthy_report():
    passed, reasons = evaluate_observability_report(_base_report())
    assert passed is True
    assert reasons == []


def test_evaluate_observability_report_should_fail_on_regressions():
    report = _base_report()
    report["regressions"] = ["sales_rational_r1"]
    passed, reasons = evaluate_observability_report(report, max_regressions=0)
    assert passed is False
    assert any("回归条目超限" in r for r in reasons)


def test_evaluate_observability_report_should_fail_on_stale_report():
    report = _base_report()
    report["timestamp"] = time.time() - 72 * 3600
    passed, reasons = evaluate_observability_report(report, max_report_age_hours=24)
    assert passed is False
    assert any("评测报告过旧" in r for r in reasons)


def test_resolve_existing_path_should_return_first_existing_path(tmp_path: Path):
    p1 = tmp_path / "missing.json"
    p2 = tmp_path / "exists.json"
    p2.write_text("{}", encoding="utf-8")

    picked = resolve_existing_path([str(p1), str(p2)])
    assert picked == str(p2)


def test_resolve_existing_path_should_return_empty_when_all_missing(tmp_path: Path):
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"

    picked = resolve_existing_path([str(p1), str(p2)])
    assert picked == ""
