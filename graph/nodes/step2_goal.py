"""
Human-OS Engine - LangGraph 节点实现

对应总控规格的 Step 0-9。
"""

from graph.state import GraphState
from utils.logger import warning, info
from utils.types import sanitize_for_prompt
import json
import re

from graph.nodes.contradiction_check import _check_logical_contradiction


BENEFIT_KEYWORDS = ["买", "赚钱", "便宜", "性价比", "效率", "省钱", "投资", "回报", "升职", "加薪", "资源", "安全", "健康", "赚", "销售", "客户", "成交", "转化", "流量", "获客", "工资", "预算", "成本", "利润", "签单", "方案", "结果", "推进"]
EMOTION_KEYWORDS = ["开心", "快乐", "认可", "面子", "尊严", "意义", "归属", "陪伴", "爱", "信任", "尊重", "愿景", "幸福", "满足", "自信", "成长", "突破", "理解", "委屈", "难过", "孤独", "崩溃", "撑不住", "离婚", "吵架", "冷战", "分手", "绝望", "焦虑", "抑郁", "失眠", "难受", "痛苦", "关系"]
GIVE_UP_KEYWORDS = ["算了", "不买了", "不聊了", "放弃", "不想说了", "结束吧", "就这样吧"]
SWITCH_KEYWORDS = ["不想聊这个", "换个话题", "说别的", "我想说", "我想聊别的", "先不说这个"]
GENERIC_GOAL_REPLIES = {"嗯", "好", "好的", "行", "继续", "然后呢", "还有呢", "明白", "知道了", "是吗"}
EXPLICIT_GOAL_PREFIXES = ["我想解决", "我想聊", "我想说", "我想", "我要", "我需要", "我希望", "请帮我", "帮我", "麻烦你", "请你", "能不能帮我", "能不能"]
DEEP_GOAL_PATTERNS = [
    (r"我其实不是想.+?[，,。；; ]+(?:我是想|我只是想|而是想|是想)(?P<goal>.+)", 0.92),
    (r"我其实最想(?P<goal>.+)", 0.92),
    (r"我最想(?P<goal>.+)", 0.9),
    (r"真正想(?:要|解决)?的是(?P<goal>.+)", 0.9),
    (r"说白了(?:我)?就是想(?P<goal>.+)", 0.88),
    (r"核心是(?P<goal>.+)", 0.84),
    (r"关键是(?P<goal>.+)", 0.84),
    (r"我卡在(?P<goal>.+)", 0.84),
    (r"问题是(?P<goal>.+)", 0.8),
]

_STEP2_CACHE_MAX_SIZE = 512
_GOAL_LLM_CACHE: dict[tuple, str | None] = {}
_RESISTANCE_LLM_CACHE: dict[str, dict | None] = {}
_SCENE_MATCH_CACHE: dict[str, tuple[str, list[str], dict[str, float]]] = {}
_SCENE_CONFIG_CACHE: dict[str, object] = {}
MANAGEMENT_FATIGUE_MARKERS = [
    "又是新工具",
    "消停会",
    "变革",
    "改革",
    "学不动了",
    "倦怠",
    "消极抵抗",
    "别再推了",
    "别再加了",
    "先停一下",
]

CAREER_TRANSITION_MARKERS = [
    "不想做了",
    "不想干了",
    "换方向",
    "换行业",
    "转行",
    "重新开始",
    "还能做什么",
    "该怎么选择",
]

WORK_SCENE_MARKERS = [
    "工作",
    "上班",
    "行业",
    "餐饮",
    "门店",
    "开店",
    "小吃店",
    "面包",
    "烘焙",
    "客户",
    "团队",
    "老板",
    "收入",
    "赚钱",
]


def _is_workplace_hurt_context(context, user_input: str) -> bool:
    """
    区分“工作里的受伤” 和 “真的在聊管理推进”。

    前者不该因为出现老板/团队，就直接被 management 抢方向。
    """
    text = (user_input or "").strip()
    if not text:
        return False

    dialogue_task = getattr(context, "dialogue_task", "") or ""
    dialogue_task_reason = getattr(context, "dialogue_task_reason", "") or ""
    situation_hint = getattr(context, "situation_hint", "") or ""
    if dialogue_task != "contain":
        return False

    if dialogue_task_reason == "workplace_hurt_first":
        return True

    if situation_hint in {"职场受挫", "情绪受伤"}:
        return True

    work_context = any(marker in text for marker in WORK_SCENE_MARKERS)
    if not work_context:
        return False

    emotion_load = [
        "骂", "委屈", "难受", "烦", "火大", "压", "崩", "被说", "被否定",
        "不开心", "怪自己", "丢脸", "挂不住",
    ]
    return any(marker in text for marker in emotion_load)


