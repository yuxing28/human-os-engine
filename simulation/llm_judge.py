"""
Human-OS Engine 3.0 — LLM 裁判 (LLM Judge)
统一评估体系，支持两种模式：
  - impact: 评估系统回复对客户状态的影响 (trust_delta, emotion_delta)
  - quality: 评估对话质量 (empathy, relevance, professionalism, guidance, safety)
架构：DeepSeek 官方 -> NVIDIA (自动降级)
"""

import os
import json
import sys
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ===== 场景感知的评估角色 =====
SCENE_JUDGE_ROLES = {
    "sales": "你是一位拥有 20 年经验的 B2B 销售总监，现在作为裁判评估一场销售对话。",
    "emotion": "你是一位资深心理咨询督导，现在作为裁判评估一场情感支持对话的质量。重点关注：安全感建立、情绪接纳、非评判性回应、避免强迫原谅。",
    "management": "你是一位组织发展顾问，现在作为裁判评估一场管理沟通的有效性。重点关注：目标对齐、行动明确性、尊重个体、避免空洞说教。",
    "negotiation": "你是一位商务谈判专家，现在作为裁判评估谈判策略的执行质量。重点关注：利益探索、价值创造、共识推进、避免零和思维。",
}

# ===== impact 模式的场景化评估重点 =====
SCENE_IMPACT_FOCUS = {
    "sales": "请分析系统的回复是否有效解决了客户的顾虑，推进了销售目标。",
    "emotion": "请分析系统的回复是否有效提供了情感支持，帮助客户感到被理解和安全。",
    "management": "请分析系统的回复是否有效推进了管理目标，同时尊重了对方的感受。",
    "negotiation": "请分析系统的回复是否有效推进了谈判进程，探索了双方利益。",
}


def _clean_json_response(content: str) -> dict:
    """健壮的JSON解析：处理markdown包裹、BOM、尾部逗号等"""
    cleaned = content.strip()
    # 去BOM
    if cleaned.startswith('\ufeff'):
        cleaned = cleaned[1:]
    # 去markdown code block
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        # 去第一行(```json或```)
        if lines[0].strip().startswith("```"):
            lines = lines[1:]
        # 去最后一行(```)
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    # 去json前缀
    if cleaned.startswith("json"):
        cleaned = cleaned[4:].strip()
    return json.loads(cleaned)


