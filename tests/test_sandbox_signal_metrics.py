from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

from scripts.testing import run_large_cycle_loop as large_cycle
from simulation import run_sandbox_50x20 as sandbox


def test_large_cycle_run_command_should_capture_output_without_pipe_deadlock(tmp_path: Path) -> None:
    script = tmp_path / "print_output.py"
    script.write_text(
        "import sys\nprint('hello stdout')\nprint('hello stderr', file=sys.stderr)\n",
        encoding="utf-8",
    )

    code, stdout, stderr, elapsed, timed_out = large_cycle._run_command(
        [sys.executable, str(script)],
        timeout=10,
    )

    assert code == 0
    assert timed_out is False
    assert elapsed >= 0
    assert "hello stdout" in stdout
    assert "hello stderr" in stderr


def test_large_cycle_run_command_should_timeout_cleanly(tmp_path: Path) -> None:
    script = tmp_path / "sleep_long.py"
    script.write_text("import time\ntime.sleep(5)\n", encoding="utf-8")

    code, stdout, stderr, elapsed, timed_out = large_cycle._run_command(
        [sys.executable, str(script)],
        timeout=1,
    )

    assert code == 124
    assert timed_out is True
    assert stdout == ""
    assert stderr == ""
    assert elapsed >= 1


def test_large_cycle_smoke_plan_should_stay_short() -> None:
    plan = large_cycle._phase_plan(smoke=True)

    assert [phase["name"] for phase in plan] == ["gate", "sandbox_probe"]
    sandbox_phase = plan[1]
    assert sandbox_phase["scenes"] == ["management"]
    assert sandbox_phase["conversations"] == 1
    assert sandbox_phase["rounds"] == 2
    assert sandbox_phase["timeout"] <= 600


def test_large_cycle_should_build_sandbox_review_outputs(tmp_path: Path) -> None:
    report = {
        "all_passed": True,
        "stable_candidate": True,
        "phases": [
            {
                "kind": "sandbox",
                "summary": {
                    "scenes": {
                        "negotiation": {
                            "action_loop_metrics": {
                                "active_goal_turns": 4,
                                "commitment_rate": 25.0,
                                "focus_rate": 25.0,
                                "action_loop_state_counts": {
                                    "推进: 继续对齐 | 承诺: 已形成方向": 1,
                                    "推进: 先观察 | 承诺: 未形成": 3,
                                },
                            },
                            "disturbance_metrics": {"disturbance_rate": 50.0},
                            "disturbance_recovery_metrics": {
                                "recovery_focus_rate": 0.0,
                                "recovery_commitment_rate": 0.0,
                            },
                        }
                    }
                },
            }
        ],
    }
    insight_path = tmp_path / "sandbox_insight_report.json"
    queue_path = tmp_path / "sandbox_validation_queue.json"
    review_cards_path = tmp_path / "sandbox_review_cards.md"

    summary = large_cycle.build_sandbox_review_outputs(
        report,
        insight_path=insight_path,
        queue_path=queue_path,
        review_cards_path=review_cards_path,
        previous_queue_path=None,
    )

    assert summary["gate_summary"] == "candidate"
    assert summary["candidate_count"] == 1
    assert summary["ready_for_review_count"] == 0
    assert summary["review_card_count"] == 0
    assert summary["main_system_write_allowed"] is False
    assert insight_path.exists()
    assert queue_path.exists()
    assert review_cards_path.exists()


def test_collect_output_layer_metrics_should_count_memory_signals_and_order_sources() -> None:
    results = [
        SimpleNamespace(
            turns=[
                SimpleNamespace(
                    output_layers={
                        "order_source": "skeleton_injected",
                        "memory_hint_signals": {
                            "failure_avoid_hint": True,
                            "experience_digest_hint": False,
                            "decision_experience_hint": True,
                        },
                    }
                ),
                SimpleNamespace(
                    output_layers={
                        "order_source": "no_order_marker",
                        "memory_hint_signals": {
                            "failure_avoid_hint": False,
                            "experience_digest_hint": True,
                            "decision_experience_hint": False,
                        },
                    }
                ),
            ]
        ),
        SimpleNamespace(
            turns=[
                SimpleNamespace(
                    output_layers={
                        "order_source": "model_explicit_order",
                        "memory_hint_signals": {
                            "failure_avoid_hint": True,
                            "experience_digest_hint": True,
                            "decision_experience_hint": False,
                        },
                    }
                )
            ]
        ),
    ]

    metrics = sandbox._collect_output_layer_metrics(results)

    assert metrics["turns_with_output_layers"] == 3
    assert metrics["memory_hint_signal_counts"] == {
        "failure_avoid_hint": 2,
        "experience_digest_hint": 2,
        "decision_experience_hint": 1,
    }
    assert metrics["memory_hint_signal_rates"] == {
        "failure_avoid_hint": 66.7,
        "experience_digest_hint": 66.7,
        "decision_experience_hint": 33.3,
    }
    assert metrics["order_source_counts"] == {
        "skeleton_injected": 1,
        "no_order_marker": 1,
        "model_explicit_order": 1,
    }