def _cache_set(cache: dict, key, value) -> None:
    """简单 FIFO 缓存，避免 Step2 对相同输入重复调用 LLM。"""
    if key in cache:
        cache[key] = value
        return
    if len(cache) >= _STEP2_CACHE_MAX_SIZE:
        first_key = next(iter(cache))
        cache.pop(first_key, None)
    cache[key] = value


def _match_scenes_cached(registry, user_input: str) -> tuple[str, list[str], dict[str, float]]:
    cache_key = (user_input or "").strip()
    if cache_key in _SCENE_MATCH_CACHE:
        primary_id, secondary_ids, scores = _SCENE_MATCH_CACHE[cache_key]
        return primary_id, list(secondary_ids), dict(scores)

    primary_id, secondary_ids, scores = registry.match_scenes(user_input)
    primary_id = primary_id or ""
    secondary_ids = list(secondary_ids or [])
    scores = dict(scores or {})
    _cache_set(_SCENE_MATCH_CACHE, cache_key, (primary_id, secondary_ids, scores))
    return primary_id, list(secondary_ids), dict(scores)


def _load_scene_config_cached(loader_fn, scene_id: str):
    if scene_id in _SCENE_CONFIG_CACHE:
        return _SCENE_CONFIG_CACHE[scene_id]
    config = loader_fn(scene_id)
    _cache_set(_SCENE_CONFIG_CACHE, scene_id, config)
    return config


def _should_invoke_goal_llm(user_input: str) -> bool:
    """低风险控调用：只有像“在表达目标/问题”的输入才触发目标 LLM。"""
    text = (user_input or "").strip()
    if len(text) <= 5:
        return False
    goal_like_tokens = [
        "想", "要", "需要", "希望", "请帮", "怎么办", "怎么", "如何",
        "问题", "卡住", "推进", "解决", "成交", "关系", "沟通",
    ]
    if any(token in text for token in goal_like_tokens):
        return True
    return any(p in text for p in ["?", "？"])


def _should_invoke_resistance_llm(user_input: str) -> bool:
    """低风险控调用：只有出现潜在阻力信号时才触发阻力 LLM。"""
    text = (user_input or "").strip()
    if len(text) <= 5:
        return False
    resistance_signals = [
        "不", "没", "难", "怕", "担心", "风险", "贵", "预算", "麻烦",
        "不确定", "犹豫", "顾虑", "不想", "不能", "太",
    ]
    if any(token in text for token in resistance_signals):
        return True
    return any(p in text for p in ["?", "？"])


def _should_skip_dynamic_scene_match(context) -> bool:
    """
    沙盒固定场景短路：
    sandbox 会话通常已在 runner 初始化时注入 scene_config，
    这里直接复用，避免每轮重复做动态场景匹配。
    """
    session_id = str(getattr(context, "session_id", "") or "")
    if not session_id.startswith("sandbox-mt-"):
        return False
    return bool(getattr(context, "scene_config", None))


def _should_recompute_scene(context, user_input: str) -> bool:
    """
    场景重算只在“可能真的换场景”时触发。

    否则默认沿用当前主场景，避免每轮都走一次场景 LLM 分类。
    """
    text = (user_input or "").strip()
    current_scene = getattr(context, "primary_scene", "") or ""
    if not text:
        return False
    if _is_workplace_hurt_context(context, text):
        return current_scene not in {"emotion", ""}
    if not current_scene or not getattr(context, "scene_config", None):
        return True

    explicit_shift_markers = [
        "换个话题", "不聊这个了", "先不说这个", "我想聊别的", "回到工作", "说点别的",
        "这不是工作问题", "这不是感情问题", "这不是销售问题", "其实是团队问题",
    ]
    if any(marker in text for marker in explicit_shift_markers):
        return True

    scene_signals = {
        "emotion": ["难受", "委屈", "崩溃", "情绪", "关系", "伴侣", "家人", "不爱我", "吵架"],
        "sales": ["客户", "报价", "价格", "成交", "签单", "预算", "竞品", "方案"],
        "negotiation": ["底线", "条件", "让步", "协商", "博弈", "条款", "账期"],
        "management": ["团队", "老板", "下属", "部门", "汇报", "执行", "项目组", "跨部门"],
    }
    for scene_id, keywords in scene_signals.items():
        if scene_id != current_scene and any(keyword in text for keyword in keywords):
            return True

    return False


def _should_use_light_goal_path(context, user_input: str) -> bool:
    """
    普通轮次走轻量目标链：
    - 短句
    - 当前场景稳定
    - 没有明显切换/复杂追问
    """
    text = (user_input or "").strip()
    if not text:
        return True
    if getattr(context, "dialogue_task", "") in {"contain", "reflect"}:
        return True
    if getattr(context, "response_mode", "ordinary") != "deep":
        return True
    if bool(getattr(context, "short_utterance", False)) or len(text) <= 18:
        return True

    heavy_markers = ["怎么办", "为什么", "其实", "真正想", "核心是", "问题是", "卡在", "不想聊这个", "换个话题"]
    if any(marker in text for marker in heavy_markers):
        return False

    return not _should_recompute_scene(context, text)


