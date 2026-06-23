from graph.nodes.step8_execution import step8_execution
from schemas.context import Context
from types import SimpleNamespace


def _state_for_quick_path(session_id: str, scene: str, output: str, user_input: str):
    context = Context(session_id=session_id)
    context.primary_scene = scene
    context.output = output
    return {
        "context": context,
        "user_input": user_input,
        "skip_to_end": True,
        "weapons_used": [],
        "priority": {},
    }


def test_step8_should_stabilize_management_self_doubt_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-management-self-doubt",
        scene="management",
        output="先说重点。",
        user_input="我觉得自己不适合这份工作",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "不适合" in output
    assert "不努力" in output
    assert "最卡的一件事" in output


def test_step8_should_stabilize_emotion_somatic_stress_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-emotion-somatic",
        scene="emotion",
        output="先说重点。",
        user_input="我看着电脑就想吐，但我没法辞职",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "身体已经在拉警报" in output
    assert "先不谈辞职" in output
    assert "小止损" in output


def test_step8_should_stabilize_sales_price_objection_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-sales-price-objection",
        scene="sales",
        output="先说重点。",
        user_input="你们的价格太贵了，竞品便宜30%",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "便宜 30%" in output
    assert "总账算清" in output
    assert "10 分钟对比" in output


def test_step8_should_stabilize_sales_delay_even_when_scene_is_management():
    state = _state_for_quick_path(
        session_id="step8-sales-delay-management-route",
        scene="management",
        output="先说重点。",
        user_input="我需要跟老板汇报，让我等消息",
    )
    result = step8_execution(state)
    output = result["output"]
    # 这里看“是否命中汇报稳态语义”，不把一句固定文案写死。
    assert ("先不用急着给我结论" in output) or ("先准备一版一页纸" in output)
    assert ("三个点" in output) or ("四件事" in output)
    assert ("30 秒" in output) or ("拍板" in output)


def test_step8_should_prefer_negotiation_next_step_template_when_config_is_negotiation():
    context = Context(session_id="step8-negotiation-template-resolve")
    context.primary_scene = "sales"
    context.secondary_scenes = ["negotiation"]
    context.scene_config = SimpleNamespace(scene_id="negotiation")
    context.output = "先说重点。"
    state = {
        "context": context,
        "user_input": "好的，我明白了。那接下来呢？",
        "skip_to_end": True,
        "weapons_used": [],
        "priority": {},
    }
    result = step8_execution(state)
    output = result["output"]
    assert "最容易谈拢的点" in output or "最容易达成一致的点" in output
    assert "回看时间" in output or "确认窗口" in output
    assert "不会回到空转" in output


def test_step8_should_stabilize_management_overload_complaint_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-management-overload",
        scene="management",
        output="先说重点。",
        user_input="为什么总是给我安排这么多任务？",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "压力已经超线" in output
    assert "最占你精力的三件事" in output
    assert "必须今天做" in output


def test_step8_should_keep_good_management_overload_output_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-management-overload-keep",
        scene="management",
        output="压力已经超线了，我先接住你。现在最占你精力的三件事是 A、B、C，今天先划开必须今天做和可以后放的边界。",
        user_input="为什么总是给我安排这么多任务？",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "最占你精力的三件事" in output
    assert "必须今天做" in output
    assert "可以后放" in output


def test_step8_should_not_override_negotiation_next_step_with_ack_template():
    context = Context(session_id="step8-negotiation-next-step-priority")
    context.primary_scene = "negotiation"
    context.output = "先说重点。"
    state = {
        "context": context,
        "user_input": "好的，我明白了。那接下来呢？",
        "skip_to_end": True,
        "weapons_used": [],
        "priority": {},
    }
    result = step8_execution(state)
    output = result["output"]
    assert "最容易谈拢的点" in output or "最容易达成一致的点" in output
    assert "交付边界" in output or "价格区间" in output or "交换条件" in output


def test_step8_should_stabilize_sales_switch_defense_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-sales-switch-defense",
        scene="sales",
        output="先说重点。",
        user_input="我现在用的系统挺好的，为什么要换？",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "先不谈“全面替换”" in output
    assert "7 天并行对比" in output
    assert "处理时长" in output


