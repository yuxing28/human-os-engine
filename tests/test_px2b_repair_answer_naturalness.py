from dataclasses import asdict

from graph.nodes.repair_contract_takeover import apply_repair_contract_takeover
from graph.nodes.response_obligation_observer import (
    observe_final_output,
    observe_skill_context,
    step1_8_response_obligation_observation,
)
from schemas.context import Context, HistoryItem
from tests.test_r2t_randomized_semantic_regression import EXPECTED, R2T_SEED, SemanticCase


PREVIOUS_DELIVERABLES = ["direct_answer", "options", "framework", "steps", "script", "emotional_support"]
BAD_OUTPUTS = ["question_only", "generic_fallback", "meta_strategy", "unknown", "too_short"]
REPAIR_SIGNALS = {
    "confusion": "没懂，你重新说",
    "dissatisfaction": "你这回答没用",
    "correction": "不是这个意思",
    "impatience": "别绕，直接补",
    "negative_feedback": "这也太离谱了",
    "mild_insult": "说人话，别糊弄",
}
SCENES = ["general", "management", "sales", "negotiation", "emotion"]
TONES = ["polite", "casual", "impatient", "annoyed", "aggressive", "confused"]
SKILLS = ["skills_off", "default_scene_skill", "leijun_on"]
PATHS = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]

BAD_OBS = {
    "question_only": {"output_satisfies_obligation": False, "deliverable_observed": "question_only"},
    "generic_fallback": {"output_satisfies_obligation": False, "deliverable_observed": "generic_fallback"},
    "meta_strategy": {"output_satisfies_obligation": False, "deliverable_observed": "meta_strategy"},
    "unknown": {"output_satisfies_obligation": "Unknown", "deliverable_observed": "unknown"},
    "too_short": {"output_satisfies_obligation": False, "deliverable_observed": "direct_answer"},
}


def _case(index: int) -> tuple[SemanticCase, str, str, str]:
    previous_expected = PREVIOUS_DELIVERABLES[index % len(PREVIOUS_DELIVERABLES)]
    bad_output = BAD_OUTPUTS[(index // len(PREVIOUS_DELIVERABLES)) % len(BAD_OUTPUTS)]
    signal_key = list(REPAIR_SIGNALS)[index % len(REPAIR_SIGNALS)]
    scene = SCENES[(index // 4) % len(SCENES)]
    tone = TONES[(index // 5) % len(TONES)]
    skill = SKILLS[(index // 7) % len(SKILLS)]
    path = PATHS[(index // 9) % len(PATHS)]
    speech_act = "negative_feedback" if signal_key in {"negative_feedback", "mild_insult", "dissatisfaction"} else "repair_request"
    case = SemanticCase(
        seed=R2T_SEED + 830000 + index,
        speech_act=speech_act,
        scene=scene,
        tone=tone,
        context_state="previous_output_generic",
        skill_state=skill,
        path=path,
        generated_input=REPAIR_SIGNALS[signal_key],
        expected_properties=EXPECTED[speech_act],
    )
    return case, previous_expected, bad_output, signal_key


def _context_for(case: SemanticCase, previous_expected: str, bad_output: str) -> Context:
    context = Context(session_id=f"px2b-{case.seed}")
    context.primary_scene = case.scene
    context.skill_flags = {"leijun": {"enabled": True}} if case.skill_state == "leijun_on" else {}
    if case.skill_state == "default_scene_skill":
        context.skill_prompt = "默认场景原则：按当前场景给清晰答复。"
    elif case.skill_state == "leijun_on":
        context.skill_prompt = "【可选人格扩展包】最终回复体现差异。可以先问一个问题。"
    previous_obligation = {
        "user_goal": f"上一轮要的是{previous_expected}类型的可用答案",
        "expected_deliverable": previous_expected,
        "answer_first_required": True,
        "clarification_allowed": "after_answer",
        "repair_required": False,
        "identity_answer_required": False,
        "final_response_boundary_required": True,
        "observation_basis": {"route_scene": case.scene},
    }
    context.history.append(
        HistoryItem(
            role="system",
            content="上一轮回答",
            metadata={
                "response_obligation": previous_obligation,
                "final_answer_observed": dict(BAD_OBS[bad_output]),
            },
        )
    )
    return context


def _run(case: SemanticCase, previous_expected: str, bad_output: str) -> tuple[dict, str]:
    context = _context_for(case, previous_expected, bad_output)
    state = {"context": context, "user_input": case.generated_input, "runtime_trace": {}}
    step1_8_response_obligation_observation(state)
    observe_skill_context(state, context)
    output = "我可能没表达清楚，你再说说。"
    observe_final_output(state, context, output)
    output = apply_repair_contract_takeover(state, context, output)
    observe_final_output(state, context, output)
    return state["runtime_trace"], output


def _has_ack(output: str) -> bool:
    markers = (
        "刚才我绕了一下",
        "你说得对",
        "前面那句太空了",
        "刚才没把",
        "刚才没有给到",
        "刚才没有真正接住",
        "没有答到点上",
        "直接补",
        "重新接一下",
    )
    return any(marker in output for marker in markers)


def _template_score(output: str) -> int:
    repeated = (
        "刚才那版没有接住重点",
        "我直接补上",
        "我直接补到这个问题上",
    )
    return sum(output.count(marker) for marker in repeated)


def test_px2b_repair_answer_random_naturalness_contract():
    total = 132
    takeover = 0
    ack = 0
    completed = 0
    no_attack = 0
    not_apology_only = 0
    template_score = 0

    forbidden = ("跟你耗", "爱听不听", "不想听算了", "你也没说清楚", "你自己")

    for index in range(total):
        case, previous_expected, bad_output, _ = _case(index)
        trace, output = _run(case, previous_expected, bad_output)
        obs = trace["final_answer_observed"]

        assert trace["repair_contract_required"] is True
        takeover += int(trace["repair_contract_takeover_used"] is True)
        ack += int(_has_ack(output))
        completed += int(obs["repair_completed_observed"] is True or obs["output_satisfies_obligation"] is True)
        no_attack += int(not any(item in output for item in forbidden))
        not_apology_only += int(len(output) >= 45 and obs["deliverable_observed"] not in {"generic_fallback", "question_only", "meta_strategy", "unknown"})
        template_score += _template_score(output)

    assert takeover == total
    assert ack == total
    assert completed / total >= 0.95
    assert no_attack == total
    assert not_apology_only == total
    assert template_score == 0


def test_px2b_skill_does_not_change_repair_result():
    base, previous_expected, bad_output, _ = _case(3)
    results = []
    for skill in SKILLS:
        case = SemanticCase(**{**asdict(base), "skill_state": skill})
        trace, output = _run(case, previous_expected, bad_output)
        results.append((trace, output))

    assert all(trace["repair_contract_takeover_used"] is True for trace, _ in results)
    assert all(trace["repair_contract_target_obligation"]["expected_deliverable"] == previous_expected for trace, _ in results)
    assert all(_has_ack(output) for _, output in results)
