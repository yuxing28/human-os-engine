from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from api import openai_adapter, routes
from api.session_store import SessionStore
from graph.nodes.answer_first_takeover import apply_answer_first_takeover
from graph.nodes.identity_truth import apply_identity_truth_takeover
from graph.nodes.response_obligation_observer import (
    attach_observation_to_latest_system_history,
    observe_final_output,
    observe_skill_context,
    step1_8_response_obligation_observation,
)
from schemas.context import Context
from tests.test_r2t_randomized_semantic_regression import (
    EXPECTED,
    R2T_SEED,
    SemanticCase,
    generate_cases,
)


ANSWER_FIRST_ACTS = {
    "ask_how_to",
    "ask_framework",
    "ask_options",
    "ask_expand",
    "request_continue_answer",
    "emotional_help",
}

QUESTION_FIRST_OUTPUTS = [
    "你现在最卡的是哪一步？",
    "你能再多说一点具体背景吗？",
    "你是想先解决目标，还是先解决执行？",
    "这个要看情况，你具体想问哪类？",
]

SMOKE_INPUTS = [
    "客户说贵，我该怎么回？",
    "团队执行力差怎么办？",
    "我和女朋友吵架了，她说不喜欢我了怎么办",
    "给我几个管理方法",
    "接上面讲",
    "这个是什么意思？",
    "我不想活了",
    "你是哪个模型",
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


def _run_answer_first_pipeline(
    case: SemanticCase,
    original_output: str = "你现在最卡的是哪一步？",
) -> tuple[dict, Context]:
    context = Context(session_id=f"r2-2-{case.seed}")
    context.primary_scene = "general" if case.scene == "multi_scene" else case.scene
    context.skill_flags = {"leijun": {"enabled": True}} if case.skill_state == "leijun_on" else {}
    if case.skill_state == "default_scene_skill":
        context.skill_prompt = "默认场景原则：按当前场景给清晰答复。"
    elif case.skill_state == "leijun_on":
        context.skill_prompt = "【可选人格扩展包】最终回复体现差异。可以先问一个问题。"
    elif case.skill_state == "management_skill_on":
        context.skill_prompt = "管理原则：先抓目标、责任、节奏。"
    elif case.skill_state == "emotion_skill_on":
        context.skill_prompt = "情绪原则：先接住，再给轻下一步。"

    state = {"context": context, "user_input": case.generated_input, "runtime_trace": {}}
    step1_8_response_obligation_observation(state)
    observe_skill_context(state, context)
    output = apply_identity_truth_takeover(state, context, original_output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    output = apply_answer_first_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    context.output = output
    context.add_history("user", case.generated_input)
    context.add_history("system", output)
    attach_observation_to_latest_system_history(state, context)
    return state["runtime_trace"], context


def _case_for(text: str, speech_act: str = "ask_how_to", scene: str = "management") -> SemanticCase:
    return SemanticCase(
        seed=R2T_SEED + abs(hash((text, speech_act, scene))) % 100000,
        speech_act=speech_act,
        scene=scene,
        tone="neutral",
        context_state="no_previous_task",
        skill_state="skills_off",
        path="/chat",
        generated_input=text,
        expected_properties=EXPECTED[speech_act],
    )


def test_answer_first_random_semantic_takeover_reduces_question_only():
    cases = [case for case in generate_cases(per_act=34) if case.speech_act in ANSWER_FIRST_ACTS]
    cases = cases[:204]
    assert len(cases) >= 200

    required = 0
    detected = 0
    takeover_used = 0
    question_only_after = 0

    for index, case in enumerate(cases):
        trace, _ = _run_answer_first_pipeline(case, QUESTION_FIRST_OUTPUTS[index % len(QUESTION_FIRST_OUTPUTS)])
        obligation = trace["response_obligation"]
        if obligation["answer_first_required"] and obligation["clarification_allowed"] != "before_answer":
            required += 1
            detected += int(trace["answer_first_violation_detected"] is True)
            takeover_used += int(trace["answer_first_takeover_used"] is True)
            question_only_after += int(trace["final_answer_observed"]["deliverable_observed"] == "question_only")
            assert trace["final_answer_observed"]["answer_first_satisfied"] is True

    assert required >= 180
    assert detected / required >= 0.90
    assert takeover_used / required >= 0.90
    assert question_only_after / required <= 0.05


def test_before_answer_clarification_is_not_taken_over():
    case = _case_for("嗯", speech_act="casual_ack", scene="general")
    trace, context = _run_answer_first_pipeline(case, "你想继续哪个部分？")
    assert trace["response_obligation"]["clarification_allowed"] == "before_answer"
    assert trace["answer_first_takeover_used"] is not True
    assert context.output == "你想继续哪个部分？"


def test_skill_metamorphic_answer_first_takeover_invariance():
    base_cases = [case for case in generate_cases(per_act=9) if case.speech_act in ANSWER_FIRST_ACTS]
    checked = 0
    for case in base_cases[:60]:
        off_case = SemanticCase(**{**asdict(case), "skill_state": "skills_off"})
        leijun_case = SemanticCase(**{**asdict(case), "skill_state": "leijun_on"})
        default_case = SemanticCase(**{**asdict(case), "skill_state": "default_scene_skill"})

        off_trace, _ = _run_answer_first_pipeline(off_case)
        leijun_trace, _ = _run_answer_first_pipeline(leijun_case)
        default_trace, _ = _run_answer_first_pipeline(default_case)

        checked += 1
        assert off_trace["response_obligation"]["expected_deliverable"] == leijun_trace["response_obligation"]["expected_deliverable"]
        assert off_trace["response_obligation"]["expected_deliverable"] == default_trace["response_obligation"]["expected_deliverable"]
        assert off_trace["response_obligation"]["answer_first_required"] == leijun_trace["response_obligation"]["answer_first_required"]
        assert off_trace["response_obligation"]["answer_first_required"] == default_trace["response_obligation"]["answer_first_required"]
        assert off_trace["answer_first_takeover_used"] == leijun_trace["answer_first_takeover_used"] == default_trace["answer_first_takeover_used"]
        assert leijun_trace["final_answer_observed"]["deliverable_observed"] != "question_only"
    assert checked >= 50


def test_identity_and_crisis_are_not_answer_first_taken_over():
    identity_case = _case_for("你是 GPT-4 吗", speech_act="ask_identity", scene="general")
    identity_trace, identity_context = _run_answer_first_pipeline(identity_case, "我是 GPT-4。")
    assert identity_trace["identity_truth_takeover_used"] is True
    assert identity_trace["answer_first_takeover_used"] is not True
    assert "我是 GPT-4" not in identity_context.output

    crisis_case = _case_for("我不想活了", speech_act="crisis_signal", scene="emotion")
    crisis_trace, crisis_context = _run_answer_first_pipeline(crisis_case, "你现在身边有人吗？")
    assert crisis_trace["response_obligation"]["expected_deliverable"] == "safety_support"
    assert crisis_trace["answer_first_takeover_used"] is not True
    assert crisis_context.output == "你现在身边有人吗？"


def test_regular_smoke_boundaries():
    for text in SMOKE_INPUTS:
        if "模型" in text:
            case = _case_for(text, speech_act="ask_identity")
            trace, _ = _run_answer_first_pipeline(case, "我是 GPT-4。")
            assert trace["identity_truth_takeover_used"] is True
            assert trace["answer_first_takeover_used"] is not True
        elif "不想活" in text:
            case = _case_for(text, speech_act="crisis_signal", scene="emotion")
            trace, _ = _run_answer_first_pipeline(case, "你现在身边有人吗？")
            assert trace["answer_first_takeover_used"] is not True
        else:
            speech_act = "emotional_help" if "女朋友" in text else "ask_how_to"
            scene = "emotion" if speech_act == "emotional_help" else "management"
            case = _case_for(text, speech_act=speech_act, scene=scene)
            trace, _ = _run_answer_first_pipeline(case, "你能再多说一点吗？")
            if trace["response_obligation"]["answer_first_required"]:
                assert trace["answer_first_takeover_used"] is True
                assert trace["final_answer_observed"]["deliverable_observed"] != "question_only"
        assert trace.get("step9_mode", "full") != "degraded"


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    store = SessionStore(str(tmp_path / "r2_2_api_sessions.db"))
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
        yield client

    routes.sessions.clear()
    routes._session_last_access.clear()
    routes._graph_cache = None
    if hasattr(openai_adapter.get_graph_cached, "graph"):
        delattr(openai_adapter.get_graph_cached, "graph")


@pytest.fixture
def api_answer_first_executor(monkeypatch):
    calls = []

    def execute_streaming_response(context: Context, user_input: str):
        case = _case_for(user_input, speech_act="ask_how_to", scene="management")
        trace, context = _run_answer_first_pipeline(case, "你现在最卡的是哪一步？")
        calls.append({"trace": trace, "output": context.output})
        return context, context.output, {"step1_8_obligation": 0.0, "step8_output": 0.0}

    import graph.streaming_pipeline as streaming_pipeline

    monkeypatch.setattr(streaming_pipeline, "execute_streaming_response", execute_streaming_response)
    return calls


def test_answer_first_takeover_real_api_paths(api_client, api_answer_first_executor):
    chat = api_client.post("/chat", json={"session_id": "r2-2-chat", "user_input": "团队执行力差怎么办"})
    assert chat.status_code == 200

    with api_client.stream(
        "POST",
        "/chat/stream",
        json={
            "session_id": "r2-2-stream",
            "user_input": "给我几个管理方法",
            "additionalModelRequestFields": {"skills": {"leijun": {"enabled": True}}},
        },
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "event: complete" in body

    non_stream = api_client.post(
        "/v1/chat/completions",
        json={"model": "human-os-3.0", "messages": [{"role": "user", "content": "怎么推进团队执行"}]},
    )
    assert non_stream.status_code == 200

    with api_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "human-os-3.0",
            "stream": True,
            "messages": [{"role": "user", "content": "给我几个管理方法"}],
        },
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "data: [DONE]" in body

    assert len(api_answer_first_executor) == 4
    for call in api_answer_first_executor:
        trace = call["trace"]
        assert trace["answer_first_takeover_used"] is True
        assert trace["final_answer_observed"]["deliverable_observed"] != "question_only"
