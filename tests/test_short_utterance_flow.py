from graph.nodes.step0_input import step0_receive_input
from schemas.context import Context


def _state_with_history(user_text: str, prev_user: str | None = None):
    ctx = Context(session_id="short-test")
    if prev_user is not None:
        ctx.add_history("user", prev_user)
    return {"context": ctx, "user_input": user_text}


def test_quick_response_enters_dynamic_flow():
    state = _state_with_history("嗯")
    result = step0_receive_input(state)
    assert result.get("skip_to_end") is False
    assert result["context"].short_utterance is True
    assert result["context"].short_utterance_reason == "quick_ack"


def test_ultra_short_enters_dynamic_flow():
    state = _state_with_history("好")
    result = step0_receive_input(state)
    assert result.get("skip_to_end") is False
    assert result["context"].short_utterance is True
    assert result["context"].short_utterance_reason in {"quick_ack", "ultra_short"}


def test_repeat_enters_dynamic_flow():
    state = _state_with_history("继续", prev_user="继续")
    result = step0_receive_input(state)
    assert result.get("skip_to_end") is False
    assert result["context"].short_utterance is True
    assert result["context"].short_utterance_reason == "repeat"
