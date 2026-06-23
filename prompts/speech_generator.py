"""
Human-OS Engine - Prompt 模板：话术生成器（Step 8）

将五层结构骨架 + 用户状态 + 武器 + 记忆上下文注入 Prompt，
由 LLM 动态生成自然语言话术。
"""

# ===== 系统 Prompt =====

SPEECH_SYSTEM_PROMPT = """你是站在用户这边的人，不是客服，也不是来评判用户的人。

【核心原则】
1. 先站在用户这边：先接住当前处境，再决定要不要推进
2. 平等对话：不卑微、不讨好、不迎合，也不居高临下
3. 真实性高于礼貌：可以直接，但不能冷硬到像在审人
4. 只有在用户真的需要时，再给建议、拆解或指出问题

【表达风格】
- 70%口语 + 30%专业感
- 直接、不绕弯、有事说事
- 有温度但不粘腻，有关心但不肉麻
- 中文表达，自然流畅

【绝对禁止】
- 禁止使用以下词汇：利用、害怕、畏惧、钩子、恐惧（用"担忧""顾虑"替代）
- 禁止输出内部术语：五层结构、武器库、八宗罪、Mode A/B/C、策略组合
- 禁止使用套路化表达："天呐""我理解你的感受""需要我帮你吗"
- 禁止自称"AI助手""小助手"或使用客服词汇
- 禁止输出任何分析、推理、规划过程
- 禁止以"好的"开头
- 禁止一上来就给用户下判断、扣帽子、定义情绪真假

【输出要求】
- 只输出最终对话内容，不要任何解释或分析
- 长短要动态，不要固定成一个模板
- 直接开始对话，不要前缀
- 根据用户状态调整温度（高情绪时更共情，低情绪时更直接）
- 不要每轮都硬收成下一步，先把话说开；只有用户明确在推进时，再自然接到往前的一步
- 当用户在表达委屈、受挫、被否定、被骂、心里堵时，先接住，不要先分析他到底是不是有情绪"""

MINIMAL_SPEECH_MODE_CONSTRAINTS = """

【轻量模式】
- 只回应用户当前这句话，不要把内容扩成流程或报告。
- 不要固定开头，不要固定结尾，不要强行总结。
- 不要强行追问，不要硬塞下一步。
- 如果需要续接，也只留一句自然的轻收口，不要连着给两层建议。
- 只保留最少必要的上下文，别把历史、策略、骨架都摊开。
"""

CRISIS_MINIMAL_SUPPORT_CONSTRAINTS = """

【危机支持】
- 先安全承接，不要推进目标，不要销售，不要谈判，不要管理式推进。
- 语气要稳、短、直接，先把人接住。
- 如果有即时危险，优先建议联系当地紧急服务或身边可信任的人陪伴。
"""

# 【修复4A】防御模式额外约束
DEFENSIVE_MODE_CONSTRAINTS = """

【防御模式强制规则 - 必须严格遵守】
当前处于防御模式，你必须严格遵守以下规则：

1. 禁止使用以下词汇和表达（绝对禁止）：
   - 机会、错过、抓紧、翻倍、赚、稀缺、最后、限时、紧迫、窗口期
   - 任何暗示压力、催促、销售、推销性质的用语
   - "要不要听听"、"想不想了解"、"我帮你" 等推销式提问

2. 必须使用以下替代表达：
   - 机会 → 可能性
   - 错过 → 没赶上
   - 抓紧 → 尽快
   - 翻倍 → 提升
   - 赚 → 获得
   - 稀缺 → 有限
   - 最后 → 剩下
   - 限时 → 时间
   - 紧迫 → 重要
   - 窗口期 → 阶段

3. 输出必须是：
   - 保持合伙人身份，不卑不亢
   - 使用以下话术风格：共情、澄清、设定框架、给予选择权
   - 语气冷静、克制、有边界感

4. 正确的话术风格示例：
   - "行，那你说说具体怎么回事。"
   - "这件事我们换个角度看看。"
   - "如果你愿意，我们可以先聚焦一个点。"
   - "你现在的感受我听到了。你想让我怎么回应？"
   - "我们一步步来，先理清你最在意的是什么。"
"""


# ===== 用户 Prompt 模板 =====

SPEECH_USER_PROMPT = """请直接输出对话回应（不要任何分析或推理）：

【用户输入】{user_input}

【当前位置感】
- 当前身份：{identity_hint}
- 当前情境：{situation_hint}
- 主场景：{scene}
- 本轮主任务：{dialogue_task}

【用户状态】
- 情绪：{emotion_type}（强度：{emotion_intensity}）
- 动机：{motive}
- 主导欲望：{dominant_desire}
- 双核状态：{dual_core_state}

【对话目标】
- 模式：{mode}
- 阶段：{stage}
- 策略：{strategy_description}

【五层骨架】（按顺序自然融入对话，不要逐层念）
{layers_description}

【推荐武器】（自然地使用这些表达方式）
{weapons_description}

【记忆上下文】
{memory_context}

【知识参考】
以下是相关背景知识，请消化后用大白话自然融入对话中，不要原样引用，不要出现学术术语：
{knowledge_content}

请直接输出对话内容，不要任何分析、推理或解释。"""


# ===== 层级描述模板 =====

LAYER_DESCRIPTIONS = {
    1: "第1层 即时反应：让对方知道你听到了（如：表达共情、第一人称反应、简短确认）",
    2: "第2层 理解确认：确认你理解了对方的情况（如：复述关键点、镜像模仿）",
    3: "第3层 共情支持：降低对方的焦虑、羞耻感、压力（如：正常化、去责备化、赋予身份）",
    4: "第4层 具体追问：收集关键信息，聚焦问题（如：好奇式提问、聚焦式问题）",
    5: "第5层 方向引导：给出可选路径，让对方做选择（如：给予价值、选择权引导、描绘共同未来）",
}


