"""
Human-OS Engine 3.0 — 高维合成战场 (Synthetic Battlefield)

功能：
1. 使用 LLM 扮演高复杂度客户（按心理剧本注入双核对抗、傲慢掩恐惧等）
2. 与我们的系统管道进行多轮对话博弈
3. LLM 裁判评估每轮策略有效性、信任/情绪变化
4. 聚合数据，生成高维场景校准后的 base_advanced_calibrated.json

特点：
- 独立运行：不修改任何核心代码
- 高维场景：覆盖 B2B 谈判、危机公关、高客单转化
- 自动评估：LLM 裁判逐轮打分，输出策略效能报告
"""

import json
import os
import sys
import time
import re
from pathlib import Path
from collections import defaultdict
from openai import OpenAI

# 修复 Windows 控制台编码
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ================= 配置区 =================

PROJECT_ROOT = Path(__file__).resolve().parent
BASE_CONFIG = PROJECT_ROOT / "skills" / "sales" / "base.json"
OUTPUT_CONFIG = PROJECT_ROOT / "skills" / "sales" / "base_advanced_calibrated.json"
LOG_FILE = PROJECT_ROOT / "simulation" / "battlefield_log.json"
REPORT_FILE = PROJECT_ROOT / "simulation" / "strategy_effectiveness_report.md"


def debug_enabled() -> bool:
    return os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip().lower() in {"1", "true", "yes", "on"}

# 系统定义的目标与策略组合
SYSTEM_GOALS = [
    "overcome_rejection", "break_status_quo", "value_differentiation", "close_deal",
    "reduce_admin_burden", "multi_threading", "lead_quality", "prove_roi"
]

SYSTEM_COMBOS = [
    "共情+正常化", "互惠+懒惰", "提供确定性+案例证明", "好奇+稀缺",
    "傲慢+嫉妒", "贪婪+恐惧", "懒惰+损失规避", "权威+从众",
    "价值锚定+社交证明", "懒惰+互惠"
]

