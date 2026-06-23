"""
扩展人格包读取器

这层只做一件事：
把 skill_packs/ 里的扩展包读出来，压成和主 skills 类似的短摘要，
方便我们手动注入测试。

它不会进入主系统默认路由。
"""

from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import re
from typing import Iterable

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PACK_ROOT = PROJECT_ROOT / "skill_packs"

_SECTION_ORDER = [
    "这是什么",
    "先看什么",
    "最该补什么",
    "最该怎么判断",
    "更像雷军式的判断口径",
    "最不能做什么",
    "怎么自然往前接",
    "这层的定位",
]


def resolve_pack_root(pack_root: str | Path | None = None) -> Path:
    root = Path(pack_root) if pack_root else DEFAULT_PACK_ROOT
    if not root.is_absolute():
        root = (PROJECT_ROOT / root).resolve()
    return root


def _split_frontmatter(content: str) -> tuple[dict, str]:
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        return {}, content.strip()
    frontmatter = yaml.safe_load(match.group(1)) or {}
    body = content[match.end():].strip()
    return frontmatter, body


def _normalize_line(line: str) -> str:
    cleaned = line.strip()
    cleaned = re.sub(r"^\d+\.\s*", "", cleaned)
    cleaned = re.sub(r"^[-*]\s*", "", cleaned)
    cleaned = re.sub(r"^###\s*", "", cleaned)
    cleaned = cleaned.strip("：:")
    return cleaned.strip()


def summarize_extension_skill_content(content: str, title: str = "") -> str:
    _, body = _split_frontmatter(content)
    sections: "OrderedDict[str, list[str]]" = OrderedDict((name, []) for name in _SECTION_ORDER)
    current_section: str | None = None

    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("# "):
            continue
        if line.startswith("## "):
            heading = line[3:].strip()
            current_section = heading if heading in sections else None
            continue
        if line.startswith(">"):
            continue
        if current_section is None:
            continue
        cleaned = _normalize_line(line)
        if cleaned and cleaned not in {"它只负责", "它不负责"}:
            sections[current_section].append(cleaned)

    lines = [f"【{title}】" if title else "【扩展人格】", "【扩展原则】"]
    if sections["这是什么"]:
        lines.append(f"- 定位：{sections['这是什么'][0]}")
    if sections["先看什么"]:
        lines.append(f"- 先看：{'；'.join(sections['先看什么'][:3])}")
    if sections["最该补什么"]:
        lines.append(f"- 重点：{'；'.join(sections['最该补什么'][:4])}")
    elif sections["最该怎么判断"]:
        lines.append(f"- 判断：{'；'.join(sections['最该怎么判断'][:4])}")
    if sections["更像雷军式的判断口径"]:
        lines.append(f"- 雷军式口径：{'；'.join(sections['更像雷军式的判断口径'][:4])}")
    if sections["最不能做什么"]:
        lines.append(f"- 禁区：{'；'.join(sections['最不能做什么'][:4])}")
    if sections["怎么自然往前接"]:
        lines.append(f"- 往前接：{'；'.join(sections['怎么自然往前接'][:3])}")
    if sections["这层的定位"]:
        lines.append(f"- 边界：{'；'.join(sections['这层的定位'][:2])}")
    return "\n".join(lines)


def load_extension_skill_prompt(pack_name: str, skill_id: str, pack_root: str | Path | None = None) -> str:
    root = resolve_pack_root(pack_root)
    skill_file = root / pack_name / skill_id / "SKILL.md"
    if not skill_file.exists():
        raise FileNotFoundError(f"找不到扩展技能文件: {skill_file}")

    content = skill_file.read_text(encoding="utf-8")
    frontmatter, _ = _split_frontmatter(content)
    title = frontmatter.get("name", skill_id)
    return summarize_extension_skill_content(content, title=title)


def build_extension_pack_prompt(
    pack_name: str,
    skill_ids: Iterable[str],
    pack_root: str | Path | None = None,
) -> str:
    prompts: list[str] = []
    normalized_skill_ids: list[str] = []
    for skill_id in skill_ids:
        skill_id = str(skill_id).strip()
        if not skill_id:
            continue
        normalized_skill_ids.append(skill_id)
        prompts.append(load_extension_skill_prompt(pack_name, skill_id, pack_root=pack_root))

    if not prompts:
        return ""

    joined = "\n\n".join(prompts)
    guardrails = ""
    if pack_name == "leijun" and "leijun_product" in normalized_skill_ids:
        guardrails = (
            "\n【雷军产品扩展禁区】\n"
            "本轮如果涉及价格、价值或产品取舍，优先讲用户价值、体验、长期口碑和厚道感。\n"
            "不要使用原价/现价、限时、仅剩、已有多少人选择、从众背书、稀缺压迫这类销售压单技巧。\n"
            "不要凭空编造具体功能、服务承诺、客户案例、行业数据或市场背书；用户没提供事实时，只给表达框架。\n"
            "如果主场景是 sales，也要把销售推进收回到真实价值和用户是否适合，不要把产品表达变成促销话术。\n"
        )
    return (
        "【可选人格扩展包】\n"
        "下面这些内容只做辅助参考，不替主系统看局面，不替主系统做最终决策。\n"
        "但本轮已经明确启用这个扩展，所以最终回复要体现一点差异：更会收主线、更会讲清为什么、更少空泛推进。\n"
        "使用方式：只借判断口径和表达气质，不模仿口头禅，不喊口号，不改主系统的核心结论。\n"
        f"{guardrails}"
        f"{joined}"
    )