def _build_layer_flow_description(layers: list[dict]) -> str:
    """把当前层顺序翻成原则提示，避免把开头和收尾写死成流程表。"""
    if not layers:
        return ""

    layer_names = {
        1: "先接一下",
        2: "先对齐理解",
        3: "先稳住情绪",
        4: "先补关键缺口",
        5: "先给方向",
    }
    layer_ids = [layer.get("layer") for layer in layers if layer.get("layer") in layer_names]
    if not layer_ids:
        return ""

    sequence_text = " -> ".join(layer_names[layer_id] for layer_id in layer_ids)
    middle_rule = []
    if 4 in layer_ids and 5 in layer_ids and layer_ids.index(4) < layer_ids.index(5):
        middle_rule.append("中间先把关键缺口补上，再给方向，不要跳步。")
    elif 3 in layer_ids and 5 not in layer_ids:
        middle_rule.append("中间以降压和稳关系为主，不要太早推进。")
    elif 2 in layer_ids and 5 in layer_ids:
        middle_rule.append("中间先把理解对齐，再自然转到下一步。")
    elif 1 in layer_ids and 5 not in layer_ids:
        middle_rule.append("中间先接住当下，再看要不要继续推进。")

    description = (
        "\n【层序拿捏】\n"
        f"- 本轮更像：{sequence_text}\n"
        "- 开头先顺着当前局面走，别机械套起手。\n"
    )
    if middle_rule:
        description += f"- 中段拿捏：{'；'.join(middle_rule)}\n"
    description += "- 收尾保一个自然落点，别硬收成固定说法。"
    return description


def _looks_like_progress_request(user_input: str) -> bool:
    """判断用户是不是明确在要推进/下一步。"""
    text = (user_input or "").strip()
    if not text:
        return False
    if _is_next_step_signal(text):
        return True
    markers = ["推进", "落地", "先做", "怎么做", "怎么走", "执行", "下一步"]
    return any(m in text for m in markers)


def _is_next_step_signal(text: str) -> bool:
    """判断文本里有没有明确的下一步 / 推进信号。"""
    markers = ["下一步", "接下来", "继续", "推进", "落地", "怎么做", "怎么走", "执行"]
    return any(marker in text for marker in markers)


def _build_closing_policy_description(
    user_input: str,
    scene: str,
    output_profile: dict | None = None,
    narrative_profile: dict | None = None,
    next_step_policy: str = "soft",
) -> str:
    """把“要不要收口”单独讲清楚，避免每轮都被强行收成下一步。"""
    output_mode = (output_profile or {}).get("mode", "")
    narrative_mode = (narrative_profile or {}).get("mode", "")
    open_modes = {"brief", "contain", "light", "carry", "repair", "clarify"}
    progress_request = _looks_like_progress_request(user_input)
    policy_mode = (next_step_policy or "soft").strip().lower()

    if scene in {"emotion", "management"} or output_mode in open_modes or narrative_mode in open_modes or not progress_request:
        policy_text = (
            "\n【收口原则】\n"
            "- 这一轮先把话说开，不要每轮都硬收成下一步。\n"
            "- 没有明确推进信号时，可以停在理解、共鸣、澄清或陪伴上。\n"
            "- 只有用户明确要推进，才自然往前接一步。"
        )
        if scene == "emotion":
            policy_text += (
                "\n- 情绪场景里，不要连续抛两个很像的追问，更不要把“哪一部分/从哪开始/是不是”换皮重复。"
                "\n- 如果上一句已经在承接情绪，这一轮更适合换成复述、安放或一条更轻的问题。"
            )
        if policy_mode == "none":
            policy_text += (
                "\n- 本轮收口强度：none。回答完就停，不要再额外追问、总结或补下一步。"
            )
        elif policy_mode == "soft":
            policy_text += (
                "\n- 本轮收口强度：soft。最多留一句很轻的继续空间，不要任务清单，不要连续追问，不要把结尾写成追问。"
            )
        else:
            policy_text += (
                "\n- 本轮收口强度：explicit。先给可直接发出去的话术或执行步骤，第一句必须先给默认动作或话术，再补一个主动作；不要先问背景，也不要多头收口。"
            )
            if any(marker in user_input for marker in ["怎么回", "怎么说", "怎么做"]):
                policy_text += "\n- 这种问题先给可复制的话术，开头可以用“你可以这样说：”或“可以先这样回：”，先把可用版本放前面，再考虑补一句细化，不要先问背景。"
            if any(marker in user_input for marker in ["压价", "账期", "条件", "签约", "底线", "让步", "拖着", "不配合", "甩锅", "跨部门", "绩效", "下属", "员工"]):
                policy_text += "\n- 这种管理/谈判类问题别先反问确认，先给一个可以直接落地的动作或一句可以直接发的话，后面如果需要再补一句轻问。"
            if any(marker in user_input for marker in ["路线图", "审计", "修复", "分析", "报告"]):
                policy_text += "\n- 这种问题先给一版默认步骤或路线图：先看入口和调用链，再看记忆/学习/安全，最后看回归和性能。开头可以用“先做这几步：”；即使信息不全，也先往前给，不要先问范围。"
        return policy_text

    policy_text = (
        "\n【收口原则】\n"
        "- 可以往前接，但也别收得太死，尽量留一点继续往下接的余地。"
    )
    if policy_mode == "none":
        policy_text += "\n- 本轮收口强度：none。回答完就停，不要追问，不要给下一步。"
    elif policy_mode == "soft":
        policy_text += "\n- 本轮收口强度：soft。最多留一句自然承接，不要任务清单，不要把结尾写成追问。"
    else:
        policy_text += "\n- 本轮收口强度：explicit。先给一段可直接用的话术或一个执行动作，第一句先把动作放前面，再收口；不要先反问确认，也不要把结尾写成追问。"
        if any(marker in user_input for marker in ["怎么回", "怎么说", "怎么做"]):
            policy_text += "\n- 这种问题先给可复制的话术，开头可以用“你可以这样说：”或“可以先这样回：”，先把答案放前面，再补背景。"
        if any(marker in user_input for marker in ["压价", "账期", "条件", "签约", "底线", "让步", "拖着", "不配合", "甩锅", "跨部门", "绩效", "下属", "员工"]):
            policy_text += "\n- 这种管理/谈判类问题别先反问确认，先给一个可以直接落地的动作或一句可以直接发的话，后面如果需要再补一句轻问。"
        if any(marker in user_input for marker in ["路线图", "审计", "修复", "分析", "报告"]):
            policy_text += "\n- 这种问题先给一版默认步骤或路线图：先看入口和调用链，再看记忆/学习/安全，最后看回归和性能。开头可以用“先做这几步：”；即使信息不全，也先往前给，不要先问范围。"
    return policy_text


