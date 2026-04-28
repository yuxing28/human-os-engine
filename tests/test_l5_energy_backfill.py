"""
L5 能量系统回填测试。
"""

from modules.L5.energy.knowledge import ENERGY_KNOWLEDGE
from modules.L5.knowledge_router import query_knowledge


def test_energy_knowledge_should_be_expanded_beyond_summary_level():
    assert len(ENERGY_KNOWLEDGE) >= 10


def test_query_knowledge_should_find_attention_recovery_for_scroll_anxiety():
    result = query_knowledge(
        "我最近刷手机停不下来，脑子很乱，焦虑也下不去，我该怎么先把注意力收回来？",
        input_type="问题咨询",
        goal_type="情绪价值",
    )

    assert result is not None
    assert result.title in {"收回注意力", "注意力被劫持", "能量自诊三问"}
    assert "注意力" in result.content or "干扰" in result.content


def test_query_knowledge_should_find_boundary_repair_for_people_pleasing():
    result = query_knowledge(
        "我总是不敢拒绝别人，别人一句话我就破防，边界感很差，怎么修？",
        input_type="问题咨询",
        goal_type="情绪价值",
    )

    assert result is not None
    assert result.title in {"修复外层与边界感", "外层破损与边界失守"}
    assert "边界" in result.content or "拒绝" in result.content


def test_query_knowledge_should_find_inner_nourishment_for_exhaustion():
    result = query_knowledge(
        "我最近长期失眠，整个人像被掏空了一样，完全没行动力，该怎么慢慢恢复？",
        input_type="问题咨询",
        goal_type="情绪价值",
    )

    assert result is not None
    assert result.title in {"滋养内在与重启系统", "内在枯竭与慢恢复", "崩溃修复总路线"}
    assert "恢复" in result.content or "睡眠" in result.content