def _looks_like_management_fatigue(user_input: str) -> bool:
    text = (user_input or "").strip()
    if not text:
        return False
    return any(marker in text for marker in MANAGEMENT_FATIGUE_MARKERS)


def _infer_first_turn_scene(user_input: str) -> str:
    """
    第一轮先用更稳的规则兜底，避免“职业选择/转行疲惫”被误打到 emotion/sales。
    """
    text = (user_input or "").strip()
    if not text:
        return ""

    if any(marker in text for marker in CAREER_TRANSITION_MARKERS) and any(
        marker in text for marker in WORK_SCENE_MARKERS
    ):
        return "management"

    return ""


def _infer_first_turn_scene_with_context(context, user_input: str) -> str:
    if _is_workplace_hurt_context(context, user_input):
        return "emotion"
    if (
        getattr(context, "dialogue_task", "") == "advance"
        and getattr(context, "situation_hint", "") == "管理执行"
    ):
        return "management"
    return _infer_first_turn_scene(user_input)


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _should_refresh_goal_anchor(user_input: str) -> bool:
    text = user_input.strip()
    if not text:
        return False
    if text in GENERIC_GOAL_REPLIES:
        return False
    if len(text) <= 4 and not _contains_any(text, ["怎么办", "怎么", "如何"]):
        return False
    return True


def _clean_goal_phrase(text: str) -> str:
    cleaned = text.strip().strip("，。！？,.!；;：: ")
    if not cleaned:
        return ""

    for sep in ["。", "？", "！", "；", ";", "\n"]:
        if sep in cleaned:
            cleaned = cleaned.split(sep, 1)[0].strip()

    # 对“我其实不是想…我是想…”这类句子，保留更核心的一段，不把前置铺垫全带进去。
    if "，" in cleaned and len(cleaned) > 12:
        first_part, second_part = cleaned.split("，", 1)
        if len(second_part.strip()) >= 4 and any(keyword in second_part for keyword in ["想", "让", "推进", "解决", "修复", "成交", "沟通", "稳住"]):
            cleaned = second_part.strip()

    return cleaned[:50]


def _extract_deeper_goal(user_input: str) -> tuple[str, float] | None:
    text = user_input.strip()
    for pattern, confidence in DEEP_GOAL_PATTERNS:
        match = re.search(pattern, text)
        if match:
            goal_text = _clean_goal_phrase(match.group("goal"))
            if goal_text:
                return goal_text, confidence
    return None


def _extract_goal_anchor(user_input: str, previous_goal: str = "") -> tuple[str, str, float]:
    """
    提取当前轮的目标锚点。

    返回：description, source, confidence
    """
    text = user_input.strip().strip("，。！？,.! ")
    if not _should_refresh_goal_anchor(text):
        return previous_goal, "system_inferred", 0.45

    for switch_kw in SWITCH_KEYWORDS:
        if switch_kw in text:
            text = text.split(switch_kw, 1)[-1].strip("，。！？,.! ")
            break

    source = "system_inferred"
    confidence = 0.65

    deeper_goal = _extract_deeper_goal(text)
    if deeper_goal:
        goal_text, goal_confidence = deeper_goal
        return goal_text, "user_explicit", goal_confidence

    for prefix in EXPLICIT_GOAL_PREFIXES:
        if text.startswith(prefix):
            stripped = text[len(prefix):].strip("，。！？,.! ")
            if stripped:
                text = stripped
            source = "user_explicit"
            confidence = 0.85
            break

    if _contains_any(text, ["怎么办", "怎么做", "如何", "怎么解决", "最担心", "卡在", "问题是"]):
        source = "user_explicit"
        confidence = max(confidence, 0.8)

    if len(text) < 4 and previous_goal:
        return previous_goal, "system_inferred", 0.45

    return _clean_goal_phrase(text), source, confidence


def _extract_surface_goal(user_input: str, previous_surface: str = "") -> str:
    """提取表层诉求：用户这一句字面上在说什么。"""
    text = (user_input or "").strip().strip("，。！？,.! ")
    if not _should_refresh_goal_anchor(text):
        return previous_surface

    for switch_kw in SWITCH_KEYWORDS:
        if switch_kw in text:
            text = text.split(switch_kw, 1)[-1].strip("，。！？,.! ")
            break

    for prefix in EXPLICIT_GOAL_PREFIXES:
        if text.startswith(prefix):
            stripped = text[len(prefix):].strip("，。！？,.! ")
            if stripped:
                text = stripped
            break

    return _clean_goal_phrase(text) or previous_surface


