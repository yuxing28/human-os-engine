"""人设一致性检查与重写。"""

from schemas.context import Context


def _check_persona_consistency(text: str, context: Context) -> tuple[bool, str]:
    """规则方式检查输出是否符合既定人设。"""
    from utils.constants import CUSTOMER_SERVICE_WORDS, CLINGY_WORDS, SELF_REF_WORDS

    for word in CUSTOMER_SERVICE_WORDS:
        if word in text:
            return False, f"包含客服词汇: {word}"

    for word in CLINGY_WORDS:
        if word in text:
            return False, f"包含肉麻表达: {word}"

    for word in SELF_REF_WORDS:
        if word in text:
            return False, f"包含不当自称: {word}"

    if len(context.history) >= 2:
        last_system_output = None
        for item in reversed(context.history):
            if item.role == "system":
                last_system_output = item.content
                break

        if last_system_output:
            current_exclaim = text.count("!") + text.count("！")
            last_exclaim = last_system_output.count("!") + last_system_output.count("！")

            if current_exclaim > 3 and last_exclaim == 0:
                return False, "感叹号密度突增，语气变化过大"
            if current_exclaim == 0 and last_exclaim > 3:
                return False, "感叹号密度突降，语气变化过大"

    return True, ""


def _rewrite_for_persona(text: str, reason: str) -> str:
    """人设不一致时进行规则重写。"""
    customer_service_replacements = {
        "亲，": "",
        "小助手": "我",
        "AI助手": "我",
        "为您服务": "",
        "抱歉，": "",
        "对不起，": "",
        "不好意思，": "",
        "打扰了": "",
    }

    result = text
    for bad, good in customer_service_replacements.items():
        result = result.replace(bad, good)

    clingy_replacements = {
        "宝贝": "",
        "亲爱的": "",
        "爱你": "",
        "么么哒": "",
        "抱抱": "",
        "我好心疼": "这确实不容易",
        "心疼你": "这确实不容易",
    }
    for bad, good in clingy_replacements.items():
        result = result.replace(bad, good)

    self_replacements = {
        "我是AI，": "我觉得",
        "我是人工智能，": "我觉得",
        "我是助手，": "我觉得",
        "作为AI，": "我觉得",
        "作为助手，": "我觉得",
    }
    for bad, good in self_replacements.items():
        result = result.replace(bad, good)

    return result
