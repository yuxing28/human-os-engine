from simulation import sandbox_core


def _make_result(scene_id: str, persona_name: str, output: str, score: float = 6.0):
    turn = sandbox_core.TurnResult(
        round_num=1,
        user_input="测试输入",
        system_output=output,
        elapsed_ms=12,
        llm_score=score,
    )
    return sandbox_core.ConversationResult(
        scene_id=scene_id,
        persona_name=persona_name,
        persona_description="测试人格",
        turns=[turn],
        total_rounds=1,
        avg_llm_score=score,
        total_violations=0,
        outcome="success",
        conversation_hash=sandbox_core.compute_conversation_hash([turn]),
    )


def test_guardrails_are_scene_aware():
    sales_violations = sandbox_core.check_guardrails("现在下单更划算", scene_id="sales")
    emotion_violations = sandbox_core.check_guardrails("现在下单更划算", scene_id="emotion")

    assert all(item["rule_id"] != "GR004" for item in sales_violations)
    assert any(item["rule_id"] == "GR004" for item in emotion_violations)


def test_compare_with_baseline_uses_current_results_without_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox_core, "BASELINE_DIR", tmp_path)

    baseline_results = [_make_result("sales", "理性型客户", "旧输出", score=6.0)]
    sandbox_core.save_baseline("sales", baseline_results)

    current_results = [_make_result("sales", "理性型客户", "新输出", score=7.5)]
    diffs = sandbox_core.compare_with_baseline("sales", current_results)

    assert len(diffs) == 1
    assert diffs[0].is_identical is False
    assert diffs[0].changed_turns == [1]
    assert diffs[0].score_delta == 1.5


def test_summarize_results_should_include_error_and_elapsed_metrics():
    ok = _make_result("sales", "理性型客户", "正常输出", score=6.0)
    ok.turns[0].elapsed_ms = 20
    ok.turns[0].step_timings_ms = {"step2": 10, "step6": 30, "step8": 50}
    ok.turns[0].execution_status = "ok"
    ok.error_turns = 0

    bad = _make_result("sales", "攻击型客户", "系统错误: boom", score=0.0)
    bad.turns[0].elapsed_ms = 40
    bad.turns[0].step_timings_ms = {"step2": 20, "step6": 40, "step8": 60}
    bad.turns[0].execution_status = "error"
    bad.turns[0].error_type = "RuntimeError"
    bad.error_turns = 1
    bad.outcome = "failure"

    summary = sandbox_core.summarize_results("sales", [ok, bad])
    assert summary.total_error_turns == 1
    assert summary.avg_turn_elapsed_ms == 30.0
    assert summary.avg_step2_elapsed_ms == 15.0
    assert summary.avg_step6_elapsed_ms == 35.0
    assert summary.avg_step8_elapsed_ms == 55.0


def test_run_conversation_should_capture_execution_error_meta(monkeypatch):
    monkeypatch.setattr(sandbox_core, "build_graph", lambda: object())
    monkeypatch.setattr(sandbox_core, "load_scene_config", lambda _scene_id: None)

    class _FakeRuntime:
        def __init__(self, *_args, **_kwargs):
            pass

        def run(self, *_args, **_kwargs):
            raise RuntimeError("boom")

    monkeypatch.setattr(sandbox_core, "EngineRuntime", _FakeRuntime)

    runner = sandbox_core.MultiTurnSandboxRunner(scene_id="sales", max_rounds=1, use_llm_judge=False)
    result = runner.run_conversation(
        persona={"name": "测试人格", "personality": "中性", "trust": 0.5, "emotion": 0.5},
        initial_input="测试输入",
    )

    assert result.total_rounds == 1
    assert result.error_turns == 1
    turn = result.turns[0]
    assert turn.execution_status == "error"
    assert turn.error_type == "RuntimeError"
    assert "boom" in turn.error_message
