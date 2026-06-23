import json
from pathlib import Path

from scripts.run_release_guard import _init_release_report, _record_release_step, _save_release_report


def test_release_guard_report_should_write_structured_json(tmp_path: Path):
    report = _init_release_report()
    _record_release_step(
        report,
        name="评测可观测日检",
        status="pass",
        exit_code=0,
        command=["python", "scripts/testing/eval_observability_daily_check.py"],
    )
    report["overall_passed"] = True

    output_path = tmp_path / "release_guard_report.json"
    _save_release_report(report, output_path)

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["overall_passed"] is True
    assert isinstance(data["timestamp"], (int, float))
    assert len(data["steps"]) == 1
    assert data["steps"][0]["name"] == "评测可观测日检"
    assert data["steps"][0]["status"] == "pass"
    assert data["steps"][0]["exit_code"] == 0
