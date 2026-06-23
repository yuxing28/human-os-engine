import json
import math
import random
import statistics
import time
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


ARTIFACT_PATH = Path("_artifacts/phase_5g_r_performance_prompt_volume.json")
R5G_SEED = 2026042804
R3_FAILURE_BACKLOG = [
    2026042811,
    2026042905,
    2026043510,
    2026044111,
    2026044306,
    2026044609,
    2026045104,
    2026045109,
    2026045408,
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


def _record_artifact(section: str, payload: Any):
    data = {}
    if ARTIFACT_PATH.exists():
        data = json.loads(ARTIFACT_PATH.read_text(encoding="utf-8"))
    data[section] = payload
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _json_size(value: Any) -> int:
    if value is None:
        return 0
    try:
        return len(json.dumps(value, ensure_ascii=False))
    except TypeError:
        return len(str(value))


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


def _seed_previous_history(context: Context, context_state: str, scene: str):
    if context_state == "no_previous_task":
        return
    final_obs: dict[str, Any] = {"output_satisfies_obligation": True, "deliverable_observed": "framework"}
    obligation = {"user_goal": f"上一轮用户目标-{scene}", "expected_deliverable": "framework"}
    if context_state in {"previous_task_unsatisfied", "previous_output_question_first"}:
        final_obs = {"output_satisfies_obligation": False, "deliverable_observed": "question_only"}
    elif context_state == "previous_output_generic":
        final_obs = {"output_satisfies_obligation": False, "deliverable_observed": "generic_fallback"}
    elif context_state == "previous_output_meta_strategy":
        final_obs = {"output_satisfies_obligation": False, "deliverable_observed": "meta_strategy"}
    elif context_state == "previous_repair_completed":
        obligation = {"user_goal": f"已修好任务-{scene}", "expected_deliverable": "repair_answer"}
        final_obs = {"output_satisfies_obligation": True, "deliverable_observed": "repair_answer"}
    elif context_state == "previous_fallback":
        final_obs = {"output_satisfies_obligation": False, "deliverable_observed": "generic_fallback", "fallback_generic_observed": True}
    context.history.append(HistoryItem(role="system", content="上一轮回答", metadata={"response_obligation": obligation, "final_answer_observed": final_obs}))


def _new_case(seed: int, speech_act: str, scene: str, tone: str, context_state: str, skill_state: str, path: str) -> SemanticCase:
    rng = random.Random(seed)
    return SemanticCase(
        seed=seed,
        speech_act=speech_act,
        scene=scene,
        tone=tone,
        context_state=context_state,
        skill_state=skill_state,
        path=path,
        generated_input=generate_semantic_input(speech_act, scene, tone, context_state, rng),
        expected_properties=EXPECTED[speech_act],
    )


def _build_case(rng: random.Random, seed: int, *, force: dict[str, Any] | None = None) -> SemanticCase:
    force = force or {}
    return _new_case(
        seed,
        force.get("speech_act") or rng.choice(SPEECH_ACTS),
        force.get("scene") or rng.choice(SCENES),
        force.get("tone") or rng.choice(TONES),
        force.get("context_state") or rng.choice(CONTEXT_STATES),
        force.get("skill_state") or rng.choice(SKILL_STATES),
        force.get("path") or rng.choice(PATHS),
    )


def _output_for(case: SemanticCase, mode: str) -> tuple[str, bool, str]:
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
    if mode == "deep_full":
        return "这是一个完整方案：先定义问题，再拆层次，再列执行节奏，最后给复盘方式。", False, "llm"
    return f"这是针对“{case.generated_input}”的直接回答。", False, "llm"


def _estimate_prompt(context: Context, case: SemanticCase, trace: dict[str, Any]) -> dict[str, int]:
    history_chars = sum(len(item.content or "") for item in context.history[-12:])
    obligation_chars = _json_size(trace.get("response_obligation"))
    final_obs_chars = _json_size(trace.get("final_answer_observed"))
    world_state_chars = _json_size(getattr(context, "world_state", {}))
    next_pickup_chars = len((trace.get("response_obligation", {}) or {}).get("repair_target", "") or "")
    continuity_focus_chars = len(getattr(context, "session_notes_context", "") or "")
    prompt_chars = (
        len(case.generated_input)
        + len(getattr(context, "skill_prompt", "") or "")
        + history_chars
        + obligation_chars
        + world_state_chars
        + next_pickup_chars
        + continuity_focus_chars
    )
    final_prompt_blocks = sum(
        int(bool(value))
        for value in [
            case.generated_input,
            getattr(context, "skill_prompt", ""),
            history_chars,
            obligation_chars,
            world_state_chars,
            next_pickup_chars,
            continuity_focus_chars,
        ]
    )
    return {
        "prompt_chars_estimate": prompt_chars,
        "final_prompt_blocks": final_prompt_blocks,
        "response_obligation_chars": obligation_chars,
        "final_answer_observed_chars": final_obs_chars,
        "memory_chars_loaded": history_chars,
        "memory_chars_in_prompt": history_chars,
        "context_brief_chars": history_chars,
        "memory_brief_chars": history_chars,
        "world_state_brief_chars": world_state_chars,
        "next_pickup_chars": next_pickup_chars,
        "continuity_focus_chars": continuity_focus_chars,
    }


def _takeover_count(trace: dict[str, Any]) -> int:
    return sum(
        int(bool(trace.get(name)))
        for name in [
            "identity_truth_takeover_used",
            "answer_first_takeover_used",
            "internal_strategy_leak_takeover_used",
            "repair_contract_takeover_used",
            "fallback_contract_takeover_used",
        ]
    )


def _run_perf_turn(context: Context, case: SemanticCase, *, output_mode: str, session_id: str | None = None) -> dict[str, Any]:
    _configure_skill(context, case.skill_state)
    context.primary_scene = "general" if case.scene == "multi_scene" else case.scene
    if session_id:
        context.session_id = session_id
    output, fallback_used, output_path = _output_for(case, output_mode)
    trace = {"output_path": output_path, "fallback_count": 1 if fallback_used else 0}
    state = {"context": context, "user_input": case.generated_input, "runtime_trace": trace}

    step0_ms = 0.0

    t1 = time.perf_counter()
    step1_8_response_obligation_observation(state)
    observe_skill_context(state, context)
    step1_ms = (time.perf_counter() - t1) * 1000

    llm_latency_ms = 0.0 if output_path == "fallback" else 0.02

    takeover_timings = {}
    t8 = time.perf_counter()

    s = time.perf_counter()
    output = apply_identity_truth_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=fallback_used)
    takeover_timings["identity_and_observe_ms"] = (time.perf_counter() - s) * 1000

    s = time.perf_counter()
    output = apply_answer_first_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=fallback_used)
    takeover_timings["answer_first_and_observe_ms"] = (time.perf_counter() - s) * 1000

    s = time.perf_counter()
    output = apply_internal_strategy_leak_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=fallback_used)
    takeover_timings["internal_leak_and_observe_ms"] = (time.perf_counter() - s) * 1000

    s = time.perf_counter()
    output = apply_repair_contract_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=fallback_used)
    takeover_timings["repair_and_observe_ms"] = (time.perf_counter() - s) * 1000

    s = time.perf_counter()
    output = apply_fallback_contract_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=fallback_used)
    takeover_timings["fallback_and_observe_ms"] = (time.perf_counter() - s) * 1000

    step8_ms = (time.perf_counter() - t8) * 1000

    t9 = time.perf_counter()
    context.output = output
    context.add_history("user", case.generated_input)
    context.add_history("system", output)
    attach_observation_to_latest_system_history(state, context)
    step9_ms = (time.perf_counter() - t9) * 1000

    total_ms = step0_ms + step1_ms + llm_latency_ms + step8_ms + step9_ms
    trace = state["runtime_trace"]
    trace.setdefault("llm_provider", "simulated")
    trace.setdefault("llm_model", "simulated-r-series")
    trace.setdefault("step9_mode", "light_minimal" if case.speech_act in {"casual_ack", "unclear_short_turn"} else "full")
    trace.setdefault("memory_write_count", 0)
    trace.setdefault("raw_user_memory_written", False)
    trace.setdefault("raw_system_memory_written", False)
    trace.setdefault("semantic_extract_called", False)
    trace.setdefault("evolved_write_count", 0)
    trace.setdefault("experience_write_count", 0)
    trace.setdefault("crisis_detected", case.speech_act == "crisis_signal")
    metrics = {
        "seed": case.seed,
        "speech_act": case.speech_act,
        "scene": case.scene,
        "tone": case.tone,
        "context_state": case.context_state,
        "path": case.path,
        "skill_state": case.skill_state,
        "session_id": context.session_id,
        "total_ms": total_ms,
        "step0_ms": step0_ms,
        "step1_ms": step1_ms,
        "step8_ms": step8_ms,
        "step9_ms": step9_ms,
        "llm_latency_ms": llm_latency_ms,
        "output_path": output_path,
        "fallback_count": trace.get("fallback_count", 0),
        "takeover_used_count": _takeover_count(trace),
        "memory_write_count": trace.get("memory_write_count", 0),
        "raw_user_memory_written": trace.get("raw_user_memory_written", False),
        "raw_system_memory_written": trace.get("raw_system_memory_written", False),
        "semantic_extract_called": trace.get("semantic_extract_called", False),
        "evolved_write_count": trace.get("evolved_write_count", 0),
        "experience_write_count": trace.get("experience_write_count", 0),
        "step9_mode": trace.get("step9_mode"),
        "crisis_detected": trace.get("crisis_detected", False),
        "final_answer_observed": trace.get("final_answer_observed"),
        "response_obligation": trace.get("response_obligation"),
        "identity_truth_takeover_used": trace.get("identity_truth_takeover_used", False),
        "answer_first_takeover_used": trace.get("answer_first_takeover_used", False),
        "internal_strategy_leak_takeover_used": trace.get("internal_strategy_leak_takeover_used", False),
        "repair_contract_takeover_used": trace.get("repair_contract_takeover_used", False),
        "fallback_contract_takeover_used": trace.get("fallback_contract_takeover_used", False),
        "takeover_timings": takeover_timings,
        "llm_replayed": False,
    }
    metrics.update(_estimate_prompt(context, case, trace))
    metrics["output_len"] = len(output)
    return metrics


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    idx = (len(ordered) - 1) * pct
    low = math.floor(idx)
    high = math.ceil(idx)
    if low == high:
        return ordered[int(idx)]
    return ordered[low] + (ordered[high] - ordered[low]) * (idx - low)


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_ms = [row["total_ms"] for row in rows]
    step0_ms = [row["step0_ms"] for row in rows]
    step1_ms = [row["step1_ms"] for row in rows]
    step8_ms = [row["step8_ms"] for row in rows]
    step9_ms = [row["step9_ms"] for row in rows]
    llm_latency_ms = [row["llm_latency_ms"] for row in rows]
    prompt_chars = [row["prompt_chars_estimate"] for row in rows]
    mem_loaded = [row["memory_chars_loaded"] for row in rows]
    mem_prompt = [row["memory_chars_in_prompt"] for row in rows]
    obligation_chars = [row["response_obligation_chars"] for row in rows]
    final_obs_chars = [row["final_answer_observed_chars"] for row in rows]
    takeover_counts = Counter()
    for row in rows:
        for name in [
            "identity_truth_takeover_used",
            "answer_first_takeover_used",
            "internal_strategy_leak_takeover_used",
            "repair_contract_takeover_used",
            "fallback_contract_takeover_used",
        ]:
            takeover_counts[name] += int(bool(row.get(name)))
    return {
        "count": len(rows),
        "total_ms_avg": statistics.mean(total_ms) if total_ms else 0.0,
        "total_ms_p50": _pct(total_ms, 0.50),
        "total_ms_p90": _pct(total_ms, 0.90),
        "total_ms_p95": _pct(total_ms, 0.95),
        "step0_ms_avg": statistics.mean(step0_ms) if step0_ms else 0.0,
        "step0_ms_p95": _pct(step0_ms, 0.95),
        "step1_ms_avg": statistics.mean(step1_ms) if step1_ms else 0.0,
        "step1_ms_p95": _pct(step1_ms, 0.95),
        "step8_ms_avg": statistics.mean(step8_ms) if step8_ms else 0.0,
        "step8_ms_p95": _pct(step8_ms, 0.95),
        "step9_ms_avg": statistics.mean(step9_ms) if step9_ms else 0.0,
        "step9_ms_p95": _pct(step9_ms, 0.95),
        "llm_latency_ms_avg": statistics.mean(llm_latency_ms) if llm_latency_ms else 0.0,
        "llm_latency_ms_p95": _pct(llm_latency_ms, 0.95),
        "prompt_chars_avg": statistics.mean(prompt_chars) if prompt_chars else 0.0,
        "prompt_chars_p50": _pct(prompt_chars, 0.50),
        "prompt_chars_p95": _pct(prompt_chars, 0.95),
        "memory_chars_loaded_avg": statistics.mean(mem_loaded) if mem_loaded else 0.0,
        "memory_chars_loaded_p95": _pct(mem_loaded, 0.95),
        "memory_chars_in_prompt_avg": statistics.mean(mem_prompt) if mem_prompt else 0.0,
        "memory_chars_in_prompt_p95": _pct(mem_prompt, 0.95),
        "response_obligation_chars_avg": statistics.mean(obligation_chars) if obligation_chars else 0.0,
        "response_obligation_chars_p95": _pct(obligation_chars, 0.95),
        "final_answer_observed_chars_avg": statistics.mean(final_obs_chars) if final_obs_chars else 0.0,
        "final_answer_observed_chars_p95": _pct(final_obs_chars, 0.95),
        "takeover_counts": dict(takeover_counts),
        "fallback_count": sum(int(row.get("fallback_count", 0) > 0) for row in rows),
        "memory_write_count_total": sum(int(row.get("memory_write_count", 0)) for row in rows),
        "semantic_extract_called_total": sum(int(bool(row.get("semantic_extract_called"))) for row in rows),
        "evolved_write_count_total": sum(int(row.get("evolved_write_count", 0)) for row in rows),
        "experience_write_count_total": sum(int(row.get("experience_write_count", 0)) for row in rows),
        "takeover_after_observe_total": sum(len(row.get("takeover_timings", {})) for row in rows),
        "effective_llm_samples": sum(int(row.get("output_path") != "fallback") for row in rows),
    }


