import sys
from types import SimpleNamespace
import json

from simulation import run_eval_set


def test_run_single_turn_should_keep_process_observability_fields(monkeypatch):
    entry = {
        "id": "sales_case_1",
        "scene": "sales",
        "persona": "理性型客户",
        "round": 1,
        "input": "我想推进成交，但客户一直犹豫",
        "gold_strategy": 8.0,
        "gold_delivery": 6.0,
        "tags": ["sales", "hesitant"],
    }

    strategy_scores = [7.0, 9.0, 8.0]
    delivery_scores = [6.0, 5.0, 7.0]

    class FakeRunner:
        call_idx = 0

        def __init__(self, *_args, **_kwargs):
            pass

        def run_conversation(self, **_kwargs):
            idx = FakeRunner.call_idx
            FakeRunner.call_idx += 1
            turn = SimpleNamespace(
                strategy_score=strategy_scores[idx],
                delivery_score=delivery_scores[idx],
                judge_result={"quality": {"guidance": 8}},
                system_output=f"output-{idx}",
                output_layers={
                    "order_source": "skeleton_injected" if idx == 0 else "no_order_marker",
                    "failure_avoid_codes": ["F03"] if idx in {0, 2} else [],
                    "memory_hint_signals": {
                        "failure_avoid_hint": idx in {0, 2},
                        "experience_digest_hint": idx in {0, 1},
                        "decision_experience_hint": True,
                    },
                },
            )
            return SimpleNamespace(turns=[turn])

    monkeypatch.setattr("simulation.sandbox_core.MultiTurnSandboxRunner", FakeRunner)

    def _fake_infer_failure_code(**_kwargs):
        return SimpleNamespace(value="F03")

    monkeypatch.setitem(
        sys.modules,
        "modules.L5.counter_example_lib",
        SimpleNamespace(infer_failure_code=_fake_infer_failure_code),
    )

    result = run_eval_set.run_single_turn(entry, repeats=3)

    assert result["repeats"] == 3
    assert result["actual_strategy_runs"] == [7.0, 9.0, 8.0]
    assert result["actual_delivery_runs"] == [6.0, 5.0, 7.0]
    assert result["actual_strategy"] == 8.0
    assert result["actual_delivery"] == 6.0
    assert result["progress_request"] is True
    assert result["output_order_marker_runs"] == [False, False, False]
    assert result["output_order_source_runs"] == ["skeleton_injected", "no_order_marker", "no_order_marker"]
    assert result["output_order_hit_rate"] == 0.0
    assert result["output_order_injected_hit_rate"] == 0.33
    assert result["failure_avoid_code_runs"] == [["F03"], [], ["F03"]]
    assert result["failure_avoid_hit_rate"] == 0.67
    assert result["memory_failure_hint_hit_rate"] == 0.67
    assert result["memory_digest_hint_hit_rate"] == 0.67
    assert result["memory_decision_hint_hit_rate"] == 1.0
    # 中位数不退化时，不挂主失败码；但过程 failure_code_runs 仍要保留
    assert result["failure_code"] == ""
    assert result["failure_code_runs"] == ["F03", "F03", "F03"]


def test_run_eval_set_should_keep_error_entry_process_shape(monkeypatch):
    monkeypatch.setattr(
        run_eval_set,
        "load_eval_set",
        lambda: [
            {
                "id": "err_case",
                "scene": "sales",
                "persona": "理性型客户",
                "round": 1,
                "input": "x",
                "gold_strategy": 8.0,
                "gold_delivery": 7.0,
                "tags": ["err"],
            }
        ],
    )

    def _raise_error(_entry, repeats=0):
        raise RuntimeError("mock eval error")

    monkeypatch.setattr(run_eval_set, "run_single_turn", _raise_error)

    results = run_eval_set.run_eval_set(repeats=3)
    row = results[0]

    assert row["id"] == "err_case"
    assert row["repeats"] == 3
    assert row["actual_strategy_runs"] == []
    assert row["actual_delivery_runs"] == []
    assert row["output_order_marker_runs"] == []
    assert row["output_order_source_runs"] == []
    assert row["output_order_hit_rate"] == 0.0
    assert row["output_order_injected_hit_rate"] == 0.0
    assert row["failure_avoid_code_runs"] == []
    assert row["failure_avoid_hit_rate"] == 0.0
    assert row["memory_hint_signal_runs"] == []
    assert row["memory_failure_hint_hit_rate"] == 0.0
    assert row["memory_digest_hint_hit_rate"] == 0.0
    assert row["memory_decision_hint_hit_rate"] == 0.0
    assert row["failure_code_runs"] == []
    assert row["error"] == "mock eval error"


