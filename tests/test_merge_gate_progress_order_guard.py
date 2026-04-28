from scripts.run_merge_gate import (
    evaluate_progress_order_coverage,
    evaluate_failure_avoid_coverage,
    evaluate_memory_hint_coverage,
)


def test_progress_order_gate_should_pass_when_coverage_meets_threshold():
    report = {
        "scene_process_summary": {
            "sales": {
                "progress_entries": 4,
                "progress_entries_with_order": 3,
            },
            "negotiation": {
                "progress_entries": 2,
                "progress_entries_with_order": 1,
            },
        }
    }
    passed, reasons, meta = evaluate_progress_order_coverage(
        report,
        min_progress_entries=2,
        min_progress_order_coverage=0.6,
    )
    assert passed is True
    assert reasons == []
    assert meta["progress_entries"] == 6
    assert meta["progress_entries_with_order"] == 4
    assert meta["progress_order_coverage"] == 0.67


def test_progress_order_gate_should_warn_only_when_sample_is_too_small():
    report = {
        "scene_process_summary": {
            "sales": {
                "progress_entries": 1,
                "progress_entries_with_order": 0,
            }
        }
    }
    passed, reasons, meta = evaluate_progress_order_coverage(
        report,
        min_progress_entries=2,
        min_progress_order_coverage=0.5,
    )
    assert passed is True
    assert any("样本不足" in r for r in reasons)
    assert meta["progress_entries"] == 1
    assert meta["progress_order_coverage"] == 0.0


def test_progress_order_gate_should_fail_when_coverage_too_low():
    report = {
        "scene_process_summary": {
            "sales": {
                "progress_entries": 4,
                "progress_entries_with_order": 1,
            }
        }
    }
    passed, reasons, meta = evaluate_progress_order_coverage(
        report,
        min_progress_entries=2,
        min_progress_order_coverage=0.5,
    )
    assert passed is False
    assert any("覆盖率偏低" in r for r in reasons)
    assert meta["progress_order_coverage"] == 0.25


def test_failure_avoid_gate_should_pass_when_hit_rate_meets_threshold():
    report = {
        "scene_process_summary": {
            "sales": {
                "entries": 6,
                "entries_with_failure_runs": 3,
                "entries_with_failure_avoid": 3,
                "degraded_entries": 2,
                "avg_failure_avoid_hit_rate": 0.5,
            },
            "negotiation": {
                "entries": 2,
                "entries_with_failure_runs": 1,
                "entries_with_failure_avoid": 1,
                "degraded_entries": 1,
                "avg_failure_avoid_hit_rate": 0.25,
            },
        }
    }
    passed, reasons, meta = evaluate_failure_avoid_coverage(
        report,
        min_failure_avoid_entries=2,
        min_failure_avoid_hit_rate=0.4,
    )
    assert passed is True
    assert reasons == []
    assert meta["entries_with_failure_avoid"] == 4
    assert meta["entries_with_failure_runs"] == 4
    assert meta["avg_failure_avoid_hit_rate"] == 0.44


def test_failure_avoid_gate_should_skip_when_no_failure_samples():
    report = {
        "scene_process_summary": {
            "sales": {
                "entries": 4,
                "entries_with_failure_runs": 0,
                "entries_with_failure_avoid": 1,
                "degraded_entries": 0,
                "avg_failure_avoid_hit_rate": 0.25,
            }
        }
    }
    passed, reasons, meta = evaluate_failure_avoid_coverage(
        report,
        min_failure_avoid_entries=2,
        min_failure_avoid_hit_rate=0.2,
    )
    assert passed is True
    assert reasons == []
    assert meta["entries_with_failure_avoid"] == 1
    assert meta["entries_with_failure_runs"] == 0
    assert meta["avg_failure_avoid_hit_rate"] == 0.25


def test_failure_avoid_gate_should_fail_when_hit_rate_too_low():
    report = {
        "scene_process_summary": {
            "sales": {
                "entries": 6,
                "entries_with_failure_runs": 3,
                "entries_with_failure_avoid": 3,
                "degraded_entries": 2,
                "avg_failure_avoid_hit_rate": 0.2,
            },
            "negotiation": {
                "entries": 2,
                "entries_with_failure_runs": 1,
                "entries_with_failure_avoid": 1,
                "degraded_entries": 1,
                "avg_failure_avoid_hit_rate": 0.0,
            },
        }
    }
    passed, reasons, meta = evaluate_failure_avoid_coverage(
        report,
        min_failure_avoid_entries=2,
        min_failure_avoid_hit_rate=0.2,
    )
    assert passed is False
    assert any("命中率偏低" in r for r in reasons)
    assert meta["avg_failure_avoid_hit_rate"] == 0.15