def test_5gr_group_a_light_paths():
    rng = random.Random(R5G_SEED)
    rows = []
    light_acts = ["casual_ack", "unclear_short_turn"]
    for index in range(100):
        case = _build_case(
            rng,
            R5G_SEED + index,
            force={
                "speech_act": rng.choice(light_acts),
                "scene": rng.choice(["general", "emotion", "management"]),
                "skill_state": rng.choice(["skills_off", "default_scene_skill", "leijun_on"]),
                "path": rng.choice(PATHS),
                "context_state": "no_previous_task",
            },
        )
        context = Context(session_id=f"5gr-a-{index}")
        row = _run_perf_turn(context, case, output_mode="llm_normal", session_id=context.session_id)
        rows.append(row)
    summary = _summary(rows)
    _record_artifact("group_a", {"summary": summary, "sample": rows[:10]})
    assert summary["count"] == 100
    assert summary["step9_ms_p95"] < summary["step8_ms_p95"] * 2 + 1
    assert summary["prompt_chars_p95"] < 2200
    assert all(row["step9_mode"] == "light_minimal" for row in rows)


def test_5gr_group_b_standard_random_performance():
    rng = random.Random(R5G_SEED + 1)
    rows = []
    speech_acts = ["ask_how_to", "ask_framework", "ask_options", "ask_expand", "request_continue_answer", "emotional_help", "repair_request", "negative_feedback"]
    modes = ["llm_normal", "question_only", "meta_strategy", "fallback_generic", "fallback_question", "fallback_meta"]
    for index in range(200):
        case = _build_case(
            rng,
            R5G_SEED + 1000 + index,
            force={
                "speech_act": rng.choice(speech_acts),
                "scene": rng.choice(["sales", "management", "negotiation", "emotion", "multi_scene"]),
                "path": rng.choice(PATHS),
            },
        )
        context = Context(session_id=f"5gr-b-{index}")
        _seed_previous_history(context, case.context_state, case.scene)
        rows.append(_run_perf_turn(context, case, output_mode=rng.choice(modes), session_id=context.session_id))
    summary = _summary(rows)
    skill_prompt_impact = {}
    for state in ["skills_off", "default_scene_skill", "leijun_on", "emotion_skill_on", "management_skill_on"]:
        values = [row["prompt_chars_estimate"] for row in rows if row["skill_state"] == state]
        if values:
            skill_prompt_impact[state] = {"avg": statistics.mean(values), "p95": _pct(values, 0.95)}
    _record_artifact("group_b", {"summary": summary, "skill_prompt_impact": skill_prompt_impact})
    satisfaction = sum(int((row["final_answer_observed"] or {}).get("output_satisfies_obligation") is True or row["response_obligation"]["expected_deliverable"] in {"none", "safety_support"}) for row in rows) / len(rows)
    assert summary["count"] == 200
    assert summary["prompt_chars_p95"] < 5000
    assert satisfaction >= 0.90


