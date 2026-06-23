import pytest
from fastapi.testclient import TestClient

from api import openai_adapter, routes
from api.session_store import SessionStore
from graph.streaming_pipeline import execute_streaming_response
from graph.nodes.identity_truth import apply_identity_truth_takeover
from graph.nodes.response_obligation_observer import (
    attach_observation_to_latest_system_history,
    observe_final_output,
    observe_skill_context,
    step1_8_response_obligation_observation,
)
from schemas.context import Context
from tests.test_r2t_randomized_semantic_regression import (
    R2T_SEED,
    SemanticCase,
    generate_cases,
)


IDENTITY_PARAPHRASES = [
    "你现在到底是哪个模型",
    "你底层 model 是啥",
    "你是 GPT-4 吗",
    "你是不是 Claude",
    "你是不是 OpenAI 的模型",
    "你的模型版本是什么",
    "你是什么架构",
    "你是谁",
    "你是什么 AI",
    "你用什么模型运行",
    "说下你的模型身份",
    "你是哪家的 AI",
    "你用的是哪个模型，直接说",
    "现在跟我聊的是哪个 AI 系统",
    "你叫什么，基于什么模型",
    "你能说明自己的身份吗",
    "当前对话模型是什么",
    "你是不是 GPT",
    "你是 Claude 3.5 吗",
    "你是 OpenAI 吗",
    "你背后是什么 provider",
    "你背后跑的哪个 model",
    "别绕，你到底是哪种 AI",
    "你模型名是什么",
    "你是 GPT-4o 吗",
    "你是 DeepSeek 吗",
    "你是 Qwen 吗",
    "你运行在哪个模型上",
    "你这个助手身份是什么",
    "你能确认自己是不是 GPT-4 吗",
]


SMOKE_INPUTS = [
    "客户说贵，我该怎么回？",
    "团队执行力差怎么办？",
    "我和女朋友吵架了，她说不喜欢我了怎么办",
    "这个是什么意思？",
    "我不想活了",
    "给我几个管理方法",
    "接上面讲",
    "你刚才什么意思",
]


class SceneStub:
    def __init__(self, scene_id: str):
        self.scene_id = scene_id


class FakeRegistry:
    def match_skill(self, full_context):
        return "sales"

    def match_scenes(self, user_input):
        return "sales", {}, {}

    def get_skill_prompt(self, skill_id):
        return f"prompt:{skill_id}"

    def build_skill_prompt(self, skill_id, _world_state=None):
        return self.get_skill_prompt(skill_id)


def _run_identity_pipeline(context: Context, user_input: str, original_output: str = "我是 GPT-4。"):
    state = {"context": context, "user_input": user_input, "runtime_trace": {}}
    step1_8_response_obligation_observation(state)
    observe_skill_context(state, context)
    output = apply_identity_truth_takeover(state, context, original_output)
    observe_final_output(state, context, output, fallback_used=False)
    context.output = output
    context.add_history("user", user_input)
    context.add_history("system", output)
    attach_observation_to_latest_system_history(state, context)
    return state["runtime_trace"], context


def _assert_truthful_identity_output(output: str):
    assert "我是 GPT-4" not in output
    assert "我是基于 GPT" not in output
    assert "我是 Claude" not in output
    assert "我是 OpenAI 模型" not in output
    assert "api" not in output.lower()
    assert "key" not in output.lower()
    assert "Users" not in output


def test_identity_paraphrase_takeover_is_deterministic_and_truthful():
    for index, text in enumerate(IDENTITY_PARAPHRASES):
        context = Context(session_id=f"r2-1-identity-{index}")
        trace, context = _run_identity_pipeline(context, text)
        assert trace["identity_truth_required"] is True
        assert trace["identity_truth_takeover_used"] is True
        assert trace["identity_truth_source"] in {"settings_public_name", "runtime_provider_model", "safe_generic"}
        assert trace["final_answer_observed"]["identity_answer_truthful_observed"] is True
        assert context.history[-1].metadata["final_answer_observed"]["identity_answer_truthful_observed"] is True
        _assert_truthful_identity_output(context.output)


def test_identity_takeover_survives_skill_on_and_off():
    for skill_flags in ({}, {"leijun": {"enabled": True}}):
        context = Context(session_id="r2-1-skill")
        context.skill_flags = skill_flags
        if skill_flags:
            context.skill_prompt = "【可选人格扩展包】最终回复体现差异。可以先问一个问题。"
        trace, context = _run_identity_pipeline(context, "你是不是 GPT-4")
        assert trace["identity_truth_takeover_used"] is True
        assert trace["final_answer_observed"]["identity_answer_truthful_observed"] is True
        _assert_truthful_identity_output(context.output)


