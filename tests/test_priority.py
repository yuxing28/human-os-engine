"""
Human-OS Engine - 测试：优先级规则
"""

import pytest
from modules.L1.priority_rules import get_priority
from graph.nodes.step4_priority import step4_priority
from schemas.user_state import (
    UserState, Emotion, Desires, Attention, Resistance, DualCore,
    EmotionType, AttentionHijacker, ResistanceType, DualCoreState
)
from schemas.context import Goal, GoalItem, Context


class TestPriorityRules:
    """优先级规则测试"""

    def test_energy_collapse(self):
        """测试能量崩溃（最高优先级）"""
        user = UserState(
            emotion=Emotion(type=EmotionType.FRUSTRATED, intensity=0.9),
            attention=Attention(focus=0.1),
            desires=Desires(fear=0.8),  # 即使有恐惧，崩溃仍优先
        )
        result = get_priority(user, Goal())
        assert result["priority_type"] == "energy_collapse"

    def test_attention_hijacked(self):
        """测试注意力被劫持"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
            attention=Attention(focus=0.2, hijacked_by=AttentionHijacker.FEAR),
        )
        result = get_priority(user, Goal())
        assert result["priority_type"] == "attention_hijacked"

    def test_resistance(self):
        """测试阻力浮现"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
            resistance=Resistance(type=ResistanceType.FEAR, intensity=0.8),
        )
        result = get_priority(user, Goal())
        assert result["priority_type"] == "resistance"

    def test_fear_by_desire(self):
        """测试恐惧（欲望权重触发）"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.5),
            desires=Desires(fear=0.8),
        )
        result = get_priority(user, Goal())
        assert result["priority_type"] == "fear"

    def test_fear_by_intensity(self):
        """测试恐惧（情绪强度触发）"""
        user = UserState(
            emotion=Emotion(type=EmotionType.FRUSTRATED, intensity=0.8),
            desires=Desires(),  # 恐惧权重低
        )
        result = get_priority(user, Goal())
        assert result["priority_type"] == "fear"

    def test_angry(self):
        """测试愤怒"""
        user = UserState(
            emotion=Emotion(type=EmotionType.ANGRY, intensity=0.7),
        )
        result = get_priority(user, Goal())
        assert result["priority_type"] == "anger_first"
        assert result["forced_weapon_type"] == "defensive"

    def test_impatient(self):
        """测试急躁"""
        user = UserState(
            emotion=Emotion(type=EmotionType.IMPATIENT, intensity=0.6),
        )
        result = get_priority(user, Goal())
        assert result["priority_type"] == "anger_first"
        assert result["forced_weapon_type"] == "defensive"

    def test_pride(self):
        """测试傲慢"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
            desires=Desires(pride=0.7),
        )
        result = get_priority(user, Goal())
        assert result["priority_type"] == "pride_first"
        assert result["forced_weapon_type"] == "defensive"

    def test_self_recovery_by_energy_pressure(self):
        """测试高能量压力优先回收"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.4),
            desires=Desires(fear=0.8),
        )
        result = get_priority(user, Goal(), self_stable=True, energy_pressure=0.85)
        assert result["priority_type"] == "self_recovery"

    def test_goal_realign(self):
        """测试目标漂移优先拉回"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.4),
            desires=Desires(greed=0.6),
        )
        goal = Goal()
        goal.current = GoalItem(description="推进客户成交", type="利益价值")
        goal.drift_detected = True
        result = get_priority(user, goal)
        assert result["priority_type"] == "goal_realign"

    def test_sloth(self):
        """测试懒惰"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
            desires=Desires(sloth=0.6),
        )
        result = get_priority(user, Goal())
        assert result["priority_type"] == "sloth"

    def test_dominant_desire(self):
        """测试主导欲望"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
            desires=Desires(greed=0.8, sloth=0.3),
        )
        result = get_priority(user, Goal())
        assert result["priority_type"] == "dominant_desire"
        assert result["details"]["desire"] == "greed"

    def test_none(self):
        """测试无特殊优先级"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
            desires=Desires(),
        )
        result = get_priority(user, Goal())
        assert result["priority_type"] == "none"

    def test_step4_node_should_read_energy_pressure_from_history(self):
        """测试 Step4 节点会接 Step3 的能量压力结果"""
        ctx = Context(session_id="priority-step4")
        ctx.user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.4),
            desires=Desires(fear=0.9),
        )
        ctx.add_history("user", "最近有点扛不住")
        ctx.history[-1].metadata["energy_pressure"] = 0.82

        result = step4_priority({"context": ctx, "user_input": "最近有点扛不住"})
        assert result["priority"]["priority_type"] == "self_recovery"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
