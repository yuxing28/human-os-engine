"""
Human-OS Engine - 基线指标测试 (Baseline Metrics)

快速运行少量模拟，建立当前版本的质量基线。
用于后续版本对比，确保不退化。
"""

import os
import sys
import json
import time
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(encoding='utf-8')

from simulation.arena_v2 import SalesArena
from simulation.persona_factory import PersonaFactory


def run_baseline(num_runs=30, max_rounds=4, output_path=None):
    """运行基线测试"""
    arena = SalesArena()
    factory = PersonaFactory()
    
    # 固定随机种子，确保统计稳定性
    random.seed(42)
    
    print(f"🚀 开始基线测试：{num_runs} 场 x {max_rounds} 轮")
    print(f"⏰ 开始时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🔒 随机种子：42（固定）\n")
    
    results = []
    success_count = 0
    total_trust = 0.0
    total_rounds = 0
    
    for i in range(num_runs):
        persona = factory.generate()
        print(f"🎭 [{i+1}/{num_runs}] {persona.name} ({persona.role})")
        
        try:
            res = arena.run_conversation(persona, max_rounds=max_rounds)
            results.append(res)
            
            trust = res['final_trust']
            total_trust += trust
            total_rounds += res.get('rounds', max_rounds)
            
            if trust > 0.7:
                success_count += 1
                print(f"   ✅ 成功 | 信任: {trust:.2f}")
            else:
                print(f"   ⚠️ 失败 | 信任: {trust:.2f}")
                
        except Exception as e:
            print(f"   ❌ 异常: {e}")
        
        # 间隔防止 API 限流
        if i < num_runs - 1:
            time.sleep(2)

    # 计算指标
    avg_trust = total_trust / len(results) if results else 0
    success_rate = success_count / len(results) if results else 0
    avg_rounds = total_rounds / len(results) if results else 0
    
    # 输出报告
    print(f"\n{'='*60}")
    print("📊 基线测试报告")
    print(f"{'='*60}")
    print(f"  总场次: {len(results)}")
    print(f"  平均最终信任: {avg_trust:.2f}")
    print(f"  成功率 (Trust > 0.7): {success_rate:.0%}")
    print(f"  平均轮数: {avg_rounds:.1f}")
    
    # 保存基线数据
    baseline = {
        "version": "1.2.4",
        "date": time.strftime('%Y-%m-%d %H:%M:%S'),
        "num_runs": num_runs,
        "max_rounds": max_rounds,
        "random_seed": 42,
        "metrics": {
            "avg_trust": round(avg_trust, 2),
            "success_rate": round(success_rate, 2),
            "avg_rounds": round(avg_rounds, 1)
        }
    }
    
    baseline_path = output_path or os.path.join(os.path.dirname(__file__), '..', 'docs', 'BASELINE_METRICS.json')
    os.makedirs(os.path.dirname(baseline_path), exist_ok=True)
    with open(baseline_path, 'w', encoding='utf-8') as f:
        json.dump(baseline, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 基线数据已保存: {baseline_path}")
    print(f"{'='*60}")
    
    return baseline


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="运行基线测试")
    parser.add_argument("--runs", type=int, default=30, help="测试场数")
    parser.add_argument("--rounds", type=int, default=4, help="每场轮数")
    parser.add_argument("--output", type=str, default=None, help="输出文件路径")
    args = parser.parse_args()
    
    out_path = args.output
    if not out_path:
        out_path = os.path.join(os.path.dirname(__file__), '..', 'docs', 'BASELINE_METRICS.json')
        
    run_baseline(num_runs=args.runs, max_rounds=args.rounds, output_path=out_path)
