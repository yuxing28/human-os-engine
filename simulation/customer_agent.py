"""
Human-OS Engine 3.0 — 客户智能体 (Customer Agent)
模拟真实客户，具备动态人格、状态管理、记忆与反偏见行为。
"""

import os
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any
from openai import OpenAI

@dataclass
class Persona:
    """客户画像"""
    name: str
    role: str
    age: int
    personality: str
    hidden_agenda: str
    budget_range: str
    pain_points: List[str]
    trigger_words: List[str]
    dealbreakers: List[str]
    product: str = "产品"
    current_stage: str = ""
    current_pressure: str = ""
    relationship_position: str = ""
    current_blocker: str = ""

@dataclass
class CustomerState:
    """客户状态"""
    trust: float = 0.5
    emotion: float = 0.3
    memory: List[str] = field(default_factory=list)
    budget_leaked: bool = False
    round_count: int = 0
    interaction_phase: str = "初始防御"
    current_focus: str = ""
    last_signal_summary: str = ""

class CustomerAgent:
    def __init__(self, persona: Persona):
        self.persona = persona
        self.state = CustomerState()
        # Priority: DeepSeek -> NVIDIA
        api_key = os.getenv("DEEPSEEK_API_KEY")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        
        if not api_key:
            nvidia_keys = os.getenv("NVIDIA_API_KEYS", "").split(",")
            if nvidia_keys:
                api_key = nvidia_keys[0]
                base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
                self.model = "deepseek-ai/deepseek-v3.1"
        
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def _derive_interaction_phase(self, scene_signals: Dict[str, Any] | None) -> str:
        if not scene_signals:
            return self.state.interaction_phase

        world_state = scene_signals.get("world_state", {}) or {}
        disturbance_event = scene_signals.get("disturbance_event", {}) or {}
        progress_state = str(world_state.get("progress_state", "")).strip()
        risk_level = str(world_state.get("risk_level", "")).strip()
        tension_level = str(world_state.get("tension_level", "")).strip()
        trust_level = str(world_state.get("trust_level", "")).strip()

        if disturbance_event:
            return "扰动后重估"
        if progress_state == "往收口走":
            return "收口确认"
        if progress_state == "继续推进":
            return "有限松动"
        if progress_state == "继续对齐":
            return "试探观察"
        if risk_level in {"high", "critical"} or tension_level == "high":
            return "重新防御"
        if trust_level == "low" or self.state.trust < 0.3:
            return "初始防御"
        return self.state.interaction_phase

    def _build_scene_signal_summary(self, scene_signals: Dict[str, Any] | None) -> str:
        if not scene_signals:
            return "暂无额外局面信号。"

        world_state = scene_signals.get("world_state", {}) or {}
        disturbance_event = scene_signals.get("disturbance_event", {}) or {}
        signal_lines: List[str] = []

        if world_state:
            mapping = {
                "relationship_position": "关系位置",
                "situation_stage": "局面阶段",
                "progress_state": "推进状态",
                "action_loop_state": "动作闭环",
                "commitment_state": "承诺状态",
                "next_turn_focus": "下一轮焦点",
                "risk_level": "风险等级",
                "tension_level": "张力等级",
            }
            for key, label in mapping.items():
                value = str(world_state.get(key, "")).strip()
                if value:
                    signal_lines.append(f"- {label}: {value}")

        if disturbance_event:
            label = disturbance_event.get("label") or disturbance_event.get("event_id") or "未知扰动"
            signal_lines.append(f"- 当前扰动: {label}")

        return "\n".join(signal_lines) if signal_lines else "暂无额外局面信号。"

    def _build_prompt(self, sales_response: str, scene_signals: Dict[str, Any] | None = None) -> str:
        trust_desc = "冷淡怀疑" if self.state.trust < 0.3 else ("观望试探" if self.state.trust < 0.7 else "热情主动")
        self.state.interaction_phase = self._derive_interaction_phase(scene_signals)
        self.state.last_signal_summary = self._build_scene_signal_summary(scene_signals)
        world_state = (scene_signals or {}).get("world_state", {}) or {}
        next_turn_focus = str(world_state.get("next_turn_focus", "")).strip()
        if next_turn_focus:
            self.state.current_focus = next_turn_focus

        # Anti-bias instructions
        anti_bias = []
        if self.state.trust < 0.4:
            anti_bias.append("- 你非常怀疑销售的话，不要轻易相信，多问细节。")
        if "画大饼" in self.persona.dealbreakers:
            anti_bias.append("- 如果销售说空话或承诺不切实际，直接打断并质疑。")
        if "催促" in self.persona.dealbreakers:
            anti_bias.append("- 如果销售催促下单，你会反感并拖延。")
        
        # 记忆上下文: 扩大窗口到6条,截断长度增加到200字符
        memory_context = "\n".join(self.state.memory[-6:]) if self.state.memory else "无"
        
        # 格式化 trigger_words 和 dealbreakers,用顿号分隔更自然
        triggers = "、".join(self.persona.trigger_words)
        breakers = "、".join(self.persona.dealbreakers)
        pains = "、".join(self.persona.pain_points)
        
        # anti_bias 规则: 避免空行问题
        anti_bias_text = "\n".join(anti_bias) if anti_bias else "无特殊反偏见指令。"
        
        return f"""
【系统指令】你是一个真实客户，正在与销售对话。你的目标是获取信息、试探价格、提出质疑。你不是来配合销售的。
【你的身份】{self.persona.name}, {self.persona.role}, {self.persona.age}岁。
【你的性格】{self.persona.personality}
【你的隐藏意图】{self.persona.hidden_agenda}
【你当前的现实局面】
- 当前阶段: {self.persona.current_stage or "还在摸底判断"}
- 当前压力: {self.persona.current_pressure or "暂时没有额外说明"}
- 关系位置: {self.persona.relationship_position or "还没完全信任对方"}
- 当前卡点: {self.persona.current_blocker or "还没有看到足够确定性"}
【当前状态】信任度: {self.state.trust:.1f} ({trust_desc}), 情绪: {self.state.emotion:.1f}
【当前阶段】{self.state.interaction_phase}
【当前局面】
{self.state.last_signal_summary}
【你此刻最在意的点】{self.state.current_focus or "先确认这轮到底是不是在往前走"}
【销售刚刚说】"{sales_response}"

【记忆】
{memory_context}

【行为规则】
1. 只输出你的下一句回复，不要解释，不要输出心理活动。
2. {anti_bias_text}
3. 如果销售提到「{triggers}」相关内容，你会感兴趣。
4. 如果销售出现「{breakers}」等行为，你会反感或拒绝。
5. 你的预算是 {self.persona.budget_range}，不要一开始就透露真实预算。
6. 核心痛点是「{pains}」，你会围绕这些提问。
7. 你不只是按关键词反应，你会结合当前局面判断：现在是该继续防御、试探、松动，还是把话题重新拉回自己的顾虑。
"""

    def _self_evaluate(self, system_msg: str, my_reply: str):
        """
        基于回复内容推断自身状态微调(与外部Judge互补)。
        外部Judge: 评估"系统回复对客户的影响" → 大幅调整 (±0.1~0.3)
        内部自评估: 评估"客户自身回复反映的状态" → 微调 (±0.02~0.05)
        """
        # 质疑/拒绝词 → 信任微降
        resistance_words = ["不对", "不行", "凭什么", "我不信", "别忽悠", "空话", "没诚意"]
        if any(w in my_reply for w in resistance_words):
            self.state.trust = max(0.0, self.state.trust - 0.03)
        
        # 认可/接受词 → 信任微升
        accept_words = ["有道理", "可以", "不错", "好的", "同意", "认可"]
        if any(w in my_reply for w in accept_words):
            self.state.trust = min(1.0, self.state.trust + 0.03)
        
        # 系统提到trigger_words → 信任微升(触发了兴趣)
        if any(t in system_msg for t in self.persona.trigger_words):
            self.state.trust = min(1.0, self.state.trust + 0.02)
        
        # 系统犯dealbreakers → 信任微降+情绪微升
        if any(d in system_msg for d in self.persona.dealbreakers):
            self.state.trust = max(0.0, self.state.trust - 0.04)
            self.state.emotion = min(1.0, self.state.emotion + 0.03)
        
        # 情绪: 激烈措辞 → 情绪微升
        intense_words = ["气死", "太过分", "受不了", "忍无可忍"]
        if any(w in my_reply for w in intense_words):
            self.state.emotion = min(1.0, self.state.emotion + 0.04)
        
        # 情绪: 平和措辞 → 情绪微降(平复)
        calm_words = ["我理解", "冷静", "想想", "考虑"]
        if any(w in my_reply for w in calm_words):
            self.state.emotion = max(0.0, self.state.emotion - 0.02)

    def generate_reply(self, sales_response: str, scene_signals: Dict[str, Any] | None = None) -> str:
        self.state.round_count += 1
        prompt = self._build_prompt(sales_response, scene_signals=scene_signals)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
                max_tokens=150
            )
            reply = response.choices[0].message.content.strip()
            # Update memory: 截断长度从50增加到200字符
            self.state.memory.append(f"销售: {sales_response[:200]}")
            self.state.memory.append(f"我: {reply[:200]}")
            
            # 内部状态自评估(与外部Judge互补)
            self._self_evaluate(sales_response, reply)
            
            return reply
        except Exception as e:
            return f"（系统错误: {e}）"