def test_save_report_should_keep_report_contract_for_results_fields(tmp_path, monkeypatch):
    report_path = tmp_path / "eval_report.json"
    monkeypatch.setattr(run_eval_set, "REPORT_PATH", report_path)

    rows = [
        {
            "id": "case_ok",
            "scene": "sales",
            "persona": "理性型客户",
            "round": 1,
            "input": "x",
            "gold_strategy": 8.0,
            "gold_delivery": 7.0,
            "actual_strategy": 8.0,
            "actual_delivery": 7.0,
            "actual_strategy_runs": [7.0, 8.0, 9.0],
            "actual_delivery_runs": [6.0, 7.0, 8.0],
            "progress_request": True,
            "output_order_marker_runs": [True, True, False],
            "output_order_source_runs": ["model_explicit_order", "model_explicit_order", "no_order_marker"],
            "output_order_hit_rate": 0.67,
            "output_order_injected_hit_rate": 0.0,
            "failure_avoid_code_runs": [["F03"], [], ["F03"]],
            "failure_avoid_hit_rate": 0.67,
            "memory_hint_signal_runs": [
                {"failure_avoid_hint": True, "experience_digest_hint": True, "decision_experience_hint": True},
                {"failure_avoid_hint": False, "experience_digest_hint": True, "decision_experience_hint": True},
                {"failure_avoid_hint": True, "experience_digest_hint": False, "decision_experience_hint": True},
            ],
            "memory_failure_hint_hit_rate": 0.67,
            "memory_digest_hint_hit_rate": 0.67,
            "memory_decision_hint_hit_rate": 1.0,
            "failure_code": "",
            "failure_code_runs": ["F03"],
            "repeats": 3,
            "strategy_delta": 0.0,
            "delivery_delta": 0.0,
            "tags": ["sales"],
        },
        {
            "id": "case_err",
            "scene": "emotion",
            "persona": "焦虑型",
            "round": 1,
            "input": "y",
            "gold_strategy": 7.0,
            "gold_delivery": 7.0,
            "actual_strategy": 0.0,
            "actual_delivery": 0.0,
            "actual_strategy_runs": [],
            "actual_delivery_runs": [],
            "progress_request": False,
            "output_order_marker_runs": [],
            "output_order_source_runs": [],
            "output_order_hit_rate": 0.0,
            "output_order_injected_hit_rate": 0.0,
            "failure_avoid_code_runs": [],
            "failure_avoid_hit_rate": 0.0,
            "memory_hint_signal_runs": [],
            "memory_failure_hint_hit_rate": 0.0,
            "memory_digest_hint_hit_rate": 0.0,
            "memory_decision_hint_hit_rate": 0.0,
            "failure_code": "",
            "failure_code_runs": [],
            "repeats": 3,
            "strategy_delta": -7.0,
            "delivery_delta": -7.0,
            "tags": ["emotion"],
            "error": "mock failure",
        },
    ]

    run_eval_set.save_report(rows, repeats=3)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    for key in [
        "timestamp",
        "repeats",
        "total_entries",
        "avg_strategy_delta",
        "avg_delivery_delta",
        "regressions",
        "failure_code_distribution",
        "scene_process_summary",
        "results",
    ]:
        assert key in payload

    assert payload["scene_process_summary"]["sales"]["entries"] == 1
    assert payload["scene_process_summary"]["sales"]["entries_with_failure_runs"] == 1
    assert payload["scene_process_summary"]["sales"]["entries_with_failure_avoid"] == 1
    assert payload["scene_process_summary"]["sales"]["avg_failure_avoid_hit_rate"] == 0.67
    assert payload["scene_process_summary"]["sales"]["entries_with_memory_failure_hint"] == 1
    assert payload["scene_process_summary"]["sales"]["entries_with_memory_digest_hint"] == 1
    assert payload["scene_process_summary"]["sales"]["entries_with_memory_decision_hint"] == 1
    assert payload["scene_process_summary"]["sales"]["avg_memory_failure_hint_hit_rate"] == 0.67
    assert payload["scene_process_summary"]["sales"]["avg_memory_digest_hint_hit_rate"] == 0.67
    assert payload["scene_process_summary"]["sales"]["avg_memory_decision_hint_hit_rate"] == 1.0
    assert payload["scene_process_summary"]["sales"]["progress_entries"] == 1
    assert payload["scene_process_summary"]["sales"]["progress_entries_with_order"] == 1
    assert payload["scene_process_summary"]["sales"]["progress_entries_with_injected_order"] == 0
    assert payload["scene_process_summary"]["sales"]["progress_order_coverage"] == 1.0
    assert payload["scene_process_summary"]["emotion"]["entries"] == 1
    assert payload["scene_process_summary"]["emotion"]["entries_with_failure_avoid"] == 0
    assert payload["scene_process_summary"]["emotion"]["entries_with_memory_failure_hint"] == 0
    assert payload["scene_process_summary"]["emotion"]["regression_entries"] == 1
    assert payload["scene_process_summary"]["emotion"]["progress_entries"] == 0

    first = payload["results"][0]
    for key in [
        "actual_strategy_runs",
        "actual_delivery_runs",
        "progress_request",
        "output_order_marker_runs",
        "output_order_source_runs",
        "output_order_hit_rate",
        "output_order_injected_hit_rate",
        "failure_avoid_code_runs",
        "failure_avoid_hit_rate",
        "memory_hint_signal_runs",
        "memory_failure_hint_hit_rate",
        "memory_digest_hint_hit_rate",
        "memory_decision_hint_hit_rate",
        "failure_code_runs",
        "repeats",
        "strategy_delta",
        "delivery_delta",
    ]:
        assert key in first