def _extract_underlying_goal(
    user_input: str,
    active_goal: str = "",
    previous_underlying: str = "",
) -> str:
    """提取深层诉求：用户怕什么、想保住什么、想争取什么。"""
    text = (user_input or "").strip()
    if not text:
        return previous_underlying

    deeper_goal = _extract_deeper_goal(text)
    if deeper_goal:
        return deeper_goal[0]

    fear_like_patterns = [
        r"(?:我)?(?:最怕|怕|担心|顾虑)(?P<goal>[^。！？!?，,；;]+)",
        r"(?:我)?(?:不敢|不想)(?P<goal>[^。！？!?，,；;]+)",
        r"(?:我)?(?:只想|只是想)(?P<goal>[^。！？!?，,；;]+)",
        r"(?:我)?(?:真正想|真正要)(?P<goal>[^。！？!?，,；;]+)",
    ]
    for pattern in fear_like_patterns:
        match = re.search(pattern, text)
        if match:
            cleaned = _clean_goal_phrase(match.group("goal"))
            if cleaned:
                return cleaned

    if active_goal and any(token in text for token in ["保住", "稳住", "避免", "别", "不要"]):
        return _clean_goal_phrase(active_goal)

    return previous_underlying


def _sync_goal_layers(context, user_input: str) -> None:
    """把三层目标同步到 context.goal.layers，不改变现有对外输出。"""
    layers = context.goal.layers
    active_goal = context.goal.current.description or layers.active_goal

    surface_goal = _extract_surface_goal(user_input, previous_surface=layers.surface_goal)
    underlying_goal = _extract_underlying_goal(
        user_input=user_input,
        active_goal=active_goal,
        previous_underlying=layers.underlying_goal,
    )

    if active_goal == "用户放弃":
        underlying_goal = "先停止当前推进，避免继续消耗"

    if context.user.resistance.type.value != "null":
        resistance_map = {
            "恐惧": "核心顾虑是风险和后果",
            "懒惰": "核心顾虑是动作成本太高",
            "傲慢": "核心顾虑是身份感和掌控感",
            "嫉妒": "核心顾虑是比较后的不甘",
            "愤怒": "核心顾虑是边界被碰触",
            "贪婪": "核心顾虑是投入产出不划算",
        }
        underlying_goal = resistance_map.get(context.user.resistance.type.value, underlying_goal)

    layers.surface_goal = surface_goal or layers.surface_goal
    layers.active_goal = active_goal or layers.active_goal
    layers.underlying_goal = underlying_goal or layers.underlying_goal


def _infer_goal_type(user_input: str, context) -> str:
    text = user_input.strip()
    benefit_count = sum(1 for kw in BENEFIT_KEYWORDS if kw in text)
    emotion_count = sum(1 for kw in EMOTION_KEYWORDS if kw in text)
    emotion_intensity = context.user.emotion.intensity
    scene_id = getattr(context.scene_config, "scene_id", "") if context.scene_config else ""

    if context.goal.granular_goal.startswith("emotion.") or scene_id == "emotion":
        return "情绪价值"
    if scene_id in {"sales", "management", "negotiation"} and benefit_count >= emotion_count:
        return "利益价值"
    if emotion_intensity >= 0.75 and emotion_count >= benefit_count:
        return "情绪价值"
    if benefit_count >= emotion_count + 2:
        return "利益价值"
    if emotion_count >= benefit_count + 2:
        return "情绪价值"
    if benefit_count > 0 and emotion_count > 0:
        return "混合"
    if benefit_count > 0:
        return "利益价值"
    if emotion_count > 0:
        return "情绪价值"
    return "混合"


def _identify_goal_with_llm(safe_user_input: str, goal_taxonomy, memory_hint: str = "") -> str | None:
    """使用 LLM 在候选目标中做语义识别。"""
    taxonomy_key = tuple(getattr(g, "granular_goal", "") for g in goal_taxonomy)
    cache_key = (safe_user_input, memory_hint, taxonomy_key)
    if cache_key in _GOAL_LLM_CACHE:
        return _GOAL_LLM_CACHE[cache_key]

    try:
        from llm.nvidia_client import invoke_fast
        goal_list = [{"id": g.granular_goal, "name": g.display_name, "desc": g.description} for g in goal_taxonomy]
        memory_block = f"\n补充记忆：\n{memory_hint}" if memory_hint else ""
        prompt = f"""分析用户发言，识别其真实目标。
用户发言：{safe_user_input}
{memory_block}
可选目标列表：{json.dumps(goal_list, ensure_ascii=False)}
请仅输出 JSON：{{"goal_id": "目标 ID", "confidence": 0.0-1.0}}"""
        result = invoke_fast(prompt, "你是一个专业的意图识别专家。")
        parsed = json.loads(result)
        goal_id = parsed.get("goal_id")
        if goal_id and any(g.granular_goal == goal_id for g in goal_taxonomy):
            _cache_set(_GOAL_LLM_CACHE, cache_key, goal_id)
            return goal_id
    except Exception:
        _cache_set(_GOAL_LLM_CACHE, cache_key, None)
        return None
    _cache_set(_GOAL_LLM_CACHE, cache_key, None)
    return None


