"""
Human-OS Engine - LangGraph 节点实现

对应总控规格的 Step 0-9。
"""

from graph.state import GraphState
from utils.logger import warning

IDENTITY_SHIFT_MARKERS = [
    "换个话题", "先不聊这个", "不说这个了", "回到家", "在家里", "在公司",
    "工作上", "回家后", "作为", "站在", "如果从",
]
SITUATION_SHIFT_MARKERS = [
    "先稳住", "先别吵", "先推进", "先谈条件", "先说结果", "先看动作",
    "回到执行", "换个方式谈", "这次重点是", "现在更想",
]
RELATION_KEYWORDS = [
    "老婆", "老公", "伴侣", "孩子", "儿子", "女儿", "父母", "家人", "朋友",
]
TEAM_KEYWORDS = [
    "团队", "下属", "部门", "老板", "公司", "项目组", "成员", "绩效", "汇报", "跨部门",
]
PERSONAL_DECISION_KEYWORDS = [
    "我想", "我要", "我准备", "我决定", "我需要", "我打算", "我得",
]
NEGOTIATION_KEYWORDS = [
    "底线", "条款", "让步", "协商", "条件", "折中", "博弈", "谈判",
]
EXECUTION_KEYWORDS = [
    "推进", "执行", "落地", "安排", "计划", "本周", "任务", "节奏",
]
EMOTION_STABILIZE_KEYWORDS = [
    "情绪", "吵架", "崩溃", "难受", "委屈", "先稳住", "冷静",
]


def _looks_like_management_scene(user_input: str, context) -> bool:
    dialogue_task = getattr(context, "dialogue_task", "") or ""
    situation_hint = getattr(context, "situation_hint", "") or ""
    scene = context.primary_scene or (context.scene_config.scene_id if getattr(context, "scene_config", None) else "")
    if dialogue_task == "contain" and situation_hint in {"职场受挫", "情绪受伤"}:
        return False
    if scene == "management":
        return True
    if dialogue_task == "contain":
        return False
    has_team_context = any(keyword in user_input for keyword in TEAM_KEYWORDS)
    has_execution_posture = any(keyword in user_input for keyword in EXECUTION_KEYWORDS)
    return has_team_context and has_execution_posture


def _infer_management_sub_intent(user_input: str, context) -> tuple[str, float]:
    text = (user_input or "").strip()
    if not text or not _looks_like_management_scene(text, context):
        return "", 0.0

    action_markers = ["本周", "落地", "动作", "怎么推进", "直接给", "别讲大道理", "先做什么", "下一步"]
    roi_markers = ["ROI", "roi", "回报率", "投入产出", "预算", "财务总监", "CFO"]
    upward_markers = ["领导", "CEO", "老板", "拍板", "汇报", "技术债", "转型进度", "不满"]
    change_markers = ["又是新工具", "消停会", "变革", "改革", "学不动了", "倦怠", "消极抵抗", "24/7"]
    cross_markers = ["研发", "市场", "跨部门", "甩锅", "移交", "各说各话", "争夺", "冷战"]

    if any(marker in text for marker in roi_markers):
        return "roi_justification", 0.9
    if any(marker in text for marker in change_markers):
        return "change_fatigue", 0.88
    if any(marker in text for marker in cross_markers):
        return "cross_team_alignment", 0.88
    if any(marker in text for marker in action_markers):
        return "action_request", 0.86
    if any(marker in text for marker in upward_markers):
        return "upward_report", 0.84
    return "diagnose", 0.62


