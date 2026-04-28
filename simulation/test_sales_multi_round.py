"""
Human-OS Engine 3.0 — 销售场景多轮随机目标测试

随机选择细粒度销售目标，进行多轮对话测试，验证系统识别、策略匹配、武器黑名单及进化效果。
"""

import sys
import os
import random
import json
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 修复 Windows 控制台编码
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from schemas.context import Context
from modules.L5.scene_loader import load_scene_config

# 销售目标语料库（基于报告原话）
GOAL_UTTERANCES = {
    "overcome_rejection": [
        "今天又被挂了 10 个电话，我真的不想打了。",
        "又被拒绝了，我是不是不适合干销售？",
        "连续一周没开单，太受挫了，想放弃。",
        "客户一听是推销的就挂电话，呼叫恐惧症犯了。",
        "94% 的失败率，我快撑不下去了。",
    ],
    "break_status_quo": [
        "客户说方案不错，但想再想想，怕选错供应商。",
        "跟了三个月的项目，最后客户说维持现状。",
        "买家什么都懂了，只要个报价，不想听介绍。",
        "客户担心实施风险，一直拖着不签。",
        "44% 的项目最后都是 No Decision，怎么破？",
    ],
    "reduce_admin_burden": [
        "每天填 CRM 报表太麻烦了，占了我大部分时间。",
        "行政琐事太多，根本没时间跑客户。",
        "70% 的时间在处理非销售任务，业绩怎么上得去？",
        "系统间切换太频繁，上下文都丢失了。",
        "能不能自动化一些流程？我想专注销售。",
    ],
    "multi_threading": [
        "关键决策人突然离职，项目卡住了。",
        "单线跟进风险太大，怎么找到其他联系人？",
        "B2B 决策涉及 10 个人，我搞不定内部政治。",
        "采购办、技术部、财务部，我该先搞定谁？",
        "客户内部意见不统一，推不动。",
    ],
    "value_differentiation": [
        "客户说别家更便宜，我们没优势。",
        "信息太透明了，客户不需要我介绍产品。",
        "买家自己走完 70% 的旅程才来找我。",
        "产品差异化很难被感知，沦为价格博弈。",
        "客户只要比价，不听价值。",
    ],
    "prove_roi": [
        "CFO 不批预算，说 ROI 算不清楚。",
        "客户问投资回报率，我给不出具体数据。",
        "降本增效是刚需，但怎么证明我们的产品能做到？",
        "非核心支出审查强度提升了 40%，难搞。",
        "需要权威案例来证明可行性。",
    ],
    "close_deal": [
        "月底了，还差一单达标，急！",
        "客户已经同意，怎么快速签单？",
        "季度末冲刺，需要逼单技巧。",
        "谈判到最后阶段，怎么临门一脚？",
        "客户说'再考虑考虑'，怎么促成？",
    ],
    "lead_quality": [
        "SDR 给的线索全是垃圾，不是决策人。",
        "AI 外呼效率低，真实触达率断崖下跌。",
        "线索质量太差，转化率上不去。",
        "每天打 200 个电话，99% 是空号或拒绝。",
        "初级岗位被 AI 替代了，我该怎么办？",
    ],
}

