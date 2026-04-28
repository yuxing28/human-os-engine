"""
Human-OS Engine - FastAPI 接口

提供 HTTP API 服务，支持：
- /chat 端点：接收用户输入，返回系统输出
- /chat/stream 端点：最终定稿后的分块流式输出
- /health 端点：健康检查
- 会话管理：基于 session_id 的 Context 持久化
"""

import uuid
import time
import asyncio
import json
import os
import secrets
import threading
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from schemas.context import Context
from graph.builder import build_graph
from api.session_store import SessionStore
from modules.engine_runtime import EngineRequest, EngineRuntime, Renderer
from modules.L5.skill_extension_bridge import extract_skill_flags
from utils.types import normalize_external_session_id
from config.settings import settings
from utils import logger

# ===== 图缓存 =====
_graph_cache = None

def get_graph():
    """获取编译好的图（单例缓存）"""
    global _graph_cache
    if _graph_cache is None:
        _graph_cache = build_graph()
    return _graph_cache


# ===== 请求/响应模型 =====

class ChatRequest(BaseModel):
    session_id: str = Field(default="", description="会话ID", max_length=64)
    user_input: str = Field(..., description="用户输入", min_length=1, max_length=10000)
    stream: bool = Field(default=False, description="是否流式输出")
    additionalModelRequestFields: dict[str, Any] = Field(default_factory=dict)


class ChatResponse(BaseModel):
    session_id: str
    output: str
    elapsed_ms: int = 0
    timestamp: str = ""


class HealthResponse(BaseModel):
    status: str
    version: str
    sessions_count: int
    uptime_seconds: float


# ===== 会话管理 =====
MAX_SESSIONS = 1000
SESSION_TTL_SECONDS = 3600
SESSION_STORE_PATH = "data/api_sessions.db"

sessions: dict[str, Context] = {}
_session_last_access: dict[str, float] = {}
_sessions_lock = asyncio.Lock()
_start_time = time.time()
session_store = SessionStore(SESSION_STORE_PATH)


async def get_or_create_session(session_id: str) -> tuple[str, Context]:
    async with _sessions_lock:
        _cleanup_expired_sessions()
        if not session_id:
            session_id = str(uuid.uuid4())[:8]
        else:
            session_id = normalize_external_session_id(session_id)
        if session_id not in sessions:
            stored = session_store.load_session(session_id)
            sessions[session_id] = stored or Context(session_id=session_id)
        _session_last_access[session_id] = time.time()
        return session_id, sessions[session_id]


def _cleanup_expired_sessions():
    now = time.time()
    expired = [sid for sid, la in _session_last_access.items() if now - la > SESSION_TTL_SECONDS]
    for sid in expired:
        sessions.pop(sid, None)
        _session_last_access.pop(sid, None)
    session_store.cleanup_expired(SESSION_TTL_SECONDS)
    while len(sessions) > MAX_SESSIONS:
        oldest = min(_session_last_access, key=_session_last_access.get)
        sessions.pop(oldest, None)
        _session_last_access.pop(oldest, None)


async def update_session(session_id: str, context: Context):
    """更新会话（线程安全 + 更新访问时间）"""
    async with _sessions_lock:
        sessions[session_id] = context
        _session_last_access[session_id] = time.time()
        _cleanup_expired_sessions()
        session_store.save_session(session_id, context, _session_last_access[session_id])


def _extract_admin_token(request: Request) -> str:
    bearer = request.headers.get("Authorization", "").strip()
    if bearer.lower().startswith("bearer "):
        return bearer[7:].strip()
    return request.headers.get("X-Admin-Token", "").strip()


def _require_admin_access(request: Request) -> None:
    configured_token = settings.admin_api_key.strip()
    if not configured_token:
        raise HTTPException(status_code=403, detail="Admin endpoints are disabled")

    provided_token = _extract_admin_token(request)
    if not provided_token:
        raise HTTPException(status_code=401, detail="Admin authentication required")

    if not secrets.compare_digest(provided_token, configured_token):
        raise HTTPException(status_code=401, detail="Invalid admin token")


# ===== FastAPI 应用 =====

