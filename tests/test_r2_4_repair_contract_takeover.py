from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from api import openai_adapter, routes
from api.session_store import SessionStore
from graph.nodes.answer_first_takeover import apply_answer_first_takeover
from graph.nodes.identity_truth import apply_identity_truth_takeover
from graph.nodes.internal_strategy_leak_takeover import apply_internal_strategy_leak_takeover
from graph.nodes.repair_contract_takeover import apply_repair_contract_takeover
from graph.nodes.response_obligation_observer import (
    attach_observation_to_latest_system_history,
    observe_final_output,
    observe_skill_context,
    step1_8_response_obligation_observation,
)
from schemas.context import Context, HistoryItem
from tests.test_r2t_randomized_semantic_regression import (
    EXPECTED,
    R2T_SEED,
    SemanticCase,
)


PREVIOUS_DELIVERABLES = ["direct_answer", "framework", "steps", "options", "script", "emotional_support"]
BAD_OUTPUT_TYPES = ["question_only", "generic_fallback", "meta_strategy", "unknown", "empty_answer"]
REPAIR_SIGNALS = [
    "没听懂，重说",
    "你这回答没用",
    "不是这个意思，重新答",
    "别绕了，直接补",
    "我问的是具体方法",
    "这也太离谱了",
    "啥意思",
    "说人话",
]
SCENES = ["management", "sales", "negotiation", "emotion", "general"]
SKILL_STATES = ["skills_off", "default_scene_skill", "leijun_on", "emotion_skill_on"]
PATHS = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]

BAD_OUTPUT_TO_OBS = {
    "question_only": {"output_satisfies_obligation": False, "deliverable_observed": "question_only"},
    "generic_fallback": {"output_satisfies_obligation": False, "deliverable_observed": "generic_fallback"},
    "meta_strategy": {"output_satisfies_obligation": False, "deliverable_observed": "meta_strategy"},
    "unknown": {"output_satisfies_obligation": "Unknown", "deliverable_observed": "unknown"},
    "empty_answer": {"output_satisfies_obligation": False, "deliverable_observed": "unknown"},
}


def _has_repair_acknowledgement(output: str) -> bool:
    return any(
        marker in output
        for marker in [
            "刚刚确实没答到你要的点",
            "刚才那版没有接住重点",
            "没答到",
            "刚才我绕了一下",
            "你说得对",
            "前面那句太空了",
            "刚才没把",
            "刚才没有给到",
            "刚才没有真正接住",
            "直接补",
            "重新接一下",
            "补到这个问题上",
            "你要解决的是",
        ]
    )


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


def _case_for(text: str, speech_act: str = "repair_request", scene: str = "management") -> SemanticCase:
    expected = EXPECTED[speech_act]
    return SemanticCase(
        seed=R2T_SEED + sum(ord(ch) for ch in f"{text}:{speech_act}:{scene}"),
        speech_act=speech_act,
        scene=scene,
        tone="neutral",
        context_state="previous_output_generic",
        skill_state="skills_off",
        path="/chat",
        generated_input=text,
        expected_properties=expected,
    )


def _build_context(
    *,
    case: SemanticCase,
    previous_expected: str = "framework",
    previous_bad_output_type: str = "generic_fallback",
    previous_satisfied: bool | str | None = None,
) -> Context:
    context = Context(session_id=f"r2-4-{case.seed}")
    context.primary_scene = "general" if case.scene == "multi_scene" else case.scene
    context.skill_flags = {"leijun": {"enabled": True}} if case.skill_state == "leijun_on" else {}
    if case.skill_state == "default_scene_skill":
        context.skill_prompt = "默认场景原则：按当前场景给清晰答复。"
    elif case.skill_state == "leijun_on":
        context.skill_prompt = "【可选人格扩展包】最终回复体现差异。可以先问一个问题。"
    elif case.skill_state == "emotion_skill_on":
        context.skill_prompt = "情绪原则：先接住，再给轻下一步。"

    previous_final = dict(BAD_OUTPUT_TO_OBS[previous_bad_output_type])
    if previous_satisfied is not None:
        previous_final["output_satisfies_obligation"] = previous_satisfied
    previous_obligation = {
        "user_goal": f"上一轮用户目标-{previous_expected}",
        "expected_deliverable": previous_expected,
        "answer_first_required": True,
        "clarification_allowed": "after_answer",
        "repair_required": False,
        "identity_answer_required": False,
        "final_response_boundary_required": True,
        "observation_basis": {"route_scene": context.primary_scene},
    }
    context.history.append(
        HistoryItem(
            role="system",
            content="上一轮回答",
            metadata={
                "response_obligation": previous_obligation,
                "final_answer_observed": previous_final,
            },
        )
    )
    return context


