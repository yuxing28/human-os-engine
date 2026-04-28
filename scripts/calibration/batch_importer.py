"""
Human-OS Engine 3.0 — 独立数据导入与校准脚本 (System-Native)

功能：
1. 读取翻译后的真实销售对话数据。
2. 调用系统 LLM 接口，对每一轮对话进行深度意图识别和策略归类。
3. 根据用户反馈计算策略成功率。
4. 生成校准后的 base_calibrated.json。

特点：
- 独立运行：不依赖主系统核心代码（graph/modules），仅复用 LLM 接口。
- 零侵入：不修改任何现有代码，只生成新配置文件。
- 高精度：使用 LLM 进行语义分析，而非简单的关键词匹配。
"""

import json
import os
import sys
import re
import time
from pathlib import Path
from collections import defaultdict
from openai import OpenAI

# 修复 Windows 控制台编码
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ================= 配置区 =================

PROJECT_ROOT = Path(__file__).resolve().parent
INPUT_FILE = PROJECT_ROOT / "deepseek_json_20260403_69ed2f.json"
BASE_CONFIG = PROJECT_ROOT / "skills" / "sales" / "base.json"
OUTPUT_FILE = PROJECT_ROOT / "skills" / "sales" / "base_calibrated.json"

# 系统定义的目标与策略组合 (必须与 base.json 一致)
SYSTEM_GOALS = [
    "overcome_rejection", "break_status_quo", "value_differentiation", "close_deal",
    "reduce_admin_burden", "multi_threading", "lead_quality", "prove_roi"
]

SYSTEM_COMBOS = [
    "共情+正常化", "互惠+懒惰", "提供确定性+案例证明", "好奇+稀缺",
    "傲慢+嫉妒", "贪婪+恐惧", "懒惰+损失规避", "权威+从众",
    "价值锚定+社交证明", "懒惰+互惠"
]

# LLM 系统提示词
ANALYSIS_PROMPT = """
你是一个资深销售数据分析师。请分析以下销售对话片段，并将其映射到指定的系统目标（Granular Goal）和策略组合（Strategy Combo）。

【对话片段】
用户上一句: {user_msg}
销售回复: {sales_msg}
用户反馈: {feedback} (positive=有效，neutral=无效/一般，negative=反感)

【映射规则】
1. **目标 (Goal)**: 从以下列表中选择最匹配的一个:
   - overcome_rejection: 用户表示拒绝、没兴趣、忙、不想听。
   - break_status_quo: 用户表示犹豫、再想想、担心风险、维持现状。
   - value_differentiation: 用户嫌贵、比价、质疑价值、问区别。
   - close_deal: 用户询问售后、保修、功能细节、表现出购买意向。
   - (若无明显匹配，选 "other")

2. **策略 (Combo)**: 从以下列表中选择销售最可能使用的一个:
   - 共情+正常化: 认同用户感受，表示"这很正常"。
   - 互惠+懒惰: 给甜头，降低门槛，让用户觉得容易。
   - 提供确定性+案例证明: 给承诺、讲案例、消除顾虑。
   - 好奇+稀缺: 提问引发好奇，强调限时/限量。
   - 傲慢+嫉妒: 身份认同，对标比较。
   - 贪婪+恐惧: 强调利益最大化或害怕损失。
   - 懒惰+损失规避: 简化步骤，强调不做的损失。
   - 权威+从众: 引用权威，大家都这么做。
   - 价值锚定+社交证明: 锚定高价值，展示社会认同。
   - 懒惰+互惠: (同上)
   - (若都不匹配，选 "other")

【输出格式】
请仅输出 JSON 格式，不要包含其他文字:
{{"goal": "目标名称", "combo": "策略名称", "effectiveness": "positive"}}
"""

# ================= 核心逻辑 =================

def get_llm_client():
    """初始化 LLM 客户端 (读取 .env)"""
    # 尝试从 .env 读取 Key
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    api_key = None
    base_url = "https://api.deepseek.com/v1" # 默认使用 DeepSeek 官方
    
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.startswith("DEEPSEEK_API_KEY="):
                    api_key = line.split("=", 1)[1].strip()
                elif line.startswith("DEEPSEEK_BASE_URL="):
                    base_url = line.split("=", 1)[1].strip()
    
    if not api_key:
        # 尝试读取 NVIDIA Key 作为备选
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

def load_json_objects(filepath):
    """读取包含多个 JSON 对象的文件"""
    objects = []
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        decoder = json.JSONDecoder()
        idx = 0
        while idx < len(content):
            match = re.compile(r'\{').search(content, idx)
            if not match:
                break
            start = match.start()
            try:
                obj, end_idx = decoder.raw_decode(content, start)
                objects.append(obj)
                idx = end_idx
            except json.JSONDecodeError:
                idx = start + 1
    return objects

def analyze_turn(client, user_msg, sales_msg, feedback):
    """调用 LLM 分析单轮对话"""
    if not user_msg or not sales_msg:
        return None
    
    prompt = ANALYSIS_PROMPT.format(
        user_msg=user_msg[:200], # 截断防止超长
        sales_msg=sales_msg[:300],
        feedback=feedback
    )
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat", # 或 "meta/llama-3.1-70b-instruct" 如果用 NVIDIA
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"  ⚠️ LLM 调用失败: {e}")
        return None

