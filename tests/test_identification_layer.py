"""
识别层补强后的定向测试。
"""

from graph.nodes.step1_identify import _estimate_attention_state
from modules.L2.collaboration_temperature import identify_emotion
from modules.L2.dual_core_recognition import identify_dual_core
from modules.L2.sins_keyword import identify_desires


def test_desire_fear_should_be_dominant_for_failure_and_missing_out():
    result = identify_desires("我有点怂了，怕失败，也担心错过这次机会")
    dominant, score = result.desires.get_dominant()
    assert dominant == "fear"
    assert score >= 0.5
    assert result.confidence >= 0.5


def test_desire_gluttony_should_catch_endless_scrolling():
    result = identify_desires("最近一刷短视频就停不下来，真的有点上瘾")
    dominant, score = result.desires.get_dominant()
    assert dominant == "gluttony"
    assert score > 0.0


def test_emotion_impatient_should_match_direct_and_hurry_style():
    result = identify_emotion("别废话，直接告诉我怎么做，快点")
    assert result.type == "急躁"
    assert result.intensity >= 0.8


def test_emotion_frustrated_should_link_to_fear_avoidance():
    result = identify_emotion("刚分手，工作也丢了，我真的快崩溃了，不知道怎么办")
    assert result.type == "挫败"
    assert result.motive == "回避恐惧"


def test_dual_core_conflict_should_detect_inner_conflict():
    result = identify_dual_core("道理都懂，但就是控制不住，明知道不该买还是买了")
    assert result.state == "对抗"
    assert result.dominant == "感性核"


def test_attention_should_mark_overload_for_long_chaotic_input():
    focus, hijacker = _estimate_attention_state(
        user_input="我现在脑子很乱，信息量太大了，一下子好多事堆在一起，真的有点看不懂，也不知道先做哪个，"
        "然后这个也要那个也要，我有点懵了",
        emotion_type="迷茫",
        emotion_intensity=0.82,
        dominant_desire="fear",
        desire_weight=0.68,
        recent_user_inputs=["我有点懵", "我有点懵"],
    )
    assert focus <= 0.35
    assert hijacker == "信息过载"


def test_attention_should_stay_focused_for_calm_structured_input():
    focus, hijacker = _estimate_attention_state(
        user_input="我想做个学习计划，你给我一个具体步骤和执行方案",
        emotion_type="平静",
        emotion_intensity=0.2,
        dominant_desire="greed",
        desire_weight=0.2,
        recent_user_inputs=["我想做个学习计划"],
    )
    assert focus >= 0.75
    assert hijacker == "null"
