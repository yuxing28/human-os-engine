"""
Human-OS Engine 运行骨架

目标：
1. 把“单轮执行”的输入输出收成统一结构。
2. 降低 API/兼容接口之间的重复逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import time
from typing import Any, Callable, Iterable

from schemas.context import Context
from utils.logger import info


@dataclass
class EngineRequest:
    session_id: str
    user_input: str
    context: Context


@dataclass
class EngineResult:
    session_id: str
    output: str
    context: Context
    elapsed_ms: int
    timestamp: str
    raw_result: dict[str, Any]


class EngineRuntime:
    """单轮主链执行器。"""

    def __init__(self, graph_getter: Callable[[], Any]):
        self._graph_getter = graph_getter

    def run(self, request: EngineRequest) -> EngineResult:
        start = time.time()
        graph = self._graph_getter()
        result = graph.invoke({"context": request.context, "user_input": request.user_input})
        context = result.get("context", request.context)
        output = result.get("output", getattr(context, "output", "") or "")
        elapsed_ms = int((time.time() - start) * 1000)
        return EngineResult(
            session_id=request.session_id,
            output=output,
            context=context,
            elapsed_ms=elapsed_ms,
            timestamp=datetime.now().isoformat(),
            raw_result=result,
        )

    def run_stream(
        self,
        request: EngineRequest,
        *,
        stream_executor: Callable[[Context, str], tuple[Any, ...]] | None = None,
    ) -> EngineResult:
        start = time.time()
        if stream_executor is None:
            from graph.streaming_pipeline import execute_streaming_response

            stream_executor = execute_streaming_response

        stream_result = stream_executor(request.context, request.user_input)
        if len(stream_result) == 3:
            context, output, step_timings = stream_result
        elif len(stream_result) == 2:
            context, output = stream_result
            step_timings = {}
        else:
            raise ValueError("stream_executor must return 2 or 3 values")
        elapsed_ms = int((time.time() - start) * 1000)
        info(
            "单轮执行完成",
            session_id=request.session_id,
            elapsed_ms=elapsed_ms,
            step_timings=step_timings,
        )
        step_timings_ms = {name: int(round(value * 1000)) for name, value in step_timings.items()}
        raw_result = {
            "stream": True,
            "step_timings": step_timings,
            "step_timings_ms": step_timings_ms,
            "output_layers": getattr(context, "output_layers", {}) or {},
            "strategy_plan": getattr(context, "current_strategy", None),
            "weapons_used": [{"name": name} for name in getattr(context, "_last_weapons_used", []) or []],
        }
        return EngineResult(
            session_id=request.session_id,
            output=output or getattr(context, "output", "") or "",
            context=context,
            elapsed_ms=elapsed_ms,
            timestamp=datetime.now().isoformat(),
            raw_result=raw_result,
        )


class Renderer:
    """统一响应渲染，避免各入口重复拼字段。"""

    @staticmethod
    def chat_payload(result: EngineResult) -> dict[str, Any]:
        return {
            "session_id": result.session_id,
            "output": result.output,
            "elapsed_ms": result.elapsed_ms,
            "timestamp": result.timestamp,
        }

    @staticmethod
    def chunk_text(text: str, size: int = 3) -> Iterable[str]:
        for i in range(0, len(text), size):
            yield text[i:i + size]
