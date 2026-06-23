"""
Human-OS Engine 3.0 — A/B 测试运行器
对比 v1.1.0 (旧版) 和 v1.2.0 (新版) 的销售策略效果。
"""

import os
import json
import time
import sys
import copy
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(encoding='utf-8') if sys.stdout.encoding != 'utf-8' else None

from simulation.arena_v2 import SalesArena
from simulation.persona_factory import PersonaFactory

# 定义 A/B 组配置差异
CONFIG_A = {
    "name": "v1.1.0 (旧版 - 贪婪/恐惧驱动)",
    "overrides": {
        "value_differentiation": [
            {"combo": "好奇+稀缺", "weight": 0.84},
            {"combo": "价值锚定+社交证明", "weight": 0.7}
        ],
        "close_deal": [
            {"combo": "贪婪+恐惧", "weight": 0.8},
            {"combo": "懒惰+损失规避", "weight": 0.7}
        ]
    }
}

CONFIG_B = {
    "name": "v1.2.0 (新版 - 权威/价值驱动)",
    "overrides": {
        "value_differentiation": [
            {"combo": "好奇+价值", "weight": 0.9},
            {"combo": "权威+案例", "weight": 0.85}
        ],
        "close_deal": [
            {"combo": "懒惰+损失规避", "weight": 0.85},
            {"combo": "提供确定性+案例证明", "weight": 0.75}
        ]
    }
}

def apply_config(scene_config, overrides):
    """应用配置覆盖"""
    for goal_key, prefs in overrides.items():
        for g in scene_config.goal_taxonomy:
            if g.granular_goal == goal_key:
                g.strategy_preferences = prefs
                break
    return scene_config

def run_ab_test(num_runs=10, max_rounds=4):
    arena = SalesArena()
    factory = PersonaFactory()
    
    results_a = []
    results_b = []
    
    # 加载基础配置
    from modules.L5.scene_loader import load_scene_config
    base_config = load_scene_config("sales")
    
    print(f"🚀 开始 A/B 测试：{num_runs} 场 x {max_rounds} 轮")
    print(f"   A 组：{CONFIG_A['name']}")
    print(f"   B 组：{CONFIG_B['name']}\n")

    for i in range(num_runs):
        persona = factory.generate()
        print(f"🎭 [{i+1}/{num_runs}] {persona.name} ({persona.role})")

        # --- 运行 A 组 ---
        config_a = copy.deepcopy(base_config)
        apply_config(config_a, CONFIG_A['overrides'])
        arena.scene_config = config_a
        
        try:
            res_a = arena.run_conversation(persona, max_rounds=max_rounds)
            results_a.append(res_a)
            print(
                f"   ✅ A 组: {res_a['outcome']} | 信任: {res_a['final_trust']:.2f} "
                f"| 违规: {res_a.get('total_violations', 0)}"
            )
        except Exception as e:
            print(f"   ❌ A 组异常: {e}")
            
        time.sleep(1) # 间隔

        # --- 运行 B 组 ---
        config_b = copy.deepcopy(base_config)
        apply_config(config_b, CONFIG_B['overrides'])
        arena.scene_config = config_b
        
        try:
            res_b = arena.run_conversation(persona, max_rounds=max_rounds)
            results_b.append(res_b)
            print(
                f"   ✅ B 组: {res_b['outcome']} | 信任: {res_b['final_trust']:.2f} "
                f"| 违规: {res_b.get('total_violations', 0)}"
            )
        except Exception as e:
            print(f"   ❌ B 组异常: {e}")
            
        time.sleep(1)

    # --- 生成报告 ---
    print(f"\n{'='*80}")
    print("📊 A/B 测试报告")
    print(f"{'='*80}")
    
    def calc_stats(results):
        avg_trust = sum(r.get('final_trust', 0) for r in results) / len(results)
        avg_violations = sum(r.get('total_violations', 0) for r in results) / len(results)
        outcomes = {}
        for r in results:
            o = r.get('outcome', '未知')
            outcomes[o] = outcomes.get(o, 0) + 1
        return avg_trust, avg_violations, outcomes

    avg_a, avg_v_a, out_a = calc_stats(results_a)
    avg_b, avg_v_b, out_b = calc_stats(results_b)

    print(f"\n📈 总体统计:")
    print(f"  A 组平均信任: {avg_a:.2f} | 平均违规: {avg_v_a:.2f} | 结果分布: {out_a}")
    print(f"  B 组平均信任: {avg_b:.2f} | 平均违规: {avg_v_b:.2f} | 结果分布: {out_b}")
    
    diff = avg_b - avg_a
    print(f"  信任提升: {diff:+.2f} ({'✅ B 组更优' if diff > 0 else '❌ A 组更优'})")

    # 保存报告
    report = {
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "group_a": {
            "name": CONFIG_A['name'],
            "avg_trust": avg_a,
            "avg_violations": avg_v_a,
            "outcomes": out_a,
            "details": results_a,
        },
        "group_b": {
            "name": CONFIG_B['name'],
            "avg_trust": avg_b,
            "avg_violations": avg_v_b,
            "outcomes": out_b,
            "details": results_b,
        },
    }
    
    path = os.path.join(os.path.dirname(__file__), 'ab_test_report.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n💾 详细报告已保存: {path}")

if __name__ == "__main__":
    run_ab_test(num_runs=10, max_rounds=4)
