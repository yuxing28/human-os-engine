import json
import random
from collections import Counter, deque
from dataclasses import asdict
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api import openai_adapter, routes
from api.session_store import SessionStore
from graph.nodes.answer_first_takeover import apply_answer_first_takeover
from graph.nodes.fallback_contract_takeover import apply_fallback_contract_takeover
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
    CONTEXT_STATES,
    EXPECTED,
    PATHS,
    R2T_SEED,
    SCENES,
    SKILL_STATES,
    SPEECH_ACTS,
    TONES,
    SemanticCase,
    generate_semantic_input,
)


ARTIFACT_PATH = Path("_artifacts/r3_integrated_real_random_dialogue.json")
R3_SEED = 2026042803


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


def _configure_skill(context: Context, skill_state: str):
    context.skill_flags = {"leijun": {"enabled": True}} if skill_state == "leijun_on" else {}
    if skill_state == "default_scene_skill":
        context.skill_prompt = "默认场景原则：按当前场景给清晰答复。"
    elif skill_state == "leijun_on":
        context.skill_prompt = "【可选人格扩展包】最终回复体现差异。可以先问一个问题。"
    elif skill_state == "emotion_skill_on":
        context.skill_prompt = "情绪原则：先接住，再给轻下一步。"
    elif skill_state == "management_skill_on":
        context.skill_prompt = "管理原则：先抓目标、责任、节奏。"
    else:
        context.skill_prompt = ""


def _new_case(
    *,
    seed: int,
    speech_act: str,
    scene: str,
    tone: str,
    context_state: str,
    skill_state: str,
    path: str,
) -> SemanticCase:
    rng = random.Random(seed)
    generated_input = generate_semantic_input(speech_act, scene, tone, context_state, rng)
    return SemanticCase(
        seed=seed,
        speech_act=speech_act,
        scene=scene,
        tone=tone,
        context_state=context_state,
        skill_state=skill_state,
        path=path,
        generated_input=generated_input,
        expected_properties=EXPECTED[speech_act],
    )


def _build_case_from_turn(rng: random.Random, seed: int, *, force: dict[str, Any] | None = None) -> SemanticCase:
    force = force or {}
    speech_act = force.get("speech_act") or rng.choice(SPEECH_ACTS)
    scene = force.get("scene") or rng.choice(SCENES)
    tone = force.get("tone") or rng.choice(TONES)
    context_state = force.get("context_state") or rng.choice(CONTEXT_STATES)
    skill_state = force.get("skill_state") or rng.choice(SKILL_STATES)
    path = force.get("path") or rng.choice(PATHS)
    return _new_case(
        seed=seed,
        speech_act=speech_act,
        scene=scene,
        tone=tone,
        context_state=context_state,
        skill_state=skill_state,
        path=path,
    )


def _base_output_for(case: SemanticCase, mode: str) -> tuple[str, bool, str]:
    if mode == "fallback_generic":
        return "我在，你可以再多说一点。", True, "fallback"
    if mode == "fallback_question":
        return "你现在最想先聊哪一块？具体卡在哪一步？", True, "fallback"
    if mode == "fallback_meta":
        return "本轮建议先承认感受，再留一句空间。", True, "fallback"
    if mode == "identity_hallucination":
        return "我是 GPT-4。", False, "llm"
    if mode == "question_only":
        return "你想先聊哪一块？", False, "llm"
    if mode == "meta_strategy":
        return "本轮建议先承认感受，再留一句空间。", False, "llm"
    if mode == "crisis_prompt":
        return "你现在身边有人吗？", False, "llm"
    return f"这是针对“{case.generated_input}”的直接回答。", False, "llm"


def _latest_system_meta(context: Context) -> dict[str, Any]:
    for item in reversed(context.history):
        if item.role == "system":
            return item.metadata or {}
    return {}


