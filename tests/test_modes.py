"""
Human-OS Engine - 测试：运作模式选择
"""

import pytest
from modules.L1.operation_modes import select_mode
from graph.nodes.step5_mode import step5_mode_selection
from schemas.user_state import (
    UserState, Emotion, Desires, Attention, Resistance, DualCore,
    EmotionType, AttentionHijacker, ResistanceType, DualCoreState, MotiveType
)
from schemas.context import Goal, GoalItem, Context
from schemas.enums import InputType, Mode, TrustLevel


class TestModeSelection:
    """模式选择测试"""

    def test_self_unstable(self):
        """测试自身不稳定"""
        mode = select_mode(
            self_stable=False,
            user=UserState(),
            goal=Goal(),
        )
        assert mode == "A"

    def test_attention_hijacked(self):
        """测试注意力被劫持"""
        user = UserState(
            attention=Attention(focus=0.2, hijacked_by=AttentionHijacker.FEAR),
        )
        mode = select_mode(True, user, Goal())
        assert mode == "A"

    def test_resistance_fear(self):
        """测试阻力-恐惧"""
        user = UserState(
            resistance=Resistance(type=ResistanceType.FEAR, intensity=0.8),
        )
        mode = select_mode(True, user, Goal())
        assert mode == "A"

    def test_resistance_sloth(self):
        """测试阻力-懒惰"""
        user = UserState(
            resistance=Resistance(type=ResistanceType.SLOTH, intensity=0.8),
        )
        mode = select_mode(True, user, Goal())
        assert mode == "B"

    def test_resistance_pride_emotion_goal(self):
        """测试阻力-傲慢+情绪价值目标"""
        user = UserState(
            resistance=Resistance(type=ResistanceType.PRIDE, intensity=0.8),
        )
        goal = Goal(current=GoalItem(type="情绪价值"))
        mode = select_mode(True, user, goal)
        assert mode == "C"

    def test_resistance_pride_benefit_goal(self):
        """测试阻力-傲慢+利益价值目标"""
        user = UserState(
            resistance=Resistance(type=ResistanceType.PRIDE, intensity=0.8),
        )
        goal = Goal(current=GoalItem(type="利益价值"))
        mode = select_mode(True, user, goal)
        assert mode == "B"

    def test_dual_core_conflict(self):
        """测试双核对抗"""
        user = UserState(
            dual_core=DualCore(state=DualCoreState.CONFLICT),
        )
        mode = select_mode(True, user, Goal())
        assert mode == "A"

    def test_high_emotion(self):
        """测试情绪过载"""
        user = UserState(
            emotion=Emotion(type=EmotionType.ANGRY, intensity=0.8),
        )
        mode = select_mode(True, user, Goal())
        assert mode == "A"

    def test_benefit_low_emotion(self):
        """测试利益价值+情绪平稳"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
        )
        goal = Goal(current=GoalItem(type="利益价值"))
        mode = select_mode(True, user, goal)
        assert mode == "B"

    def test_emotion_value_upgrade(self):
        """测试情绪价值+升维条件满足"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.4),
            motive=MotiveType.LIFE_EXPECTATION,
        )
        goal = Goal(current=GoalItem(type="情绪价值"))
        mode = select_mode(True, user, goal)
        assert mode == "C"

    def test_emotion_value_no_upgrade(self):
        """测试情绪价值+升维条件不满足（情绪过载）"""
        user = UserState(
            emotion=Emotion(type=EmotionType.FRUSTRATED, intensity=0.7),
            motive=MotiveType.LIFE_EXPECTATION,
        )
        goal = Goal(current=GoalItem(type="情绪价值"))
        mode = select_mode(True, user, goal)
        assert mode == "A"

    def test_emotion_value_stress_passive(self):
        """测试情绪价值+压力被动（无反思意愿）"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.4),
            motive=MotiveType.STRESS_PASSIVE,
        )
        goal = Goal(current=GoalItem(type="情绪价值"))
        mode = select_mode(True, user, goal)
        assert mode == "A"

    def test_greed_pride_mix(self):
        """测试贪婪+傲慢混合"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
            desires=Desires(greed=0.7, pride=0.6),
        )
        mode = select_mode(True, user, Goal())
        assert mode == "A+B"

    def test_greed_emotion_value(self):
        """测试贪婪+情绪价值"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
            desires=Desires(greed=0.7),
        )
        goal = Goal(current=GoalItem(type="情绪价值"))
        mode = select_mode(True, user, goal)
        assert mode == "B→C"

    def test_default_b(self):
        """测试默认 Mode B"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
            desires=Desires(),
        )
        mode = select_mode(True, user, Goal())
        assert mode == "B"

    def test_priority_self_recovery_forces_mode_a(self):
        """测试自我回收优先级强制 A"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.4),
            desires=Desires(greed=0.8),
        )
        mode = select_mode(
            True,
            user,
            Goal(),
            priority={"priority_type": "self_recovery"},
            input_type="问题咨询",
        )
        assert mode == "A"

    def test_priority_pride_first_emotion_goal_goes_c(self):
        """测试傲慢优先在情绪目标下走 C"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.4),
            desires=Desires(pride=0.8),
        )
        goal = Goal(current=GoalItem(type="情绪价值"))
        mode = select_mode(
            True,
            user,
            goal,
            priority={"priority_type": "pride_first"},
            input_type="场景描述",
        )
        assert mode == "C"

    def test_priority_goal_realign_forces_mode_a(self):
        """测试目标拉回优先时先走 A"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.3),
            desires=Desires(greed=0.7),
        )
        goal = Goal(current=GoalItem(type="利益价值"))
        mode = select_mode(
            True,
            user,
            goal,
            priority={"priority_type": "goal_realign"},
            input_type="混合",
        )
        assert mode == "A"

    def test_consultation_mixed_goal_can_go_b_to_c(self):
        """测试咨询型混合目标可走 B→C"""
        user = UserState(
            emotion=Emotion(type=EmotionType.CALM, intensity=0.35),
            motive=MotiveType.LIFE_EXPECTATION,
            trust_level=TrustLevel.MEDIUM,
        )
        goal = Goal(current=GoalItem(type="混合"))
        mode = select_mode(
            True,
            user,
            goal,
            priority={"priority_type": "none"},
            input_type="问题咨询",
        )
        assert mode == "B→C"

    def test_step5_node_should_sync_energy_mode_and_sequence(self):
        """测试 Step5 节点会同步更新 energy_mode 和 mode_sequence"""
        ctx = Context(session_id="mode-step5")
        ctx.user.input_type = InputType.CONSULTATION
        ctx.user.emotion = Emotion(type=EmotionType.CALM, intensity=0.35)
        ctx.user.motive = MotiveType.LIFE_EXPECTATION
        ctx.user.trust_level = TrustLevel.MEDIUM
        ctx.goal.current = GoalItem(type="混合")

        result = step5_mode_selection({
            "context": ctx,
            "user_input": "我想系统梳理一下这件事",
            "priority": {"priority_type": "none"},
        })

        assert result["selected_mode"] == "B→C"
        assert result["context"].self_state.energy_mode == Mode.B
        assert result["context"].current_strategy.mode_sequence == [Mode.B, Mode.C]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
