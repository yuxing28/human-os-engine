"""
Human-OS Engine 3.1 — 技能注册表 (Skill Registry)

实现多场景混合调度：
1. 启动时扫描 skills/ 目录
2. 解析 SKILL.md 的 YAML Frontmatter
3. 运行时根据用户输入匹配多标签场景 (Top-3 + 优先级仲裁)
"""

import os
import re
import json
import time
import hashlib
from pathlib import Path
from collections import OrderedDict
from typing import Optional, List, Dict, Tuple
from utils.logger import info, warning, error


class SkillMetadata:
    """技能元数据"""
    def __init__(self, name: str, description: str, triggers: list, version: str = "1.0.0", path: str = ""):
        self.name = name
        self.description = description
        self.triggers = triggers
        self.version = version
        self.path = path


# 场景优先级映射 (情感 > 谈判 > 销售 > 管理)
# 依据：07-优先级规则模块 & 01-核心概念模块 (安全/危机优先)
SCENE_PRIORITY = {
    "emotion": 4,
    "negotiation": 3,
    "sales": 2,
    "management": 1
}

# 默认只自动加载这 4 个主场景 skill。
# 其他人格包 / 方法论包只能放在单独目录中手动调用，
# 不能自动混进主系统默认路由。
DEFAULT_AUTO_LOADED_SKILLS = {"sales", "management", "negotiation", "emotion"}