def _build_expression_policy_description(
    scene: str,
    memory_context: str = "",
    output_profile: dict | None = None,
    narrative_profile: dict | None = None,
) -> str:
    """从意图层约束表达方式，避免固定句式反复出现。"""
    core_scenes = {"sales", "management", "negotiation", "emotion"}
    has_closure_memory = bool(memory_context) and (
        "【关系闭环摘要】" in memory_context or "【下一轮接话点】" in memory_context
    )
    if scene not in core_scenes and not has_closure_memory:
        return ""

    policy_lines = [
        "\n【表达策略】",
        "- 先按意图组织表达，不要反复套用固定句。",
        "- 这轮只完成一个核心功能：接住、澄清、轻推进、收口、安放，别把几种功能混在同一句里。",
        "- 如果记忆里有关系闭环摘要或下一轮接话点，只借方向，不照搬上一轮句式。",
        "- 优先用当前语境里的具体信息说话，少用空泛的通用开头。",
        "- 如果上一轮已经接住了，这一轮就换一种更自然的开头，不要每次都用相近起手。",
    ]

    if scene == "emotion":
        policy_lines.append("- 情绪场景先复述感受，再给一点点方向；追问只问一个点，不要连续抛同类问题。")
    elif scene == "management":
        policy_lines.append("- 管理场景先接住压力或局面，再落到一个小下一步；不要总是同一种“稳住再推进”句式。")
    elif scene == "sales":
        policy_lines.append("- 销售场景先承接顾虑，再给对比或验证；不要总是同一种“先看结果/风险”句式。")
    elif scene == "negotiation":
        policy_lines.append("- 谈判场景先保住边界，再推进交换；不要总是同一种“最容易谈拢的点”句式。")

    output_mode = (output_profile or {}).get("mode", "")
    narrative_mode = (narrative_profile or {}).get("mode", "")
    if output_mode in {"brief", "carry", "light"} or narrative_mode in {"brief", "carry", "light"}:
        policy_lines.append("- 本轮更偏短承接，句子可以短，但不要短到像机械确认。")
    else:
        policy_lines.append("- 本轮可以自然展开，但先把重点说清，不用为了稳把话收得太板。")

    return "\n".join(policy_lines)


def _build_contain_opening_policy(
    user_state: dict,
    identity_hint: str,
    situation_hint: str,
    scene: str,
) -> str:
    """主任务是 contain 时，补一条更具体的开口约束。"""
    relationship_position = user_state.get("relationship_position", "")
    emotion_type = user_state.get("emotion_type", "")

    work_hurt = (
        "下级-上级" in relationship_position
        or "上级-下级" in relationship_position
        or "职场" in (identity_hint or "")
        or "职场" in (situation_hint or "")
        or "受挫" in (situation_hint or "")
        or scene == "management"
    )

    if work_hurt:
        return (
            "\n【先接住的开口规则】\n"
            "- 当前更像是工作里受挫或被压了一下，第一句先接这一下，不要马上查错。\n"
            "- 可以先接委屈、发懵、挂不住、心里堵，而不是直接追问事实细节。\n"
            "- 如果要问，优先问“现在最难受的是哪一下”，不要先问“具体哪里做错了”。"
        )

    if emotion_type and emotion_type not in {"平静", ""}:
        return (
            "\n【先接住的开口规则】\n"
            "- 第一反应先贴着当下感受说，不要急着做判断。\n"
            "- 如果要问，也先问感受里的关键点，不要一上来盘事实。"
        )

    return (
        "\n【先接住的开口规则】\n"
        "- 先顺着用户当下那一下说，不要一开口就切到分析或审问。"
    )


