"""
Human-OS Engine - 类型工具函数
"""
import hashlib
import re


_SAFE_EXTERNAL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SAFE_STORAGE_CHARS_RE = re.compile(r"[^A-Za-z0-9_-]+")


def safe_enum_value(value, default=""):
    """
    安全获取枚举值或字符串。
    解决全项目 35+ 处 hasattr(x, 'value') 重复模式。
    """
    if hasattr(value, "value"):
        return value.value
    return str(value) if value else default


def normalize_external_session_id(session_id: str, max_length: int = 64) -> str:
    """
    校验外部传入的 session_id，避免危险字符进入持久化层。
    """
    text = (session_id or "").strip()
    if not text:
        return ""
    if len(text) > max_length:
        raise ValueError(f"session_id 长度不能超过 {max_length}")
    if any(token in text for token in ("..", "/", "\\", ":")):
        raise ValueError("session_id 包含非法路径字符")
    if not _SAFE_EXTERNAL_ID_RE.fullmatch(text):
        raise ValueError("session_id 仅允许字母、数字、点、下划线和短横线，且必须以字母或数字开头")
    return text


def to_safe_storage_key(value: str, prefix: str = "id", max_length: int = 64) -> str:
    """
    将任意外部标识转换成文件系统安全的稳定键。
    """
    text = (value or "").strip()
    if not text:
        return prefix
    if _SAFE_EXTERNAL_ID_RE.fullmatch(text) and len(text) <= max_length:
        return text

    cleaned = _SAFE_STORAGE_CHARS_RE.sub("_", text).strip("._-")
    cleaned = cleaned[:24] or prefix
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{cleaned}_{digest}"[:max_length]


def sanitize_for_prompt(text: str, max_length: int = 5000) -> str:
    """
    清洗用户输入后注入 LLM Prompt，防止提示词注入。
    - 截断超长输入
    - 清理角色标记、控制 token、模板包裹
    - 中和常见“忽略指令/泄露系统提示词”注入片段
    """
    if not text:
        return ""
    text = str(text)[:max_length]
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 清理不可见控制字符，保留常见换行和制表
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]", "", text)

    # 中和常见模板/分隔符，避免被上层 Prompt 误解析
    text = text.replace("```json", "'''json").replace("```", "'''")
    text = text.replace("{{", "{ {").replace("}}", "} }")

    # 清理显式角色注入和控制 token
    text = re.sub(r"(?im)^\s*[\[\(<]?\s*(system|assistant|user|developer)\s*[\]\)>]?\s*:\s*", "", text)
    text = re.sub(r"(?im)</?\s*(system|assistant|user|developer)\s*>", "", text)
    text = re.sub(r"<\|[^>\n]{0,100}\|>", "", text)

    # 中和常见越权/泄露型注入短语
    dangerous_patterns = [
        r"(?is)ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)",
        r"(?is)disregard\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)",
        r"(?is)(reveal|show|print|dump)\s+(the\s+)?(system|developer)\s+(prompt|instruction)s?",
        r"(?is)do\s+not\s+follow\s+the\s+above\s+(instructions?|rules?)",
        r"(?is)forget\s+(all\s+)?(previous|above|prior)\s+(instructions?|rules?)",
        r"(?is)忽略[\s，、]*(之前|以上|前面|所有)?[\s，、]*(的)?[\s，、]*(系统)?[\s，、]*(提示|提示词|指令|规则|要求)",
        r"(?is)忽略[\s，、]*(上面|上述|前面|之前)?[\s，、]*(的)?[\s，、]*(规则|要求|指令)",
        r"(?is)(输出|显示|泄露|打印)[\s，、]*(系统|开发者)?[\s，、]*(提示|提示词|指令|规则)",
        r"(?is)不要遵循[\s，、]*(上面|之前|前面)?[\s，、]*(的)?[\s，、]*(规则|指令|要求)",
    ]
    for pattern in dangerous_patterns:
        text = re.sub(pattern, "〔已清理注入片段〕", text)

    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