def _run_repair_pipeline(
    case: SemanticCase,
    *,
    previous_expected: str = "framework",
    previous_bad_output_type: str = "generic_fallback",
    previous_satisfied: bool | str | None = None,
    original_output: str = "我在，你可以再多说一点。",
) -> tuple[dict, Context]:
    context = _build_context(
        case=case,
        previous_expected=previous_expected,
        previous_bad_output_type=previous_bad_output_type,
        previous_satisfied=previous_satisfied,
    )
    state = {"context": context, "user_input": case.generated_input, "runtime_trace": {}}
    step1_8_response_obligation_observation(state)
    observe_skill_context(state, context)
    output = apply_identity_truth_takeover(state, context, original_output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    output = apply_answer_first_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    output = apply_internal_strategy_leak_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    output = apply_repair_contract_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    context.output = output
    context.add_history("user", case.generated_input)
    context.add_history("system", output)
    attach_observation_to_latest_system_history(state, context)
    return state["runtime_trace"], context


def _repair_cases(total: int = 240) -> list[tuple[SemanticCase, str, str]]:
    cases: list[tuple[SemanticCase, str, str]] = []
    index = 0
    while len(cases) < total:
        previous_expected = PREVIOUS_DELIVERABLES[index % len(PREVIOUS_DELIVERABLES)]
        bad_output = BAD_OUTPUT_TYPES[(index // len(PREVIOUS_DELIVERABLES)) % len(BAD_OUTPUT_TYPES)]
        signal = REPAIR_SIGNALS[index % len(REPAIR_SIGNALS)]
        scene = SCENES[(index // 3) % len(SCENES)]
        skill_state = SKILL_STATES[(index // 5) % len(SKILL_STATES)]
        speech_act = "negative_feedback" if index % 2 else "repair_request"
        case = SemanticCase(
            seed=R2T_SEED + 400000 + index,
            speech_act=speech_act,
            scene=scene,
            tone="annoyed",
            context_state="previous_output_generic",
            skill_state=skill_state,
            path=PATHS[index % len(PATHS)],
            generated_input=signal,
            expected_properties=EXPECTED[speech_act],
        )
        cases.append((case, previous_expected, bad_output))
        index += 1
    return cases


def test_repair_random_semantic_takeover_contract():
    cases = _repair_cases(220)
    required = 0
    takeover_used = 0
    bad_after = 0
    completed = 0

    for case, previous_expected, bad_output in cases:
        trace, _ = _run_repair_pipeline(case, previous_expected=previous_expected, previous_bad_output_type=bad_output)
        if trace["repair_obligation_required"] is not True:
            continue
        required += 1
        takeover_used += int(trace["repair_contract_takeover_used"] is True)
        observed = trace["final_answer_observed"]["deliverable_observed"]
        bad_after += int(observed in {"question_only", "generic_fallback", "meta_strategy"})
        completed += int(
            trace["final_answer_observed"]["repair_completed_observed"] is True
            or trace["final_answer_observed"]["output_satisfies_obligation"] is True
        )
        assert _has_repair_acknowledgement(_.output)

    assert required >= 200
    assert takeover_used / required >= 0.90
    assert bad_after / required <= 0.05
    assert completed / required >= 0.90


def test_negative_feedback_does_not_talk_back():
    case = _case_for("你这回答也太离谱了", speech_act="negative_feedback", scene="management")
    trace, context = _run_repair_pipeline(case, previous_expected="steps", previous_bad_output_type="question_only")
    assert trace["repair_contract_takeover_used"] is True
    forbidden = ["跟你耗", "你自己", "爱听不听", "不想听算了", "你也没说清楚"]
    assert not any(item in context.output for item in forbidden)
    assert _has_repair_acknowledgement(context.output)


def test_skill_metamorphic_repair_invariance():
    base = _case_for("我问的是具体方法，别绕", speech_act="negative_feedback", scene="management")
    checked = 0
    for skill_state in ["skills_off", "leijun_on", "default_scene_skill"]:
        case = SemanticCase(**{**asdict(base), "skill_state": skill_state})
        trace, _ = _run_repair_pipeline(case, previous_expected="framework", previous_bad_output_type="meta_strategy")
        checked += 1
        assert trace["repair_obligation_required"] is True
        assert trace["repair_contract_takeover_used"] is True
        assert trace["repair_contract_target_obligation"]["expected_deliverable"] == "framework"
    assert checked == 3


def test_identity_crisis_and_new_task_are_not_repair_taken_over():
    identity_case = _case_for("你是哪个模型", speech_act="ask_identity", scene="general")
    identity_trace, _ = _run_repair_pipeline(identity_case, previous_expected="framework", previous_bad_output_type="generic_fallback", original_output="我是 GPT-4。")
    assert identity_trace["identity_truth_takeover_used"] is True
    assert identity_trace["repair_contract_takeover_used"] is not True

    crisis_case = _case_for("我不想活了", speech_act="crisis_signal", scene="emotion")
    crisis_trace, crisis_context = _run_repair_pipeline(crisis_case, previous_expected="framework", previous_bad_output_type="generic_fallback", original_output="你现在身边有人吗？")
    assert crisis_trace["response_obligation"]["expected_deliverable"] == "safety_support"
    assert crisis_trace["repair_contract_takeover_used"] is not True
    assert crisis_context.output == "你现在身边有人吗？"

    new_task_case = _case_for("给我几个管理方法", speech_act="ask_how_to", scene="management")
    new_task_trace, _ = _run_repair_pipeline(new_task_case, previous_expected="framework", previous_bad_output_type="generic_fallback")
    assert new_task_trace["repair_obligation_required"] is not True
    assert new_task_trace["repair_contract_takeover_used"] is not True


def test_regular_repair_smoke_cases():
    smoke = [
        ("没听懂，重说", "framework", "question_only"),
        ("你这回答没用", "steps", "generic_fallback"),
        ("刚才啥意思", "emotional_support", "meta_strategy"),
        ("你这也太离谱了", "options", "unknown"),
    ]
    for text, previous_expected, bad_type in smoke:
        case = _case_for(text, speech_act="negative_feedback" if "离谱" in text or "没用" in text else "repair_request")
        trace, context = _run_repair_pipeline(case, previous_expected=previous_expected, previous_bad_output_type=bad_type)
        assert trace["repair_contract_takeover_used"] is True
        assert trace["final_answer_observed"]["deliverable_observed"] not in {"question_only", "generic_fallback", "meta_strategy"}
        assert _has_repair_acknowledgement(context.output)
        assert trace.get("step9_mode", "full") != "degraded"


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    store = SessionStore(str(tmp_path / "r2_4_api_sessions.db"))
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
def api_repair_executor(monkeypatch):
    calls = []

    def execute_streaming_response(context: Context, user_input: str, *args, **kwargs):
        case = _case_for(user_input, speech_act="negative_feedback", scene="management")
        trace, context = _run_repair_pipeline(case, previous_expected="framework", previous_bad_output_type="generic_fallback")
        calls.append({"trace": trace, "output": context.output})
        return context, context.output, {"step1_8_obligation": 0.0, "step8_output": 0.0}

    import graph.streaming_pipeline as streaming_pipeline

    monkeypatch.setattr(streaming_pipeline, "execute_streaming_response", execute_streaming_response)
    return calls


def test_repair_takeover_real_api_paths(api_client, api_repair_executor):
    chat = api_client.post("/chat", json={"session_id": "r2-4-chat", "user_input": "你这回答没用"})
    assert chat.status_code == 200

    with api_client.stream(
        "POST",
        "/chat/stream",
        json={
            "session_id": "r2-4-stream",
            "user_input": "我问的是具体方法",
            "additionalModelRequestFields": {"skills": {"leijun": {"enabled": True}}},
        },
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "event: complete" in body

    non_stream = api_client.post(
        "/v1/chat/completions",
        json={"model": "human-os-3.0", "messages": [{"role": "user", "content": "别绕了，重新答"}]},
    )
    assert non_stream.status_code == 200

    with api_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "human-os-3.0",
            "stream": True,
            "messages": [{"role": "user", "content": "啥意思，说人话"}],
        },
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "data: [DONE]" in body

    assert len(api_repair_executor) == 4
    for call in api_repair_executor:
        trace = call["trace"]
        assert trace["repair_contract_takeover_used"] is True
        assert trace["final_answer_observed"]["deliverable_observed"] not in {"question_only", "generic_fallback", "meta_strategy"}