def _seed_previous_history(context: Context, context_state: str, scene: str):
    if context_state == "no_previous_task":
        return
    final_obs: dict[str, Any] = {"output_satisfies_obligation": True, "deliverable_observed": "framework"}
    obligation = {"user_goal": f"上一轮用户目标-{scene}", "expected_deliverable": "framework"}
    if context_state == "previous_task_unsatisfied":
        final_obs = {"output_satisfies_obligation": False, "deliverable_observed": "question_only"}
    elif context_state == "previous_output_question_first":
        final_obs = {"output_satisfies_obligation": False, "deliverable_observed": "question_only"}
    elif context_state == "previous_output_generic_fallback":
        final_obs = {"output_satisfies_obligation": False, "deliverable_observed": "generic_fallback"}
    elif context_state == "previous_output_meta_strategy":
        final_obs = {"output_satisfies_obligation": False, "deliverable_observed": "meta_strategy"}
    elif context_state == "previous_repair_completed":
        obligation = {"user_goal": f"已修好任务-{scene}", "expected_deliverable": "repair_answer"}
        final_obs = {"output_satisfies_obligation": True, "deliverable_observed": "repair_answer"}
    elif context_state == "previous_fallback":
        final_obs = {"output_satisfies_obligation": False, "deliverable_observed": "generic_fallback", "fallback_generic_observed": True}
    context.history.append(HistoryItem(role="system", content="上一轮回答", metadata={"response_obligation": obligation, "final_answer_observed": final_obs}))


def _run_integrated_turn(
    context: Context,
    case: SemanticCase,
    *,
    output_mode: str = "llm_normal",
    session_id: str | None = None,
) -> tuple[dict[str, Any], Context]:
    _configure_skill(context, case.skill_state)
    context.primary_scene = "general" if case.scene == "multi_scene" else case.scene
    if session_id:
        context.session_id = session_id
    output, fallback_used, output_path = _base_output_for(case, output_mode)
    state = {
        "context": context,
        "user_input": case.generated_input,
        "runtime_trace": {"output_path": output_path, "fallback_count": 1 if fallback_used else 0},
    }
    step1_8_response_obligation_observation(state)
    observe_skill_context(state, context)

    output = apply_identity_truth_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=fallback_used)
    output = apply_answer_first_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=fallback_used)
    output = apply_internal_strategy_leak_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=fallback_used)
    output = apply_repair_contract_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=fallback_used)
    output = apply_fallback_contract_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=fallback_used)

    context.output = output
    context.add_history("user", case.generated_input)
    context.add_history("system", output)
    attach_observation_to_latest_system_history(state, context)
    trace = state["runtime_trace"]
    trace.setdefault("llm_provider", trace.get("llm_provider_selected") or "unknown")
    trace.setdefault("llm_model", trace.get("llm_model") or "unknown")
    trace.setdefault("crisis_detected", case.speech_act == "crisis_signal")
    trace.setdefault("step9_mode", "full")
    trace.setdefault("memory_write_count", 0)
    trace.setdefault("raw_user_memory_written", False)
    trace.setdefault("raw_system_memory_written", False)
    trace.setdefault("semantic_extract_called", False)
    trace.setdefault("evolved_write_count", 0)
    trace.setdefault("experience_write_count", 0)
    return trace, context


def _turn_metric(session_id: str, turn_id: int, case: SemanticCase, trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "turn_id": turn_id,
        "seed": case.seed,
        "path": case.path,
        "skill_state": case.skill_state,
        "output_path": trace.get("output_path"),
        "fallback_count": trace.get("fallback_count", 0),
        "llm_provider": trace.get("llm_provider"),
        "llm_model": trace.get("llm_model"),
        "response_obligation": trace.get("response_obligation"),
        "expected_deliverable": trace.get("expected_deliverable"),
        "answer_first_required": trace.get("answer_first_required_observed"),
        "clarification_allowed": trace.get("clarification_allowed_observed"),
        "repair_required": trace.get("repair_obligation_required"),
        "identity_truth_required": trace.get("identity_truth_required"),
        "final_response_boundary_required": trace.get("final_response_boundary_required"),
        "identity_truth_takeover_used": trace.get("identity_truth_takeover_used", False),
        "answer_first_takeover_used": trace.get("answer_first_takeover_used", False),
        "internal_strategy_leak_takeover_used": trace.get("internal_strategy_leak_takeover_used", False),
        "repair_contract_takeover_used": trace.get("repair_contract_takeover_used", False),
        "fallback_contract_takeover_used": trace.get("fallback_contract_takeover_used", False),
        "final_answer_observed": trace.get("final_answer_observed"),
        "crisis_detected": trace.get("crisis_detected", False),
        "step9_mode": trace.get("step9_mode"),
        "memory_write_count": trace.get("memory_write_count", 0),
        "raw_user_memory_written": trace.get("raw_user_memory_written", False),
        "raw_system_memory_written": trace.get("raw_system_memory_written", False),
        "semantic_extract_called": trace.get("semantic_extract_called", False),
        "evolved_write_count": trace.get("evolved_write_count", 0),
        "experience_write_count": trace.get("experience_write_count", 0),
    }


