from types import SimpleNamespace

from scripts.run_release_guard import _decode_output, build_eval_command, build_gate_command


def test_build_eval_command_should_include_repeats_and_limit():
    cmd = build_eval_command(3, 8)
    assert "scripts/testing/eval_observability_daily_check.py" in cmd
    assert "--repeats" in cmd
    assert "--limit" in cmd
    assert cmd[cmd.index("--repeats") + 1] == "3"
    assert cmd[cmd.index("--limit") + 1] == "8"


def test_build_gate_command_should_include_thresholds_and_skip_flag():
    args = SimpleNamespace(
        merge_gate_output_path="data/merge_gate_report.json",
        max_report_age_hours=24.0,
        min_repeats=3,
        min_sample_size=8,
        min_strategy_delta=-0.2,
        min_delivery_delta=-0.2,
        max_regressions=0,
        max_failure_codes=0,
        min_progress_entries=2,
        min_progress_order_coverage=0.5,
        min_failure_avoid_entries=2,
        min_failure_avoid_hit_rate=0.1,
        min_memory_hint_entries=2,
        min_memory_decision_hit_rate=0.1,
        strict_progress_order_gate=True,
        strict_failure_avoid_gate=True,
        strict_memory_hint_gate=True,
        sandbox_seed=20260410,
        sandbox_rounds=1,
        max_sandbox_scene_duration_seconds=45.0,
        max_sandbox_scene_duration_seconds_by_scene='{"sales":60,"emotion":80}',
        sandbox_performance_history_path="data/sandbox_performance_history.jsonl",
        sandbox_trend_window=5,
        sandbox_slowdown_ratio=0.2,
        sandbox_slowdown_absolute_seconds=5.0,
        strict_sandbox_performance_gate=True,
        strict_sandbox_performance_trend_gate=True,
        skip_report_gate=True,
        skip_doc_gate=True,
        skip_sandbox_gate=True,
    )
    cmd = build_gate_command(args)
    assert "scripts/run_merge_gate.py" in cmd
    assert "--gate-output-path" in cmd
    assert "--max-report-age-hours" in cmd
    assert "--min-sample-size" in cmd
    assert "--min-progress-entries" in cmd
    assert "--min-progress-order-coverage" in cmd
    assert "--min-failure-avoid-entries" in cmd
    assert "--min-failure-avoid-hit-rate" in cmd
    assert "--min-memory-hint-entries" in cmd
    assert "--min-memory-decision-hit-rate" in cmd
    assert "--sandbox-seed" in cmd
    assert "--sandbox-rounds" in cmd
    assert "--max-sandbox-scene-duration-seconds" in cmd
    assert "--max-sandbox-scene-duration-seconds-by-scene" in cmd
    assert cmd[cmd.index("--max-sandbox-scene-duration-seconds-by-scene") + 1] == '{"sales":60,"emotion":80}'
    assert "--sandbox-performance-history-path" in cmd
    assert "--sandbox-trend-window" in cmd
    assert "--sandbox-slowdown-ratio" in cmd
    assert "--sandbox-slowdown-absolute-seconds" in cmd
    assert "--strict-progress-order-gate" in cmd
    assert "--strict-failure-avoid-gate" in cmd
    assert "--strict-memory-hint-gate" in cmd
    assert "--strict-sandbox-performance-gate" in cmd
    assert "--strict-sandbox-performance-trend-gate" in cmd
    assert "--skip-report-gate" in cmd
    assert "--skip-doc-gate" in cmd
    assert "--skip-sandbox-gate" in cmd


def test_decode_output_should_support_utf8_and_gbk_bytes():
    assert _decode_output("发布门禁".encode("utf-8")) == "发布门禁"
    assert _decode_output("发布门禁".encode("gbk")) == "发布门禁"
