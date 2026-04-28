"""
Step 6 路由层定向测试。
"""

from types import SimpleNamespace

from graph.nodes.step6_strategy import _prioritize_action_steps, step6_strategy_generation
from modules.L5.knowledge_router import query_knowledge, match_case_detail
from schemas.context import Context, GoalItem
from schemas.enums import EmotionType, InputType, ResistanceType
from schemas.user_state import Emotion, Desires, Resistance


def _base_state(ctx: Context, user_input: str, selected_mode: str = "B"):
    return {
        "context": ctx,
        "user_input": user_input,
        "selected_mode": selected_mode,
        "priority": {"priority_type": "none"},
    }


def test_query_knowledge_should_route_business_consultation_to_marketing_module():
    result = query_knowledge(
        "客户转化率一直上不去，成交也卡住了，怎么优化？",
        input_type="问题咨询",
        goal_type="利益价值",
        scene_id="sales",
    )

    assert result is not None
    assert "人性营销模块" in result.module_name
    assert "转化" in result.title or "成交" in result.content


def test_prioritize_action_steps_should_put_sales_relevant_action_first():
    steps = [
        "先稳定情绪再看问题",
        "展示从众和真实案例",
        "重新做价格锚定",
    ]

    ranked = _prioritize_action_steps(
        steps=steps,
        user_input="客户转化率一直很差，成交推进不动，我现在最想先把签单这件事往前推",
        goal_type="利益价值",
        emotion_type="平静",
    )

    assert ranked[0] in {"展示从众和真实案例", "重新做价格锚定"}


def test_step6_problem_consultation_should_build_action_playbook_from_knowledge():
    ctx = Context(session_id="step6-problem-playbook")
    ctx.user.input_type = InputType.CONSULTATION
    ctx.goal.current = GoalItem(type="利益价值")
    ctx.scene_config = SimpleNamespace(scene_id="sales")

    result = step6_strategy_generation(
        _base_state(ctx, "客户转化率一直上不去，成交卡住了，应该先从哪里下手？", selected_mode="B")
    )

    plan = result["strategy_plan"]
    assert plan is not None
    assert plan.stage == "知识"
    assert "当前更适合的做法：" in plan.description
    assert any(token in plan.description for token in ["先", "再", "最后"])


def test_step6_should_carry_goal_and_state_focus_into_playbook():
    ctx = Context(session_id="step6-alignment")
    ctx.user.input_type = InputType.CONSULTATION
    ctx.goal.current = GoalItem(description="推进客户成交", type="利益价值")
    ctx.scene_config = SimpleNamespace(scene_id="sales")
    ctx.unified_context = """【用户画像】
职业: 运营
【相关记忆】
偏好记忆: 用户习惯先听结论
经验记忆: 上次先收口更顺"""
    ctx.add_history("user", "客户一直拖着不签")
    ctx.history[-1].metadata["state_trend"] = "worsening"
    ctx.history[-1].metadata["collapse_stage"] = "outer_damage"
    ctx.history[-1].metadata["recovery_focus"] = "先把边界和过滤能力补回来"

    result = step6_strategy_generation(
        _base_state(ctx, "客户一直拖着不签，我想先把成交往前推", selected_mode="B")
    )

    plan = result["strategy_plan"]
    assert plan is not None
    assert "当前目标：推进客户成交" in plan.description
    assert "当前重点：先把边界和过滤能力补回来" in plan.description
    assert "先别做：" in plan.description
    assert "记忆提示：" in plan.description
    assert "经验决策提示：" in plan.description
    assert "偏好记忆: 用户习惯先听结论" in plan.description
    assert "经验记忆: 上次先收口更顺" in plan.description


def test_step6_should_prioritize_decision_experience_hint_for_progress_input():
    ctx = Context(session_id="step6-progress-priority")
    ctx.user.input_type = InputType.CONSULTATION
    ctx.goal.current = GoalItem(description="推进客户成交", type="利益价值")
    ctx.scene_config = SimpleNamespace(scene_id="sales")
    ctx.unified_context = """【用户画像】
职业: 运营
【相关记忆】
对话记忆: 我们上轮聊了很多背景
决策记忆: 上轮决定先收口再推进
经验记忆: 失败经验: 上次直接强推导致对抗升级，先别急着压结果
【经验索引】
- 失败避坑: 失败经验: 场景=sales | 失败码=F03 | 先别急着压结果
- 决策线索: 上轮决定先收口再推进
【经验提示】
1. 先对齐目标
2. 再推进动作"""

    result = step6_strategy_generation(
        _base_state(ctx, "客户一直拖着不签，我下一步到底先做什么？", selected_mode="B")
    )
    plan = result["strategy_plan"]
    assert plan is not None
    assert "经验决策提示：" in plan.description
    assert "经验索引提示：" in plan.description
    assert "记忆提示：" in plan.description
    assert "失败规避提示：" in plan.description
    assert plan.description.index("失败规避提示：") < plan.description.index("经验决策提示：")
    assert plan.description.index("失败规避提示：") < plan.description.index("经验索引提示：")
    assert plan.description.index("经验索引提示：") < plan.description.index("经验决策提示：")
    assert plan.description.index("经验决策提示：") < plan.description.index("记忆提示：")
    assert "决策记忆: 上轮决定先收口再推进" in plan.description


