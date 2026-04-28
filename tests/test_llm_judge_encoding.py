from types import SimpleNamespace
import builtins

from simulation.llm_judge import LLMJudge
from simulation import llm_judge


def test_safe_print_should_fallback_when_console_encoding_raises(monkeypatch):
    calls = []

    def fake_print(message):
        calls.append(message)
        if len(calls) == 1:
            raise UnicodeEncodeError("gbk", str(message), 0, 1, "cannot encode")

    monkeypatch.setattr(builtins, "print", fake_print)
    monkeypatch.setattr(llm_judge.sys, "stdout", SimpleNamespace(encoding="ascii"))

    LLMJudge._safe_print("⚠️ test")

    assert len(calls) == 2
    assert all(ord(ch) < 128 for ch in calls[-1])


def test_evaluate_quality_should_return_fallback_payload_on_llm_error():
    judge = object.__new__(LLMJudge)
    judge._call_llm = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("供应商失败⚠️"))

    result = judge.evaluate_quality("你好", "我理解你")

    assert result["overall"] == 0
    assert result["strategy_score"] == 0.0
    assert "评估失败" in result["reason"]


def test_llm_judge_should_skip_nvidia_provider_when_model_not_configured(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-deepseek")
    monkeypatch.setenv("NVIDIA_API_KEYS", "test-nvidia")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)

    judge = LLMJudge()

    assert len(judge.providers) == 1
    assert judge.providers[0]["name"] == "DeepSeek"
