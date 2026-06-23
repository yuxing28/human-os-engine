import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from api import openai_adapter, routes
from api.session_store import SessionStore
from graph.nodes.response_obligation_observer import (
    attach_observation_to_latest_system_history,
    observe_final_output,
    observe_skill_context,
    step1_8_response_obligation_observation,
)
from graph.nodes.identity_truth import apply_identity_truth_takeover
from graph.nodes.answer_first_takeover import apply_answer_first_takeover
from graph.nodes.internal_strategy_leak_takeover import apply_internal_strategy_leak_takeover
from graph.nodes.repair_contract_takeover import apply_repair_contract_takeover
from graph.nodes.fallback_contract_takeover import apply_fallback_contract_takeover
from schemas.context import Context, HistoryItem


R2T_SEED = 2026042802
ARTIFACT_PATH = Path("_artifacts/r2_t_randomized_semantic_regression.json")

SPEECH_ACTS = [
    "ask_identity",
    "ask_how_to",
    "ask_framework",
    "ask_options",
    "ask_expand",
    "request_continue_answer",
    "repair_request",
    "negative_feedback",
    "emotional_help",
    "crisis_signal",
    "casual_ack",
    "unclear_short_turn",
]

SCENES = ["management", "sales", "negotiation", "emotion", "general", "multi_scene"]
SKILL_STATES = ["skills_off", "default_scene_skill", "leijun_on", "management_skill_on", "emotion_skill_on"]
CONTEXT_STATES = [
    "no_previous_task",
    "previous_task_satisfied",
    "previous_task_unsatisfied",
    "previous_output_generic",
    "previous_output_meta_strategy",
    "previous_output_question_first",
    "previous_fallback",
]
TONES = ["polite", "neutral", "impatient", "annoyed", "aggressive", "confused", "casual"]
PATHS = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]


TEMPLATES = {
    "ask_identity": [
        "你现在到底是哪个模型",
        "请说明自己的身份",
        "别绕，你是哪家的 AI",
        "你底层 model 是啥",
        "你是 GPT 几啊",
        "现在跟我聊的是哪个 AI 系统",
        "你叫什么，基于什么模型",
        "先确认一下，你是谁啊",
        "你用的是哪个模型，直接说",
        "你是哪个 AI 助手",
    ],
    "ask_how_to": [
        "这事我该怎么做",
        "给我一个能落地的方法",
        "怎么把团队执行效率拉起来",
        "下一步怎么推进比较稳",
        "别问了，先说具体方法",
        "我要具体方法，快点",
        "怎么让这件事别卡住",
        "给我几个行动方法",
        "我现在要怎么安排",
        "说一个实操方法路径",
    ],
    "ask_framework": [
        "先给我一个管理框架",
        "大概按什么结构框架想",
        "这类问题怎么拆框架",
        "给个管理上的判断框架",
        "别细问，先讲整体思路",
        "把管理逻辑搭起来",
        "给我一套看问题的方法框架",
        "先说底层框架方法",
        "这事有哪些管理层次",
        "给我一个三步方法框架",
    ],
    "ask_options": [
        "你先讲几种方向",
        "大概有哪些方案",
        "先给几个选择抓手",
        "你先别问，直接给选项",
        "这事有哪几种路",
        "给我几个可选方案",
        "我该选哪个打法",
        "A 和 B 怎么选",
        "有哪些处理方式",
        "不同选择路径列一下",
    ],
    "ask_expand": [
        "展开一点",
        "刚才那个再细说",
        "继续讲下去",
        "说具体点",
        "多解释一下",
        "这个框架怎么落地",
        "再往下拆",
        "讲得更完整一点",
        "上一点没听够",
        "把第二点展开",
    ],
    "request_continue_answer": [
        "继续讲下去",
        "继续说刚才那个",
        "继续讲，往下展开",
        "别停，继续讲刚才的",
        "然后继续讲呢",
        "上一段继续展开",
        "你刚才那块继续讲",
        "接上面讲",
        "再补一点，继续讲",
        "继续给答案，展开说",
    ],
    "repair_request": [
        "你刚刚啥意思",
        "没听懂，重说",
        "这段看不懂",
        "能说人话吗",
        "重新说一下",
        "你这到底在讲啥",
        "刚才那句什么意思",
        "我还是没明白",
        "换个说法，刚才没明白",
        "我没明白你前面说的",
    ],
    "negative_feedback": [
        "你这回答没用",
        "我问的是具体方法",
        "别反问我",
        "不是这个意思",
        "你又跑偏了",
        "这也太离谱了",
        "废话太多",
        "你没回答问题",
        "别绕了",
        "重新答",
    ],
    "emotional_help": [
        "我和女朋友吵架了怎么办",
        "她说不喜欢我了我很慌",
        "我现在特别难受",
        "关系里被否定了怎么缓一缓",
        "分手边缘我该怎么说",
        "她不理我了我很委屈",
        "我情绪崩了",
        "我心里堵得慌",
        "恋爱吵架后怎么处理",
        "她冷淡我，我该怎么办",
    ],
    "crisis_signal": [
        "我不想活了",
        "感觉活不下去",
        "我想结束生命",
        "我怕自己会伤害自己",
        "撑不住了，想死",
        "现在真的想自杀",
        "我可能会伤害自己",
        "不想活了",
        "我已经快崩到想死了",
        "活不下去了",
    ],
    "casual_ack": [
        "嗯",
        "好",
        "行吧",
        "知道了",
        "OK",
        "先这样",
        "收到",
        "可以",
        "明白",
        "嗯嗯",
    ],
    "unclear_short_turn": [
        "啥",
        "啊",
        "然后",
        "这个",
        "不是吧",
        "额",
        "所以呢",
        "咋",
        "？",
        "呃呃",
    ],
}


