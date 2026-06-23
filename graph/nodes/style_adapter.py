"""输出风格与术语处理。"""

import re


QUICK_ACK_SET = {"嗯", "好的", "可以", "行", "好", "ok", "OK", "收到", "嗯嗯", "继续"}


def _adapt_output_style(input_type: str, emotion_intensity: float) -> dict:
    """根据输入类型和情绪强度计算风格参数。"""
    if input_type == "情绪表达":
        return {
            "professionalism": 0.2,
            "empathy_depth": 0.9,
            "logic_density": 0.2,
            "spoken_ratio": 0.85,
        }
    if input_type == "问题咨询":
        return {
            "professionalism": 0.8,
            "empathy_depth": 0.3,
            "logic_density": 0.8,
            "spoken_ratio": 0.5,
        }
    if input_type == "场景描述":
        return {
            "professionalism": 0.5,
            "empathy_depth": 0.5,
            "logic_density": 0.5,
            "spoken_ratio": 0.6,
        }
    if emotion_intensity > 0.6:
        return {
            "professionalism": 0.3,
            "empathy_depth": 0.7,
            "logic_density": 0.4,
            "spoken_ratio": 0.7,
        }
    return {
        "professionalism": 0.6,
        "empathy_depth": 0.4,
        "logic_density": 0.6,
        "spoken_ratio": 0.55,
        }


def _build_output_profile(
    user_input: str,
    input_type: str,
    emotion_intensity: float,
    strategy_stage: str = "",
    scene: str = "",
) -> dict:
    """根据当前输入决定这轮输出该短一点还是该展开一点。"""
    text = (user_input or "").strip()
    punctuation_count = sum(text.count(mark) for mark in ["，", "。", "？", "！", ",", ".", "?", "!"])
    is_short_ack = text in QUICK_ACK_SET or len(text) <= 3
    is_mid_short = len(text) <= 12 and punctuation_count <= 1
    is_complex = len(text) >= 40 or punctuation_count >= 3

    if is_short_ack:
        return {
            "mode": "brief",
            "min_chars": 8,
            "max_chars": 45,
            "prompt_hint": "这轮只要短承接，别把意思拉散。",
            "scene": scene,
        }

    if emotion_intensity >= 0.82:
        return {
            "mode": "contain",
            "min_chars": 18,
            "max_chars": 90,
            "prompt_hint": "这轮先接住情绪和关系，别把内容推太满。",
            "scene": scene,
        }

    if is_mid_short and input_type in {"情绪表达", "混合"}:
        return {
            "mode": "light",
            "min_chars": 16,
            "max_chars": 70,
            "prompt_hint": "这轮轻轻接住就好，别为了完整讲太多。",
            "scene": scene,
        }

    if input_type == "问题咨询" and is_complex:
        return {
            "mode": "expanded",
            "min_chars": 70,
            "max_chars": 220,
            "prompt_hint": "这轮可以展开，但先把重点说清，再补必要动作。",
            "scene": scene,
        }

    if input_type in {"场景描述", "混合"} or strategy_stage in {"知识", "混合", "案例"}:
        return {
            "mode": "balanced",
            "min_chars": 45,
            "max_chars": 170,
            "prompt_hint": "这轮自然展开，但别把话说得太板。",
            "scene": scene,
        }

    return {
        "mode": "normal",
        "min_chars": 30,
        "max_chars": 120,
        "prompt_hint": "这轮按自然对话来，先说清楚，再看要不要补动作。",
        "scene": scene,
    }


def _is_scene_output_concrete_enough(text: str, scene: str) -> bool:
    """判断输出是不是已经够具体，够具体就少动它的节奏。"""
    result = (text or "").strip()
    if not result or not scene:
        return False

    scene_anchors = {
        "sales": ["结果", "成本", "节奏", "风险", "对比", "30 秒", "10 分钟", "7 天", "最担心点", "明天"],
        "management": ["小动作", "回看", "负责人", "今天", "卡的一件事", "30 分钟", "最占你精力"],
        "negotiation": ["条件", "边界", "区间", "让步", "拍板人", "确认窗口", "交付边界", "最容易谈拢"],
        "emotion": ["最刺痛", "最难受", "不舒服", "先不急着争对错", "身体", "小止损", "没被认真看见"],
    }
    anchors = scene_anchors.get(scene, [])
    if scene == "management" and "负责人" in result and "回看" in result:
        return True
    if scene == "negotiation" and "可执行的下一步" in result:
        return True
    if scene == "emotion" and "最刺痛" in result and any(marker in result for marker in ["不舒服", "最难受", "先不急着争对错"]):
        return True
    if len(result) < 28:
        return False
    hit_count = sum(1 for anchor in anchors if anchor in result)
    return hit_count >= 2


