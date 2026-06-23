"""
L5 知识路由核心行为测试。
"""

import sys
from types import SimpleNamespace

from modules.L5.loader import CaseEntry, KnowledgeEntry
from modules.L5.knowledge_router import match_case, match_case_detail, query_knowledge
from schemas.context import Context
from schemas.enums import EmotionType, ResistanceType


def _build_context() -> Context:
    ctx = Context(session_id="test-knowledge-router")
    ctx.user.emotion.type = EmotionType.ANGRY
    ctx.user.desires.greed = 0.9
    ctx.user.resistance.type = ResistanceType.GREED
    ctx.user.relationship_position = "服务-客户"
    ctx.situation_stage = "推进"
    ctx.primary_scene = "sales"
    return ctx


def test_query_knowledge_should_prefer_trigger_and_append_action_and_hints(monkeypatch):
    ctx = _build_context()
    ctx.goal.granular_goal = "goal.sales"

    weak_entry = KnowledgeEntry(
        id="weak",
        title="弱匹配",
        category="life_methodology",
        keywords=["情绪"],
        content="普通内容",
        source_file="11-人生方法论模块-内核层.md",
    )
    strong_entry = KnowledgeEntry(
        id="strong",
        title="强匹配",
        category="marketing",
        keywords=["转化", "价格"],
        content="高匹配内容",
        source_file="20-人性营销模块-情绪操盘与仪式感设计.md",
        trigger_conditions={
            "emotion_types": ["愤怒"],
            "desires": ["greed"],
            "situation_stages": ["推进"],
            "relationship_positions": ["服务-客户"],
        },
        action_mapping="先稳住情绪，再推进成交问题",
        priority_scenes=["sales"],
    )

    monkeypatch.setattr(
        "modules.L5.knowledge_router.search_knowledge",
        lambda *_args, **_kwargs: [weak_entry, strong_entry],
    )

    fake_counter_example_lib = SimpleNamespace(
        get_failure_hints=lambda *_args, **_kwargs: ["[避坑] 不要先压价对抗 (近期2次)"]
    )
    monkeypatch.setitem(sys.modules, "modules.L5.counter_example_lib", fake_counter_example_lib)

    result = query_knowledge(
        user_input="客户一直卡价格，我想提升转化",
        input_type="问题咨询",
        goal_type="利益价值",
        scene_id="sales",
        context=ctx,
    )

    assert result is not None
    assert result.title == "强匹配"
    assert "[策略指引] 先稳住情绪，再推进成交问题" in result.content
    assert "[避坑] 不要先压价对抗" in result.content
    assert result.confidence >= 0.9


def test_query_knowledge_should_return_none_when_no_result(monkeypatch):
    monkeypatch.setattr(
        "modules.L5.knowledge_router.search_knowledge",
        lambda *_args, **_kwargs: [],
    )
    result = query_knowledge("完全无匹配输入")
    assert result is None


def test_match_case_detail_should_pick_best_context_case_and_append_quick_parts(monkeypatch):
    ctx = _build_context()
    ctx.goal.current.type = "利益价值"

    weak_case = CaseEntry(
        id="weak",
        title="弱案例",
        category="engineer",
        scenario_keywords=["关系"],
        emotion_types=["平静"],
        desires=["fear"],
        content="弱案例内容",
        source_file="cases_weak.md",
        goal_types=["情绪价值"],
        core_purpose="",
        tactical_sequence=[],
        emergency_plan="",
        quick_principle="",
    )
    strong_case = CaseEntry(
        id="strong",
        title="强案例",
        category="engineer",
        scenario_keywords=["老板", "价格", "预算"],
        emotion_types=["愤怒"],
        desires=["greed", "贪婪"],
        content="强案例内容",
        source_file="cases_strong.md",
        goal_types=["利益价值"],
        core_purpose="稳住关系，再谈方案",
        tactical_sequence=["先接住", "再澄清", "最后推进"],
        emergency_plan="用户升级对抗时先降压",
        quick_principle="先关系后价格",
        applicable_scenes=["sales"],
        relationship_positions=["服务-客户"],
        continuation_hints=["下一轮先问预算边界"],
    )

    monkeypatch.setattr(
        "modules.L5.knowledge_router.CASE_DATABASE",
        {"weak": weak_case, "strong": strong_case},
    )
    monkeypatch.setattr(
        "modules.L5.knowledge_router.search_cases",
        lambda *_args, **_kwargs: [weak_case],
    )

    result = match_case_detail("老板一直压价，我要谈预算", context=ctx)

    assert result is not None
    assert result.title == "强案例"
    assert "核心目的：稳住关系，再谈方案" in result.content
    assert "连招主线：先接住 -> 再澄清 -> 最后推进" in result.content
    assert result.continuation_hints == ["下一轮先问预算边界"]
    assert result.confidence >= 0.78


def test_match_case_detail_should_fallback_to_search_cases_when_no_context_match(monkeypatch):
    ctx = _build_context()
    fallback_case = CaseEntry(
        id="fallback",
        title="兜底案例",
        category="engineer",
        scenario_keywords=["客户"],
        emotion_types=["平静"],
        desires=["fear"],
        content="兜底内容",
        source_file="cases_fallback.md",
        goal_types=["利益价值"],
        core_purpose="",
        tactical_sequence=[],
        emergency_plan="",
        quick_principle="",
    )

    monkeypatch.setattr("modules.L5.knowledge_router.CASE_DATABASE", {})
    monkeypatch.setattr(
        "modules.L5.knowledge_router.search_cases",
        lambda *_args, **_kwargs: [fallback_case],
    )

    result = match_case_detail("给我一个案例", context=ctx)

    assert result is not None
    assert result.title == "兜底案例"
    assert result.confidence == 0.65


def test_match_case_should_return_title_or_none(monkeypatch):
    monkeypatch.setattr(
        "modules.L5.knowledge_router.match_case_detail",
        lambda *_args, **_kwargs: SimpleNamespace(title="案例标题"),
    )
    assert match_case("test") == "案例标题"

    monkeypatch.setattr("modules.L5.knowledge_router.match_case_detail", lambda *_args, **_kwargs: None)
    assert match_case("test") is None
