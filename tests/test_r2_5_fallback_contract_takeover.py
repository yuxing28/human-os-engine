from dataclasses import asdict

import pytest
from fastapi.testclient import TestClient

from api import openai_adapter, routes
from api.session_store import SessionStore
from graph.nodes.fallback_contract_takeover import apply_fallback_contract_takeover
from graph.nodes.identity_truth import apply_identity_truth_takeover
from graph.nodes.response_obligation_observer import (
    attach_observation_to_latest_system_history,
    observe_final_output,
    observe_skill_context,
    step1_8_response_obligation_observation,
)
from schemas.context import Context, HistoryItem
from tests.test_r2t_randomized_semantic_regression import EXPECTED, R2T_SEED, SemanticCase


EXPECTED_DELIVERABLES = [
    "direct_answer",
    "framework",
    "steps",
    "options",
    "script",
    "emotional_support",
    "repair_answer",
]
FALLBACK_BAD_TYPES = ["generic_fallback", "question_only", "meta_strategy", "unknown", "empty_answer"]
SCENES = ["management", "sales", "negotiation", "emotion", "general"]
SKILL_STATES = ["skills_off", "default_scene_skill", "leijun_on", "emotion_skill_on"]
PATHS = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]

BAD_OUTPUT_TEXT = {
    "generic_fallback": "我在，你可以再多说一点。",
    "question_only": "你现在最想先聊哪一块？具体卡在哪一步？",
    "meta_strategy": "本轮建议先承认感受，再留一句空间。",
    "unknown": "",
    "empty_answer": "",
}

PREVIOUS_FINAL_MAP = {
    "generic_fallback": {"output_satisfies_obligation": False, "deliverable_observed": "generic_fallback"},
    "question_only": {"output_satisfies_obligation": False, "deliverable_observed": "question_only"},
    "meta_strategy": {"output_satisfies_obligation": False, "deliverable_observed": "meta_strategy"},
    "unknown": {"output_satisfies_obligation": "Unknown", "deliverable_observed": "unknown"},
    "empty_answer": {"output_satisfies_obligation": False, "deliverable_observed": "unknown"},
}


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


def _speech_act_for(expected_deliverable: str) -> str:
    mapping = {
        "direct_answer": "ask_expand",
        "framework": "ask_how_to",
        "steps": "ask_how_to",
        "options": "ask_options",
        "script": "ask_script",
        "emotional_support": "emotional_help",
        "repair_answer": "negative_feedback",
    }
    return mapping[expected_deliverable]


def _input_for(expected_deliverable: str, scene: str) -> str:
    scene_word = {
        "management": "团队",
        "sales": "客户",
        "negotiation": "谈判",
        "emotion": "关系",
        "general": "事情",
    }[scene]
    mapping = {
        "direct_answer": f"这个是什么意思，和{scene_word}有关",
        "framework": f"给我一个{scene_word}处理框架",
        "steps": f"{scene_word}这件事具体怎么做",
        "options": f"{scene_word}这事先给我几个方向",
        "script": f"{scene_word}这事给我一段能直接说的话",
        "emotional_support": "我和女朋友吵架了，她说不喜欢我了怎么办",
        "repair_answer": "我问的是具体方法，别绕",
    }
    return mapping[expected_deliverable]


def _context_for(case: SemanticCase, previous_repair_completed: bool = False) -> Context:
    context = Context(session_id=f"r2-5-{case.seed}")
    context.primary_scene = "general" if case.scene == "multi_scene" else case.scene
    context.skill_flags = {"leijun": {"enabled": True}} if case.skill_state == "leijun_on" else {}
    if case.skill_state == "default_scene_skill":
        context.skill_prompt = "默认场景原则：按当前场景给清晰答复。"
    elif case.skill_state == "leijun_on":
        context.skill_prompt = "【可选人格扩展包】最终回复体现差异。可以先问一个问题。"
    elif case.skill_state == "emotion_skill_on":
        context.skill_prompt = "情绪原则：先接住，再给轻下一步。"

    if previous_repair_completed:
        context.history.append(
            HistoryItem(
                role="system",
                content="上一轮回答",
                metadata={
                    "response_obligation": {"user_goal": "上一轮已完成问题", "expected_deliverable": "framework", "observation_basis": {"route_scene": context.primary_scene}},
                    "final_answer_observed": {"output_satisfies_obligation": True, "deliverable_observed": "framework"},
                },
            )
        )
    return context


