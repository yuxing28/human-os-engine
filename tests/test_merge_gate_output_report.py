import json
from pathlib import Path

from scripts.run_merge_gate import _init_gate_report, _record_gate_step, _save_gate_report


def test_gate_report_should_write_structured_json(tmp_path: Path):
    report = _init_gate_report()
    _record_gate_step(
        report,
        name="示例门禁",
        passed=True,
        status="pass",
        reasons=[],
        meta={"k": "v"},
    )
    report["overall_passed"] = True

    output_path = tmp_path / "merge_gate_report.json"
    _save_gate_report(report, output_path)

    data = json.loads(output_path.read_text(encoding="utf-8"))
    assert data["overall_passed"] is True
    assert isinstance(data["timestamp"], (int, float))
    assert len(data["steps"]) == 1
    assert data["steps"][0]["name"] == "示例门禁"
    assert data["steps"][0]["status"] == "pass"
    assert data["steps"][0]["meta"] == {"k": "v"}
