"""
Human-OS Engine - 自我博弈 MVP 运行脚本

用法: 
  py simulation/run_mvp.py                          # 默认运行所有场景
  py simulation/run_mvp.py --scenario picky_customer # 只运行指定场景
  py simulation/run_mvp.py --rounds 10 --runs 5     # 自定义轮数和场次
"""

import argparse
import time
import json
import os
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding='utf-8')
# 确保项目根目录在 sys.path 中
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 如果 simulation/ 在 ninv/ 下，需要找到 human-os-engine/
for d in [project_root, os.path.join(project_root, 'human-os-engine')]:
    if os.path.isdir(os.path.join(d, 'schemas')):
        project_root = d
        break
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from simulation.arena_loop import run_arena


def auto_analyze_weaknesses(all_outcomes: list) -> list:
    """自动分析系统弱点"""
    weaknesses = []

    # 1. 武器效果分析
    weapon_success = defaultdict(list)
    for outcome in all_outcomes:
        for weapon, count in outcome.get("weapon_counts", {}).items():
            weapon_success[weapon].append(outcome["trust_change"] > 0)

    for weapon, results in weapon_success.items():
        success_rate = sum(results) / len(results)
        if success_rate < 0.3 and len(results) >= 3:
            weaknesses.append(f"武器 '{weapon}' 成功率仅 {success_rate:.0%}，建议减少使用")

    # 2. 场景适配分析
    scene_success = defaultdict(list)
    for outcome in all_outcomes:
        scene_success[outcome.get("scenario", "unknown")].append(
            outcome["outcome"] == "system_win"
        )

    for scene, results in scene_success.items():
        win_rate = sum(results) / len(results)
        if win_rate < 0.3:
            weaknesses.append(f"场景 '{scene}' 胜率仅 {win_rate:.0%}，需要策略调整")

    # 3. 护栏违规分析
    scene_violations = defaultdict(list)
    for outcome in all_outcomes:
        scene = outcome.get("scenario", "unknown")
        scene_violations[scene].append(outcome.get("total_violations", 0))

    for scene, violations in scene_violations.items():
        avg_violations = sum(violations) / len(violations)
        if avg_violations >= 1.0:
            weaknesses.append(f"场景 '{scene}' 平均违规 {avg_violations:.2f}，建议优先收紧护栏策略")

    return weaknesses


# 场景配置映射
SCENARIOS = {
    "picky_customer": {
        "name": "挑剔型客户",
        "config": "picky_customer.json",
        "description": "防备心重，喜欢比价，对直接推销有抵触"
    },
    "hesitant_decision": {
        "name": "犹豫决策者",
        "config": "hesitant_decision.json",
        "description": "恐惧与懒惰驱动，反复权衡，容易被风险提示和简化流程打动"
    },
    "aggressive_opponent": {
        "name": "攻击性对手",
        "config": "aggressive_opponent.json",
        "description": "傲慢与愤怒驱动，喜欢打断、质疑、贬低"
    },
    "hesitant_manager": {
        "name": "犹豫型采购经理",
        "config": "hesitant_manager.json",
        "description": "恐惧驱动，担心决策失误，需要确定性证明"
    },
}


def print_result(result: dict, elapsed: float):
    """打印单场结果"""
    print(f"  结果: {result['outcome']}")
    print(f"  轮数: {result['total_rounds']}")
    print(f"  信任变化: {result['trust_initial']} → {result['trust_final']} ({result['trust_change']:+.3f})")
    print(f"  情绪变化: {result['emotion_initial']} → {result['emotion_final']} ({result['emotion_change']:+.3f})")
    print(f"  武器多样性: {result['weapon_diversity']}")
    if result['weapon_counts']:
        weapon_str = ", ".join(f"{k}({v})" for k, v in sorted(result['weapon_counts'].items()))
        print(f"  武器使用: {weapon_str}")
    print(f"  模式切换: {' → '.join(result['mode_sequence']) if result['mode_sequence'] else '无'} ({result['mode_switches']}次)")
    print(f"  纠正权触发: {result['corrections_triggered']}")
    print(f"  阻力应对: {result['resistance_resolved']}/{result['resistance_events']} ({result['resistance_success_rate']:.0%})")
    print(f"  护栏违规: {result.get('total_violations', 0)} (关键: {result.get('critical_violations', 0)})")
    if result.get("guardrail_terminated"):
        print("  终止原因: 关键违规触发提前终止")
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  日志: simulation/logs/{result['trace_id']}.jsonl")


