"""
Step 1.5 身份/情境触发机制测试。
"""

from graph.nodes.step1_5_meta import step1_5_meta_controller
from schemas.context import Context


def _state(user_input: str, ctx: Context | None = None):
    return {
        "context": ctx or Context(session_id="step1-5-meta"),
        "user_input": user_input,
    }


def test_step1_5_should_keep_identity_and_situation_without_trigger(monkeypatch):
    import llm.nvidia_client as nvidia_client

    monkeypatch.setattr(
        nvidia_client,
        "invoke_fast",
        lambda *_args, **_kwargs: (
            '{"input_type":"混合","confidence":0.7,'
            '"identity_hint":"个人决策","identity_confidence":0.92,'
            '"situation_hint":"推进结果","situation_confidence":0.9}'
        ),
    )

    ctx = Context(session_id="meta-keep")
    ctx.identity_hint = "团队决策"
    ctx.identity_confidence = 0.88
    ctx.situation_hint = "管理执行"
    ctx.situation_confidence = 0.82

    result = step1_5_meta_controller(_state("继续", ctx))

    assert result["context"].identity_hint == "团队决策"
    assert result["context"].situation_hint == "管理执行"


def test_step1_5_should_refresh_identity_and_situation_on_explicit_shift(monkeypatch):
    import llm.nvidia_client as nvidia_client

    monkeypatch.setattr(
        nvidia_client,
        "invoke_fast",
        lambda *_args, **_kwargs: (
            '{"input_type":"场景描述","confidence":0.82,'
            '"identity_hint":"关系沟通","identity_confidence":0.87,'
            '"situation_hint":"稳定情绪","situation_confidence":0.83}'
        ),
    )

    ctx = Context(session_id="meta-shift")
    ctx.identity_hint = "团队决策"
    ctx.identity_confidence = 0.88
    ctx.situation_hint = "管理执行"
    ctx.situation_confidence = 0.82

    result = step1_5_meta_controller(_state("先不聊工作了，回家后我更担心孩子最近情绪不太对", ctx))

    assert result["context"].identity_hint == "关系沟通"
    assert result["context"].situation_hint == "稳定情绪"


def test_step1_5_should_trigger_guidance_when_identity_or_situation_missing(monkeypatch):
    import llm.nvidia_client as nvidia_client

    monkeypatch.setattr(
        nvidia_client,
        "invoke_fast",
        lambda *_args, **_kwargs: (
            '{"input_type":"问题咨询","confidence":0.76,'
            '"identity_hint":"未识别","identity_confidence":0.2,'
            '"situation_hint":"未识别","situation_confidence":0.2}'
        ),
    )

    ctx = Context(session_id="meta-guidance")
    ctx.add_history("user", "前面我说了很多")
    ctx.add_history("system", "我在听")
    ctx.add_history("user", "继续")
    ctx.guidance_cooldown = 0

    result = step1_5_meta_controller(_state("给我一个方案", ctx))

    assert result["context"].guidance_needed is True
    assert result["context"].guidance_focus in {"identity", "situation", "both"}
    assert result["context"].guidance_prompt


def test_step1_5_should_set_management_sub_intent_for_action_request(monkeypatch):
    import llm.nvidia_client as nvidia_client

    monkeypatch.setattr(
        nvidia_client,
        "invoke_fast",
        lambda *_args, **_kwargs: (
            '{"input_type":"问题咨询","confidence":0.8,'
            '"identity_hint":"团队决策","identity_confidence":0.82,'
            '"situation_hint":"管理执行","situation_confidence":0.84}'
        ),
    )

    ctx = Context(session_id="meta-mgmt-action")
    ctx.primary_scene = "management"

    result = step1_5_meta_controller(_state("你先别讲大道理，给我一个本周能落地的动作。", ctx))

    assert result["context"].management_sub_intent == "action_request"
    assert result["context"].management_sub_intent_confidence >= 0.8


