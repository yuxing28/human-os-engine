"""Human-OS Engine - 节点辅助函数聚合。"""

import hashlib

from schemas.context import Context
from utils.logger import warning
from graph.nodes.contradiction_check import _check_logical_contradiction
from graph.nodes.style_adapter import _adapt_output_style, _replace_academic_terms, _smart_compress
from graph.nodes.persona_checker import _check_persona_consistency, _rewrite_for_persona
from graph.nodes.strategy_selector import _select_strategy


__all__ = [
    "_check_logical_contradiction",
    "_adapt_output_style",
    "_replace_academic_terms",
    "_smart_compress",
    "_check_persona_consistency",
    "_rewrite_for_persona",
    "_select_strategy",
    "_generate_collapse_output",
    "_generate_upgrade_speech",
    "_fallback_generate_speech",
    "_should_take_task_first_fallback",
    "_is_light_turn",
    "_turn_load_level",
    "_turn_behavior_profile",
    "_update_trust_level",
    "_record_strategy_to_library",
    "_record_scene_evolution",
    "_evaluate_strategy_experience",
    "_extract_session_notes",
    "_advance_mode_sequence",
    "_generate_history_summary",
    "_build_memory_material_summary",
]


def _generate_collapse_output(context) -> str:
    """生成系统崩溃时的修复话术（基于 25-崩溃模型）。"""
    inner = context.self_state.energy_allocation.inner
    mode = context.self_state.energy_mode
    latest_meta = context.history[-1].metadata if context.history else {}
    collapse_stage = latest_meta.get("collapse_stage")

    if collapse_stage == "inner_exhaustion":
        return "我们先别继续往前推了。现在更重要的不是多做，而是先把状态稳住。先只留一个最小目标，其他事情先放一放。"
    if collapse_stage == "outer_damage":
        return "我先帮你把范围收窄一点。我们这轮只处理一个核心问题，其他先不接，这样你不会再被一堆东西同时拉扯。"
    if collapse_stage == "attention_hijack":
        return "先别再铺新信息了。我们把干扰先压下去，只盯住眼前最可控的一件事，这样会快很多。"
    if inner < 0.3 or mode.value == "C":
        return "我需要先停一下。连续几轮效果都不好，说明方法有问题。你可以先记录下你的核心诉求，我调整一下状态再继续。"
    if inner < 0.5:
        return "我注意到我们有点在绕圈子。让我先设定一个边界：我们只聚焦一个核心问题，其他先放一放。你最想解决的是什么？"
    return "我建议我们先停一下，关掉不必要的干扰，只专注这一件事。你现在的核心诉求是什么？"


def _generate_upgrade_speech(user_input: str, context: Context) -> str:
    """Mode C 升维话术：用愿景/尊严将情绪锚定到共同目标。"""
    import random

    user_emotion = context.user.emotion.type.value if hasattr(context.user.emotion.type, "value") else str(context.user.emotion.type)
    anger_templates = [
        "我理解你的愤怒，因为我们都是希望这件事做到最好。你提到的这些问题，其实说明你在乎结果。让我们一起看看怎么把它做好。",
        "你的标准很高，这恰恰是我尊重的地方。现在的问题不是谁对谁错，而是我们怎么一起把这件事推到你期待的样子。",
        "你的不满说明你在意。我们换个角度，你最在意的到底是哪一点？把这个理清楚，其他的都好办。",
        "你说的这些我都听到了。我能感觉到你不是在发脾气，而是真的觉得这件事可以更好。那我们聚焦一个问题来解决，你选哪个？",
    ]
    fear_templates = [
        "面对不确定，很多人都会怕。但正是这种挑战，让我们有机会突破自己。",
        "担心是正常的，说明你在认真对待。我们一起把风险列出来，看看哪些是真实的，哪些是想象的。",
        "你的顾虑我理解。我们不用一下子做决定，先弄清楚最坏的情况是什么，再看值不值得冒这个险。",
    ]
    default_templates = [
        "我们回到最初的目标，看看怎么一起解决这个问题。",
        "不管之前怎么聊的，现在最重要的是：你到底想达成什么？",
        "我不会说服你做任何你不想做的事。但我们至少可以理清思路，看看有没有更好的选择。",
    ]

    if user_emotion in ["愤怒", "急躁"]:
        return random.choice(anger_templates)
    if user_emotion in ["恐惧", "挫败"]:
        return random.choice(fear_templates)
    return random.choice(default_templates)


def _stable_reply_variant(options: list[str], *, seed_text: str) -> str:
    """根据上下文做稳定轮换，避免每次都固定一句。"""
    if not options:
        return ""
    digest = hashlib.md5((seed_text or "").encode("utf-8")).hexdigest()
    index = int(digest[:8], 16) % len(options)
    return options[index]


def _build_task_first_fallback(context: Context, user_input: str) -> str:
    """主任务优先的轻量兜底，避免承接轮一上来就空泛。"""
    dialogue_task = getattr(context, "dialogue_task", "")
    dialogue_task_reason = getattr(context, "dialogue_task_reason", "")
    relationship_position = getattr(context.user, "relationship_position", "") or ""
    situation_hint = getattr(context, "situation_hint", "") or ""
    scene = getattr(context, "primary_scene", "") or ""
    emotion_type = context.user.emotion.type.value if hasattr(context.user.emotion.type, "value") else str(context.user.emotion.type)

    if dialogue_task != "contain":
        return ""

    text = (user_input or "").strip()

    if dialogue_task_reason == "repair_after_missed_attunement":
        active_topic = getattr(getattr(context, "dialogue_frame", None), "active_topic", "") or ""
        if active_topic:
            repair_options = [
                f"你说得对，我刚才没接住重点。我们回到你原本问的这件事：{active_topic}。我先不换题，直接按这个问题往下拆。",
                f"行，这里我收回来。你不是要听一套空话，你是在问：{active_topic}。我接下来就围绕这个讲具体做法。",
                f"确实，刚才那样回不行。重点应该回到：{active_topic}。我们先按这个问题本身处理，不再绕到别的方向。",
            ]
            seed = f"{context.session_id}|frame_repair|{text}|{active_topic}|{len(context.history)}"
            return _stable_reply_variant(repair_options, seed_text=seed)

        repair_options = [
            "行，我刚才那句说偏了，不是你没情绪，是我没接住。被那样一压，烦和委屈一起上来很正常。你现在更偏哪边？",
            "好，我收一下，刚才那句确实没跟上你。你不是没反应，是那一下把你顶着了。你现在更偏委屈，还是更偏火大？",
            "嗯，我刚才那句说得不对，问题不在你，是我没接住那股劲。被那样一压，心里冒火也正常。你现在更靠近烦，还是更靠近委屈？",
            "行，这里算我刚才说偏了。你不是在随口说，是那一下真的把你惹到了。你现在更明显的是堵得慌，还是火上来了？",
        ]
        recent_system_turn = ""
        for item in reversed(context.history):
            if item.role == "system":
                recent_system_turn = (item.content or "").strip()
                break
        seed = f"{context.session_id}|repair|{text}|{recent_system_turn}|{len(context.history)}"
        return _stable_reply_variant(repair_options, seed_text=seed)

    work_hurt = (
        dialogue_task_reason == "workplace_hurt_first"
        or
        "下级-上级" in relationship_position
        or "上级-下级" in relationship_position
        or situation_hint == "职场受挫"
        or (scene == "management" and dialogue_task == "contain")
    )
    if work_hurt:
        return "这一下确实会很难受，尤其还是在工作里被上级直接压了一下。你现在更难受的是委屈，还是有点怪自己没做好？"

    user_turns = sum(1 for item in context.history if item.role == "user")
    has_second_person_target = any(token in text for token in ["你", "你这", "你是不是", "你根本", "你又"])
    vague_emotion_opening = (
        user_turns <= 1
        and len(text) <= 18
        and not has_second_person_target
    )
    if vague_emotion_opening:
        return "行，那今天就聊这个。你先别急着总结，先说说今天最堵你的那一下是什么。"

    if emotion_type not in {"", "平静"}:
        return "这一下确实会堵得慌。你现在更难受的是心里委屈，还是整个人有点乱？"

    return "这一下听着就不太舒服。你现在心里最卡的是哪一下？"


