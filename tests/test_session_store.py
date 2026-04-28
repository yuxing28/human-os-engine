import time
import pytest

from api.routes import get_or_create_session
from api.session_store import SessionStore
from modules import memory as memory_module
from modules.memory import MemoryManager, shutdown_memory_runtime
from schemas.context import Context


def test_session_store_can_save_and_load_context(tmp_path):
    db_path = str(tmp_path / "api_sessions.db")
    store = SessionStore(db_path)

    context = Context(session_id="sess-001")
    context.add_history("user", "你好")
    context.add_history("system", "你好，我在。")
    context.identity_hint = "创业者"
    context.situation_hint = "准备谈合作"

    store.save_session("sess-001", context, last_access=12345.0)
    restored = store.load_session("sess-001")

    assert restored is not None
    assert restored.session_id == "sess-001"
    assert restored.identity_hint == "创业者"
    assert restored.situation_hint == "准备谈合作"
    assert len(restored.history) == 2
    assert restored.history[0].content == "你好"


def test_session_store_lists_latest_user_input(tmp_path):
    db_path = str(tmp_path / "api_sessions.db")
    store = SessionStore(db_path)

    context = Context(session_id="sess-002")
    context.add_history("user", "第一句")
    context.add_history("system", "收到")
    context.add_history("user", "第二句")

    store.save_session("sess-002", context, last_access=200.0)
    sessions = store.list_sessions(limit=10)

    assert len(sessions) == 1
    assert sessions[0]["session_id"] == "sess-002"
    assert sessions[0]["history_count"] == 3
    assert sessions[0]["last_input"] == "第二句"


def test_session_store_cleanup_expired_and_delete(tmp_path):
    db_path = str(tmp_path / "api_sessions.db")
    store = SessionStore(db_path)

    old_context = Context(session_id="expired")
    fresh_context = Context(session_id="fresh")

    now = time.time()
    store.save_session("expired", old_context, last_access=now - 10)
    store.save_session("fresh", fresh_context, last_access=now)

    deleted_count = store.cleanup_expired(ttl_seconds=5)

    assert deleted_count == 1
    assert store.load_session("expired") is None
    assert store.load_session("fresh") is not None
    assert store.delete_session("fresh") is True
    assert store.load_session("fresh") is None


@pytest.mark.asyncio
async def test_get_or_create_session_rejects_unsafe_session_id():
    with pytest.raises(ValueError):
        await get_or_create_session("../evil")


def test_memory_manager_sanitizes_storage_directory(tmp_path):
    manager = MemoryManager(storage_dir=str(tmp_path / "memory"))
    try:
        manager.add_memory("../evil/path", "hello", importance=0.9)

        created_dirs = [p.name for p in (tmp_path / "memory").iterdir() if p.is_dir()]
        assert len(created_dirs) == 1
        assert ".." not in created_dirs[0]
        assert "/" not in created_dirs[0]
        assert "\\" not in created_dirs[0]
    finally:
        shutdown_memory_runtime()


def test_shutdown_memory_runtime_releases_global_client(tmp_path):
    class FakeSystem:
        def __init__(self):
            self.stopped = False

        def stop(self):
            self.stopped = True

    class FakeClient:
        def __init__(self, system):
            self._system = system
            self.cache_cleared = False

        def clear_system_cache(self):
            self.cache_cleared = True

    system = FakeSystem()
    client = FakeClient(system)

    memory_module._chroma_client = client
    memory_module._chroma_collections = {"user-1": object()}
    memory_module._session_memory = memory_module.SessionMemory(storage_dir=str(tmp_path / "sessions"))
    memory_module._memory_manager = MemoryManager(storage_dir=str(tmp_path / "memory"))

    assert shutdown_memory_runtime() is True
    assert client.cache_cleared is True
    assert system.stopped is True
    assert memory_module._chroma_client is None
    assert memory_module._chroma_collections == {}
    assert memory_module._session_memory is None
    assert memory_module._memory_manager is None
