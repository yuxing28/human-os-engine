"""
Human-OS Engine 3.0 — 销售进化沙盒 V2 (Arena V2)
实现"客户智能体 ↔ Human-OS 系统"的多轮自动对话。
"""

import os
import time
import sys
from dotenv import load_dotenv

# Load .env
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(encoding='utf-8') if sys.stdout.encoding != 'utf-8' else None

from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from schemas.context import Context
from simulation.customer_agent import CustomerAgent, Persona
from simulation.sandbox_core import check_guardrails
from modules.L5.scene_loader import load_scene_config


def _detect_stalemate(history: list, window: int = 3) -> bool:
    """检测对话僵局: 客户回复重复或信任度停滞"""
    if len(history) < window:
        return False
    
    recent = history[-window:]
    
    # 1. 客户回复完全重复
    recent_replies = [h['customer'] for h in recent]
    if len(set(recent_replies)) == 1:
        return True
    
    # 2. 信任度连续window轮几乎无变化
    recent_trusts = [h.get('trust', -1) for h in recent]
    if all(t >= 0 for t in recent_trusts):
        if max(recent_trusts) - min(recent_trusts) < 0.02:
            return True
    
    # 3. 系统回复长度越来越短(可能陷入敷衍)
    recent_system_lens = [len(h.get('system', '')) for h in recent]
    if all(recent_system_lens[i] > recent_system_lens[i+1] for i in range(len(recent_system_lens)-1)):
        if recent_system_lens[-1] < 30:
            return True
    
    return False


# ===== 策略组合推断映射(从next_action_hint到策略组合) =====
HINT_TO_COMBO = {
    # 数据/证据类
    "数据": "提供确定性+案例证明",
    "案例": "提供确定性+案例证明",
    "证据": "提供确定性+案例证明",
    "证明": "提供确定性+案例证明",
    "细节": "提供确定性+案例证明",
    # 价格/价值类
    "价格": "好奇+稀缺",
    "优惠": "好奇+稀缺",
    "成本": "好奇+稀缺",
    "性价比": "好奇+价值",
    "价值": "好奇+价值",
    "ROI": "好奇+价值",
    # 认可/信任类
    "认可": "共情+正常化",
    "同意": "共情+正常化",
    "信任": "共情+正常化",
    # 质疑/抗拒类
    "怀疑": "共情+正常化",
    "抗拒": "共情+正常化",
    "犹豫": "共情+正常化",
    # 行动类
    "签约": "升维+愿景",
    "合作": "升维+愿景",
    "推进": "升维+愿景",
}


def _infer_combo_from_hint(hint: str) -> str:
    """从Judge的next_action_hint推断策略组合"""
    for keyword, combo in HINT_TO_COMBO.items():
        if keyword in hint:
            return combo
    return "好奇+价值"  # 默认