def _run_fallback_pipeline(
    case: SemanticCase,
    *,
    expected_deliverable: str,
    fallback_bad_type: str,
    previous_repair_completed: bool = False,
    clarification_before_answer: bool = False,
) -> tuple[dict, Context]:
    context = _context_for(case, previous_repair_completed=previous_repair_completed)
    state = {"context": context, "user_input": case.generated_input, "runtime_trace": {"output_path": "fallback"}}
    step1_8_response_obligation_observation(state)
    trace = state["runtime_trace"]
    obligation = trace.get("response_obligation", {})
    obligation["expected_deliverable"] = expected_deliverable
    obligation["answer_first_required"] = expected_deliverable != "none"
    obligation["clarification_allowed"] = "before_answer" if clarification_before_answer else ("not_allowed" if expected_deliverable == "repair_answer" else "after_answer")
    trace["response_obligation"] = obligation
    trace["expected_deliverable"] = expected_deliverable
    trace["answer_first_required_observed"] = obligation["answer_first_required"]
    trace["clarification_allowed_observed"] = obligation["clarification_allowed"]
    observe_skill_context(state, context)

    output = BAD_OUTPUT_TEXT[fallback_bad_type]
    output = apply_identity_truth_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=True)
    if previous_repair_completed:
        trace["repair_contract_takeover_used"] = True
        trace["post_repair_final_answer_observed"] = {
            "output_satisfies_obligation": True,
            "deliverable_observed": expected_deliverable,
        }
    output = apply_fallback_contract_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=True)
    context.output = output
    context.add_history("user", case.generated_input)
    context.add_history("system", output)
    attach_observation_to_latest_system_history(state, context)
    return state["runtime_trace"], context


