import json

from scripts.testing import compare_standardization_daily_loop_history as compare


def test_load_reports_should_return_empty_when_archive_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(compare, "ARCHIVE_DIR", tmp_path / "missing")

    assert compare._load_reports() == []


def test_main_should_print_difference_between_latest_two(tmp_path, monkeypatch, capsys):
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    monkeypatch.setattr(compare, "ARCHIVE_DIR", archive_dir)

    latest = {
        "started_at": "2026-04-18T00:00:00+00:00",
        "all_passed": True,
        "elapsed_seconds": 41.0,
        "results": [
            {"label": "输出", "passed": 60},
            {"label": "记忆", "passed": 23},
            {"label": "进化/场景加载", "passed": 29},
        ],
    }
    previous = {
        "started_at": "2026-04-17T00:00:00+00:00",
        "all_passed": False,
        "elapsed_seconds": 42.5,
        "results": [
            {"label": "输出", "passed": 59},
            {"label": "记忆", "passed": 22},
            {"label": "进化/场景加载", "passed": 28},
        ],
    }
    (archive_dir / "standardization_daily_loop_report_20260418_000000.json").write_text(
        json.dumps(latest, ensure_ascii=False),
        encoding="utf-8",
    )
    (archive_dir / "standardization_daily_loop_report_20260417_000000.json").write_text(
        json.dumps(previous, ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = compare.main()
    out = capsys.readouterr().out

    assert exit_code == 0
    assert "最近两次标准化日常循环对比" in out
    assert "输出: +1" in out
    assert "记忆: +1" in out
    assert "进化/场景加载: +1" in out
    assert "总耗时: -1.5s" in out