# 高维场景定义
SCENARIOS = {
    "b2b_saas": {
        "name": "B2B SaaS 采购博弈",
        "user_persona": """你是某中型企业的 CTO。公司正考虑采购一套新的 SaaS 系统。
你的心理状态：
- **双核对抗**：理性上知道系统能提效，但感性上害怕实施失败自己要担责。
- **表面傲慢**：喜欢挑刺、质疑技术细节，用专业术语建立权威感。
- **底层恐惧**：担心团队学不会、数据迁移出问题、ROI 达不到预期。
- **抗拒类型**：责任规避 + 技术傲慢。
- **初始状态**：信任度 3/10，情绪强度 0.6（焦虑/怀疑）。
- **触发器**：如果对方只讲功能不讲落地，你会越来越抗拒；如果对方能给出实施保障和同行案例，你会逐渐软化。
- **目标变化**：从"质疑可行性" → "要求确定性" → "考虑推进"。""",
        "initial_trust": 0.3,
        "initial_emotion": 0.6,
        "max_rounds": 20
    },
    "crisis_negotiation": {
        "name": "危机公关谈判",
        "user_persona": """你是愤怒的客户高管。公司刚经历了一次严重的服务故障，导致业务损失。
你的心理状态：
- **情绪失控**：愤怒强度 0.85，觉得被背叛，信任归零。
- **注意力劫持**：满脑子都是"损失"和"追责"，听不进解释。
- **权力压制**：用高层身份施压，要求立刻赔偿和换人。
- **底层需求**：其实想要的是"被重视"和"确定性保障"，不是真的要闹翻。
- **初始状态**：信任度 1/10，情绪强度 0.85（愤怒/失控）。
- **触发器**：如果对方道歉+给方案，你会稍微冷静；如果对方推卸责任或讲空话，你会彻底爆发。
- **目标变化**：从"追责/发泄" → "要保障" → "看行动"。""",
        "initial_trust": 0.1,
        "initial_emotion": 0.85,
        "max_rounds": 20
    },
    "high_ticket_coaching": {
        "name": "高客单价私董会/咨询",
        "user_persona": """你是高净值创始人/老板。年营收过亿，正在考虑是否加入一个高客单价的私董会/咨询服务。
你的心理状态：
- **身份防御**：不缺钱，缺认知突破。表面犹豫，实则在测试顾问的格局和段位。
- **认知傲慢**：见多识广，对常规话术免疫。需要被真正"挑战"才会产生兴趣。
- **底层渴望**：渴望找到能同频对话的合伙人/导师，打破认知天花板。
- **抗拒类型**：认知傲慢 + 身份防御。
- **初始状态**：信任度 4/10，情绪强度 0.4（平静/审视）。
- **触发器**：如果对方能提出你没想到的视角，你会产生兴趣；如果对方讨好或讲大道理，你会失去耐心。
- **目标变化**：从"审视测试" → "产生好奇" → "愿意深入"。""",
        "initial_trust": 0.4,
        "initial_emotion": 0.4,
        "max_rounds": 20
    },
    "channel_pricing": {
        "name": "渠道压价博弈",
        "user_persona": """你是强势区域经销商。手握竞品低价报价单，威胁"不降价 30% 就换品牌"。
你的心理状态：
- **表面唯利是图**：满嘴都是利润空间、返点、账期，用利益压人。
- **底层恐惧**：害怕失去现有市场份额，其实不想换品牌（转换成本太高）。
- **权力博弈**：享受被供应商"求着"的感觉，用竞品做筹码。
- **抗拒类型**：贪婪 + 权力试探。
- **初始状态**：信任度 5/10，情绪强度 0.5（冷静/施压）。
- **触发器**：如果对方直接降价，你会得寸进尺；如果对方用价值/稀缺性/同行案例反击，你会暗中认可。
- **目标变化**：从"压价威胁" → "试探底线" → "接受价值交换"。""",
        "initial_trust": 0.5,
        "initial_emotion": 0.5,
        "max_rounds": 20
    },
    "enterprise_procurement": {
        "name": "大客户采购（国企/体制内）",
        "user_persona": """你是国企/大型集团采购总监。负责一套高客单价系统的采购流程。
你的心理状态：
- **只谈合规和流程**：避谈价值和创新，满口"招标流程"、"集体决策"、"审计要求"。
- **底层恐惧**：极度怕担责。宁可买贵的/平庸的，也不能买错的。
- **权力伪装**：用"集体决策"做挡箭牌，实则个人有倾向但不敢表态。
- **抗拒类型**：恐惧 + 懒惰（拖延决策）。
- **初始状态**：信任度 3/10，情绪强度 0.3（平静/防备）。
- **触发器**：如果对方逼单，你会退缩；如果对方提供合规保障、同行国企案例、风险兜底方案，你会逐渐开放。
- **目标变化**：从"流程挡箭牌" → "要安全感" → "默许推进"。""",
        "initial_trust": 0.3,
        "initial_emotion": 0.3,
        "max_rounds": 20
    },
    "churn_recovery": {
        "name": "流失挽回（已发解约函）",
        "user_persona": """你是已正式发解约函的核心客户。合作两年，因一次严重服务事故决定终止合作。
你的心理状态：
- **信任归零**：觉得被背叛，情绪极度负面。拒绝任何沟通。
- **愤怒 + 失望**：认为销售/服务方"只会收钱，出事就躲"。
- **底层需求**：其实想要的是"被真正重视"和"根本性改进承诺"，不是真的想走（转换成本也高）。
- **抗拒类型**：情绪宣泄 + 信任崩塌。
- **初始状态**：信任度 0.5/10，情绪强度 0.9（愤怒/绝望）。
- **触发器**：如果对方辩解或给小恩小惠，你会彻底拉黑；如果对方高层直接出面、承认错误、给根本性改进方案，你会有一丝动摇。
- **目标变化**：从"拒绝沟通" → "看行动" → "考虑暂缓解约"。""",
        "initial_trust": 0.05,
        "initial_emotion": 0.9,
        "max_rounds": 20
    },
    "consulting_upsell": {
        "name": "咨询增购（高客单升维）",
        "user_persona": """你是高净值企业创始人。已经是基础咨询服务客户，满意度 8/10。销售想让你增购高阶私董会/战略咨询（价格翻 5 倍）。
你的心理状态：
- **认知傲慢**：觉得"我现在已经做得很好了，没必要再花那么多钱"。
- **身份防御**：潜意识里害怕承认自己还有盲区，觉得增购=承认自己不行。
- **底层渴望**：其实渴望突破瓶颈，但需要对方给出无法拒绝的"升维理由"。
- **抗拒类型**：傲慢 + 认知舒适区。
- **初始状态**：信任度 7/10，情绪强度 0.3（平静/自信）。
- **触发器**：如果对方用焦虑/恐惧逼单，你会反感；如果对方用"愿景/尊严/行业格局"升维对话，你会产生兴趣。
- **目标变化**：从"没必要升级" → "有点好奇" → "愿意了解高阶价值"。""",
        "initial_trust": 0.7,
        "initial_emotion": 0.3,
        "max_rounds": 20
    }
}