class SkillRegistry:
    """
    技能注册表
    
    负责：
    1. 启动时扫描 skills/ 目录
    2. 解析 SKILL.md 的 YAML Frontmatter
    3. 运行时根据用户输入匹配多标签场景 (Top-3 + 优先级仲裁)
    """

    PROJECT_ROOT = Path(__file__).resolve().parents[2]

    def __init__(self, skills_dir: str = "skills"):
        self.skills_dir = str(self._resolve_skills_dir(skills_dir))
        self.skills: dict[str, SkillMetadata] = {}
        self._scan_skills()
        
        # 场景分类缓存 (TTL 5 分钟)
        self._scene_cache: dict[str, tuple[float, tuple]] = {}
        self._cache_ttl = 300

    @classmethod
    def _resolve_skills_dir(cls, skills_dir: str) -> Path:
        """默认 skills 目录固定锚定到项目根目录。"""
        path = Path(skills_dir)
        if not path.is_absolute() and skills_dir == "skills":
            path = cls.PROJECT_ROOT / path
        return path.resolve()

    def _scan_skills(self):
        """扫描 skills/ 目录并解析元数据"""
        if not os.path.exists(self.skills_dir):
            info(f"技能目录不存在: {self.skills_dir}")
            return

        for entry in os.listdir(self.skills_dir):
            skill_path = os.path.join(self.skills_dir, entry)
            if not os.path.isdir(skill_path):
                continue

            if entry not in DEFAULT_AUTO_LOADED_SKILLS:
                info(f"跳过 (非默认主场景 skill): {entry}")
                continue

            skill_md = os.path.join(skill_path, "SKILL.md")
            if not os.path.exists(skill_md):
                info(f"跳过 (无 SKILL.md): {entry}")
                continue

            metadata = self._parse_frontmatter(skill_md)
            if metadata:
                metadata.path = skill_path
                self.skills[entry] = metadata
                info(f"加载技能: {metadata.name} ({entry})")

    def _parse_frontmatter(self, file_path: str) -> Optional[SkillMetadata]:
        """解析 Markdown 文件的 YAML Frontmatter"""
        try:
            import yaml
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 匹配 --- 之间的内容
            match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
            if not match:
                return None
            
            yaml_content = match.group(1)
            data = yaml.safe_load(yaml_content)
            
            return SkillMetadata(
                name=data.get('name', ''),
                description=data.get('description', ''),
                triggers=data.get('triggers', []),
                version=data.get('version', '1.0.0'),
            )
        except Exception as e:
            warning(f"解析 Frontmatter 失败 {file_path}: {e}")
            return None

    def _strip_frontmatter(self, content: str) -> str:
        match = re.match(r'^---\s*\n.*?\n---\s*\n', content, re.DOTALL)
        if match:
            return content[match.end():].strip()
        return content.strip()

    def _normalize_skill_line(self, line: str) -> str:
        cleaned = line.strip()
        cleaned = re.sub(r"^\d+\.\s*", "", cleaned)
        cleaned = re.sub(r"^[-*]\s*", "", cleaned)
        return cleaned.strip()

    def _summarize_skill_body(self, body: str) -> str:
        """把 SKILL.md 正文压成简短原则摘要，避免整段正文直接压进 prompt。"""
        section_order = [
            "这是什么场景",
            "先看什么",
            "最该做什么",
            "最不能做什么",
            "怎么自然往前接",
        ]
        sections: "OrderedDict[str, list[str]]" = OrderedDict((name, []) for name in section_order)
        current_section: Optional[str] = None

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
            if current_section is None:
                continue
            if line.startswith(">"):
                # 新口径下不再把例句直接注入 prompt
                continue

            cleaned = self._normalize_skill_line(line)
            if not cleaned:
                continue
            sections[current_section].append(cleaned)

        summary_parts = ["【场景原则】"]
        if sections["这是什么场景"]:
            summary_parts.append(f"- 场景：{sections['这是什么场景'][0]}")
        if sections["先看什么"]:
            summary_parts.append(f"- 先看：{'；'.join(sections['先看什么'][:3])}")
        if sections["最该做什么"]:
            summary_parts.append(f"- 重点：{'；'.join(sections['最该做什么'][:3])}")
        if sections["最不能做什么"]:
            summary_parts.append(f"- 禁区：{'；'.join(sections['最不能做什么'][:3])}")
        if sections["怎么自然往前接"]:
            summary_parts.append(f"- 往前接：{'；'.join(sections['怎么自然往前接'][:3])}")
        return "\n".join(summary_parts)

    def match_scenes(self, user_input: str) -> Tuple[Optional[str], List[str], Dict[str, float]]:
        """
        多标签场景识别 (LLM 语义分类 + 关键词 Fallback + 缓存)
        
        策略：
        1. 检查缓存 (TTL 5 分钟)
        2. LLM 语义分类（优先）
        3. LLM 失败时 Fallback 到关键词匹配
        4. 激活阈值过滤
        5. Top-3 截断
        6. 模糊区间仲裁
        """
        if not user_input:
            return None, [], {}

        # 1. 检查缓存
        cache_key = hashlib.md5(user_input.strip().lower().encode()).hexdigest()
        now = time.time()
        if cache_key in self._scene_cache:
            cached_time, cached_result = self._scene_cache[cache_key]
            if now - cached_time < self._cache_ttl:
                return cached_result
            else:
                del self._scene_cache[cache_key]

        # 2. 同时计算语义分和关键词分，避免模型漂移压过明确业务信号
        llm_scores = self._classify_scenes_llm(user_input)
        keyword_scores = self._classify_scenes_keywords(user_input)

        if llm_scores and keyword_scores:
            scores = {}
            scene_ids = set(llm_scores) | set(keyword_scores)
            for scene_id in scene_ids:
                llm_score = llm_scores.get(scene_id, 0.0)
                keyword_score = keyword_scores.get(scene_id, 0.0)
                # 语义分保持主导，但明确触发词要有足够话语权
                scores[scene_id] = max(llm_score, min(1.0, llm_score * 0.65 + keyword_score * 0.85))

            # 当关键词出现明显头部场景时，给予少量仲裁加权，防止被泛化语义误带偏
            keyword_rank = sorted(
                keyword_scores.items(),
                key=lambda x: (x[1], SCENE_PRIORITY.get(x[0], 0)),
                reverse=True
            )
            if keyword_rank:
                top_scene, top_score = keyword_rank[0]
                next_score = keyword_rank[1][1] if len(keyword_rank) > 1 else 0.0
                if top_score >= 0.3 and (top_score - next_score) >= 0.1:
                    scores[top_scene] = min(1.0, scores.get(top_scene, 0.0) + 0.2)
        else:
            scores = llm_scores or keyword_scores
        
        if not scores:
            return None, [], {}

        # 3. 激活阈值过滤
        # Fallback 关键词匹配时，单个强触发词也应能激活场景
        ACTIVATION_THRESHOLD = 0.03
        filtered_scores = {k: v for k, v in scores.items() if v >= ACTIVATION_THRESHOLD}
        if not filtered_scores:
            return None, [], scores

        # 4. Top-3 截断 & 排序
        sorted_scenes = sorted(
            filtered_scores.items(), 
            key=lambda x: (x[1], SCENE_PRIORITY.get(x[0], 0)), 
            reverse=True
        )
        
        top_3 = sorted_scenes[:3]
        
        # 5. 确定主副场景
        primary_id = top_3[0][0]
        secondary_ids = [s[0] for s in top_3[1:]]
        
        # 6. 模糊区间仲裁 (分差 < 0.15 时高优先级场景可抢占 Primary)
        if len(top_3) > 1:
            diff = top_3[0][1] - top_3[1][1]
            if diff < 0.15:
                p1_id = top_3[0][0]
                p2_id = top_3[1][0]
                if SCENE_PRIORITY.get(p2_id, 0) > SCENE_PRIORITY.get(p1_id, 0):
                    primary_id = p2_id
                    secondary_ids = [p1_id] + [s[0] for s in top_3[2:]]
                    secondary_ids = sorted(secondary_ids, key=lambda x: filtered_scores.get(x, 0), reverse=True)

        result = (primary_id, secondary_ids, filtered_scores)
        
        # 写入缓存
        self._scene_cache[cache_key] = (now, result)
        
        return result

    def _classify_scenes_llm(self, user_input: str) -> Dict[str, float]:
        """LLM 语义分类：不依赖关键词词库，直接理解语义"""
        try:
            from llm.nvidia_client import invoke_fast
            from utils.types import sanitize_for_prompt
            
            safe_input = sanitize_for_prompt(user_input, max_length=2000)
            
            prompt = f"""分析用户发言，判断涉及哪些场景，给出 0.0-1.0 的置信度分数。

场景定义：
- sales：涉及价格、合同、签单、报价、客户、竞品、预算、成本、利润、转化率等商业交易
- emotion：涉及情绪困扰、压力、焦虑、崩溃、失眠、伤心、绝望、委屈、孤独、疲惫、撑不住等情感诉求
- negotiation：涉及谈判、让步、底线、僵局、筹码、博弈、协商、BATNA 等协商博弈
- management：涉及团队、下属、绩效、考核、汇报、跨部门、内卷、员工、管理等管理事务

用户发言：{safe_input}

请仅输出 JSON，格式如下：
{{"sales": 0.0-1.0, "emotion": 0.0-1.0, "negotiation": 0.0-1.0, "management": 0.0-1.0}}

只输出 JSON，不要其他内容。"""
            
            result = invoke_fast(prompt, "你是场景分类专家。只输出 JSON，不要其他内容。")
            
            # 清理可能的 Markdown 包裹
            result = result.strip()
            if result.startswith("```"):
                result = result.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            if result.startswith("json"):
                result = result[4:].strip()
            
            parsed = json.loads(result)
            scores = {}
            for scene_id in ["sales", "emotion", "negotiation", "management"]:
                val = parsed.get(scene_id, 0)
                if isinstance(val, (int, float)):
                    # 钳制到 [0, 1] 范围
                    val = max(0.0, min(1.0, float(val)))
                    if val > 0:
                        scores[scene_id] = val
            
            return scores
            
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            warning(f"LLM 返回格式异常，回退到关键词匹配: {e}")
            return {}
        except Exception as e:
            warning(f"LLM 分类失败，回退到关键词匹配: {e}")
            return {}

    def _classify_scenes_keywords(self, user_input: str) -> Dict[str, float]:
        """关键词匹配 Fallback（当 LLM 不可用时）"""
        input_lower = user_input.lower()
        scores = {}
        
        for skill_id, meta in self.skills.items():
            score = 0.0
            for trigger in meta.triggers:
                trigger_lower = trigger.lower()
                if trigger_lower in input_lower:
                    # 长 trigger 往往语义更明确，避免“达标”之类短词抢走“下属绩效”这种更明确场景
                    score += 1.0 + min(len(trigger_lower), 6) * 0.15
            if score > 0:
                # fallback 侧重命中强度，不再按 trigger 总数稀释
                normalized = min(max(score * 0.2, 0.0), 1.0)
                scores[skill_id] = normalized
        
        return scores

    def match_skill(self, user_input: str) -> Optional[str]:
        """
        兼容旧接口：返回最佳匹配的场景 ID
        """
        primary, _, _ = self.match_scenes(user_input)
        return primary

    def get_skill_prompt(self, skill_id: str) -> str:
        """读取 SKILL.md 并压成简短原则摘要，避免整段正文直接注入。"""
        skill_md = os.path.join(self.skills_dir, skill_id, "SKILL.md")
        if not os.path.exists(skill_md):
            return ""
        
        try:
            with open(skill_md, 'r', encoding='utf-8') as f:
                content = f.read()

            body = self._strip_frontmatter(content)
            summarized = self._summarize_skill_body(body)
            return summarized or body
        except Exception as e:
            warning(f"读取 SKILL.md 失败: {e}")
            return ""

    def _build_world_state_brief(self, skill_id: str, world_state) -> str:
        """按场景只提最相关的局面状态，避免 skill 再次长成第二个大脑。"""
        if not world_state:
            return ""

        hints = []
        phase = getattr(world_state, "situation_stage", "") or ""
        risk = getattr(world_state, "risk_level", "") or ""
        tension = getattr(world_state, "tension_level", "") or ""
        progress = getattr(world_state, "progress_state", "") or ""
        commitment = getattr(world_state, "commitment_state", "") or ""
        action_loop = getattr(world_state, "action_loop_state", "") or ""
        focus = getattr(world_state, "next_turn_focus", "") or ""
        trust = getattr(world_state, "trust_level", "") or ""
        pressure = getattr(world_state, "pressure_level", "") or ""
        relationship = getattr(world_state, "relationship_position", "") or ""

        def add_if(name: str, value: str, *, skip_values: set[str] | None = None):
            skip_values = skip_values or set()
            if value and value not in skip_values:
                hints.append(f"{name}={value}")

        common_builders = {
            "sales": lambda: [
                add_if("阶段", phase, skip_values={"未识别"}),
                add_if("风险", risk, skip_values={"未识别", "low"}),
                add_if("推进", progress, skip_values={"未识别", "观察中"}),
                add_if("承诺", commitment, skip_values={"未识别", "未形成"}),
                add_if("动作", action_loop),
                add_if("焦点", focus),
            ],
            "management": lambda: [
                add_if("阶段", phase, skip_values={"未识别"}),
                add_if("压力", pressure, skip_values={"未识别", "low"}),
                add_if("张力", tension, skip_values={"未识别", "low"}),
                add_if("风险", risk, skip_values={"未识别", "low"}),
                add_if("动作", action_loop),
                add_if("焦点", focus),
            ],
            "negotiation": lambda: [
                add_if("阶段", phase, skip_values={"未识别"}),
                add_if("张力", tension, skip_values={"未识别", "low"}),
                add_if("风险", risk, skip_values={"未识别", "low"}),
                add_if("推进", progress, skip_values={"未识别", "观察中"}),
                add_if("动作", action_loop),
                add_if("焦点", focus),
            ],
            "emotion": lambda: [
                add_if("关系", relationship, skip_values={"未识别"}),
                add_if("信任", trust, skip_values={"未识别"}),
                add_if("张力", tension, skip_values={"未识别", "low"}),
                add_if("风险", risk, skip_values={"未识别", "low"}),
                add_if("动作", action_loop),
                add_if("焦点", focus),
            ],
        }

        builder = common_builders.get(skill_id)
        if builder:
            builder()
        else:
            add_if("阶段", phase, skip_values={"未识别"})
            add_if("风险", risk, skip_values={"未识别", "low"})
            add_if("张力", tension, skip_values={"未识别", "low"})
            add_if("推进", progress, skip_values={"未识别", "观察中"})
            add_if("承诺", commitment, skip_values={"未识别", "未形成"})
            add_if("动作", action_loop)
            add_if("焦点", focus)

        if not hints:
            return ""
        return "【当前局面】\n- " + " | ".join(hints)

    def build_skill_prompt(self, skill_id: str, world_state=None) -> str:
        """组合技能原则和少量局面状态，让 skills 只做辅助提醒。"""
        skill_prompt = self.get_skill_prompt(skill_id)
        world_state_brief = self._build_world_state_brief(skill_id, world_state)
        if skill_prompt and world_state_brief:
            return f"{skill_prompt}\n{world_state_brief}"
        return skill_prompt or world_state_brief


# 全局实例
_registry: Optional[SkillRegistry] = None

def get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        _registry = SkillRegistry()
    return _registry
