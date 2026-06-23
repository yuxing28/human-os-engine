from __future__ import annotations

import random
from types import SimpleNamespace

from graph.nodes.step8_execution import _warm_emotional_support_first_sentence, step8_execution
from schemas.context import Context


RAW_EMOTIONAL_SUPPORT_OUTPUTS = [
    "我理解你的感受。你可以先停一下争辩，晚点再确认真实想法。",
    "这确实让人难受。先让情绪降一点，再做一个小动作。",
    "你可以先冷静一下，再想下一步怎么沟通。",
    "建议先暂停争辩，等双方冷静后再沟通。",
    "直接结论：先降温，再确认对方真实想法。",
]


def _emotion_context(seed: int, scene: str, skill_state: str, *, expected: str = "emotional_support") -> Context:
    ctx = Context(session_id=f"px2e-emotion-{seed}")
    ctx.primary_scene = scene
    object.__setattr__(ctx, "turn_load_level", "standard")
    trace = {
        "response_obligation": {
            "expected_deliverable": expected,
            "answer_first_required": True,
            "identity_answer_required": False,
            "repair_required": False,
        },
        "route_state": {
            "conversation_phase": "current_turn",
            "risk_level": "normal",
        },
        "skill_context_used": skill_state != "skills_off",
        "skill_extension_used": [skill_state] if skill_state not in {"skills_off", "default_scene_skill"} else [],
    }
    object.__setattr__(ctx, "runtime_trace", trace)
    object.__setattr__(ctx, "route_state", trace["route_state"])
    return ctx


def _first_sentence(text: str) -> str:
    for mark in "。！？!?":
        if mark in text:
            return text.split(mark, 1)[0] + mark
    return text


def test_px2e_random_emotional_support_first_sentence_is_warm_non_crisis():
    rng = random.Random(20260501)
    speech_acts = [
        "emotional_help",
        "relationship_distress",
        "pressure_expression",
        "mild_sadness",
        "anger_without_crisis",
        "anxiety_without_crisis",
        "conflict_after_argument",
        "low_mood_non_crisis",
    ]
    scenes = ["emotion", "management", "sales", "negotiation", "general"]
    tones = ["sad", "confused", "impatient", "annoyed", "vulnerable", "casual"]
    skills = ["skills_off", "default_scene_skill", "emotion_skill_on", "leijun_on"]
    paths = ["/chat", "/chat/stream", "/v1/chat/completions", "/v1/chat/completions stream"]
    inputs = {
        "emotional_help": ["我现在有点难受", "心里堵得慌", "有点撑不住但没有危险"],
        "relationship_distress": ["我们吵架后我很慌", "她刚才那句话让我很受伤", "我感觉被推开了"],
        "pressure_expression": ["最近压力很大", "我觉得好累", "这阵子一直很烦"],
        "mild_sadness": ["今天有点低落", "我有点失落", "突然很没劲"],
        "anger_without_crisis": ["我现在很烦", "我有点生气", "这事让我火大"],
        "anxiety_without_crisis": ["我有点焦虑", "我心里不踏实", "我总觉得会出事"],
        "conflict_after_argument": ["刚吵完我不知道怎么办", "争完以后我很乱", "吵完我心里很空"],
        "low_mood_non_crisis": ["状态很低", "人有点蔫", "没什么精神"],
    }
    warm_anchors = ["刺", "慌", "堵", "委屈", "难受", "发紧", "推开", "责怪自己", "不奇怪"]
    action_anchors = ["先", "小动作", "停一下", "降一点", "确认", "沟通", "冷静"]

    passed = 0
    for idx in range(150):
        speech_act = rng.choice(speech_acts)
        case = {
            "seed": 2026050100 + idx,
            "speech_act": speech_act,
            "scene": rng.choice(scenes),
            "tone": rng.choice(tones),
            "skill": rng.choice(skills),
            "path": rng.choice(paths),
            "user_input": rng.choice(inputs[speech_act]),
            "raw_output": rng.choice(RAW_EMOTIONAL_SUPPORT_OUTPUTS),
        }
        ctx = _emotion_context(case["seed"], case["scene"], case["skill"])
        output, used, reason = _warm_emotional_support_first_sentence(
            ctx,
            case["user_input"],
            case["raw_output"],
        )
        first = _first_sentence(output)

        assert output.strip()
        assert len(output) <= 120
        assert used is True
        assert reason == "first_sentence_warmed"
        assert any(anchor in first for anchor in warm_anchors)
        assert not first.startswith(("你可以", "建议", "直接结论"))
        assert any(anchor in output for anchor in action_anchors)
        passed += 1

    assert passed == 150


def test_px2e_does_not_touch_crisis_identity_repair_or_non_emotional_support():
    base_output = "我理解你的感受。你可以先停一下争辩，晚点再确认真实想法。"

    crisis = _emotion_context(1, "emotion", "skills_off")
    crisis.runtime_trace["route_state"]["risk_level"] = "crisis"
    output, used, reason = _warm_emotional_support_first_sentence(crisis, "我不想活了", base_output)
    assert output == base_output
    assert used is False
    assert reason == "skip_crisis"

    identity = _emotion_context(2, "emotion", "skills_off")
    identity.runtime_trace["response_obligation"]["expected_deliverable"] = "identity_answer"
    identity.runtime_trace["response_obligation"]["identity_answer_required"] = True
    output, used, reason = _warm_emotional_support_first_sentence(identity, "你是谁", base_output)
    assert output == base_output
    assert used is False
    assert reason == "skip_not_emotional_support"

    repair = _emotion_context(3, "emotion", "skills_off")
    repair.runtime_trace["response_obligation"]["repair_required"] = True
    output, used, reason = _warm_emotional_support_first_sentence(repair, "你刚才没听懂", base_output)
    assert output == base_output
    assert used is False
    assert reason == "skip_repair"

    normal = _emotion_context(4, "emotion", "skills_off", expected="direct_answer")
    output, used, reason = _warm_emotional_support_first_sentence(normal, "怎么处理", base_output)
    assert output == base_output
    assert used is False
    assert reason == "skip_not_emotional_support"


def test_px2e_skip_to_end_integration_keeps_emotional_support_short(monkeypatch):
    import modules.L4.field_quality as field_quality

    monkeypatch.setattr(
        field_quality,
        "quality_check",
        lambda output, context: SimpleNamespace(passed=True, failed_items=[]),
    )

    ctx = _emotion_context(5, "emotion", "emotion_skill_on")
    ctx.output = "我理解你的感受。你可以先停一下争辩，晚点再确认真实想法。"

    result = step8_execution(
        {
            "context": ctx,
            "user_input": "我和她吵完以后很慌",
            "skip_to_end": True,
            "runtime_trace": ctx.runtime_trace,
        }
    )

    output = result["output"]
    trace = result["context"].runtime_trace

    assert output.strip()
    assert len(output) <= 120
    assert not output.startswith("我理解你的感受")
    assert trace["emotional_support_warmth_polish_used"] is True
    assert trace.get("repair_contract_takeover_used") is not True
    assert trace.get("fallback_contract_takeover_used") is not True