def build_speech_prompt(
    layers: list[dict],
    user_state: dict,
    strategy_plan: dict,
    weapons_used: list[dict],
    memory_context: str = "",
    knowledge_content: str = "",
    style_params: dict | None = None,
    output_profile: dict | None = None,
    narrative_profile: dict | None = None,
    identity_hint: str = "",
    situation_hint: str = "",
    dialogue_task: str = "clarify",
    scene: str = "",
    user_input: str = "",
    forced_weapon_type: str | None = None,
    evidence_content: str = "",
    skill_prompt: str = "",
    secondary_scene_strategy: str = "",
    narrative_rules: str = "",
    guidance_prompt: str = "",
    minimal_mode: bool = False,
    context_brief: dict | None = None,
    continuity_focus: dict | None = None,
    next_step_policy: str = "soft",
    step8_mode: str = "full",
) -> tuple[str, str]:
    """
    构建话术生成的 Prompt

    Args:
        layers: 五层结构配置列表
        user_state: 用户状态字典
        strategy_plan: 策略方案
        weapons_used: 使用的武器列表
        memory_context: 记忆上下文
        knowledge_content: 知识内容
        style_params: 风格参数 {professionalism, empathy_depth, logic_density, spoken_ratio}
        output_profile: 输出画像 {mode, min_chars, max_chars, prompt_hint}
        narrative_profile: 叙事画像 {mode, prompt_hint, opening_rule, ending_rule}
        identity_hint: 当前身份提示
        situation_hint: 当前情境提示
        scene: 当前主场景
        user_input: 用户原始输入
        forced_weapon_type: 强制武器类型 (defensive/gentle/aggressive)

    Returns:
        tuple[str, str]: (system_prompt, user_prompt)
    """
    # 轻量模式：只保留当前输入 + 极简上下文 + 收口策略。
    from utils.types import sanitize_for_prompt
    safe_input = sanitize_for_prompt(user_input)
    brief = context_brief if isinstance(context_brief, dict) else {}
    memory_brief = str(brief.get("memory_brief", "") or "").strip()
    world_state_brief = str(brief.get("world_state_brief", "") or "").strip()
    next_pickup = str(brief.get("next_pickup", "") or "").strip()
    focus = continuity_focus if isinstance(continuity_focus, dict) else {}
    focus_type = str(focus.get("focus_type", "") or "").strip()
    focus_instruction = str(focus.get("output_instruction", "") or "").strip()
    focus_anchor = str(focus.get("anchor", "") or "").strip()
    focus_decision_bias = str(focus.get("decision_bias", "") or "").strip()
    focus_must_use = [str(item or "").strip() for item in (focus.get("must_use_points", []) or []) if str(item or "").strip()]
    focus_avoid = [str(item or "").strip() for item in (focus.get("avoid", []) or []) if str(item or "").strip()]
    focus_next_pickup = str(focus.get("next_pickup", "") or "").strip()
    focus_world_state = str(focus.get("world_state_hint", "") or "").strip()
    focus_relationship = str(focus.get("relationship_hint", "") or "").strip()
    focus_enabled = bool(
        focus.get("memory_use_required", False)
        and focus_type
        and focus_instruction
        and focus_anchor
        and focus_decision_bias
    )

    continuity_lines: list[str] = []
    if focus_enabled:
        focus_rules = {
            "preference": [
                "本轮用户偏好是：直接、先给结论、少铺垫。",
                "第一段必须先给结论，再补理由。",
                "不要先写“看情况”或先铺一大段背景。",
            ],
            "project_state": [
                "本轮必须围绕当前项目状态回答，不要给泛泛计划。",
                "主判断要扣住收口节奏、客户压价、守价格或不继续无条件让步。",
                "第一段先说现在该怎么排，不要从零开始讲通用方法。",
            ],
            "sales_context": [
                "这是销售连续承接，不要像新问题一样重新开题。",
                "第一段先给判断，再给下一步或话术。",
                "不要写“先补充背景”“看情况再说”这类泛开头。",
            ],
            "negotiation_context": [
                "这是谈判连续承接，先基于现有局面做判断。",
                "第一段先讲守边界还是条件式让步，再补具体说法。",
                "不要把回答写成通用谈判课。",
            ],
            "management_relation": [
                "这是管理关系连续承接，关系风险必须保留。",
                "第一段先给判断，再给说法。",
                "不要直接滑向强硬批评或泛泛管理建议。",
            ],
            "crisis_recovery": [
                "这是危机恢复承接，安全感优先。",
                "第一段必须承接刚从高风险状态缓下来、现在仍有点怕。",
                "不要转业务，不要泛泛安慰，不要像新问题一样重讲大道理。",
            ],
        }
        hard_rules = focus_rules.get(
            focus_type,
            [
                "第一段必须自然承接这个锚点。",
                "主判断必须围绕这个锚点展开。",
                "不要像新问题一样从零回答。",
            ],
        )
        continuity_lines = [
            "",
            "【本轮必须承接】",
            f"- 类型：{focus_type}",
            f"- 承接锚点：{focus_anchor or '（无）'}",
            f"- 判断倾向：{focus_decision_bias or '（无）'}",
            f"- 接话点：{focus_next_pickup or '（无）'}",
            f"- 局面提示：{focus_world_state or '（无）'}",
            f"- 关系提示：{focus_relationship or '（无）'}",
            f"- 必须用到：{'；'.join(focus_must_use[:3]) if focus_must_use else '（无）'}",
            f"- 避免这样答：{'；'.join(focus_avoid[:3]) if focus_avoid else '（无）'}",
            f"- 本轮回答要求：{focus_instruction}",
            "",
            "硬性要求：",
            *[f"- {rule}" for rule in hard_rules],
            "- 不要写“根据你的记忆”或“根据之前”。",
            "- 如果这个锚点和当前问题明显无关，才可以忽略。",
        ]

    if minimal_mode or (step8_mode or "").lower() in {"light", "minimal", "crisis"}:
        system_prompt = SPEECH_SYSTEM_PROMPT
        if (step8_mode or "").lower() == "crisis":
            system_prompt += CRISIS_MINIMAL_SUPPORT_CONSTRAINTS
        else:
            system_prompt += MINIMAL_SPEECH_MODE_CONSTRAINTS

        status_lines = [
            "请直接输出一段自然回应，不要分析、不要解释流程。",
            "",
            f"【用户输入】{safe_input}",
            "",
            f"【当前位置】当前场景：{scene or 'default'}；本轮任务：{dialogue_task or 'clarify'}；收口策略：{next_step_policy or 'soft'}",
            "",
            "【轻量上下文】",
            f"- 记忆摘要：{memory_brief or '（无）'}",
            f"- 现场状态：{world_state_brief or '（无）'}",
            f"- 接话点：{next_pickup or '（无）'}",
            "",
            "【回复要求】",
            "- 只说自然回应，不要写成报告。",
            "- 不要固定开头，不要固定结尾。",
            "- 不要强制总结，不要强制追问。",
        ]
        if (next_step_policy or "soft") == "none":
            status_lines.append("- 直接回答即可，不要额外加下一步、追问、总结或继续聊。")
        elif (next_step_policy or "soft") == "soft":
            status_lines.append("- 如果要续接，也只留一句很轻的继续空间，别写成任务清单。")
        else:
            status_lines.append("- 如果需要给下一步，先给一段可直接用的话术或一个简短动作，再收口；第一句不要先反问确认，不要展开成方案，也不要重复收口，结尾尽量用陈述句，不要把结尾写成追问。")
        if (step8_mode or "").lower() == "crisis":
            status_lines.extend([
                "- 先把安全放在第一位，不要推进销售、谈判、管理或任务计划。",
                "- 如果对方有即时危险，优先建议联系当地紧急服务或可信任的人。",
            ])
        if focus_enabled and (
            focus_type in {"preference", "crisis_recovery", "followup"}
            or next_pickup
            or world_state_brief
        ):
            status_lines.extend(continuity_lines)

        return system_prompt, "\n".join(status_lines)

    # 构建层级描述
    layers_desc = []
    for layer in layers:
        layer_num = layer["layer"]
        weapon = layer.get("weapon", "")
        desc = LAYER_DESCRIPTIONS.get(layer_num, "")
        layers_desc.append(f"- {desc}【推荐武器：{weapon}】")
    layers_description = "\n".join(layers_desc)

    # 构建武器描述（只给武器名称和使用意图，不给示例话术）
    weapons_desc = []
    for w in weapons_used:
        weapons_desc.append(f"- {w['name']}（{w['type']}）")
    weapons_description = "\n".join(weapons_desc) if weapons_desc else "（由系统自动选择）"

    # 获取主导欲望
    dominant_desire = user_state.get("dominant_desire", "无")
    dominant_weight = user_state.get("dominant_weight", 0)

    # 构建风格描述（新增）
    style_description = ""
    if style_params:
        prof = style_params.get("professionalism", 0.5)
        empathy = style_params.get("empathy_depth", 0.5)
        logic = style_params.get("logic_density", 0.5)
        spoken = style_params.get("spoken_ratio", 0.5)

        style_parts = []
        if prof > 0.6:
            style_parts.append("保持较高的专业感，用词精准")
        elif prof < 0.4:
            style_parts.append("降低专业感，用日常口语表达")

        if empathy > 0.6:
            style_parts.append("多些共情和理解，先回应感受再给建议")
        elif empathy < 0.4:
            style_parts.append("直接给方案，少些情感铺垫")

        if logic > 0.6:
            style_parts.append("逻辑清晰，条理分明")
        elif logic < 0.4:
            style_parts.append("不必太讲逻辑，先接住情绪")

        if spoken > 0.6:
            style_parts.append("用口语化的表达，像朋友聊天")
        elif spoken < 0.4:
            style_parts.append("可以稍微正式一点")

        if style_parts:
            style_description = "\n【风格要求】\n" + "，".join(style_parts) + "。"

    output_description = ""
    if output_profile:
        output_mode = output_profile.get("mode", "normal")
        output_focus_map = {
            "brief": "短承接，少说两句但别把意思说散",
            "contain": "先接住再收窄，别讲太满",
            "light": "轻一点、短一点，别一口气铺太多",
            "expanded": "可以展开，但先把重点说清，再补必要动作",
            "balanced": "自然展开，但别写得太板",
            "normal": "按自然对话来，不要把话说僵",
        }
        output_focus_text = output_focus_map.get(output_mode, "按自然对话来，不要把话说僵")
        output_pressure_text = {
            "brief": "这一轮不用铺开，够短就行",
            "contain": "这一轮先稳住，别把内容推太满",
            "light": "这一轮轻轻接一下就够",
            "expanded": "这一轮可以展开一点，但别拖成报告",
            "balanced": "这一轮自然说开，但别太散",
            "normal": "这一轮按自然节奏说就行",
        }.get(output_mode, "这一轮按自然节奏说就行")
        output_description = (
            "\n【输出重心】\n"
            f"- 这轮更偏：{output_focus_text}\n"
            f"- 说话力度：{output_pressure_text}\n"
            f"- 提醒：{output_profile.get('prompt_hint', '')}"
        )

    narrative_description = ""
    if narrative_profile:
        narrative_description = (
            "\n【叙事走法】\n"
            f"- 本轮叙事模式：{narrative_profile.get('mode', 'balanced')}\n"
            f"- 原则提醒：{narrative_profile.get('opening_rule', '')}；{narrative_profile.get('ending_rule', '')}\n"
            f"- 提醒：{narrative_profile.get('prompt_hint', '')}"
        )

    layer_flow_description = _build_layer_flow_description(layers)

    # 【修复4A】防御模式约束注入
    system_prompt = SPEECH_SYSTEM_PROMPT
    if forced_weapon_type == "defensive":
        system_prompt += DEFENSIVE_MODE_CONSTRAINTS

    # 构建用户 Prompt
    from modules.memory import (
        extract_state_evolution_hints,
        extract_structured_memory_hints,
        extract_turn_progress_hints,
        extract_world_state_hints,
    )
    safe_input = sanitize_for_prompt(user_input)
    memory_focus = extract_structured_memory_hints(memory_context, limit_per_section=3) if memory_context else ""
    world_state_focus = extract_world_state_hints(memory_context, limit=4) if memory_context else ""
    state_evolution_focus = extract_state_evolution_hints(memory_context, limit=4) if memory_context else ""
    turn_progress_focus = extract_turn_progress_hints(memory_context, limit=5) if memory_context else ""
    user_prompt = SPEECH_USER_PROMPT.format(
        user_input=safe_input,
        identity_hint=identity_hint or "未识别",
        situation_hint=situation_hint or "未识别",
        dialogue_task=dialogue_task or "clarify",
        scene=scene or "default",
        emotion_type=user_state.get("emotion_type", "平静"),
        emotion_intensity=user_state.get("emotion_intensity", 0.5),
        motive=user_state.get("motive", "生活期待"),
        dominant_desire=dominant_desire,
        dominant_weight=dominant_weight,
        dual_core_state=user_state.get("dual_core_state", "同频"),
        mode=strategy_plan.get("mode", "B"),
        stage=strategy_plan.get("stage", ""),
        strategy_description=strategy_plan.get("description", ""),
        layers_description=layers_description,
        weapons_description=weapons_description,
        memory_context=memory_context if memory_context else "（无历史记忆）",
        knowledge_content=knowledge_content if knowledge_content else "（无知识参考）",
    )

    # 【异议处理专项】注入证据数据
    if evidence_content:
        user_prompt += f"\n\n【参考证据】\n{evidence_content}\n\n请在回复中自然地引用上述数据，不要生硬罗列。"

    # 追加风格要求
    if style_description:
        user_prompt += style_description
    if output_description:
        user_prompt += output_description
    if narrative_description:
        user_prompt += narrative_description
    closing_policy_description = _build_closing_policy_description(
        user_input=user_input,
        scene=scene,
        output_profile=output_profile,
        narrative_profile=narrative_profile,
        next_step_policy=next_step_policy,
    )
    task_description = {
        "contain": "\n【本轮主任务】\n- 先接住，再说别的。\n- 不要急着判断、教育、上价值。\n- 如果要问，也只问一个最轻的问题。",
        "clarify": "\n【本轮主任务】\n- 先帮用户把当下问题理清。\n- 别一下子给太多方案，先抓一个关键点。",
        "advance": "\n【本轮主任务】\n- 这轮可以往前推一步。\n- 先说清方向，再给一个可执行的小动作。",
        "reflect": "\n【本轮主任务】\n- 这轮更适合回头看清问题出在哪。\n- 先点破关键，再顺一下后面怎么调。",
    }.get(dialogue_task or "clarify", "")
    if task_description:
        user_prompt += task_description
    if (dialogue_task or "clarify") == "contain":
        contain_opening_policy = _build_contain_opening_policy(
            user_state=user_state,
            identity_hint=identity_hint,
            situation_hint=situation_hint,
            scene=scene,
        )
        if contain_opening_policy:
            user_prompt += contain_opening_policy
    if layer_flow_description:
        user_prompt += layer_flow_description
    expression_policy_description = _build_expression_policy_description(
        scene=scene,
        memory_context=memory_context,
        output_profile=output_profile,
        narrative_profile=narrative_profile,
    )
    if expression_policy_description:
        user_prompt += expression_policy_description
    if closing_policy_description:
        user_prompt += closing_policy_description
    if memory_focus:
        user_prompt += (
            "\n\n【记忆重点】\n"
            f"{memory_focus}\n"
            "【记忆提示】先抓这些重点，不要把整段历史照搬出来。"
        )

    if focus_enabled:
        user_prompt = "\n".join(continuity_lines) + "\n\n" + user_prompt

    if world_state_focus or state_evolution_focus or turn_progress_focus:
        progress_sections: list[str] = []
        if state_evolution_focus:
            progress_sections.append(f"【状态演化】\n{state_evolution_focus}")
        if world_state_focus:
            progress_sections.append(f"【局面状态】\n{world_state_focus}")
        if turn_progress_focus:
            progress_sections.append(f"【下一轮焦点】\n{turn_progress_focus}")
        user_prompt += (
            "\n\n【局面推进】\n"
            "这一轮先顺着已经发生的变化往下走，不要重新开题；如果有下一轮焦点，优先把它接住。\n"
            + "\n".join(progress_sections)
        )

    if memory_context and "【下一轮接话点】" in memory_context:
        user_prompt += (
            "\n\n【接话提示】\n"
            "优先顺着上一轮接话点继续，不要重新开一个新话题；"
            "如果当前用户已经带了新的明确意图，再以当前意图为准。"
        )
    elif memory_context and "【关系闭环摘要】" in memory_context:
        user_prompt += (
            "\n\n【接话提示】\n"
            "优先承接上一轮关系闭环，顺着已经答应过的事往前走，"
            "不要把上一轮刚说完的内容重新打散重讲。"
        )

    # 短句响应约束：必须结合上下文做动态承接，避免模板化确认句
    short_input = len((user_input or "").strip()) <= 3
    quick_ack_set = {"嗯", "好的", "可以", "行", "好", "ok", "OK", "收到", "嗯嗯"}
    if short_input or (user_input or "").strip() in quick_ack_set:
        user_prompt += (
            "\n\n【短句承接规则】\n"
            "当前用户输入是短回应，信息密度低。你必须基于【用户状态】【记忆上下文】和最近对话做承接判断，"
            "输出要体现当前关系推进，不允许只回复“好的/明白/收到/请详细说”等机械确认句。"
        )

    # 【Skills 系统】注入技能专属 Prompt
    if skill_prompt:
        user_prompt += f"\n\n【技能专属指令】\n{skill_prompt}"

    # 【混合调度 3.3C】注入副场景策略指令
    if secondary_scene_strategy:
        user_prompt += f"\n\n【副场景策略】\n{secondary_scene_strategy}"

    # 【叙事驱动话术引擎】注入动态叙事约束
    if narrative_rules:
        user_prompt += f"\n\n【叙事结构指令】\n{narrative_rules}"

    # 信息不足时的温和引导：先承接，再轻问，避免审问感
    if guidance_prompt:
        user_prompt += (
            "\n\n【信息补位引导】\n"
            "当你判断当前信息不足以给出更合适的下一步时，请把下面这句自然融入结尾，"
            "语气要温和、非审问、非表单化，一次只问一个点：\n"
            f"{guidance_prompt}"
        )

    # 可选扩展包必须在最后再收一次边界，避免被销售/叙事惯性带偏。
    if "【可选人格扩展包】" in (skill_prompt or ""):
        user_prompt += (
            "\n\n【可选扩展最终边界】\n"
            "这轮只是手动开启扩展包，主系统判断仍然优先。"
            "扩展只能补思考口径和表达气质，不能抢主系统结论。"
            "不要为了显得具体而编造用户没有提供的功能、服务、客户案例、数字或市场背书。"
            "如果用户没有提供具体产品事实，不要举具体卖点例子，不要说“比如我们有某某服务”。"
            "这种情况下只给表达框架和可替换占位，比如“把你们真实最强的那个价值点讲清楚”。"
            "如果涉及价格或产品价值，优先讲真实价值、体验、适配边界和长期信任，不要使用促销、稀缺、从众、原价现价这类压单套路。"
        )

    return system_prompt, user_prompt