def test_failure_avoid_gate_should_warn_when_failure_samples_exist_but_hits_too_small():
    report = {
        "scene_process_summary": {
            "sales": {
                "entries": 4,
                "entries_with_failure_runs": 2,
                "entries_with_failure_avoid": 1,
                "degraded_entries": 1,
                "avg_failure_avoid_hit_rate": 0.25,
            }
        }
    }
    passed, reasons, meta = evaluate_failure_avoid_coverage(
        report,
        min_failure_avoid_entries=2,
        min_failure_avoid_hit_rate=0.2,
    )
    assert passed is True
    assert any("命中条目不足" in r for r in reasons)
    assert meta["entries_with_failure_runs"] == 2


def test_memory_hint_gate_should_pass_when_decision_hit_rate_meets_threshold():
    report = {
        "scene_process_summary": {
            "sales": {
                "entries": 6,
                "entries_with_memory_failure_hint": 3,
                "entries_with_memory_digest_hint": 2,
                "entries_with_memory_decision_hint": 3,
                "avg_memory_failure_hint_hit_rate": 0.5,
                "avg_memory_digest_hint_hit_rate": 0.3,
                "avg_memory_decision_hint_hit_rate": 0.5,
            },
            "emotion": {
                "entries": 2,
                "entries_with_memory_failure_hint": 1,
                "entries_with_memory_digest_hint": 1,
                "entries_with_memory_decision_hint": 1,
                "avg_memory_failure_hint_hit_rate": 0.2,
                "avg_memory_digest_hint_hit_rate": 0.2,
                "avg_memory_decision_hint_hit_rate": 0.2,
            },
        }
    }
    passed, reasons, meta = evaluate_memory_hint_coverage(
        report,
        min_memory_hint_entries=2,
        min_memory_decision_hit_rate=0.4,
    )
    assert passed is True
    assert reasons == []
    assert meta["entries_with_memory_decision_hint"] == 4
    assert meta["avg_memory_decision_hint_hit_rate"] == 0.42


def test_memory_hint_gate_should_warn_when_entries_too_small():
    report = {
        "scene_process_summary": {
            "sales": {
                "entries": 4,
                "degraded_entries": 1,
                "entries_with_memory_failure_hint": 1,
                "entries_with_memory_digest_hint": 1,
                "entries_with_memory_decision_hint": 1,
                "avg_memory_failure_hint_hit_rate": 0.2,
                "avg_memory_digest_hint_hit_rate": 0.2,
                "avg_memory_decision_hint_hit_rate": 0.2,
            }
        }
    }
    passed, reasons, meta = evaluate_memory_hint_coverage(
        report,
        min_memory_hint_entries=2,
        min_memory_decision_hit_rate=0.2,
    )
    assert passed is True
    assert any("命中条目不足" in r for r in reasons)
    assert meta["entries_with_memory_decision_hint"] == 1


def test_memory_hint_gate_should_skip_when_no_degraded_entries():
    report = {
        "scene_process_summary": {
            "sales": {
                "entries": 4,
                "degraded_entries": 0,
                "entries_with_memory_failure_hint": 1,
                "entries_with_memory_digest_hint": 1,
                "entries_with_memory_decision_hint": 0,
                "avg_memory_failure_hint_hit_rate": 0.25,
                "avg_memory_digest_hint_hit_rate": 0.25,
                "avg_memory_decision_hint_hit_rate": 0.0,
            }
        }
    }
    passed, reasons, meta = evaluate_memory_hint_coverage(
        report,
        min_memory_hint_entries=2,
        min_memory_decision_hit_rate=0.2,
    )
    assert passed is True
    assert reasons == []
    assert meta["degraded_entries"] == 0
    assert meta["entries_with_memory_decision_hint"] == 0


def test_memory_hint_gate_should_fail_when_decision_hit_rate_too_low():
    report = {
        "scene_process_summary": {
            "sales": {
                "entries": 6,
                "degraded_entries": 1,
                "entries_with_memory_failure_hint": 3,
                "entries_with_memory_digest_hint": 2,
                "entries_with_memory_decision_hint": 3,
                "avg_memory_failure_hint_hit_rate": 0.5,
                "avg_memory_digest_hint_hit_rate": 0.3,
                "avg_memory_decision_hint_hit_rate": 0.2,
            },
            "emotion": {
                "entries": 2,
                "degraded_entries": 1,
                "entries_with_memory_failure_hint": 1,
                "entries_with_memory_digest_hint": 1,
                "entries_with_memory_decision_hint": 1,
                "avg_memory_failure_hint_hit_rate": 0.2,
                "avg_memory_digest_hint_hit_rate": 0.2,
                "avg_memory_decision_hint_hit_rate": 0.0,
            },
        }
    }
    passed, reasons, meta = evaluate_memory_hint_coverage(
        report,
        min_memory_hint_entries=2,
        min_memory_decision_hit_rate=0.2,
    )
    assert passed is False
    assert any("命中率偏低" in r for r in reasons)
    assert meta["avg_memory_decision_hint_hit_rate"] == 0.15