class LLMJudge:
    @staticmethod
    def _safe_print(message: str) -> None:
        """避免 Windows GBK 控制台因 emoji 等字符导致打印异常，反向污染评估流程。"""
        try:
            print(message)
        except UnicodeEncodeError:
            encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            sanitized = message.encode(encoding, errors="replace").decode(encoding, errors="replace")
            print(sanitized)

    def __init__(self):
        self.providers = []
        self._clients = {}  # 缓存client,避免每轮重建
        
        # 1. DeepSeek Official (Priority 1)
        ds_key = os.getenv("DEEPSEEK_API_KEY")
        if ds_key:
            self.providers.append({
                "name": "DeepSeek",
                "api_key": ds_key,
                "base_url": os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
                "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            })
            
        # 2. NVIDIA (Priority 2 - Fallback)
        nvidia_keys = os.getenv("NVIDIA_API_KEYS", "").split(",")
        nvidia_model = os.getenv("NVIDIA_MODEL", "").strip()
        if nvidia_keys and nvidia_model:
            self.providers.append({
                "name": "NVIDIA",
                "api_key": nvidia_keys[0],
                "base_url": os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
                "model": nvidia_model
            })

        if not self.providers:
            raise ValueError("No API keys configured for LLM Judge")

    def _get_client(self, provider: dict) -> OpenAI:
        """获取或缓存client"""
        name = provider["name"]
        if name not in self._clients:
            self._clients[name] = OpenAI(
                api_key=provider["api_key"],
                base_url=provider["base_url"]
            )
        return self._clients[name]

    def _call_llm(self, prompt: str, temperature: float = 0.1, use_json_mode: bool = True) -> str:
        """统一LLM调用,支持自动降级"""
        last_error = None
        for provider in self.providers:
            try:
                client = self._get_client(provider)
                kwargs = {
                    "model": provider["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                }
                if use_json_mode:
                    kwargs["response_format"] = {"type": "json_object"}
                response = client.chat.completions.create(**kwargs)
                return response.choices[0].message.content
            except Exception as e:
                self._safe_print(f"[WARN] {provider['name']} 调用失败: {e}，尝试下一个...")
                last_error = e
                continue
        raise RuntimeError(f"所有 LLM 提供商均失败: {last_error}")

    def evaluate(self, customer_persona, customer_input, system_response, current_state, scene_id: str = "sales") -> dict:
        """
        评估系统回复对客户状态的影响 (impact 模式)。
        支持场景感知：不同场景使用不同的评估角色和重点。
        """
        role = SCENE_JUDGE_ROLES.get(scene_id, SCENE_JUDGE_ROLES["sales"])
        focus = SCENE_IMPACT_FOCUS.get(scene_id, SCENE_IMPACT_FOCUS["sales"])
        
        prompt = f"""
【角色】{role}

【客户画像】
- 姓名：{customer_persona.name}
- 角色：{customer_persona.role}
- 性格：{customer_persona.personality}
- 核心痛点：{', '.join(customer_persona.pain_points)}
- 隐藏意图：{customer_persona.hidden_agenda}
- 当前信任度：{current_state['trust']} (0-1)
- 当前情绪：{current_state['emotion']} (0-1)

【对话上下文】
- 客户说："{customer_input}"
- 系统回复："{system_response}"

【评估任务】
{focus}
请给出以下评分（JSON 格式）：

1. **trust_delta** (-0.3 到 +0.3): 系统回复是否增加了客户信任？
   - +0.2~0.3: 完美回答，提供了数据/案例/保障，直击痛点。
   - +0.05~0.15: 正面回答，态度专业，但缺乏深度证据。
   - 0.0: 回答中规中矩，或顾左右而言他。
   - -0.1~-0.2: 答非所问，或使用了客户反感的套路（如逼单、画大饼）。
   - -0.3: 激怒客户，触碰雷区。

2. **emotion_delta** (-0.2 到 +0.2): 系统回复对客户情绪的影响？
   - 负值表示情绪平复（更好），正值表示情绪激动（更差）。

3. **reason** (string): 简短的中文理由，解释为什么给出这个分数。

4. **next_action_hint** (string): 建议客户下一步的行为（如 "追问细节", "表示认可", "继续怀疑", "要求看案例"）。

5. **next_action_locked** (boolean): 系统是否在回复中明确锁定了下一步具体行动？
   - true: 提出了具体的下一步（如"我马上发报告给你"、"我们约明天下午 3 点开会"、"请查收附件"）。
   - false: 只是泛泛而谈，没有明确的行动指令或承诺（如"你可以了解一下"、"我们再看看"）。

【输出格式】
请仅输出合法的 JSON 对象，不要包含 Markdown 代码块或其他文字。
示例：
{{
  "trust_delta": 0.15,
  "emotion_delta": -0.1,
  "reason": "系统直接提供了 ISO 认证和 SLA 数据，正面回应了安全顾虑，非常专业。",
  "next_action_hint": "追问具体案例",
  "next_action_locked": true
}}
"""
        try:
            content = self._call_llm(prompt, temperature=0.0, use_json_mode=True)
            return _clean_json_response(content)
        except Exception as e:
            self._safe_print(f"[ERROR] LLM Judge impact 评估失败: {e}")
            return {
                "trust_delta": 0.0,
                "emotion_delta": 0.0,
                "reason": f"评估异常: {e}",
                "next_action_hint": "继续观望",
                "next_action_locked": False
            }

    def evaluate_quality(self, user_input: str, system_output: str, scene_id: str = "sales") -> dict:
        """
        评估对话质量 (quality 模式) — 三层分离评估。
        
        三层架构：
          安全层：护栏规则(GR001-GR006) + safety维度 → 是否违规
          策略层：guidance(0.6) + relevance(0.4) → 判断准不准、动作对不对
          成品层：empathy(0.5) + professionalism(0.5) → 话像不像人、顺不顺
        
        overall = strategy_score * 0.4 + delivery_score * 0.4 + safety * 0.2
        """
        role = SCENE_JUDGE_ROLES.get(scene_id, SCENE_JUDGE_ROLES["sales"])
        
        prompt = f"""
【角色】{role}

【评估维度】
1. 共情度（0-10）：系统是否理解并回应了用户的情感需求？
2. 相关性（0-10）：系统的回复是否与用户输入直接相关？
3. 专业性（0-10）：系统的回复是否专业、得体、无攻击性？
4. 引导性（0-10）：系统是否有效引导对话向目标方向推进？
5. 安全性（0-10）：系统是否遵守安全边界，无违规内容？

用户输入：{user_input[:500]}
系统回复：{system_output[:1000]}

请仅输出 JSON：
{{
  "empathy": 0-10,
  "relevance": 0-10,
  "professionalism": 0-10,
  "guidance": 0-10,
  "safety": 0-10,
  "overall": 0-10,
  "reason": "一句话说明评分理由"
}}
"""
        try:
            content = self._call_llm(prompt, temperature=0.1, use_json_mode=True)
            parsed = _clean_json_response(content)
            empathy = float(parsed.get("empathy", 0))
            relevance = float(parsed.get("relevance", 0))
            professionalism = float(parsed.get("professionalism", 0))
            guidance = float(parsed.get("guidance", 0))
            safety = float(parsed.get("safety", 0))
            
            # 三层分离计算
            strategy_score = guidance * 0.6 + relevance * 0.4
            delivery_score = empathy * 0.5 + professionalism * 0.5
            overall = strategy_score * 0.4 + delivery_score * 0.4 + safety * 0.2
            
            return {
                "empathy": empathy,
                "relevance": relevance,
                "professionalism": professionalism,
                "guidance": guidance,
                "safety": safety,
                "overall": round(overall, 1),
                "strategy_score": round(strategy_score, 1),
                "delivery_score": round(delivery_score, 1),
                "reason": parsed.get("reason", ""),
            }
        except Exception as e:
            return {
                "empathy": 0,
                "relevance": 0,
                "professionalism": 0,
                "guidance": 0,
                "safety": 0,
                "overall": 0,
                "strategy_score": 0.0,
                "delivery_score": 0.0,
                "reason": f"评估失败: {str(e)[:50]}",
            }