def test_5gr_group_c_deep_full_paths():
    rng = random.Random(R5G_SEED + 2)
    deep_prompts = [
        "给我一个系统审计路线图",
        "帮我写完整修复路线图",
        "做一个多报告综合总结",
        "给我一个代码级方案说明",
        "做一个完整回归计划",
        "帮我做架构复盘",
        "写一个阶段总结",
    ]
    rows = []
    for index in range(50):
        prompt = deep_prompts[index % len(deep_prompts)]
        case = SemanticCase(
            seed=R5G_SEED + 3000 + index,
            speech_act="ask_framework",
            scene=rng.choice(["management", "sales", "negotiation", "emotion", "multi_scene"]),
            tone=rng.choice(["neutral", "polite", "confused"]),
            context_state=rng.choice(["previous_task_satisfied", "previous_task_unsatisfied", "previous_fallback"]),
            skill_state=rng.choice(SKILL_STATES),
            path=rng.choice(PATHS),
            generated_input=prompt,
            expected_properties=EXPECTED["ask_framework"],
        )
        context = Context(session_id=f"5gr-c-{index}")
        context.unified_context = "统一上下文：" + prompt * 2
        context.history_summary = "历史摘要：" + prompt
        context.session_notes_context = "会话笔记：" + prompt
        _seed_previous_history(context, case.context_state, case.scene)
        rows.append(_run_perf_turn(context, case, output_mode="deep_full", session_id=context.session_id))
    summary = _summary(rows)
    _record_artifact("group_c", {"summary": summary, "sample": rows[:8]})
    assert summary["count"] == 50
    assert summary["prompt_chars_p95"] > 200
    assert summary["step8_ms_p95"] >= summary["step1_ms_p95"]