def test_large_cycle_summary_should_pass_through_signal_metrics(tmp_path: Path) -> None:
    report_path = tmp_path / "sandbox_report.json"
    payload = {
        "global": {
            "total_conversations": 2,
            "total_rounds": 6,
            "success_rate": 100.0,
            "failure_rate": 0.0,
            "timeout_rate": 0.0,
            "avg_rounds_per_conversation": 3.0,
            "total_violations": 0,
            "signal_metrics": {"order_source_counts": {"no_order_marker": 2}},
            "action_loop_metrics": {"focus_rate": 50.0},
            "disturbance_metrics": {"disturbance_turns": 1, "disturbance_rate": 50.0},
            "disturbance_response_metrics": {
                "disturbed_turns": 1,
                "disturbed_progress_counts": {"继续对齐": 1},
            },
            "disturbance_recovery_metrics": {
                "recovery_turns": 1,
                "recovery_progress_counts": {"继续推进": 1},
            },
        },
        "scenes": {
            "sales": {
                "success": 2,
                "failure": 0,
                "timeout": 0,
                "total_violations": 0,
                "signal_metrics": {"memory_hint_signal_rates": {"failure_avoid_hint": 50.0}},
                "action_loop_metrics": {"focus_rate": 50.0},
                "disturbance_metrics": {"disturbance_turns": 1, "disturbance_rate": 50.0},
                "disturbance_response_metrics": {
                    "disturbed_turns": 1,
                    "disturbed_progress_counts": {"继续对齐": 1},
                },
                "disturbance_recovery_metrics": {
                    "recovery_turns": 1,
                    "recovery_progress_counts": {"继续推进": 1},
                },
            }
        },
    }
    report_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    summary = large_cycle._summarize_sandbox(report_path, None)

    assert summary["signal_metrics"] == {"order_source_counts": {"no_order_marker": 2}}
    assert summary["action_loop_metrics"] == {"focus_rate": 50.0}
    assert summary["disturbance_metrics"] == {"disturbance_turns": 1, "disturbance_rate": 50.0}
    assert summary["disturbance_response_metrics"] == {
        "disturbed_turns": 1,
        "disturbed_progress_counts": {"继续对齐": 1},
    }
    assert summary["disturbance_recovery_metrics"] == {
        "recovery_turns": 1,
        "recovery_progress_counts": {"继续推进": 1},
    }
    assert summary["scenes"]["sales"]["signal_metrics"] == {
        "memory_hint_signal_rates": {"failure_avoid_hint": 50.0}
    }
    assert summary["scenes"]["sales"]["action_loop_metrics"] == {"focus_rate": 50.0}
    assert summary["scenes"]["sales"]["disturbance_metrics"] == {
        "disturbance_turns": 1,
        "disturbance_rate": 50.0,
    }
    assert summary["scenes"]["sales"]["disturbance_response_metrics"] == {
        "disturbed_turns": 1,
        "disturbed_progress_counts": {"继续对齐": 1},
    }
    assert summary["scenes"]["sales"]["disturbance_recovery_metrics"] == {
        "recovery_turns": 1,
        "recovery_progress_counts": {"继续推进": 1},
    }