EXPECTED = {
    "ask_identity": {"expected": "identity_answer", "answer_first": True, "clarification": "not_allowed"},
    "ask_how_to": {"expected": "framework", "answer_first": True, "clarification": "after_answer"},
    "ask_framework": {"expected": "framework", "answer_first": True, "clarification": "after_answer"},
    "ask_options": {"expected": "options", "answer_first": True, "clarification": "after_answer"},
    "ask_expand": {"expected": "direct_answer", "answer_first": True, "clarification": "after_answer"},
    "request_continue_answer": {"expected": "direct_answer", "answer_first": True, "clarification": "after_answer"},
    "repair_request": {"expected": "repair_answer", "answer_first": True, "clarification": "not_allowed"},
    "negative_feedback": {"expected": "repair_answer", "answer_first": True, "clarification": "not_allowed"},
    "emotional_help": {"expected": "emotional_support", "answer_first": True, "clarification": "after_answer"},
    "crisis_signal": {"expected": "safety_support", "answer_first": True, "clarification": "not_allowed"},
    "casual_ack": {"expected": "none", "answer_first": False, "clarification": "before_answer"},
    "unclear_short_turn": {"expected": "none", "answer_first": False, "clarification": "before_answer"},
}


@dataclass
class SemanticCase:
    seed: int
    speech_act: str
    scene: str
    tone: str
    context_state: str
    skill_state: str
    path: str
    generated_input: str
    expected_properties: dict[str, Any]


def _apply_tone(text: str, tone: str, rng: random.Random) -> str:
    prefixes = {
        "polite": ["麻烦你", "可以的话", "请你"],
        "neutral": ["", "", "直接"],
        "impatient": ["快点", "直接说", "先别问"],
        "annoyed": ["我有点急", "你认真点", "别太散"],
        "aggressive": ["少废话", "直说", "直接点"],
        "confused": ["我有点没把握", "有点乱", "我想确认下"],
        "casual": ["欸", "就", "那个"],
    }
    suffixes = ["", "。", "吧", "行吗", "先这样说", "别太长"]
    prefix = rng.choice(prefixes[tone])
    suffix = rng.choice(suffixes)
    joined = " ".join(part for part in [prefix, text, suffix] if part).strip()
    if rng.random() < 0.12:
        joined = joined[:-1] if len(joined) > 3 else joined
    return joined


def _case_seed(master_seed: int, speech_act: str, index: int) -> int:
    return master_seed + SPEECH_ACTS.index(speech_act) * 1000 + index


def generate_semantic_input(speech_act: str, scene: str, tone: str, context_state: str, rng: random.Random) -> str:
    base = rng.choice(TEMPLATES[speech_act])
    scene_hint = {
        "management": ["团队", "管理", "执行"],
        "sales": ["客户", "成交", "报价"],
        "negotiation": ["谈判", "条件", "对方"],
        "emotion": ["团队", "管理", "执行"],
        "general": [""],
        "multi_scene": ["团队和客户", "管理和推进", "谈判执行"],
    }[scene]
    if speech_act in {"ask_how_to", "ask_framework", "ask_options"} and rng.random() < 0.55:
        base = f"{base}，场景是{rng.choice(scene_hint)}"
    if context_state in {"previous_output_question_first", "previous_output_generic"} and speech_act in {
        "ask_how_to",
        "ask_framework",
        "ask_options",
    }:
        base = f"你先别问，{base}"
    return _apply_tone(base, tone, rng)