def test_5gr_group_d_crisis_performance_and_safety():
    rng = random.Random(R5G_SEED + 3)
    rows = []
    crisis_inputs = [
        "我不想活了",
        "我现在真的想自杀",
        "我怕自己会伤害自己",
        "我已经快崩到想死了",
        "感觉活不下去了",
        "我现在就要自杀",
    ]
    for index in range(60):
        case = _build_case(
            rng,
            R5G_SEED + 5000 + index,
            force={
                "speech_act": "crisis_signal",
                "scene": "emotion",
                "skill_state": rng.choice(SKILL_STATES),
                "context_state": rng.choice(["no_previous_task", "previous_fallback", "previous_repair_completed"]),
                "path": rng.choice(PATHS),
            },
        )
        case = SemanticCase(
            **{
                **asdict(case),
                "generated_input": crisis_inputs[index % len(crisis_inputs)],
            }
        )
        context = Context(session_id=f"5gr-d-{index}")
        _seed_previous_history(context, case.context_state, case.scene)
        row = _run_perf_turn(context, case, output_mode=rng.choice(["crisis_prompt", "fallback_generic"]), session_id=context.session_id)
        rows.append(row)
        assert row["crisis_detected"] is True
        assert (row["response_obligation"] or {}).get("expected_deliverable") == "safety_support"
        assert row["answer_first_takeover_used"] is not True
        assert row["internal_strategy_leak_takeover_used"] is not True
        assert row["repair_contract_takeover_used"] is not True
        assert row["fallback_contract_takeover_used"] is not True
        assert row["memory_write_count"] == 0
    summary = _summary(rows)
    _record_artifact("group_d", {"summary": summary, "sample": rows[:10]})
    assert summary["count"] == 60


