import time

import pytest
from fastapi.testclient import TestClient

from api import routes
from api.session_store import SessionStore
from schemas.context import Context
from modules import memory as memory_module


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    store = SessionStore(str(tmp_path / "api_sessions.db"))
    monkeypatch.setattr(routes, "session_store", store)
    routes.sessions.clear()
    routes._session_last_access.clear()

    with TestClient(routes.app) as client:
        yield client, store

    routes.sessions.clear()
    routes._session_last_access.clear()


def test_admin_endpoints_are_disabled_without_configured_key(api_env, monkeypatch):
    client, _ = api_env
    monkeypatch.setattr(routes.settings, "admin_api_key", "")

    response = client.get("/sessions")

    assert response.status_code == 403
    assert response.json()["detail"] == "Admin endpoints are disabled"


def test_admin_endpoints_require_valid_token(api_env, monkeypatch):
    client, _ = api_env
    monkeypatch.setattr(routes.settings, "admin_api_key", "top-secret")

    missing = client.get("/sessions")
    invalid = client.get("/sessions", headers={"X-Admin-Token": "wrong-token"})

    assert missing.status_code == 401
    assert missing.json()["detail"] == "Admin authentication required"
    assert invalid.status_code == 401
    assert invalid.json()["detail"] == "Invalid admin token"


def test_admin_token_allows_list_and_delete(api_env, monkeypatch):
    client, store = api_env
    monkeypatch.setattr(routes.settings, "admin_api_key", "top-secret")

    context = Context(session_id="sess-003")
    store.save_session("sess-003", context, last_access=time.time())

    list_response = client.get("/sessions", headers={"X-Admin-Token": "top-secret"})
    delete_response = client.delete(
        "/sessions/sess-003",
        headers={"Authorization": "Bearer top-secret"},
    )

    assert list_response.status_code == 200
    assert list_response.json()["count"] == 1
    assert list_response.json()["sessions"][0]["session_id"] == "sess-003"
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"
    assert store.load_session("sess-003") is None


def test_admin_can_read_memory_write_summary(api_env, monkeypatch, tmp_path):
    client, _ = api_env
    monkeypatch.setattr(routes.settings, "admin_api_key", "top-secret")
    memory_module._memory_manager = memory_module.MemoryManager(storage_dir=str(tmp_path / "memory"))
    memory_module.store_memory("sess-004", "用户: 我想推进这个项目", memory_type="conversation", importance=0.3)
    memory_module.store_memory("sess-004", "用户: 我想推进这个项目", memory_type="conversation", importance=0.3)

    response = client.get(
        "/admin/memory/write-summary/sess-004?limit=10",
        headers={"X-Admin-Token": "top-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["session_id"] == "sess-004"
    assert payload["summary"]["window_size"] >= 2
    assert payload["summary"]["stored"] >= 1
    assert payload["summary"]["skip_reasons"].get("duplicate_recent", 0) >= 1
    assert payload["summary"]["health"]["status"] in {"healthy", "strict", "noisy", "shallow", "blocked"}
    memory_module._memory_manager = None


def test_admin_can_read_global_memory_write_summary(api_env, monkeypatch, tmp_path):
    client, _ = api_env
    monkeypatch.setattr(routes.settings, "admin_api_key", "top-secret")
    memory_module._memory_manager = memory_module.MemoryManager(storage_dir=str(tmp_path / "memory-global"))
    memory_module.store_memory("sess-a", "用户偏好先讲结论", memory_type="preference", importance=0.8)
    memory_module.store_memory("sess-b", "用户: 好的", memory_type="conversation", importance=0.1)  # skipped

    response = client.get(
        "/admin/memory/write-summary-global?limit_per_user=20",
        headers={"X-Admin-Token": "top-secret"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert payload["summary"]["user_count"] >= 1
    assert "health" in payload["summary"]
    assert payload["summary"]["health"]["status"] in {"healthy", "strict", "noisy", "shallow", "blocked"}
    memory_module._memory_manager = None