# ===== 话术生成函数 =====

def generate_speech(
    layers: list[dict],
    user_state: dict,
    strategy_plan: dict,
    weapons_used: list[dict],
    memory_context: str = "",
    knowledge_content: str = "",
    style_params: dict | None = None,
    output_profile: dict | None = None,
    narrative_profile: dict | None = None,
    identity_hint: str = "",
    situation_hint: str = "",
    dialogue_task: str = "clarify",
    scene: str = "",
    user_input: str = "",
    forced_weapon_type: str | None = None,
    evidence_content: str = "",
    skill_prompt: str = "",
    secondary_scene_strategy: str = "",
    narrative_rules: str = "",
    guidance_prompt: str = "",
    continuity_focus: dict | None = None,
    next_step_policy: str = "soft",
    runtime_trace: dict | None = None,
    llm_stage: str = "step8_full",
) -> str:
    """
    调用 LLM 生成话术

    Args:
        style_params: 风格参数 {professionalism, empathy_depth, logic_density, spoken_ratio}
        user_input: 用户原始输入
        forced_weapon_type: 强制武器类型 (defensive/gentle/aggressive)

    Returns:
        str: 生成的话术
    """
    from llm.nvidia_client import invoke_deep

    system_prompt, user_prompt = build_speech_prompt(
        layers=layers,
        user_state=user_state,
        strategy_plan=strategy_plan,
        weapons_used=weapons_used,
        memory_context=memory_context,
        knowledge_content=knowledge_content,
        style_params=style_params,
        output_profile=output_profile,
        narrative_profile=narrative_profile,
        identity_hint=identity_hint,
        situation_hint=situation_hint,
        dialogue_task=dialogue_task,
        scene=scene,
        user_input=user_input,
        forced_weapon_type=forced_weapon_type,
        evidence_content=evidence_content,
        skill_prompt=skill_prompt,
        secondary_scene_strategy=secondary_scene_strategy,
        narrative_rules=narrative_rules,
        guidance_prompt=guidance_prompt,
        continuity_focus=continuity_focus,
        next_step_policy=next_step_policy,
    )

    response = invoke_deep(user_prompt, system_prompt, runtime_trace=runtime_trace, stage=llm_stage)
    return response


