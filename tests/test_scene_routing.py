"""
Human-OS Engine 3.0 - Skill Routing Tests
"""

import pytest
from modules.L5.skill_registry import SkillRegistry
from schemas.context import Context
from graph.builder import build_graph
from modules.L5.scene_loader import load_scene_config


class TestSkillRegistry:
    def _new_registry(self):
        return SkillRegistry()

    def test_sales_detection(self):
        registry = self._new_registry()
        cases = [
            "客户一直拖着不签，月底了怎么办",
            "线索太差了，全是空号",
            "竞品比我们便宜 30%，怎么打",
            "这个月还差 3 单达标",
            "ROI 算不清楚，CFO 不批预算",
        ]
        for text in cases:
            skill_id = registry.match_skill(text)
            assert skill_id == "sales", f"'{text}' -> {skill_id}"

    def test_management_detection(self):
        registry = self._new_registry()
        cases = [
            "下属绩效不达标，怎么谈",
            "团队内卷严重，大家都在摸鱼",
            "跨部门协同推不动",
            "向上汇报，领导期望太高",
            "员工加班太多，要 burnout 了",
        ]
        for text in cases:
            skill_id = registry.match_skill(text)
            assert skill_id == "management", f"'{text}' -> {skill_id}"

    def test_negotiation_detection(self):
        registry = self._new_registry()
        cases = [
            "谈判陷入僵局，对方不肯让步",
            "我们的 BATNA 是什么",
            "锚定价格太高，需要重置",
            "最后通牒，不签就走人",
            "合同条款有争议",
        ]
        for text in cases:
            skill_id = registry.match_skill(text)
            assert skill_id == "negotiation", f"'{text}' -> {skill_id}"

    def test_emotion_detection(self):
        registry = self._new_registry()
        cases = [
            "你根本就不爱我，否则怎么可能忘了纪念日",
            "没有她我真的活不下去了",
            "我老婆拿走了我的身份证",
            "孩子一直在哭，我快失控了",
            "我感觉自己像个透明人，消失了大家都会更高兴",
        ]
        for text in cases:
            skill_id = registry.match_skill(text)
            assert skill_id == "emotion", f"'{text}' -> {skill_id}"

    def test_empty_input(self):
        registry = self._new_registry()
        assert registry.match_skill("") is None

    def test_no_match(self):
        registry = self._new_registry()
        assert registry.match_skill("今天天气不错") is None

    def test_cross_scene_keywords(self):
        registry = self._new_registry()
        assert registry.match_skill("客户要签约了，但这个月业绩还差一单") == "sales"
        assert registry.match_skill("吵架后他摔门走了，我觉得心好痛") == "emotion"


class TestSkillRouting:
    @pytest.fixture
    def graph(self):
        return build_graph()

    def test_sales_routing(self, graph):
        ctx = Context(session_id="test-route-sales")
        result = graph.invoke({
            "context": ctx,
            "user_input": "客户一直拖着不签，月底了怎么办",
        })
        assert ctx.scene_config is not None
        assert ctx.scene_config.scene_id == "sales"
        assert result.get("output") is not None

    def test_management_routing(self, graph):
        ctx = Context(session_id="test-route-mgmt")
        result = graph.invoke({
            "context": ctx,
            "user_input": "下属绩效不达标，怎么跟他谈",
        })
        assert ctx.scene_config is not None
        assert ctx.scene_config.scene_id == "management"
        assert result.get("output") is not None

    def test_negotiation_routing(self, graph):
        ctx = Context(session_id="test-route-nego")
        result = graph.invoke({
            "context": ctx,
            "user_input": "谈判陷入僵局，对方不肯让步",
        })
        assert ctx.scene_config is not None
        assert ctx.scene_config.scene_id == "negotiation"
        assert result.get("output") is not None

    def test_emotion_routing(self, graph):
        ctx = Context(session_id="test-route-emotion")
        result = graph.invoke({
            "context": ctx,
            "user_input": "你根本就不爱我，否则怎么可能忘了我们的纪念日",
        })
        assert ctx.scene_config is not None
        assert ctx.scene_config.scene_id == "emotion"
        assert result.get("output") is not None

    def test_skills_loaded(self):
        expected = {"sales": 9, "management": 8, "negotiation": 16, "emotion": 12}
        for skill_id, goal_count in expected.items():
            config = load_scene_config(skill_id)
            assert config.scene_id == skill_id
            assert len(config.goal_taxonomy) == goal_count