def _infer_sales_sub_intent(user_input: str, context) -> tuple[str, float]:
    text = (user_input or "").strip()
    scene = context.primary_scene or (context.scene_config.scene_id if getattr(context, "scene_config", None) else "")
    if not text or scene != "sales":
        return "", 0.0
    if any(marker in text for marker in ["跟老板汇报", "让我等消息", "回去汇报", "等我消息", "我再看看"]):
        return "delay_followup", 0.88
    has_price_signal = any(marker in text for marker in ["太贵", "价格高", "贵了", "便宜", "降价"])
    has_competitor_signal = any(marker in text for marker in ["竞品", "同行", "其他家", "别家"])
    if has_price_signal and has_competitor_signal:
        return "price_objection", 0.9
    if any(marker in text for marker in ["现在用的系统", "现在系统", "现有系统", "现在这套"]) and any(marker in text for marker in ["为什么要换", "为啥要换", "为什么换", "没必要换"]):
        return "switch_defense", 0.88
    if "有道理" in text and any(marker in text for marker in ["确实是这样想", "我确实是这样想", "确实这样想"]):
        return "soft_agreement", 0.84
    return "diagnose", 0.6


def _infer_negotiation_sub_intent(user_input: str, context) -> tuple[str, float]:
    text = (user_input or "").strip()
    scene = context.primary_scene or (context.scene_config.scene_id if getattr(context, "scene_config", None) else "")
    if not text or scene != "negotiation":
        return "", 0.0
    if any(marker in text for marker in ["账期", "90 天", "90天", "天账期"]) and any(marker in text for marker in ["否则不签", "不签", "签不了"]):
        return "payment_term", 0.9
    if any(marker in text for marker in ["接下来呢", "下一步呢", "那接下来", "下一步怎么走", "接下来怎么做"]):
        return "next_step_close", 0.86
    if any(marker in text for marker in ["有道理", "确实", "明白了", "你说得对"]):
        return "soft_agreement", 0.78
    return "diagnose", 0.6


def _infer_emotion_sub_intent(user_input: str, context) -> tuple[str, float]:
    text = (user_input or "").strip()
    scene = context.primary_scene or (context.scene_config.scene_id if getattr(context, "scene_config", None) else "")
    if not text or scene != "emotion":
        return "", 0.0
    accusation_markers = [
        "你根本就不爱我", "你根本不爱我", "你是不是不爱我", "你是不是不在乎我",
        "忘了纪念日", "你在敷衍我", "我觉得你在敷衍我", "不被放在心上",
    ]
    low_energy_markers = ["没精力想这么多", "不想想这么多", "太累了", "不想再想了", "脑子转不动", "现在只想躺着"]
    somatic_markers = ["看着电脑就想吐", "一看电脑就想吐", "没法辞职", "不能辞职", "又不能辞职"]
    failure_markers = ["如果失败了怎么办", "要是失败怎么办", "万一失败了怎么办", "失败了怎么办"]
    if any(marker in text for marker in accusation_markers):
        return "accusation_repair", 0.9
    if any(marker in text for marker in somatic_markers):
        return "somatic_relief", 0.9
    if any(marker in text for marker in low_energy_markers):
        return "low_energy_support", 0.88
    if any(marker in text for marker in failure_markers):
        return "failure_containment", 0.86
    return "diagnose", 0.6


def _extract_json_object(raw: str) -> str:
    """尽量从模型输出中提取 JSON 主体，降低解析失败率。"""
    text = (raw or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start:end + 1]
    return text


