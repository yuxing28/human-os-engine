"""
Step 8 输出层定向测试。
"""

from types import SimpleNamespace

from graph.nodes.step8_execution import _guard_optional_product_extension_output, step8_execution
from graph.nodes.style_adapter import _build_narrative_profile, _build_output_profile, _shape_output_rhythm, _trim_to_output_profile
from modules.L4.conversion_rules import convert_to_output
from prompts.speech_generator import build_speech_prompt
from schemas.context import Context
from schemas.user_state import EmotionType
from schemas.strategy import StrategyPlan


def test_convert_to_output_should_strip_visible_packaging_labels():
    raw = (
        "表达模式：逻辑模式。先说重点。"
        "\n知识参考《提高转化率：七大认知偏差》：这里是一段内部参考。"
        "\n案例参考《亲密关系：终止争吵》：这里是一段案例。"
        "\n[环境建议] visual: 暖光"
    )

    converted, _ = convert_to_output(raw)

    assert "表达模式" not in converted
    assert "知识参考" not in converted
    assert "案例参考" not in converted
    assert "环境建议" not in converted
    assert "先说重点" in converted


def test_optional_product_extension_should_not_keep_unsupported_specific_claims():
    output = "可以强调我们的服务支持是7x24小时专属技术顾问，这在行业里是不多见的。"

    guarded = _guard_optional_product_extension_output(
        output,
        user_input="客户觉得价格高，怎么讲价值？",
        skill_prompt="【雷军产品扩展禁区】",
    )

    assert "7x24" not in guarded
    assert "专属技术顾问" not in guarded
    assert "先把价值讲实" in guarded