def test_print_summary_should_include_scene_process_summary(capsys):
    rows = [
        {
            "id": "case_ok",
            "scene": "sales",
            "strategy_delta": 0.2,
            "delivery_delta": 0.1,
            "progress_request": True,
            "output_order_hit_rate": 1.0,
            "output_order_injected_hit_rate": 0.0,
            "failure_code": "",
            "failure_code_runs": ["F03"],
            "failure_avoid_code_runs": [["F03"]],
            "failure_avoid_hit_rate": 1.0,
            "memory_failure_hint_hit_rate": 1.0,
            "memory_digest_hint_hit_rate": 1.0,
            "memory_decision_hint_hit_rate": 1.0,
            "repeats": 3,
        },
        {
            "id": "case_warn",
            "scene": "emotion",
            "strategy_delta": -0.4,
            "delivery_delta": -0.1,
            "progress_request": False,
            "output_order_hit_rate": 0.0,
            "output_order_injected_hit_rate": 0.0,
            "failure_code": "F02",
            "failure_code_runs": ["F02"],
            "failure_avoid_code_runs": [],
            "failure_avoid_hit_rate": 0.0,
            "memory_failure_hint_hit_rate": 0.0,
            "memory_digest_hint_hit_rate": 0.0,
            "memory_decision_hint_hit_rate": 0.0,
            "repeats": 3,
        },
    ]

    run_eval_set.print_summary(rows)
    out = capsys.readouterr().out

    assert "场景过程汇总" in out
    assert "sales: entries=1" in out
    assert "emotion: entries=1" in out
    assert "avg_repeats=3.00" in out


def test_build_scene_process_summary_should_include_progress_order_coverage():
    rows = [
        {
            "id": "s1",
            "scene": "sales",
            "strategy_delta": 0.1,
            "delivery_delta": 0.1,
            "repeats": 3,
            "failure_code_runs": [],
            "failure_avoid_code_runs": [["F03"]],
            "failure_avoid_hit_rate": 1.0,
            "memory_failure_hint_hit_rate": 1.0,
            "memory_digest_hint_hit_rate": 1.0,
            "memory_decision_hint_hit_rate": 1.0,
            "progress_request": True,
            "output_order_hit_rate": 1.0,
            "output_order_injected_hit_rate": 1.0,
        },
        {
            "id": "s2",
            "scene": "sales",
            "strategy_delta": 0.2,
            "delivery_delta": 0.2,
            "repeats": 3,
            "failure_code_runs": [],
            "failure_avoid_code_runs": [],
            "failure_avoid_hit_rate": 0.0,
            "memory_failure_hint_hit_rate": 0.0,
            "memory_digest_hint_hit_rate": 0.0,
            "memory_decision_hint_hit_rate": 0.0,
            "progress_request": True,
            "output_order_hit_rate": 0.0,
            "output_order_injected_hit_rate": 0.0,
        },
    ]

    summary = run_eval_set.build_scene_process_summary(rows)
    sales = summary["sales"]
    assert sales["progress_entries"] == 2
    assert sales["progress_entries_with_order"] == 1
    assert sales["progress_entries_with_injected_order"] == 1
    assert sales["progress_order_coverage"] == 0.5
    assert sales["entries_with_failure_avoid"] == 1
    assert sales["avg_failure_avoid_hit_rate"] == 0.5
    assert sales["entries_with_memory_failure_hint"] == 1
    assert sales["entries_with_memory_digest_hint"] == 1
    assert sales["entries_with_memory_decision_hint"] == 1
    assert sales["avg_memory_failure_hint_hit_rate"] == 0.5