def _build_soft_guidance_prompt(
    identity_hint: str,
    situation_hint: str,
    focus: str,
    scene: str = "",
) -> str:
    """构建温和引导语，不使用盘问式表达。"""
    scene_key = scene if scene in {"emotion", "sales", "negotiation", "management"} else "default"

    tone_pack = {
        "emotion": {
            "identity": "我想把接下来的话说得更贴你一点。你现在更像是在为自己拿主意，还是还要顾到身边的人？",
            "situation": "我先轻轻对齐一下方向：你更希望我先陪你把情绪稳住，还是先一起理一个可执行的小动作？",
            "both": "我顺着你的处境来说会更合适。你更希望我现在先稳情绪，还是先给一个你今天就能用的小步骤？",
        },
        "sales": {
            "identity": "为了把建议更贴到你的位置，我先确认一个小点：你现在是自己拍板，还是还要和团队一起决策？",
            "situation": "我先和你对齐推进方向：你更想先看结果和动作，还是先把顾虑和关系面稳住？",
            "both": "我想把建议说得更有用一点。你这会儿更偏自己决策还是团队决策？我再按你的节奏给结果导向方案。",
        },
        "negotiation": {
            "identity": "为了不把话说偏，我先确认一下你的位置：你更像在替自己谈，还是在代表团队做协调？",
            "situation": "我先对齐谈法：你现在更想先推进条件结果，还是先把分歧和关系面的温度稳住？",
            "both": "我先顺着你的谈判位置来讲。你这会儿更偏个人拍板还是团队协调？我再给对应折中路径。",
        },
        "management": {
            "identity": "为了给你更能落地的建议，我先对齐一个点：这件事你是自己推进，还是要带团队一起推进？",
            "situation": "我先确认你此刻更需要哪种支持：先拿执行动作，还是先把团队分歧和节奏理顺？",
            "both": "我想把建议说得更贴管理现场。你现在更偏个人推进还是团队推进？我再给本周可执行版本。",
        },
        "default": {
            "identity": "我想把话说得更贴你一点。你现在更像在自己做决定，还是还要顾到团队这边？",
            "situation": "我先跟你对齐一个小方向：你现在更想先拿到动作结果，还是先把关系和情绪稳住？",
            "both": "我先贴着你的处境来说会更有用。你更希望我先给可执行动作，还是先把眼下的分歧和压力理顺？",
        },
    }

    # 微调：根据当前识别轻微替换默认问法
    if focus == "identity" and situation_hint == "管理执行":
        return "为了给你更能落地的动作，我先轻轻对齐一下：这件事是你自己推进，还是你要带着团队一起推进？"
    if focus == "identity" and situation_hint == "协商分歧":
        return "我想把建议贴近你的位置来讲。你这会儿更像是在替自己拍板，还是在代表团队协调？"
    if focus == "situation" and identity_hint == "团队决策":
        return "我先顺着你的角色来讲会更准一点。你更希望我先帮你推进结果，还是先把分歧和关系稳住？"

    pack = tone_pack.get(scene_key, tone_pack["default"])
    return pack.get(focus, pack["both"])


def _infer_identity_bucket(user_input: str) -> str:
    if any(keyword in user_input for keyword in RELATION_KEYWORDS):
        return "关系沟通"
    if any(keyword in user_input for keyword in TEAM_KEYWORDS):
        return "团队决策"
    if any(keyword in user_input for keyword in PERSONAL_DECISION_KEYWORDS):
        return "个人决策"
    return "未识别"


def _infer_situation_bucket(user_input: str) -> str:
    if any(keyword in user_input for keyword in NEGOTIATION_KEYWORDS):
        return "协商分歧"
    if any(keyword in user_input for keyword in EXECUTION_KEYWORDS):
        return "管理执行"
    if any(keyword in user_input for keyword in EMOTION_STABILIZE_KEYWORDS):
        return "稳定情绪"
    if any(keyword in user_input for keyword in ["怎么", "如何", "方案", "建议", "结果"]):
        return "推进结果"
    return "未识别"


def _should_refresh_identity(context, user_input: str, identity_hint: str, identity_conf: float) -> bool:
    current_identity = context.identity_hint or "未识别"
    if current_identity == "未识别":
        return True

    if identity_conf < 0.6:
        return False

    explicit_shift = any(marker in user_input for marker in IDENTITY_SHIFT_MARKERS)
    inferred_bucket = _infer_identity_bucket(user_input)
    bucket_changed = inferred_bucket != "未识别" and inferred_bucket != current_identity and inferred_bucket == identity_hint
    if getattr(context, "response_mode", "ordinary") != "deep" and not explicit_shift and not bucket_changed:
        return False
    return explicit_shift or bucket_changed