@asynccontextmanager
async def lifespan(app: FastAPI):
    os.makedirs("data", exist_ok=True)
    session_store.cleanup_expired(SESSION_TTL_SECONDS)
    # 后台预热 Chroma，避免首个请求同步初始化阻塞
    def _warmup_memory():
        try:
            from modules.memory import warmup_vector_store
            warmup_vector_store()
        except Exception:
            pass

    def _warmup_skills():
        try:
            from modules.L5.skill_registry import get_registry
            from modules.L5.scene_loader import load_scene_config

            registry = get_registry()
            for scene_id in getattr(registry, "skills", {}).keys():
                try:
                    load_scene_config(scene_id)
                except Exception:
                    pass
        except Exception:
            pass

    def _warmup_l2_runtime():
        try:
            from modules.L2.sins_keyword import identify_desires
            from modules.L2.collaboration_temperature import identify_emotion
            from modules.L2.dual_core_recognition import identify_dual_core
            from modules.L2.dimension_recognition import identify_dimensions

            seed_text = "你好"
            identify_desires(seed_text)
            identify_emotion(seed_text)
            identify_dual_core(seed_text)
            identify_dimensions(seed_text)
        except Exception:
            pass

    warmup_thread = threading.Thread(target=_warmup_memory, daemon=True)
    skills_thread = threading.Thread(target=_warmup_skills, daemon=True)
    l2_thread = threading.Thread(target=_warmup_l2_runtime, daemon=True)
    warmup_thread.start()
    skills_thread.start()
    l2_thread.start()
    logger.info("Human-OS Engine 启动", version="3.0", api="http://localhost:8000")
    yield
    if warmup_thread.is_alive():
        warmup_thread.join(timeout=1.0)
    if skills_thread.is_alive():
        skills_thread.join(timeout=1.0)
    if l2_thread.is_alive():
        l2_thread.join(timeout=1.0)
    try:
        from modules.memory import shutdown_memory_runtime
        shutdown_memory_runtime()
    except Exception:
        pass
    logger.info("Human-OS Engine 已关闭")


app = FastAPI(title="Human-OS Engine", description="目标导向、注意力驱动、平等博弈的人类行为引擎", version="3.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:3000", "http://localhost:8080"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

# 注册 OpenAI 兼容适配器
from api.openai_adapter import router as openai_router
app.include_router(openai_router)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    return HealthResponse(status="ok", version="3.0", sessions_count=session_store.count_sessions(), uptime_seconds=time.time() - _start_time)


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        session_id, context = await get_or_create_session(request.session_id)
        context.skill_flags = extract_skill_flags(request.additionalModelRequestFields)
        runtime = EngineRuntime(get_graph)
        engine_result = runtime.run_stream(
            EngineRequest(session_id=session_id, user_input=request.user_input, context=context)
        )
        await update_session(session_id, engine_result.context)
        return ChatResponse(**Renderer.chat_payload(engine_result))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    最终定稿后的分块流式输出

    内部完整执行判断与修正链路，对外只分块输出最终展示文本。
    """
    try:
        session_id, initial_ctx = await get_or_create_session(request.session_id)
        initial_ctx.skill_flags = extract_skill_flags(request.additionalModelRequestFields)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    async def event_stream() -> AsyncGenerator[str, None]:
        try:
            def emit_token(token: str):
                return f"event: token\ndata: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

            def emit_complete(result):
                payload = Renderer.chat_payload(result)
                return f"event: complete\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

            runtime = EngineRuntime(get_graph)
            stream_result = runtime.run_stream(
                EngineRequest(
                    session_id=session_id,
                    user_input=request.user_input,
                    context=initial_ctx,
                )
            )
            for token in Renderer.chunk_text(stream_result.output):
                yield emit_token(token)
            yield emit_complete(stream_result)
            await update_session(session_id, stream_result.context)

        except Exception as e:
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no",
    })

@app.get("/sessions")
async def list_sessions(request: Request):
    _require_admin_access(request)
    stored_sessions = session_store.list_sessions(limit=MAX_SESSIONS)
    return {"count": session_store.count_sessions(), "sessions": stored_sessions}


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    _require_admin_access(request)
    try:
        session_id = normalize_external_session_id(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    deleted = session_store.delete_session(session_id)
    if session_id in sessions:
        del sessions[session_id]
        _session_last_access.pop(session_id, None)
        deleted = True
    if deleted:
        return {"status": "deleted", "session_id": session_id}
    raise HTTPException(status_code=404, detail="Session not found")


@app.get("/admin/memory/write-summary/{session_id}")
async def get_memory_write_summary(session_id: str, request: Request, limit: int = 50):
    """查看指定会话的记忆写入汇总（受 admin token 保护）。"""
    _require_admin_access(request)
    try:
        session_id = normalize_external_session_id(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from modules.memory import get_memory_write_summary as _get_memory_write_summary

    summary = _get_memory_write_summary(session_id, limit=max(1, min(limit, 200)))
    return {"session_id": session_id, "summary": summary}


@app.get("/admin/memory/write-summary-global")
async def get_global_memory_write_summary(request: Request, limit_per_user: int = 50):
    """查看全局记忆写入汇总（受 admin token 保护）。"""
    _require_admin_access(request)

    from modules.memory import get_global_memory_write_summary as _get_global_memory_write_summary

    summary = _get_global_memory_write_summary(limit_per_user=max(1, min(limit_per_user, 200)))
    return {"summary": summary}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
