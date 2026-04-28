"""
Human-OS Engine - 测试：新增模块（L4 + L5）
"""

import pytest
import os
import json


# ===== 五感施加系统测试 =====

class TestSensoryApplication:
    """五感施加系统测试"""

    def test_apply_sensory_strategy_by_goal(self):
        """根据目标生成五感方案"""
        from modules.L4.sensory_application import apply_sensory_strategy

        actions = apply_sensory_strategy(goal="激发行动")
        assert len(actions) > 0
        # 激发行动应包含视觉"制造冲动"
        visual_actions = [a for a in actions if a.sense == "visual"]
        assert len(visual_actions) > 0

    def test_apply_sensory_strategy_by_field_setup(self):
        """根据预设场域生成方案"""
        from modules.L4.sensory_application import apply_sensory_strategy, FieldSetup

        field = FieldSetup(
            element="火",
            visual="暖光",
            audio="快节奏音乐",
            smell="温暖调香氛",
            touch="温暖材质",
            taste="热饮",
        )
        actions = apply_sensory_strategy(field_setup=field)
        assert len(actions) == 5

    def test_get_field_setup_by_element(self):
        """根据五行获取场域设计"""
        from modules.L4.sensory_application import get_field_setup_by_element

        fire = get_field_setup_by_element("火")
        assert fire.element == "火"
        assert "暖光" in fire.visual

        wood = get_field_setup_by_element("木")
        assert wood.element == "木"
        assert "绿色" in wood.visual

    def test_check_sensory_prerequisites(self):
        """检查前提条件"""
        from modules.L4.sensory_application import check_sensory_prerequisites

        result = check_sensory_prerequisites()
        assert result["can_apply"] is False  # 线上场景默认不满足

    def test_five_elements_map_complete(self):
        """五行映射完整性"""
        from modules.L4.sensory_application import FIVE_ELEMENTS_MAP

        assert len(FIVE_ELEMENTS_MAP) == 5
        for element in ["火", "水", "土", "金", "木"]:
            assert element in FIVE_ELEMENTS_MAP
            config = FIVE_ELEMENTS_MAP[element]
            assert "visual" in config
            assert "audio" in config


# ===== 表达辩证测试 =====

class TestExpressionDialectics:
    """表达辩证与群体逻辑测试"""

    def test_select_expression_mode_high_emotion(self):
        """高情绪 → 情绪模式"""
        from modules.L4.expression_dialectics import select_expression_mode

        mode = select_expression_mode({
            "emotion_type": "愤怒",
            "emotion_intensity": 0.8,
            "dominant_desire": "wrath",
        })
        assert mode == "情绪模式"

    def test_select_expression_mode_consultation(self):
        """问题咨询 → 逻辑模式"""
        from modules.L4.expression_dialectics import select_expression_mode

        mode = select_expression_mode({
            "emotion_type": "平静",
            "emotion_intensity": 0.3,
            "dominant_desire": "greed",
        }, input_type="问题咨询")
        assert mode == "逻辑模式"

    def test_select_expression_mode_scenario(self):
        """场景描述 → 人际模式"""
        from modules.L4.expression_dialectics import select_expression_mode

        mode = select_expression_mode({
            "emotion_type": "平静",
            "emotion_intensity": 0.5,
            "dominant_desire": "pride",
        }, input_type="场景描述")
        assert mode == "人际模式"

    def test_mode_transition_negative(self):
        """负面反馈 → 更温和的模式"""
        from modules.L4.expression_dialectics import get_mode_transition

        next_mode = get_mode_transition("逻辑模式", "negative")
        assert next_mode in ("人际模式", "情绪模式")

    def test_mode_transition_positive(self):
        """正面反馈 → 更理性的模式"""
        from modules.L4.expression_dialectics import get_mode_transition

        next_mode = get_mode_transition("情绪模式", "positive")
        assert next_mode in ("人际模式", "逻辑模式")

    def test_get_layer_adjustment(self):
        """获取五层调整"""
        from modules.L4.expression_dialectics import get_layer_adjustment

        adj = get_layer_adjustment("逻辑模式")
        assert 2 in adj["emphasis"]  # 强调 L2
        assert 3 in adj["weaken"]  # 弱化 L3

    def test_build_order_framework(self):
        """构建 ORDER 框架"""
        from modules.L4.expression_dialectics import build_order_framework

        result = build_order_framework(
            goal="提升团队效率",
            shared_interest="大家都轻松",
        )
        assert "提升团队效率" in result
        assert "大家都轻松" in result

    def test_build_group_mobilization(self):
        """群体动员策略"""
        from modules.L4.expression_dialectics import build_group_mobilization

        strategy = build_group_mobilization("情绪模式", "large")
        assert strategy["focus"] == "集体行动"
        assert strategy["tone"] == "感染力、共情、故事化"


# ===== 场域判断与质量检查测试 =====