def _should_refresh_situation(context, user_input: str, situation_hint: str, situation_conf: float) -> bool:
    current_situation = context.situation_hint or "未识别"
    if current_situation == "未识别":
        return True

    if situation_conf < 0.58:
        return False

    explicit_shift = any(marker in user_input for marker in SITUATION_SHIFT_MARKERS)
    inferred_bucket = _infer_situation_bucket(user_input)
    bucket_changed = inferred_bucket != "未识别" and inferred_bucket != current_situation and inferred_bucket == situation_hint
    if getattr(context, "response_mode", "ordinary") != "deep" and not explicit_shift and not bucket_changed:
        return False
    return explicit_shift or bucket_changed


def _needs_heavy_meta_classification(context, user_input: str, fallback_result: dict) -> bool:
    """
    只有真的拿不准时，才让 Step1.5 去调模型。

    轻链路原则：
    - 短句直接规则
    - 常规输入优先规则
    - 只有长输入 + 明显复杂 + 规则置信度不够时，才走重判断
    """
    text = (user_input or "").strip()
    if not text:
        return False

    if bool(getattr(context, "short_utterance", False)) or len(text) <= 12:
        return False

    fallback_conf = float(fallback_result.get("confidence", 0.0) or 0.0)
    identity_conf = float(fallback_result.get("identity_confidence", 0.0) or 0.0)
    situation_conf = float(fallback_result.get("situation_confidence", 0.0) or 0.0)

    current_identity = getattr(context, "identity_hint", "") or "未识别"
    current_situation = getattr(context, "situation_hint", "") or "未识别"
    explicit_shift = any(marker in text for marker in IDENTITY_SHIFT_MARKERS + SITUATION_SHIFT_MARKERS)
    inferred_identity_bucket = _infer_identity_bucket(text)
    inferred_situation_bucket = _infer_situation_bucket(text)
    if getattr(context, "response_mode", "ordinary") != "deep" and not explicit_shift:
        return False

    if explicit_shift and (
        (inferred_identity_bucket != "未识别" and inferred_identity_bucket != current_identity)
        or (inferred_situation_bucket != "未识别" and inferred_situation_bucket != current_situation)
    ):
        return True

    complex_markers = ["但是", "可是", "不过", "一边", "另一方面", "到底", "其实", "同时", "怎么办", "为什么", "如何"]
    has_complex_signal = len(text) >= 28 or sum(1 for marker in complex_markers if marker in text) >= 2

    if explicit_shift and has_complex_signal:
        return True

    if fallback_conf >= 0.68 and identity_conf >= 0.55 and situation_conf >= 0.55:
        return False

    if current_identity != "未识别" and current_situation != "未识别" and not explicit_shift:
        return False

    return has_complex_signal and (fallback_conf < 0.58 or identity_conf < 0.45 or situation_conf < 0.45)


