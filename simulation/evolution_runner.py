"""
Human-OS Engine 3.0 — 进化运行器 (Evolution Runner)
大规模运行模拟，积累数据以驱动策略自动进化。
"""

import os
import sys
import time
import json
import random

# 固定随机种子，确保结果可复现
random.seed(42)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(encoding='utf-8') if sys.stdout.encoding != 'utf-8' else None

from simulation.arena_v2 import SalesArena
from simulation.persona_factory import PersonaFactory
from simulation.scene_evolver import SceneEvolver

def run_evolution(num_runs=20, max_rounds=6):
    arena = SalesArena()
    factory = PersonaFactory()
    
    print(f"🚀 开始进化模拟：{num_runs} 场 x {max_rounds} 轮")
    print(f"⏰ 开始时间：{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    stats = {"total": 0, "success": 0, "avg_trust": 0.0, "total_violations": 0, "outcomes": {}}
    
    for i in range(num_runs):
        persona = factory.generate()
        print(f"🎭 [{i+1}/{num_runs}] {persona.name} ({persona.role}, {persona.personality[:10]}...)")
        
        try:
            res = arena.run_conversation(persona, max_rounds=max_rounds)
            stats["total"] += 1
            stats["avg_trust"] += res['final_trust']
            violations = res.get("total_violations", 0)
            stats["total_violations"] += violations
            
            outcome = res.get('outcome', '未知')
            stats["outcomes"][outcome] = stats["outcomes"].get(outcome, 0) + 1
            
            if res['final_trust'] > 0.7 and violations == 0:
                stats["success"] += 1
                print(f"   ✅ 成功 | 信任: {res['final_trust']:.2f} | 违规: {violations}")
            else:
                print(f"   ⚠️ 失败 | 信任: {res['final_trust']:.2f} | 违规: {violations}")
                
        except Exception as e:
            print(f"   ❌ 异常: {e}")
        
        # 关键：防止 API 限流 (DeepSeek/NVIDIA)
        if i < num_runs - 1:
            time.sleep(3)

    # 总结
    if stats["total"] > 0:
        avg_trust = stats["avg_trust"] / stats["total"]
        success_rate = stats["success"] / stats["total"]
        
        print(f"\n{'='*80}")
        print("📊 进化模拟总结")
        print(f"{'='*80}")
        print(f"  总场次: {stats['total']}")
        print(f"  成功率 (信任>0.7 且无违规): {success_rate:.0%}")
        print(f"  平均最终信任: {avg_trust:.2f}")
        print(f"  护栏违规总数: {stats['total_violations']}")
        print(f"  结果分布: {stats['outcomes']}")
        print(f"{'='*80}")
        
        # 读取进化数据
        evolver_path = SceneEvolver("sales").current_path
        if os.path.exists(evolver_path):
            with open(evolver_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"\n🧬 进化状态:")
            print(f"  迭代次数: {data.get('iterations', 0)}")
            print(f"  总交互数: {data.get('performance_metrics', {}).get('total_interactions', 0)}")
            print(f"  当前成功率: {data.get('performance_metrics', {}).get('success_rate', 0):.0%}")

if __name__ == "__main__":
    run_evolution(num_runs=20, max_rounds=6)