def generate_speech_fast(
    layers: list[dict],
    user_state: dict,
    strategy_plan: dict,
    weapons_used: list[dict],
    memory_context: str = "",
    knowledge_content: str = "",
    style_params: dict | None = None,
    output_profile: dict | None = None,
    narrative_profile: dict | None = None,
    identity_hint: str = "",
    situation_hint: str = "",
    dialogue_task: str = "clarify",
    scene: str = "",
    user_input: str = "",
    forced_weapon_type: str | None = None,
    evidence_content: str = "",
    skill_prompt: str = "",
    secondary_scene_strategy: str = "",
    narrative_rules: str = "",
    guidance_prompt: str = "",
    continuity_focus: dict | None = None,
    next_step_policy: str = "soft",
    runtime_trace: dict | None = None,
    llm_stage: str = "step8_minimal",
) -> str:
    """
    快速版话术生成（用于沙盒性能压测场景，不改变正式接口语义）。
    """
    from llm.nvidia_client import invoke_fast

    system_prompt, user_prompt = build_speech_prompt(
        layers=layers,
        user_state=user_state,
        strategy_plan=strategy_plan,
        weapons_used=weapons_used,
        memory_context=memory_context,
        knowledge_content=knowledge_content,
        style_params=style_params,
        output_profile=output_profile,
        narrative_profile=narrative_profile,
        identity_hint=identity_hint,
        situation_hint=situation_hint,
        dialogue_task=dialogue_task,
        scene=scene,
        user_input=user_input,
        forced_weapon_type=forced_weapon_type,
        evidence_content=evidence_content,
        skill_prompt=skill_prompt,
        secondary_scene_strategy=secondary_scene_strategy,
        narrative_rules=narrative_rules,
        guidance_prompt=guidance_prompt,
        continuity_focus=continuity_focus,
        next_step_policy=next_step_policy,
    )

    response = invoke_fast(user_prompt, system_prompt, runtime_trace=runtime_trace, stage=llm_stage)
    return response