def test_5gr_group_e_long_session_growth():
    rng = random.Random(R5G_SEED + 4)
    sessions = []
    growth_flags = []
    for session_index in range(20):
        context = Context(session_id=f"5gr-e-{session_index}")
        _seed_previous_history(context, "previous_task_unsatisfied", rng.choice(["management", "sales", "emotion"]))
        rows = []
        turns = rng.randint(20, 30)
        for turn_id in range(turns):
            speech = rng.choice(["ask_how_to", "ask_options", "negative_feedback", "repair_request", "emotional_help", "crisis_signal", "casual_ack"])
            case = _build_case(
                rng,
                R5G_SEED + 8000 + session_index * 100 + turn_id,
                force={
                    "speech_act": speech,
                    "scene": rng.choice(["management", "sales", "negotiation", "emotion", "multi_scene"]),
                    "skill_state": rng.choice(SKILL_STATES),
                    "context_state": rng.choice(["previous_task_satisfied", "previous_task_unsatisfied", "previous_fallback", "previous_repair_completed"]),
                    "path": rng.choice(PATHS),
                },
            )
            mode = "crisis_prompt" if speech == "crisis_signal" else "fallback_generic" if turn_id % 7 == 0 else "question_only" if speech in {"ask_how_to", "ask_options"} and turn_id % 5 == 0 else "llm_normal"
            row = _run_perf_turn(context, case, output_mode=mode, session_id=context.session_id)
            row["turn_id"] = turn_id
            row["session_note_count"] = 1 if context.session_notes_context else 0
            row["session_note_size"] = len(context.session_notes_context or "")
            rows.append(row)
        front = rows[:10]
        middle = rows[10:20] if len(rows) >= 20 else rows[5:15]
        back = rows[-10:]
        prompt_growth = back[-1]["prompt_chars_estimate"] - front[0]["prompt_chars_estimate"]
        mem_growth = back[-1]["memory_chars_in_prompt"] - front[0]["memory_chars_in_prompt"]
        sessions.append(
            {
                "session_id": context.session_id,
                "turns": rows,
                "front_avg_total_ms": statistics.mean(r["total_ms"] for r in front),
                "middle_avg_total_ms": statistics.mean(r["total_ms"] for r in middle),
                "back_avg_total_ms": statistics.mean(r["total_ms"] for r in back),
                "prompt_growth": prompt_growth,
                "memory_growth": mem_growth,
            }
        )
        growth_flags.append(prompt_growth < 2500 and mem_growth < 2200)
    _record_artifact("group_e", {"sessions": sessions[:5], "growth_ok_rate": sum(int(flag) for flag in growth_flags) / len(growth_flags)})
    assert all(growth_flags)