class TestFieldQuality:
    """场域判断与质量检查测试"""

    def test_assess_field_online(self):
        """线上场景不应用场域"""
        from modules.L4.field_quality import assess_field

        result = assess_field()
        assert result.can_apply_field is False

    def test_assess_field_recommends_element(self):
        """根据策略推断五行属性"""
        from modules.L4.field_quality import assess_field
        from types import SimpleNamespace

        strategy = SimpleNamespace(stage="钩子", mode="B")
        result = assess_field(strategy_plan=strategy)
        assert result.recommended_element == "火"

    def test_quality_check_pass(self):
        """合规输出通过检查"""
        from modules.L4.field_quality import quality_check

        result = quality_check("好的，我帮你看看这个问题。")
        assert result.passed is True
        assert result.score >= 90

    def test_quality_check_forbidden_words(self):
        """禁用词汇检测"""
        from modules.L4.field_quality import quality_check

        result = quality_check("利用你的恐惧来推动决策")
        assert result.passed is False
        assert any("利用" in item for item in result.failed_items)

    def test_quality_check_internal_terms(self):
        """框架泄露检测"""
        from modules.L4.field_quality import quality_check

        result = quality_check("根据五层结构，第一层是共情")
        assert result.passed is False
        assert any("五层结构" in item for item in result.failed_items)

    def test_quality_check_customer_service(self):
        """客服词汇检测"""
        from modules.L4.field_quality import quality_check

        result = quality_check("亲，小助手为您服务")
        assert result.passed is False

    def test_quality_check_ai_neologisms(self):
        """AI 新造词检测"""
        from modules.L4.field_quality import quality_check

        result = quality_check("这是你的注意力黑洞")
        assert len(result.warnings) > 0

    def test_quality_check_empty_output(self):
        """空输出检测"""
        from modules.L4.field_quality import quality_check

        result = quality_check("")
        assert result.passed is False
        assert result.score <= 50


# ===== 离线评估器测试 =====

class TestEvaluator:
    """离线评估器测试"""

    def test_evaluate_response_good(self):
        """高质量回复评分"""
        from modules.L5.evaluator import evaluate_response
        from schemas.context import Context
        from schemas.user_state import UserState, Emotion, Desires

        ctx = Context(session_id="test")
        ctx.user.emotion = Emotion(type="挫败", intensity=0.6)
        ctx.user.desires = Desires(fear=0.7, greed=0.3)

        result = evaluate_response(ctx, "这确实不容易。很多人都会遇到类似的情况。你可以先从最简单的步骤开始试试，要不要我帮你拆解一下？")

        assert result.total_score > 60
        assert result.expression_normativity >= 15

    def test_evaluate_response_bad(self):
        """低质量回复评分"""
        from modules.L5.evaluator import evaluate_response
        from schemas.context import Context

        ctx = Context(session_id="test")

        result = evaluate_response(ctx, "利用你的恐惧和贪婪，我设计了钩子来操控你")

        assert result.total_score < 70
        assert len(result.issues) > 0

    def test_record_strategy_persistence(self):
        """策略持久化"""
        from modules.L5.evaluator import (
            StrategyRecord, record_effective_strategy, record_counter_example,
            STRATEGY_LIBRARY_PATH, COUNTER_EXAMPLES_PATH, get_strategy_stats,
            _ensure_data_dir, _load_json, _save_json,
        )

        # 清理测试数据
        for path in [STRATEGY_LIBRARY_PATH, COUNTER_EXAMPLES_PATH]:
            if os.path.exists(path):
                os.remove(path)

        record = StrategyRecord(
            strategy_name="钩子",
            mode="B",
            stage="钩子",
            context_summary="测试",
            output="测试输出",
            feedback="positive",
            score=80.0,
        )

        record_effective_strategy(record)

        assert os.path.exists(STRATEGY_LIBRARY_PATH)
        data = _load_json(STRATEGY_LIBRARY_PATH)
        assert len(data) > 0

        # 清理
        os.remove(STRATEGY_LIBRARY_PATH)

    def test_counter_example_persistence(self):
        """反例持久化"""
        from modules.L5.evaluator import (
            StrategyRecord, record_counter_example,
            COUNTER_EXAMPLES_PATH, _load_json,
        )

        # 清理
        if os.path.exists(COUNTER_EXAMPLES_PATH):
            os.remove(COUNTER_EXAMPLES_PATH)

        record = StrategyRecord(
            strategy_name="钩子",
            mode="B",
            stage="钩子",
            context_summary="测试",
            output="测试输出",
            feedback="negative",
            score=30.0,
        )

        record_counter_example(record)

        assert os.path.exists(COUNTER_EXAMPLES_PATH)
        data = _load_json(COUNTER_EXAMPLES_PATH)
        assert len(data) > 0

        # 清理
        os.remove(COUNTER_EXAMPLES_PATH)

    def test_get_strategy_stats_empty(self):
        """空策略库统计"""
        from modules.L5.evaluator import get_strategy_stats

        stats = get_strategy_stats()
        assert "total_effective" in stats
        assert "total_counter" in stats

    def test_evaluate_response_handles_mode_enum_values(self):
        from modules.L5.evaluator import evaluate_response
        from schemas.context import Context
        from schemas.enums import Mode

        ctx = Context(session_id="enum-test")
        ctx.current_strategy.mode_sequence = [Mode.A]

        result = evaluate_response(ctx, "现在就成交购买吧")
        assert any("Mode A（稳定自身）不应直接推动成交" in item for item in result.issues)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
