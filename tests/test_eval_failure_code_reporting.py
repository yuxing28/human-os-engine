import json

from simulation import analyze_intervention
from simulation import run_eval_set
from simulation.run_eval_set import build_failure_code_distribution
from simulation.run_eval_set import pick_primary_failure_code


def test_build_failure_code_distribution_should_count_only_degraded_entries():
    results = [
        {"strategy_delta": -0.8, "delivery_delta": 0.1, "failure_code": "F02"},
        {"strategy_delta": 0.2, "delivery_delta": -0.6, "failure_code": "F02"},
        {"strategy_delta": 0.0, "delivery_delta": 0.0, "failure_code": "F07"},
        {"strategy_delta": -0.4, "delivery_delta": -0.2, "failure_code": "F01"},
        {"strategy_delta": -0.1, "delivery_delta": -0.2, "failure_code": "F10"},
    ]

    dist = build_failure_code_distribution(results, warn_threshold=-0.3)

    assert dist == {"F02": 2, "F01": 1}


def test_pick_primary_failure_code_should_ignore_noise_when_median_not_degraded():
    code = pick_primary_failure_code(
        failure_code_runs=["F10"],
        strategy_delta=0.6,
        delivery_delta=0.5,
    )

    assert code == ""


def test_pick_primary_failure_code_should_keep_code_when_median_degraded():
    code = pick_primary_failure_code(
        failure_code_runs=["F03", "F03"],
        strategy_delta=-0.2,
        delivery_delta=-0.5,
    )

    assert code == "F03"


def test_analyze_scene_should_report_failure_code_distribution(tmp_path, monkeypatch):
    skills_dir = tmp_path / "skills"
    scene_dir = skills_dir / "sales"
    scene_dir.mkdir(parents=True)

    (scene_dir / "success_spectrum.json").write_text("[]", encoding="utf-8")
    (scene_dir / "counter_examples.json").write_text(
        """
[
  {"goal":"g1","strategy":"s1","failure_type":"timing_error","failure_code":"F02","timestamp":100},
  {"goal":"g1","strategy":"s1","failure_type":"timing_error","failure_code":"F02","timestamp":120},
  {"goal":"g1","strategy":"s2","failure_type":"narrative_error","failure_code":"F03","timestamp":130}
]
        """.strip(),
        encoding="utf-8",
    )

    monkeypatch.setattr(analyze_intervention, "SKILLS_DIR", skills_dir)
    monkeypatch.setattr(analyze_intervention.time, "time", lambda: 200)

    result = analyze_intervention.analyze_scene("sales")

    assert result["failure_by_code"]["F02"] == 2
    assert result["failure_by_code"]["F03"] == 1
    assert result["hint_code_triggered"]["F02"] == 2


def test_save_report_should_include_failure_code_distribution(tmp_path, monkeypatch):
    report_path = tmp_path / "eval_report.json"
    monkeypatch.setattr(run_eval_set, "REPORT_PATH", report_path)

    results = [
        {
            "id": "t1",
            "scene": "sales",
            "strategy_delta": -0.8,
            "delivery_delta": 0.0,
            "failure_code": "F02",
        },
        {
            "id": "t2",
            "scene": "sales",
            "strategy_delta": 0.0,
            "delivery_delta": 0.0,
            "failure_code": "F01",
        },
    ]

    run_eval_set.save_report(results, repeats=2)

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["repeats"] == 2
    assert payload["failure_code_distribution"] == {"F02": 1}


def test_run_eval_set_should_default_to_three_repeats(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        run_eval_set,
        "load_eval_set",
        lambda: [{"id": "t1", "scene": "sales", "persona": "理性型客户", "round": 1, "input": "x", "gold_strategy": 8, "gold_delivery": 8}],
    )

    def _fake_run_single_turn(entry, repeats=0):
        captured["repeats"] = repeats
        return {
            "id": entry["id"],
            "scene": entry["scene"],
            "persona": entry["persona"],
            "round": entry["round"],
            "input": entry["input"],
            "gold_strategy": entry["gold_strategy"],
            "gold_delivery": entry["gold_delivery"],
            "actual_strategy": 8.0,
            "actual_delivery": 8.0,
            "actual_strategy_runs": [8.0, 8.0, 8.0],
            "actual_delivery_runs": [8.0, 8.0, 8.0],
            "failure_code": "",
            "failure_code_runs": [],
            "repeats": repeats,
            "strategy_delta": 0.0,
            "delivery_delta": 0.0,
            "tags": [],
        }

    monkeypatch.setattr(run_eval_set, "run_single_turn", _fake_run_single_turn)

    results = run_eval_set.run_eval_set()

    assert captured["repeats"] == 3
    assert results[0]["repeats"] == 3
