"""
L5 人性营销回填测试。
"""

from modules.L5.knowledge_router import query_knowledge
from modules.L5.marketing.marketing import MARKETING_KNOWLEDGE


def test_marketing_knowledge_should_be_expanded_beyond_summary_level():
    assert len(MARKETING_KNOWLEDGE) >= 30


def test_query_knowledge_should_find_community_building_for_brand_belonging():
    result = query_knowledge(
        "我做一个新品牌，想让用户慢慢形成归属感和参与感，怎么做社群比较对？",
        input_type="问题咨询",
        goal_type="利益价值",
        scene_id="sales",
    )

    assert result is not None
    assert result.title in {"社群构建与归属感", "身份认同营销"}
    assert "归属感" in result.content or "社群" in result.content


def test_query_knowledge_should_find_aida_map_for_conversion_path_design():
    result = query_knowledge(
        "我在设计转化链路，想按AIDA把认知、兴趣、欲望、行动一路串起来，应该怎么拆？",
        input_type="问题咨询",
        goal_type="利益价值",
        scene_id="sales",
    )

    assert result is not None
    assert result.title == "用户决策路径植入地图"
    assert "AIDA" in result.content


def test_query_knowledge_should_find_price_fairness_for_anti_harvest_concern():
    result = query_knowledge(
        "我不想让用户觉得我们在割韭菜，怎么把价格公平和定价逻辑讲清楚？",
        input_type="问题咨询",
        goal_type="利益价值",
        scene_id="sales",
    )

    assert result is not None
    assert result.title == "价格公平与资源分配叙事"
    assert "公平" in result.content or "定价" in result.content


def test_query_knowledge_should_find_ecosystem_future_for_long_term_brand_plan():
    result = query_knowledge(
        "一个科技品牌除了卖单品，还想做生态和未来感，应该怎么讲这件事？",
        input_type="问题咨询",
        goal_type="利益价值",
        scene_id="sales",
    )

    assert result is not None
    assert result.title == "生态系统与未来感"
    assert "生态" in result.content or "未来感" in result.content
