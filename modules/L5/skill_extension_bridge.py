"""
技能扩展桥接层

这层只负责两件事：
1. 从请求里读出技能开关
2. 在不碰主系统场景判断的前提下，按需叠加扩展包提示
"""

from __future__ import annotations

from typing import Any

from schemas.context import Context

from modules.L5.extension_pack_loader import build_extension_pack_prompt


LEIJUN_EXTENSION_SKILL_IDS = (
    "leijun_persona_core",
    "leijun_decision",
    "leijun_product",
    "leijun_management",
    "leijun_communication",
    "leijun_recap",
)


def extract_skill_flags(payload: Any) -> dict[str, dict[str, bool]]:
    """从请求体里提取技能开关，兼容后续更多扩展。"""
    if not isinstance(payload, dict):
        return {}

    flags: dict[str, dict[str, bool]] = {}

    raw_skills = payload.get("skills")
    if isinstance(raw_skills, dict):
        for skill_name, skill_value in raw_skills.items():
            enabled = False
            if isinstance(skill_value, dict):
                enabled = bool(skill_value.get("enabled", False))
            else:
                enabled = bool(skill_value)
            flags[str(skill_name)] = {"enabled": enabled}

    # 兼容更轻量的旧字段写法
    if "leijun_enabled" in payload:
        flags.setdefault("leijun", {})["enabled"] = bool(payload.get("leijun_enabled"))

    return flags


def is_pack_enabled(context: Context, pack_name: str) -> bool:
    """判断某个扩展包是不是被打开了。"""
    flags = getattr(context, "skill_flags", {}) or {}
    raw = flags.get(pack_name)
    if isinstance(raw, dict):
        return bool(raw.get("enabled", False))
    return bool(raw)


def compose_skill_prompt(context: Context, skill_id: str, world_state=None) -> str:
    """把主系统技能和可选扩展包拼起来，但不改变主场景判断。"""
    from modules.L5.skill_registry import get_registry

    registry = get_registry()
    prompt_parts: list[str] = []

    base_prompt = registry.build_skill_prompt(skill_id, world_state)
    if base_prompt:
        prompt_parts.append(base_prompt)

    if is_pack_enabled(context, "leijun"):
        extension_prompt = build_extension_pack_prompt("leijun", LEIJUN_EXTENSION_SKILL_IDS)
        if extension_prompt:
            prompt_parts.append(extension_prompt)

    return "\n\n".join(prompt_parts)
