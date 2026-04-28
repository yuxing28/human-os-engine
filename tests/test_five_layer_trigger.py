"""
五层触发机制测试。
"""

from modules.L4.five_layer_structure import (
    generate_five_layer_output,
    should_trigger_layer1,
    should_trigger_layer2,
    should_trigger_layer3,
    should_trigger_layer4,
    should_trigger_layer5,
)
from schemas.enums import EmotionType, MotiveType
from schemas.user_state import Emotion, UserState


def _user(
    emotion_type=EmotionType.CALM,
    intensity=0.3,
    motive=MotiveType.LIFE_EXPECTATION,
):
    return UserState(
        emotion=Emotion(type=emotion_type, intensity=intensity),
        motive=motive,
    )


def test_layer4_should_trigger_for_vague_question_with_missing_goal():
    user = _user()

    triggered = should_trigger_layer4(
        user=user,
        user_input="这个事我到底该怎么办",
        input_type="问题咨询",
        mode="B",
        guidance_needed=False,
        short_utterance=False,
        goal_description="未明确",
    )

    assert triggered is True


def test_layer1_should_stay_for_relationship_repair_scene():
    user = _user(emotion_type=EmotionType.FRUSTRATED, intensity=0.61)

    triggered = should_trigger_layer1(
        user=user,
        user_input="我和伴侣现在越聊越僵，我真的不知道该怎么开口了",
        input_type="混合",
        scene="emotion",
        identity_hint="关系沟通",
        situation_hint="稳定情绪",
        mode="A",
        guidance_needed=False,
        short_utterance=False,
        goal_description="修复关系",
    )

    assert triggered is True


def test_layer1_should_not_trigger_for_low_emotion_direct_business_action_ask():
    user = _user(emotion_type=EmotionType.CALM, intensity=0.24)

    triggered = should_trigger_layer1(
        user=user,
        user_input="给我推进模板",
        input_type="问题咨询",
        scene="sales",
        identity_hint="个人决策",
        situation_hint="推进结果",
        mode="B",
        guidance_needed=False,
        short_utterance=False,
        goal_description="推进客户成交",
    )

    assert triggered is False


def test_layer3_should_trigger_for_relationship_repair_scene():
    user = _user(emotion_type=EmotionType.ANGRY, intensity=0.78)

    triggered = should_trigger_layer3(
        user=user,
        user_input="我和老婆又吵起来了，我现在真的很顶",
        input_type="混合",
        scene="emotion",
        identity_hint="关系沟通",
        situation_hint="稳定情绪",
        mode="A",
        short_utterance=False,
    )

    assert triggered is True


def test_layer2_should_trigger_for_relationship_conflict_alignment():
    user = _user(emotion_type=EmotionType.FRUSTRATED, intensity=0.62)

    triggered = should_trigger_layer2(
        user=user,
        user_input="我其实不是想吵赢，我是想让她别再误会我的意思",
        input_type="混合",
        scene="emotion",
        identity_hint="关系沟通",
        situation_hint="协商分歧",
        mode="A",
        guidance_needed=False,
        short_utterance=False,
        goal_description="修复关系",
    )

    assert triggered is True


def test_layer2_should_not_trigger_for_short_direct_business_push():
    user = _user(emotion_type=EmotionType.CALM, intensity=0.26)

    triggered = should_trigger_layer2(
        user=user,
        user_input="给我推进话术",
        input_type="问题咨询",
        scene="sales",
        identity_hint="个人决策",
        situation_hint="推进结果",
        mode="B",
        guidance_needed=False,
        short_utterance=False,
        goal_description="推进客户成交",
    )

    assert triggered is False


def test_layer3_should_not_trigger_for_low_emotion_business_question():
    user = _user(emotion_type=EmotionType.CALM, intensity=0.28)

    triggered = should_trigger_layer3(
        user=user,
        user_input="客户成交一直卡住，我想要一个更直接的推进方案",
        input_type="问题咨询",
        scene="sales",
        identity_hint="个人决策",
        situation_hint="推进结果",
        mode="B",
        short_utterance=False,
    )

    assert triggered is False


def test_layer5_should_trigger_for_low_emotion_business_push():
    user = _user(emotion_type=EmotionType.CALM, intensity=0.35)

    triggered = should_trigger_layer5(
        user=user,
        user_input="客户推进卡住了，我现在想要一个更直接的推进方案",
        input_type="问题咨询",
        scene="sales",
        identity_hint="个人决策",
        situation_hint="推进结果",
        mode="B",
        short_utterance=False,
        guidance_needed=False,
        goal_description="推进客户成交",
        layer4_needed=False,
    )

    assert triggered is True


def test_layer5_should_not_trigger_when_emotion_needs_stabilizing_first():
    user = _user(emotion_type=EmotionType.ANGRY, intensity=0.82)

    triggered = should_trigger_layer5(
        user=user,
        user_input="我和老婆现在越聊越炸，我知道该沟通但我现在真的压不住",
        input_type="混合",
        scene="emotion",
        identity_hint="关系沟通",
        situation_hint="稳定情绪",
        mode="A",
        short_utterance=False,
        guidance_needed=False,
        goal_description="修复关系",
        layer4_needed=False,
    )

    assert triggered is False