def test_step8_should_only_return_visible_final_message(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.L4.sensory_application as sensory_application
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: (
            "先说重点：我们先把最关键的问题抓住。"
            "\n知识参考《提高转化率：七大认知偏差》：内部知识"
            "\n案例参考《商业谈判：扭转劣势》：内部案例"
        ),
    )
    monkeypatch.setattr(
        field_quality,
        "assess_field",
        lambda **kwargs: SimpleNamespace(can_apply_field=True),
    )
    monkeypatch.setattr(
        sensory_application,
        "apply_sensory_strategy",
        lambda **kwargs: [SimpleNamespace(sense="visual", method="暖光")],
    )
    monkeypatch.setattr(
        memory_module,
        "get_memory_manager",
        lambda: SimpleNamespace(get_unified_context=lambda **kwargs: ""),
    )

    ctx = Context(session_id="step8-visible")
    state = {
        "context": ctx,
        "user_input": "客户一直拖着不签，我该怎么推进？",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="知识咨询",
            stage="知识",
            description="知识参考《提高转化率：七大认知偏差》：内部知识",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "先说重点" in output
    assert "知识参考" not in output
    assert "案例参考" not in output
    assert "环境建议" not in output


def test_step8_should_use_fast_speech_generator_in_sandbox_session(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    def _should_not_call_generate_speech(**kwargs):
        raise AssertionError("sandbox session should use generate_speech_fast")

    monkeypatch.setattr(speech_generator, "generate_speech", _should_not_call_generate_speech)
    monkeypatch.setattr(
        speech_generator,
        "generate_speech_fast",
        lambda **kwargs: "sandbox fast output",
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

    ctx = Context(session_id="sandbox-mt-sales-123")
    state = {
        "context": ctx,
        "user_input": "客户一直拖着不签，我该怎么推进？",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="知识咨询",
            stage="知识",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    assert "sandbox fast output" in result["output"]


def test_step8_should_soften_structured_scaffolding_into_human_language(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: (
            "核心目的：先让对方愿意好好说话\n"
            "连招主线：共情 -> 聚焦 -> 给选择\n"
            "速用原则：先停火，再谈问题\n"
            "应急预案：如果对方继续顶，就先把范围收窄"
        ),
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

    ctx = Context(session_id="step8-soften")
    state = {
        "context": ctx,
        "user_input": "我和伴侣又吵起来了，现在最怕越聊越炸",
        "strategy_plan": StrategyPlan(
            mode="C",
            combo_name="亲密关系：终止争吵",
            stage="混合",
            description="案例参考《亲密关系：终止争吵》：内部案例",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "核心目的" not in output
    assert "连招主线" not in output
    assert "速用原则" not in output
    assert "应急预案" not in output
    assert "先把目标放在先让对方愿意好好说话" in output
    assert "顺序上可以先共情，再聚焦，再给选择" in output


def test_step8_should_soften_goal_and_state_alignment_labels(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: (
            "当前目标：推进客户成交\n"
            "当前重点：先把边界和过滤能力补回来\n"
            "先别做：别一边上头一边扩话题，先把节奏收回来\n"
            "当前更适合的做法：先重新做价格锚定，再补真实案例。"
        ),
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

    ctx = Context(session_id="step8-align")
    state = {
        "context": ctx,
        "user_input": "客户拖着不签，我怕越聊越乱",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="知识咨询",
            stage="知识",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "当前目标" not in output
    assert "当前重点" not in output
    assert "先别做" not in output
    assert "这轮先盯住推进客户成交" in output
    assert "眼下先顾住先把边界和过滤能力补回来" in output
    assert "先别急着一边上头一边扩话题" in output


def test_output_profile_should_be_short_for_ack_and_longer_for_complex_question():
    short_profile = _build_output_profile(
        user_input="嗯",
        input_type="混合",
        emotion_intensity=0.2,
        strategy_stage="",
    )
    long_profile = _build_output_profile(
        user_input="客户已经拖了两周不签，我现在既担心压太紧把关系搞坏，又怕继续等下去彻底没窗口了，这种情况我到底该怎么推进？",
        input_type="问题咨询",
        emotion_intensity=0.42,
        strategy_stage="知识",
    )

    assert short_profile["mode"] == "brief"
    assert short_profile["max_chars"] <= 45
    assert long_profile["mode"] == "expanded"
    assert long_profile["max_chars"] >= 170


def test_shape_output_rhythm_should_keep_concrete_scene_reply_together():
    text = "今天先把最卡的一件事变成一个30分钟可完成的小动作，明天固定一个回看时间，只复盘做了什么、卡在哪、下一步谁负责。"
    shaped = _shape_output_rhythm(
        text,
        {"mode": "balanced", "max_chars": 120, "scene": "management"},
        {"mode": "balanced"},
    )

    assert shaped == text


def test_trim_to_output_profile_should_keep_concrete_scene_reply_when_close_enough():
    text = "今天先把最卡的一件事变成一个30分钟可完成的小动作，明天固定一个回看时间，只复盘做了什么、卡在哪、下一步谁负责，再把最占你精力的那件事先放到今天。"
    trimmed = _trim_to_output_profile(
        text,
        {"mode": "balanced", "max_chars": 50, "scene": "management"},
    )

    assert trimmed == text


def test_narrative_profile_should_shift_with_scene_and_emotion():
    repair_profile = _build_narrative_profile(
        user_input="我和老婆又吵起来了，我现在真的很顶",
        input_type="混合",
        emotion_intensity=0.9,
        scene="emotion",
        identity_hint="关系沟通",
        situation_hint="稳定情绪",
        strategy_stage="混合",
    )
    action_profile = _build_narrative_profile(
        user_input="客户拖了很久不签，这周我想把推进往前拉一步",
        input_type="问题咨询",
        emotion_intensity=0.3,
        scene="sales",
        identity_hint="个人决策",
        situation_hint="推进结果",
        strategy_stage="知识",
    )

    assert repair_profile["mode"] == "repair"
    assert action_profile["mode"] == "action"


def test_narrative_profile_should_follow_direct_push_layer_order():
    profile = _build_narrative_profile(
        user_input="给我推进模板",
        input_type="问题咨询",
        emotion_intensity=0.24,
        scene="sales",
        identity_hint="个人决策",
        situation_hint="推进结果",
        strategy_stage="知识",
        layers=[{"layer": 5, "weapon": "选择权引导"}],
    )

    assert profile["mode"] == "action"
    assert "最关键的变化点" in profile["opening_rule"]
    assert "说清" in profile["prompt_hint"]


def test_narrative_profile_should_follow_gap_first_layer_order():
    profile = _build_narrative_profile(
        user_input="这个事我到底该怎么办",
        input_type="问题咨询",
        emotion_intensity=0.38,
        scene="sales",
        identity_hint="个人决策",
        situation_hint="推进结果",
        strategy_stage="知识",
        layers=[{"layer": 1, "weapon": "共情"}, {"layer": 2, "weapon": "镜像"}, {"layer": 4, "weapon": "聚焦式问题"}],
    )

    assert profile["mode"] == "clarify"
    assert "关键追问" in profile["ending_rule"]


def test_build_speech_prompt_should_include_narrative_profile():
    system_prompt, user_prompt = build_speech_prompt(
        layers=[{"layer": 1, "weapon": "共情"}],
        user_state={
            "emotion_type": "挫败",
            "emotion_intensity": 0.7,
            "motive": "生活期待",
            "dominant_desire": "fear",
            "dominant_weight": 0.6,
            "dual_core_state": "对抗",
        },
        strategy_plan={"mode": "A", "stage": "混合", "description": "内部说明"},
        weapons_used=[{"name": "共情", "type": "温和型"}],
        style_params={"professionalism": 0.3, "empathy_depth": 0.8, "logic_density": 0.3, "spoken_ratio": 0.8},
        output_profile={"mode": "contain", "min_chars": 18, "max_chars": 90, "prompt_hint": "先稳住"},
        narrative_profile={
            "mode": "repair",
            "prompt_hint": "先停火再推进",
            "opening_rule": "先接住情绪",
            "ending_rule": "结尾只放一个小动作",
        },
        identity_hint="关系沟通",
        situation_hint="稳定情绪",
        scene="emotion",
        user_input="我和伴侣又吵起来了",
    )

    assert "【叙事走法】" in user_prompt
    assert "【当前位置感】" in user_prompt
    assert "当前身份：关系沟通" in user_prompt
    assert "当前情境：稳定情绪" in user_prompt
    assert "本轮叙事模式：repair" in user_prompt
    assert "原则提醒" in user_prompt
    assert "先接住情绪" in user_prompt


def test_build_speech_prompt_should_include_memory_focus():
    system_prompt, user_prompt = build_speech_prompt(
        layers=[{"layer": 1, "weapon": "共情"}],
        user_state={
            "emotion_type": "平静",
            "emotion_intensity": 0.3,
            "motive": "生活期待",
            "dominant_desire": "gain",
            "dominant_weight": 0.5,
            "dual_core_state": "同频",
        },
        strategy_plan={"mode": "B", "stage": "知识", "description": "内部说明"},
        weapons_used=[{"name": "共情", "type": "温和型"}],
        identity_hint="个人决策",
        situation_hint="推进结果",
        scene="sales",
        user_input="我想先把这事理顺",
        memory_context="""【用户画像】
职业: 运营
【相关记忆】
偏好记忆: 用户习惯先讲结论
事实记忆: 用户正在准备汇报""",
    )

    assert "【记忆重点】" in user_prompt
    assert "偏好记忆: 用户习惯先讲结论" in user_prompt
    assert "先抓这些重点" in user_prompt


def test_build_speech_prompt_should_include_layer_flow_guidance():
    system_prompt, user_prompt = build_speech_prompt(
        layers=[
            {"layer": 1, "weapon": "共情"},
            {"layer": 3, "weapon": "去责备化"},
            {"layer": 2, "weapon": "镜像"},
        ],
        user_state={
            "emotion_type": "挫败",
            "emotion_intensity": 0.72,
            "motive": "生活期待",
            "dominant_desire": "fear",
            "dominant_weight": 0.6,
            "dual_core_state": "对抗",
        },
        strategy_plan={"mode": "A", "stage": "混合", "description": "内部说明"},
        weapons_used=[{"name": "共情", "type": "温和型"}],
        identity_hint="关系沟通",
        situation_hint="稳定情绪",
        scene="emotion",
        user_input="我和伴侣又僵住了",
    )

    assert "【层序拿捏】" in user_prompt
    assert "本轮更像：先接一下 -> 先稳住情绪 -> 先对齐理解" in user_prompt
    assert "开头先顺着当前局面走，别机械套起手。" in user_prompt
    assert "收尾保一个自然落点，别硬收成固定说法。" in user_prompt


def test_build_speech_prompt_should_include_open_closing_policy_for_non_progress_input():
    system_prompt, user_prompt = build_speech_prompt(
        layers=[
            {"layer": 1, "weapon": "共情"},
        ],
        user_state={
            "emotion_type": "疲惫",
            "emotion_intensity": 0.82,
            "motive": "生活期待",
            "dominant_desire": "fear",
            "dominant_weight": 0.7,
            "dual_core_state": "脆弱",
        },
        strategy_plan={"mode": "A", "stage": "混合", "description": "内部说明"},
        weapons_used=[{"name": "共情", "type": "温和型"}],
        output_profile={"mode": "contain", "stage": "情绪承接", "description": "内部说明"},
        narrative_profile={"mode": "repair", "stage": "情绪修复", "description": "内部说明"},
        identity_hint="关系沟通",
        situation_hint="先接住情绪",
        scene="emotion",
        user_input="我现在只是想说说，今天真的很累，不想马上推进。",
    )

    assert "不要每轮都硬收成下一步" in system_prompt
    assert "【收口原则】" in user_prompt
    assert "这一轮先把话说开，不要每轮都硬收成下一步。" in user_prompt
    assert "理解、共鸣、澄清或陪伴" in user_prompt
    assert "只有用户明确要推进，才自然往前接一步。" in user_prompt
    assert "不要连续抛两个很像的追问" in user_prompt
    assert "哪一部分/从哪开始/是不是" in user_prompt


def test_build_speech_prompt_should_translate_direct_push_sequence():
    system_prompt, user_prompt = build_speech_prompt(
        layers=[{"layer": 5, "weapon": "选择权引导"}],
        user_state={
            "emotion_type": "平静",
            "emotion_intensity": 0.25,
            "motive": "生活期待",
            "dominant_desire": "gain",
            "dominant_weight": 0.7,
            "dual_core_state": "同频",
        },
        strategy_plan={"mode": "B", "stage": "知识", "description": "内部说明"},
        weapons_used=[{"name": "选择权引导", "type": "推进型"}],
        identity_hint="个人决策",
        situation_hint="推进结果",
        scene="sales",
        user_input="给我推进模板",
    )

    assert "本轮更像：先给方向" in user_prompt
    assert "开头先顺着当前局面走，别机械套起手。" in user_prompt
    assert "收尾保一个自然落点，别硬收成固定说法。" in user_prompt


def test_build_speech_prompt_should_include_output_focus_when_output_profile_exists():
    system_prompt, user_prompt = build_speech_prompt(
        layers=[{"layer": 1, "weapon": "共情"}],
        user_state={
            "emotion_type": "平静",
            "emotion_intensity": 0.34,
            "motive": "生活期待",
            "dominant_desire": "gain",
            "dominant_weight": 0.55,
            "dual_core_state": "同频",
        },
        strategy_plan={"mode": "B", "stage": "知识", "description": "内部说明"},
        weapons_used=[{"name": "共情", "type": "温和型"}],
        output_profile={
            "mode": "expanded",
            "min_chars": 70,
            "max_chars": 220,
            "prompt_hint": "这轮可以适当展开，但也要像真人说话。先给重点，再补1到3个关键动作，不要固定模板。",
        },
        identity_hint="个人决策",
        situation_hint="推进结果",
        scene="sales",
        user_input="我想把这事讲清楚一点",
    )

    assert "【输出重心】" in user_prompt
    assert "这轮更偏：可以展开，但先把重点说清，再补必要动作" in user_prompt
    assert "说话力度：这一轮可以展开一点，但别拖成报告" in user_prompt


def test_shape_output_rhythm_should_keep_brief_reply_in_one_breath():
    text = "我知道。先别急。我们先盯住一个点。后面再展开。"
    shaped = _shape_output_rhythm(
        text,
        {"mode": "brief", "max_chars": 45},
        {"mode": "carry"},
    )

    assert "\n\n" not in shaped
    assert shaped == "我知道。先别急。"


def test_shape_output_rhythm_should_split_repair_reply_into_two_parts():
    text = "这一下确实会顶。你先别急着证明谁对。先把火压下来。等情绪掉一点再谈。"
    shaped = _shape_output_rhythm(
        text,
        {"mode": "contain", "max_chars": 120},
        {"mode": "repair"},
    )

    assert "\n\n" in shaped
    first, second = shaped.split("\n\n")
    assert first == "这一下确实会顶。你先别急着证明谁对。"
    assert second == "先把火压下来。等情绪掉一点再谈。"


def test_step8_should_trim_overlong_reply_for_short_input(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: (
            "我听到了。你先别急。我们先只盯住一个点，把现在最卡的地方说清楚。"
            "如果你愿意，我可以陪你把这件事从头到尾拆一遍，再一起决定下一步。"
            "现在不用一下子讲那么多。"
        ),
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

    ctx = Context(session_id="step8-short-trim")
    state = {
        "context": ctx,
        "user_input": "嗯",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert len(output) <= 45
    assert "我听到了" in output


def test_step8_should_soften_ack_followup_when_tone_is_pushy(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "你打算让现在的状况再拖多久？你到底是要还是不要？",
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

    ctx = Context(session_id="step8-ack-soften")
    ctx.primary_scene = "sales"
    state = {
        "context": ctx,
        "user_input": "嗯，听起来不错，继续说。",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="知识咨询",
            stage="知识",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "我先不催你下结论" in output
    assert "你到底是要还是不要" not in output


def test_step8_should_append_crisis_guard_for_high_risk_emotion_input(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "我在。",
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

    ctx = Context(session_id="step8-crisis-guard")
    ctx.primary_scene = "emotion"
    state = {
        "context": ctx,
        "user_input": "没有她我真的活不下去了",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "110/120" in output
    assert "认真对待" in output


def test_step8_should_extend_too_short_non_short_utterance_output(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "嗯。",
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

    ctx = Context(session_id="step8-min-len")
    ctx.primary_scene = "emotion"
    ctx.short_utterance = False
    state = {
        "context": ctx,
        "user_input": "我现在没精力想这么多。",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "不用逼自己立刻想清楚" in output
    assert len(output.replace("\n", "").strip()) >= 12


def test_step8_should_use_stable_continue_template_in_emotion_scene(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "行，我接着说。关键不在我这儿。",
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

    ctx = Context(session_id="step8-emotion-continue")
    ctx.primary_scene = "emotion"
    state = {
        "context": ctx,
        "user_input": "嗯，听起来不错，继续说。",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "最刺痛你的那个点" in output
    assert "关键不在我这儿" not in output


def test_step8_should_use_stable_next_step_template_in_management_scene(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "行，那你先说说你最想推进哪一步。",
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

    ctx = Context(session_id="step8-management-next-step")
    ctx.primary_scene = "management"
    state = {
        "context": ctx,
        "user_input": "好的，我明白了。那接下来呢？",
        "strategy_plan": StrategyPlan(
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

    assert "今天先挑一件能推进的小事" in output or "30 分钟可完成的小动作" in output
    assert "回看" in output
    assert "你最想推进的是哪一步" not in output


def test_step8_should_keep_good_management_next_step_output(monkeypatch):
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

    ctx = Context(session_id="step8-management-next-step-keep")
    ctx.primary_scene = "management"
    state = {
        "context": ctx,
        "user_input": "好的，我明白了。那接下来呢？",
        "strategy_plan": StrategyPlan(
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
    assert "30 分钟可完成的小动作" not in output


def test_step8_should_rescue_management_action_request_when_output_keeps_asking(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "你觉得目前最卡住团队的点是什么？是目标本身不清晰，还是大家执行起来总被干扰？",
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

    ctx = Context(session_id="step8-management-next-step-rescue")
    ctx.primary_scene = "management"
    state = {
        "context": ctx,
        "user_input": "你先别讲大道理，给我一个本周能落地的动作。",
        "strategy_plan": StrategyPlan(
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

    assert "你觉得目前最卡住团队的点是什么" not in output
    assert any(marker in output for marker in ["本周", "今天", "20分钟", "20 分钟", "30 分钟", "小动作"])


def test_step8_should_rescue_management_roi_request_when_output_turns_generic(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "现在最拖累团队、最消耗精力的是哪一块？",
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

    ctx = Context(session_id="step8-management-roi-rescue")
    ctx.primary_scene = "management"
    state = {
        "context": ctx,
        "user_input": "财务总监要求证明 AI 投入的 ROI",
        "strategy_plan": StrategyPlan(
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

    assert "最拖累团队、最消耗精力的是哪一块" not in output
    assert any(marker in output for marker in ["基线", "节省", "成本", "一页", "对比"])


def test_step8_should_rescue_management_upward_expectation_request(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "具体是哪些部分拖慢了进度？",
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

    ctx = Context(session_id="step8-management-upward-rescue")
    ctx.primary_scene = "management"
    state = {
        "context": ctx,
        "user_input": "领导对 AI 转型进度不满，但实际情况是技术债很重",
        "strategy_plan": StrategyPlan(
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

    assert "哪些部分拖慢了进度" not in output
    assert any(marker in output for marker in ["现状", "风险", "节点", "取舍", "一页"])


def test_step8_should_follow_management_sub_intent_action_request_without_keyword_dependency(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "你觉得现在最卡的一步是什么？",
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

    ctx = Context(session_id="step8-management-sub-intent-action")
    ctx.primary_scene = "management"
    ctx.management_sub_intent = "action_request"
    ctx.management_sub_intent_confidence = 0.9
    state = {
        "context": ctx,
        "user_input": "先别绕了，给我一个能直接开干的版本。",
        "strategy_plan": StrategyPlan(
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

    assert "你觉得现在最卡的一步是什么" not in output
    assert any(marker in output for marker in ["今天", "本周", "小动作", "回看"])


def test_step8_should_follow_management_sub_intent_change_fatigue_without_keyword_dependency(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "你先说说现在最卡的是哪一块。",
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

    ctx = Context(session_id="step8-management-sub-intent-change")
    ctx.primary_scene = "management"
    ctx.management_sub_intent = "change_fatigue"
    ctx.management_sub_intent_confidence = 0.9
    state = {
        "context": ctx,
        "user_input": "团队已经有点顶不住了。",
        "strategy_plan": StrategyPlan(
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

    assert "你先说说现在最卡的是哪一块" not in output
    assert any(marker in output for marker in ["暂停", "保留", "一件", "减法", "先停"])


def test_step8_should_not_let_upward_template_override_roi_sub_intent(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "你先说说现在最卡的是哪一块。",
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

    ctx = Context(session_id="step8-management-sub-intent-roi")
    ctx.primary_scene = "management"
    ctx.management_sub_intent = "roi_justification"
    ctx.management_sub_intent_confidence = 0.9
    state = {
        "context": ctx,
        "user_input": "这事得给财务那边一个交代。",
        "strategy_plan": StrategyPlan(
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

    assert any(marker in output for marker in ["基线", "节省", "成本", "对比", "一页"])
    assert "现状卡在哪" not in output


def test_step8_should_allow_management_sub_intent_to_hold_when_scene_temporarily_emotional(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "听你这语气，是最近有点烦了？",
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

    ctx = Context(session_id="step8-management-sub-intent-emotion-bridge")
    ctx.primary_scene = "emotion"
    ctx.management_sub_intent = "change_fatigue"
    ctx.management_sub_intent_confidence = 0.92
    state = {
        "context": ctx,
        "user_input": "团队已经被变化压得有点烦了。",
        "strategy_plan": StrategyPlan(
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

    assert "最近有点烦了" not in output
    assert any(marker in output for marker in ["暂停", "保留", "一件", "减负", "先停"])


def test_step8_should_follow_management_sub_intent_cross_team_alignment(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "这种跨部门扯皮其实挺常见的，不是谁对谁错的问题，往往是目标没对齐。",
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

    ctx = Context(session_id="step8-management-sub-intent-cross")
    ctx.primary_scene = "management"
    ctx.management_sub_intent = "cross_team_alignment"
    ctx.management_sub_intent_confidence = 0.93
    state = {
        "context": ctx,
        "user_input": "两个部门最近一直在顶牛。",
        "strategy_plan": StrategyPlan(
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

    assert "目标没对齐" not in output
    assert any(marker in output for marker in ["拉到一起", "同一张纸", "争议点", "统一口径"])


def test_step8_should_follow_sales_sub_intent_price_objection_without_keyword_dependency(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "要不你先看看别家？",
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

    ctx = Context(session_id="step8-sales-sub-intent-price")
    ctx.primary_scene = "sales"
    ctx.sales_sub_intent = "price_objection"
    ctx.sales_sub_intent_confidence = 0.9
    state = {
        "context": ctx,
        "user_input": "我现在最卡的就是预算。",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="销售推进",
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

    assert "看看别家" not in output
    assert any(marker in output for marker in ["总账算清", "总成本", "10 分钟对比", "故障损失"])


def test_step8_should_follow_negotiation_sub_intent_payment_term_without_keyword_dependency(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "这个要不你们再内部商量一下？",
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

    ctx = Context(session_id="step8-neg-sub-intent-payment")
    ctx.primary_scene = "negotiation"
    ctx.negotiation_sub_intent = "payment_term"
    ctx.negotiation_sub_intent_confidence = 0.9
    state = {
        "context": ctx,
        "user_input": "这个条件我们这边真有压力。",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="谈判推进",
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

    assert "内部商量" not in output
    assert any(marker in output for marker in ["90 天", "60 天", "预付款", "签约窗口", "交换式"])


def test_step8_should_hold_sales_sub_intent_when_scene_temporarily_shifts_to_management(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "这种时候你先看看领导那边怎么说。",
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

    ctx = Context(session_id="step8-sales-sub-intent-bridge")
    ctx.primary_scene = "management"
    ctx.sales_sub_intent = "delay_followup"
    ctx.sales_sub_intent_confidence = 0.92
    state = {
        "context": ctx,
        "user_input": "客户说要回去跟老板汇报一下。",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="销售推进",
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

    assert "看看领导那边怎么说" not in output
    assert any(marker in output for marker in ["汇报", "三个点", "30 秒", "最小动作"])
    assert "现状卡在哪" not in output


def test_step8_should_not_accept_light_sales_followup_when_sales_sub_intent_is_delay(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "明白，需要跟老板过一下。这种情况挺常见的。你这边是打算先等老板的反馈，还是我们可以先准备一些汇报时可能用到的材料？",
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

    ctx = Context(session_id="step8-sales-delay-stronger")
    ctx.primary_scene = "management"
    ctx.sales_sub_intent = "delay_followup"
    ctx.sales_sub_intent_confidence = 0.92
    state = {
        "context": ctx,
        "user_input": "客户说要回去跟老板汇报一下。",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="销售推进",
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

    assert "先等老板的反馈" not in output
    assert any(marker in output for marker in ["三个点", "30 秒", "最小动作"])


def test_step8_should_follow_emotion_sub_intent_low_energy_without_keyword_dependency(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "那你先想清楚再说。",
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

    ctx = Context(session_id="step8-emotion-sub-intent-low-energy")
    ctx.primary_scene = "emotion"
    ctx.emotion_sub_intent = "low_energy_support"
    ctx.emotion_sub_intent_confidence = 0.9
    state = {
        "context": ctx,
        "user_input": "我现在真的不太有力气了。",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "想清楚再说" not in output
    assert any(marker in output for marker in ["不用逼自己立刻想清楚", "眼前这一点", "累", "堵得慌"])


def test_step8_should_follow_emotion_sub_intent_failure_containment_without_keyword_dependency(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "你先别想那么多了。",
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

    ctx = Context(session_id="step8-emotion-sub-intent-failure")
    ctx.primary_scene = "emotion"
    ctx.emotion_sub_intent = "failure_containment"
    ctx.emotion_sub_intent_confidence = 0.9
    state = {
        "context": ctx,
        "user_input": "我现在脑子里全是最坏结果。",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "先别想那么多了" not in output
    assert any(marker in output for marker in ["后面整串", "眼前这一格", "最先让你难受", "怎么兜"])


def test_step8_should_stabilize_emotional_accusation_before_question(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "纪念日这件事，我确实没记住。不过我们之间是不是还有别的问题？",
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

    ctx = Context(session_id="step8-emotion-accusation")
    ctx.primary_scene = "emotion"
    state = {
        "context": ctx,
        "user_input": "你根本就不爱我，否则怎么可能忘了纪念日？",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "真的让你不舒服" in output or "真的碰到你了" in output or "不是在闹情绪" in output
    assert "先不急着争对错" in output or "先别急着定谁对谁错" in output or "先别急着争道理" in output
    assert "还有别的问题" not in output


def test_step8_should_use_stable_next_step_template_in_negotiation_scene(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "那就往下收，先谈价格。",
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

    ctx = Context(session_id="step8-negotiation-next-step")
    ctx.primary_scene = "negotiation"
    state = {
        "context": ctx,
        "user_input": "好的，我明白了。那接下来呢？",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="谈判推进",
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

    assert "最容易谈拢的点" in output or "最容易达成一致的点" in output
    assert "回看时间" in output or "确认窗口" in output
    assert "价格区间" in output or "交付边界" in output


def test_step8_should_keep_good_sales_price_output(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "竞品便宜 30% 这个点，我理解你为什么会先卡住。我们先不急着比采购单价，先把总账算清。",
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

    ctx = Context(session_id="step8-sales-price-keep")
    ctx.primary_scene = "sales"
    state = {
        "context": ctx,
        "user_input": "你们的价格太贵了，竞品便宜 30%",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="销售推进",
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

    assert "总账算清" in output
    assert "10 分钟对比" not in output or "总成本" in output


def test_step8_should_keep_good_sales_soft_agreement_output(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "我们已经有共识了，你先给我 1 个最担心点和 1 个最想看到的结果。",
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

    ctx = Context(session_id="step8-sales-soft-agreement-keep")
    ctx.primary_scene = "sales"
    state = {
        "context": ctx,
        "user_input": "有道理，我确实是这样想的。",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="销售推进",
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

    assert "最担心点" in output
    assert "最想看到的结果" in output


def test_step8_should_use_affirmation_template_in_negotiation_scene(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "嗯，那我们顺着往下谈。",
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

    ctx = Context(session_id="step8-negotiation-affirm")
    ctx.primary_scene = "negotiation"
    state = {
        "context": ctx,
        "user_input": "有道理，我确实是这样想的。",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="谈判推进",
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

    assert "认可很重要" in output
    assert "最容易谈拢的点" in output


def test_step8_should_keep_good_emotion_followup_output(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "我们先别急着争对错，你刚才最难受的那一下，是事情本身，还是那种被晾在一边的感觉？",
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

    ctx = Context(session_id="step8-emotion-followup-keep")
    ctx.primary_scene = "emotion"
    state = {
        "context": ctx,
        "user_input": "嗯，听起来不错，继续说。",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "最难受的那一下" in output
    assert "被晾在一边的感觉" in output
    assert "最刺痛你的那个点" not in output


def test_step8_should_stabilize_low_energy_emotion_input(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "嗯，那就先不想。",
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

    ctx = Context(session_id="step8-low-energy")
    ctx.primary_scene = "emotion"
    state = {
        "context": ctx,
        "user_input": "我现在没精力想这么多。",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "不用逼自己立刻想清楚" in output
    assert "累、烦，还是心里堵" in output


def test_step8_should_not_append_unsolicited_sensory_hint(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "嗯，老板让你等消息，这个状态我明白。你回想一下，汇报时老板最关注的是哪个点？",
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

    ctx = Context(session_id="step8-no-sensory-hint")
    ctx.primary_scene = "sales"
    state = {
        "context": ctx,
        "user_input": "我需要跟老板汇报，让我等消息",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="销售跟进",
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

    assert "身体动作指导" not in output
    assert "目光怎么放" not in output


def test_step8_should_stabilize_sales_delay_signal(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "你先回去想想，想好了再来找我。",
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

    ctx = Context(session_id="step8-sales-delay")
    ctx.primary_scene = "sales"
    state = {
        "context": ctx,
        "user_input": "我需要跟老板汇报，让我等消息",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="销售跟进",
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

    assert "先不用急着给我结论" in output
    assert "三个点" in output


def test_step8_should_stabilize_failure_anxiety(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "失败了也没关系，你先往前冲。",
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

    ctx = Context(session_id="step8-failure-anxiety")
    ctx.primary_scene = "emotion"
    state = {
        "context": ctx,
        "user_input": "如果失败了怎么办？",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "怕一旦失败" in output
    assert "最先让你难受的会是哪一部分" in output


def test_step8_should_rotate_emotional_accusation_template(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "我知道你在说什么，但我还是不太信。",
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

    ctx = Context(session_id="step8-emotion-accusation-rotate")
    ctx.primary_scene = "emotion"
    state = {
        "context": ctx,
        "user_input": "我觉得你在敷衍我，这听起来像套路。",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "先别急着争对错" in output or "我先不跟你争道理" in output or "先别急着定谁对谁错" in output
    assert "最难受的，是他忘了这件事本身" not in output


def test_step8_should_pass_strategy_skeleton_hint_into_generation(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    captured = {}

    def _fake_generate_speech(**kwargs):
        captured["knowledge_content"] = kwargs.get("knowledge_content", "")
        return "先说重点：我们先稳住。"

    monkeypatch.setattr(speech_generator, "generate_speech", _fake_generate_speech)
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

    ctx = Context(session_id="step8-skeleton-hint")
    ctx.current_strategy.skeleton.do_now = ["先接住情绪，再收成一个点"]
    ctx.current_strategy.skeleton.do_later = ["回稳后再推进方案"]
    ctx.current_strategy.skeleton.avoid_now = ["不要强推结果"]
    ctx.current_strategy.skeleton.fallback_move = "卡住时先停火再单点确认。"

    state = {
        "context": ctx,
        "user_input": "我现在很顶，别逼我",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    step8_execution(state)

    assert "【策略骨架】" in captured["knowledge_content"]
    assert "先做：" in captured["knowledge_content"]
    assert "先别做：" in captured["knowledge_content"]


def test_step8_should_clean_internal_terms_after_sensory_guide_append(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module
    import modules.L4.sensory_application as sensory_application

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "先稳住，再往前走。",
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
    monkeypatch.setattr(sensory_application, "detect_scenario_intent", lambda _text: None)
    monkeypatch.setattr(sensory_application, "detect_regulation_need", lambda *_args, **_kwargs: "anger")
    monkeypatch.setattr(sensory_application, "generate_regulation_guide", lambda _need: object())
    monkeypatch.setattr(
        sensory_application,
        "format_regulation_guide",
        lambda _guide: "先给理性核3秒启动时间，再把感性核放缓。",
    )

    ctx = Context(session_id="step8-sensory-clean")
    ctx.primary_scene = "emotion"
    ctx.user.emotion.intensity = 0.86
    state = {
        "context": ctx,
        "user_input": "我现在很炸，详细说说怎么稳住",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "理性核" not in output
    assert "感性核" not in output


def test_step8_should_not_append_regulation_guide_for_failure_containment_without_detail_request(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module
    import modules.L4.sensory_application as sensory_application

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "怕很正常，这件事对你来说很重要。我们先别一下想到最后，只拆眼前这一格。",
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
    monkeypatch.setattr(sensory_application, "detect_scenario_intent", lambda _text: None)
    monkeypatch.setattr(sensory_application, "detect_regulation_need", lambda *_args, **_kwargs: "sadness")
    monkeypatch.setattr(
        sensory_application,
        "generate_regulation_guide",
        lambda _need: (_ for _ in ()).throw(AssertionError("regulation guide should not be generated for failure containment without detail request")),
    )

    ctx = Context(session_id="step8-no-regulation-failure-containment")
    ctx.primary_scene = "emotion"
    ctx.emotion_sub_intent = "failure_containment"
    ctx.emotion_sub_intent_confidence = 0.92
    ctx.user.emotion.intensity = 0.86
    state = {
        "context": ctx,
        "user_input": "如果失败了怎么办，我现在真的很怕。",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "自我调节方法" not in output
    assert "呼吸：" not in output


def test_step8_should_not_append_self_regulation_guide_outside_emotion_scene(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module
    import modules.L4.sensory_application as sensory_application

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "先把关键问题说清楚。",
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
    monkeypatch.setattr(sensory_application, "detect_scenario_intent", lambda _text: None)
    monkeypatch.setattr(sensory_application, "detect_regulation_need", lambda *_args, **_kwargs: "anger")
    monkeypatch.setattr(
        sensory_application,
        "generate_regulation_guide",
        lambda _need: (_ for _ in ()).throw(AssertionError("regulation guide should not be generated outside emotion scene")),
    )

    ctx = Context(session_id="step8-no-regulation-outside-emotion")
    ctx.primary_scene = "sales"
    ctx.user.emotion.type = EmotionType.ANGRY
    ctx.user.emotion.intensity = 0.86
    state = {
        "context": ctx,
        "user_input": "客户一直拖着不签，我有点焦虑",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="销售推进",
            stage="知识",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]

    assert "自我调节方法" not in output
    assert "呼吸：" not in output
    assert "触觉锚定" not in output


def test_step8_should_inject_skeleton_order_when_progress_request_lacks_sequence(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "我建议你继续推进，不要断掉节奏。",
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

    ctx = Context(session_id="step8-skeleton-order-inject")
    ctx.primary_scene = "sales"
    ctx.current_strategy.skeleton.do_now = ["先把一个推进动作说清楚"]
    ctx.current_strategy.skeleton.do_later = ["回稳后再谈价格细项"]
    ctx.current_strategy.skeleton.avoid_now = ["不要一上来就压结果"]
    state = {
        "context": ctx,
        "user_input": "我想推进落地，但不想把关系搞僵。",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="销售推进",
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
    output_layers = result["output_layers"]

    assert "这轮先做一件事：" not in output
    assert "等这步稳住，再做：" not in output
    assert "现在先别做：" not in output
    assert "这轮先把一个推进动作说清楚" in output
    assert "等这步稳住，再补回稳后再谈价格细项" in output
    assert "先别急着一上来就压结果" in output
    assert output_layers["order_source"] == "skeleton_injected"
    assert output_layers["failure_avoid_codes"] == []


def test_step8_should_not_inject_skeleton_order_when_output_already_has_sequence(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "先把一个推进动作说清楚，再谈价格细项。",
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

    ctx = Context(session_id="step8-skeleton-order-skip")
    ctx.primary_scene = "sales"
    ctx.current_strategy.skeleton.do_now = ["先把一个推进动作说清楚"]
    ctx.current_strategy.skeleton.do_later = ["回稳后再谈价格细项"]
    state = {
        "context": ctx,
        "user_input": "下一步怎么走？",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="销售推进",
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
    output_layers = result["output_layers"]

    assert output.count("这轮先做一件事：") == 0
    assert output_layers["order_source"] == "model_explicit_order"
    assert output_layers["failure_avoid_codes"] == []


def test_step8_should_skip_skeleton_order_injection_when_output_is_concrete(monkeypatch):
    import importlib

    step8_module = importlib.import_module("graph.nodes.step8_execution")
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "今天先把最卡的一件事变成一个 30 分钟可完成的小动作，明天固定一个回看时间，只复盘做了什么、卡在哪、下一步谁负责。",
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
    monkeypatch.setattr(
        step8_module,
        "_inject_skeleton_order_if_missing",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("skeleton order should have been skipped")),
    )

    ctx = Context(session_id="step8-skeleton-order-concrete-skip")
    ctx.primary_scene = "management"
    ctx.current_strategy.skeleton.do_now = ["先把一个推进动作说清楚"]
    ctx.current_strategy.skeleton.do_later = ["回稳后再谈细项"]
    ctx.current_strategy.skeleton.avoid_now = ["不要一上来就压结果"]
    state = {
        "context": ctx,
        "user_input": "下一步怎么走？",
        "strategy_plan": StrategyPlan(
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
    output_layers = result["output_layers"]

    assert "30 分钟可完成的小动作" in output
    assert "回看时间" in output
    assert "这轮先做一件事：" not in output
    assert output_layers["order_source"] == "model_explicit_order"


def test_step8_should_skip_skeleton_order_injection_for_weekly_management_action(monkeypatch):
    import importlib

    step8_module = importlib.import_module("graph.nodes.step8_execution")
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "本周就做一件事：把下周要交付的任务拆成三个明确的检查点，每天下班前花10分钟同步进度。",
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
        "_inject_skeleton_order_if_missing",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("skeleton order should have been skipped")),
    )

    ctx = Context(session_id="step8-management-weekly-action")
    ctx.primary_scene = "management"
    ctx.current_strategy.skeleton.do_now = ["先确认当前最卡的一步"]
    ctx.current_strategy.skeleton.do_later = ["执行后再补第二步和复盘点"]
    ctx.current_strategy.skeleton.avoid_now = ["不要一次给太多方案"]
    state = {
        "context": ctx,
        "user_input": "你先别讲大道理，给我一个本周能落地的动作。",
        "strategy_plan": StrategyPlan(
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
    output_layers = result["output_layers"]

    assert "本周就做一件事" in output
    assert "这轮先把" not in output
    assert "先别急着" not in output
    assert output_layers["order_source"] == "model_explicit_order"


def test_step8_should_keep_emotion_output_open_when_user_is_not_pushing_progress(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "我听到了，你现在真的很累。我们先把这件事说清，不急着推进。",
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

    ctx = Context(session_id="step8-emotion-open-ending")
    ctx.primary_scene = "emotion"
    state = {
        "context": ctx,
        "user_input": "我现在只是想说说，真的很累。",
        "strategy_plan": StrategyPlan(
            mode="A",
            combo_name="情绪承接",
            stage="混合",
            description="内部说明",
            fallback="",
        ),
        "weapons_used": [{"name": "共情", "type": "温和型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output = result["output"]
    output_layers = result["output_layers"]

    assert output_layers["order_source"] == "not_progress_request"
    assert "这轮先做一件事：" not in output
    assert "下一步" not in output


def test_step8_should_expose_failure_avoid_codes_from_strategy_skeleton(monkeypatch):
    import prompts.speech_generator as speech_generator
    import modules.L4.field_quality as field_quality
    import modules.memory as memory_module

    monkeypatch.setattr(
        speech_generator,
        "generate_speech",
        lambda **kwargs: "我们先稳住，再推进一个动作。",
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

    ctx = Context(session_id="step8-failure-avoid-codes")
    ctx.primary_scene = "sales"
    state = {
        "context": ctx,
        "user_input": "我想推进落地",
        "strategy_plan": StrategyPlan(
            mode="B",
            combo_name="销售推进",
            stage="知识",
            description="内部说明",
            fallback="",
        ),
        "strategy_skeleton": {
            "do_now": ["先推进一个动作"],
            "do_later": ["再确认下一步"],
            "avoid_now": ["不要推进过早"],
            "fallback_move": "先收口",
            "failure_avoid_codes": ["F02", "F03"],
        },
        "weapons_used": [{"name": "聚焦", "type": "直接型"}],
        "priority": {"priority_type": "none"},
        "skip_to_end": False,
    }

    result = step8_execution(state)
    output_layers = result["output_layers"]
    assert output_layers["failure_avoid_codes"] == ["F02", "F03"]