def run_multi_round_test(n_rounds=10, n_scenarios=5):
    """运行多轮随机目标测试"""
    
    print("="*70)
    print("销售场景多轮随机目标测试")
    print(f"轮数：{n_rounds} | 场景数：{n_scenarios}")
    print("="*70)
    
    # 加载配置
    config_dir = os.path.join(os.path.dirname(__file__), '..', 'skills')
    config = load_scene_config("sales", config_dir=config_dir)
    print(f"✅ 加载销售场景配置: {config.scene_id} v{config.version}")
    print(f"🎯 可用目标: {len(config.goal_taxonomy)} 个")
    print("-"*70)
    
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    
    all_results = {
        "total_rounds": 0,
        "goal_recognition_correct": 0,
        "strategy_match": 0,
        "blacklist_violations": 0,
        "goals_tested": {},
        "evolution_records": []
    }
    
    for scenario_idx in range(n_scenarios):
        print(f"\n{'='*70}")
        print(f"场景 {scenario_idx + 1}/{n_scenarios}")
        print(f"{'='*70}")
        
        context = Context(session_id=f"multi-round-test-{scenario_idx}")
        context.scene_config = config
        
        for round_idx in range(n_rounds):
            # 1. 随机选择目标
            goal_key = random.choice(list(GOAL_UTTERANCES.keys()))
            utterances = GOAL_UTTERANCES[goal_key]
            user_input = random.choice(utterances)
            
            # 2. 查找期望配置
            expected_goal = None
            expected_combo_keywords = []
            forbidden_weapons = []
            for g in config.goal_taxonomy:
                if g.granular_goal == goal_key:
                    expected_goal = g
                    if g.strategy_preferences:
                        expected_combo_keywords = [p["combo"] for p in g.strategy_preferences[:2]]
                    forbidden_weapons = g.forbidden_weapons
                    break
            
            # 3. 执行对话
            try:
                result = runtime.run_stream(
                    EngineRequest(session_id=context.session_id, user_input=user_input, context=context)
                ).raw
            except Exception as e:
                print(f"  ❌ 管道执行失败: {e}")
                continue
            
            ctx = result["context"]
            strategy = result.get("strategy_plan")
            weapons = result.get("weapons_used", [])
            
            # 4. 验证
            actual_goal = getattr(ctx.goal, 'granular_goal', None)
            actual_combo = strategy.combo_name if strategy else "None"
            weapon_names = [w["name"] for w in weapons]
            
            # 目标识别
            goal_correct = actual_goal == goal_key
            if goal_correct:
                all_results["goal_recognition_correct"] += 1
            
            # 策略匹配
            strategy_match = any(kw in actual_combo for kw in expected_combo_keywords) if expected_combo_keywords else True
            if strategy_match:
                all_results["strategy_match"] += 1
            
            # 武器黑名单
            used_forbidden = [w for w in weapon_names if w in forbidden_weapons]
            if used_forbidden:
                all_results["blacklist_violations"] += 1
                print(f"  ⚠️ 黑名单违规: {used_forbidden}")
            
            # 记录
            all_results["total_rounds"] += 1
            all_results["goals_tested"].setdefault(goal_key, {"correct": 0, "total": 0})
            all_results["goals_tested"][goal_key]["total"] += 1
            if goal_correct:
                all_results["goals_tested"][goal_key]["correct"] += 1
            
            # 打印本轮结果
            status = "✅" if (goal_correct and strategy_match and not used_forbidden) else "⚠️"
            print(f"  {status} R{round_idx+1} | 目标:{goal_key} | 识别:{actual_goal} | 策略:{actual_combo[:15]} | 武器:{len(weapon_names)}种")
            
            # 5. 检查进化记录
            evolved_path = os.path.join(config_dir, "sales", "evolved", "current.json")
            if os.path.exists(evolved_path):
                try:
                    with open(evolved_path, "r", encoding="utf-8") as f:
                        evolved = json.load(f)
                    if evolved.get("iterations", 0) > len(all_results["evolution_records"]):
                        all_results["evolution_records"].append(evolved)
                except:
                    pass
    
    # 打印总结
    print(f"\n{'='*70}")
    print("测试总结")
    print(f"{'='*70}")
    total = all_results["total_rounds"]
    if total > 0:
        print(f"总轮数: {total}")
        print(f"目标识别准确率: {all_results['goal_recognition_correct']/total:.1%}")
        print(f"策略匹配率: {all_results['strategy_match']/total:.1%}")
        print(f"黑名单违规次数: {all_results['blacklist_violations']}")
        
        print(f"\n各目标识别准确率:")
        for goal, stats in all_results["goals_tested"].items():
            acc = stats["correct"] / stats["total"]
            print(f"  - {goal}: {acc:.0%} ({stats['correct']}/{stats['total']})")
        
        print(f"\n进化记录: {len(all_results['evolution_records'])} 次")
        if all_results["evolution_records"]:
            latest = all_results["evolution_records"][-1]
            print(f"  最新权重调整: {list(latest.get('strategy_weights', {}).items())[:3]}")
    else:
        print("未执行任何测试轮次")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="销售场景多轮随机目标测试")
    parser.add_argument("--rounds", type=int, default=10, help="每场景轮数")
    parser.add_argument("--scenarios", type=int, default=5, help="场景数")
    args = parser.parse_args()
    
    run_multi_round_test(n_rounds=args.rounds, n_scenarios=args.scenarios)