def test_build_scene_insights_should_rank_scenes_and_mark_conservative_ones() -> None:
    phase_results = [
        {
            "kind": "sandbox",
            "name": "multi_scene",
            "summary": {
                "scenes": {
                    "emotion": {
                        "action_loop_metrics": {
                            "commitment_rate": 66.7,
                            "focus_rate": 66.7,
                            "action_loop_state_counts": {
                                "推进: 继续推进 | 承诺: 已形成方向": 2,
                                "推进: 继续对齐 | 承诺: 已形成方向": 1,
                            },
                        },
                        "disturbance_metrics": {"disturbance_rate": 10.0},
                        "disturbance_response_metrics": {},
                        "disturbance_recovery_metrics": {
                            "recovery_commitment_rate": 100.0,
                            "recovery_focus_rate": 100.0,
                            "recovery_progress_counts": {"继续推进": 1},
                        },
                    },
                    "management": {
                        "action_loop_metrics": {
                            "commitment_rate": 20.0,
                            "focus_rate": 20.0,
                            "action_loop_state_counts": {
                                "推进: 先观察 | 承诺: 未形成": 3,
                                "推进: 继续对齐 | 承诺: 已形成方向": 1,
                            },
                        },
                        "disturbance_metrics": {"disturbance_rate": 30.0},
                        "disturbance_response_metrics": {
                            "disturbed_progress_counts": {"继续对齐": 1},
                        },
                        "disturbance_recovery_metrics": {
                            "recovery_commitment_rate": 0.0,
                            "recovery_focus_rate": 0.0,
                            "recovery_progress_counts": {},
                        },
                    },
                }
            },
        }
    ]

    insights = large_cycle._build_scene_insights(phase_results)

    assert insights["strongest_scene"] == "emotion"
    assert insights["needs_attention"] == ["management"]
    assert insights["scene_rank"][0] == "emotion"
    assert insights["scene_insights"]["emotion"]["status"] in {"恢复力较强", "推进较稳"}
    assert insights["scene_insights"]["management"]["status"] == "偏保守"
    assert insights["scene_insights"]["management"]["observe_share"] == 75.0


def test_build_scene_trend_should_compare_with_previous_report() -> None:
    current = {
        "scene_insights": {
            "sales": {
                "avg_commitment_rate": 80.0,
                "avg_focus_rate": 80.0,
                "avg_recovery_commitment_rate": 50.0,
                "avg_recovery_focus_rate": 50.0,
                "observe_share": 10.0,
            },
            "negotiation": {
                "avg_commitment_rate": 30.0,
                "avg_focus_rate": 30.0,
                "avg_recovery_commitment_rate": 0.0,
                "avg_recovery_focus_rate": 0.0,
                "observe_share": 60.0,
            },
        }
    }
    previous = {
        "scene_insights": {
            "sales": {
                "avg_commitment_rate": 70.0,
                "avg_focus_rate": 70.0,
                "avg_recovery_commitment_rate": 0.0,
                "avg_recovery_focus_rate": 0.0,
                "observe_share": 20.0,
            },
            "negotiation": {
                "avg_commitment_rate": 40.0,
                "avg_focus_rate": 40.0,
                "avg_recovery_commitment_rate": 0.0,
                "avg_recovery_focus_rate": 0.0,
                "observe_share": 50.0,
            },
        }
    }

    trends = large_cycle._build_scene_trend(current, previous)

    assert trends["sales"]["summary"] in {"比上一轮更稳", "比上一轮略有改善"}
    assert trends["sales"]["commitment_delta"] == 10.0
    assert trends["sales"]["focus_delta"] == 10.0
    assert trends["sales"]["observe_share_delta"] == -10.0
    assert trends["negotiation"]["summary"] in {"比上一轮更保守", "比上一轮略有回弹"}
    assert trends["negotiation"]["commitment_delta"] == -10.0
    assert trends["negotiation"]["focus_delta"] == -10.0
    assert trends["negotiation"]["observe_share_delta"] == 10.0


def test_collect_world_state_metrics_should_count_non_default_states() -> None:
    results = [
        SimpleNamespace(
            turns=[
                SimpleNamespace(
                    world_state_snapshot={
                        "situation_stage": "推进",
                        "progress_state": "继续推进",
                        "risk_level": "medium",
                        "commitment_state": "已形成方向",
                        "action_loop_state": "推进: 继续推进 | 承诺: 已形成方向 | 下一轮: 先对齐预算边界",
                        "next_turn_focus": "先对齐预算边界",
                    }
                ),
                SimpleNamespace(
                    world_state_snapshot={
                        "situation_stage": "观察",
                        "progress_state": "观察中",
                        "risk_level": "low",
                        "commitment_state": "未形成",
                        "next_turn_focus": "",
                    }
                ),
            ]
        )
    ]

    metrics = sandbox._collect_world_state_metrics(results)

    assert metrics["turns_with_world_state"] == 2
    assert metrics["world_state_coverage_rate"] == 100.0
    assert metrics["stage_counts"] == {"推进": 1, "观察": 1}
    assert metrics["progress_counts"] == {"继续推进": 1, "观察中": 1}
    assert metrics["risk_counts"] == {"medium": 1, "low": 1}
    assert metrics["commitment_counts"] == {"已形成方向": 1, "未形成": 1}
    assert metrics["turns_with_action_loop"] == 1
    assert metrics["action_loop_coverage_rate"] == 50.0
    assert metrics["turns_with_next_turn_focus"] == 1
    assert metrics["next_turn_focus_rate"] == 50.0


