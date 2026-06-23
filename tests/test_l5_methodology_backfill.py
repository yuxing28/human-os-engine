"""
L5 人生方法论回填测试。
"""

from modules.L5.knowledge_router import query_knowledge
from modules.L5.life_methodology.methodology import METHODOLOGY_KNOWLEDGE


def test_methodology_knowledge_should_be_expanded_beyond_summary_level():
    assert len(METHODOLOGY_KNOWLEDGE) >= 18


def test_query_knowledge_should_find_desire_noise_reduction():
    result = query_knowledge(
        "我总会被社交媒体种草，老想买东西，怎么给欲望降噪？",
        input_type="问题咨询",
        goal_type="情绪价值",
    )

    assert result is not None
    assert result.title in {"欲望降噪", "欲望管理"}
    assert "欲望" in result.content


def test_query_knowledge_should_find_rules_adaptation_for_new_environment():
    result = query_knowledge(
        "刚到新公司，感觉很多不成文规矩和组织文化我都摸不透，怎么办？",
        input_type="问题咨询",
        goal_type="利益价值",
    )

    assert result is not None
    assert result.title == "明规则与潜在惯例"
    assert "不成文" in result.content or "惯例" in result.content


def test_query_knowledge_should_find_optionality_for_uncertain_decision():
    result = query_knowledge(
        "现在环境太不确定了，我做决定时怎么保留选择权，不想一下把路走死？",
        input_type="问题咨询",
        goal_type="利益价值",
    )

    assert result is not None
    assert result.title in {"保留选择权", "不确定性与反脆弱"}
    assert "选择权" in result.content or "余地" in result.content
