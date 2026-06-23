"""
Human-OS Engine - L5 知识库加载器

从子模块加载知识，统一合并后提供查询接口。

子模块：
- energy/knowledge.py：能量管理、崩溃修复
- engineer_cases/cases.py：6 个实战案例
- life_methodology/methodology.py：情绪管理、欲望管理、认知偏误等
- marketing/marketing.py：认知偏差、赚钱铁律、人群透镜、情绪操盘、社会原力等
"""

from dataclasses import dataclass, field

# ===== 从子模块导入 =====

from modules.L5.energy.knowledge import ENERGY_KNOWLEDGE
from modules.L5.engineer_cases.cases import ENGINEER_CASES, CaseEntry as CaseEntryFromCases
from modules.L5.life_methodology.methodology import METHODOLOGY_KNOWLEDGE
from modules.L5.marketing.marketing import MARKETING_KNOWLEDGE


# ===== 数据结构（统一接口）=====

@dataclass
class KnowledgeEntry:
    """知识条目"""
    id: str
    title: str
    category: str  # life_methodology/engineer_cases/marketing/energy
    keywords: list[str]
    content: str
    source_file: str
    trigger_conditions: dict = field(default_factory=dict)
    action_mapping: str = ""
    priority_scenes: list[str] = field(default_factory=list)


@dataclass
class CaseEntry:
    """案例条目"""
    id: str
    title: str
    category: str
    scenario_keywords: list[str]  # 场景关键词
    emotion_types: list[str]      # 适用情绪类型
    desires: list[str]            # 适用欲望
    content: str
    source_file: str
    goal_types: list[str]
    core_purpose: str
    tactical_sequence: list[str]
    emergency_plan: str
    quick_principle: str
    applicable_scenes: list[str] = field(default_factory=list)
    relationship_positions: list[str] = field(default_factory=list)
    continuation_hints: list[str] = field(default_factory=list)


# ===== 知识库合并 =====

def _convert_knowledge(raw: dict) -> dict[str, KnowledgeEntry]:
    """将原始知识条目转换为统一格式"""
    result = {}
    for key, entry in raw.items():
        if hasattr(entry, '__dataclass_fields__'):
            result[key] = KnowledgeEntry(
                id=entry.id,
                title=entry.title,
                category=entry.category,
                keywords=entry.keywords,
                content=entry.content,
                source_file=entry.source_file,
                trigger_conditions=getattr(entry, "trigger_conditions", {}) or {},
                action_mapping=getattr(entry, "action_mapping", "") or "",
                priority_scenes=getattr(entry, "priority_scenes", []) or [],
            )
        else:
            result[key] = entry
    return result


def _convert_cases(raw: dict) -> dict[str, CaseEntry]:
    """将原始案例条目转换为统一格式"""
    result = {}
    for key, entry in raw.items():
        if hasattr(entry, '__dataclass_fields__'):
            result[key] = CaseEntry(
                id=entry.id,
                title=entry.title,
                category=entry.category,
                scenario_keywords=entry.scenario_keywords,
                emotion_types=entry.emotion_types,
                desires=entry.desires,
                content=entry.content,
                source_file=entry.source_file,
                goal_types=getattr(entry, "goal_types", []),
                core_purpose=getattr(entry, "core_purpose", ""),
                tactical_sequence=getattr(entry, "tactical_sequence", []),
                emergency_plan=getattr(entry, "emergency_plan", ""),
                quick_principle=getattr(entry, "quick_principle", ""),
                applicable_scenes=getattr(entry, "applicable_scenes", []) or [],
                relationship_positions=getattr(entry, "relationship_positions", []) or [],
                continuation_hints=getattr(entry, "continuation_hints", []) or [],
            )
        else:
            result[key] = entry
    return result


# 合并所有知识库
KNOWLEDGE_DATABASE: dict[str, KnowledgeEntry] = {
    **_convert_knowledge(ENERGY_KNOWLEDGE),
    **_convert_knowledge(METHODOLOGY_KNOWLEDGE),
    **_convert_knowledge(MARKETING_KNOWLEDGE),
}

# 合并所有案例库
CASE_DATABASE: dict[str, CaseEntry] = _convert_cases(ENGINEER_CASES)


# ===== 查询接口 =====

def get_all_knowledge() -> dict[str, KnowledgeEntry]:
    """获取所有知识条目"""
    return KNOWLEDGE_DATABASE


def get_all_cases() -> dict[str, CaseEntry]:
    """获取所有案例条目"""
    return CASE_DATABASE


def search_knowledge(query: str, limit: int = 3) -> list[KnowledgeEntry]:
    """搜索知识条目"""
    query_lower = query.lower()
    scored = []

    for entry in KNOWLEDGE_DATABASE.values():
        score = 0
        # 关键词匹配
        for kw in entry.keywords:
            if kw in query_lower:
                score += 2
        # 标题匹配
        if entry.title.lower() in query_lower:
            score += 3
        # 内容匹配
        if any(word in entry.content.lower() for word in query_lower.split()):
            score += 1

        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:limit]]


def search_cases(query: str, limit: int = 3) -> list[CaseEntry]:
    """搜索案例"""
    query_lower = query.lower()
    scored = []

    for entry in CASE_DATABASE.values():
        score = 0
        # 场景关键词匹配
        for kw in entry.scenario_keywords:
            if kw in query_lower:
                score += 3
        # 标题匹配
        if any(word in entry.title.lower() for word in query_lower.split()):
            score += 2

        if score > 0:
            scored.append((score, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:limit]]


# ===== 测试入口 =====

if __name__ == "__main__":
    print(f"知识库条目数: {len(KNOWLEDGE_DATABASE)}")
    print(f"案例库条目数: {len(CASE_DATABASE)}")

    print("\n=== 知识搜索测试 ===")
    results = search_knowledge("如何控制情绪")
    for r in results:
        print(f"- {r.title}: {r.content[:50]}...")

    print("\n=== 案例搜索测试 ===")
    results = search_cases("老板让我加班")
    for r in results:
        print(f"- {r.title}")
