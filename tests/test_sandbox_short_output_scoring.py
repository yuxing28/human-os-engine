"""沙盒评分门槛回归测试：短输出也应该进入 LLM 评分。"""

from simulation.sandbox_core import MultiTurnSandboxRunner


class _FakeGraph:
    def __init__(self, output: str):
        self._output = output

    def invoke(self, _state: dict) -> dict:
        return {"output": self._output}


def test_short_non_empty_output_should_still_be_scored(monkeypatch):
    runner = MultiTurnSandboxRunner(scene_id="emotion", max_rounds=1, use_llm_judge=True)
    runner.graph = _FakeGraph("嗯。")

    monkeypatch.setattr(
        "simulation.sandbox_core.llm_judge_turn",
        lambda *_args, **_kwargs: {
            "overall": 7.2,
            "reason": "短输出但有效",
            "strategy_score": 6.8,
            "delivery_score": 7.0,
        },
    )

    result = runner.run_conversation(
        persona={"name": "疲惫型", "personality": "疲惫，资源耗尽", "trust": 0.3, "emotion": 0.6},
        initial_input="我现在没精力想这么多。",
    )

    turn = result.turns[0]
    assert turn.system_output == "嗯。"
    assert turn.llm_score == 7.2
    assert turn.strategy_score == 6.8
    assert turn.delivery_score == 7.0
