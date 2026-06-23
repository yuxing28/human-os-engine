"""逻辑矛盾与对抗输入检测。"""

from schemas.context import Context
from utils.types import safe_enum_value


def _is_targeted_derogatory(user_input: str, derogatory_words: list[str]) -> bool:
    """
    区分“在描述问题”（如：团队氛围差）和“在攻击对象”（如：你们太烂）。
    """
    text = user_input or ""
    has_strong_attack = any(word in text for word in ["骗子", "傻子", "忽悠", "套路", "懂什么", "资格", "背话术"])
    if has_strong_attack:
        return True

    mild_attack_words = [w for w in derogatory_words if w not in {"骗子", "傻子", "忽悠", "套路", "懂什么", "资格", "背话术"}]
    has_mild_attack = any(word in text for word in mild_attack_words)
    if not has_mild_attack:
        return False

    attack_targets = ["你", "你们", "你家", "你司", "你这", "你们的", "你这个", "你这种", "贵司", "这产品", "这服务", "这方案", "这个系统", "你们公司"]
    return any(target in text for target in attack_targets)


def _check_logical_contradiction(context: Context, user_input: str) -> str | None:
    """
    检测用户输入中的逻辑矛盾。

    通过对比当前输入与历史中的目标/陈述，检测明显矛盾。
    """
    contradiction_pairs = [
        (["赚钱", "赚", "收入", "加薪", "升职", "财务"], ["不想工作", "不想动", "懒得做", "不想努力", "躺平", "摆烂"]),
        (["减肥", "瘦", "健身", "锻炼", "运动"], ["不想动", "懒得", "太累", "太麻烦", "不想去"]),
        (["学习", "提升", "进步", "成长"], ["不想学", "懒得学", "太麻烦", "没时间学", "学不会"]),
        (["社交", "交朋友", "人脉", "关系"], ["不想见人", "社恐", "不想出门", "懒得社交"]),
        (["创业", "做生意", "开店"], ["不想冒险", "怕失败", "怕亏", "不敢"]),
        (["优惠", "便宜", "打折", "买", "交易", "合作", "考虑"], ["不行", "差", "烂", "垃圾", "骗子", "忽悠", "套路"]),
        (["你们的产品", "你们的服务", "你们公司"], ["不行", "差", "烂", "垃圾", "骗子", "忽悠"]),
    ]

    for positive_kw, negative_kw in contradiction_pairs:
        has_positive = any(kw in user_input for kw in positive_kw)
        has_negative = any(kw in user_input for kw in negative_kw)
        if has_positive and has_negative:
            pos_match = next((kw for kw in positive_kw if kw in user_input), "")
            neg_match = next((kw for kw in negative_kw if kw in user_input), "")
            return f"你提到{neg_match}，但又说{pos_match}。这两个矛盾，我们得先想清楚你到底要什么。"

    if context.goal.current.description and context.goal.current.description not in ("", "用户放弃", "未明确"):
        goal = context.goal.current.description
        if "不想" in user_input or "算了" in user_input or "放弃" in user_input:
            explicit_quit_words = ["不想做了", "不做了", "算了", "放弃", "不干了"]
            if "想要" in user_input and not any(word in user_input for word in explicit_quit_words):
                return None
            rewrite_intent_markers = [
                "不想再靠",
                "不想一直靠",
                "不想继续靠",
                "不想再这么",
                "不想总是",
                "不想老是",
                "不想只靠",
            ]
            if any(marker in user_input for marker in rewrite_intent_markers):
                return None
            resistance_words = ["麻烦", "太贵", "怕", "担心", "累", "没时间", "复杂"]
            if any(w in user_input for w in resistance_words):
                return None
            if len(user_input) < 30:
                return f"你的目标是{goal}，但现在你说不想做了。要不要先聊聊是什么让你想放弃？"

    user_emotion = safe_enum_value(context.user.emotion.type)
    if user_emotion in ["愤怒", "急躁"] or context.user.desires.pride > 0.6:
        derogatory = ["不行", "差", "烂", "垃圾", "骗子", "忽悠", "套路", "没用", "废话", "傻子", "浪费时间"]
        transactional = ["优惠", "便宜", "买", "交易", "合作", "考虑", "方案", "价格"]
        has_derogatory = any(kw in user_input for kw in derogatory)
        has_transactional = any(kw in user_input for kw in transactional)
        if has_derogatory and has_transactional:
            return "你一边说我们不行，一边又在考虑合作。这两个态度矛盾，你想清楚到底是要还是不要？"

    derogatory = ["不行", "差", "烂", "垃圾", "骗子", "忽悠", "套路", "没用", "废话", "傻子", "浪费时间", "懂什么", "资格", "背话术"]
    transactional = ["优惠", "便宜", "买", "交易", "合作", "考虑", "方案", "价格"]
    has_derogatory = _is_targeted_derogatory(user_input, derogatory)
    has_transactional = any(kw in user_input for kw in transactional)
    if has_derogatory and not has_transactional:
        return "你一直在贬低，却不说明具体问题。如果你想继续对话，请直接说出真实诉求，否则我们只能到此为止。"

    consecutive_attacks = 0
    for item in reversed(context.history[-6:]):
        if item.role == "user":
            content = item.content
            if _is_targeted_derogatory(content, derogatory):
                consecutive_attacks += 1
            else:
                break
    if consecutive_attacks >= 2:
        return "你已经连续两轮在攻击，但一直没有说明具体问题。我们回到最初的话题，你到底想解决什么？"

    return None