def test_step1_5_should_set_management_sub_intent_for_upward_report(monkeypatch):
    import llm.nvidia_client as nvidia_client

    monkeypatch.setattr(
        nvidia_client,
        "invoke_fast",
        lambda *_args, **_kwargs: (
            '{"input_type":"场景描述","confidence":0.8,'
            '"identity_hint":"团队决策","identity_confidence":0.82,'
            '"situation_hint":"管理执行","situation_confidence":0.84}'
        ),
    )

    ctx = Context(session_id="meta-mgmt-upward")
    ctx.primary_scene = "management"

    result = step1_5_meta_controller(_state("领导对 AI 转型进度不满，但实际情况是技术债很重", ctx))

    assert result["context"].management_sub_intent == "upward_report"


def test_step1_5_should_set_management_sub_intent_for_change_fatigue(monkeypatch):
    import llm.nvidia_client as nvidia_client

    monkeypatch.setattr(
        nvidia_client,
        "invoke_fast",
        lambda *_args, **_kwargs: (
            '{"input_type":"场景描述","confidence":0.8,'
            '"identity_hint":"团队决策","identity_confidence":0.82,'
            '"situation_hint":"管理执行","situation_confidence":0.84}'
        ),
    )

    ctx = Context(session_id="meta-mgmt-change")
    ctx.primary_scene = "management"

    result = step1_5_meta_controller(_state("又是新工具，能不能消停会？", ctx))

    assert result["context"].management_sub_intent == "change_fatigue"


def test_step1_5_should_set_sales_sub_intent_for_price_objection(monkeypatch):
    import llm.nvidia_client as nvidia_client

    monkeypatch.setattr(
        nvidia_client,
        "invoke_fast",
        lambda *_args, **_kwargs: (
            '{"input_type":"问题咨询","confidence":0.8,'
            '"identity_hint":"个人决策","identity_confidence":0.82,'
            '"situation_hint":"推进结果","situation_confidence":0.84}'
        ),
    )

    ctx = Context(session_id="meta-sales-price")
    ctx.primary_scene = "sales"

    result = step1_5_meta_controller(_state("你们的价格太贵了，竞品便宜 30%", ctx))

    assert result["context"].sales_sub_intent == "price_objection"


def test_step1_5_should_set_negotiation_sub_intent_for_payment_term(monkeypatch):
    import llm.nvidia_client as nvidia_client

    monkeypatch.setattr(
        nvidia_client,
        "invoke_fast",
        lambda *_args, **_kwargs: (
            '{"input_type":"问题咨询","confidence":0.8,'
            '"identity_hint":"团队决策","identity_confidence":0.82,'
            '"situation_hint":"协商分歧","situation_confidence":0.84}'
        ),
    )

    ctx = Context(session_id="meta-neg-payment")
    ctx.primary_scene = "negotiation"

    result = step1_5_meta_controller(_state("对方坚持 90 天账期，否则不签", ctx))

    assert result["context"].negotiation_sub_intent == "payment_term"


def test_step1_5_should_set_emotion_sub_intent_for_low_energy(monkeypatch):
    import llm.nvidia_client as nvidia_client

    monkeypatch.setattr(
        nvidia_client,
        "invoke_fast",
        lambda *_args, **_kwargs: (
            '{"input_type":"情绪表达","confidence":0.8,'
            '"identity_hint":"个人决策","identity_confidence":0.82,'
            '"situation_hint":"稳定情绪","situation_confidence":0.84}'
        ),
    )

    ctx = Context(session_id="meta-emotion-low-energy")
    ctx.primary_scene = "emotion"

    result = step1_5_meta_controller(_state("我现在没精力想这么多。", ctx))

    assert result["context"].emotion_sub_intent == "low_energy_support"


def test_step1_5_should_set_emotion_sub_intent_for_failure_containment(monkeypatch):
    import llm.nvidia_client as nvidia_client

    monkeypatch.setattr(
        nvidia_client,
        "invoke_fast",
        lambda *_args, **_kwargs: (
            '{"input_type":"情绪表达","confidence":0.8,'
            '"identity_hint":"个人决策","identity_confidence":0.82,'
            '"situation_hint":"稳定情绪","situation_confidence":0.84}'
        ),
    )

    ctx = Context(session_id="meta-emotion-failure")
    ctx.primary_scene = "emotion"

    result = step1_5_meta_controller(_state("如果失败了怎么办，我现在很怕。", ctx))

    assert result["context"].emotion_sub_intent == "failure_containment"
