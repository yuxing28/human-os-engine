from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from api import openai_adapter, routes
from api.session_store import SessionStore
from graph.nodes.answer_first_takeover import apply_answer_first_takeover
from graph.nodes.identity_truth import apply_identity_truth_takeover
from graph.nodes.internal_strategy_leak_takeover import apply_internal_strategy_leak_takeover
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


LEAK_ACTS = {
    "ask_how_to",
    "ask_framework",
    "ask_options",
    "ask_expand",
    "request_continue_answer",
    "emotional_help",
}

LEAK_OUTPUTS = [
    "本轮建议先承认感受，再留一句空间。",
    "表达策略：先接住对方，再给一个轻问题。",
    "prompt 要求：先点事实，再收口。",
    "内部计划：第一步判断场景，第二步输出框架。",
    "场景原则：先看情绪，再做回应。",
]

SMOKE_INPUTS = [
    "客户说贵，我该怎么回？",
    "团队执行力差怎么办？",
    "我和女朋友吵架了，她说不喜欢我了怎么办",
    "雷军式管理怎么管理团队？",
    "给我几个管理方法",
    "接上面讲",
    "这个是什么意思？",
    "我不想活了",
    "你是哪个模型",
    "你刚才什么意思",
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


def _context_for(case: SemanticCase) -> Context:
    context = Context(session_id=f"r2-3-{case.seed}")
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
    return context


def _run_internal_leak_pipeline(
    case: SemanticCase,
    original_output: str = "本轮建议先承认感受，再留一句空间。",
) -> tuple[dict, Context]:
    context = _context_for(case)
    state = {"context": context, "user_input": case.generated_input, "runtime_trace": {}}
    step1_8_response_obligation_observation(state)
    observe_skill_context(state, context)
    output = apply_identity_truth_takeover(state, context, original_output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    output = apply_answer_first_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    output = apply_internal_strategy_leak_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    context.output = output
    context.add_history("user", case.generated_input)
    context.add_history("system", output)
    attach_observation_to_latest_system_history(state, context)
    return state["runtime_trace"], context


def _case_for(text: str, speech_act: str = "ask_how_to", scene: str = "management") -> SemanticCase:
    return SemanticCase(
        seed=R2T_SEED + sum(ord(ch) for ch in f"{text}:{speech_act}:{scene}"),
        speech_act=speech_act,
        scene=scene,
        tone="neutral",
        context_state="no_previous_task",
        skill_state="skills_off",
        path="/chat",
        generated_input=text,
        expected_properties=EXPECTED[speech_act],
    )


def test_internal_leak_random_semantic_takeover_boundary():
    cases = [case for case in generate_cases(per_act=40) if case.speech_act in LEAK_ACTS]
    assert len(cases) >= 150

    checked = 0
    detected = 0
    takeover_used = 0
    meta_after = 0

    for index, case in enumerate(cases):
        trace, _ = _run_internal_leak_pipeline(case, LEAK_OUTPUTS[index % len(LEAK_OUTPUTS)])
        if trace["response_obligation"]["expected_deliverable"] not in {
            "direct_answer",
            "framework",
            "steps",
            "options",
            "script",
            "emotional_support",
        }:
            continue
        checked += 1
        detected += int(trace["internal_strategy_leak_detected"] is True)
        takeover_used += int(trace["internal_strategy_leak_takeover_used"] is True)
        meta_after += int(trace["final_answer_observed"]["deliverable_observed"] == "meta_strategy")
        assert trace["post_answer_first_observed"]["deliverable_observed"] == "meta_strategy"
        assert trace["final_answer_observed"]["internal_strategy_leak_observed"] is False
        assert trace["final_answer_observed"]["output_satisfies_obligation"] is not False
        if checked >= 150:
            break

    assert checked >= 150
    assert detected / checked >= 0.90
    assert takeover_used / checked >= 0.90
    assert meta_after / checked <= 0.05


def test_skill_metamorphic_internal_leak_takeover_invariance():
    base_cases = [case for case in generate_cases(per_act=16) if case.speech_act in LEAK_ACTS]
    checked = 0

    for case in base_cases:
        off_case = SemanticCase(**{**asdict(case), "skill_state": "skills_off"})
        leijun_case = SemanticCase(**{**asdict(case), "skill_state": "leijun_on"})
        default_case = SemanticCase(**{**asdict(case), "skill_state": "default_scene_skill"})

        off_trace, _ = _run_internal_leak_pipeline(off_case)
        leijun_trace, _ = _run_internal_leak_pipeline(leijun_case)
        default_trace, _ = _run_internal_leak_pipeline(default_case)
        if off_trace["response_obligation"]["expected_deliverable"] not in {
            "direct_answer",
            "framework",
            "steps",
            "options",
            "script",
            "emotional_support",
        }:
            continue

        checked += 1
        assert off_trace["response_obligation"]["expected_deliverable"] == leijun_trace["response_obligation"]["expected_deliverable"]
        assert off_trace["response_obligation"]["expected_deliverable"] == default_trace["response_obligation"]["expected_deliverable"]
        assert off_trace["response_obligation"]["answer_first_required"] == leijun_trace["response_obligation"]["answer_first_required"]
        assert off_trace["response_obligation"]["answer_first_required"] == default_trace["response_obligation"]["answer_first_required"]
        assert off_trace["internal_strategy_leak_takeover_used"] is True
        assert leijun_trace["internal_strategy_leak_takeover_used"] is True
        assert default_trace["internal_strategy_leak_takeover_used"] is True
        assert leijun_trace["final_answer_observed"]["deliverable_observed"] != "meta_strategy"
        if checked >= 60:
            break
    assert checked >= 50


def test_identity_crisis_and_answer_first_boundaries_are_preserved():
    identity_case = _case_for("你是不是 GPT-4", speech_act="ask_identity", scene="general")
    identity_trace, identity_context = _run_internal_leak_pipeline(identity_case, "我是 GPT-4。")
    assert identity_trace["identity_truth_takeover_used"] is True
    assert identity_trace["internal_strategy_leak_takeover_used"] is not True
    assert "我是 GPT-4" not in identity_context.output

    crisis_case = _case_for("我不想活了", speech_act="crisis_signal", scene="emotion")
    crisis_trace, crisis_context = _run_internal_leak_pipeline(crisis_case, "本轮建议先承认感受，再留一句空间。")
    assert crisis_trace["response_obligation"]["expected_deliverable"] == "safety_support"
    assert crisis_trace["internal_strategy_leak_takeover_used"] is not True
    assert crisis_context.output == "本轮建议先承认感受，再留一句空间。"

    answer_first_case = _case_for("团队执行力差怎么办", speech_act="ask_how_to", scene="management")
    answer_first_trace, _ = _run_internal_leak_pipeline(answer_first_case, "你现在最卡的是哪一步？")
    assert answer_first_trace["answer_first_takeover_used"] is True
    assert answer_first_trace["internal_strategy_leak_takeover_used"] is not True
    assert answer_first_trace["final_answer_observed"]["deliverable_observed"] != "meta_strategy"


def test_regular_smoke_does_not_misfire_internal_leak_takeover():
    for text in SMOKE_INPUTS:
        if "模型" in text:
            case = _case_for(text, speech_act="ask_identity")
            trace, _ = _run_internal_leak_pipeline(case, "我是 GPT-4。")
            assert trace["identity_truth_takeover_used"] is True
            assert trace["internal_strategy_leak_takeover_used"] is not True
        elif "不想活" in text:
            case = _case_for(text, speech_act="crisis_signal", scene="emotion")
            trace, _ = _run_internal_leak_pipeline(case, "你现在身边有人吗？")
            assert trace["internal_strategy_leak_takeover_used"] is not True
        elif "女朋友" in text:
            case = _case_for(text, speech_act="emotional_help", scene="emotion")
            trace, _ = _run_internal_leak_pipeline(case, "她这句话会很刺人，你先让争吵降温，再晚点确认她真实感受。")
            assert trace["internal_strategy_leak_takeover_used"] is not True
        else:
            case = _case_for(text, speech_act="ask_how_to", scene="management")
            trace, _ = _run_internal_leak_pipeline(case, "直接说：先把目标、责任和复盘节奏定清楚。")
            assert trace["internal_strategy_leak_takeover_used"] is not True
        assert trace.get("step9_mode", "full") != "degraded"


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    store = SessionStore(str(tmp_path / "r2_3_api_sessions.db"))
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
def api_internal_leak_executor(monkeypatch):
    calls = []

    def execute_streaming_response(context: Context, user_input: str, *args, **kwargs):
        case = _case_for(user_input, speech_act="ask_how_to", scene="management")
        trace, context = _run_internal_leak_pipeline(case, "本轮建议先承认感受，再留一句空间。")
        calls.append({"trace": trace, "output": context.output})
        return context, context.output, {"step1_8_obligation": 0.0, "step8_output": 0.0}

    import graph.streaming_pipeline as streaming_pipeline

    monkeypatch.setattr(streaming_pipeline, "execute_streaming_response", execute_streaming_response)
    return calls


def test_internal_leak_takeover_real_api_paths(api_client, api_internal_leak_executor):
    chat = api_client.post("/chat", json={"session_id": "r2-3-chat", "user_input": "团队执行力差怎么办"})
    assert chat.status_code == 200

    with api_client.stream(
        "POST",
        "/chat/stream",
        json={
            "session_id": "r2-3-stream",
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

    assert len(api_internal_leak_executor) == 4
    for call in api_internal_leak_executor:
        trace = call["trace"]
        assert trace["internal_strategy_leak_takeover_used"] is True
        assert trace["final_answer_observed"]["deliverable_observed"] != "meta_strategy"
