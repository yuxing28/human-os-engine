import pytest
from fastapi.testclient import TestClient

from api import openai_adapter, routes
from api.session_store import SessionStore
from graph.nodes.response_obligation_observer import (
    attach_observation_to_latest_system_history,
    observe_final_output,
    observe_skill_context,
    step1_8_response_obligation_observation,
)
from schemas.context import Context, HistoryItem


class SceneStub:
    def __init__(self, scene_id: str):
        self.scene_id = scene_id


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    store = SessionStore(str(tmp_path / "api_sessions.db"))
    monkeypatch.setattr(routes, "session_store", store)
    routes.sessions.clear()
    routes._session_last_access.clear()
    routes._graph_cache = None
    if hasattr(openai_adapter.get_graph_cached, "graph"):
        delattr(openai_adapter.get_graph_cached, "graph")

    with TestClient(routes.app) as client:
        yield client, store

    routes.sessions.clear()
    routes._session_last_access.clear()
    routes._graph_cache = None
    if hasattr(openai_adapter.get_graph_cached, "graph"):
        delattr(openai_adapter.get_graph_cached, "graph")


@pytest.fixture
def real_path_executor(monkeypatch):
    calls: list[dict] = []

    def execute_streaming_response(context: Context, user_input: str):
        skill_flags = getattr(context, "skill_flags", {}) or {}
        leijun_enabled = bool((skill_flags.get("leijun") or {}).get("enabled"))
        if leijun_enabled:
            context.skill_prompt = "【可选人格扩展包】最终回复体现差异。可以先问一个问题。"
        elif getattr(context, "skill_prompt", ""):
            context.skill_prompt = context.skill_prompt
        else:
            context.skill_prompt = ""

        state = {
            "context": context,
            "user_input": user_input,
            "runtime_trace": {},
        }
        state = step1_8_response_obligation_observation(state)
        observe_skill_context(state, context)

        output = f"真实路径回答:{user_input}"
        observe_final_output(state, context, output, fallback_used=False)
        context.output = output
        context.add_history("user", user_input)
        context.add_history("system", output)
        attach_observation_to_latest_system_history(state, context)

        trace = getattr(context, "runtime_trace", {}) or {}
        calls.append(
            {
                "session_id": context.session_id,
                "user_input": user_input,
                "history_size_before_system": len(context.history) - 2,
                "skill_flags": skill_flags,
                "trace": trace,
                "context": context,
            }
        )
        return context, output, {"step1_8_obligation": 0.0, "step8_output": 0.0}

    import graph.streaming_pipeline as streaming_pipeline

    monkeypatch.setattr(streaming_pipeline, "execute_streaming_response", execute_streaming_response)
    return calls


class FakeRegistry:
    def __init__(self, skill_id: str | None = "sales"):
        self.skill_id = skill_id

    def match_skill(self, full_context):
        return self.skill_id

    def match_scenes(self, user_input):
        return self.skill_id or "sales", {}, {}

    def get_skill_prompt(self, skill_id):
        return f"prompt:{skill_id}"

    def build_skill_prompt(self, skill_id, _world_state=None):
        return self.get_skill_prompt(skill_id)


def _stub_openai_skill_loading(monkeypatch, skill_id: str | None = "sales"):
    import modules.L5.skill_registry as skill_registry

    registry = FakeRegistry(skill_id=skill_id)
    monkeypatch.setattr(openai_adapter, "get_registry", lambda: registry)
    monkeypatch.setattr(skill_registry, "get_registry", lambda: registry)
    monkeypatch.setattr(openai_adapter, "load_scene_config", lambda scene_id: SceneStub(scene_id))


def assert_r1_observation_present(trace: dict):
    assert "response_obligation" in trace
    assert "final_answer_observed" in trace
    assert "expected_deliverable" in trace
    assert "answer_first_required_observed" in trace
    assert "clarification_allowed_observed" in trace
    assert "final_response_boundary_required" in trace


def test_health_reports_session_count(api_client):
    client, store = api_client
    context = Context(session_id="health-001")
    store.save_session("health-001", context)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["sessions_count"] == 1