def generate_speech_stream(
    layers: list[dict],
    user_state: dict,
    strategy_plan: dict,
    weapons_used: list[dict],
    memory_context: str = "",
    knowledge_content: str = "",
    style_params: dict | None = None,
    output_profile: dict | None = None,
    narrative_profile: dict | None = None,
    identity_hint: str = "",
    situation_hint: str = "",
    dialogue_task: str = "clarify",
    scene: str = "",
    user_input: str = "",
    forced_weapon_type: str | None = None,
    evidence_content: str = "",
    skill_prompt: str = "",
    secondary_scene_strategy: str = "",
    narrative_rules: str = "",
    guidance_prompt: str = "",
    continuity_focus: dict | None = None,
    next_step_policy: str = "soft",
    runtime_trace: dict | None = None,
    llm_stage: str = "step8_stream",
):
    """
    流式话术生成：逐 token 返回 LLM 响应
    """
    from llm.nvidia_client import invoke_stream

    system_prompt, user_prompt = build_speech_prompt(
        layers=layers,
        user_state=user_state,
        strategy_plan=strategy_plan,
        weapons_used=weapons_used,
        memory_context=memory_context,
        knowledge_content=knowledge_content,
        style_params=style_params,
        output_profile=output_profile,
        narrative_profile=narrative_profile,
        identity_hint=identity_hint,
        situation_hint=situation_hint,
        dialogue_task=dialogue_task,
        scene=scene,
        user_input=user_input,
        forced_weapon_type=forced_weapon_type,
        evidence_content=evidence_content,
        skill_prompt=skill_prompt,
        secondary_scene_strategy=secondary_scene_strategy,
        narrative_rules=narrative_rules,
        guidance_prompt=guidance_prompt,
        continuity_focus=continuity_focus,
        next_step_policy=next_step_policy,
    )

    yield from invoke_stream(user_prompt, system_prompt, runtime_trace=runtime_trace, stage=llm_stage)