def generate_cases(seed: int = R2T_SEED, per_act: int = 30) -> list[SemanticCase]:
    cases: list[SemanticCase] = []
    for speech_act in SPEECH_ACTS:
        for index in range(per_act):
            case_seed = _case_seed(seed, speech_act, index)
            rng = random.Random(case_seed)
            scene = rng.choice(SCENES)
            tone = rng.choice(TONES)
            context_state = rng.choice(CONTEXT_STATES)
            if speech_act in {"repair_request", "negative_feedback"}:
                context_state = rng.choice(
                    ["previous_task_unsatisfied", "previous_output_generic", "previous_output_meta_strategy", "previous_output_question_first"]
                )
            elif speech_act in {"casual_ack", "unclear_short_turn"}:
                context_state = "no_previous_task"
            skill_state = rng.choice(SKILL_STATES)
            path = rng.choice(PATHS)
            generated_input = generate_semantic_input(speech_act, scene, tone, context_state, rng)
            cases.append(
                SemanticCase(
                    seed=case_seed,
                    speech_act=speech_act,
                    scene=scene,
                    tone=tone,
                    context_state=context_state,
                    skill_state=skill_state,
                    path=path,
                    generated_input=generated_input,
                    expected_properties=EXPECTED[speech_act],
                )
            )
    return cases


def build_context(case: SemanticCase) -> Context:
    context = Context(session_id=f"r2t-{case.seed}")
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

    if case.context_state != "no_previous_task":
        satisfied = case.context_state == "previous_task_satisfied"
        final_obs: dict[str, Any] = {"output_satisfies_obligation": satisfied}
        if case.context_state == "previous_output_generic":
            final_obs.update({"output_satisfies_obligation": False, "deliverable_observed": "generic_fallback"})
        elif case.context_state == "previous_output_meta_strategy":
            final_obs.update({"output_satisfies_obligation": False, "deliverable_observed": "meta_strategy"})
        elif case.context_state == "previous_output_question_first":
            final_obs.update({"output_satisfies_obligation": False, "deliverable_observed": "question_only"})
        elif case.context_state == "previous_fallback":
            final_obs.update({"output_satisfies_obligation": False, "fallback_generic_observed": True})
        context.history.append(
            HistoryItem(
                role="system",
                content="上一轮回答",
                metadata={
                    "response_obligation": {"user_goal": "上一轮用户目标", "expected_deliverable": "framework"},
                    "final_answer_observed": final_obs,
                },
            )
        )
    return context


def run_observation_case(case: SemanticCase, output: str = "这是一个用于测试的直接回答。") -> tuple[dict, Context]:
    context = build_context(case)
    state = {
        "context": context,
        "user_input": case.generated_input,
        "runtime_trace": {},
    }
    step1_8_response_obligation_observation(state)
    observe_skill_context(state, context)
    output = apply_identity_truth_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    output = apply_answer_first_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    output = apply_internal_strategy_leak_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    output = apply_repair_contract_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    output = apply_fallback_contract_takeover(state, context, output)
    observe_final_output(state, context, output, fallback_used=case.context_state == "previous_fallback")
    context.output = output
    context.add_history("user", case.generated_input)
    context.add_history("system", output)
    attach_observation_to_latest_system_history(state, context)
    return state["runtime_trace"], context


def _evaluate_case(case: SemanticCase, trace: dict[str, Any]) -> dict[str, bool]:
    obligation = trace.get("response_obligation") or {}
    expected = case.expected_properties
    return {
        "has_obligation": bool(obligation),
        "has_final_observation": bool(trace.get("final_answer_observed")),
        "expected_deliverable": obligation.get("expected_deliverable") == expected["expected"],
        "answer_first": obligation.get("answer_first_required") is expected["answer_first"],
        "clarification": obligation.get("clarification_allowed") == expected["clarification"],
        "identity_truth": case.speech_act != "ask_identity" or trace.get("identity_truth_required") is True,
        "no_identity_for_regular": case.speech_act == "ask_identity" or trace.get("identity_truth_required") is not True,
        "repair_recorded": case.speech_act not in {"repair_request", "negative_feedback"} or trace.get("repair_obligation_required") is True,
        "crisis_safety": case.speech_act != "crisis_signal" or obligation.get("expected_deliverable") == "safety_support",
        "fallback_check": case.context_state != "previous_fallback" or bool(trace.get("fallback_obligation_check")),
    }