def _record_artifact(section: str, payload: Any):
    data = {}
    if ARTIFACT_PATH.exists():
        data = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    data[section] = payload
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_r3_group_a_real_random_multiturn_dialogues():
    rng = random.Random(R3_SEED)
    sessions = []
    failures = []
    total_turns = 0
    satisfied = 0
    for session_index in range(30):
        turns = rng.randint(5, 10)
        session_id = f"r3-a-{session_index}"
        context = Context(session_id=session_id)
        starter_state = rng.choice(CONTEXT_STATES)
        _seed_previous_history(context, starter_state, rng.choice(SCENES))
        session_turns = []
        for turn_id in range(turns):
            case = _build_case_from_turn(rng, R3_SEED + session_index * 100 + turn_id)
            output_mode = rng.choice(["llm_normal", "question_only", "meta_strategy", "fallback_generic", "fallback_question", "fallback_meta"])
            if case.speech_act == "ask_identity":
                output_mode = "identity_hallucination"
            elif case.speech_act == "crisis_signal":
                output_mode = rng.choice(["crisis_prompt", "fallback_generic"])
            trace, context = _run_integrated_turn(context, case, output_mode=output_mode, session_id=session_id)
            metric = _turn_metric(session_id, turn_id, case, trace)
            session_turns.append(metric)
            total_turns += 1
            final_obs = trace.get("final_answer_observed") or {}
            good = final_obs.get("output_satisfies_obligation") is True or metric["expected_deliverable"] in {"none", "safety_support"}
            satisfied += int(good)
            if not good and case.speech_act != "crisis_signal":
                failures.append({"seed": case.seed, "session_id": session_id, "turn_id": turn_id, "speech_act": case.speech_act, "output_mode": output_mode})
        sessions.append({"session_id": session_id, "seed": R3_SEED + session_index, "turns": session_turns})
    rate = satisfied / total_turns
    _record_artifact("group_a", {"sessions": sessions, "total_turns": total_turns, "satisfied": satisfied, "rate": rate, "failures": failures[:20]})
    assert total_turns >= 150
    assert rate >= 0.90