def _recent_user_turns(context: Context, limit: int = 4) -> list[str]:
    turns: list[str] = []
    for item in reversed(context.history):
        if item.role == "user":
            turns.append((item.content or "").strip())
            if len(turns) >= limit:
                break
    return turns


def _has_compensation_topic(text: str) -> bool:
    markers = [
        "涨工资", "涨薪", "加薪", "薪资", "工资", "薪水", "待遇", "调薪",
        "薪酬", "收入", "年终奖", "奖金",
    ]
    return any(marker in text for marker in markers)


def _has_upward_authority(text: str) -> bool:
    markers = ["老板", "领导", "主管", "经理", "上级", "公司", "hr", "HR"]
    return any(marker in text for marker in markers)


def _is_followup_request(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    markers = [
        "具体", "怎么做", "怎么说", "咋说", "话术", "然后呢", "下一步",
        "继续", "细说", "展开", "开口", "怎么谈", "怎么办",
    ]
    return len(stripped) <= 18 and any(marker in stripped for marker in markers)


def _is_upward_negotiation_context(context: Context, user_input: str) -> bool:
    """
    识别“向上谈个人利益/薪资”的任务。

    这不是团队管理，也不是销售转化；它的核心是低位一方向权力方提出利益调整。
    """
    text = (user_input or "").strip()
    if not text:
        return False

    if _has_compensation_topic(text) and (_has_upward_authority(text) or "涨" in text):
        return True

    relationship_position = getattr(context.user, "relationship_position", "") or ""
    if _has_compensation_topic(text) and relationship_position == "下级-上级":
        return True

    if _is_followup_request(text):
        for previous in _recent_user_turns(context):
            if previous == text:
                continue
            if _has_compensation_topic(previous) and (_has_upward_authority(previous) or "涨" in previous):
                return True

    goal_text = getattr(getattr(context, "goal", None).current, "description", "") if getattr(context, "goal", None) else ""
    if _is_followup_request(text) and _has_compensation_topic(goal_text):
        return True

    return False


def _has_recent_upward_negotiation(context: Context) -> bool:
    goal_text = getattr(getattr(context, "goal", None).current, "description", "") if getattr(context, "goal", None) else ""
    if _has_compensation_topic(goal_text):
        return True
    return any(
        _has_compensation_topic(turn) and (_has_upward_authority(turn) or "涨" in turn)
        for turn in _recent_user_turns(context)
    )


def _has_prior_upward_negotiation(context: Context, current_text: str) -> bool:
    current = (current_text or "").strip()
    for turn in _recent_user_turns(context):
        if turn == current:
            continue
        if _has_compensation_topic(turn) and (_has_upward_authority(turn) or "涨" in turn):
            return True
    return False


def _build_upward_negotiation_reply(context: Context, user_input: str) -> str:
    """向上谈判/涨薪的轻量直出：不走项目推进模板。"""
    if not _is_upward_negotiation_context(context, user_input):
        return ""

    text = (user_input or "").strip()
    if _is_followup_request(text) and _has_prior_upward_negotiation(context, text):
        options = [
            "可以，具体就按三步来：先列你最近做出的结果，再定一个你能说出口的涨薪区间，最后约老板单独聊。开场可以说：“我想和您单独聊一下我最近的工作结果，以及薪资调整的可能性。”",
            "具体做法是先准备一页纸：你负责了什么、结果是什么、比以前多承担了什么、你希望调整到多少。谈的时候别绕，先讲贡献，再说期待，最后问老板这件事怎么进入评估流程。",
            "你可以这样推进：先别在情绪上开口，先把证据备好。然后找一个不忙的时间说：“我想复盘一下近期贡献，也想讨论一下薪资是否有调整空间。”这句话比直接问“能不能涨工资”稳很多。",
        ]
        seed = f"{context.session_id}|salary_followup|{text}|{len(context.history)}"
        return _stable_reply_variant(options, seed_text=seed)

    options = [
        "这件事不要直接冲上去要钱，先按向上谈判来。你先准备三样东西：最近的具体贡献、可对标的岗位价值、你想要的涨薪区间。跟老板聊时先讲结果，再讲期待。",
        "可以谈，但别只说“我想涨工资”。更稳的顺序是：我最近承担了什么、带来了什么结果、现在薪资和贡献哪里不匹配、我希望怎么调整。这样老板更容易进入讨论。",
        "这不是简单要钱，是一次向上沟通。先把你的价值证据摆出来，再提出一个明确但可谈的区间。不要在被骂或情绪上头时谈，挑一个老板能听进去的时间。",
    ]
    seed = f"{context.session_id}|salary_initial|{text}|{len(context.history)}"
    return _stable_reply_variant(options, seed_text=seed)


def _build_management_advance_reply(context: Context, user_input: str) -> str:
    """管理推进轮的轻量直出：先定卡点，再落一个小动作。"""
    scene = getattr(context, "primary_scene", "") or ""
    dialogue_task = getattr(context, "dialogue_task", "") or ""
    if dialogue_task != "advance" or scene != "management":
        return ""
    if _is_upward_negotiation_context(context, user_input):
        return ""

    options = [
        "这件事先别摊太大。你先抓一个点：现在项目最卡的是人、时间，还是目标没对齐。先把这个问清，再定下一步谁负责、什么时候回看。",
        "先别急着全面推进。你可以先做一个小对齐：把当前目标、最卡环节、负责人和回看时间放到一张纸上。先让大家对同一件事有共识。",
        "这轮先落小一点。先确认三件事：目标是不是一致，卡点在哪里，谁能推动第一步。确认完，再给老板回一个清楚的下一步安排。",
    ]
    seed = f"{context.session_id}|management_advance|{user_input}|{len(context.history)}"
    return _stable_reply_variant(options, seed_text=seed)


def _build_frame_direct_reply(context: Context, user_input: str) -> str:
    """按对话框架直答：不按行业词命中，只按当前议题和用户动作承接。"""
    frame = getattr(context, "dialogue_frame", None)
    if not frame:
        return ""

    dialogue_task = getattr(context, "dialogue_task", "")
    if dialogue_task != "advance":
        return ""

    topic = (getattr(frame, "active_topic", "") or user_input or "").strip()
    user_act = getattr(frame, "user_act", "") or "new_topic"
    if not topic:
        return ""

    if user_act == "followup_detail":
        options = [
            f"可以，咱们就围绕这件事拆具体步骤：{topic}。第一步先把你的目标说清，第二步准备能支撑你的事实，第三步找一个合适场合开口。不要一上来把话说死，先把讨论空间打开。",
            f"具体做法可以分三步：先写清楚你想要什么，再列出为什么现在适合谈，最后准备一句开场白。重点是别绕，也别只表达情绪，要让对方听到事实、诉求和下一步。",
            f"这件事具体别急着硬冲。先准备一份很短的依据，再想好你能接受的结果区间，最后约一个能认真聊的时间。开口时先讲背景和事实，再说你的请求。",
        ]
        seed = f"{context.session_id}|frame_followup|{topic}|{len(context.history)}"
        return _stable_reply_variant(options, seed_text=seed)

    if user_act == "new_topic":
        options = [
            f"可以，这事先别急着做决定。你先抓三点：你真正想要的结果是什么、你手里有什么依据、对方可能卡在哪。三点清楚后，再选一个最稳的开口方式。",
            f"这件事能做，但不要凭感觉冲。先把目标、依据、风险三个东西摆出来。目标决定你怎么说，依据决定对方会不会听，风险决定你要留多少余地。",
            f"先把这件事当成一次沟通设计。第一步定目标，第二步准备事实，第三步设计开场。你只要先把这三步理顺，后面就不会乱。"
        ]
        seed = f"{context.session_id}|frame_new|{topic}|{len(context.history)}"
        return _stable_reply_variant(options, seed_text=seed)

    return ""


def _build_continuity_focus_fallback(
    *,
    user_input: str,
    continuity_focus: dict | None,
    next_step_policy: str = "soft",
) -> str:
    focus = continuity_focus if isinstance(continuity_focus, dict) else {}
    if not focus or not focus.get("memory_use_required"):
        return ""

    focus_type = str(focus.get("focus_type", "") or "none")
    anchor = str(focus.get("anchor", "") or "").strip()
    next_pickup = str(focus.get("next_pickup", "") or "").strip()
    world_state_hint = str(focus.get("world_state_hint", "") or "").strip()
    relationship_hint = str(focus.get("relationship_hint", "") or "").strip()

    if focus_type == "preference":
        if "建议" in user_input:
            return "结论先说：先抓最关键的一步，不要一下子铺太开。你现在先把问题压到一个可执行动作上，再决定要不要继续展开。"
        if "分析" in user_input:
            return "先给结论：别急着铺很多层，先把最关键的判断抓出来。你先看清现在到底卡在哪，再决定要不要往下拆原因。"
        return "先说结论：别铺太开，先抓最关键的一步。你现在先把问题压到一个能立刻执行的动作上，再决定要不要往下展开。"

    if focus_type == "project_state":
        if "下一步" in user_input or "今天要做什么" in user_input:
            return "先按“这周收口”来排。下一步不要再扩方案，先把客户压价这件事处理掉：守住价格底线，只留条件式让步空间。"
        if "还压价" in user_input:
            return "如果对方还压价，这轮先别松底线。前面你已经定了先处理压价、守住价格，所以更稳的做法是先守价格，再把任何让步都绑定到条件上。"
        state_hint = anchor or next_pickup or world_state_hint
        if state_hint:
            return f"先按你现在这条主线来：{state_hint}。这轮别再铺新方向，先把眼前最关键的一步定下来，再往后推。"
        return "先别把事情摊大。这轮就围绕你现在最急的项目状态走，先定一个最关键的动作，不要给泛泛步骤。"

    if focus_type in {"sales_context", "negotiation_context"}:
        state_hint = anchor or next_pickup or world_state_hint
        if "让一点" in user_input or "守价格" in user_input or "压价" in user_input:
            return "现在不建议直接让价。前面已经有压价、再考虑和竞品更便宜这些压力了，你可以先守住价格，但把让步变成条件：只有对方确认时间、数量或付款条件，再谈一点空间。"
        if "怎么回" in user_input or "怎么接" in user_input:
            return "先别急着解释太多。前面这轮核心还是客户嫌贵，所以你先稳住价格锚点，再把讨论往价值和条件上带，不要一上来就掉到让价。"
        if state_hint:
            return f"顺着前面的局面往下接，别重新开题。现在核心还是“{state_hint}”，所以这轮先围绕这个卡点给下一步，不要泛泛说看情况。"
        return "这轮别从零开始。先承接前面的客户反馈，再给一个具体下一步，不要只说“看情况再定”。"

    if focus_type == "management_relation":
        relation_anchor = relationship_hint or anchor or next_pickup or world_state_hint
        if "先批评还是先问情况" in user_input:
            return "先问情况，再收标准。你现在有火是正常的，但这轮如果直接批评，关系很容易顶僵。先把对方最近的压力和卡点问出来，再把交付标准收紧。"
        if "压力很大" in user_input:
            return "这轮先别急着压标准，先把对方的压力和卡点问清。你前面已经担心关系会被顶僵，所以更稳的顺序是先问情况，再把要求收回来。"
        if relation_anchor:
            return f"这轮先别只看对错，关系和承受度也要一起保住。你前面卡住的点还是“{relation_anchor}”，所以先稳住对话，再落要求。"
        return "这轮要把关系风险一起算进去。别一上来就给强硬管理话术，先稳住人，再把标准说清。"

    if focus_type == "crisis_recovery":
        return "你刚刚才从很危险、很乱的状态里缓下来，现在还有点怕是正常的。先别急着分析问题，也先别谈项目；这一轮只做一件事：继续待在安全的位置，让身体和呼吸慢一点。"

    if focus_type == "followup":
        if next_pickup and next_step_policy != "none":
            return f"顺着刚才那一步往下接，这轮先抓“{next_pickup}”，不要重新从头铺开。"
        return "这轮就顺着上一轮往下接，先把眼前这一步说清，不要重新从零开始。"

    return ""


def _compact_material_text(text: str, limit: int = 48) -> str:
    value = (text or "").strip().replace("\n", " ").replace("\r", " ")
    return value[:limit].strip(" ，。！？；;:")


def _contains_any_marker(text: str, markers: list[str]) -> bool:
    clean = (text or "").strip()
    return bool(clean) and any(marker in clean for marker in markers)


def _build_memory_material_summary(context: Context, user_input: str, output: str) -> dict:
    """把本轮沉淀成下一轮更好用的判断素材，而不是泛记录。"""
    route_state = getattr(context, "route_state", None) or {}
    if not isinstance(route_state, dict):
        route_state = {}
    policy_state = route_state.get("policy_state", {})
    if not isinstance(policy_state, dict):
        policy_state = {}

    scene = (getattr(context, "primary_scene", "") or (context.scene_config.scene_id if context.scene_config else "") or "").strip().lower()
    text_in = (user_input or "").strip()
    text_out = (output or "").strip()
    combined = f"{text_in} {text_out}".strip()
    conversation_phase = str(route_state.get("conversation_phase", "") or "")
    risk_level = str(route_state.get("risk_level", "") or "")

    material = {
        "scene": scene or "general",
        "situation": "",
        "user_pressure": "",
        "decision_needed": "",
        "suggested_direction": "",
        "avoid_next": "",
        "next_pickup": "",
        "decision_question": "",
        "recommended_answer": "",
        "reason_basis": [],
        "risk_if_wrong": "",
        "next_action": "",
        "first_sentence_bias": "",
    }

    preference_markers = ["直接一点", "先给结论", "不要绕", "少铺垫"]
    if _contains_any_marker(combined, preference_markers):
        material.update({
            "scene": "preference",
            "situation": "用户对表达方式有明确偏好，希望更直接、先给结论、少铺垫。",
            "user_pressure": "不想被绕，也不想先听大段背景。",
            "decision_needed": "下一轮先结论还是先铺背景。",
            "suggested_direction": "先结论，再给理由；少铺垫，不绕。",
            "avoid_next": "不要先追问一堆背景，不要长开场。",
            "decision_question": "下一轮第一句先给结论，还是先铺背景。",
            "recommended_answer": "先给结论，再给理由。",
            "reason_basis": ["用户偏好直接", "用户不喜欢绕", "先追问会显得拖"],
            "risk_if_wrong": "先铺垫或先追问，会让回答显得拖沓。",
            "next_action": "第一句先给明确结论，再补一句理由。",
            "first_sentence_bias": "下一轮第一句倾向：先给结论，再给理由，不要铺垫。",
            "next_pickup": "下一轮第一句倾向：先给结论，再给理由，不要铺垫。",
        })
        return material

    if scene in {"sales", "negotiation"} or _contains_any_marker(combined, ["压价", "太贵", "竞品更便宜", "再考虑", "账期", "守住价格"]):
        material.update({
            "scene": "negotiation" if scene == "negotiation" else "sales",
            "situation": "客户连续用贵、再考虑、竞品更便宜等信号施压，当前卡点在价格和让步边界。",
            "user_pressure": "用户倾向守价格，但担心继续顶住会谈崩。",
            "decision_needed": "下一轮先判断守价格还是条件式让步。",
            "suggested_direction": "先守价格，只有对方给明确承诺时才条件式让步。",
            "avoid_next": "不要先追问背景，不要直接建议降价，不要泛泛说看情况。",
            "decision_question": "下一轮先判断守价格还是让一点。",
            "recommended_answer": "先守价格，不直接让；只有对方确认时间、数量、付款等条件时，才条件式让步。",
            "reason_basis": ["客户连续说贵", "对方多次说再考虑", "竞品更便宜被拿来压价"],
            "risk_if_wrong": "直接让价会把底线打薄，还会让对方继续试探。",
            "next_action": "先回应价值和边界，再抛条件式交换。",
            "first_sentence_bias": "下一轮第一句倾向：先守价格，不直接让；如果要让，也必须绑定明确条件。",
            "next_pickup": "下一轮第一句倾向：先守价格，不直接让；如果要让，也必须绑定明确条件。",
        })
        return material

    if scene == "management" or policy_state.get("has_relationship_risk") or _contains_any_marker(combined, ["执行力差", "事情总是拖", "有点火", "不想直接骂人", "不想伤关系", "压力很大"]):
        material.update({
            "scene": "management",
            "situation": "团队执行力差、事情拖，当前不是信息不够，而是管理开口方式容易伤关系。",
            "user_pressure": "用户有火，但不想一上来把关系顶僵；同时担心对方也可能有压力。",
            "decision_needed": "下一轮先判断先问情况还是先批评。",
            "suggested_direction": "先问压力和卡点，再收交付标准。",
            "avoid_next": "不要直接强硬批评，不要泛泛管理建议，不要跑成上级压用户。",
            "decision_question": "下一轮先问情况还是先批评。",
            "recommended_answer": "先问情况，再收标准。",
            "reason_basis": ["执行力差和事情拖已持续", "用户有火但不想伤关系", "对方可能有压力"],
            "risk_if_wrong": "一上来批评会让关系顶僵，后面更难推进。",
            "next_action": "用低冲突开场先问卡点，再把交付时间和标准收紧。",
            "first_sentence_bias": "下一轮第一句倾向：先问情况，再收标准，不要一上来批评。",
            "next_pickup": "下一轮第一句倾向：先问情况，再收标准，不要一上来批评。",
        })
        return material

    if risk_level == "crisis" or conversation_phase in {"crisis_continuation", "crisis_recovery"} or policy_state.get("is_crisis_recovery"):
        material.update({
            "scene": "crisis_recovery",
            "situation": "用户刚从高风险情绪中缓下来，现在没有现实危险，但情绪余波还在。",
            "user_pressure": "仍然害怕、发虚，不适合转业务或立刻分析。",
            "decision_needed": "下一轮先判断如何继续稳住安全感。",
            "suggested_direction": "先承接刚缓过来和仍害怕，只做安全连续性支持。",
            "avoid_next": "不要转业务，不要泛泛安慰，不要把它讲成普通情绪问题。",
            "decision_question": "下一轮先判断如何继续稳住安全感，而不是分析问题。",
            "recommended_answer": "先确认现在没有现实危险，再做一个很小的稳定动作，不转业务。",
            "reason_basis": ["用户刚从高风险状态缓下来", "现在没有现实危险", "仍然有害怕感"],
            "risk_if_wrong": "过早分析或转业务会让压力重新上来。",
            "next_action": "陪用户继续待在安全位置，必要时联系现实支持。",
            "first_sentence_bias": "下一轮第一句倾向：你刚刚才缓下来，现在怕是正常的；先继续保持安全。",
            "next_pickup": "下一轮第一句倾向：你刚刚才缓下来，现在怕是正常的；先继续保持安全。",
        })
        return material

    if _contains_any_marker(combined, ["项目", "这周必须收口", "先处理客户压价", "守住价格", "不再继续让步", "下周三之前必须回复"]):
        material.update({
            "scene": "project_state",
            "situation": "当前项目节奏紧，目标是尽快收口，主要阻力落在客户压价和推进节奏上。",
            "user_pressure": "用户既想收口，又担心让步过多把底线打薄。",
            "decision_needed": "下一轮先判断怎么围绕收口节奏安排动作。",
            "suggested_direction": "优先处理客户压价，守住价格底线，不继续无条件让步。",
            "avoid_next": "不要给泛泛计划，不要重新问项目背景。",
            "decision_question": "下一轮先判断今天围绕收口先做哪几步。",
            "recommended_answer": "今天先处理压价并推动收口，先守价格，再发跟进，再设回看时间。",
            "reason_basis": ["项目这周必须收口", "客户压价是当前主要阻力", "用户决定守住价格"],
            "risk_if_wrong": "继续泛整理会拖延收口，还可能被对方继续压价。",
            "next_action": "今天先定价格底线、发跟进信息、约一个回看时间。",
            "first_sentence_bias": "下一轮第一句倾向：今天先做三件事，先定底线、发跟进、约回看。",
            "next_pickup": "下一轮第一句倾向：今天先做三件事，先定底线、发跟进、约回看。",
        })
        return material

    return material


def _fallback_generate_speech(
    layers: list[dict],
    user_input: str,
    weapons_used: list[dict],
    context: Context | None = None,
    continuity_focus: dict | None = None,
    next_step_policy: str = "soft",
) -> str:
    """Fallback 话术生成（LLM 失败时使用）。"""
    if context is not None:
        focus_direct = _build_continuity_focus_fallback(
            user_input=user_input,
            continuity_focus=continuity_focus,
            next_step_policy=next_step_policy,
        )
        if focus_direct:
            return focus_direct

        management_advance = _build_management_advance_reply(context, user_input)
        if management_advance:
            return management_advance

        frame_direct = _build_frame_direct_reply(context, user_input)
        if frame_direct:
            return frame_direct

        task_first = _build_task_first_fallback(context, user_input)
        if task_first:
            return task_first

    output_parts = []

    for layer in layers:
        layer_num = layer["layer"]
        weapon_name = layer["weapon"]

        if layer_num == 1:
            if weapon_name == "共情":
                output_parts.append("这压力确实大。")
            elif weapon_name == "直接指令":
                output_parts.append("没问题。")
            elif weapon_name == "沉默":
                output_parts.append("...")
            else:
                output_parts.append("嗯。")
        elif layer_num == 2:
            output_parts.append(f"所以你是说{user_input[:20]}，对吗？")
        elif layer_num == 3:
            if weapon_name == "正常化":
                output_parts.append("换谁都会这样。")
            elif weapon_name == "赋予身份":
                output_parts.append("你能意识到这个问题，已经很厉害了。")
            else:
                output_parts.append("我理解。")
        elif layer_num == 4:
            output_parts.append("最卡的是哪一步？")
        elif layer_num == 5:
            if weapon_name == "选择权引导":
                output_parts.append("你是想先解决A，还是先处理B？")
            elif weapon_name == "给予价值":
                output_parts.append("要不要我帮你看看？")
            else:
                output_parts.append("我们一步步来。")

    return " ".join(output_parts)


def _should_take_task_first_fallback(context: Context, user_input: str, scene: str) -> bool:
    """统一判断当前这轮是否该走主任务优先的轻量承接。"""
    text = (user_input or "").strip()
    if not text:
        return True

    dialogue_task = getattr(context, "dialogue_task", "")
    frame = getattr(context, "dialogue_frame", None)
    frame_act = getattr(frame, "user_act", "") if frame else ""
    if dialogue_task == "advance" and frame_act in {"new_topic", "followup_detail"} and len(text) <= 48:
        return True

    if dialogue_task == "advance" and scene == "management":
        return True

    if dialogue_task != "contain":
        return False

    relationship_position = getattr(context.user, "relationship_position", "") or ""
    situation_hint = getattr(context, "situation_hint", "") or ""
    repair_turn = getattr(context, "dialogue_task_reason", "") == "repair_after_missed_attunement"
    workplace_hurt_turn = getattr(context, "dialogue_task_reason", "") == "workplace_hurt_first"
    work_hurt = (
        len(text) <= 40
        and (
            workplace_hurt_turn
            or
            "下级-上级" in relationship_position
            or "上级-下级" in relationship_position
            or situation_hint == "职场受挫"
            or scene == "management"
        )
    )
    user_turns = sum(1 for item in context.history if item.role == "user")
    has_second_person_target = any(token in text for token in ["你", "你这", "你是不是", "你根本", "你又"])
    open_emotion_opening = user_turns <= 1 and len(text) <= 18 and not has_second_person_target
    return repair_turn or work_hurt or open_emotion_opening


def _is_light_direct_reply(context: Context) -> bool:
    """轻量直出回复不阻塞做重反馈。"""
    dialogue_task = getattr(context, "dialogue_task", "")
    dialogue_task_reason = getattr(context, "dialogue_task_reason", "")
    scene = getattr(context, "primary_scene", "") or ""
    return (
        dialogue_task_reason in {"workplace_hurt_first", "repair_after_missed_attunement"}
        or (dialogue_task == "advance" and getattr(getattr(context, "dialogue_frame", None), "user_act", "") in {"new_topic", "followup_detail"})
        or (dialogue_task == "advance" and scene == "management")
    )


def _is_light_turn(context: Context, user_input: str, scene: str = "") -> bool:
    """统一判断这轮是不是该按轻路径处理。"""
    text = (user_input or "").strip()
    if not text:
        return True

    if getattr(context, "short_utterance", False):
        return True

    if _is_light_direct_reply(context):
        return True

    if _should_take_task_first_fallback(context, text, scene):
        return True

    dialogue_task = getattr(context, "dialogue_task", "")
    frame_act = getattr(getattr(context, "dialogue_frame", None), "user_act", "") or ""
    response_mode = getattr(context, "response_mode", "ordinary")

    ack_like = text in {"嗯", "嗯嗯", "好", "好的", "行", "可以", "收到", "ok", "OK"}
    if dialogue_task == "advance" and frame_act in {"new_topic", "followup_detail"}:
        return response_mode != "deep" and ack_like

    if response_mode != "deep":
        if ack_like:
            return True
        return len(text) <= 8 and not any(ch in text for ch in "？?！!") and not any(
            token in text for token in [
                "怎么办", "怎么做", "怎么说", "下一步", "具体", "细说", "展开",
                "项目", "老板", "客户", "工资", "涨薪", "关系", "沟通", "方案", "安排",
            ]
        )

    return False


def _turn_load_level(context: Context, user_input: str, scene: str = "") -> str:
    """把这一轮分成 light / medium / heavy 三档。"""
    text = (user_input or "").strip()
    if not text:
        return "light"

    if _is_light_turn(context, text, scene):
        return "light"

    response_mode = getattr(context, "response_mode", "ordinary")
    dialogue_task = getattr(context, "dialogue_task", "")
    frame_act = getattr(getattr(context, "dialogue_frame", None), "user_act", "") or ""
    has_question = any(ch in text for ch in "？?")
    has_action = any(token in text for token in ["怎么办", "怎么做", "如何", "下一步", "推进", "方案", "计划", "安排", "处理"])
    has_emotion = any(token in text for token in ["委屈", "难受", "崩", "烦", "气", "骂", "不开心", "想哭"])
    has_context_anchor = any(token in text for token in ["老板", "项目", "客户", "团队", "关系", "沟通", "结果", "工资", "涨薪", "合作"])
    has_uncertainty = any(token in text for token in ["有点", "还没想好", "先别", "不确定", "拿不准", "说不清", "还不清楚", "先看看"])
    task_request = _looks_like_task_request(text)

    if response_mode == "deep" or dialogue_task == "advance" or frame_act in {"followup_detail", "new_topic"}:
        if len(text) >= 24 or has_action or has_emotion or has_context_anchor or (has_question and len(text) >= 10):
            return "heavy"
        if has_uncertainty:
            return "medium"
        if has_question or task_request:
            return "medium"
        return "medium"

    if has_action or has_emotion:
        if has_context_anchor or len(text) >= 12:
            return "medium"
        return "light"

    if has_question:
        if has_context_anchor or len(text) >= 8 or task_request:
            return "medium"
        return "light"

    if has_uncertainty:
        return "medium"

    if has_context_anchor:
        if len(text) >= 8 or task_request:
            return "medium"
        return "light"

    if task_request or len(text) >= 18:
        return "medium"

    return "light"


def _looks_like_task_request(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    markers = [
        "具体", "怎么做", "怎么说", "咋说", "话术", "然后呢", "下一步",
        "继续", "细说", "展开", "开口", "怎么谈", "怎么办", "如何", "安排",
    ]
    return any(marker in stripped for marker in markers)


def _turn_behavior_profile(context: Context, user_input: str, scene: str = "") -> dict[str, str | bool]:
    """把轻中重、后处理、学习阈值放到一处，避免各层自己猜。"""
    level = _turn_load_level(context, user_input, scene)
    return {
        "level": level,
        "minimize_post_processing": level in {"light", "medium"},
        "skip_heavy_memory": level == "light",
    }


def _update_trust_level(context: Context):
    """动态更新用户信任等级。"""
    from schemas.enums import TrustLevel

    feedback = context.last_feedback
    current = context.user.trust_level

    trust_order = [TrustLevel.LOW, TrustLevel.MEDIUM, TrustLevel.HIGH]
    current_idx = trust_order.index(current) if current in trust_order else 1
    feedback_str = feedback.value if hasattr(feedback, "value") else feedback

    if feedback_str == "positive":
        new_idx = min(current_idx + 1, len(trust_order) - 1)
    elif feedback_str == "negative":
        new_idx = max(current_idx - 1, 0)
    else:
        medium_idx = trust_order.index(TrustLevel.MEDIUM)
        if current_idx < medium_idx:
            new_idx = current_idx + 1
        elif current_idx > medium_idx:
            new_idx = current_idx - 1
        else:
            new_idx = current_idx

    context.user.trust_level = trust_order[new_idx]


def _record_strategy_to_library(context: Context, user_input: str):
    """将有效/无效策略记录到策略库/反例库。"""
    from datetime import datetime
    from modules.L5.evaluator import StrategyRecord, record_effective_strategy, record_counter_example, evaluate_response

    strategy_plan = context.current_strategy
    if not strategy_plan.mode_sequence and not strategy_plan.stage:
        return

    if strategy_plan.mode_sequence:
        mode_str = "→".join(m.value for m in strategy_plan.mode_sequence)
    else:
        mode_str = str(context.self_state.energy_mode.value)

    eval_score = 0.0
    try:
        eval_result = evaluate_response(context, context.output, user_input)
        eval_score = eval_result.total_score
    except Exception:
        pass

    record = StrategyRecord(
        strategy_name=strategy_plan.stage or "unknown",
        mode=mode_str,
        stage=strategy_plan.stage or "",
        context_summary=user_input[:100],
        output=context.output[:200],
        feedback=context.last_feedback.value if hasattr(context.last_feedback, "value") else str(context.last_feedback),
        score=eval_score,
        timestamp=datetime.now().isoformat(),
    )

    if record.feedback == "positive":
        record_effective_strategy(record)
    elif record.feedback == "negative":
        record_counter_example(record)


def _record_scene_evolution(context: Context):
    """记录场景进化数据（基于对话反馈调整策略权重）。"""
    if not context.scene_config:
        return

    granular_goal = getattr(context.goal, "granular_goal", None)
    if not granular_goal:
        return

    strategy_plan = context.current_strategy
    combo_name = strategy_plan.stage if strategy_plan else "unknown"
    if hasattr(context, "_last_combo_name"):
        combo_name = context._last_combo_name

    feedback = context.last_feedback
    feedback_str = feedback.value if hasattr(feedback, "value") else str(feedback)
    success = feedback_str == "positive"

    emotion_type = context.user.emotion.type.value if hasattr(context.user.emotion.type, "value") else str(context.user.emotion.type)
    emotion_intensity = context.user.emotion.intensity
    trust_val = context.user.trust_level.value if hasattr(context.user.trust_level, "value") else str(context.user.trust_level)
    trust_change = context.last_feedback_trust_change or 0.0
    resistance_type = context.user.resistance.type.value if hasattr(context.user.resistance.type, "value") else str(context.user.resistance.type)
    resistance_intensity = context.user.resistance.intensity
    energy_mode = context.self_state.energy_mode.value if hasattr(context.self_state.energy_mode, "value") else str(context.self_state.energy_mode)
    dual_core_state = context.user.dual_core.state.value if hasattr(context.user.dual_core.state, "value") else str(context.user.dual_core.state)
    desires = context.user.desires.model_dump() if hasattr(context.user.desires, "model_dump") else {}

    rich_context = {
        "emotion": emotion_type,
        "emotion_intensity": emotion_intensity,
        "trust_level": trust_val,
        "trust_change": trust_change,
        "resistance_type": resistance_type,
        "resistance_intensity": resistance_intensity,
        "energy_mode": energy_mode,
        "dual_core_state": dual_core_state,
        "desires": desires,
    }

    try:
        from modules.L5.scene_evolver import SceneEvolver

        evolver = SceneEvolver(context.scene_config.scene_id)
        evolver.record_outcome(granular_goal, combo_name, success, context=rich_context)
        evolver.save_evolved_version()
    except Exception as e:
        warning(f"场景进化记录失败: {e}")


def _evaluate_strategy_experience(context: Context, user_input: str):
    """策略评估与经验沉淀。"""
    if not context.scene_config:
        return

    granular_goal = getattr(context.goal, "granular_goal", None)
    if not granular_goal:
        return

    strategy_plan = context.current_strategy
    if not strategy_plan:
        return

    feedback = context.last_feedback
    feedback_str = feedback.value if hasattr(feedback, "value") else str(feedback)

    weapons_used = []
    if hasattr(context, "_last_weapons_used"):
        weapons_used = context._last_weapons_used

    try:
        from modules.L5.strategy_evaluator import StrategyEvaluator

        evaluator = StrategyEvaluator()
        result = evaluator.evaluate(
            goal_id=granular_goal,
            emotion_type=context.user.emotion.type.value if hasattr(context.user.emotion.type, "value") else str(context.user.emotion.type),
            trust_level=context.user.trust_level.value if hasattr(context.user.trust_level, "value") else str(context.user.trust_level),
            strategy_desc=strategy_plan.description or "未知策略",
            weapons_used=weapons_used,
            feedback=feedback_str,
            user_response_summary=user_input[:100],
        )

        if result:
            experience = {
                "situation": f"目标:{granular_goal} | 情绪:{context.user.emotion.type} | 信任:{context.user.trust_level}",
                "strategy": strategy_plan.combo_name or "动态组合",
                "weapons": weapons_used,
                "score": result["score"],
                "analysis": result["analysis"],
                "suggestion": result["suggestion"],
                "feedback": feedback_str,
            }
            evaluator.save_experience(experience)
    except Exception:
        pass


def _extract_session_notes(context: Context, user_input: str, round_num: int):
    """提取本轮重要决策为会话笔记。"""
    from modules.memory import add_session_note, get_session_memory

    session_id = context.session_id
    feedback_str = context.last_feedback.value if hasattr(context.last_feedback, "value") else str(context.last_feedback)
    energy_mode_val = context.self_state.energy_mode.value if hasattr(context.self_state.energy_mode, "value") else str(context.self_state.energy_mode)
    scene_id = context.scene_config.scene_id if context.scene_config else getattr(context, "primary_scene", "")
    relationship_position = getattr(context.user, "relationship_position", "") or "未识别"
    situation_stage = getattr(context, "situation_stage", "") or "未识别"

    def _to_level(value: float) -> str:
        if value >= 0.75:
            return "high"
        if value >= 0.4:
            return "medium"
        return "low"

    def _find_commitment_excerpt() -> tuple[str, str]:
        sources = [
            ("output", getattr(context, "output", "") or ""),
            ("user_input", user_input or ""),
        ]
        markers = [
            "下一步",
            "接下来",
            "明天",
            "下次",
            "后面",
            "回头",
            "跟进",
            "对齐",
            "确认",
            "我会",
            "我们可以",
            "先把",
            "先做",
            "收口",
            "继续",
        ]
        for source_name, text in sources:
            clean = text.strip()
            if not clean:
                continue
            for marker in markers:
                idx = clean.find(marker)
                if idx >= 0:
                    start = max(0, idx - 6)
                    end = min(len(clean), idx + 22)
                    excerpt = clean[start:end].strip(" ，。！？：:")
                    return source_name, excerpt
        return "", ""

    def _has_marker(text: str, markers: list[str]) -> bool:
        clean = (text or "").strip()
        if not clean:
            return False
        return any(marker in clean for marker in markers)

    def _derive_scene_focus(
        scene_id: str,
        progress_state: str,
        active_goal: str,
        risk: str,
        tension: str,
    ) -> str:
        scene_id = (scene_id or "").strip().lower()
        progress_state = (progress_state or "").strip()
        active_goal = (active_goal or "").strip().lower()
        risk = (risk or "").strip().lower()
        tension = (tension or "").strip().lower()

        if progress_state in {"先观察", "继续观察", "回到修复", "先修复"}:
            return ""
        if risk == "high" or tension == "high":
            return ""

        if "negotiation" in scene_id:
            if "interest_probing" in active_goal:
                return "先把对方最在意的交换条件对齐，再确认下一轮怎么继续谈。"
            if "anchor_reset" in active_goal:
                return "先把最容易达成一致的点放到桌面上，再确认下一轮交换条件。"
            return "先把最容易谈拢的点对齐，再确认下一轮怎么接。"

        if "management" in scene_id:
            if "task_acceptance" in active_goal:
                return "先把当前最卡的一步对齐，再确认谁来接和什么时候回看。"
            if "conflict_resolution" in active_goal:
                return "先把最容易卡住的分歧点说清，再确认下一轮谁先推动。"
            return "先把当前最卡的一步对齐，再确认下一轮怎么接。"

        if "sales" in scene_id:
            if "prove_roi" in active_goal:
                return "先把总账算清，再确认下一轮最想看的结果。"
            if "value_differentiation" in active_goal:
                return "先把最打动对方的价值点对齐，再确认下一轮怎么继续推。"
            if "break_status_quo" in active_goal:
                return "先把最担心的一点说透，再确认下一轮怎么继续看。"
            if "close_deal" in active_goal:
                return "先把风险怎么兜和最小下一步说清，再确认下一轮怎么接。"
            if "multi_threading" in active_goal:
                return "先确认谁是当前关键人，再对齐下一轮往谁那边推进。"
            if "crisis_management" in active_goal:
                return "先把眼前最急的一点稳住，再确认下一轮先补哪块。"
            return "先把对方最在意的一点对齐，再确认下一轮怎么继续推。"

        if "emotion" in scene_id:
            if "identify_unmet_need" in active_goal:
                return "先把最刺痛的那一下说透，再确认下一轮最想先稳住哪一点。"
            if "validate_feeling" in active_goal:
                return "先把最难受的那一块接住，再确认下一轮先顾哪一点。"
            if "deescalate_conflict" in active_goal:
                return "先别争对错，把最卡的那一下放下来，再确认下一轮怎么继续说。"
            if "physiological_soothing" in active_goal:
                return "先把身体和节奏稳住，再确认下一轮先补哪一点。"
            if "safety_screening" in active_goal:
                return "先把最需要稳住的那一点看清，再确认下一轮先顾哪边。"
            return "先把最难受的那一块接住，再确认下一轮先往哪一点继续。"

        return ""

    def _derive_progress_state(
        feedback: str,
        scene_id: str,
        stage: str,
        commitment_excerpt: str,
        active_goal: str,
        risk: str,
        tension: str,
    ) -> str:
        scene_id = (scene_id or "").strip().lower()
        stage = (stage or "").strip()
        active_goal = (active_goal or "").strip()
        risk = (risk or "").strip()
        tension = (tension or "").strip()
        has_commitment = bool((commitment_excerpt or "").strip())
        has_active_goal = bool(active_goal)
        high_pressure = risk == "high" or tension == "high"
        medium_pressure = risk == "medium" or tension == "medium"
        negotiation_scene = "negotiation" in scene_id
        management_scene = "management" in scene_id

        if feedback == "negative":
            if stage == "推进" and not high_pressure and (has_commitment or has_active_goal):
                return "先修复"
            return "回到修复"

        if has_commitment:
            if stage == "收口":
                return "往收口走"
            if stage == "推进":
                return "继续推进"
            if stage == "探索":
                return "继续对齐"
            return "继续推进"

        if feedback == "positive":
            if stage in {"推进", "收口"}:
                return "继续推进"
            if stage == "探索" and not medium_pressure and (has_active_goal or has_commitment):
                return "继续对齐"
            if (negotiation_scene or management_scene) and has_active_goal and not high_pressure:
                return "继续对齐"
            return "继续观察"

        if stage == "收口" and not high_pressure:
            return "往收口走"
        if stage == "推进" and not high_pressure:
            if negotiation_scene and has_active_goal:
                return "继续推进"
            if management_scene and has_active_goal and not medium_pressure:
                return "继续推进"
            if has_active_goal or has_commitment:
                return "继续推进"
            return "继续对齐"
        if stage == "探索" and not medium_pressure:
            if negotiation_scene and has_active_goal:
                return "继续对齐"
            if management_scene and has_active_goal:
                return "继续对齐"
            if has_active_goal or has_commitment:
                return "继续对齐"
            return "继续观察"
        if stage == "探索" and medium_pressure:
            if negotiation_scene and has_active_goal and not high_pressure:
                return "继续对齐"
            if management_scene and has_active_goal and risk != "high":
                return "继续对齐"
        sales_scene = "sales" in scene_id
        emotion_scene = "emotion" in scene_id
        if (negotiation_scene or management_scene or sales_scene or emotion_scene) and has_active_goal and not high_pressure:
            return "继续对齐"
        return "先观察"

    mode_history = [h for h in context.history if h.metadata.get("selected_mode")]
    if len(mode_history) >= 2:
        prev_mode = mode_history[-2].metadata.get("selected_mode", "")
        curr_mode = mode_history[-1].metadata.get("selected_mode", "")
        if prev_mode != curr_mode:
            add_session_note(session_id, round_num, "mode_switch", f"模式切换: {prev_mode} → {curr_mode}", {"from": prev_mode, "to": curr_mode})

    if not context.current_strategy.upgrade_eligible and energy_mode_val == "A":
        add_session_note(
            session_id,
            round_num,
            "upgrade_failed",
            "升维无效，已回退到 Mode A",
            {"upgrade_failed_count": context.current_strategy.upgrade_failed_count},
        )

    if not context.self_state.is_stable:
        add_session_note(
            session_id,
            round_num,
            "collapse",
            "系统不稳定（连续负面反馈），已切换到安抚模式",
            {"energy_mode": energy_mode_val},
        )

    if context.history:
        prev_trust = None
        for h in reversed(context.history[:-1]):
            if h.metadata.get("trust_level"):
                prev_trust = h.metadata["trust_level"]
                break
        curr_trust = context.user.trust_level.value if hasattr(context.user.trust_level, "value") else str(context.user.trust_level)
        if prev_trust and prev_trust != curr_trust:
            add_session_note(session_id, round_num, "trust_change", f"信任等级变化: {prev_trust} → {curr_trust}", {"from": prev_trust, "to": curr_trust})

    if context.user.emotion.intensity > 0.8 and feedback_str == "negative":
        add_session_note(
            session_id,
            round_num,
            "high_emotion",
            f"用户情绪失控({context.user.emotion.type.value} {context.user.emotion.intensity:.1f})，触发纠正",
            {"emotion": context.user.emotion.type.value, "intensity": context.user.emotion.intensity},
        )

    if relationship_position and relationship_position != "未识别":
        add_session_note(
            session_id,
            round_num,
            "relationship_state",
            f"关系位置: {relationship_position} | 场景: {scene_id or '未识别'} | 阶段: {situation_stage}",
            {
                "relationship_position": relationship_position,
                "scene_id": scene_id or "",
                "situation_stage": situation_stage,
            },
        )

    commitment_source, commitment_excerpt = _find_commitment_excerpt()
    material_summary = _build_memory_material_summary(context, user_input, getattr(context, "output", "") or "")
    trust_level = context.user.trust_level.value if hasattr(context.user.trust_level, "value") else str(context.user.trust_level)
    tension_level = getattr(context.self_check, "interaction_tension", "low") or "low"
    risk_level = getattr(context.self_check, "push_risk", "low") or "low"
    pressure_level = _to_level(float(getattr(context.self_check, "energy_pressure", 0.0) or 0.0))
    active_goal = getattr(context.goal, "granular_goal", "") or getattr(context.goal.current, "description", "")
    progress_state = _derive_progress_state(
        feedback_str,
        scene_id,
        situation_stage,
        commitment_excerpt,
        active_goal,
        risk_level,
        tension_level,
    )
    commitment_state = "未形成"
    if commitment_excerpt:
        if situation_stage == "收口":
            commitment_state = "已形成收口"
        elif _has_marker(commitment_excerpt, ["明天", "下次", "跟进", "对齐", "确认", "回看"]):
            commitment_state = "已形成跟进"
        else:
            commitment_state = "已形成方向"

    next_turn_focus = material_summary.get("next_pickup", "") or commitment_excerpt or _derive_scene_focus(
        scene_id,
        progress_state,
        active_goal,
        risk_level,
        tension_level,
    )
    if not commitment_excerpt and next_turn_focus and progress_state in {"继续对齐", "继续推进", "往收口走"}:
        commitment_state = "已形成方向"
    action_loop_parts = [
        f"推进: {progress_state}",
        f"承诺: {commitment_state}",
        f"局面: {_compact_material_text(material_summary.get('situation', ''), 42)}" if material_summary.get("situation") else "",
        f"压力: {_compact_material_text(material_summary.get('user_pressure', ''), 34)}" if material_summary.get("user_pressure") else "",
        f"判断: {_compact_material_text(material_summary.get('decision_needed', ''), 30)}" if material_summary.get("decision_needed") else "",
        f"方向: {_compact_material_text(material_summary.get('suggested_direction', ''), 34)}" if material_summary.get("suggested_direction") else "",
        f"建议: {_compact_material_text(material_summary.get('recommended_answer', ''), 34)}" if material_summary.get("recommended_answer") else "",
        f"风险: {_compact_material_text(material_summary.get('risk_if_wrong', ''), 28)}" if material_summary.get("risk_if_wrong") else "",
        f"下一步: {_compact_material_text(material_summary.get('next_action', ''), 30)}" if material_summary.get("next_action") else "",
        f"避免: {_compact_material_text(material_summary.get('avoid_next', ''), 28)}" if material_summary.get("avoid_next") else "",
        f"下一轮: {next_turn_focus}" if next_turn_focus else "",
        f"当前目标: {active_goal}" if active_goal else "",
    ]
    action_loop_state = " | ".join(part for part in action_loop_parts if part)[:220]
    context.world_state.scene_id = scene_id or "未识别"
    context.world_state.relationship_position = relationship_position
    context.world_state.situation_stage = situation_stage
    context.world_state.trust_level = trust_level
    context.world_state.tension_level = tension_level
    context.world_state.risk_level = risk_level
    context.world_state.pressure_level = pressure_level
    context.world_state.progress_state = progress_state
    context.world_state.commitment_state = commitment_state
    context.world_state.action_loop_state = action_loop_state
    context.world_state.active_goal = active_goal or ""
    context.world_state.next_turn_focus = next_turn_focus

    world_state_parts = [
        f"场景: {scene_id or '未识别'}",
        f"局面: {_compact_material_text(material_summary.get('situation', ''), 40)}" if material_summary.get("situation") else "",
        f"压力: {_compact_material_text(material_summary.get('user_pressure', ''), 32)}" if material_summary.get("user_pressure") else "",
        f"判断: {_compact_material_text(material_summary.get('decision_needed', ''), 28)}" if material_summary.get("decision_needed") else "",
        f"方向: {_compact_material_text(material_summary.get('suggested_direction', ''), 32)}" if material_summary.get("suggested_direction") else "",
        f"建议: {_compact_material_text(material_summary.get('recommended_answer', ''), 30)}" if material_summary.get("recommended_answer") else "",
        f"风险: {_compact_material_text(material_summary.get('risk_if_wrong', ''), 26)}" if material_summary.get("risk_if_wrong") else "",
        f"下一步: {_compact_material_text(material_summary.get('next_action', ''), 28)}" if material_summary.get("next_action") else "",
        f"避免: {_compact_material_text(material_summary.get('avoid_next', ''), 28)}" if material_summary.get("avoid_next") else "",
        f"关系: {relationship_position}",
        f"阶段: {situation_stage}",
        f"信任: {trust_level}",
        f"张力: {tension_level}",
        f"风险: {risk_level}",
        f"推进: {progress_state}",
        f"承诺: {commitment_state}",
    ]
    if next_turn_focus:
        world_state_parts.append(f"下一轮: {next_turn_focus}")
    if action_loop_state:
        world_state_parts.append(f"动作: {action_loop_state}")
    add_session_note(
        session_id,
        round_num,
        "world_state",
        " | ".join(world_state_parts),
        {
            "scene_id": scene_id or "",
            "relationship_position": relationship_position,
            "situation_stage": situation_stage,
            "trust_level": trust_level,
            "tension_level": tension_level,
            "risk_level": risk_level,
            "pressure_level": pressure_level,
            "progress_state": progress_state,
            "commitment_state": commitment_state,
            "action_loop_state": action_loop_state,
            "active_goal": active_goal or "",
            "next_turn_focus": next_turn_focus,
            "current_blocker": str(material_summary.get("situation", "") or ""),
            "user_tension": str(material_summary.get("user_pressure", "") or ""),
            "decision_point": str(material_summary.get("decision_needed", "") or ""),
            "decision_question": str(material_summary.get("decision_question", "") or ""),
            "recommended_bias": str(material_summary.get("suggested_direction", "") or ""),
            "recommended_answer": str(material_summary.get("recommended_answer", "") or ""),
            "risk_if_wrong": str(material_summary.get("risk_if_wrong", "") or ""),
            "next_action": str(material_summary.get("next_action", "") or ""),
            "avoid": str(material_summary.get("avoid_next", "") or ""),
            "first_sentence_bias": str(material_summary.get("first_sentence_bias", "") or ""),
        },
    )

    def _previous_world_state_summary() -> dict[str, str]:
        notes = get_session_memory().get_recent_notes(session_id, limit=10)
        for note in reversed(notes[:-1]):
            if note.note_type == "world_state":
                return {
                    "scene_id": str(note.detail.get("scene_id", "")),
                    "relationship_position": str(note.detail.get("relationship_position", "")),
                    "situation_stage": str(note.detail.get("situation_stage", "")),
                    "trust_level": str(note.detail.get("trust_level", "")),
                    "tension_level": str(note.detail.get("tension_level", "")),
                    "risk_level": str(note.detail.get("risk_level", "")),
                    "pressure_level": str(note.detail.get("pressure_level", "")),
                    "progress_state": str(note.detail.get("progress_state", "")),
                    "commitment_state": str(note.detail.get("commitment_state", "")),
                    "active_goal": str(note.detail.get("active_goal", "")),
                    "next_turn_focus": str(note.detail.get("next_turn_focus", "")),
                }
        return {}

    prev_state = _previous_world_state_summary()
    evolution_bits: list[str] = []
    if prev_state:
        prev_trust = prev_state.get("trust_level", "")
        if prev_trust and prev_trust != trust_level:
            evolution_bits.append(f"信任 {prev_trust}→{trust_level}")
        prev_stage = prev_state.get("situation_stage", "")
        if prev_stage and prev_stage != situation_stage:
            evolution_bits.append(f"阶段 {prev_stage}→{situation_stage}")
        prev_tension = prev_state.get("tension_level", "")
        if prev_tension and prev_tension != tension_level:
            evolution_bits.append(f"张力 {prev_tension}→{tension_level}")
        prev_progress = prev_state.get("progress_state", "")
        if prev_progress and prev_progress != progress_state:
            evolution_bits.append(f"推进 {prev_progress}→{progress_state}")
        prev_commitment = prev_state.get("commitment_state", "")
        if prev_commitment and prev_commitment != commitment_state:
            evolution_bits.append(f"承诺 {prev_commitment}→{commitment_state}")
        prev_focus = prev_state.get("next_turn_focus", "")
        if prev_focus and next_turn_focus and prev_focus != next_turn_focus:
            evolution_bits.append("下一轮焦点已更新")
        prev_action_loop = prev_state.get("action_loop_state", "")
        if prev_action_loop and action_loop_state and prev_action_loop != action_loop_state:
            evolution_bits.append("动作闭环已更新")

    if evolution_bits:
        add_session_note(
            session_id,
            round_num,
            "state_evolution",
            " | ".join(evolution_bits),
            {
                "from": prev_state,
                "to": {
                    "scene_id": scene_id or "",
                    "relationship_position": relationship_position,
                    "situation_stage": situation_stage,
                    "trust_level": trust_level,
                    "tension_level": tension_level,
                    "risk_level": risk_level,
                    "pressure_level": pressure_level,
                    "progress_state": progress_state,
                    "commitment_state": commitment_state,
                    "action_loop_state": action_loop_state,
                    "active_goal": active_goal or "",
                    "next_turn_focus": next_turn_focus,
                },
            },
        )

    if commitment_excerpt:
        closure_content = f"本轮闭环: {commitment_excerpt}"
        if feedback_str:
            closure_content = f"本轮结果: {feedback_str} | {closure_content}"
        add_session_note(
            session_id,
            round_num,
            "closure",
            closure_content,
            {
                "source": commitment_source,
                "relationship_position": relationship_position,
                "scene_id": scene_id or "",
                "situation_stage": situation_stage,
            },
        )

    action_loop_content = "动作闭环: " + action_loop_state
    if feedback_str:
        action_loop_content = f"本轮结果: {feedback_str} | {action_loop_content}"
    add_session_note(
        session_id,
        round_num,
        "action_loop",
        action_loop_content,
        {
            "progress_state": progress_state,
            "commitment_state": commitment_state,
            "action_loop_state": action_loop_state,
            "next_turn_focus": next_turn_focus,
            "active_goal": active_goal,
            "scene_id": scene_id or "",
            "relationship_position": relationship_position,
            "situation_stage": situation_stage,
        },
    )


def _advance_mode_sequence(context: Context):
    """根据反馈推进串联模式序列，并在连续失败时触发模式切换。"""
    from schemas.enums import Mode, DualCoreState

    seq = context.current_strategy.mode_sequence
    feedback = context.last_feedback
    feedback_str = feedback.value if hasattr(feedback, "value") else feedback

    if seq:
        idx = context.current_strategy.current_step_index

        if feedback_str == "positive":
            next_idx = idx + 1
            if next_idx >= len(seq):
                context.current_strategy.mode_sequence = []
                context.current_strategy.current_step_index = 0
                context.current_strategy.fallback_count = 0
            else:
                current_mode = seq[idx]
                next_mode = seq[next_idx]

                if current_mode == Mode.A and next_mode == Mode.B:
                    if context.user.emotion.intensity >= 0.6:
                        return
                    if context.user.dual_core.state == DualCoreState.CONFLICT:
                        return

                if current_mode == Mode.B and next_mode == Mode.C:
                    goal_achieved = context.goal.current.confidence >= 0.7 and context.goal.current.type in ("利益价值", "mixed")
                    mentions_long_term = any(
                        kw in (h.content if hasattr(h, "content") else "")
                        for h in context.history[-4:]
                        for kw in ["长期", "合作", "信任", "一起", "未来", "长期合作"]
                    )
                    if not goal_achieved and not mentions_long_term:
                        return

                context.current_strategy.current_step_index = next_idx
                context.current_strategy.fallback_count = 0

        elif feedback_str == "negative":
            weight = 1
            trust_change = context.last_feedback_trust_change
            if trust_change is not None and trust_change < -0.03:
                weight = 2
            context.current_strategy.fallback_count += weight
            if context.current_strategy.fallback_count >= 2:
                context.current_strategy.mode_sequence = []
                context.current_strategy.current_step_index = 0
                context.current_strategy.fallback_count = 0

    else:
        trust_change = context.last_feedback_trust_change
        if feedback_str == "negative" and trust_change is not None and trust_change < -0.03:
            current_mode = context.self_state.energy_mode
            mode_order = [Mode.A, Mode.B, Mode.C]
            current_idx = mode_order.index(current_mode) if current_mode in mode_order else 0
            new_idx = (current_idx + 1) % len(mode_order)
            new_mode = mode_order[new_idx]
            context.self_state.energy_mode = new_mode
            context.current_strategy.mode_sequence = [new_mode]
            context.current_strategy.current_step_index = 0
            context.current_strategy.fallback_count = 0
        elif feedback_str == "negative":
            context.current_strategy.fallback_count += 1
            if context.current_strategy.fallback_count >= 2:
                current_mode = context.self_state.energy_mode
                mode_order = [Mode.A, Mode.B, Mode.C]
                current_idx = mode_order.index(current_mode) if current_mode in mode_order else 0
                new_idx = (current_idx + 1) % len(mode_order)
                new_mode = mode_order[new_idx]
                context.self_state.energy_mode = new_mode
                context.current_strategy.mode_sequence = [new_mode]
                context.current_strategy.current_step_index = 0
                context.current_strategy.fallback_count = 0
        elif feedback_str == "positive":
            context.current_strategy.fallback_count = 0


def _generate_history_summary(context: Context) -> str:
    """当历史对话过长时，生成摘要压缩上下文。"""
    from llm.nvidia_client import invoke_fast
    from utils.types import sanitize_for_prompt

    middle_history = context.history[3:33]
    if not middle_history:
        return ""

    dialogue_lines = []
    for h in middle_history:
        role = "用户" if h.role == "user" else "系统"
        safe_content = sanitize_for_prompt(h.content, max_length=120)
        dialogue_lines.append(f"{role}: {safe_content[:80]}")

    dialogue_text = "\n".join(dialogue_lines)

    prompt = f"""以下是对话的中间部分（共 {len(middle_history)} 轮），请生成一段简洁的摘要。

规则：
1. 只保留关键信息：用户的核心诉求、系统的主要策略、重要决策
2. 控制在 100 字以内
3. 不要逐轮复述，要提炼要点

对话内容：
{dialogue_text}

请输出摘要："""

    try:
        summary = invoke_fast(prompt, "你是对话摘要助手。")
        return summary.strip()[:200]
    except Exception:
        return f"（历史摘要生成失败，保留 {len(middle_history)} 轮原始对话）"