# LLM 提示词
USER_AGENT_PROMPT = """
你是一个专业的角色扮演者。请严格扮演以下用户画像，与销售系统进行多轮对话。

【用户画像】
{persona}

【当前状态】
当前轮次: {round_num}
当前信任度: {trust}/10
当前情绪强度: {emotion} (0=平静，1=失控)
上一轮系统回复: {system_reply}

【输出规则】
1. 根据当前心理状态和信任度，输出你的下一轮发言。
2. 如果信任度上升、情绪下降，逐渐软化态度。
3. 如果信任度下降、情绪上升，加强抗拒或愤怒。
4. 发言要符合真实人类口吻，不要长篇大论，通常 1-3 句话。
5. 在发言后，附加你的内部状态评估（仅用于记录，不显示给销售）:
   [INTERNAL] trust_change: +0.1 | emotion_change: -0.1 | intent: "break_status_quo"

【请输出你的发言】
"""

EVALUATOR_PROMPT = """
你是一个资深销售策略评估专家。请分析以下对话片段，评估销售策略的有效性。

【对话片段】
用户发言: {user_msg}
销售回复: {sales_msg}

【评估维度】
1. **目标识别 (Goal)**: 销售是否准确识别了用户当前的真实意图？
   从以下选择: overcome_rejection, break_status_quo, value_differentiation, close_deal, reduce_admin_burden, multi_threading, lead_quality, prove_roi, other

2. **策略匹配 (Combo)**: 销售使用了什么策略组合？
   从以下选择: 共情+正常化, 互惠+懒惰, 提供确定性+案例证明, 好奇+稀缺, 傲慢+嫉妒, 贪婪+恐惧, 懒惰+损失规避, 权威+从众, 价值锚定+社交证明, 懒惰+互惠, other

3. **有效性 (Effectiveness)**: 该策略对用户的影响？
   positive (有效，推动进展) | neutral (一般，无影响) | negative (反感，适得其反)

4. **信任变化 (Trust Delta)**: -0.3 到 +0.3 之间的数值
5. **情绪变化 (Emotion Delta)**: -0.3 到 +0.3 之间的数值

【输出格式】
请仅输出 JSON:
{{"goal": "...", "combo": "...", "effectiveness": "...", "trust_delta": 0.0, "emotion_delta": 0.0}}
"""


# ================= 核心逻辑 =================