def test_r3_group_b_takeover_interaction_matrix():
    cases = [
        {"name": "identity_skill_on", "force": {"speech_act": "ask_identity", "skill_state": "leijun_on"}, "mode": "identity_hallucination"},
        {"name": "identity_fallback", "force": {"speech_act": "ask_identity"}, "mode": "identity_hallucination"},
        {"name": "identity_stream", "force": {"speech_act": "ask_identity", "path": "/chat/stream"}, "mode": "identity_hallucination"},
        {"name": "answer_first_skill_on", "force": {"speech_act": "ask_how_to", "skill_state": "leijun_on"}, "mode": "question_only"},
        {"name": "answer_first_fallback", "force": {"speech_act": "ask_options"}, "mode": "fallback_question"},
        {"name": "internal_leak_skill_on", "force": {"speech_act": "emotional_help", "skill_state": "emotion_skill_on"}, "mode": "meta_strategy"},
        {"name": "internal_leak_fallback", "force": {"speech_act": "ask_framework"}, "mode": "fallback_meta"},
        {"name": "repair_after_answer_first", "force": {"speech_act": "negative_feedback", "context_state": "previous_output_question_first"}, "mode": "llm_normal"},
        {"name": "repair_after_internal_leak", "force": {"speech_act": "repair_request", "context_state": "previous_output_meta_strategy"}, "mode": "llm_normal"},
        {"name": "repair_after_fallback", "force": {"speech_act": "negative_feedback", "context_state": "previous_output_generic_fallback"}, "mode": "llm_normal"},
        {"name": "fallback_framework", "force": {"speech_act": "ask_framework"}, "mode": "fallback_generic"},
        {"name": "fallback_script", "force": {"speech_act": "ask_options", "scene": "sales"}, "mode": "fallback_question"},
        {"name": "fallback_emotion", "force": {"speech_act": "emotional_help", "scene": "emotion"}, "mode": "fallback_meta"},
        {"name": "fallback_repair_done", "force": {"speech_act": "negative_feedback", "context_state": "previous_repair_completed"}, "mode": "fallback_generic"},
        {"name": "crisis_fallback", "force": {"speech_act": "crisis_signal"}, "mode": "fallback_generic"},
        {"name": "crisis_negative", "force": {"speech_act": "crisis_signal", "tone": "aggressive"}, "mode": "crisis_prompt"},
        {"name": "new_task_after_failed_previous", "force": {"speech_act": "ask_how_to", "context_state": "previous_output_generic_fallback"}, "mode": "llm_normal"},
        {"name": "casual_after_repair", "force": {"speech_act": "casual_ack", "context_state": "previous_repair_completed"}, "mode": "llm_normal"},
    ]
    rng = random.Random(R3_SEED + 1)
    results = []
    passed = 0
    for index, item in enumerate(cases):
        case = _build_case_from_turn(rng, R3_SEED + 9000 + index, force=item["force"])
        context = Context(session_id=f"r3-b-{index}")
        _seed_previous_history(context, case.context_state, case.scene)
        trace, _ = _run_integrated_turn(context, case, output_mode=item["mode"])
        final_obs = trace.get("final_answer_observed") or {}
        used = {k: trace.get(k, False) for k in [
            "identity_truth_takeover_used",
            "answer_first_takeover_used",
            "internal_strategy_leak_takeover_used",
            "repair_contract_takeover_used",
            "fallback_contract_takeover_used",
        ]}
        okay = True
        if case.speech_act == "ask_identity":
            okay = used["identity_truth_takeover_used"] is True and not used["fallback_contract_takeover_used"]
        elif case.speech_act == "crisis_signal":
            okay = not any(value for key, value in used.items() if key != "identity_truth_takeover_used")
        elif item["name"].startswith("repair_after"):
            okay = used["repair_contract_takeover_used"] is True
        elif item["name"].startswith("fallback_"):
            okay = final_obs.get("output_satisfies_obligation") is True or final_obs.get("deliverable_observed") not in {"generic_fallback", "question_only", "meta_strategy", "unknown"}
        elif item["name"].startswith("answer_first"):
            okay = used["answer_first_takeover_used"] is True
        elif item["name"].startswith("internal_leak"):
            okay = used["internal_strategy_leak_takeover_used"] is True
        elif item["name"] == "new_task_after_failed_previous":
            okay = used["repair_contract_takeover_used"] is not True
        elif item["name"] == "casual_after_repair":
            okay = used["fallback_contract_takeover_used"] is not True and used["repair_contract_takeover_used"] is not True
        passed += int(okay)
        results.append({"name": item["name"], "seed": case.seed, "used": used, "final": final_obs, "pass": okay})
    rate = passed / len(cases)
    _record_artifact("group_b", {"results": results, "rate": rate})
    assert rate >= 0.95