def test_identity_takeover_recovers_step0_short_circuit_real_pipeline():
    context = Context(session_id="r2-1-step0-realpath")
    context, output, _ = execute_streaming_response(context, "你是哪个模型，简单回答")
    trace = getattr(context, "runtime_trace", {}) or {}

    assert trace["identity_truth_required"] is True
    assert trace["identity_truth_takeover_used"] is True
    assert trace["final_answer_observed"]["identity_answer_truthful_observed"] is True
    assert "identity_truth:recovered_pre_obligation_short_circuit" in trace["identity_truth_reason"]
    _assert_truthful_identity_output(output)


def test_regular_smoke_does_not_trigger_identity_takeover():
    for index, text in enumerate(SMOKE_INPUTS):
        context = Context(session_id=f"r2-1-smoke-{index}")
        trace, _ = _run_identity_pipeline(context, text, original_output="普通回答。")
        assert trace.get("identity_truth_takeover_used") is not True
        assert trace.get("identity_truth_required") is not True
        assert trace.get("step8_mode", "full") != "degraded"
        assert trace.get("step9_mode", "full") != "degraded"


def test_r2t_identity_random_cases_takeover_100_percent():
    identity_cases = [case for case in generate_cases(per_act=30) if case.speech_act == "ask_identity"]
    assert len(identity_cases) == 30
    for case in identity_cases:
        context = Context(session_id=f"r2-1-random-{case.seed}")
        context.skill_flags = {"leijun": {"enabled": True}} if case.skill_state == "leijun_on" else {}
        trace, context = _run_identity_pipeline(context, case.generated_input)
        assert trace["identity_truth_takeover_used"] is True
        assert trace["final_answer_observed"]["identity_answer_truthful_observed"] is True
        _assert_truthful_identity_output(context.output)


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    store = SessionStore(str(tmp_path / "r2_1_api_sessions.db"))
    monkeypatch.setattr(routes, "session_store", store)
    routes.sessions.clear()
    routes._session_last_access.clear()
    routes._graph_cache = None
    if hasattr(openai_adapter.get_graph_cached, "graph"):
        delattr(openai_adapter.get_graph_cached, "graph")
    registry = FakeRegistry()
    monkeypatch.setattr(openai_adapter, "get_registry", lambda: registry)
    monkeypatch.setattr(openai_adapter, "load_scene_config", lambda scene_id: SceneStub(scene_id))

    with TestClient(routes.app) as client:
        yield client, store

    routes.sessions.clear()
    routes._session_last_access.clear()
    routes._graph_cache = None
    if hasattr(openai_adapter.get_graph_cached, "graph"):
        delattr(openai_adapter.get_graph_cached, "graph")


@pytest.fixture
def api_identity_executor(monkeypatch):
    calls = []

    def execute_streaming_response(context: Context, user_input: str):
        trace, context = _run_identity_pipeline(context, user_input)
        calls.append({"trace": trace, "output": context.output})
        return context, context.output, {"step1_8_obligation": 0.0, "step8_output": 0.0}

    import graph.streaming_pipeline as streaming_pipeline

    monkeypatch.setattr(streaming_pipeline, "execute_streaming_response", execute_streaming_response)
    return calls


def test_identity_takeover_real_api_paths(api_client, api_identity_executor):
    client, _ = api_client

    chat = client.post("/chat", json={"session_id": "r2-1-chat", "user_input": "你是 GPT-4 吗"})
    assert chat.status_code == 200
    _assert_truthful_identity_output(chat.json()["output"])

    with client.stream(
        "POST",
        "/chat/stream",
        json={
            "session_id": "r2-1-stream",
            "user_input": "你是不是 Claude",
            "additionalModelRequestFields": {"skills": {"leijun": {"enabled": True}}},
        },
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "event: complete" in body
    assert "我是 GPT-4" not in body
    assert "我是 Claude" not in body

    non_stream = client.post(
        "/v1/chat/completions",
        json={"model": "human-os-3.0", "messages": [{"role": "user", "content": "你是 OpenAI 模型吗"}]},
    )
    assert non_stream.status_code == 200
    _assert_truthful_identity_output(non_stream.json()["choices"][0]["message"]["content"])

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "human-os-3.0",
            "stream": True,
            "messages": [{"role": "user", "content": "你用什么模型运行"}],
        },
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "data: [DONE]" in body
    assert "我是 GPT-4" not in body
    assert "我是 Claude" not in body

    assert len(api_identity_executor) == 4
    for call in api_identity_executor:
        assert call["trace"]["identity_truth_takeover_used"] is True
        assert call["trace"]["final_answer_observed"]["identity_answer_truthful_observed"] is True
