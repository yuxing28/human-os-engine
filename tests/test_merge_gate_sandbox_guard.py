from types import SimpleNamespace

from scripts.run_merge_gate import (
    SANDBOX_SCENES,
    _parse_sandbox_scene_thresholds,
    build_sandbox_smoke_commands,
    evaluate_sandbox_performance_gate,
    evaluate_sandbox_performance_trend_gate,
    evaluate_sandbox_smoke_gate,
)


def test_build_sandbox_smoke_commands_should_cover_all_core_scenes():
    commands = build_sandbox_smoke_commands(seed=20260410, rounds=1)
    scenes = [cmd[cmd.index("--scene") + 1] for cmd in commands]
    assert scenes == list(SANDBOX_SCENES)
    assert all("--no-judge" in cmd for cmd in commands)
    assert all(cmd[cmd.index("--rounds") + 1] == "1" for cmd in commands)


def test_evaluate_sandbox_smoke_gate_should_fail_when_any_scene_fails():
    def _fake_run(cmd, **kwargs):
        scene = cmd[cmd.index("--scene") + 1]
        if scene == "negotiation":
            return SimpleNamespace(returncode=1, stdout="neg fail", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    passed, reasons, meta = evaluate_sandbox_smoke_gate(seed=20260410, rounds=1, run_cmd_fn=_fake_run)
    assert passed is False
    assert any("场景 negotiation 运行失败" in r for r in reasons)
    assert len(meta) == len(SANDBOX_SCENES)
    assert any(m["scene"] == "negotiation" and m["exit_code"] == 1 for m in meta)


def test_evaluate_sandbox_performance_gate_should_pass_when_all_scenes_fast():
    run_meta = [
        {"scene": "sales", "duration_seconds": 3.2},
        {"scene": "management", "duration_seconds": 2.8},
    ]
    passed, reasons, meta = evaluate_sandbox_performance_gate(
        run_meta,
        max_scene_duration_seconds=5.0,
    )
    assert passed is True
    assert reasons == []
    assert meta["slow_scene_count"] == 0
    assert meta["max_observed_duration_seconds"] == 3.2


def test_evaluate_sandbox_performance_gate_should_fail_when_scene_too_slow():
    run_meta = [
        {"scene": "sales", "duration_seconds": 3.2},
        {"scene": "negotiation", "duration_seconds": 8.6},
    ]
    passed, reasons, meta = evaluate_sandbox_performance_gate(
        run_meta,
        max_scene_duration_seconds=5.0,
    )
    assert passed is False
    assert any("negotiation" in r and "8.60s" in r for r in reasons)
    assert meta["slow_scene_count"] == 1
    assert meta["max_observed_duration_seconds"] == 8.6


def test_evaluate_sandbox_performance_gate_should_use_scene_override_threshold():
    run_meta = [
        {"scene": "sales", "duration_seconds": 50.0},
        {"scene": "emotion", "duration_seconds": 60.0},
    ]
    passed, reasons, meta = evaluate_sandbox_performance_gate(
        run_meta,
        max_scene_duration_seconds=45.0,
        max_scene_duration_seconds_by_scene={"sales": 55.0, "emotion": 58.0},
    )
    assert passed is False
    assert len(reasons) == 1
    assert "emotion" in reasons[0]
    assert "60.00s" in reasons[0]
    assert "58.00s" in reasons[0]
    assert meta["slow_scene_count"] == 1
    assert meta["slow_scenes"] == ["emotion"]
    assert meta["max_scene_duration_seconds_by_scene"] == {"sales": 55.0, "emotion": 58.0}


def test_parse_sandbox_scene_thresholds_should_parse_valid_json():
    parsed = _parse_sandbox_scene_thresholds('{"sales": 60, "emotion": 80.5}')
    assert parsed == {"sales": 60.0, "emotion": 80.5}


def test_parse_sandbox_scene_thresholds_should_reject_unknown_scene():
    try:
        _parse_sandbox_scene_thresholds('{"unknown": 60}')
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "未知场景" in str(exc)


def test_evaluate_sandbox_performance_trend_gate_should_warn_when_significant_slowdown():
    run_meta = [
        {"scene": "sales", "duration_seconds": 70.0},
        {"scene": "emotion", "duration_seconds": 80.0},
    ]
    history_entries = [
        {"scene_durations": {"sales": 50.0, "emotion": 75.0}},
        {"scene_durations": {"sales": 52.0, "emotion": 76.0}},
        {"scene_durations": {"sales": 51.0, "emotion": 74.0}},
    ]
    passed, reasons, meta = evaluate_sandbox_performance_trend_gate(
        run_meta,
        history_entries=history_entries,
        trend_window=3,
        slowdown_ratio=0.2,
        slowdown_absolute_seconds=5.0,
    )
    assert passed is False
    assert len(reasons) == 1
    assert "sales" in reasons[0]
    assert meta["slow_scene_count"] == 1
    assert meta["slow_scene_details"][0]["scene"] == "sales"
    assert meta["slow_scene_details"][0]["recent_samples_seconds"] == [50.0, 52.0, 51.0]
    assert meta["slow_scene_details"][0]["triage_hint"]["probe_order"] == [
        "step2_goal",
        "step8_execution",
        "step6_strategy",
    ]
    assert meta["scene_recent_samples"]["sales"] == [50.0, 52.0, 51.0]
    assert meta["default_triage_probe_order"] == [
        "step2_goal",
        "step8_execution",
        "step6_strategy",
    ]


def test_evaluate_sandbox_performance_trend_gate_should_pass_when_no_significant_slowdown():
    run_meta = [
        {"scene": "sales", "duration_seconds": 54.0},
        {"scene": "emotion", "duration_seconds": 77.0},
    ]
    history_entries = [
        {"scene_durations": {"sales": 50.0, "emotion": 75.0}},
        {"scene_durations": {"sales": 52.0, "emotion": 76.0}},
        {"scene_durations": {"sales": 51.0, "emotion": 74.0}},
    ]
    passed, reasons, meta = evaluate_sandbox_performance_trend_gate(
        run_meta,
        history_entries=history_entries,
        trend_window=3,
        slowdown_ratio=0.2,
        slowdown_absolute_seconds=5.0,
    )
    assert passed is True
    assert reasons == []
    assert meta["slow_scene_count"] == 0
    assert meta["scene_recent_samples"]["sales"] == [50.0, 52.0, 51.0]