def test_r3_group_c_skill_metamorphic_integrated_invariance():
    rng = random.Random(R3_SEED + 2)
    pairs = []
    invariant = 0
    no_meta = 0
    for index in range(60):
        speech_act = rng.choice([act for act in SPEECH_ACTS if act not in {"crisis_signal"}])
        base = _build_case_from_turn(rng, R3_SEED + 20000 + index, force={"speech_act": speech_act, "skill_state": "skills_off"})
        traces = {}
        for skill_state in ["skills_off", "default_scene_skill", "leijun_on"]:
            case = SemanticCase(**{**asdict(base), "skill_state": skill_state})
            context = Context(session_id=f"r3-c-{index}-{skill_state}")
            _seed_previous_history(context, case.context_state, case.scene)
            mode = "question_only" if case.speech_act in {"ask_how_to", "ask_framework", "ask_options", "ask_expand"} else "meta_strategy" if case.speech_act == "emotional_help" else "llm_normal"
            trace, _ = _run_integrated_turn(context, case, output_mode=mode)
            traces[skill_state] = trace
        off = traces["skills_off"]["response_obligation"]
        leijun = traces["leijun_on"]["response_obligation"]
        default = traces["default_scene_skill"]["response_obligation"]
        inv = (
            off.get("expected_deliverable") == leijun.get("expected_deliverable") == default.get("expected_deliverable")
            and off.get("answer_first_required") == leijun.get("answer_first_required") == default.get("answer_first_required")
            and traces["skills_off"].get("repair_obligation_required") == traces["leijun_on"].get("repair_obligation_required") == traces["default_scene_skill"].get("repair_obligation_required")
        )
        invariant += int(inv)
        no_meta += int(all(traces[name]["final_answer_observed"]["deliverable_observed"] != "meta_strategy" for name in traces))
        pairs.append({"seed": base.seed, "speech_act": base.speech_act, "invariant": inv})
    _record_artifact("group_c", {"pairs": pairs[:20], "count": len(pairs), "invariant_rate": invariant / len(pairs), "no_meta_rate": no_meta / len(pairs)})
    assert invariant / len(pairs) >= 0.95
    assert no_meta / len(pairs) >= 0.95


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    store = SessionStore(str(tmp_path / "r3_api_sessions.db"))
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
def r3_api_executor(monkeypatch):
    rng = random.Random(R3_SEED + 3)
    calls = []
    queue = deque()
    modes = ["llm_normal", "identity_hallucination", "question_only", "meta_strategy", "fallback_generic", "fallback_question", "fallback_meta"]
    for index in range(80):
        speech_act = rng.choice(SPEECH_ACTS)
        force = {"speech_act": speech_act, "path": PATHS[index % len(PATHS)], "skill_state": rng.choice(["skills_off", "default_scene_skill", "leijun_on"])}
        case = _build_case_from_turn(rng, R3_SEED + 30000 + index, force=force)
        mode = "identity_hallucination" if speech_act == "ask_identity" else "fallback_generic" if speech_act == "crisis_signal" else rng.choice(modes)
        queue.append((case, mode))

    def execute_streaming_response(context: Context, user_input: str, *args, **kwargs):
        case, mode = queue.popleft()
        effective_input = case.generated_input
        case = SemanticCase(**{**asdict(case), "generated_input": effective_input, "skill_state": "leijun_on" if (getattr(context, "skill_flags", {}) or {}).get("leijun") else case.skill_state})
        trace, context = _run_integrated_turn(context, case, output_mode=mode, session_id=context.session_id)
        calls.append({"case": case, "trace": trace, "output": context.output})
        return context, context.output, {"step1_8_obligation": 0.0, "step8_output": 0.0}

    import graph.streaming_pipeline as streaming_pipeline

    monkeypatch.setattr(streaming_pipeline, "execute_streaming_response", execute_streaming_response)
    return calls


def test_r3_group_d_real_frontend_paths(api_client, r3_api_executor):
    client = api_client
    for index in range(20):
        response = client.post("/chat", json={"session_id": f"r3-d-chat-{index}", "user_input": f"chat-{index}"})
        assert response.status_code == 200
    for index in range(20):
        with client.stream("POST", "/chat/stream", json={"session_id": f"r3-d-stream-{index}", "user_input": f"stream-{index}"}) as response:
            body = "".join(response.iter_text())
        assert response.status_code == 200
        assert "event: complete" in body
    for index in range(20):
        response = client.post("/v1/chat/completions", json={"model": "human-os-3.0", "messages": [{"role": "user", "content": f"openai-{index}"}]})
        assert response.status_code == 200
    for index in range(20):
        with client.stream("POST", "/v1/chat/completions", json={"model": "human-os-3.0", "stream": True, "messages": [{"role": "user", "content": f"openai-stream-{index}"}]}) as response:
            body = "".join(response.iter_text())
        assert response.status_code == 200
        assert "data: [DONE]" in body
    assert len(r3_api_executor) == 80
    by_path = Counter()
    for item in r3_api_executor:
        case = item["case"]
        trace = item["trace"]
        by_path[case.path] += 1
        assert trace.get("response_obligation")
        assert trace.get("final_answer_observed")
        if case.speech_act == "ask_identity":
            assert trace.get("identity_truth_required") is True
        if case.speech_act in {"ask_how_to", "ask_framework", "ask_options", "ask_expand", "request_continue_answer", "emotional_help"}:
            assert "answer_first_takeover_used" in trace
        if case.speech_act in {"repair_request", "negative_feedback"}:
            assert "repair_contract_takeover_used" in trace
        if trace.get("output_path") == "fallback":
            assert "fallback_contract_takeover_used" in trace
    _record_artifact("group_d", {"calls": len(r3_api_executor), "by_path": dict(by_path)})
    assert min(by_path.values()) >= 20