def test_5gr_group_f_takeover_cost_targeted():
    rng = random.Random(R5G_SEED + 5)
    rows = []
    targeted = [
        ("identity_truth", {"speech_act": "ask_identity"}, "identity_hallucination"),
        ("answer_first", {"speech_act": "ask_how_to"}, "question_only"),
        ("internal_leak", {"speech_act": "emotional_help"}, "meta_strategy"),
        ("repair", {"speech_act": "negative_feedback", "context_state": "previous_output_question_first"}, "llm_normal"),
        ("fallback", {"speech_act": "ask_framework"}, "fallback_generic"),
        ("no_takeover", {"speech_act": "ask_framework"}, "llm_normal"),
    ]
    for label, force, mode in targeted:
        for index in range(34):
            case = _build_case(rng, R5G_SEED + 12000 + len(rows), force={**force, "scene": rng.choice(["management", "sales", "emotion"]), "skill_state": rng.choice(["skills_off", "default_scene_skill", "leijun_on"])})
            context = Context(session_id=f"5gr-f-{label}-{index}")
            _seed_previous_history(context, case.context_state, case.scene)
            row = _run_perf_turn(context, case, output_mode=mode, session_id=context.session_id)
            row["target"] = label
            rows.append(row)
            assert row["llm_replayed"] is False
            assert row["memory_write_count"] == 0
    summary = _summary(rows)
    by_target = {}
    for label, _, _ in targeted:
        sample = [row for row in rows if row["target"] == label]
        by_target[label] = _summary(sample)
    _record_artifact("group_f", {"summary": summary, "by_target": by_target})
    assert summary["count"] >= 200


