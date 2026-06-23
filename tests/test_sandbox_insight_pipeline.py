from simulation.sandbox_insight_pipeline import (
    analyze_large_cycle_report,
    build_review_cards,
    build_validation_queue,
    render_review_cards_markdown,
)


def test_sandbox_insight_should_observe_conservative_scene_without_writing_main_system():
    report = {
        "all_passed": True,
        "stable_candidate": True,
        "scene_trends": {"management": {"summary": "比上一轮更保守"}},
        "phases": [
            {
                "kind": "sandbox",
                "summary": {
                    "scenes": {
                        "management": {
                            "action_loop_metrics": {
                                "active_goal_turns": 2,
                                "commitment_rate": 0.0,
                                "focus_rate": 0.0,
                                "action_loop_state_counts": {
                                    "推进: 先观察 | 承诺: 未形成 | 当前目标: task_acceptance": 2
                                },
                            },
                            "disturbance_metrics": {"disturbance_rate": 0.0},
                            "disturbance_recovery_metrics": {},
                        }
                    }
                },
            }
        ],
    }

    result = analyze_large_cycle_report(report)

    assert result["main_system_write_allowed"] is False
    assert result["gate_summary"] == "observe"
    assert result["insights"][0]["scene"] == "management"
    assert result["insights"][0]["gate"] == "observe"
    assert "偏观察" in result["insights"][0]["observation"]
    assert "commitment_rate=0.0%" in result["insights"][0]["evidence"]