def _build_narrative_profile(
    user_input: str,
    input_type: str,
    emotion_intensity: float,
    scene: str = "",
    identity_hint: str = "",
    situation_hint: str = "",
    strategy_stage: str = "",
    layers: list[dict] | None = None,
) -> dict:
    """决定这轮更适合哪种叙事走法。"""
    text = (user_input or "").strip()
    short_ack = text in QUICK_ACK_SET or len(text) <= 3
    layer_ids = [layer.get("layer") for layer in (layers or []) if isinstance(layer, dict)]

    if short_ack:
        return {
            "mode": "carry",
            "prompt_hint": "这轮以轻承接为主，像真人顺着上一句接一下，不要一上来把话讲满。",
            "opening_rule": "先顺一下当前对话，再轻轻往前带半步。",
            "ending_rule": "结尾留一点空间，不要收得太死。",
        }

    if strategy_stage == "升维":
        return {
            "mode": "reframe",
            "prompt_hint": "这轮适合重定问题，不要陷在表面拉扯里。先换框架，再给方向。",
            "opening_rule": "开头不要直接讲道理，先把问题抬高一层。",
            "ending_rule": "结尾给一个更高视角下的下一步。",
        }

    if layer_ids and layer_ids[0] == 5:
        return {
            "mode": "action",
            "prompt_hint": "这轮以推进为主。先把最关键的变化点说清，再补一两个能往前接的说法，不要把话说得太像在补格子。",
            "opening_rule": "开头先贴住最关键的变化点，先说清再往前带。",
            "ending_rule": "结尾自然落到下一步或一个小选择上，不要硬收成清单。",
        }

    if layer_ids[:2] == [1, 3] and 5 not in layer_ids:
        return {
            "mode": "repair",
            "prompt_hint": "这轮先接住，再慢慢收，不要急着按同一种路子往下走。",
            "opening_rule": "开头先接住和降压，别急着解释对错。",
            "ending_rule": "结尾先留余地，别把后面说太满。",
        }

    if 4 in layer_ids and 5 not in layer_ids:
        return {
            "mode": "clarify",
            "prompt_hint": "这轮重点是先把关键缺口补上，别假装已经能给完整方案。",
            "opening_rule": "开头先贴住问题，再自然把缺口点出来。",
            "ending_rule": "结尾停在一个关键追问上，不要硬收方案。",
        }

    if emotion_intensity >= 0.8 or situation_hint == "稳定情绪":
        if identity_hint == "关系沟通" or any(keyword in text for keyword in ["老婆", "老公", "伴侣", "家人", "吵架"]):
            return {
                "mode": "repair",
                "prompt_hint": "这轮先停火、先保关系，不要急着证明谁对。先接住，再收窄，再给一个小动作。",
                "opening_rule": "先承认当下难受和卡点，别一上来讲方法。",
                "ending_rule": "结尾只放一个可执行的小动作，别讲太满。",
            }
        return {
            "mode": "contain",
            "prompt_hint": "这轮先接住情绪，先稳住，再慢慢聚焦。不要一口气给很多建议。",
            "opening_rule": "先回应情绪和压力，再慢慢收范围。",
            "ending_rule": "结尾只留一个下一步，别铺太开。",
        }

    if scene in {"sales", "negotiation"} or situation_hint in {"推进结果", "协商分歧"}:
        return {
            "mode": "action",
            "prompt_hint": "这轮以推进为主。先把最关键的变化点说清，再补少量能往前接的说法，不要把话说得太像在补格子。",
            "opening_rule": "开头可以直接切重点，但先把重点说清，别一下子套固定起手。",
            "ending_rule": "结尾给自然的下一步或一个可选方向，不要硬收成清单。",
        }

    if input_type in {"问题咨询", "场景描述", "混合"}:
        return {
            "mode": "balanced",
            "prompt_hint": "这轮走自然推进：先对齐，再往前接一步，不要老是同一种说法，也别一下子散开。",
            "opening_rule": "开头先贴住用户当下的问题。",
            "ending_rule": "结尾收在一个自然的下一步上。",
        }

    return {
        "mode": "companion",
        "prompt_hint": "这轮更像陪伴式交流，顺着对方说，但还是轻轻往前接一点。",
        "opening_rule": "开头先接住，不要太硬。",
        "ending_rule": "结尾保留一点继续往下接的余地。",
    }