def test_layer4_should_not_trigger_for_detailed_question():
    user = _user()

    triggered = should_trigger_layer4(
        user=user,
        user_input="客户已经拖了两周不签，我现在担心压太紧把关系搞坏，但继续等下去窗口又会过去，这种情况我到底该先推进价格还是先补价值证明？",
        input_type="问题咨询",
        mode="B",
        guidance_needed=False,
        short_utterance=False,
        goal_description="推进客户成交",
    )

    assert triggered is False


def test_layer4_should_not_trigger_when_high_emotion_needs_stabilizing_first():
    user = _user(emotion_type=EmotionType.ANGRY, intensity=0.9)

    triggered = should_trigger_layer4(
        user=user,
        user_input="我现在真的很炸，这件事到底怎么办",
        input_type="混合",
        mode="A",
        guidance_needed=False,
        short_utterance=False,
        goal_description="修复关系",
    )

    assert triggered is False


def test_generate_five_layer_output_should_add_layer4_when_gap_exists():
    user = _user(motive=MotiveType.LIFE_EXPECTATION)

    layers = generate_five_layer_output(
        user=user,
        strategy_weapons=[],
        weapon_usage={},
        mode="B",
        user_input="这件事我到底该怎么办",
        input_type="问题咨询",
        scene="sales",
        identity_hint="个人决策",
        situation_hint="推进结果",
        guidance_needed=True,
        short_utterance=False,
        goal_description="未明确",
    )

    layer_ids = [layer["layer"] for layer in layers]
    assert layer_ids == [1, 2, 4]
    assert 4 in layer_ids


def test_generate_five_layer_output_should_remove_layer4_when_detail_is_enough():
    user = _user(intensity=0.5)

    layers = generate_five_layer_output(
        user=user,
        strategy_weapons=[],
        weapon_usage={},
        mode="B",
        user_input="客户已经拖了两周不签，我担心压太紧伤关系，也怕继续拖下去没窗口，这种情况我更该先重做价格锚定还是先补价值证明？",
        input_type="问题咨询",
        scene="sales",
        identity_hint="个人决策",
        situation_hint="推进结果",
        guidance_needed=False,
        short_utterance=False,
        goal_description="推进客户成交",
    )

    layer_ids = [layer["layer"] for layer in layers]
    assert 4 not in layer_ids


def test_generate_five_layer_output_should_remove_layer3_for_low_emotion_business_push():
    user = _user(emotion_type=EmotionType.CALM, intensity=0.32, motive=MotiveType.LIFE_EXPECTATION)

    layers = generate_five_layer_output(
        user=user,
        strategy_weapons=[],
        weapon_usage={},
        mode="B",
        user_input="客户推进卡住了，我现在想直接拿一个更有效的推进动作",
        input_type="问题咨询",
        scene="sales",
        identity_hint="个人决策",
        situation_hint="推进结果",
        guidance_needed=False,
        short_utterance=False,
        goal_description="推进客户成交",
    )

    layer_ids = [layer["layer"] for layer in layers]
    assert layer_ids == [5]
    assert 1 not in layer_ids
    assert 2 not in layer_ids
    assert 3 not in layer_ids
    assert 5 in layer_ids


def test_generate_five_layer_output_should_add_layer3_for_relationship_repair():
    user = _user(emotion_type=EmotionType.FRUSTRATED, intensity=0.72, motive=MotiveType.LIFE_EXPECTATION)

    layers = generate_five_layer_output(
        user=user,
        strategy_weapons=[],
        weapon_usage={},
        mode="A",
        user_input="我和伴侣越聊越僵，我现在最怕关系彻底冷掉",
        input_type="混合",
        scene="emotion",
        identity_hint="关系沟通",
        situation_hint="稳定情绪",
        guidance_needed=False,
        short_utterance=False,
        goal_description="修复关系",
    )

    layer_ids = [layer["layer"] for layer in layers]
    assert layer_ids == [1, 3, 2]
    assert 1 in layer_ids
    assert 2 in layer_ids
    assert 3 in layer_ids
    assert 5 not in layer_ids


def test_generate_five_layer_output_should_remove_layer5_when_gap_is_large():
    user = _user(emotion_type=EmotionType.CALM, intensity=0.38)

    layers = generate_five_layer_output(
        user=user,
        strategy_weapons=[],
        weapon_usage={},
        mode="B",
        user_input="这个事我到底该怎么办",
        input_type="问题咨询",
        scene="sales",
        identity_hint="个人决策",
        situation_hint="推进结果",
        guidance_needed=True,
        short_utterance=False,
        goal_description="未明确",
    )

    layer_ids = [layer["layer"] for layer in layers]
    assert 4 in layer_ids
    assert 5 not in layer_ids
