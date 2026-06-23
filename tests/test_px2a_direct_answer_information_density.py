from dataclasses import asdict

from graph.nodes.answer_first_takeover import apply_answer_first_takeover
from graph.nodes.fallback_contract_takeover import apply_fallback_contract_takeover
from graph.nodes.identity_truth import apply_identity_truth_takeover
from graph.nodes.internal_strategy_leak_takeover import apply_internal_strategy_leak_takeover
from graph.nodes.response_obligation_observer import (
    observe_final_output,
    observe_skill_context,
    step1_8_response_obligation_observation,
)
from schemas.context import Context
from tests.test_r2t_randomized_semantic_regression import EXPECTED, R2T_SEED, SemanticCase


SCENES = ["general", "management", "sales", "negotiation", "emotion"]
TONES = ["polite", "casual", "impatient", "vague"]
PATHS = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]
SKILL_STATES = ["skills_off", "default_scene_skill", "leijun_on"]
TAKEOVER_PATHS = ["answer_first", "internal_leak", "fallback"]


def _case(index: int, *, scene: str, tone: str, path: str, skill_state: str) -> SemanticCase:
    text_by_scene = {
        "general": "这个到底是什么意思，直接说就行",
        "management": "团队这个问题你直接给个判断",
        "sales": "客户这个反应到底该怎么看",
        "negotiation": "这个谈判局面你直接判断一下",
        "emotion": "她这样说到底意味着什么",
    }
    return SemanticCase(
        seed=R2T_SEED + 820000 + index,
        speech_act="ask_expand",
        scene=scene,
        tone=tone,
        context_state="no_previous_task",
        skill_state=skill_state,
        path=path,
        generated_input=text_by_scene[scene],
        expected_properties=EXPECTED["ask_expand"],
    )


def _context_for(case: SemanticCase) -> Context:
    context = Context(session_id=f"px2a-{case.seed}")
    context.primary_scene = case.scene
    context.skill_flags = {"leijun": {"enabled": True}} if case.skill_state == "leijun_on" else {}
    if case.skill_state == "default_scene_skill":
        context.skill_prompt = "默认场景原则：按当前场景给清晰答复。"
    elif case.skill_state == "leijun_on":
        context.skill_prompt = "【可选人格扩展包】最终回复体现差异。可以先问一个问题。"
    return context


def _force_direct_answer(trace: dict) -> None:
    obligation = trace["response_obligation"]
    obligation["expected_deliverable"] = "direct_answer"
    obligation["answer_first_required"] = True
    obligation["clarification_allowed"] = "after_answer"
    trace["response_obligation"] = obligation
    trace["expected_deliverable"] = "direct_answer"
    trace["answer_first_required_observed"] = True
    trace["clarification_allowed_observed"] = "after_answer"


def _run_direct_answer_case(case: SemanticCase, takeover_path: str) -> tuple[dict, str]:
    context = _context_for(case)
    state = {"context": context, "user_input": case.generated_input, "runtime_trace": {}}
    if takeover_path == "fallback":
        state["runtime_trace"]["output_path"] = "fallback"

    step1_8_response_obligation_observation(state)
    trace = state["runtime_trace"]
    _force_direct_answer(trace)
    observe_skill_context(state, context)

    if takeover_path == "answer_first":
        output = "你能再多说一点具体背景吗？"
        output = apply_identity_truth_takeover(state, context, output)
        observe_final_output(state, context, output)
        output = apply_answer_first_takeover(state, context, output)
    elif takeover_path == "internal_leak":
        output = "本轮建议先承认感受，再留一句空间。"
        output = apply_identity_truth_takeover(state, context, output)
        observe_final_output(state, context, output)
        output = apply_answer_first_takeover(state, context, output)
        observe_final_output(state, context, output)
        output = apply_internal_strategy_leak_takeover(state, context, output)
    else:
        output = "我在，你可以再多说一点。"
        output = apply_identity_truth_takeover(state, context, output)
        observe_final_output(state, context, output, fallback_used=True)
        output = apply_fallback_contract_takeover(state, context, output)

    observe_final_output(state, context, output, fallback_used=takeover_path == "fallback")
    return state["runtime_trace"], output


def _has_direct_density(output: str) -> bool:
    text = str(output or "").strip()
    sentence_count = sum(text.count(mark) for mark in ("。", "！", "？", ".", "!", "?"))
    action_markers = ("你可以", "先", "今天", "下一步", "写清", "定一个", "补一句", "停下")
    reason_markers = ("原因", "因为", "通常", "不是")
    return (
        48 <= len(text) <= 180
        and sentence_count >= 3
        and any(marker in text for marker in reason_markers)
        and any(marker in text for marker in action_markers)
    )


def test_px2a_direct_answer_random_information_density():
    cases = []
    for index in range(105):
        scene = SCENES[index % len(SCENES)]
        tone = TONES[(index // len(SCENES)) % len(TONES)]
        path = PATHS[(index // 7) % len(PATHS)]
        skill_state = SKILL_STATES[(index // 11) % len(SKILL_STATES)]
        cases.append(_case(index, scene=scene, tone=tone, path=path, skill_state=skill_state))

    short_or_thin = 0
    too_long = 0
    goal_hit = 0
    template_risk = 0

    for index, case in enumerate(cases):
        takeover_path = TAKEOVER_PATHS[index % len(TAKEOVER_PATHS)]
        trace, output = _run_direct_answer_case(case, takeover_path)
        final_obs = trace["final_answer_observed"]

        assert trace["response_obligation"]["expected_deliverable"] == "direct_answer"
        assert final_obs["answer_first_satisfied"] is True
        assert final_obs["output_satisfies_obligation"] is not False
        assert final_obs["deliverable_observed"] not in {"question_only", "generic_fallback", "meta_strategy", "unknown"}

        short_or_thin += int(not _has_direct_density(output))
        too_long += int(len(output) > 180)
        goal_hit += int(final_obs["output_satisfies_obligation"] is True)
        template_risk += int(output.startswith("直接结论：") and output.count("原因") == 1 and output.count("你可以") == 1)

    assert len(cases) >= 100
    assert short_or_thin / len(cases) <= 0.05
    assert too_long == 0
    assert goal_hit / len(cases) >= 0.95
    assert template_risk / len(cases) <= 1.0


def test_px2a_light_input_is_not_pulled_into_direct_answer_takeover():
    case = _case(999, scene="general", tone="casual", path="/chat", skill_state="skills_off")
    light_case = SemanticCase(**{**asdict(case), "speech_act": "casual_ack", "generated_input": "嗯", "expected_properties": EXPECTED["casual_ack"]})
    context = _context_for(light_case)
    state = {"context": context, "user_input": light_case.generated_input, "runtime_trace": {}}

    step1_8_response_obligation_observation(state)
    observe_skill_context(state, context)
    output = "你想继续哪个部分？"
    observe_final_output(state, context, output)
    output = apply_answer_first_takeover(state, context, output)
    observe_final_output(state, context, output)

    trace = state["runtime_trace"]
    assert trace["response_obligation"]["clarification_allowed"] == "before_answer"
    assert trace["answer_first_takeover_used"] is not True
    assert output == "你想继续哪个部分？"