def test_collect_action_loop_metrics_should_measure_focus_commitment_and_goal() -> None:
    results = [
        SimpleNamespace(
            turns=[
                SimpleNamespace(
                    world_state_snapshot={
                        "action_loop_state": "推进: 继续推进 | 承诺: 已形成跟进 | 下一轮: 明天继续对齐",
                        "active_goal": "推进预算确认",
                        "commitment_state": "已形成跟进",
                        "next_turn_focus": "明天继续对齐",
                    }
                ),
                SimpleNamespace(
                    world_state_snapshot={
                        "action_loop_state": "推进: 继续对齐 | 承诺: 未形成 | 当前目标: 先稳住关系",
                        "active_goal": "先稳住关系",
                        "commitment_state": "未形成",
                        "next_turn_focus": "",
                    }
                ),
            ]
        )
    ]

    metrics = sandbox._collect_action_loop_metrics(results)

    assert metrics["active_goal_turns"] == 2
    assert metrics["active_goal_rate"] == 100.0
    assert metrics["commitment_turns"] == 1
    assert metrics["commitment_rate"] == 50.0
    assert metrics["focus_turns"] == 1
    assert metrics["focus_rate"] == 50.0
    assert metrics["action_loop_state_counts"] == {
        "推进: 继续推进 | 承诺: 已形成跟进 | 下一轮: 明天继续对齐": 1,
        "推进: 继续对齐 | 承诺: 未形成 | 当前目标: 先稳住关系": 1,
    }


def test_collect_world_state_transition_metrics_should_count_state_changes() -> None:
    results = [
        SimpleNamespace(
            turns=[
                SimpleNamespace(
                    world_state_snapshot={
                        "situation_stage": "破冰",
                        "progress_state": "继续观察",
                        "commitment_state": "未形成",
                        "risk_level": "low",
                        "tension_level": "low",
                        "action_loop_state": "推进: 继续观察 | 承诺: 未形成",
                    }
                ),
                SimpleNamespace(
                    world_state_snapshot={
                        "situation_stage": "探索",
                        "progress_state": "继续观察",
                        "commitment_state": "未形成",
                        "risk_level": "medium",
                        "tension_level": "medium",
                        "action_loop_state": "推进: 继续观察 | 承诺: 未形成 | 下一轮: 先补信息",
                    }
                ),
                SimpleNamespace(
                    world_state_snapshot={
                        "situation_stage": "推进",
                        "progress_state": "继续推进",
                        "commitment_state": "已形成",
                        "risk_level": "medium",
                        "tension_level": "high",
                        "action_loop_state": "推进: 继续推进 | 承诺: 已形成 | 下一轮: 明天确认",
                    }
                ),
            ]
        )
    ]

    metrics = sandbox._collect_world_state_transition_metrics(results)

    assert metrics["conversations_with_transition"] == 1
    assert metrics["conversation_transition_rate"] == 100.0
    assert metrics["total_transition_steps"] == 9
    assert metrics["field_change_counts"] == {
        "situation_stage": 2,
        "progress_state": 1,
        "commitment_state": 1,
        "risk_level": 1,
        "tension_level": 2,
        "action_loop_state": 2,
    }


def test_collect_progress_balance_metrics_should_measure_passive_forward_rate() -> None:
    results = [
        SimpleNamespace(
            turns=[
                SimpleNamespace(
                    world_state_snapshot={
                        "situation_stage": "推进",
                        "progress_state": "继续观察",
                    }
                ),
                SimpleNamespace(
                    world_state_snapshot={
                        "situation_stage": "推进",
                        "progress_state": "继续推进",
                    }
                ),
                SimpleNamespace(
                    world_state_snapshot={
                        "situation_stage": "收口",
                        "progress_state": "先观察",
                    }
                ),
                SimpleNamespace(
                    world_state_snapshot={
                        "situation_stage": "探索",
                        "progress_state": "继续观察",
                    }
                ),
            ]
        )
    ]

    metrics = sandbox._collect_progress_balance_metrics(results)

    assert metrics == {
        "forward_stage_turns": 3,
        "passive_forward_turns": 2,
        "passive_forward_rate": 66.7,
    }