def test_sandbox_insight_should_mark_disturbance_recovery_as_candidate():
    report = {
        "all_passed": True,
        "stable_candidate": False,
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

    result = analyze_large_cycle_report(report)

    assert result["gate_summary"] == "candidate"
    assert result["insights"][0]["gate"] == "candidate"
    assert "扰动后的下一轮焦点恢复偏弱" in result["insights"][0]["observation"]


def test_sandbox_insight_should_hold_stable_scene():
    report = {
        "all_passed": True,
        "stable_candidate": True,
        "phases": [
            {
                "kind": "sandbox",
                "summary": {
                    "scenes": {
                        "emotion": {
                            "action_loop_metrics": {
                                "active_goal_turns": 3,
                                "commitment_rate": 66.7,
                                "focus_rate": 66.7,
                                "action_loop_state_counts": {
                                    "推进: 继续推进 | 承诺: 已形成方向": 3
                                },
                            },
                            "disturbance_metrics": {"disturbance_rate": 0.0},
                            "disturbance_recovery_metrics": {},
                        }
                    }
                },
            }
        ],
    }

    result = analyze_large_cycle_report(report)

    assert result["gate_summary"] == "hold"
    assert result["insights"][0]["gate"] == "hold"
    assert "动作闭环比较稳" in result["insights"][0]["observation"]


def test_validation_queue_should_only_include_candidate_insights():
    insight_report = {
        "report_path": "data/large_cycle_report.json",
        "insights": [
            {
                "scene": "management",
                "gate": "observe",
                "observation": "偏观察",
                "evidence": ["observe_rate=100.0%"],
            },
            {
                "scene": "negotiation",
                "gate": "candidate",
                "observation": "扰动后的下一轮焦点恢复偏弱。",
                "hypothesis": "扰动没有稳定转成承接点。",
                "proposal": "检查 disturbance_event 到 next_turn_focus 的桥接逻辑。",
                "risk": "可能误伤普通对话。",
                "evidence": ["disturbance_rate=50.0%", "recovery_focus_rate=0.0%"],
            },
            {
                "scene": "emotion",
                "gate": "hold",
                "observation": "动作闭环比较稳。",
                "evidence": ["focus_rate=66.7%"],
            },
        ],
    }

    queue = build_validation_queue(insight_report)

    assert queue["main_system_write_allowed"] is False
    assert queue["queue_size"] == 1
    assert queue["ready_for_review_count"] == 0
    assert queue["items"][0]["scene"] == "negotiation"
    assert queue["items"][0]["status"] == "needs_retest"
    assert queue["items"][0]["occurrence_count"] == 1
    assert queue["items"][0]["main_system_write_allowed"] is False
    assert "连续两轮" in queue["items"][0]["next_check"]


def test_validation_queue_should_stay_empty_when_no_candidate():
    insight_report = {
        "insights": [
            {"scene": "management", "gate": "observe"},
            {"scene": "emotion", "gate": "hold"},
        ]
    }

    queue = build_validation_queue(insight_report)

    assert queue["queue_size"] == 0
    assert queue["items"] == []


def test_validation_queue_should_promote_repeated_candidate_to_review():
    insight_report = {
        "report_path": "data/large_cycle_report_second.json",
        "insights": [
            {
                "scene": "negotiation",
                "gate": "candidate",
                "observation": "negotiation 有扰动，但扰动后的下一轮焦点恢复偏弱。",
                "hypothesis": "系统能识别扰动，但没有稳定把扰动影响转成下一轮承接点。",
                "proposal": "检查 disturbance_event 到 next_turn_focus 的桥接逻辑。",
                "risk": "过度强化扰动恢复，可能让普通对话也被误判成风险处理。",
                "evidence": ["disturbance_rate=50.0%", "recovery_focus_rate=0.0%"],
            }
        ],
    }
    previous_queue = build_validation_queue({
        "report_path": "data/large_cycle_report_first.json",
        "insights": insight_report["insights"],
    })

    queue = build_validation_queue(insight_report, previous_queue=previous_queue)

    assert queue["queue_size"] == 1
    assert queue["ready_for_review_count"] == 1
    assert queue["items"][0]["status"] == "ready_for_review"
    assert queue["items"][0]["priority"] == "high"
    assert queue["items"][0]["occurrence_count"] == 2
    assert queue["items"][0]["previous_source_report"] == "data/large_cycle_report_first.json"
    assert queue["items"][0]["main_system_write_allowed"] is False
    assert "不能自动改主系统" in queue["items"][0]["next_check"]


def test_review_cards_should_only_render_ready_for_review_items():
    ready_queue = {
        "items": [
            {
                "id": "negotiation:candidate:1",
                "scene": "negotiation",
                "status": "ready_for_review",
                "reason": "negotiation 有扰动，但扰动后的下一轮焦点恢复偏弱。",
                "hypothesis": "系统能识别扰动，但没有稳定转成下一轮承接点。",
                "proposal": "检查 disturbance_event 到 next_turn_focus 的桥接逻辑。",
                "risk": "可能误伤普通对话。",
                "evidence": ["disturbance_rate=50.0%", "recovery_focus_rate=0.0%"],
                "source_report": "data/large_cycle_report_second.json",
                "previous_source_report": "data/large_cycle_report_first.json",
            },
            {
                "id": "management:candidate:1",
                "scene": "management",
                "status": "needs_retest",
                "reason": "偏观察。",
            },
        ]
    }

    cards = build_review_cards(ready_queue)
    markdown = render_review_cards_markdown(cards)

    assert cards["main_system_write_allowed"] is False
    assert cards["card_count"] == 1
    assert cards["cards"][0]["scene"] == "negotiation"
    assert cards["cards"][0]["main_system_write_allowed"] is False
    assert "谈判候选问题决策卡" in markdown
    assert "你不需要懂代码" in markdown
    assert "这件事是什么意思" in markdown
    assert "你只需要决定" in markdown
    assert "A. 继续观察" in markdown
    assert "B. 小范围修" in markdown
    assert "C. 提高优先级" in markdown
    assert "Codex 建议：选 B" in markdown
    assert "disturbance_rate=50.0%" in markdown
    assert "不直接改主线" in markdown
    assert "management" not in markdown


def test_review_cards_should_say_empty_when_no_ready_items():
    cards = build_review_cards({"items": [{"scene": "negotiation", "status": "needs_retest"}]})
    markdown = render_review_cards_markdown(cards)

    assert cards["card_count"] == 0
    assert "暂无需要人工复盘" in markdown
