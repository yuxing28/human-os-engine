"""
Step 1.7 - 主任务判断

这层先回答一个更根本的问题：
这一轮最该做的是接住、理清、推进，还是复盘。
"""

from graph.state import GraphState
from graph.nodes.helpers import _turn_load_level
from graph.nodes.step1_5_meta import TEAM_KEYWORDS, EXECUTION_KEYWORDS


def _history_user_turns(context) -> int:
    return sum(1 for item in context.history if item.role == "user")


def _looks_like_action_request(text: str) -> bool:
    markers = [
        "怎么办", "怎么做", "怎么选", "该怎么", "下一步", "接下来",
        "给我方案", "帮我分析", "怎么推进", "怎么处理", "如何",
    ]
    return any(marker in text for marker in markers)


def _looks_like_reflection_request(text: str) -> bool:
    markers = [
        "复盘", "总结", "回头看", "哪里有问题", "为什么会这样",
        "问题在哪", "哪里做错", "哪里没做好", "帮我看看",
    ]
    return any(marker in text for marker in markers)


def _looks_like_work_action_context(text: str) -> bool:
    return any(marker in text for marker in TEAM_KEYWORDS + EXECUTION_KEYWORDS)


def _looks_like_emotional_impact(context, text: str) -> bool:
    emotion_type = getattr(getattr(context.user, "emotion", None), "type", "") or ""
    emotion_intensity = getattr(getattr(context.user, "emotion", None), "intensity", 0.0) or 0.0
    situation_hint = getattr(context, "situation_hint", "") or ""
    impact_markers = [
        "骂", "委屈", "难受", "崩", "烦", "压得", "受不了", "不开心",
        "生气", "气死", "想哭", "心累", "被说", "被否定",
    ]
    if any(marker in text for marker in impact_markers):
        return True
    if emotion_intensity >= 0.68:
        return True
    if emotion_type not in {"", "平静"} and emotion_intensity >= 0.5:
        return True
    if situation_hint in {"情绪受伤", "关系受伤", "职场受挫"}:
        return True
    return False


def _looks_like_workplace_hurt(context, text: str) -> bool:
    """
    判断这轮是不是“工作关系里的受伤”，而不是“管理推进”。

    这里不决定怎么回，只给后面的场景和输出一个更清楚的方向。
    """
    if not _looks_like_emotional_impact(context, text):
        return False
    if _looks_like_action_request(text) or _looks_like_reflection_request(text):
        return False

    relation = getattr(context.user, "relationship_position", "") or ""
    if relation in {"下级-上级", "上级-下级"}:
        return True

    situation_hint = getattr(context, "situation_hint", "") or ""
    return situation_hint == "职场受挫"


def _looks_like_need_clarify(text: str) -> bool:
    clarify_markers = [
        "到底", "其实", "就是", "有点", "不知道", "说不清", "想不明白",
        "卡住", "拿不准", "不确定", "纠结",
    ]
    return any(marker in text for marker in clarify_markers)


def _recent_system_turn(context) -> str:
    for item in reversed(context.history):
        if item.role == "system":
            return (item.content or "").strip()
    return ""


def _has_second_person_target(text: str) -> bool:
    return any(token in text for token in ["你", "你这", "你是不是", "你根本", "你又"])


