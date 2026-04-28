"""
Human-OS Engine 3.0 — 动态策略引擎 (Dynamic Strategy Engine)

阶段二核心组件：彻底抛弃静态组合，由 LLM 根据战局实时生成策略。
"""

import json
import math
import os
import re
from typing import Optional

from schemas.strategy import StrategyPlan
from modules.L3.weapon_arsenal import ALL_WEAPONS
from llm.nvidia_client import invoke_fast
from utils.types import sanitize_for_prompt


class DynamicStrategyEngine:
    """
    动态策略生成引擎
    
    根据当前上下文（目标、情绪、信任、历史）实时生成策略组合。
    """

    def generate(
        self, 
        goal_id: str, 
        goal_desc: str, 
        emotion_type: str, 
        emotion_intensity: float,
        trust_level: str,
        history_summary: str = ""
    ) -> Optional[StrategyPlan]:
        """
        生成动态策略
        
        Args:
            goal_id: 目标 ID
            goal_desc: 目标描述
            emotion_type: 对手情绪类型
            emotion_intensity: 情绪强度 (0.0-1.0)
            trust_level: 信任等级 (high/medium/low)
            history_summary: 历史交锋摘要
            
        Returns:
            StrategyPlan: 动态生成的策略计划，失败返回 None
        """
        
        # 1. 构建 Prompt
        prompt = self._build_prompt(
            goal_id, goal_desc, emotion_type, emotion_intensity, 
            trust_level, history_summary
        )
        
        system_prompt = """你是一个高级博弈策略专家。请根据当前局势，从武器库中挑选最合适的 3 个武器组合，并设定语气基调。
输出必须是合法的 JSON 格式，不要包含任何解释性文字。
JSON 格式：
{
    "weapons": ["武器 1", "武器 2", "武器 3"],
    "tone": "语气基调（如：专业冷静、共情温和、坚定强硬）",
    "reasoning": "简短的策略理由（一句话）"
}"""

        # 2. 调用 LLM（带重试机制）
        max_retries = 2
        last_error = None
        
        for attempt in range(max_retries + 1):
            try:
                response = invoke_fast(prompt, system_prompt)
                
                # 3. 解析输出（增强容错）
                if not response or not response.strip():
                    raise ValueError("LLM 返回空内容")
                
                response = response.strip()
                
                # 清理所有 Markdown 变体
                if response.startswith("```json"):
                    response = response[7:]
                elif response.startswith("```"):
                    response = response[3:]
                
                if response.endswith("```"):
                    response = response[:-3]
                
                response = response.strip()
                if not response:
                    raise ValueError("LLM 返回内容为空（清理后）")
                
                data = json.loads(response)
                
                # 4. 验证武器
                weapons = data.get("weapons", [])
                if not isinstance(weapons, list):
                    raise ValueError(f"weapons 不是列表: {type(weapons)}")
                
                valid_weapons = [w for w in weapons if w in ALL_WEAPONS]
                
                if not valid_weapons:
                    raise ValueError(f"无有效武器: {weapons}")
                    
                # 5. 构建 StrategyPlan
                return StrategyPlan(
                    mode="Dynamic",
                    combo_name="动态组合",
                    stage="动态生成",
                    description=data.get("reasoning", "LLM 动态生成策略"),
                    fallback="",
                    weapons=valid_weapons,
                    tone=data.get("tone", "专业")
                )
                
            except json.JSONDecodeError as e:
                last_error = e
                if attempt < max_retries:
                    print(f"[DynamicStrategyEngine] JSON 解析失败 (尝试 {attempt+1}/{max_retries+1})，重试...")
                    continue
            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    print(f"[DynamicStrategyEngine] 生成失败 (尝试 {attempt+1}/{max_retries+1}): {e}，重试...")
                    continue
        
        print(f"[DynamicStrategyEngine] {max_retries+1} 次尝试均失败: {last_error}")
        return None

    def _retrieve_experience(self, goal_id: str, emotion_type: str, top_k: int = 3) -> list[dict]:
        """
        从经验记忆库检索相似历史案例（语义匹配 + 多维度加权）
        
        检索策略：
        1. 构建查询向量（goal_id + emotion_type + 关键词）
        2. 用 TF-IDF 风格的余弦相似度计算语义相似度
        3. 结合评分加权排序
        """
        exp_path = os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'memory', 'strategy_experience.json')
        if not os.path.exists(exp_path):
            return []
        
        try:
            with open(exp_path, 'r', encoding='utf-8') as f:
                experiences = json.load(f)
        except Exception:
            return []
        
        if not experiences:
            return []
        
        # 构建查询文本（只保留核心语义词，去除结构词）
        goal_core = goal_id.split('.')[-1] if '.' in goal_id else goal_id
        # 查询只用核心词和情绪类型，避免"目标:"、"情绪:"等结构词干扰
        query_text = f"{goal_core} {emotion_type}"
        
        # 中文分词（简单方案：按字符 n-gram + 常用词）
        query_tokens = self._tokenize(query_text)
        
        scored = []
        for exp in experiences:
            situation = exp.get('situation', '')
            analysis = exp.get('analysis', '')
            suggestion = exp.get('suggestion', '')
            exp_score = exp.get('score', 0)
            exp_weapons = exp.get('weapons', [])
            
            # 构建文档文本
            doc_text = f"{situation} {analysis} {suggestion}"
            doc_tokens = self._tokenize(doc_text)
            
            # 语义相似度（余弦相似度）
            semantic_sim = self._cosine_similarity(query_tokens, doc_tokens)
            
            # 必要条件：语义相似度 > 0.05（过滤纯噪声）
            if semantic_sim < 0.05:
                continue
            
            # 多维度加权评分
            score = 0.0
            
            # 1. 语义相似度（0-1 范围，权重 8，主导排序）
            score += semantic_sim * 8.0
            
            # 2. 目标精确匹配（额外加分，但不作为必要条件）
            if goal_id and goal_id in situation:
                score += 3.0
            elif goal_core and goal_core in situation:
                score += 1.5
            
            # 3. 情绪匹配
            if emotion_type and emotion_type in situation:
                score += 1.0
            
            # 4. 高评分经验优先
            if exp_score >= 4:
                score += 0.5
            
            # 5. 负面经验也有参考价值
            if exp_score <= 2:
                score += 0.25
            
            if score > 0:
                scored.append((score, exp))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [exp for _, exp in scored[:top_k]]

    @staticmethod
    def _tokenize(text: str) -> dict[str, int]:
        """
        零依赖中文分词：字符 bigram + 英文单词
        
        不用 jieba 等外部库，保持零依赖。
        """
        tokens: dict[str, int] = {}
        
        # 提取英文单词
        for word in re.findall(r'[a-zA-Z_]+', text):
            w = word.lower()
            tokens[w] = tokens.get(w, 0) + 1
        
        # 中文字符 bigram（2-gram）
        chinese_chars = re.sub(r'[a-zA-Z0-9_\s]', '', text)
        for i in range(len(chinese_chars) - 1):
            bigram = chinese_chars[i:i+2]
            tokens[bigram] = tokens.get(bigram, 0) + 1
        
        # 单个中文字符（unigram）
        for char in chinese_chars:
            tokens[char] = tokens.get(char, 0) + 1
        
        return tokens

    @staticmethod
    def _cosine_similarity(tokens_a: dict[str, int], tokens_b: dict[str, int]) -> float:
        """
        计算两个词频向量的余弦相似度
        """
        if not tokens_a or not tokens_b:
            return 0.0
        
        # 所有词汇
        all_tokens = set(tokens_a.keys()) | set(tokens_b.keys())
        
        # 向量点积
        dot_product = sum(tokens_a.get(t, 0) * tokens_b.get(t, 0) for t in all_tokens)
        
        # 向量模长
        norm_a = math.sqrt(sum(v * v for v in tokens_a.values()))
        norm_b = math.sqrt(sum(v * v for v in tokens_b.values()))
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)

    def _build_prompt(
        self, 
        goal_id, goal_desc, emotion_type, emotion_intensity, 
        trust_level, history_summary
    ) -> str:
        """构建上下文 Prompt（含经验检索 Few-Shot）"""
        safe_goal_id = sanitize_for_prompt(goal_id, max_length=200)
        safe_goal_desc = sanitize_for_prompt(goal_desc, max_length=500)
        safe_emotion_type = sanitize_for_prompt(emotion_type, max_length=80)
        safe_trust_level = sanitize_for_prompt(trust_level, max_length=80)
        safe_history_summary = sanitize_for_prompt(history_summary, max_length=1200)
        
        # 获取可用武器列表
        available_weapons = list(ALL_WEAPONS.keys())[:50]
        weapon_str = ", ".join(available_weapons)
        
        # 【BUG-3 修复】检索历史经验
        experiences = self._retrieve_experience(goal_id, emotion_type)
        exp_section = ""
        if experiences:
            exp_lines = ["历史经验参考："]
            for i, exp in enumerate(experiences, 1):
                exp_lines.append(
                    f"  {i}. 策略 [{exp.get('strategy', '未知')}] "
                    f"武器 {exp.get('weapons', [])} "
                    f"评分 {exp.get('score', '?')}/5 "
                    f"分析：{exp.get('analysis', '')} "
                    f"建议：{exp.get('suggestion', '')}"
                )
            exp_section = "\n" + "\n".join(exp_lines) + "\n"
        
        return f"""
当前局势分析：
1. 核心目标：{safe_goal_id} ({safe_goal_desc})
2. 对手状态：情绪 {safe_emotion_type} (强度 {emotion_intensity})，信任度 {safe_trust_level}
3. 历史交锋：{safe_history_summary if safe_history_summary else "首轮博弈"}
{exp_section}
可用武器库：
{weapon_str}

请根据局势（参考历史经验），挑选 3 个武器并设定语气基调。
"""