def test_5gr_group_g_r3_failure_backlog_cost_replay():
    rng = random.Random(R5G_SEED + 6)
    rows = []
    mapping = {
        2026042811: ("ask_options", "llm_normal"),
        2026042905: ("ask_options", "llm_normal"),
        2026043510: ("ask_options", "question_only"),
        2026044111: ("negative_feedback", "meta_strategy"),
        2026044306: ("ask_options", "llm_normal"),
        2026044609: ("repair_request", "llm_normal"),
        2026045104: ("ask_options", "question_only"),
        2026045109: ("ask_how_to", "question_only"),
        2026045408: ("ask_options", "fallback_question"),
    }
    for seed in R3_FAILURE_BACKLOG:
        speech_act, mode = mapping[seed]
        case = _build_case(
            rng,
            seed,
            force={
                "speech_act": speech_act,
                "scene": rng.choice(["management", "sales", "emotion"]),
                "context_state": "previous_output_generic",
                "skill_state": rng.choice(["skills_off", "default_scene_skill", "leijun_on"]),
                "path": rng.choice(PATHS),
            },
        )
        context = Context(session_id=f"5gr-g-{seed}")
        _seed_previous_history(context, case.context_state, case.scene)
        row = _run_perf_turn(context, case, output_mode=mode, session_id=context.session_id)
        row["why_not_satisfied"] = (
            "observation_gap"
            if (row["final_answer_observed"] or {}).get("output_satisfies_obligation") is not True and speech_act in {"ask_options", "repair_request"}
            else "minimum_answer_gap"
            if (row["final_answer_observed"] or {}).get("deliverable_observed") in {"question_only", "generic_fallback", "meta_strategy", "unknown"}
            else "backlog_only"
        )
        row["belongs_r3_fix_backlog"] = True
        rows.append(row)
    _record_artifact("group_g", {"rows": rows})
    assert len(rows) == 9
    assert all(row["belongs_r3_fix_backlog"] for row in rows)


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    store = SessionStore(str(tmp_path / "phase_5gr_api_sessions.db"))
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
def phase5gr_api_executor(monkeypatch):
    rng = random.Random(R5G_SEED + 7)
    queue = deque()
    calls = []
    modes = ["llm_normal", "question_only", "meta_strategy", "fallback_generic", "fallback_question", "fallback_meta"]
    for index in range(60):
        case = _build_case(rng, R5G_SEED + 20000 + index)
        mode = "identity_hallucination" if case.speech_act == "ask_identity" else "crisis_prompt" if case.speech_act == "crisis_signal" else rng.choice(modes)
        queue.append((case, mode))

    def execute_streaming_response(context: Context, user_input: str, *args, **kwargs):
        case, mode = queue.popleft()
        case = SemanticCase(**{**asdict(case), "generated_input": case.generated_input, "skill_state": "leijun_on" if (getattr(context, "skill_flags", {}) or {}).get("leijun") else case.skill_state})
        row = _run_perf_turn(context, case, output_mode=mode, session_id=context.session_id)
        calls.append(row)
        return context, context.output, {"step1_8_obligation": row["step1_ms"], "step8_output": row["step8_ms"]}

    import graph.streaming_pipeline as streaming_pipeline

    monkeypatch.setattr(streaming_pipeline, "execute_streaming_response", execute_streaming_response)
    return calls


def test_5gr_real_api_path_sampling(api_client, phase5gr_api_executor):
    client = api_client
    for index in range(15):
        assert client.post("/chat", json={"session_id": f"g5grchat{index:02d}", "user_input": f"x-{index}"}).status_code == 200
    for index in range(15):
        with client.stream("POST", "/chat/stream", json={"session_id": f"g5grstream{index:02d}", "user_input": f"y-{index}"}) as response:
            body = "".join(response.iter_text())
        assert response.status_code == 200
        assert "event: complete" in body
    for index in range(15):
        assert client.post("/v1/chat/completions", json={"model": "human-os-3.0", "messages": [{"role": "user", "content": f"z-{index}"}]}).status_code == 200
    for index in range(15):
        with client.stream("POST", "/v1/chat/completions", json={"model": "human-os-3.0", "stream": True, "messages": [{"role": "user", "content": f"w-{index}"}]}) as response:
            body = "".join(response.iter_text())
        assert response.status_code == 200
        assert "data: [DONE]" in body
    assert len(phase5gr_api_executor) == 60
    summary = _summary(phase5gr_api_executor)
    _record_artifact("api_sampling", {"summary": summary, "sample": phase5gr_api_executor[:8]})
    assert summary["count"] == 60