def run_batch_import():
    print("="*80)
    print("🚀 开始系统原生数据导入与校准")
    print("="*80)

    # 1. 初始化 LLM
    print("\n🔌 正在连接 LLM 接口...")
    try:
        client = get_llm_client()
        print("✅ LLM 连接成功")
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return

    # 2. 加载数据
    print(f"\n📂 加载数据文件：{INPUT_FILE}")
    dialogues = load_json_objects(INPUT_FILE)
    print(f"✅ 成功加载 {len(dialogues)} 个对话")

    # 3. 加载基础配置
    print(f"\n⚙️ 加载基础配置：{BASE_CONFIG}")
    try:
        with open(BASE_CONFIG, 'r', encoding='utf-8') as f:
            base_config = json.load(f)
    except Exception as e:
        print(f"❌ 加载配置失败：{e}")
        return

    # 4. 逐轮分析
    print("\n🧠 正在调用 LLM 进行深度分析 (这可能需要几分钟)...")
    
    # 统计结构：{ goal: { combo: { success: 0, total: 0 } } }
    stats = defaultdict(lambda: defaultdict(lambda: {"success": 0, "total": 0}))
    
    processed_count = 0
    total_turns = 0

    for d_idx, dialogue in enumerate(dialogues):
        utterances = dialogue.get("utterances", [])
        print(f"\n📝 分析对话 {d_idx + 1}/{len(dialogues)}...")
        
        for i, turn in enumerate(utterances):
            if turn.get("speaker") != "sales":
                continue
            
            sales_msg = turn.get("message", "")
            
            # 获取用户上一句话
            user_msg = ""
            for j in range(i-1, -1, -1):
                if utterances[j].get("speaker") == "user":
                    user_msg = utterances[j].get("message", "")
                    break
            
            # 获取反馈
            feedback = "neutral"
            for ev in turn.get("user_utterance_evals", []):
                if ev.get("label") == "GOAL_ACCEPTANCE":
                    raw_ans = ev.get("answer", "")
                    if "positive" in str(raw_ans).lower():
                        feedback = "positive"
                    elif "negative" in str(raw_ans).lower():
                        feedback = "negative"
                    break
            
            if not user_msg:
                continue

            total_turns += 1
            
            # 调用 LLM (限流控制)
            if processed_count % 5 == 0 and processed_count > 0:
                time.sleep(1) # 简单限流

            result = analyze_turn(client, user_msg, sales_msg, feedback)
            
            if result and result.get("goal") in SYSTEM_GOALS and result.get("combo") in SYSTEM_COMBOS:
                goal = result["goal"]
                combo = result["combo"]
                
                stats[goal][combo]["total"] += 1
                if feedback == "positive":
                    stats[goal][combo]["success"] += 1
                
                processed_count += 1
                print(f"  ✅ 轮次 {i}: {goal} | {combo} | {feedback}")

    print(f"\n📊 分析完成！共处理 {processed_count} 个有效回合 (总 {total_turns} 轮)")

    # 5. 计算新权重
    print("\n📈 计算校准权重...")
    
    adjustments = {}
    for goal in SYSTEM_GOALS:
        for combo, counts in stats[goal].items():
            if counts["total"] >= 2: # 至少 2 个样本才调整
                success_rate = counts["success"] / counts["total"]
                
                # 获取当前权重
                current_w = 0.5
                for g_def in base_config.get("goal_taxonomy", []):
                    if g_def["granular_goal"] == goal:
                        for pref in g_def.get("strategy_preferences", []):
                            if pref["combo"] == combo:
                                current_w = pref["weight"]
                                break
                
                # 计算新权重 (基于成功率)
                # 逻辑：成功率 > 60% 则加分，< 40% 则减分
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

    # 6. 生成报告
    print("\n" + "="*90)
    print("📝 校准报告 (基于真实数据)")
    print("="*90)
    print(f"{'目标 (Goal)':<25} | {'策略 (Combo)':<25} | {'旧权重':<8} | {'新权重':<8} | {'变化':<8} | {'成功率'}")
    print("-" * 110)
    
    for key, info in sorted(adjustments.items()):
        goal, combo = key.split("::")
        success, total = map(int, info['data'].split('/'))
        rate = f"{(success/total)*100:.0f}%"
        print(f"{goal:<25} | {combo:<25} | {info['old']:<8.3f} | {info['new']:<8.3f} | {info['delta']:<+.3f} | {rate}")

    print("\n" + "="*90)
    print("🛡️ 隔离保护：以下目标因无数据支持，保持原权重不变")
    print("="*90)
    protected = [g for g in SYSTEM_GOALS if g not in [k.split("::")[0] for k in adjustments.keys()]]
    for g in protected:
        print(f"  - {g}")

    # 7. 保存配置
    if adjustments:
        print(f"\n💾 正在保存校准后的配置到：{OUTPUT_FILE}")
        for key, info in adjustments.items():
            goal, combo = key.split("::")
            for g_def in base_config["goal_taxonomy"]:
                if g_def["granular_goal"] == goal:
                    for pref in g_def["strategy_preferences"]:
                        if pref["combo"] == combo:
                            pref["weight"] = info["new"]
                            break
        
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(base_config, f, ensure_ascii=False, indent=2)
        print("✅ 完成！请检查 base_calibrated.json。")
    else:
        print("\n⚠️ 未检测到显著权重变化，无需生成新文件。")

if __name__ == "__main__":
    run_batch_import()
