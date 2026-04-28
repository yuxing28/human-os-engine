"""
Human-OS Engine 3.0 — 策略评估器 (Strategy Evaluator)

[离线工具 - 不进主链] 本模块用于策略复盘分析，不参与沙盒主线的运行时评估。
沙盒主线统一使用 simulation/llm_judge.py 的10分制评估。

阶段三核心组件：对每一轮使用的策略进行复盘评估，生成经验数据，用于后续的自我优化。
"""

import json
import os
from typing import Dict, Any, Optional

from llm.nvidia_client import invoke_standard
from utils.file_lock import safe_json_read, safe_json_write
from utils import logger
from utils.types import sanitize_for_prompt


class StrategyEvaluator:
    """
    策略复盘评估引擎
    
    在每轮对话结束后，分析当前策略的有效性，并生成结构化建议。
    """

    def evaluate(
        self, 
        goal_id: str,
        emotion_type: str,
        trust_level: str,
        strategy_desc: str,
        weapons_used: list,
        feedback: str,
        user_response_summary: str
    ) -> Optional[Dict[str, Any]]:
        """
        评估策略效果
        
        Args:
            goal_id: 当前目标
            emotion_type: 用户情绪
            trust_level: 用户信任度
            strategy_desc: 使用的策略描述
            weapons_used: 使用的武器列表
            feedback: 系统推断的反馈 (positive/negative/neutral)
            user_response_summary: 用户回复摘要
            
        Returns:
            Dict: 评估结果 (score, analysis, suggestion)，失败返回 None
        """
        
        # 1. 构建 Prompt
        prompt = self._build_prompt(
            goal_id, emotion_type, trust_level, 
            strategy_desc, weapons_used, feedback, user_response_summary
        )
        
        system_prompt = """你是一个资深的博弈策略分析师。请根据当前局势和结果，对刚刚使用的策略进行复盘评估。
输出必须是合法的 JSON 格式，不要包含任何解释性文字。
JSON 格式：
{
    "score": 1-5 (整数，1 分极差，5 分极好),
    "analysis": "简短分析为什么有效或无效（一句话）",
    "suggestion": "针对此类局势，下次的改进建议（一句话）"
}"""

        # 2. 调用 LLM
        try:
            response = invoke_standard(prompt, system_prompt)
            
            # 3. 解析输出
            if response.startswith("```json"):
                response = response.split("```json")[1]
            if response.endswith("```"):
                response = response.rsplit("```", 1)[0]
            
            data = json.loads(response.strip())
            
            # 4. 验证数据
            if "score" not in data or "analysis" not in data:
                return None
                
            return {
                "score": int(data.get("score", 3)),
                "analysis": data.get("analysis", ""),
                "suggestion": data.get("suggestion", "")
            }
            
        except Exception as e:
            logger.warning("策略评估失败，跳过本轮经验沉淀", error=str(e))
            return None

    def _build_prompt(
        self, goal_id, emotion_type, trust_level, 
        strategy_desc, weapons_used, feedback, user_response_summary
    ) -> str:
        """构建评估 Prompt"""
        safe_goal_id = sanitize_for_prompt(goal_id, max_length=200)
        safe_emotion_type = sanitize_for_prompt(emotion_type, max_length=80)
        safe_trust_level = sanitize_for_prompt(trust_level, max_length=80)
        safe_strategy_desc = sanitize_for_prompt(strategy_desc, max_length=600)
        safe_feedback = sanitize_for_prompt(feedback, max_length=80)
        safe_user_response = sanitize_for_prompt(user_response_summary, max_length=1200)
        safe_weapons = [sanitize_for_prompt(str(w), max_length=80) for w in weapons_used]
        
        return f"""
局势回顾：
1. 目标：{safe_goal_id}
2. 用户状态：情绪 {safe_emotion_type}, 信任 {safe_trust_level}
3. 我方策略：{safe_strategy_desc} (武器：{', '.join(safe_weapons)})
4. 用户反应：{safe_user_response}
5. 系统反馈判定：{safe_feedback}

请评估该策略的有效性并给出建议。
"""

    def save_experience(self, experience: Dict[str, Any], file_path: str = "data/memory/strategy_experience.json"):
        """保存经验到本地文件（安全写入）"""
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        data = safe_json_read(file_path, [])
        data.append(experience)
        
        if len(data) > 500:
            data = data[-500:]
            
        safe_json_write(file_path, data)
