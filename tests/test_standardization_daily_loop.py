import json
import sys

from scripts.testing import run_standardization_daily_loop as daily_loop


def test_run_daily_loop_should_collect_three_groups(monkeypatch):
    runs = iter(
        [
            (0, "..... 60 passed in 7.51s\n", ""),
            (0, "..... 23 passed in 14.99s\n", ""),
            (0, "..... 29 passed in 7.91s\n", ""),
        ]
    )

    def _fake_run_pytest(_tests):
        return next(runs)

    monkeypatch.setattr(daily_loop, "_run_pytest", _fake_run_pytest)

    report = daily_loop.run_daily_loop()

    assert report["all_passed"] is True
    assert len(report["results"]) == 3
    assert [item["name"] for item in report["results"]] == [
        "output",
        "memory",
        "evolution",
    ]
    assert [item["passed"] for item in report["results"]] == [60, 23, 29]
    assert [item["returncode"] for item in report["results"]] == [0, 0, 0]
    assert all(item["elapsed_seconds"] >= 0 for item in report["results"])
    assert "started_at" in report


def test_run_daily_loop_should_mark_failed_group(monkeypatch):
    runs = iter(
        [
            (0, "..... 60 passed in 7.51s\n", ""),
            (1, ".... 22 passed in 15.01s\n", "boom"),
            (0, "..... 29 passed in 7.91s\n", ""),
        ]
    )

    def _fake_run_pytest(_tests):
        return next(runs)

    monkeypatch.setattr(daily_loop, "_run_pytest", _fake_run_pytest)

    report = daily_loop.run_daily_loop()

    assert report["all_passed"] is False
    assert [item["returncode"] for item in report["results"]] == [0, 1, 0]
    assert report["results"][1]["passed"] == 22
    assert report["results"][1]["stderr_tail"] == ["boom"]


def test_save_report_should_write_report_file(tmp_path, monkeypatch):
    report_path = tmp_path / "standardization_daily_loop_report.json"
    monkeypatch.setattr(daily_loop, "REPORT_PATH", report_path)
    monkeypatch.setattr(daily_loop, "DEFAULT_REPORT_PATH", report_path)
    archive_dir = tmp_path / "archives"
    monkeypatch.setattr(daily_loop, "ARCHIVE_DIR", archive_dir)

    report = {
        "timestamp": 123456.0,
        "started_at": "2026-04-17T00:00:00+00:00",
        "elapsed_seconds": 1.23,
        "results": [
            {
                "name": "output",
                "label": "输出",
                "tests": ["tests/test_step8_output_layer.py"],
                "returncode": 0,
                "passed": 60,
                "elapsed_seconds": 7.51,
                "stdout_tail": ["60 passed in 7.51s"],
                "stderr_tail": [],
            }
        ],
        "all_passed": True,
    }

    daily_loop.save_report(report)

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["all_passed"] is True
    assert payload["started_at"] == "2026-04-17T00:00:00+00:00"
    assert payload["results"][0]["passed"] == 60
    archive_files = list(archive_dir.glob("standardization_daily_loop_report_*.json"))
    assert len(archive_files) == 1


def test_main_should_accept_custom_report_path(tmp_path, monkeypatch):
    report_path = tmp_path / "custom_report.json"
    seen = {}

    def _fake_run_daily_loop():
        return {
            "timestamp": 123.0,
            "started_at": "2026-04-17T00:00:00+00:00",
            "elapsed_seconds": 0.1,
            "results": [
                {
                    "name": "output",
                    "label": "输出",
                    "tests": ["tests/test_step8_output_layer.py"],
                    "returncode": 0,
                    "passed": 60,
                    "elapsed_seconds": 7.51,
                    "stdout_tail": ["60 passed in 7.51s"],
                    "stderr_tail": [],
                }
            ],
            "all_passed": True,
        }

    def _fake_save_report(report):
        seen["report"] = report
        seen["report_path"] = str(daily_loop.REPORT_PATH)

    monkeypatch.setattr(daily_loop, "run_daily_loop", _fake_run_daily_loop)
    monkeypatch.setattr(daily_loop, "save_report", _fake_save_report)
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_standardization_daily_loop.py", "--report-path", str(report_path)],
    )

    exit_code = daily_loop.main()

    assert exit_code == 0
    assert seen["report"]["all_passed"] is True
    assert seen["report_path"] == str(report_path)