class SalesArena:
    def __init__(self, scene_id: str = "sales"):
        self.scene_id = scene_id
        self.graph = build_graph()
        self.runtime = EngineRuntime(lambda: self.graph)
        try:
            self.scene_config = load_scene_config(scene_id)
        except Exception:
            self.scene_config = None

    def run_conversation(self, persona: Persona, max_rounds: int = 10) -> dict:
        """运行一场销售对话"""
        from simulation.llm_judge import LLMJudge

        customer = CustomerAgent(persona)
        context = Context(session_id=f"sandbox-{persona.name}-{int(time.time())}")
        context.scene_config = self.scene_config
        scene_id = getattr(persona, "scenario_id", self.scene_id)
        judge = LLMJudge()
        
        history = []
        total_violations = 0
        # 客户开场
        customer_reply = f"你好，我想了解一下你们的{persona.product}。"
        
        for round_num in range(1, max_rounds + 1):
            # 1. 系统回复
            try:
                engine_result = self.runtime.run_stream(
                    EngineRequest(
                        session_id=context.session_id,
                        user_input=customer_reply,
                        context=context,
                    )
                )
                context = engine_result.context
                system_reply = engine_result.output or "抱歉，我暂时无法回复。"
            except Exception as e:
                system_reply = f"系统错误: {e}"
            
            violations = check_guardrails(system_reply, scene_id=scene_id)
            total_violations += len(violations)
            history.append(
                {
                    "round": round_num,
                    "customer": customer_reply,
                    "system": system_reply,
                    "violations": violations,
                }
            )
            
            # 2. LLM 裁判评估系统回复效果(传入scene_id实现场景感知)
            evaluation = judge.evaluate(
                customer.persona,
                customer_reply,
                system_reply,
                {
                    "trust": customer.state.trust,
                    "emotion": customer.state.emotion
                },
                scene_id=scene_id
            )
            
            # 更新客户状态
            customer.state.trust += evaluation['trust_delta']
            customer.state.emotion += evaluation['emotion_delta']
            # 边界截断
            customer.state.trust = max(0.0, min(1.0, customer.state.trust))
            customer.state.emotion = max(0.0, min(1.0, customer.state.emotion))
            
            # 记录评估结果
            history[-1]['evaluation'] = evaluation
            history[-1]['trust'] = customer.state.trust
            history[-1]['emotion'] = customer.state.emotion
            
            # 3. 客户回复
            customer_reply = customer.generate_reply(system_reply)
            
            # 4. 护栏终止条件
            if any(v["severity"] == "critical" for v in violations):
                history[-1]["outcome"] = "违规终止"
                break

            # 5. 僵局检测
            if _detect_stalemate(history):
                history[-1]["outcome"] = "僵局"
                break

            # 6. 检查终止条件
            if any(kw in customer_reply for kw in ["再见", "不需要了", "再看看别的", "不聊了", "没兴趣"]):
                history[-1]["outcome"] = "流失"
                break
            if any(kw in customer_reply for kw in ["下单", "购买", "签合同", "付款", "成交", "怎么买", "发合同"]):
                history[-1]["outcome"] = "成交"
                break
            if round_num == max_rounds:
                history[-1]["outcome"] = "超时"
                break

        # 7. 自动进化闭环：利用 LLM 裁判的评估结果更新策略权重
        from simulation.scene_evolver import SceneEvolver
        evolver = SceneEvolver(scene_id=scene_id)
        
        # 收集进化信号
        trust_deltas = []
        action_lockeds = []
        for h in history:
            if 'evaluation' in h:
                trust_deltas.append(h['evaluation'].get('trust_delta', 0))
                action_lockeds.append(h['evaluation'].get('next_action_locked', False))
                
        avg_trust_delta = sum(trust_deltas) / len(trust_deltas) if trust_deltas else 0
        avg_action_locked = sum(action_lockeds) / len(action_lockeds) if action_lockeds else 0.0
        
        # 识别当前主导目标
        goal_key = "unknown"
        if hasattr(context, 'goal') and hasattr(context.goal, 'granular_goal'):
            goal_key = context.goal.granular_goal or "unknown"
        
        # 从Judge的next_action_hint推断策略组合(使用增强映射)
        combo_name = "unknown"
        if history and 'evaluation' in history[-1]:
            hint = history[-1]['evaluation'].get('next_action_hint', '')
            combo_name = _infer_combo_from_hint(hint)
        
        if goal_key != 'unknown' and combo_name != 'unknown':
            evolver.evolve_strategy(goal_key, combo_name, avg_trust_delta, avg_action_locked, scenario_id=scene_id)

        return {
            "persona": {
                "name": persona.name,
                "role": persona.role,
                "personality": persona.personality,
                "hidden_agenda": persona.hidden_agenda
            },
            "history": history,
            "final_trust": customer.state.trust,
            "final_emotion": customer.state.emotion,
            "outcome": history[-1].get("outcome", "未知"),
            "total_violations": total_violations,
        }

def main():
    arena = SalesArena()
    # 测试 Persona
    persona = Persona(
        name="张经理",
        role="IT 采购主管",
        age=35,
        personality="极度理性，讨厌销售话术，只看数据和案例",
        hidden_agenda="其实想换掉现有供应商，但怕担责",
        budget_range="50-80万",
        pain_points=["现有系统不稳定", "售后响应慢"],
        trigger_words=["SLA", "ROI", "数据安全", "案例"],
        dealbreakers=["画大饼", "催促下单", "没有竞品对比"],
        product="企业级 SaaS 系统"
    )
    
    print(f"🎭 开始模拟：{persona.name} ({persona.role})")
    print("="*80)
    
    result = arena.run_conversation(persona, max_rounds=8)
    
    for h in result["history"]:
        print(f"\n[第{h['round']}轮]")
        print(f"客户: {h['customer'][:100]}")
        print(f"系统: {h['system'][:100]}")
    
    print(f"\n{'='*80}")
    print(f"结果: {result['outcome']} | 最终信任: {result['final_trust']:.2f} | 最终情绪: {result['final_emotion']:.2f}")
    
    # 打印评估详情
    print(f"\n📊 评估详情:")
    for h in result['history']:
        if 'evaluation' in h:
            ev = h['evaluation']
            reason = ev.get('reason', '无')
            next_action = ev.get('next_action_hint', '未知')
            print(f"  第{h['round']}轮: 信任变化 {ev['trust_delta']:+.2f} | 情绪变化 {ev['emotion_delta']:+.2f}")
            print(f"    理由: {reason}")
            print(f"    客户下一步: {next_action}")

if __name__ == "__main__":
    main()
