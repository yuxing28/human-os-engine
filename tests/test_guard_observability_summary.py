from scripts.testing.guard_observability_summary import build_overview


def test_build_overview_should_mark_ready_when_all_reports_pass():
    eval_report = {
        "repeats": 3,
        "sample_size": 8,
        "avg_strategy_delta": 0.8,
        "avg_delivery_delta": 0.6,
        "regressions": [],
        "scene_process_summary": {
            "sales": {
                "progress_entries": 3,
                "progress_entries_with_order": 2,
                "progress_entries_with_injected_order": 1,
                "entries_with_failure_avoid": 2,
                "avg_failure_avoid_hit_rate": 0.67,
                "entries_with_memory_failure_hint": 2,
                "entries_with_memory_digest_hint": 1,
                "entries_with_memory_decision_hint": 3,
                "avg_memory_failure_hint_hit_rate": 0.67,
                "avg_memory_digest_hint_hit_rate": 0.33,
                "avg_memory_decision_hint_hit_rate": 1.0,
            },
            "emotion": {
                "progress_entries": 1,
                "progress_entries_with_order": 1,
                "progress_entries_with_injected_order": 0,
                "entries_with_failure_avoid": 1,
                "avg_failure_avoid_hit_rate": 0.5,
                "entries_with_memory_failure_hint": 1,
                "entries_with_memory_digest_hint": 1,
                "entries_with_memory_decision_hint": 1,
                "avg_memory_failure_hint_hit_rate": 0.5,
                "avg_memory_digest_hint_hit_rate": 0.5,
                "avg_memory_decision_hint_hit_rate": 0.5,
            },
        },
    }
    merge_report = {
        "overall_passed": True,
        "steps": [
            {"name": "x"},
            {
                "name": "沙盒性能趋势门禁",
                "status": "warn",
                "reasons": ["场景 sales 相比近5次基线明显变慢"],
                "meta": {
                    "slow_scene_count": 1,
                    "scene_recent_samples": {"sales": [50.0, 52.0, 51.0]},
                    "slow_scene_details": [
                        {
                            "scene": "sales",
                            "recent_samples_seconds": [50.0, 52.0, 51.0],
                            "triage_hint": {"probe_order": ["step2_goal", "step8_execution", "step6_strategy"]},
                        }
                    ],
                },
            },
        ],
    }
    release_report = {"overall_passed": True, "steps": [{"name": "y"}]}

    overview = build_overview(eval_report, merge_report, release_report)
    assert overview["ready_for_release"] is True
    assert overview["missing_reports"] == []
    assert overview["steps"]["eval_observability"]["passed"] is True
    assert overview["steps"]["eval_observability"]["progress_entries"] == 4
    assert overview["steps"]["eval_observability"]["progress_entries_with_order"] == 3
    assert overview["steps"]["eval_observability"]["progress_entries_with_injected_order"] == 1
    assert overview["steps"]["eval_observability"]["progress_order_coverage"] == 0.75
    assert overview["steps"]["eval_observability"]["entries_with_failure_avoid"] == 3
    assert overview["steps"]["eval_observability"]["avg_failure_avoid_hit_rate"] == 0.58
    assert overview["steps"]["eval_observability"]["entries_with_memory_failure_hint"] == 3
    assert overview["steps"]["eval_observability"]["entries_with_memory_digest_hint"] == 2
    assert overview["steps"]["eval_observability"]["entries_with_memory_decision_hint"] == 4
    assert overview["steps"]["eval_observability"]["avg_memory_failure_hint_hit_rate"] == 0.58
    assert overview["steps"]["eval_observability"]["avg_memory_digest_hint_hit_rate"] == 0.42
    assert overview["steps"]["eval_observability"]["avg_memory_decision_hint_hit_rate"] == 0.75
    assert overview["steps"]["merge_gate"]["passed"] is True
    assert overview["steps"]["merge_gate"]["sandbox_trend"]["status"] == "warn"
    assert overview["steps"]["merge_gate"]["sandbox_trend"]["slow_scene_count"] == 1
    assert overview["steps"]["merge_gate"]["sandbox_trend"]["scene_recent_samples"]["sales"] == [50.0, 52.0, 51.0]
    assert overview["steps"]["merge_gate"]["sandbox_trend"]["slow_scene_details"][0]["triage_hint"]["probe_order"] == [
        "step2_goal",
        "step8_execution",
        "step6_strategy",
    ]
    assert overview["steps"]["merge_gate"]["sandbox_trend"]["is_red"] is True
    assert overview["steps"]["release_guard"]["passed"] is True


def test_build_overview_should_handle_missing_reports():
    eval_report = {
        "repeats": 3,
        "sample_size": 8,
        "avg_strategy_delta": 0.2,
        "avg_delivery_delta": 0.1,
        "regressions": [],
        "scene_process_summary": {},
    }

    overview = build_overview(eval_report, None, None)
    assert overview["ready_for_release"] is False
    assert "merge_gate_report.json" in overview["missing_reports"]
    assert "release_guard_report.json" in overview["missing_reports"]
    assert overview["steps"]["merge_gate"]["exists"] is False
    assert overview["steps"]["release_guard"]["exists"] is False
    assert overview["steps"]["merge_gate"]["sandbox_trend"]["status"] is None
    assert overview["steps"]["merge_gate"]["sandbox_trend"]["is_red"] is None
    assert overview["steps"]["eval_observability"]["progress_order_coverage"] == 0.0
    assert overview["steps"]["eval_observability"]["entries_with_failure_avoid"] == 0
    assert overview["steps"]["eval_observability"]["avg_failure_avoid_hit_rate"] == 0.0
    assert overview["steps"]["eval_observability"]["entries_with_memory_failure_hint"] == 0
    assert overview["steps"]["eval_observability"]["avg_memory_failure_hint_hit_rate"] == 0.0
