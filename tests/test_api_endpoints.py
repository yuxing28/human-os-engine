from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel

from api import openai_adapter, routes
from api.session_store import SessionStore
from schemas.context import Context


class RecordingGraph:
    def __init__(self, output_prefix: str = "reply"):
        self.output_prefix = output_prefix
        self.calls: list[dict] = []

    def invoke(self, payload):
        context = payload["context"]
        user_input = payload["user_input"]
        self.calls.append(
            {
                "session_id": context.session_id,
                "history_roles": [item.role for item in context.history],
                "history_size": len(context.history),
                "scene_id": getattr(context.scene_config, "scene_id", None),
                "skill_prompt": getattr(context, "skill_prompt", ""),
                "user_input": user_input,
            }
        )
        context.add_history("user", user_input)
        context.add_history("system", f"{self.output_prefix}:{user_input}")
        context.output = f"{self.output_prefix}:{user_input}"
        return {
            "context": context,
            "output": context.output,
            "priority": {"priority_type": "test"},
            "selected_mode": "A",
        }


class SceneStub(BaseModel):
    scene_id: str


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


def test_health_reports_session_count(api_client):
    client, store = api_client
    context = Context(session_id="health-001")
    store.save_session("health-001", context)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["sessions_count"] == 1


def test_chat_reuses_existing_session_context(api_client, monkeypatch):
    client, store = api_client
    graph = RecordingGraph(output_prefix="chat")
    monkeypatch.setattr(routes, "get_graph", lambda: graph)

    first = client.post("/chat", json={"session_id": "sess001", "user_input": "第一句"})
    second = client.post("/chat", json={"session_id": "sess001", "user_input": "第二句"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["session_id"] == "sess001"
    assert second.json()["session_id"] == "sess001"
    assert graph.calls[0]["history_size"] == 0
    assert graph.calls[1]["history_size"] == 2
    assert "mode" not in first.json()
    assert "priority" not in first.json()
    assert "emotion" not in first.json()
    assert "input_type" not in first.json()
    restored = store.load_session("sess001")
    assert restored is not None
    assert len(restored.history) == 4
    assert restored.history[-1].content == "chat:第二句"


def test_chat_rejects_invalid_session_id(api_client):
    client, _ = api_client

    response = client.post("/chat", json={"session_id": "../bad", "user_input": "你好"})

    assert response.status_code == 400
    assert "session_id" in response.json()["detail"]


def test_chat_returns_500_when_graph_fails(api_client, monkeypatch):
    client, _ = api_client

    class BrokenGraph:
        def invoke(self, payload):
            raise RuntimeError("boom")

    monkeypatch.setattr(routes, "get_graph", lambda: BrokenGraph())

    response = client.post("/chat", json={"session_id": "safe123", "user_input": "你好"})

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"


def test_chat_stream_only_emits_final_display_output(api_client, monkeypatch):
    client, store = api_client
    import graph.streaming_pipeline as streaming_pipeline

    def execute_streaming_response(context, user_input):
        context.scene_config = SceneStub(scene_id="sales")
        context.output = "最终成品"
        context.add_history("user", user_input)
        context.add_history("system", context.output)
        return context, context.output

    monkeypatch.setattr(streaming_pipeline, "execute_streaming_response", execute_streaming_response)

    with client.stream(
        "POST",
        "/chat/stream",
        json={"session_id": "stream01", "user_input": "来一段"},
    ) as response:
        body = "".join(response.iter_text())

    assert response.status_code == 200
    assert "event: status" not in body
    assert "event: token" in body
    assert '"token": "最终成"' in body
    assert '"token": "品"' in body
    assert "event: complete" in body
    assert '"session_id": "stream01"' in body
    assert "你" not in body
    assert "好" not in body
    restored = store.load_session("stream01")
    assert restored is not None
    assert restored.output == "最终成品"


def test_openai_models_endpoint_returns_model_list(api_client):
    client, _ = api_client

    response = client.get("/v1/models")

    assert response.status_code == 200
    payload = response.json()
    assert payload["object"] == "list"
    assert payload["data"][0]["id"] == "human-os-3.0"


def test_openai_chat_rebuilds_history_and_falls_back_to_sales(api_client, monkeypatch):
    client, _ = api_client
    graph = RecordingGraph(output_prefix="oa")
    import modules.L5.skill_registry as skill_registry

    class FakeRegistry:
        def match_skill(self, full_context):
            return "broken-skill"

        def get_skill_prompt(self, skill_id):
            return f"prompt:{skill_id}"

        def build_skill_prompt(self, skill_id, _world_state=None):
            return self.get_skill_prompt(skill_id)

    def fake_load_scene_config(scene_id):
        if scene_id == "broken-skill":
            raise ValueError("broken")
        return SimpleNamespace(scene_id=scene_id)

    monkeypatch.setattr(openai_adapter, "get_registry", lambda: FakeRegistry())
    monkeypatch.setattr(skill_registry, "get_registry", lambda: FakeRegistry())
    monkeypatch.setattr(openai_adapter, "load_scene_config", fake_load_scene_config)
    monkeypatch.setattr(openai_adapter, "get_graph_cached", lambda: graph)

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
    assert payload["choices"][0]["message"]["content"] == "oa:继续"
    assert graph.calls[0]["history_roles"] == ["system", "user", "system"]
    assert graph.calls[0]["scene_id"] == "sales"
    assert graph.calls[0]["skill_prompt"].startswith("prompt:sales")
    assert "【可选人格扩展包】" in graph.calls[0]["skill_prompt"]
    assert "【雷军产品扩展禁区】" in graph.calls[0]["skill_prompt"]


def test_openai_chat_without_leijun_keeps_main_prompt_clean(api_client, monkeypatch):
    client, _ = api_client
    graph = RecordingGraph(output_prefix="oa")
    import modules.L5.skill_registry as skill_registry

    class FakeRegistry:
        def match_skill(self, full_context):
            return "sales"

        def get_skill_prompt(self, skill_id):
            return f"prompt:{skill_id}"

        def build_skill_prompt(self, skill_id, _world_state=None):
            return self.get_skill_prompt(skill_id)

    monkeypatch.setattr(openai_adapter, "get_registry", lambda: FakeRegistry())
    monkeypatch.setattr(skill_registry, "get_registry", lambda: FakeRegistry())
    monkeypatch.setattr(openai_adapter, "load_scene_config", lambda scene_id: SimpleNamespace(scene_id=scene_id))
    monkeypatch.setattr(openai_adapter, "get_graph_cached", lambda: graph)

    response = client.post(
        "/v1/chat/completions",
        json={
            "model": "human-os-3.0",
            "messages": [{"role": "user", "content": "你好"}],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["choices"][0]["message"]["content"] == "oa:你好"
    assert graph.calls[0]["scene_id"] == "sales"
    assert graph.calls[0]["skill_prompt"] == "prompt:sales"
    assert "【可选人格扩展包】" not in graph.calls[0]["skill_prompt"]
    assert "【雷军产品扩展禁区】" not in graph.calls[0]["skill_prompt"]


def test_openai_chat_requires_at_least_one_message(api_client):
    client, _ = api_client

    response = client.post(
        "/v1/chat/completions",
        json={"model": "human-os-3.0", "messages": []},
    )

    assert response.status_code == 422


def test_openai_stream_returns_sse_chunks_and_done(api_client, monkeypatch):
    client, _ = api_client
    import graph.streaming_pipeline as streaming_pipeline

    class FakeRegistry:
        def match_skill(self, full_context):
            return None

        def get_skill_prompt(self, skill_id):
            return ""

    def execute_streaming_response(context, user_input):
        context.output = "最终回答"
        return context, context.output

    monkeypatch.setattr(openai_adapter, "get_registry", lambda: FakeRegistry())
    monkeypatch.setattr(openai_adapter, "load_scene_config", lambda scene_id: SimpleNamespace(scene_id=scene_id))
    monkeypatch.setattr(openai_adapter, "get_graph_cached", lambda: object())
    monkeypatch.setattr(streaming_pipeline, "execute_streaming_response", execute_streaming_response)

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
    assert '"content": "最终回"' in body
    assert '"content": "答"' in body
    assert "x_status" not in body
    assert '"finish_reason": "stop"' in body
    assert "data: [DONE]" in body