def test_step8_should_stabilize_sales_soft_agreement_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-sales-soft-agreement",
        scene="sales",
        output="先说重点。",
        user_input="有道理，我确实是这样想的。",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "已经有共识" in output
    assert "1 个最担心点" in output
    assert "明天这个时间" in output


def test_step8_should_keep_good_sales_price_output_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-sales-price-keep",
        scene="sales",
        output="竞品便宜 30% 这个点，我理解你为什么会先卡住。我们先不急着比采购单价，先把总账算清。",
        user_input="你们的价格太贵了，竞品便宜30%",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "总账算清" in output
    assert "10 分钟对比" not in output or "总成本" in output


def test_step8_should_keep_good_sales_soft_agreement_output_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-sales-soft-agreement-keep",
        scene="sales",
        output="我们已经有共识了，你先给我 1 个最担心点和 1 个最想看到的结果。",
        user_input="有道理，我确实是这样想的。",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "最担心点" in output
    assert "最想看到的结果" in output


def test_step8_should_stabilize_negotiation_long_payment_term_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-negotiation-long-payment",
        scene="negotiation",
        output="先说重点。",
        user_input="我们需要 90 天账期，否则不签",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "交换式谈法" in output
    assert "60 天" in output
    assert "条款草案对齐" in output


def test_step8_should_stabilize_management_atmosphere_decline_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-management-atmosphere-decline",
        scene="management",
        output="先说重点。",
        user_input="我觉得团队氛围越来越差了",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "最近一周里" in output
    assert "发生了什么、影响了谁" in output
    assert "今天就能去对齐" in output


def test_step8_should_keep_good_management_atmosphere_output_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-management-atmosphere-decline-keep",
        scene="management",
        output="最近一周里最典型的一次协作里，发生了什么、影响了谁、你希望怎么变，我们今天就能去对齐。",
        user_input="我觉得团队氛围越来越差了",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "最近一周里" in output
    assert "发生了什么、影响了谁" in output
    assert "今天就能去对齐" in output


def test_step8_should_stabilize_management_next_step_execution_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-management-next-step-execution",
        scene="management",
        output="先说重点。",
        user_input="好的，我明白了。那接下来呢？",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "24小时内能完成的小动作" in output or "24小时内" in output
    assert "回看时间" in output
    assert "30 分钟可完成的小动作" in output or "24小时内能完成的小动作" in output
    assert "谁负责" in output or "责任人" in output


def test_step8_should_keep_good_management_next_step_output_on_quick_path():
    state = _state_for_quick_path(
        session_id="step8-management-next-step-execution-keep",
        scene="management",
        output="今天先把最卡的一件事变成一个 30 分钟可完成的小动作，明天固定一个回看时间，只复盘做了什么、卡在哪、下一步谁负责。",
        user_input="好的，我明白了。那接下来呢？",
    )
    result = step8_execution(state)
    output = result["output"]
    assert "30 分钟可完成的小动作" in output
    assert "回看时间" in output
    assert "下一步谁负责" in output


def test_step8_should_skip_scene_specific_repair_when_output_is_already_concrete(monkeypatch):
    import importlib

    step8_module = importlib.import_module("graph.nodes.step8_execution")
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "我们先别把盘子一下铺太大，今天先挑一件能推进的小事，把负责人和回看时间一起定住。",
    )
    monkeypatch.setattr(
        field_quality,
        "assess_field",
        lambda **kwargs: SimpleNamespace(can_apply_field=False),
    )
    monkeypatch.setattr(
        memory_module,
        "get_memory_manager",
        lambda: SimpleNamespace(get_unified_context=lambda **kwargs: ""),
    )
    monkeypatch.setattr(
        step8_module,
        "_apply_scene_specific_stabilizers",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("scene-specific repair should have been skipped")),
    )

    ctx = Context(session_id="step8-management-skip-scene-repair")
    ctx.primary_scene = "management"
    state = {
        "context": ctx,
        "user_input": "好的，那接下来呢？",
        "strategy_plan": SimpleNamespace(
            mode="B",
            combo_name="管理推进",
            stage="知识",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "聚焦", "type": "直接型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "今天先挑一件能推进的小事" in output
    assert "负责人和回看时间" in output
