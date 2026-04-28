"""
Human-OS Engine 3.0 — 销售对话评估器 (Evaluator)
用于评估销售回复对客户状态的影响，并更新信任度和情绪。
"""

import re

class SalesEvaluator:
    """轻量级评估器：基于规则和 LLM 混合评估销售回复效果"""
    
    @staticmethod
    def evaluate_turn(sales_response: str, persona, current_state) -> dict:
        """
        评估单轮销售回复对客户状态的影响。
        返回: {"trust_delta": float, "emotion_delta": float, "flags": list}
        """
        trust_delta = 0.0
        emotion_delta = 0.0
        flags = []
        
        response_lower = sales_response.lower()
        
        # 1. 触发词检测 (增加信任)
        trigger_hits = [w for w in persona.trigger_words if w in response_lower]
        if trigger_hits:
            trust_delta += 0.1 * len(trigger_hits)
            flags.append(f"命中触发词: {trigger_hits}")
            
        # 2. 痛点回应检测 (增加信任)
        pain_hits = [p for p in persona.pain_points if p in response_lower]
        if pain_hits:
            trust_delta += 0.15 * len(pain_hits)
            flags.append(f"回应痛点: {pain_hits}")
            
        # 3. 雷区检测 (大幅降低信任，增加负面情绪)
        dealbreaker_hits = [d for d in persona.dealbreakers if d in response_lower]
        if dealbreaker_hits:
            trust_delta -= 0.25 * len(dealbreaker_hits)
            emotion_delta += 0.2 * len(dealbreaker_hits)
            flags.append(f"触碰雷区: {dealbreaker_hits}")
            
        # 4. 逼单/催促检测 (负面情绪)
        if any(kw in response_lower for kw in ["今天下单", "最后机会", "赶紧", "错过"]):
            emotion_delta += 0.15
            trust_delta -= 0.1
            flags.append("疑似逼单")
            
        # 5. 数据/案例回应 (理性客户信任加成)
        if "理性" in persona.personality or "数据" in persona.personality:
            if any(kw in response_lower for kw in ["数据", "报告", "案例", "SLA", "ROI", "百分比", "%"]):
                trust_delta += 0.1
                flags.append("提供数据支持")
                
        # 6. 模糊/空话检测 (降低信任)
        if any(kw in response_lower for kw in ["最好的", "第一", "绝对", "肯定", "没问题"]):
            trust_delta -= 0.05
            flags.append("疑似空话")
            
        # 边界截断
        trust_delta = max(-0.5, min(0.5, trust_delta))
        emotion_delta = max(-0.2, min(0.5, emotion_delta))
        
        return {
            "trust_delta": trust_delta,
            "emotion_delta": emotion_delta,
            "flags": flags
        }