def _replace_academic_terms(text: str) -> str:
    """把学术/系统术语替换成大白话。"""
    academic_replacements = {
        "认知偏误": "思维误区",
        "确认偏误": "只看自己想看的",
        "损失厌恶": "怕失去",
        "幸存者偏差": "只看到成功的",
        "锚定效应": "先入为主",
        "从众效应": "跟风",
        "框架效应": "换个说法",
        "互惠原理": "拿人手短",
        "情绪管理": "管住情绪",
        "欲望管理": "管住欲望",
        "认知重构": "换个角度想",
        "心理阻力": "心里过不去",
        "元认知": "反思自己",
        "概率思维": "用概率想问题",
        "决策日记": "记录决策",
        "T型能力结构": "一专多能",
        "T型能力": "一专多能",
        "产品化": "让你的本事能复制给别人",
        "品牌化": "让你的价值能传播出去",
        "双账户模型": "两个账户",
        "价值账户": "利益账户",
        "情感账户": "感情账户",
        "指数移动平均": "逐步调整",
        "注意力劫持": "注意力被分散",
        "能量分配": "精力分配",
        "内在枯竭": "精疲力尽",
        "外层破损": "边界不清",
        "问题猎手": "主动找难题解决的人",
        "解决方案的不可替代性": "别人做不了的本事",
        "解决方案的可替代性": "别人能不能替代你",
        "市场只为结果付费": "别人只看结果不看过程",
        "不为过程买单": "",
        "努力幻觉": "以为拼命干就有用",
        "证书幻觉": "以为拿个证就有用",
        "自我中心幻觉": "以为自己很重要",
        "情绪暂停与命名": "先停下来，给情绪起个名字",
        "事实与叙事剥离": "把事实和想法分开",
        "欲望的金字塔结构": "欲望的优先级",
        "个人价值公式": "个人价值的算法",
        "价值幻觉": "自我感觉良好的错觉",
        "复利效应": "越积越多",
        "熵增定律": "不整理就会越来越乱",
        "知行合一": "知道不如做到",
    }

    result = text
    for academic, plain in academic_replacements.items():
        result = result.replace(academic, plain)
    return result


def _soften_internal_scaffolding(text: str) -> str:
    """把结构化骨架标签收成更像自然对话的话。"""
    if not text:
        return text

    def _rewrite_sequence(match):
        sequence = match.group(1).replace("→", "->")
        parts = [part.strip() for part in sequence.split("->") if part.strip()]
        return f"顺序上可以先{'，再'.join(parts)}。"

    def _rewrite_emergency(match):
        content = match.group(1).strip()
        if content.startswith("如果"):
            return f"{content}。"
        return f"如果中间卡住，就{content}。"

    def _clean_instruction_head(content: str) -> str:
        cleaned = content.strip().rstrip("。")
        for prefix in ("先把", "先", "再", "后面", "之后", "不要", "别", "先别"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                break
        return cleaned or content.strip().rstrip("。")

    def _rewrite_do_now(match):
        content = _clean_instruction_head(match.group(1))
        return f"这轮先把{content}。"

    def _rewrite_do_later(match):
        content = _clean_instruction_head(match.group(1))
        return f"等这步稳住，再补{content}。"

    def _rewrite_avoid(match):
        content = _clean_instruction_head(match.group(1))
        return f"先别急着{content}。"

    replacements = [
        (r"(?im)^\s*核心目的[:：]\s*(.+)$", r"先把目标放在\1。"),
        (r"(?im)^\s*连招主线[:：]\s*(.+)$", _rewrite_sequence),
        (r"(?im)^\s*速用原则[:：]\s*(.+)$", r"记住一点，\1。"),
        (r"(?im)^\s*应急预案[:：]\s*(.+)$", _rewrite_emergency),
        (r"(?im)^\s*案例底稿[:：]\s*(.+)$", r"\1"),
        (r"(?im)^\s*修复焦点[:：]\s*(.+)$", r"你现在先盯住\1。"),
        (r"(?im)^\s*当前目标[:：]\s*(.+)$", r"这轮先盯住\1。"),
        (r"(?im)^\s*当前重点[:：]\s*(.+)$", r"眼下先顾住\1。"),
        (r"(?im)^\s*先别做[:：]\s*(.+)$", _rewrite_avoid),
        (r"(?im)^\s*这轮先做一件事[:：]\s*(.+)$", _rewrite_do_now),
        (r"(?im)^\s*等这步稳住，再做[:：]\s*(.+)$", _rewrite_do_later),
        (r"(?im)^\s*现在先别做[:：]\s*(.+)$", _rewrite_avoid),
    ]

    result = text
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result)

    result = re.sub(r"(?im)^\s*建议动作[:：]\s*", "", result)
    result = re.sub(r"(?im)^\s*-\s*", "", result)
    result = re.sub(r"\n\s*\n+", "\n\n", result)
    return result.strip()