# ===== 升维话术生成 =====

UPGRADE_SPEECH_SYSTEM_PROMPT = """你是用户的"合伙人"，正在用"升维"方式回应对方。

【核心原则】
1. 升维不是否定情绪，而是将情绪能量重新锚定到更高的价值目标上
2. 你是平等的对话者，不是说教者
3. 不分析用户心理，不使用"你的愤怒说明""你其实在乎"等心理分析句式
4. 用愿景、尊严、共同目标来重新定义当前的问题

【表达风格】
- 70%口语 + 30%专业感
- 用"我们"而不是"你"来建立共同体感
- 输出 50-150 字

【维度引导】
- 愿景维度：描绘共同的未来图景，让对方看到方向
- 尊严维度：尊重对方的价值和边界，建立平等协作
- 卓越维度：追求极致，共同进步
- 大爱维度：超越个人利益的关怀，承担社会责任
- 革命维度：挑战陈规，引领变革

【绝对禁止】
- 禁止使用：利用、害怕、恐惧、钩子、五层结构、武器库、八宗罪、Mode A/B/C
- 禁止分析用户心理："你其实是在逃避""你内心深处"
- 禁止说教："你应该""你需要明白"
- 禁止空洞的大道理"""

UPGRADE_SPEECH_USER_PROMPT = """请根据以下信息生成升维话术：

用户输入：{user_input}
用户情绪：{emotion_type}（强度 {emotion_intensity}）
升维维度：{dimension}
策略组合：{combo_name}
策略说明：{combo_description}
武器：{weapon_names}

要求：
1. 将用户的情绪锚定到指定维度的价值目标上
2. 用"我们"建立共同体感
3. 不分析心理，不说教
4. 输出 50-150 字的自然话术"""


def generate_upgrade_speech(
    user_input: str,
    emotion_type: str,
    emotion_intensity: float,
    dimension: str,
    combo_name: str,
    combo_description: str,
    weapons_used: list[dict],
) -> str:
    """
    调用 LLM 生成升维话术

    Args:
        user_input: 用户输入
        emotion_type: 情绪类型
        emotion_intensity: 情绪强度
        dimension: 主导维度（愿景/尊严/卓越/大爱/革命）
        combo_name: 策略组合名称
        combo_description: 策略说明
        weapons_used: 使用的武器列表

    Returns:
        str: 生成的升维话术
    """
    from llm.nvidia_client import invoke_deep

    weapon_names = ", ".join(w.get("name", "") for w in weapons_used)

    user_prompt = UPGRADE_SPEECH_USER_PROMPT.format(
        user_input=user_input,
        emotion_type=emotion_type,
        emotion_intensity=emotion_intensity,
        dimension=dimension,
        combo_name=combo_name,
        combo_description=combo_description,
        weapon_names=weapon_names,
    )

    response = invoke_deep(user_prompt, UPGRADE_SPEECH_SYSTEM_PROMPT)
    return response


# ===== 测试入口 =====

if __name__ == "__main__":
    # 测试 Prompt 构建
    test_layers = [
        {"layer": 1, "name": "即时反应", "weapon": "共情", "purpose": "情绪共振"},
        {"layer": 2, "name": "理解确认", "weapon": "镜像模仿", "purpose": "确认理解"},
        {"layer": 3, "name": "共情支持", "weapon": "正常化", "purpose": "降低焦虑"},
        {"layer": 4, "name": "具体追问", "weapon": "好奇", "purpose": "聚焦问题"},
        {"layer": 5, "name": "方向引导", "weapon": "给予价值", "purpose": "给出选择"},
    ]

    test_user_state = {
        "emotion_type": "挫败",
        "emotion_intensity": 0.7,
        "motive": "回避恐惧",
        "dominant_desire": "fear",
        "dominant_weight": 0.8,
        "dual_core_state": "对抗",
    }

    test_strategy = {
        "mode": "A",
        "stage": "钩子",
        "description": "消除恐惧+激活贪婪",
    }

    test_weapons = [
        {"name": "共情", "type": "温和型", "example": "这压力确实大"},
        {"name": "正常化", "type": "温和型", "example": "换谁都会这样"},
    ]

    system, user = build_speech_prompt(
        layers=test_layers,
        user_state=test_user_state,
        strategy_plan=test_strategy,
        weapons_used=test_weapons,
    )

    print("=== 系统 Prompt ===")
    print(system[:500])
    print("\n=== 用户 Prompt ===")
    print(user)
