"""
L5 人性工程师案例回填测试。
"""

from modules.L5.engineer_cases.cases import ENGINEER_CASES
from modules.L5.knowledge_router import match_case_detail
from schemas.context import Context, GoalItem
from schemas.enums import EmotionType, ResistanceType
from schemas.user_state import Emotion, Desires, Resistance


def test_engineer_cases_should_cover_original_major_scenarios():
    assert len(ENGINEER_CASES) >= 10


def test_match_case_detail_should_find_horizontal_collaboration_case():
    ctx = Context(session_id="case-horizontal")
    ctx.goal.current = GoalItem(type="利益价值")
    ctx.user.emotion = Emotion(type=EmotionType.CALM, intensity=0.42)
    ctx.user.desires = Desires(pride=0.7, greed=0.6)
    ctx.user.resistance = Resistance(type=ResistanceType.PRIDE, intensity=0.5)

    result = match_case_detail("跨部门那个老油条同事一直推诿不配合，我怎么推进协作？", context=ctx)

    assert result is not None
    assert result.title == "横向协作：推动老油条同事配合"
    assert "连招主线" in result.content


def test_match_case_detail_should_find_family_boundary_case():
    ctx = Context(session_id="case-family")
    ctx.goal.current = GoalItem(type="情绪价值")
    ctx.user.emotion = Emotion(type=EmotionType.FRUSTRATED, intensity=0.7)
    ctx.user.desires = Desires(fear=0.8, pride=0.4)
    ctx.user.resistance = Resistance(type=ResistanceType.FEAR, intensity=0.7)

    result = match_case_detail("家里长辈总拿孝顺压我，逼我答应不合理要求，我该怎么设边界？", context=ctx)

    assert result is not None
    assert result.title == "家庭伦理：拒绝道德绑架"
    assert "核心目的" in result.content


def test_match_case_detail_should_find_public_speaking_case():
    ctx = Context(session_id="case-speaking")
    ctx.goal.current = GoalItem(type="利益价值")
    ctx.user.emotion = Emotion(type=EmotionType.CONFUSED, intensity=0.55)
    ctx.user.desires = Desires(pride=0.6, fear=0.7)
    ctx.user.resistance = Resistance(type=ResistanceType.FEAR, intensity=0.6)

    result = match_case_detail("我在公开汇报时被人当场刁钻提问，明显想让我难堪，这种场面怎么接？", context=ctx)

    assert result is not None
    assert result.title == "公众表达：化解刁钻提问"
    assert "应急预案" in result.content