def test_match_case_detail_should_hit_intimate_conflict_case():
    ctx = Context(session_id="step6-case-detail")
    ctx.goal.current = GoalItem(type="情绪价值")
    ctx.user.emotion = Emotion(type=EmotionType.ANGRY, intensity=0.86)
    ctx.user.desires = Desires(wrath=0.9, fear=0.6)
    ctx.user.resistance = Resistance(type=ResistanceType.WRATH, intensity=0.8)

    result = match_case_detail("我和老婆又吵起来了，现在两个人都在翻旧账", context=ctx)

    assert result is not None
    assert result.title == "亲密关系：终止争吵"
    assert "先处理情绪，再处理问题" in result.content


def test_step6_scenario_path_should_use_real_case_content():
    ctx = Context(session_id="step6-scenario")
    ctx.user.input_type = InputType.SCENARIO
    ctx.goal.current = GoalItem(type="情绪价值")
    ctx.user.emotion = Emotion(type=EmotionType.ANGRY, intensity=0.82)
    ctx.user.desires = Desires(wrath=0.9, fear=0.4)
    ctx.user.resistance = Resistance(type=ResistanceType.WRATH, intensity=0.7)

    result = step6_strategy_generation(
        _base_state(ctx, "我和老婆这两天一直吵架，已经开始翻旧账了", selected_mode="C")
    )

    plan = result["strategy_plan"]
    assert plan is not None
    assert plan.stage == "案例"
    assert plan.combo_name == "亲密关系：终止争吵"
    assert "核心目的：" in plan.description
    assert "连招主线：" in plan.description
    assert "先处理情绪，再处理问题" in plan.description
    assert "亲密关系：终止争吵" in result["context"].knowledge_refs


def test_step6_mixed_path_should_attach_business_knowledge():
    ctx = Context(session_id="step6-mixed")
    ctx.user.input_type = InputType.MIXED
    ctx.goal.current = GoalItem(type="利益价值")
    ctx.user.emotion = Emotion(type=EmotionType.FRUSTRATED, intensity=0.62)
    ctx.user.desires = Desires(greed=0.8, fear=0.5)
    ctx.scene_config = SimpleNamespace(scene_id="sales")

    result = step6_strategy_generation(
        _base_state(ctx, "我现在很烦，客户一直不成交，转化率也很差，到底怎么推进？", selected_mode="B")
    )

    plan = result["strategy_plan"]
    assert plan is not None
    assert plan.stage == "混合"
    assert "知识参考《" in plan.description
    assert "当前更适合的做法：" in plan.description
    assert any("人性营销模块" in ref for ref in result["context"].knowledge_refs)


def test_step6_mixed_path_should_attach_case_playbook_when_case_exists():
    ctx = Context(session_id="step6-mixed-case")
    ctx.user.input_type = InputType.MIXED
    ctx.goal.current = GoalItem(type="情绪价值")
    ctx.user.emotion = Emotion(type=EmotionType.ANGRY, intensity=0.88)
    ctx.user.desires = Desires(wrath=0.9, fear=0.6)
    ctx.user.resistance = Resistance(type=ResistanceType.WRATH, intensity=0.8)

    result = step6_strategy_generation(
        _base_state(ctx, "我现在很炸，我和老婆又吵起来了，她一说我我就更想顶回去，到底怎么收住？", selected_mode="C")
    )

    plan = result["strategy_plan"]
    assert plan is not None
    assert plan.stage == "混合"
    assert "案例参考《亲密关系：终止争吵》" in plan.description
    assert "核心目的：" in plan.description
    assert "连招主线：" in plan.description


def test_step6_should_output_strategy_skeleton_for_next_steps():
    ctx = Context(session_id="step6-skeleton")
    ctx.user.input_type = InputType.MIXED
    ctx.user.emotion = Emotion(type=EmotionType.ANGRY, intensity=0.86)
    ctx.goal.current = GoalItem(type="情绪价值")
    ctx.self_check.push_risk = "high"
    ctx.self_check.repair_need = True

    result = step6_strategy_generation(
        _base_state(ctx, "我现在很炸，越聊越顶", selected_mode="A")
    )

    skeleton = result["context"].current_strategy.skeleton
    assert len(skeleton.do_now) > 0
    assert len(skeleton.avoid_now) > 0
    assert skeleton.fallback_move != ""
    assert "不要强推结果" in skeleton.avoid_now


def test_step6_skeleton_should_inject_failure_code_avoid_actions_from_memory():
    ctx = Context(session_id="step6-failure-avoid-map")
    ctx.user.input_type = InputType.CONSULTATION
    ctx.goal.current = GoalItem(type="利益价值")
    ctx.scene_config = SimpleNamespace(scene_id="sales")
    ctx.unified_context = """【相关记忆】
经验记忆: 失败经验: 场景=sales | 失败码=F02 | 先别急着压结果
经验记忆: 失败经验: 场景=sales | 失败码=F03 | 关系脆弱时先承接"""

    result = step6_strategy_generation(
        _base_state(ctx, "客户说回去汇报，我下一步该怎么推进？", selected_mode="B")
    )
    skeleton = result["context"].current_strategy.skeleton
    skeleton_payload = result["strategy_skeleton"]

    assert any("不要推进过早" in item for item in skeleton.avoid_now)
    assert any("不要跳过承接修复" in item for item in skeleton.avoid_now)
    assert skeleton_payload["failure_avoid_codes"] == ["F02", "F03"]