def _fallback_cases(total: int = 280) -> list[tuple[SemanticCase, str, str]]:
    cases: list[tuple[SemanticCase, str, str]] = []
    for index in range(total):
        expected_deliverable = EXPECTED_DELIVERABLES[index % len(EXPECTED_DELIVERABLES)]
        fallback_bad_type = FALLBACK_BAD_TYPES[(index // len(EXPECTED_DELIVERABLES)) % len(FALLBACK_BAD_TYPES)]
        scene = SCENES[(index // 5) % len(SCENES)]
        skill_state = SKILL_STATES[(index // 7) % len(SKILL_STATES)]
        speech_act = "repair_request" if expected_deliverable == "repair_answer" else _speech_act_for(expected_deliverable)
        case = SemanticCase(
            seed=R2T_SEED + 500000 + index,
            speech_act=speech_act,
            scene=scene,
            tone="neutral",
            context_state="previous_fallback",
            skill_state=skill_state,
            path=PATHS[index % len(PATHS)],
            generated_input=_input_for(expected_deliverable, scene),
            expected_properties=EXPECTED.get(speech_act, EXPECTED["ask_how_to"]),
        )
        cases.append((case, expected_deliverable, fallback_bad_type))
    return cases


def test_fallback_contract_random_semantic_takeover():
    cases = _fallback_cases(300)
    required = 0
    takeover_used = 0
    bad_after = 0
    improved = 0

    for case, expected_deliverable, fallback_bad_type in cases:
        previous_repair_completed = expected_deliverable == "repair_answer" and (case.seed % 3 == 0)
        trace, _ = _run_fallback_pipeline(
            case,
            expected_deliverable=expected_deliverable,
            fallback_bad_type=fallback_bad_type,
            previous_repair_completed=previous_repair_completed,
        )
        if previous_repair_completed:
            assert trace["repair_contract_takeover_used"] is True
            assert trace["fallback_contract_takeover_used"] is not True
            continue
        fallback_check = trace.get("fallback_obligation_check") or {}
        pre_obs = trace.get("pre_fallback_contract_final_answer_observed") or {}
        final_obs = trace.get("final_answer_observed") or {}
        fallback_unsatisfied = (
            fallback_check.get("fallback_satisfies_obligation") is False
            or pre_obs.get("output_satisfies_obligation") is False
            or str(pre_obs.get("deliverable_observed") or "") in {"generic_fallback", "question_only", "meta_strategy", "unknown"}
        )
        if not fallback_unsatisfied:
            continue
        required += 1
        takeover_used += int(trace["fallback_contract_takeover_used"] is True)
        observed = final_obs["deliverable_observed"]
        bad_after += int(observed in {"generic_fallback", "question_only", "meta_strategy", "unknown"})
        improved += int(
            final_obs["output_satisfies_obligation"] is True
            or observed not in {"generic_fallback", "question_only", "meta_strategy", "unknown"}
        )

    assert required >= 250
    assert takeover_used / required >= 0.90
    assert bad_after / required <= 0.05
    assert improved / required >= 0.90


def test_skill_metamorphic_fallback_contract_invariance():
    base = SemanticCase(
        seed=R2T_SEED + 599001,
        speech_act="ask_how_to",
        scene="management",
        tone="neutral",
        context_state="previous_fallback",
        skill_state="skills_off",
        path="/chat",
        generated_input="给我一个管理框架",
        expected_properties=EXPECTED["ask_how_to"],
    )
    for skill_state in ["skills_off", "leijun_on", "default_scene_skill"]:
        case = SemanticCase(**{**asdict(base), "skill_state": skill_state})
        trace, _ = _run_fallback_pipeline(case, expected_deliverable="framework", fallback_bad_type="generic_fallback")
        assert trace["fallback_contract_required"] is True
        assert trace["fallback_contract_takeover_used"] is True
        assert trace["fallback_contract_expected_deliverable"] == "framework"


def test_identity_crisis_repair_completed_and_before_answer_are_skipped():
    identity_case = SemanticCase(
        seed=R2T_SEED + 599002,
        speech_act="ask_identity",
        scene="general",
        tone="neutral",
        context_state="previous_fallback",
        skill_state="skills_off",
        path="/chat",
        generated_input="你是哪个模型",
        expected_properties=EXPECTED["ask_identity"],
    )
    identity_trace, _ = _run_fallback_pipeline(identity_case, expected_deliverable="identity_answer", fallback_bad_type="generic_fallback")
    assert identity_trace["identity_truth_takeover_used"] is True
    assert identity_trace["fallback_contract_takeover_used"] is not True

    crisis_case = SemanticCase(
        seed=R2T_SEED + 599003,
        speech_act="crisis_signal",
        scene="emotion",
        tone="neutral",
        context_state="previous_fallback",
        skill_state="skills_off",
        path="/chat",
        generated_input="我不想活了",
        expected_properties=EXPECTED["crisis_signal"],
    )
    crisis_trace, crisis_context = _run_fallback_pipeline(crisis_case, expected_deliverable="safety_support", fallback_bad_type="generic_fallback")
    assert crisis_trace["fallback_contract_takeover_used"] is not True
    assert crisis_context.output == BAD_OUTPUT_TEXT["generic_fallback"]

    repair_done_case = SemanticCase(
        seed=R2T_SEED + 599004,
        speech_act="negative_feedback",
        scene="management",
        tone="neutral",
        context_state="previous_fallback",
        skill_state="skills_off",
        path="/chat",
        generated_input="我问的是具体方法",
        expected_properties=EXPECTED["negative_feedback"],
    )
    repair_done_trace, _ = _run_fallback_pipeline(
        repair_done_case,
        expected_deliverable="repair_answer",
        fallback_bad_type="generic_fallback",
        previous_repair_completed=True,
    )
    assert repair_done_trace["repair_contract_takeover_used"] is True
    assert repair_done_trace["fallback_contract_takeover_used"] is not True

    clarify_case = SemanticCase(
        seed=R2T_SEED + 599005,
        speech_act="casual_ack",
        scene="general",
        tone="neutral",
        context_state="previous_fallback",
        skill_state="skills_off",
        path="/chat",
        generated_input="嗯",
        expected_properties=EXPECTED["casual_ack"],
    )
    clarify_trace, _ = _run_fallback_pipeline(
        clarify_case,
        expected_deliverable="direct_answer",
        fallback_bad_type="question_only",
        clarification_before_answer=True,
    )
    assert clarify_trace["fallback_contract_takeover_used"] is not True


def test_regular_fallback_smoke_cases():
    smoke = [
        ("framework", "generic_fallback", "management"),
        ("script", "question_only", "sales"),
        ("emotional_support", "meta_strategy", "emotion"),
        ("steps", "unknown", "negotiation"),
    ]
    for expected_deliverable, fallback_bad_type, scene in smoke:
        case = SemanticCase(
            seed=R2T_SEED + 600000 + len(scene),
            speech_act=_speech_act_for(expected_deliverable),
            scene=scene,
            tone="neutral",
            context_state="previous_fallback",
            skill_state="leijun_on",
            path="/chat",
            generated_input=_input_for(expected_deliverable, scene),
            expected_properties=EXPECTED.get(_speech_act_for(expected_deliverable), EXPECTED["ask_how_to"]),
        )
        trace, _ = _run_fallback_pipeline(case, expected_deliverable=expected_deliverable, fallback_bad_type=fallback_bad_type)
        assert trace["fallback_contract_takeover_used"] is True
        assert trace["final_answer_observed"]["deliverable_observed"] not in {"generic_fallback", "question_only", "meta_strategy", "unknown"}
        assert trace.get("step9_mode", "full") != "degraded"


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    store = SessionStore(str(tmp_path / "r2_5_api_sessions.db"))
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
def api_fallback_executor(monkeypatch):
    calls = []

    def execute_streaming_response(context: Context, user_input: str, *args, **kwargs):
        case = SemanticCase(
            seed=R2T_SEED + 700000 + len(calls),
            speech_act="ask_how_to",
            scene="management",
            tone="neutral",
            context_state="previous_fallback",
            skill_state="leijun_on" if (getattr(context, "skill_flags", {}) or {}).get("leijun") else "skills_off",
            path="/chat",
            generated_input=user_input,
            expected_properties=EXPECTED["ask_how_to"],
        )
        trace, context = _run_fallback_pipeline(case, expected_deliverable="framework", fallback_bad_type="generic_fallback")
        calls.append({"trace": trace, "output": context.output})
        return context, context.output, {"step1_8_obligation": 0.0, "step8_output": 0.0}

    import graph.streaming_pipeline as streaming_pipeline

    monkeypatch.setattr(streaming_pipeline, "execute_streaming_response", execute_streaming_response)
    return calls


def test_fallback_contract_real_api_paths(api_client, api_fallback_executor):
    chat = api_client.post("/chat", json={"session_id": "r2-5-chat", "user_input": "给我一个管理框架"})
    assert chat.status_code == 200

    with api_client.stream(
        "POST",
        "/chat/stream",
        json={
            "session_id": "r2-5-stream",
            "user_input": "给我几个管理方向",
            "additionalModelRequestFields": {"skills": {"leijun": {"enabled": True}}},
        },
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "event: complete" in body

    non_stream = api_client.post(
        "/v1/chat/completions",
        json={"model": "human-os-3.0", "messages": [{"role": "user", "content": "给我一个管理框架"}]},
    )
    assert non_stream.status_code == 200

    with api_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "human-os-3.0",
            "stream": True,
            "messages": [{"role": "user", "content": "先给我几个方向"}],
        },
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "data: [DONE]" in body

    assert len(api_fallback_executor) == 4
    for call in api_fallback_executor:
        trace = call["trace"]
        assert trace["fallback_contract_takeover_used"] is True
        assert trace["final_answer_observed"]["deliverable_observed"] not in {"generic_fallback", "question_only", "meta_strategy", "unknown"}