def _identify_resistance_with_llm(safe_user_input: str):
    """使用 LLM 识别隐性阻力。"""
    if safe_user_input in _RESISTANCE_LLM_CACHE:
        return _RESISTANCE_LLM_CACHE[safe_user_input]

    try:
        from llm.nvidia_client import invoke_fast
        res_prompt = f"""分析用户发言，识别是否存在隐性阻力。
阻力类型：恐惧（怕失败/怕损失）、懒惰（怕麻烦/不想动）、傲慢（不需要/看不上）、嫉妒（攀比/不甘）、愤怒（不满/底线）、贪婪（太贵/不值）。
用户发言：{safe_user_input}
如果存在阻力，请输出 JSON：{{"type": "阻力类型", "intensity": 0.0-1.0}}
如果没有阻力，输出：{{"type": "none", "intensity": 0.0}}"""
        res_result = invoke_fast(res_prompt, "你是一个销售阻力识别专家。")
        parsed = json.loads(res_result)
        _cache_set(_RESISTANCE_LLM_CACHE, safe_user_input, parsed)
        return parsed
    except Exception:
        _cache_set(_RESISTANCE_LLM_CACHE, safe_user_input, None)
        return None


def step2_goal_detection(state: GraphState) -> GraphState:
    """Step 2：目标检测与阻力探测"""
    context = state["context"]
    user_input = state["user_input"]
    if getattr(context, "dialogue_task_reason", "") == "" and getattr(context, "dialogue_task", "clarify") == "clarify":
        try:
            from graph.nodes.step1_7_dialogue_task import step1_7_dialogue_task

            state = step1_7_dialogue_task(state)
            context = state["context"]
        except Exception:
            pass
    short_mode = getattr(context, "short_utterance", False)
    light_goal_path = _should_use_light_goal_path(context, user_input)
    if state.get("skip_to_end", False):
        return {**state, "context": context}
    safe_user_input = sanitize_for_prompt(user_input, max_length=2000)
    from modules.memory import extract_structured_memory_hints
    memory_hint = ""
    if not short_mode:
        memory_hint = extract_structured_memory_hints(getattr(context, "unified_context", ""), limit_per_section=3)

    from schemas.user_state import Resistance, ResistanceType
    from schemas.context import GoalItem
    user_rounds = sum(1 for item in getattr(context, "history", []) or [] if getattr(item, "role", "") == "user")

    if (
        not getattr(context, "primary_scene", "")
        and not getattr(context, "scene_config", None)
        and user_rounds <= 1
    ):
        inferred_scene = _infer_first_turn_scene_with_context(context, user_input)
        if inferred_scene:
            try:
                from modules.L5.scene_loader import load_scene_config
                context.primary_scene = inferred_scene
                context.secondary_scenes = []
                context.secondary_configs = {}
                context.secondary_scene_strategy = ""
                context.scene_config = _load_scene_config_cached(load_scene_config, inferred_scene)
                context.matched_scenes = {inferred_scene: 0.72}
            except Exception:
                pass

    if _should_skip_dynamic_scene_match(context):
        scene_id = getattr(context.scene_config, "scene_id", "") if getattr(context, "scene_config", None) else ""
        if scene_id:
            context.primary_scene = context.primary_scene or scene_id
            context.secondary_scenes = []
            context.secondary_configs = {}
            context.secondary_scene_strategy = ""
            if not context.matched_scenes:
                context.matched_scenes = {scene_id: 1.0}
    elif light_goal_path:
        scene_id = (
            getattr(getattr(context, "scene_config", None), "scene_id", "")
            or getattr(context, "primary_scene", "")
        )
        try:
            from modules.L5.skill_registry import get_registry
            registry = get_registry()
            _, secondary_ids, scores = _match_scenes_cached(registry, user_input)
            if scores:
                context.matched_scenes = scores
                if not context.secondary_scenes:
                    context.secondary_scenes = secondary_ids
        except Exception:
            pass
        if scene_id:
            context.primary_scene = context.primary_scene or scene_id
            if not context.matched_scenes:
                context.matched_scenes = {scene_id: 1.0}
        context.secondary_scenes = []
        context.secondary_configs = {}
        context.secondary_scene_strategy = ""
        if scene_id and not getattr(context, "scene_config", None):
            try:
                from modules.L5.scene_loader import load_scene_config
                context.scene_config = _load_scene_config_cached(load_scene_config, scene_id)
            except Exception:
                pass
    else:
        # 0. 技能自动检测（动态注册表 - 混合调度）
        # 每轮运行以支持动态换挡 (Dynamic Shifting)
        try:
            from modules.L5.skill_registry import get_registry
            from modules.L5.scene_loader import load_scene_config
            
            registry = get_registry()
            primary_id, secondary_ids, scores = _match_scenes_cached(registry, user_input)
            
            # 记录所有匹配分数
            context.matched_scenes = scores
            
            # 决策是否切换主场景
            should_switch = False
            if primary_id:
                if not context.primary_scene:
                    should_switch = True
                else:
                    current_score = scores.get(context.primary_scene, 0)
                    new_score = scores.get(primary_id, 0)
                    if current_score == 0 and new_score > 0:
                        should_switch = True
                    elif new_score > current_score + 0.05:
                        should_switch = True

            # 管理场景的“变革疲劳”先留在管理，不轻易被情绪场景抢走
            if (
                should_switch
                and context.primary_scene == "management"
                and primary_id == "emotion"
                and _looks_like_management_fatigue(user_input)
            ):
                should_switch = False
            
            if should_switch:
                # 执行切换
                context.primary_scene = primary_id
                context.secondary_scenes = secondary_ids
                
                # 加载配置
                context.scene_config = _load_scene_config_cached(load_scene_config, primary_id)
                context.skill_prompt = registry.build_skill_prompt(primary_id, getattr(context, "world_state", None))
                
                # 加载副场景配置
                context.secondary_configs = {}
                for sec_id in secondary_ids:
                    try:
                        context.secondary_configs[sec_id] = _load_scene_config_cached(load_scene_config, sec_id)
                    except Exception:
                        pass
                
                # 融合黑名单 (底线法则)
                merged_blacklist = {}
                if context.scene_config.weapon_blacklist:
                    for k, v in context.scene_config.weapon_blacklist.items():
                        merged_blacklist.setdefault(k, []).extend(v)
                for sec_cfg in context.secondary_configs.values():
                    if sec_cfg.weapon_blacklist:
                        for k, v in sec_cfg.weapon_blacklist.items():
                            if k not in merged_blacklist:
                                merged_blacklist[k] = []
                            merged_blacklist[k].extend(v)
                            merged_blacklist[k] = list(set(merged_blacklist[k]))
                context.merged_weapon_blacklist = merged_blacklist
                
                # 【混合调度 3.3C】构建副场景策略指令
                secondary_strategy_parts = []
                for sec_id, sec_cfg in context.secondary_configs.items():
                    sec_score = scores.get(sec_id, 0)
                    sec_strategies = []
                    if sec_cfg.goal_taxonomy:
                        for g in sec_cfg.goal_taxonomy[:2]:
                            for p in getattr(g, 'strategy_preferences', [])[:1]:
                                sec_strategies.append(p.get('combo', ''))
                    if sec_strategies:
                        secondary_strategy_parts.append(
                            f"检测到用户存在【{sec_id}】诉求（匹配度 {sec_score:.0%}），"
                            f"请在推进{context.primary_scene}目标时，适当使用以下策略进行缓冲："
                            f"{', '.join(sec_strategies)}。"
                        )
                    else:
                        secondary_strategy_parts.append(
                            f"检测到用户存在【{sec_id}】诉求（匹配度 {sec_score:.0%}），"
                            f"请在推进{context.primary_scene}目标时，注意语气和表达方式的适配。"
                        )
                context.secondary_scene_strategy = '\n'.join(secondary_strategy_parts) if secondary_strategy_parts else ''
                
                info(f"场景切换/初始化: Primary={primary_id}, Secondaries={secondary_ids}")
                
        except Exception:
            pass  # 无技能配置时跳过
        active_skill_id = context.primary_scene or getattr(context.scene_config, "scene_id", "") or ""
        from modules.L5.skill_extension_bridge import compose_skill_prompt
        context.skill_prompt = (
            compose_skill_prompt(
                context,
                active_skill_id,
                getattr(context, "world_state", None),
            )
            if active_skill_id
            else ""
        )

    # 0.5 细粒度目标识别（基于场景配置 + LLM 语义识别）
    # 每轮重置，避免"粘滞"到上一轮目标
    if context.scene_config and context.scene_config.goal_taxonomy:
        # 保存上一轮目标，作为兜底
        previous_goal = context.goal.granular_goal
        
        context.goal.granular_goal = ""
        context.goal.display_name = ""
        
        # 先用关键词匹配做快速筛选
        best_score = 0
        best_goal = None
        for goal_def in context.scene_config.goal_taxonomy:
            score = sum(1 for kw in goal_def.keywords if kw in user_input)
            if score > best_score:
                best_score = score
                best_goal = goal_def
        
        if best_goal and best_score > 0:
            context.goal.granular_goal = best_goal.granular_goal
            context.goal.display_name = best_goal.display_name
        
        # 如果关键词匹配失败或置信度低，用 LLM 语义识别
        if not short_mode and not light_goal_path and best_score < 2 and _should_invoke_goal_llm(user_input):
            goal_id = _identify_goal_with_llm(
                safe_user_input,
                context.scene_config.goal_taxonomy,
                memory_hint=memory_hint,
            )
            if goal_id:
                context.goal.granular_goal = goal_id
                for g in context.scene_config.goal_taxonomy:
                    if g.granular_goal == goal_id:
                        context.goal.display_name = g.display_name
                        break
        
        # 【修复】当关键词和 LLM 都失败时，回退到上一轮目标或场景默认目标
        if not context.goal.granular_goal:
            if previous_goal and any(g.granular_goal == previous_goal for g in context.scene_config.goal_taxonomy):
                # 保持上一轮目标（对话连续性）
                context.goal.granular_goal = previous_goal
                for g in context.scene_config.goal_taxonomy:
                    if g.granular_goal == previous_goal:
                        context.goal.display_name = g.display_name
                        break
            else:
                # 回退到场景第一个目标（兜底）
                first_goal = context.scene_config.goal_taxonomy[0]
                context.goal.granular_goal = first_goal.granular_goal
                context.goal.display_name = first_goal.display_name

    previous_goal_description = context.goal.current.description
    extracted_goal_description, goal_source, goal_confidence = _extract_goal_anchor(
        user_input=user_input,
        previous_goal=previous_goal_description,
    )
    inferred_goal_type = _infer_goal_type(user_input, context)
    is_switch = any(kw in user_input for kw in SWITCH_KEYWORDS)

    light_management_advance = (
        light_goal_path
        and getattr(context, "dialogue_task", "") == "advance"
        and getattr(context, "primary_scene", "") == "management"
    )

    # 【修复 P0】情感场景目标强制推断为"情绪价值"
    if context.goal.granular_goal and context.goal.granular_goal.startswith("emotion."):
        context.goal.current.type = "情绪价值"

    # 1. 放弃信号检测
    RESISTANCE_KEYWORDS = {
        "恐惧": ["怕", "担心", "风险", "万一", "失败", "亏", "赔"],
        "懒惰": ["麻烦", "太复杂", "没时间", "累", "不想做", "费劲"],
        "傲慢": ["不需要", "看不上", "不感兴趣", "没用", "我不需要", "你懂什么", "做梦", "破方案", "垃圾", "浪费时间", "你凭什么", "你能行吗"],
        "贪婪": ["太贵", "不值", "性价比", "优惠", "便宜点"],
    }

    # 检测放弃信号
    is_give_up = any(kw in user_input for kw in GIVE_UP_KEYWORDS)

    if is_give_up:
        # 判断是真正放弃还是阻力浮现
        detected_resistance = None
        for res_type, keywords in RESISTANCE_KEYWORDS.items():
            if any(kw in user_input for kw in keywords):
                detected_resistance = res_type
                break

        if detected_resistance:
            # 阻力浮现：不改变原目标，标记阻力
            resistance_type_map = {
                "恐惧": ResistanceType.FEAR,
                "懒惰": ResistanceType.SLOTH,
                "傲慢": ResistanceType.PRIDE,
                "贪婪": ResistanceType.GREED,
            }
            context.user.resistance = Resistance(
                type=resistance_type_map.get(detected_resistance, ResistanceType.FEAR),
                intensity=0.7,
                original_goal=context.goal.current.description,
            )
        else:
            # 真正放弃
            context.goal.current = GoalItem(
                description="用户放弃",
                type=inferred_goal_type,
                confidence=0.8,
                source="user_explicit",
            )
    elif not is_switch:
        # 正常轮次：每轮都尝试重新锚定目标，但对“嗯/继续”这类低信息输入保持稳定
        if extracted_goal_description:
            if not (
                light_goal_path
                and goal_source == "system_inferred"
                and extracted_goal_description == previous_goal_description
            ):
                context.goal.current = GoalItem(
                    description=extracted_goal_description,
                    type=inferred_goal_type,
                    confidence=goal_confidence,
                    source=goal_source,
                )

    if light_management_advance:
        _sync_goal_layers(context, user_input)
        return {**state, "context": context}

    # 2.5 LLM 语义识别阻力（即使没有放弃信号，也检测隐性阻力）
    if context.user.resistance.type == ResistanceType.NONE and len(user_input.strip()) > 5:
        # 先用扩展关键词库做快速匹配
        EXTENDED_RESISTANCE_KEYWORDS = {
            "恐惧": ["怕", "担心", "风险", "万一", "失败", "亏", "赔", "责任", "兜底", "保障", "安全", "不确定", "顾虑", "怕担责", "怕出问题", "后果"],
            "懒惰": ["麻烦", "太复杂", "没时间", "累", "不想做", "费劲", "简单", "省事", "一键", "太折腾"],
            "傲慢": ["不需要", "看不上", "不感兴趣", "没用", "我不需要", "你懂什么", "做梦", "破方案", "垃圾", "浪费时间", "你凭什么", "你能行吗", "忽悠", "虚头巴脑", "套路"],
            "嫉妒": ["别人", "同行", "竞品", "为什么他们", "不公平", "差距", "落后"],
            "愤怒": ["不满", "受够了", "底线", "对抗", "不能接受", "太过分", "态度", "敷衍"],
            "贪婪": ["太贵", "不值", "性价比", "优惠", "便宜点", "折扣", "利润", "回报", "ROI"],
        }
        for res_type, keywords in EXTENDED_RESISTANCE_KEYWORDS.items():
            if any(kw in user_input for kw in keywords):
                res_map = {
                    "恐惧": ResistanceType.FEAR, "懒惰": ResistanceType.SLOTH,
                    "傲慢": ResistanceType.PRIDE, "嫉妒": ResistanceType.ENVY,
                    "愤怒": ResistanceType.WRATH, "贪婪": ResistanceType.GREED,
                }
                context.user.resistance = Resistance(
                    type=res_map.get(res_type, ResistanceType.FEAR),
                    intensity=0.6,
                    original_goal=context.goal.current.description,
                )
                break
        
        # 如果关键词也没命中，再用 LLM（可选增强）
        if (
            not short_mode
            and not light_goal_path
            and context.user.resistance.type == ResistanceType.NONE
            and _should_invoke_resistance_llm(user_input)
        ):
            res_parsed = _identify_resistance_with_llm(safe_user_input)
            if res_parsed and res_parsed.get("type") and res_parsed["type"] != "none":
                res_map = {
                    "恐惧": ResistanceType.FEAR, "懒惰": ResistanceType.SLOTH,
                    "傲慢": ResistanceType.PRIDE, "嫉妒": ResistanceType.ENVY,
                    "愤怒": ResistanceType.WRATH, "贪婪": ResistanceType.GREED,
                }
                context.user.resistance = Resistance(
                    type=res_map.get(res_parsed["type"], ResistanceType.FEAR),
                    intensity=res_parsed.get("intensity", 0.5),
                    original_goal=context.goal.current.description,
                )

    # 2. 目标显式切换检测
    if is_switch:
        # 存入历史
        context.goal.history.append(context.goal.current)
        context.goal.drift_detected = True

        # 尝试提取新目标
        new_goal_text = user_input
        for kw in ["我想说", "我想聊", "说说", "换个话题", "不想聊这个"]:
            if kw in user_input:
                idx = user_input.index(kw) + len(kw)
                new_goal_text = user_input[idx:].strip()
                break

        switch_goal_description, switch_source, switch_confidence = _extract_goal_anchor(
            new_goal_text,
            previous_goal="未明确",
        )

        context.goal.current = GoalItem(
            description=switch_goal_description if switch_goal_description else "未明确",
            type=_infer_goal_type(new_goal_text or user_input, context),
            confidence=max(switch_confidence, 0.8),
            source="user_explicit" if switch_source != "system_inferred" else "user_explicit",
        )

    # 同步三层目标（不改变现有主链行为，只补内部结构化状态）
    _sync_goal_layers(context, user_input)

    # 3. 逻辑矛盾检测（纠正权，新增）
    contradiction_check = _check_logical_contradiction(context, user_input)
    if contradiction_check:
        # 检测到逻辑矛盾，从武器库选择纠正武器
        from modules.L3.weapon_arsenal import get_weapon
        weapon = get_weapon("质问")  # 默认使用质问武器
        if not weapon:
            weapon = get_weapon("质疑")
        weapon_example = weapon.example if weapon else ""
        # 组合纠正话术
        context.output = f"{contradiction_check} {weapon_example}"
        return {**state, "context": context, "output": context.output, "skip_to_end": True}

    # 4. 情绪失控纠正（连续 2 轮高情绪）
    if context.user.emotion.intensity > 0.8:
        high_emotion_count = 0
        for item in context.history:
            if item.role == "user":
                # 简单判断：如果历史中有高情绪标记
                if item.metadata.get("high_emotion"):
                    high_emotion_count += 1
        if high_emotion_count >= 1:
            context.output = "我注意到你情绪很激动。这样聊不出结果，你是想继续发泄，还是愿意换个角度解决问题？"
            return {**state, "context": context, "output": context.output, "skip_to_end": True}

    # 5. 漂移拒绝纠正（drift_detected + 用户拒绝回题）
    if context.goal.drift_detected:
        REFUSE_RETURN_KEYWORDS = ["不想聊", "就说这个", "别提", "不回去", "换个", "说别的"]
        if any(kw in user_input for kw in REFUSE_RETURN_KEYWORDS):
            context.output = "你一直在偏离最初的问题。如果你不想解决那个，至少告诉我你现在到底想聊什么。"
            return {**state, "context": context, "output": context.output, "skip_to_end": True}

    # 标记当前轮情绪状态供下一轮使用
    if context.user.emotion.intensity > 0.8:
        # 更新最新历史条目的元数据
        if context.history:
            context.history[-1].metadata["high_emotion"] = True

    return {**state, "context": context}