def test_collect_disturbance_metrics_should_measure_event_coverage() -> None:
    results = [
        SimpleNamespace(
            turns=[
                SimpleNamespace(disturbance_event={"event_id": "budget_freeze", "label": "预算突然收紧"}),
                SimpleNamespace(disturbance_event={}),
                SimpleNamespace(disturbance_event={"event_id": "budget_freeze", "label": "预算突然收紧"}),
                SimpleNamespace(disturbance_event={"event_id": "leader_pressure", "label": "上级突然施压"}),
            ]
        )
    ]

    metrics = sandbox._collect_disturbance_metrics(results)

    assert metrics == {
        "disturbance_turns": 3,
        "disturbance_rate": 75.0,
        "disturbance_type_counts": {
            "budget_freeze": 2,
            "leader_pressure": 1,
        },
    }


def test_collect_disturbance_response_metrics_should_measure_reaction_shape() -> None:
    results = [
        SimpleNamespace(
            turns=[
                SimpleNamespace(
                    disturbance_event={"event_id": "budget_freeze", "label": "预算突然收紧"},
                    world_state_snapshot={
                        "progress_state": "继续对齐",
                        "situation_stage": "探索",
                        "commitment_state": "未形成",
                        "next_turn_focus": "",
                    },
                ),
                SimpleNamespace(
                    disturbance_event={"event_id": "counterparty_cools", "label": "对方态度转冷"},
                    world_state_snapshot={
                        "progress_state": "继续推进",
                        "situation_stage": "推进",
                        "commitment_state": "已形成方向",
                        "next_turn_focus": "先对齐预算边界",
                    },
                ),
                SimpleNamespace(
                    disturbance_event={},
                    world_state_snapshot={
                        "progress_state": "继续观察",
                        "situation_stage": "观察",
                        "commitment_state": "未形成",
                        "next_turn_focus": "",
                    },
                ),
            ]
        )
    ]

    metrics = sandbox._collect_disturbance_response_metrics(results)

    assert metrics == {
        "disturbed_turns": 2,
        "disturbed_progress_counts": {
            "继续对齐": 1,
            "继续推进": 1,
        },
        "disturbed_stage_counts": {
            "探索": 1,
            "推进": 1,
        },
        "disturbed_commitment_turns": 1,
        "disturbed_commitment_rate": 50.0,
        "disturbed_focus_turns": 1,
        "disturbed_focus_rate": 50.0,
    }


def test_collect_disturbance_recovery_metrics_should_measure_next_turn_recovery() -> None:
    results = [
        SimpleNamespace(
            turns=[
                SimpleNamespace(
                    disturbance_event={"event_id": "budget_freeze"},
                    world_state_snapshot={
                        "progress_state": "继续对齐",
                        "situation_stage": "探索",
                        "commitment_state": "未形成",
                        "next_turn_focus": "",
                    },
                ),
                SimpleNamespace(
                    disturbance_event={},
                    world_state_snapshot={
                        "progress_state": "继续推进",
                        "situation_stage": "推进",
                        "commitment_state": "已形成方向",
                        "next_turn_focus": "先把总账算清，再确认怎么继续推",
                    },
                ),
                SimpleNamespace(
                    disturbance_event={"event_id": "team_resistance"},
                    world_state_snapshot={
                        "progress_state": "继续对齐",
                        "situation_stage": "探索",
                        "commitment_state": "已形成方向",
                        "next_turn_focus": "先把最卡的一步对齐",
                    },
                ),
                SimpleNamespace(
                    disturbance_event={},
                    world_state_snapshot={
                        "progress_state": "继续对齐",
                        "situation_stage": "探索",
                        "commitment_state": "已形成方向",
                        "next_turn_focus": "先把最卡的一步对齐",
                    },
                ),
            ]
        )
    ]

    metrics = sandbox._collect_disturbance_recovery_metrics(results)

    assert metrics == {
        "recovery_turns": 2,
        "recovery_progress_counts": {
            "继续推进": 1,
            "继续对齐": 1,
        },
        "recovery_stage_counts": {
            "推进": 1,
            "探索": 1,
        },
        "recovery_commitment_turns": 2,
        "recovery_commitment_rate": 100.0,
        "recovery_focus_turns": 2,
        "recovery_focus_rate": 100.0,
    }