def step1_5_meta_controller(state: GraphState) -> GraphState:
    """Step 1.5：元控制器 - 输入类型判断"""
    context = state["context"]
    user_input = state["user_input"]
    if state.get("skip_to_end", False):
        return {**state, "context": context}

    from prompts.meta_controller import build_meta_controller_prompt, fallback_classify
    from schemas.enums import InputType

    fallback_result = fallback_classify(user_input)
    # 轻链路默认走规则，只有复杂且拿不准时才让模型再判一次
    should_skip_llm = not _needs_heavy_meta_classification(context, user_input, fallback_result)
    result = fallback_result

    # 尝试使用 LLM 分类（使用快速模型）
    try:
        if should_skip_llm:
            raise RuntimeError("short_utterance_skip_llm")

        from llm.nvidia_client import invoke_fast
        import json

        system_prompt, user_prompt = build_meta_controller_prompt(
            user_input=user_input,
            emotion_type=context.user.emotion.type.value if hasattr(context.user.emotion.type, 'value') else context.user.emotion.type,
            emotion_intensity=context.user.emotion.intensity,
        )

        runtime_trace = getattr(context, "runtime_trace", None)
        response = invoke_fast(
            user_prompt,
            system_prompt,
            runtime_trace=runtime_trace if isinstance(runtime_trace, dict) else None,
            stage="classifier",
        )

        # 解析 JSON 响应
        result = json.loads(_extract_json_object(response))
        input_type_str = result.get("input_type", "混合")
        confidence = result.get("confidence", 0.5)

    except Exception as e:
        if str(e) != "short_utterance_skip_llm":
            warning(f"元控制器 LLM 失败，使用 Fallback: {e}")
        # LLM 不可用，使用 Fallback 规则
        input_type_str = result["input_type"]
        confidence = result["confidence"]

    # 更新 Context
    context.user.input_type = input_type_str

    # 身份/情境信号：默认沿用已有判断，只在明显切换或确实缺失时更新
    identity_hint = result.get("identity_hint", "未识别")
    identity_conf = float(result.get("identity_confidence", 0.0) or 0.0)
    situation_hint = result.get("situation_hint", "未识别")
    situation_conf = float(result.get("situation_confidence", 0.0) or 0.0)

    if _should_refresh_identity(context, user_input, identity_hint, identity_conf):
        context.identity_hint = identity_hint
        context.identity_confidence = max(0.0, min(1.0, identity_conf))
    if _should_refresh_situation(context, user_input, situation_hint, situation_conf):
        context.situation_hint = situation_hint
        context.situation_confidence = max(0.0, min(1.0, situation_conf))

    management_sub_intent, management_sub_intent_conf = _infer_management_sub_intent(user_input, context)
    if management_sub_intent:
        context.management_sub_intent = management_sub_intent
        context.management_sub_intent_confidence = management_sub_intent_conf
    sales_sub_intent, sales_sub_intent_conf = _infer_sales_sub_intent(user_input, context)
    if sales_sub_intent:
        context.sales_sub_intent = sales_sub_intent
        context.sales_sub_intent_confidence = sales_sub_intent_conf
    negotiation_sub_intent, negotiation_sub_intent_conf = _infer_negotiation_sub_intent(user_input, context)
    if negotiation_sub_intent:
        context.negotiation_sub_intent = negotiation_sub_intent
        context.negotiation_sub_intent_confidence = negotiation_sub_intent_conf
    emotion_sub_intent, emotion_sub_intent_conf = _infer_emotion_sub_intent(user_input, context)
    if emotion_sub_intent:
        context.emotion_sub_intent = emotion_sub_intent
        context.emotion_sub_intent_confidence = emotion_sub_intent_conf

    # 信息不足引导触发：一次只补一个缺口 + 冷却
    # 触发条件：
    # 1) 短句/低信息密度；2) 要给动作的意图明显；3) 当前身份/情境有缺口
    action_like_keywords = ["怎么做", "落地", "动作", "方案", "建议", "怎么推进", "本周", "给我一个"]
    wants_action = any(k in user_input for k in action_like_keywords)
    has_context = len(context.history) >= 3
    low_info = bool(getattr(context, "info_density_low", False)) or len(user_input.strip()) <= 3

    identity_missing = context.identity_hint in ("", "未识别") or context.identity_confidence < 0.45
    situation_missing = context.situation_hint in ("", "未识别") or context.situation_confidence < 0.45

    should_consider_guidance = (
        has_context
        and getattr(context, "guidance_cooldown", 0) <= 0
        and (low_info or wants_action)
        and (identity_missing or situation_missing)
    )

    if should_consider_guidance:
        if identity_missing and not situation_missing:
            focus = "identity"
        elif situation_missing and not identity_missing:
            focus = "situation"
        else:
            focus = "both"
        context.guidance_needed = True
        context.guidance_focus = focus
        scene = context.primary_scene or (context.scene_config.scene_id if getattr(context, "scene_config", None) else "")
        context.guidance_prompt = _build_soft_guidance_prompt(
            context.identity_hint,
            context.situation_hint,
            focus,
            scene=scene,
        )
        context.guidance_cooldown = 2

    return {**state, "context": context}
