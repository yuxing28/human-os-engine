import json

from scripts.testing import show_standardization_daily_loop_history as history


def test_load_reports_should_return_empty_when_archive_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(history, "ARCHIVE_DIR", tmp_path / "missing")

    assert history._load_reports() == []


def test_load_reports_should_collect_latest_items(tmp_path, monkeypatch):
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    monkeypatch.setattr(history, "ARCHIVE_DIR", archive_dir)

    payload_1 = {
        "started_at": "2026-04-17T00:00:00+00:00",
        "all_passed": True,
        "elapsed_seconds": 10.0,
        "results": [
            {"label": "输出", "passed": 60},
            {"label": "记忆", "passed": 23},
            {"label": "进化/场景加载", "passed": 29},
        ],
    }
    payload_2 = {
        "started_at": "2026-04-18T00:00:00+00:00",
        "all_passed": False,
        "elapsed_seconds": 11.0,
        "results": [
            {"label": "输出", "passed": 59},
        ],
    }
    (archive_dir / "standardization_daily_loop_report_20260417_000000.json").write_text(
        json.dumps(payload_1, ensure_ascii=False),
        encoding="utf-8",
    )
    (archive_dir / "standardization_daily_loop_report_20260418_000000.json").write_text(
        json.dumps(payload_2, ensure_ascii=False),
        encoding="utf-8",
    )

    reports = history._load_reports()

    assert [item["all_passed"] for item in reports] == [False, True]
    assert reports[0]["summary"] == ["输出: 59 passed"]
    assert reports[1]["summary"] == ["输出: 60 passed", "记忆: 23 passed", "进化/场景加载: 29 passed"]
