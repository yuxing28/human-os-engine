"""
Human-OS Engine - OpenAI API 兼容适配器

实现 OpenAI 标准接口 (/v1/chat/completions, /v1/models)，
使 LobeChat、Open WebUI 等第三方客户端可以直接连接 Human-OS。
"""

import time
import uuid
import json
import asyncio
from typing import Any, AsyncGenerator, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from graph.builder import build_graph
from schemas.context import Context
from modules.engine_runtime import EngineRequest, EngineRuntime, Renderer
from modules.L5.scene_loader import load_scene_config
from modules.L5.skill_registry import get_registry
from modules.L5.skill_extension_bridge import compose_skill_prompt, extract_skill_flags
from utils import logger

router = APIRouter()

# ===== 数据模型 =====

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str = "human-os"
    messages: List[Message] = Field(min_length=1)
    stream: bool = False
    temperature: Optional[float] = 1.0
    max_tokens: Optional[int] = None
    additionalModelRequestFields: dict[str, Any] = Field(default_factory=dict)

class Choice(BaseModel):
    index: int = 0
    message: Optional[Message] = None
    delta: Optional[Message] = None
    finish_reason: Optional[str] = None

class Usage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage

# ===== 辅助函数 =====

def get_graph_cached():
    """获取图实例（简单缓存）"""
    if not hasattr(get_graph_cached, "graph"):
        get_graph_cached.graph = build_graph()
    return get_graph_cached.graph

def extract_user_input(messages: List[Message]) -> str:
    """从 OpenAI messages 中提取最后一个用户输入"""
    for msg in reversed(messages):
        if msg.role == "user":
            return msg.content
    return ""

def detect_scene_for_openai(user_input: str) -> str:
    """检测场景"""
    registry = get_registry()
    primary_id, _, _ = registry.match_scenes(user_input)
    return primary_id or "sales"


def _apply_scene_config(context: Context, skill_id: str | None) -> None:
    """优先加载匹配技能；失败时回退到默认销售场景，避免兼容接口直接 500。"""
    active_skill_id = skill_id or "sales"
    try:
        context.scene_config = load_scene_config(active_skill_id)
    except Exception as exc:
        if active_skill_id != "sales":
            logger.warning("OpenAI 兼容接口加载技能失败，改走默认场景", skill_id=active_skill_id, error=str(exc))
            active_skill_id = "sales"
            try:
                context.scene_config = load_scene_config(active_skill_id)
            except Exception as fallback_exc:
                logger.error("OpenAI 兼容接口加载默认场景失败", skill_id=active_skill_id, error=str(fallback_exc))
                return
        else:
            logger.error("OpenAI 兼容接口加载默认场景失败", skill_id=active_skill_id, error=str(exc))
            return

    context.skill_prompt = compose_skill_prompt(
        context,
        active_skill_id,
        getattr(context, "world_state", None),
    )
    if active_skill_id == skill_id:
        logger.info("OpenAI 兼容接口命中技能", skill_id=active_skill_id)
    else:
        logger.info("OpenAI 兼容接口回退到默认场景", skill_id=active_skill_id)

# ===== 路由 =====

@router.get("/v1/models")
async def list_models():
    """返回可用模型列表"""
    return {
        "object": "list",
        "data": [
            {
                "id": "human-os-3.0",
                "object": "model",
                "created": 1712000000,
                "owned_by": "human-os",
            }
        ],
    }

@router.post("/v1/chat/completions")
async def chat_completions(req: ChatRequest):
    """
    OpenAI 兼容聊天接口
    
    支持流式 (stream: true) 和非流式 (stream: false)。
    """
    # 1. 重建上下文历史 (OpenAI messages 已自带上下文，避免不同用户串会话)
    session_id = f"openai-{uuid.uuid4().hex[:12]}"
    context = Context(session_id=session_id)
    context.skill_flags = extract_skill_flags(req.additionalModelRequestFields)
    
    # 将历史消息加载到 Context 中 (排除最后一条当前输入)
    for msg in req.messages[:-1]:
        role = "user" if msg.role == "user" else "system"
        context.add_history(role, msg.content)

    # 获取当前用户输入
    user_input = req.messages[-1].content
    if not user_input:
        user_input = extract_user_input(req.messages) or "你好"
    
    # 2. 技能匹配与配置加载
    registry = get_registry()
    
    # 结合历史对话进行技能匹配，避免单句模糊导致场景丢失
    full_context = "\n".join([m.content for m in req.messages])
    skill_id = registry.match_skill(full_context)
    _apply_scene_config(context, skill_id)

    if req.stream:
        return StreamingResponse(
            _stream_response(req, context, user_input),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    else:
        runtime = EngineRuntime(get_graph_cached)
        engine_result = runtime.run_stream(
            EngineRequest(session_id=session_id, user_input=user_input, context=context)
        )
        output = engine_result.output
        
        return ChatResponse(
            id=f"chatcmpl-{uuid.uuid4().hex[:12]}",
            object="chat.completion",
            created=int(time.time()),
            model=req.model,
            choices=[
                Choice(
                    index=0,
                    message=Message(role="assistant", content=output),
                    finish_reason="stop",
                )
            ],
            usage=Usage(
                prompt_tokens=max(1, len(user_input) // 4),
                completion_tokens=max(1, len(output) // 4),
                total_tokens=max(1, len(user_input) // 4) + max(1, len(output) // 4),
            ),
        )

async def _stream_response(req: ChatRequest, context: Context, user_input: str) -> AsyncGenerator[str, None]:
    """生成 OpenAI 格式的流式响应，但对外只暴露最终定稿后的内容。"""
    queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    
    # 发送角色信息
    first_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": req.model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": ""},
                "finish_reason": None,
            }
        ],
    }
    yield f"data: {json.dumps(first_chunk, ensure_ascii=False)}\n\n"

    def run_stream_pipeline():
        """在后台线程中执行同步流式管道，并只推送最终定稿后的展示文本分块。"""
        def _push(item):
            loop.call_soon_threadsafe(queue.put_nowait, item)

        try:
            from graph.streaming_pipeline import execute_streaming_response

            stream_context, final_output, _step_timings = execute_streaming_response(
                context,
                user_input,
            )

            # 对外统一只输出最终定稿文本的分块流。
            for token in Renderer.chunk_text(final_output):
                _push(token)

            # 与 non-stream 保持一致：把最终上下文回写，方便后续扩展使用。
            context.output = final_output
            if hasattr(stream_context, "long_term_memory"):
                context.long_term_memory = stream_context.long_term_memory
            if hasattr(stream_context, "history"):
                context.history = stream_context.history
        except Exception as e:
            _push(e)
        finally:
            _push(None) # Sentinel

    # 在后台线程启动
    loop.run_in_executor(None, run_stream_pipeline)

    # 异步消费队列，只输出最终定稿后的内容 chunk
    while True:
        item = await queue.get()

        if item is None:
            break # 结束标记

        if isinstance(item, Exception):
            error_chunk = {
                "id": chunk_id,
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": req.model,
                "choices": [{"index": 0, "delta": {"content": f"Error: {str(item)}"}, "finish_reason": "stop"}],
            }
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
            break

        chunk = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": req.model,
            "choices": [{"index": 0, "delta": {"content": item}, "finish_reason": None}],
        }
        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"

    # 发送结束标记
    end_chunk = {
        "id": chunk_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": req.model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(end_chunk, ensure_ascii=False)}\n\n"
    yield "data: [DONE]\n\n"
