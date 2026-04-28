"""
Human-OS Engine 3.0 — 批量压力测试脚本 (Batch Runner)
运行 100 场模拟，生成《策略效能热力图》。
"""

import os
import json
import time
import sys
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.stdout.reconfigure(encoding='utf-8') if sys.stdout.encoding != 'utf-8' else None

from simulation.arena_v2 import SalesArena
from simulation.persona_factory import PersonaFactory

def main():
    print("="*80)
    print("🚀 Human-OS Engine 3.0 — 销售沙盒批量压力测试")
    print("="*80)
    
    # 1. 初始化
    arena = SalesArena()
    factory = PersonaFactory()
    
    BATCH_SIZE = 10  # 每次运行 10 场
    MAX_ROUNDS = 6   # 每场最多 6 轮
    
    print(f"\n📋 计划运行 {BATCH_SIZE} 场模拟，每场最多 {MAX_ROUNDS} 轮")
    print(f"⏰ 开始时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    
    results = []
    
    for i in range(BATCH_SIZE):
        # 生成随机客户
        persona = factory.generate()
        print(f"\n{'='*60}")
        print(f"🎭 [{i+1}/{BATCH_SIZE}] {persona.name} ({persona.role}, {persona.personality[:15]}...)")
        print(f"   行业：{persona.product} | 隐藏意图：{persona.hidden_agenda}")
        
        # 运行对话
        try:
            result = arena.run_conversation(persona, max_rounds=MAX_ROUNDS)
            results.append(result)
            
            # 打印结果
            outcome = result['outcome']
            trust = result['final_trust']
            emotion = result['final_emotion']
            violations = result.get('total_violations', 0)
            print(f"   ✅ 结果: {outcome} | 信任: {trust:.2f} | 情绪: {emotion:.2f} | 违规: {violations}")
            
        except Exception as e:
            print(f"   ❌ 异常: {e}")
            results.append(
                {
                    "outcome": "error",
                    "persona": {"name": persona.name, "role": persona.role},
                    "total_violations": 1,
                }
            )
        
        # 间隔防止限流
        if i < BATCH_SIZE - 1:
            time.sleep(2)
    
    # 2. 生成报告
    print(f"\n{'='*80}")
    print("📊 批量测试报告")
    print(f"{'='*80}")
    
    # 统计结果
    outcomes = {}
    avg_trust = 0
    avg_emotion = 0
    total_violations = 0
    valid_count = 0
    
    for r in results:
        o = r.get('outcome', '未知')
        outcomes[o] = outcomes.get(o, 0) + 1
        if r.get('final_trust') is not None:
            avg_trust += r['final_trust']
            avg_emotion += r.get('final_emotion', 0)
            valid_count += 1
        total_violations += r.get("total_violations", 0)
    
    avg_trust = avg_trust / valid_count if valid_count > 0 else 0
    avg_emotion = avg_emotion / valid_count if valid_count > 0 else 0
    
    print(f"\n📈 总体统计:")
    print(f"  总场次: {len(results)}")
    print(f"  平均最终信任: {avg_trust:.2f}")
    print(f"  平均最终情绪: {avg_emotion:.2f}")
    print(f"  护栏违规总数: {total_violations}")
    print(f"  结果分布: {outcomes}")
    
    # 保存报告
    report_path = os.path.join(os.path.dirname(__file__), 'batch_report.json')
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 详细报告已保存: {report_path}")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