def print_summary(outcomes: list, scenario_name: str):
    """打印汇总统计"""
    if not outcomes:
        return

    wins = sum(1 for o in outcomes if o["outcome"] == "system_win")
    losses = sum(1 for o in outcomes if o["outcome"] == "agent_win")
    draws = sum(1 for o in outcomes if o["outcome"] == "draw")
    total = len(outcomes)

    avg_trust = sum(o["trust_final"] for o in outcomes) / total
    avg_emotion = sum(o["emotion_final"] for o in outcomes) / total
    avg_trust_change = sum(o["trust_change"] for o in outcomes) / total
    avg_diversity = sum(o["weapon_diversity"] for o in outcomes) / total
    avg_corrections = sum(o["corrections_triggered"] for o in outcomes) / total
    avg_resistance_rate = sum(o["resistance_success_rate"] for o in outcomes) / total
    avg_violations = sum(o.get("total_violations", 0) for o in outcomes) / total
    avg_critical_violations = sum(o.get("critical_violations", 0) for o in outcomes) / total

    # 合并所有武器计数
    all_weapons = defaultdict(int)
    for o in outcomes:
        for w, c in o["weapon_counts"].items():
            all_weapons[w] += c

    print(f"\n{'='*60}")
    print(f"场景汇总: {scenario_name}")
    print(f"{'='*60}")
    print(f"  总场次: {total}")
    print(f"  系统胜率: {wins}/{total} ({wins/total*100:.0f}%)")
    print(f"  代理胜率: {losses}/{total} ({losses/total*100:.0f}%)")
    print(f"  平局: {draws}/{total} ({draws/total*100:.0f}%)")
    print(f"  平均信任变化: {avg_trust_change:+.3f}")
    print(f"  平均情绪变化: {avg_emotion - 0.6:+.3f}")
    print(f"  平均武器多样性: {avg_diversity:.1f}")
    print(f"  平均纠正权触发: {avg_corrections:.1f}")
    print(f"  平均阻力应对成功率: {avg_resistance_rate:.0%}")
    print(f"  平均护栏违规: {avg_violations:.2f} (关键: {avg_critical_violations:.2f})")
    if all_weapons:
        weapon_str = ", ".join(f"{k}({v})" for k, v in sorted(all_weapons.items(), key=lambda x: -x[1]))
        print(f"  武器总使用: {weapon_str}")


def main():
    parser = argparse.ArgumentParser(description="Human-OS Self-Play System")
    parser.add_argument("--scenario", type=str, default=None, 
                       choices=list(SCENARIOS.keys()) + ["all"],
                       help="运行指定场景（默认运行所有场景）")
    parser.add_argument("--rounds", type=int, default=10, help="每场最大轮数（默认 10）")
    parser.add_argument("--runs", type=int, default=3, help="每场景运行场次（默认 3）")
    args = parser.parse_args()

    # 确定要运行的场景
    if args.scenario and args.scenario != "all":
        scenarios_to_run = {args.scenario: SCENARIOS[args.scenario]}
    else:
        scenarios_to_run = SCENARIOS

    configs_dir = os.path.join(os.path.dirname(__file__), "configs")

    print("=" * 60)
    print("Human-OS Engine 自我博弈系统")
    print("=" * 60)
    print(f"场景数: {len(scenarios_to_run)}")
    print(f"每场轮数: {args.rounds}")
    print(f"每场景场次: {args.runs}")
    print()

    all_outcomes = {}

    for scenario_key, scenario_info in scenarios_to_run.items():
        config_path = os.path.join(configs_dir, scenario_info["config"])
        if not os.path.exists(config_path):
            print(f"⚠️ 场景配置不存在: {config_path}")
            continue

        print(f"\n{'#'*60}")
        print(f"# 场景: {scenario_info['name']} ({scenario_key})")
        print(f"# 描述: {scenario_info['description']}")
        print(f"{'#'*60}")

        outcomes = []
        for i in range(args.runs):
            print(f"\n--- 第 {i+1}/{args.runs} 场 ---")
            start = time.time()

            try:
                result = run_arena(
                    scenario=scenario_key,
                    agent_config_path=config_path,
                    max_rounds=args.rounds,
                )
                elapsed = time.time() - start
                print_result(result, elapsed)
                outcomes.append(result)
            except Exception as e:
                print(f"  ❌ 错误: {e}")
                import traceback
                traceback.print_exc()

        all_outcomes[scenario_key] = outcomes
        print_summary(outcomes, scenario_info["name"])

    # 全局汇总
    if len(all_outcomes) > 1:
        print(f"\n{'='*60}")
        print("全局汇总")
        print(f"{'='*60}")
        for scenario_key, outcomes in all_outcomes.items():
            if outcomes:
                wins = sum(1 for o in outcomes if o["outcome"] == "system_win")
                total = len(outcomes)
                scenario_name = SCENARIOS[scenario_key]["name"]
                print(f"  {scenario_name}: 胜率 {wins}/{total} ({wins/total*100:.0f}%)")

    # 自动弱点分析
    print(f"\n{'='*60}")
    print("自动弱点分析")
    print(f"{'='*60}")
    all_flat = []
    for scenario_key, outcomes in all_outcomes.items():
        for o in outcomes:
            o["scenario"] = scenario_key
            all_flat.append(o)

    weaknesses = auto_analyze_weaknesses(all_flat)
    if weaknesses:
        for w in weaknesses:
            print(f"  ⚠️ {w}")
    else:
        print("  ✅ 未发现明显弱点")


if __name__ == "__main__":
    main()