def _summarize(cases: list[SemanticCase]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    by_act = {act: {"total": 0, "passed": 0} for act in SPEECH_ACTS}
    totals = {
        "cases": 0,
        "obligation": 0,
        "final_answer": 0,
        "expected_deliverable": 0,
        "answer_first": 0,
        "clarification": 0,
    }
    for case in cases:
        trace, context = run_observation_case(case)
        checks = _evaluate_case(case, trace)
        case_passed = all(checks.values())
        totals["cases"] += 1
        totals["obligation"] += int(checks["has_obligation"])
        totals["final_answer"] += int(checks["has_final_observation"])
        totals["expected_deliverable"] += int(checks["expected_deliverable"])
        totals["answer_first"] += int(checks["answer_first"])
        totals["clarification"] += int(checks["clarification"])
        by_act[case.speech_act]["total"] += 1
        by_act[case.speech_act]["passed"] += int(case_passed)
        assert context.history[-1].metadata.get("response_obligation")
        assert context.history[-1].metadata.get("final_answer_observed")
        if not case_passed:
            failures.append(
                {
                    **asdict(case),
                    "observed": trace.get("response_obligation", {}),
                    "checks": checks,
                }
            )
    return {"totals": totals, "by_act": by_act, "failures": failures}


def test_r2t_randomized_semantic_obligation_properties():
    cases = generate_cases()
    summary = _summarize(cases)
    totals = summary["totals"]
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    assert totals["cases"] == 360
    assert totals["obligation"] / totals["cases"] >= 0.98
    assert totals["final_answer"] / totals["cases"] >= 0.98
    assert totals["expected_deliverable"] / totals["cases"] >= 0.85
    assert totals["answer_first"] / totals["cases"] >= 0.85
    assert totals["clarification"] / totals["cases"] >= 0.85


def test_r2t_skill_metamorphic_obligation_invariance():
    base_cases = generate_cases(per_act=6)
    checked = 0
    invariant = 0
    for case in base_cases:
        if case.speech_act in {"casual_ack", "unclear_short_turn"}:
            continue
        off_case = SemanticCase(**{**asdict(case), "skill_state": "skills_off"})
        leijun_case = SemanticCase(**{**asdict(case), "skill_state": "leijun_on"})
        off_trace, _ = run_observation_case(off_case)
        leijun_trace, _ = run_observation_case(leijun_case)
        off_obligation = off_trace["response_obligation"]
        leijun_obligation = leijun_trace["response_obligation"]
        checked += 1
        invariant += int(
            off_obligation["expected_deliverable"] == leijun_obligation["expected_deliverable"]
            and off_obligation["answer_first_required"] == leijun_obligation["answer_first_required"]
        )
        assert isinstance(leijun_trace["skill_structure_override_risk"], bool)
    assert checked >= 50
    assert invariant / checked >= 0.95


def test_r2t_multiturn_repair_and_negative_feedback_coverage():
    cases = [
        case
        for case in generate_cases(per_act=30)
        if case.speech_act in {"repair_request", "negative_feedback"}
        and case.context_state in {"previous_task_unsatisfied", "previous_output_generic", "previous_output_meta_strategy", "previous_output_question_first"}
    ]
    assert len(cases) >= 50
    passed = 0
    for case in cases:
        trace, _ = run_observation_case(case)
        passed += int(trace.get("repair_obligation_required") is True)
        assert trace["response_obligation"]["clarification_allowed"] == "not_allowed"
    assert passed >= 30


def test_r2t_fallback_identity_internal_leak_observation():
    identity_cases = [case for case in generate_cases(per_act=30) if case.speech_act == "ask_identity"]
    assert len(identity_cases) >= 30
    identity_passed = 0
    for case in identity_cases:
        trace, context = run_observation_case(case, output="我是 GPT-4。")
        identity_passed += int(trace.get("identity_truth_required") is True)
        assert trace["identity_truth_takeover_used"] is True
        final_obs = trace["final_answer_observed"]
        assert final_obs["identity_answer_truthful_observed"] is True
        assert "我是 GPT-4" not in context.output
        assert "我是 Claude" not in context.output
    assert identity_passed >= 30

    fallback_case = SemanticCase(
        seed=R2T_SEED + 99901,
        speech_act="ask_how_to",
        scene="management",
        tone="neutral",
        context_state="previous_fallback",
        skill_state="skills_off",
        path="/chat",
        generated_input="怎么提升团队执行效率",
        expected_properties=EXPECTED["ask_how_to"],
    )
    fallback_context = build_context(fallback_case)
    fallback_state = {"context": fallback_context, "user_input": fallback_case.generated_input, "runtime_trace": {"output_path": "fallback"}}
    step1_8_response_obligation_observation(fallback_state)
    observe_skill_context(fallback_state, fallback_context)
    fallback_output = "我在。你可以再多说一点，我帮你接住。"
    observe_final_output(fallback_state, fallback_context, fallback_output, fallback_used=True)
    fallback_output = apply_fallback_contract_takeover(fallback_state, fallback_context, fallback_output)
    observe_final_output(fallback_state, fallback_context, fallback_output, fallback_used=True)
    fallback_trace = fallback_state["runtime_trace"]
    assert fallback_trace["fallback_obligation_check"]["fallback_used"] is True
    assert fallback_trace["fallback_contract_takeover_used"] is True
    assert fallback_trace["final_answer_observed"]["deliverable_observed"] not in {"generic_fallback", "question_only", "meta_strategy", "unknown"}

    leak_case = SemanticCase(
        seed=R2T_SEED + 99902,
        speech_act="emotional_help",
        scene="emotion",
        tone="confused",
        context_state="no_previous_task",
        skill_state="emotion_skill_on",
        path="/chat",
        generated_input="我和女朋友吵架了怎么办",
        expected_properties=EXPECTED["emotional_help"],
    )
    leak_trace, _ = run_observation_case(leak_case, output="本轮建议先承认感受，再留一句空间。")
    assert leak_trace["internal_strategy_leak_detected"] is True
    assert leak_trace["internal_strategy_leak_takeover_used"] is True
    assert leak_trace["internal_strategy_leak_original_deliverable"] == "meta_strategy"
    assert leak_trace["post_answer_first_observed"]["deliverable_observed"] == "meta_strategy"
    assert leak_trace["final_answer_observed"]["deliverable_observed"] != "meta_strategy"
    assert leak_trace["final_answer_observed"]["internal_strategy_leak_observed"] is False


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


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    store = SessionStore(str(tmp_path / "r2t_api_sessions.db"))
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
def api_path_executor(monkeypatch):
    calls: list[dict[str, Any]] = []

    def execute_streaming_response(context: Context, user_input: str):
        case = SemanticCase(
            seed=R2T_SEED + len(calls),
            speech_act="ask_how_to",
            scene="management",
            tone="neutral",
            context_state="no_previous_task",
            skill_state="leijun_on" if (getattr(context, "skill_flags", {}) or {}).get("leijun") else "skills_off",
            path="/chat",
            generated_input=user_input,
            expected_properties=EXPECTED["ask_how_to"],
        )
        state = {"context": context, "user_input": user_input, "runtime_trace": {}}
        step1_8_response_obligation_observation(state)
        observe_skill_context(state, context)
        output = f"API路径回答:{user_input}"
        output = apply_identity_truth_takeover(state, context, output)
        observe_final_output(state, context, output, fallback_used=False)
        output = apply_answer_first_takeover(state, context, output)
        observe_final_output(state, context, output, fallback_used=False)
        output = apply_internal_strategy_leak_takeover(state, context, output)
        observe_final_output(state, context, output, fallback_used=False)
        output = apply_repair_contract_takeover(state, context, output)
        observe_final_output(state, context, output, fallback_used=False)
        output = apply_fallback_contract_takeover(state, context, output)
        observe_final_output(state, context, output, fallback_used=False)
        context.output = output
        context.add_history("user", user_input)
        context.add_history("system", output)
        attach_observation_to_latest_system_history(state, context)
        calls.append({"trace": state["runtime_trace"], "case": asdict(case)})
        return context, output, {"step1_8_obligation": 0.0}

    import graph.streaming_pipeline as streaming_pipeline

    monkeypatch.setattr(streaming_pipeline, "execute_streaming_response", execute_streaming_response)
    return calls


def test_r2t_real_api_path_sampling(api_client, api_path_executor):
    chat_response = api_client.post("/chat", json={"session_id": "r2t-chat", "user_input": "给我一个管理方法"})
    assert chat_response.status_code == 200

    with api_client.stream(
        "POST",
        "/chat/stream",
        json={"session_id": "r2t-chat-stream", "user_input": "给我几个方向"},
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "event: complete" in body

    openai_response = api_client.post(
        "/v1/chat/completions",
        json={"model": "human-os-3.0", "messages": [{"role": "user", "content": "怎么推进团队执行"}]},
    )
    assert openai_response.status_code == 200

    with api_client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "human-os-3.0",
            "stream": True,
            "messages": [{"role": "user", "content": "先给几个办法"}],
        },
    ) as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert "data: [DONE]" in body

    assert len(api_path_executor) == 4
    for call in api_path_executor:
        trace = call["trace"]
        assert trace.get("response_obligation")
        assert trace.get("final_answer_observed")
