from modules.engine_runtime import EngineRequest, EngineRuntime, Renderer
from schemas.context import Context


class GraphWithOutput:
    def invoke(self, payload):
        context = payload["context"]
        user_input = payload["user_input"]
        context.output = f"ok:{user_input}"
        return {"context": context, "output": context.output}


class GraphWithoutOutputField:
    def invoke(self, payload):
        context = payload["context"]
        user_input = payload["user_input"]
        context.output = f"fallback:{user_input}"
        return {"context": context}


def test_engine_runtime_should_return_structured_result():
    runtime = EngineRuntime(lambda: GraphWithOutput())
    request = EngineRequest(session_id="s1", user_input="hello", context=Context(session_id="s1"))

    result = runtime.run(request)

    assert result.session_id == "s1"
    assert result.output == "ok:hello"
    assert result.context.output == "ok:hello"
    assert result.elapsed_ms >= 0
    assert result.timestamp


def test_engine_runtime_should_fallback_to_context_output_when_missing_output_field():
    runtime = EngineRuntime(lambda: GraphWithoutOutputField())
    request = EngineRequest(session_id="s2", user_input="hi", context=Context(session_id="s2"))

    result = runtime.run(request)

    assert result.output == "fallback:hi"


def test_renderer_chat_payload_should_keep_public_boundary():
    runtime = EngineRuntime(lambda: GraphWithOutput())
    result = runtime.run(
        EngineRequest(session_id="s3", user_input="go", context=Context(session_id="s3"))
    )

    payload = Renderer.chat_payload(result)

    assert set(payload.keys()) == {"session_id", "output", "elapsed_ms", "timestamp"}
    assert payload["session_id"] == "s3"
    assert payload["output"] == "ok:go"


def test_engine_runtime_run_stream_should_use_stream_executor():
    runtime = EngineRuntime(lambda: GraphWithOutput())
    context = Context(session_id="s4")

    def fake_stream_executor(ctx, user_input):
        ctx.output = f"stream:{user_input}"
        return ctx, ctx.output

    result = runtime.run_stream(
        EngineRequest(session_id="s4", user_input="hey", context=context),
        stream_executor=fake_stream_executor,
    )

    assert result.output == "stream:hey"
    assert result.context.output == "stream:hey"


def test_renderer_chunk_text_should_split_final_output():
    chunks = list(Renderer.chunk_text("最终成品", size=2))
    assert chunks == ["最终", "成品"]