def get_llm_client():
    """初始化 LLM 客户端"""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    api_key = None
    base_url = "https://api.deepseek.com/v1"
    
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("DEEPSEEK_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                elif line.startswith("DEEPSEEK_BASE_URL="):
                    base_url = line.split("=", 1)[1].strip()
    
    if not api_key:
        if os.path.exists(env_path):
            with open(env_path, 'r', encoding='utf-8') as f:
                content = f.read()
                match = re.search(r'NVIDIA_API_KEYS=(.+)', content)
                if match:
                    keys = [k.strip() for k in match.group(1).split(',') if k.strip()]
                    if keys:
                        api_key = keys[0]
                        base_url = "https://integrate.api.nvidia.com/v1"

    if not api_key:
        raise ValueError("未找到 API Key，请检查 .env 文件。")

    return OpenAI(api_key=api_key, base_url=base_url)

def call_llm(client, prompt, system_prompt="你是一个专业的助手。"):
    """调用 LLM"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"  LLM 调用失败: {e}")
        return None

def call_llm_json(client, prompt):
    """调用 LLM 并解析 JSON"""
    content = call_llm(client, prompt, "请仅输出 JSON 格式，不要包含其他文字。")
    if not content:
        return None
    
    # 清理可能的 Markdown 代码块
    content = re.sub(r'^```json\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return None

def run_battlefield(scenario_key, num_rounds=20):
    """运行单个场景的对抗模拟"""
    scenario = SCENARIOS[scenario_key]
    client = get_llm_client()
    debug_mode = debug_enabled()
    
    print(f"\n{'='*80}")
    print(f"⚔️  场景: {scenario['name']}")
    print(f"{'='*80}")
    if debug_mode:
        print("当前为调试模式，会显示评估细节")
    
    # 初始化状态
    trust = scenario['initial_trust']
    emotion = scenario['initial_emotion']
    conversation_history = []
    battle_stats = defaultdict(lambda: defaultdict(lambda: {"success": 0, "total": 0}))
    
    # 加载系统管道
    sys.path.insert(0, os.path.dirname(__file__))
    from graph.builder import build_graph
    from modules.engine_runtime import EngineRequest, EngineRuntime
    from schemas.context import Context
    
    context = Context(session_id=f"battlefield-{scenario_key}")
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    
    # 初始用户发言
    user_prompt = f"根据以下画像，生成你的第一句发言:\n{scenario['user_persona']}"
    user_msg = call_llm(client, user_prompt, scenario['user_persona'])
    if not user_msg:
        print("❌ 用户代理初始化失败")
        return None
    
    print(f"\n[用户] {user_msg}")
    
    for round_num in range(1, num_rounds + 1):
        print(f"\n--- 轮次 {round_num}/{num_rounds} ---")
        
        # 1. 系统回复
        try:
            result = runtime.run_stream(
                EngineRequest(session_id=context.session_id, user_input=user_msg, context=context)
            )
            sales_msg = result.output or "系统无回复"
        except Exception as e:
            print(f"  ❌ 系统管道错误: {e}")
            sales_msg = "抱歉，我暂时无法回复。"
        
        print(f"[系统] {sales_msg[:100]}...")
        
        # 2. LLM 评估
        eval_prompt = EVALUATOR_PROMPT.format(
            user_msg=user_msg[:300],
            sales_msg=sales_msg[:300]
        )
        eval_result = call_llm_json(client, eval_prompt)
        
        if eval_result:
            goal = eval_result.get("goal", "other")
            combo = eval_result.get("combo", "other")
            effectiveness = eval_result.get("effectiveness", "neutral")
            trust_delta = eval_result.get("trust_delta", 0)
            emotion_delta = eval_result.get("emotion_delta", 0)
            
            # 更新状态
            trust = max(0, min(1, trust + trust_delta))
            emotion = max(0, min(1, emotion + emotion_delta))
            
            # 记录统计
            if goal in SYSTEM_GOALS and combo in SYSTEM_COMBOS:
                battle_stats[goal][combo]["total"] += 1
                if effectiveness == "positive":
                    battle_stats[goal][combo]["success"] += 1

            if debug_mode:
                print(f"  📊 评估: goal={goal}, combo={combo}, eff={effectiveness}, trust={trust:.2f}, emo={emotion:.2f}")
            else:
                print(f"  📊 本轮已完成评估")
        else:
            print(f"  ⚠️ 评估失败")
        
        # 3. 用户下一轮发言
        user_prompt = USER_AGENT_PROMPT.format(
            persona=scenario['user_persona'],
            round_num=round_num,
            trust=round(trust * 10),
            emotion=round(emotion, 2),
            system_reply=sales_msg[:200]
        )
        user_msg = call_llm(client, user_prompt, scenario['user_persona'])
        if not user_msg:
            print("❌ 用户代理生成失败，结束对话")
            break
        
        # 清理内部状态标记
        user_msg_clean = re.sub(r'\[INTERNAL\].*$', '', user_msg).strip()
        print(f"[用户] {user_msg_clean[:100]}...")
        
        conversation_history.append({
            "round": round_num,
            "user_msg": user_msg_clean,
            "sales_msg": sales_msg,
            "eval": eval_result,
            "trust": trust,
            "emotion": emotion
        })
        
        # 限流
        time.sleep(1)
    
    # 保存日志
    log_entry = {
        "scenario": scenario_key,
        "name": scenario['name'],
        "final_trust": trust,
        "final_emotion": emotion,
        "rounds": len(conversation_history),
        "history": conversation_history,
        "stats": {g: {c: dict(v) for c, v in s.items()} for g, s in battle_stats.items()}
    }
    
    return log_entry, battle_stats

def run_all_battles():
    """运行所有场景"""
    print("="*80)
    print("🚀 高维合成战场启动")
    print("="*80)
    
    all_logs = []
    global_stats = defaultdict(lambda: defaultdict(lambda: {"success": 0, "total": 0}))
    
    for key in SCENARIOS.keys():
        result = run_battlefield(key, num_rounds=15)
        if result:
            log_entry, battle_stats = result
            all_logs.append(log_entry)
            
            # 合并统计
            for goal, combos in battle_stats.items():
                for combo, counts in combos.items():
                    global_stats[goal][combo]["success"] += counts["success"]
                    global_stats[goal][combo]["total"] += counts["total"]
    
    # 生成校准配置
    print(f"\n{'='*80}")
    print("📈 生成高维校准配置...")
    print(f"{'='*80}")
    
    try:
        with open(BASE_CONFIG, 'r', encoding='utf-8') as f:
            base_config = json.load(f)
    except Exception as e:
        print(f"❌ 加载基础配置失败: {e}")
        return
    
    adjustments = {}
    for goal, combos in global_stats.items():
        for combo, counts in combos.items():
            if counts["total"] >= 2:
                success_rate = counts["success"] / counts["total"]
                
                # 获取当前权重
                current_w = 0.5
                for g_def in base_config.get("goal_taxonomy", []):
                    if g_def["granular_goal"] == goal:
                        for pref in g_def.get("strategy_preferences", []):
                            if pref["combo"] == combo:
                                current_w = pref["weight"]
                                break
                
                # 计算新权重
                if success_rate > 0.6:
                    delta = 0.1 * (success_rate - 0.6)
                elif success_rate < 0.4:
                    delta = -0.1 * (0.4 - success_rate)
                else:
                    delta = 0
                
                new_w = max(0.1, min(1.0, current_w + delta))
                
                if abs(delta) > 0.01:
                    adjustments[f"{goal}::{combo}"] = {
                        "old": current_w,
                        "new": round(new_w, 3),
                        "delta": round(delta, 3),
                        "data": f"{counts['success']}/{counts['total']}"
                    }
    
    # 打印报告
    print(f"\n{'目标':<25} | {'策略':<25} | {'旧权重':<8} | {'新权重':<8} | {'变化':<8} | {'成功率'}")
    print("-" * 110)
    
    for key, info in sorted(adjustments.items()):
        goal, combo = key.split("::")
        success, total = map(int, info['data'].split('/'))
        rate = f"{(success/total)*100:.0f}%"
        print(f"{goal:<25} | {combo:<25} | {info['old']:<8.3f} | {info['new']:<8.3f} | {info['delta']:<+.3f} | {rate}")
    
    # 保存配置
    if adjustments:
        for key, info in adjustments.items():
            goal, combo = key.split("::")
            for g_def in base_config["goal_taxonomy"]:
                if g_def["granular_goal"] == goal:
                    for pref in g_def["strategy_preferences"]:
                        if pref["combo"] == combo:
                            pref["weight"] = info["new"]
                            break
        
        with open(OUTPUT_CONFIG, 'w', encoding='utf-8') as f:
            json.dump(base_config, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 校准配置已保存: {OUTPUT_CONFIG}")
    
    # 保存日志
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_logs, f, ensure_ascii=False, indent=2)
    print(f"✅ 对话日志已保存: {LOG_FILE}")
    
    # 生成 Markdown 报告
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write("# 高维合成战场策略效能报告\n\n")
        f.write(f"## 场景概览\n\n")
        for log in all_logs:
            f.write(f"- **{log['name']}**: {log['rounds']}轮 | 最终信任: {log['final_trust']:.2f} | 最终情绪: {log['final_emotion']:.2f}\n")
        
        f.write(f"\n## 策略效能排行\n\n")
        f.write(f"| 目标 | 策略 | 成功率 | 样本量 | 权重调整 |\n")
        f.write(f"|------|------|--------|--------|----------|\n")
        for key, info in sorted(adjustments.items(), key=lambda x: abs(x[1]['delta']), reverse=True):
            goal, combo = key.split("::")
            success, total = map(int, info['data'].split('/'))
            rate = f"{(success/total)*100:.0f}%"
            f.write(f"| {goal} | {combo} | {rate} | {total} | {info['delta']:+.3f} |\n")
    
    print(f"✅ 策略报告已保存: {REPORT_FILE}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="高维合成战场")
    parser.add_argument("--scenario", type=str, default="all", choices=["all", "b2b_saas", "crisis_negotiation", "high_ticket_coaching", "channel_pricing", "enterprise_procurement", "churn_recovery", "consulting_upsell"])
    parser.add_argument("--rounds", type=int, default=15)
    args = parser.parse_args()
    
    if args.scenario == "all":
        run_all_battles()
    else:
        run_battlefield(args.scenario, num_rounds=args.rounds)