def _smart_compress(text: str, max_length: int = 300) -> str:
    """先替换术语，再做智能截断。"""
    result = _replace_academic_terms(text)
    result = _soften_internal_scaffolding(result)
    if len(result) <= max_length:
        return result

    last_period = result.rfind("。", 0, max_length)
    if last_period > max_length * 0.6:
        return result[: last_period + 1]
    return result[: max_length - 3] + "..."


def _trim_to_output_profile(text: str, profile: dict) -> str:
    """根据这轮输出画像做最后一层收口，避免短输入配长篇输出。"""
    result = (text or "").strip()
    if not result:
        return result

    max_chars = int(profile.get("max_chars", 300) or 300)
    scene = str(profile.get("scene", "") or "")
    if scene and _is_scene_output_concrete_enough(result, scene) and len(result) <= int(max_chars * 1.5):
        return result
    if len(result) <= max_chars:
        return result

    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[。！？!?])\s*", result)
        if sentence.strip()
    ]
    if not sentences:
        return result[: max_chars - 3] + "..."

    trimmed = ""
    for sentence in sentences:
        candidate = f"{trimmed}{sentence}"
        if len(candidate) > max_chars:
            break
        trimmed = candidate

    if trimmed:
        return trimmed

    return result[: max_chars - 3] + "..."


def _shape_output_rhythm(text: str, output_profile: dict, narrative_profile: dict | None = None) -> str:
    """根据输出形态和叙事模式，做最后一层句式与段落节奏收口。"""
    result = (text or "").strip()
    if not result:
        return result

    result = re.sub(r"\n\s*\n+", "\n\n", result)
    scene = str((output_profile or {}).get("scene", "") or "")
    if scene and _is_scene_output_concrete_enough(result, scene):
        return result
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[。！？!?])\s*", result)
        if sentence.strip()
    ]
    if not sentences:
        return result

    output_mode = (output_profile or {}).get("mode", "normal")
    narrative_mode = (narrative_profile or {}).get("mode", "balanced")

    if output_mode == "brief" or narrative_mode == "carry":
        return "".join(sentences[:2]).replace("\n", "")

    if narrative_mode == "action":
        return "".join(sentences[:3]).replace("\n", "")

    if narrative_mode == "clarify":
        if len(sentences) <= 2:
            return "".join(sentences)
        return f"{''.join(sentences[:1])}\n\n{''.join(sentences[1:3])}".strip()

    if narrative_mode in {"repair", "contain"}:
        if len(sentences) <= 2:
            return "".join(sentences)
        head = "".join(sentences[:2])
        tail = "".join(sentences[2:4])
        return f"{head}\n\n{tail}".strip()

    if output_mode in {"balanced", "expanded"} and len(sentences) >= 4:
        head = "".join(sentences[:2])
        tail = "".join(sentences[2:4])
        return f"{head}\n\n{tail}".strip()

    return result