def _has_reactive_shape(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    short_sharp = len(stripped) <= 12
    punctuation_burst = any(token in stripped for token in ["？", "!", "！", "??", "？！"])
    ending_particle = stripped.endswith(("啊", "吧", "吗", "呢", "呀"))
    return short_sharp and (punctuation_burst or ending_particle)


def _recent_user_turn_before_system(context) -> str:
    seen_system = False
    for item in reversed(context.history):
        if item.role == "system" and not seen_system:
            seen_system = True
            continue
        if seen_system and item.role == "user":
            return (item.content or "").strip()
    return ""


def _is_followup_detail_request(text: str) -> bool:
    stripped = (text or "").strip()
    if not stripped:
        return False
    markers = [
        "具体", "细说", "展开", "怎么做", "怎么说", "下一步", "然后呢",
        "继续", "详细", "举例", "话术", "步骤",
    ]
    return len(stripped) <= 24 and any(marker in stripped for marker in markers)


def _is_acknowledge_turn(text: str) -> bool:
    return (text or "").strip() in {"嗯", "嗯嗯", "好", "好的", "行", "可以", "收到", "ok", "OK"}


def _previous_user_was_followup_or_request(text: str) -> bool:
    if not text:
        return False
    markers = [
        "怎么办", "怎么做", "怎么说", "具体", "细说", "展开", "下一步",
        "如何", "给我方案", "帮我分析",
    ]
    return any(marker in text for marker in markers)


def _update_dialogue_frame(context, text: str, task: str, reason: str) -> None:
    """
    维护一个跨轮的对话框架。

    这层只判断“这一轮和上一轮是什么关系”，不判断具体行业内容。
    """
    frame = context.dialogue_frame
    current = (text or "").strip()
    previous_topic = (frame.active_topic or "").strip()

    if reason == "repair_after_missed_attunement":
        frame.user_act = "repair_challenge"
        if previous_topic:
            frame.answer_contract = f"先承认上一轮没有接住，再回到用户原本的问题：{previous_topic}。不要换题，不要套模板。"
        else:
            frame.answer_contract = "先承认上一轮没有接住，再请用户把要解决的点拉回来。不要防御。"
        return

    if _is_acknowledge_turn(current):
        frame.user_act = "acknowledge"
        frame.answer_contract = "用户只是确认或轻承接，延续上一轮议题，不要重新定义问题。"
        return

    if _is_followup_detail_request(current) and previous_topic:
        frame.user_act = "followup_detail"
        frame.answer_contract = f"用户在追问上一轮议题的具体做法。必须围绕这个议题展开：{previous_topic}。不要把它改写成别的场景。"
        return

    frame.user_act = "new_topic"
    frame.active_topic = current
    if task == "contain":
        frame.answer_contract = f"用户开启了一个需要先接住的议题：{current}。先回应感受，再轻轻理清。"
    elif task == "advance":
        frame.answer_contract = f"用户开启了一个需要给做法的议题：{current}。先回答问题，再给可执行下一步。"
    elif task == "reflect":
        frame.answer_contract = f"用户在要求复盘这个议题：{current}。先指出问题结构，再给改法。"
    else:
        frame.answer_contract = f"用户开启了一个需要理清的议题：{current}。先确认他真正想解决什么。"


def _looks_like_relation_break_reply(context, text: str) -> bool:
    recent_assistant = _recent_system_turn(context)
    if not recent_assistant:
        return False

    if _looks_like_action_request(text) or _looks_like_reflection_request(text):
        return False

    if not _has_second_person_target(text):
        return False

    previous_user_turn = _recent_user_turn_before_system(context)
    if not previous_user_turn or len(previous_user_turn) < 4:
        return False

    emotion_intensity = getattr(getattr(context.user, "emotion", None), "intensity", 0.0) or 0.0
    previous_was_request = _previous_user_was_followup_or_request(previous_user_turn)
    if emotion_intensity < 0.45 and not _has_reactive_shape(text) and not previous_was_request:
        return False

    # 这类输入更像在反馈“你刚才那句不对”，而不是继续讲事情本身。
    return len(text) <= 18 and (len(text) < len(previous_user_turn) or previous_was_request)


def step1_7_dialogue_task(state: GraphState) -> GraphState:
    """主任务判断：让系统先知道这轮最该做什么。"""
    context = state["context"]
    if state.get("skip_to_end", False):
        return {**state, "context": context}

    text = (state.get("user_input") or "").strip()
    turns = _history_user_turns(context)
    scene = (getattr(context, "primary_scene", "") or "").strip()
    response_mode = getattr(context, "response_mode", "ordinary")
    previous_topic = (getattr(getattr(context, "dialogue_frame", None), "active_topic", "") or "").strip()
    turn_level = _turn_load_level(context, text, scene)

    task = "clarify"
    reason = "default_clarify"

    if _looks_like_reflection_request(text):
        task = "reflect"
        reason = "explicit_reflection_request"
    elif _looks_like_relation_break_reply(context, text):
        task = "contain"
        reason = "repair_after_missed_attunement"
    elif _looks_like_workplace_hurt(context, text):
        task = "contain"
        reason = "workplace_hurt_first"
        context.situation_hint = "职场受挫"
        context.situation_confidence = max(getattr(context, "situation_confidence", 0.0) or 0.0, 0.72)
    elif _looks_like_emotional_impact(context, text) and not _looks_like_action_request(text):
        task = "contain"
        reason = "emotional_impact_first"
    elif _looks_like_action_request(text):
        if turn_level == "heavy" and (previous_topic or scene in {"sales", "negotiation", "management"} or turns >= 2):
            task = "advance"
            reason = "explicit_action_request"
        elif turns <= 1 and _looks_like_work_action_context(text):
            task = "advance"
            reason = "first_turn_work_action_request"
        elif turn_level == "medium" and (previous_topic or turns >= 2):
            task = "clarify"
            reason = "medium_action_request_need_more_context"
        else:
            task = "clarify"
            reason = "light_action_request_need_context"
    elif scene == "emotion":
        task = "contain"
        reason = "emotion_scene_default_contain"
    elif scene in {"sales", "negotiation"} and response_mode == "deep":
        task = "advance"
        reason = "high_value_scene_deep_mode"
    elif turns <= 1 and _looks_like_need_clarify(text):
        task = "clarify"
        reason = "early_turn_need_clarify"
    elif turns >= 3 and _looks_like_need_clarify(text):
        task = "reflect"
        reason = "stuck_multi_turn_reflect"

    context.dialogue_task = task
    context.dialogue_task_reason = reason
    _update_dialogue_frame(context, text, task, reason)
    return {**state, "context": context, "dialogue_task": task}