def test_chat_uses_streaming_pipeline_and_persists_r1_observation(api_client, real_path_executor):
    client, store = api_client

    first = client.post("/chat", json={"session_id": "sess001", "user_input": "你是哪个模型"})
    second = client.post("/chat", json={"session_id": "sess001", "user_input": "第二句"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["session_id"] == "sess001"
    assert second.json()["session_id"] == "sess001"
    assert len(real_path_executor) == 2
    assert real_path_executor[0]["history_size_before_system"] == 0
    assert real_path_executor[1]["history_size_before_system"] == 2
    assert "mode" not in first.json()
    assert "priority" not in first.json()
    assert "emotion" not in first.json()
    assert "input_type" not in first.json()

    restored = store.load_session("sess001")
    assert restored is not None
    assert len(restored.history) == 4
    assert restored.history[-1].content == "真实路径回答:第二句"
    assert_r1_observation_present(real_path_executor[-1]["trace"])


def test_chat_rejects_invalid_session_id(api_client):
    client, _ = api_client

    response = client.post("/chat", json={"session_id": "../bad", "user_input": "你好"})

    assert response.status_code == 400
    assert "session_id" in response.json()["detail"]


def test_chat_returns_500_when_streaming_pipeline_fails(api_client, monkeypatch):
    client, _ = api_client

    def broken_executor(context, user_input):
        raise RuntimeError("boom")

    import graph.streaming_pipeline as streaming_pipeline

    monkeypatch.setattr(streaming_pipeline, "execute_streaming_response", broken_executor)

    response = client.post("/chat", json={"session_id": "safe123", "user_input": "你好"})

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"


def test_chat_stream_uses_streaming_pipeline_and_emits_final_output(api_client, real_path_executor):
    client, store = api_client

    with client.stream(
        "POST",
        "/chat/stream",
        json={
            "session_id": "stream01",
            "user_input": "我如果领导团队怎么让团队更好的执行效率",
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: status" not in body
    assert "event: token" in body
    assert "真实路径" in body
    assert "event: complete" in body
    assert '"session_id": "stream01"' in body
    restored = store.load_session("stream01")
    assert restored is not None
    assert restored.output == "真实路径回答:我如果领导团队怎么让团队更好的执行效率"
    assert_r1_observation_present(real_path_executor[-1]["trace"])


def test_openai_models_endpoint_returns_model_list(api_client):
    client, _ = api_client

    response = client.get("/v1/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "list"
    assert payload["data"][0]["id"] == "human-os-3.0"


def test_openai_chat_non_stream_uses_streaming_pipeline_and_records_leijun_skill(
    api_client,
    monkeypatch,
    real_path_executor,
):
    client, _ = api_client
    _stub_openai_skill_loading(monkeypatch, skill_id="sales")

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "human-os-3.0",
            "additionalModelRequestFields": {"skills": {"leijun": {"enabled": True}}},
            "messages": [
                {"role": "system", "content": "你是助手"},
                {"role": "user", "content": "第一轮"},
                {"role": "assistant", "content": "收到"},
                {"role": "user", "content": "继续"},
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["choices"][0]["message"]["content"] == "真实路径回答:继续"
    trace = real_path_executor[-1]["trace"]
    assert_r1_observation_present(trace)
    assert trace["skill_context_used"] is True
    assert trace["skill_extension_used"] == ["leijun"]
    assert trace["skill_structure_override_risk"] is True


def test_openai_chat_non_stream_without_leijun_records_skill_off(api_client, monkeypatch, real_path_executor):
    client, _ = api_client
    _stub_openai_skill_loading(monkeypatch, skill_id=None)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "human-os-3.0",
            "messages": [{"role": "user", "content": "你好"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["choices"][0]["message"]["content"] == "真实路径回答:你好"
    trace = real_path_executor[-1]["trace"]
    assert_r1_observation_present(trace)
    assert trace["skill_context_used"] is True
    assert trace["default_scene_skill_used"] is True
    assert trace["skill_extension_used"] == []
    assert isinstance(trace["skill_structure_override_risk"], bool)


def test_openai_chat_requires_at_least_one_message(api_client):
    client, _ = api_client

    response = client.post(
        "/v1/chat/completions",
        json={"model": "human-os-3.0", "messages": []},
    )

    assert response.status_code == 422


def test_openai_stream_uses_streaming_pipeline_and_done(api_client, monkeypatch, real_path_executor):
    client, _ = api_client
    _stub_openai_skill_loading(monkeypatch, skill_id=None)

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "human-os-3.0",
            "stream": True,
            "messages": [{"role": "user", "content": "给我一个回答"}],
        },
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert '"role": "assistant"' in body
    assert '"content": "真实路"' in body
    assert '"finish_reason": "stop"' in body
    assert "data: [DONE]" in body
    assert_r1_observation_present(real_path_executor[-1]["trace"])


def test_identity_repair_fallback_and_internal_leak_observation_fields():
    identity_context = Context(session_id="identity-check")
    identity_state = {
        "context": identity_context,
        "user_input": "你是哪个模型",
        "runtime_trace": {},
    }
    step1_8_response_obligation_observation(identity_state)
    assert identity_state["runtime_trace"]["identity_truth_required"] is True

    repair_context = Context(session_id="repair-check")
    repair_context.history.append(
        HistoryItem(
            role="system",
            content="我在，你可以多说一点。",
            metadata={
                "response_obligation": {"user_goal": "上一轮任务"},
                "final_answer_observed": {"output_satisfies_obligation": False},
            },
        )
    )
    repair_state = {
        "context": repair_context,
        "user_input": "你这回答也太离谱了",
        "runtime_trace": {},
    }
    step1_8_response_obligation_observation(repair_state)
    assert repair_state["runtime_trace"]["repair_obligation_required"] is True

    fallback_context = Context(session_id="fallback-check")
    fallback_state = {
        "context": fallback_context,
        "user_input": "怎么提升团队执行效率",
        "runtime_trace": {},
    }
    step1_8_response_obligation_observation(fallback_state)
    observe_final_output(fallback_state, fallback_context, "我在。你可以再多说一点，我帮你接住。", fallback_used=True)
    fallback_check = fallback_state["runtime_trace"]["fallback_obligation_check"]
    assert fallback_check["fallback_used"] is True
    assert fallback_check["fallback_generic_observed"] is True
    assert fallback_check["fallback_satisfies_obligation"] is False

    leak_context = Context(session_id="leak-check")
    leak_state = {
        "context": leak_context,
        "user_input": "我和女朋友吵架了怎么办",
        "runtime_trace": {},
    }
    step1_8_response_obligation_observation(leak_state)
    observe_final_output(leak_state, leak_context, "本轮建议先承认感受，再留一句空间。", fallback_used=False)
    final_obs = leak_state["runtime_trace"]["final_answer_observed"]
    assert final_obs["deliverable_observed"] == "meta_strategy"
    assert final_obs["internal_strategy_leak_observed"] is True