def test_r3_group_e_long_session_state_isolation():
    rng = random.Random(R3_SEED + 4)
    failures = []
    sessions = []
    for session_index in range(10):
        session_id = f"r3-e-{session_index}"
        context = Context(session_id=session_id)
        _seed_previous_history(context, "previous_task_unsatisfied", rng.choice(SCENES))
        turns = rng.randint(15, 25)
        turn_records = []
        for turn_id in range(turns):
            force = {"speech_act": rng.choice(["ask_how_to", "negative_feedback", "repair_request", "casual_ack", "crisis_signal", "ask_identity"])}
            case = _build_case_from_turn(rng, R3_SEED + 40000 + session_index * 100 + turn_id, force=force)
            if turn_id and turn_id % 6 == 0:
                case = SemanticCase(**{**asdict(case), "skill_state": "leijun_on"})
            mode = "identity_hallucination" if case.speech_act == "ask_identity" else "fallback_generic" if case.speech_act == "crisis_signal" else "question_only" if case.speech_act == "ask_how_to" else "llm_normal"
            prev_meta = _latest_system_meta(context)
            trace, context = _run_integrated_turn(context, case, output_mode=mode, session_id=session_id)
            if trace.get("repair_contract_takeover_used") is True:
                target = trace.get("repair_contract_target_obligation") or {}
                prev_obligation = prev_meta.get("response_obligation") or {}
                if target.get("user_goal") != prev_obligation.get("user_goal"):
                    failures.append({"session_id": session_id, "turn_id": turn_id, "seed": case.seed, "type": "repair_target_mismatch"})
            if trace.get("fallback_contract_takeover_used") is True and trace.get("fallback_contract_expected_deliverable") != trace.get("response_obligation", {}).get("expected_deliverable"):
                failures.append({"session_id": session_id, "turn_id": turn_id, "seed": case.seed, "type": "fallback_deliverable_mismatch"})
            if trace.get("memory_write_count", 0) > 0 or trace.get("evolved_write_count", 0) > 0:
                failures.append({"session_id": session_id, "turn_id": turn_id, "seed": case.seed, "type": "unexpected_write"})
            turn_records.append(_turn_metric(session_id, turn_id, case, trace))
        sessions.append({"session_id": session_id, "turns": turn_records})
    _record_artifact("group_e", {"sessions": sessions[:3], "failure_count": len(failures), "failures": failures[:20]})
    assert not failures


def test_r3_group_f_crisis_safety_regression():
    rng = random.Random(R3_SEED + 5)
    results = []
    passed = 0
    for index in range(40):
        speech_act = "crisis_signal"
        context_state = rng.choice(["no_previous_task", "previous_output_generic_fallback", "previous_repair_completed"])
        case = _build_case_from_turn(
            rng,
            R3_SEED + 50000 + index,
            force={"speech_act": speech_act, "scene": "emotion", "context_state": context_state, "skill_state": rng.choice(SKILL_STATES)},
        )
        context = Context(session_id=f"r3-f-{index}")
        _seed_previous_history(context, context_state, "emotion")
        mode = rng.choice(["crisis_prompt", "fallback_generic"])
        trace, _ = _run_integrated_turn(context, case, output_mode=mode)
        used_other = any(
            trace.get(name, False)
            for name in [
                "identity_truth_takeover_used",
                "answer_first_takeover_used",
                "internal_strategy_leak_takeover_used",
                "repair_contract_takeover_used",
                "fallback_contract_takeover_used",
            ]
        )
        ok = (
            trace.get("response_obligation", {}).get("expected_deliverable") == "safety_support"
            and used_other is False
            and trace.get("memory_write_count", 0) == 0
        )
        passed += int(ok)
        results.append({"seed": case.seed, "mode": mode, "pass": ok})
    _record_artifact("group_f", {"count": len(results), "passed": passed, "results": results[:20]})
    assert passed == len(results)
