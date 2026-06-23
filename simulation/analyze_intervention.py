"""
Human-OS Engine - 进化闭环介入分析脚本

用法: py -m simulation.analyze_intervention

功能:
1. 读取各场景的 success_spectrum.json 和 counter_examples.json
2. 统计 bonus 触发频率、hint 触发频率
3. 输出介入概览和评分对比
"""

import json
import time
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = PROJECT_ROOT / "skills"
SCENES = ["sales", "negotiation", "management", "emotion"]


def load_json(path: Path) -> list:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def analyze_scene(scene_id: str) -> dict:
    """分析单个场景的进化闭环数据"""
    scene_dir = SKILLS_DIR / scene_id
    
    # 成功谱
    success_records = load_json(scene_dir / "success_spectrum.json")
    # 反例库
    failure_records = load_json(scene_dir / "counter_examples.json")
    
    now = time.time()
    window_4h = 3600 * 4
    window_2h = 3600 * 2
    
    # 近期成功统计
    recent_success = [r for r in success_records if now - r.get("timestamp", 0) < window_4h]
    success_by_strategy = defaultdict(list)
    for r in recent_success:
        strat = r.get("strategy", "")
        score = float(r.get("score", 0))
        if strat and score > 0:
            success_by_strategy[strat].append(score)
    
    # 近期失败统计
    recent_failure = [r for r in failure_records if now - r.get("timestamp", 0) < window_2h]
    failure_by_strategy = defaultdict(int)
    failure_by_type = defaultdict(int)
    failure_by_code = defaultdict(int)
    for r in recent_failure:
        strat = r.get("strategy", "")
        ft = r.get("failure_type", "")
        fc = r.get("failure_code", "")
        if strat:
            failure_by_strategy[strat] += 1
        if ft:
            failure_by_type[ft] += 1
        if fc:
            failure_by_code[fc] += 1
    
    # 计算bonus触发
    bonus_triggered = {}
    for strat, scores in success_by_strategy.items():
        count = len(scores)
        avg = sum(scores) / count
        if count >= 3 and avg >= 7.0:
            bonus_triggered[strat] = {"bonus": 1.3, "count": count, "avg_score": round(avg, 1)}
        elif count >= 2 and avg >= 7.0:
            bonus_triggered[strat] = {"bonus": 1.15, "count": count, "avg_score": round(avg, 1)}
        elif count >= 1 and avg >= 8.0:
            bonus_triggered[strat] = {"bonus": 1.1, "count": count, "avg_score": round(avg, 1)}
    
    # 计算hint触发
    hint_triggered = {}
    for ft, count in failure_by_type.items():
        if count >= 2:
            hint_triggered[ft] = count

    hint_code_triggered = {}
    for fc, count in failure_by_code.items():
        if count >= 2:
            hint_code_triggered[fc] = count

    return {
        "scene_id": scene_id,
        "total_success_records": len(success_records),
        "total_failure_records": len(failure_records),
        "recent_success_count": len(recent_success),
        "recent_failure_count": len(recent_failure),
        "bonus_triggered": bonus_triggered,
        "hint_triggered": hint_triggered,
        "hint_code_triggered": hint_code_triggered,
        "failure_by_type": dict(failure_by_type),
        "failure_by_code": dict(failure_by_code),
    }


def print_report(results: list[dict]):
    """打印分析报告"""
    print("=" * 60)
    print("进化闭环介入分析报告")
    print("=" * 60)
    
    total_bonus = 0
    total_hint = 0
    total_hint_code = 0
    
    for r in results:
        scene = r["scene_id"]
        n_bonus = len(r["bonus_triggered"])
        n_hint = len(r["hint_triggered"])
        n_hint_code = len(r["hint_code_triggered"])
        total_bonus += n_bonus
        total_hint += n_hint
        total_hint_code += n_hint_code
        
        print(f"\n--- {scene} ---")
        print(f"  成功谱: {r['total_success_records']}条(近期{r['recent_success_count']}) | 反例库: {r['total_failure_records']}条(近期{r['recent_failure_count']})")
        
        if r["bonus_triggered"]:
            print(f"  Bonus触发 ({n_bonus}个):")
            for strat, info in r["bonus_triggered"].items():
                print(f"    {strat}: x{info['bonus']} ({info['count']}次成功, 均分{info['avg_score']})")
        else:
            print(f"  Bonus触发: 无")
        
        if r["hint_triggered"]:
            print(f"  Hint触发 ({n_hint}个):")
            for ft, count in r["hint_triggered"].items():
                print(f"    {ft}: 近期{count}次")
        else:
            print(f"  Hint触发: 无")

        if r["hint_code_triggered"]:
            print(f"  失败码触发 ({n_hint_code}个):")
            for fc, count in r["hint_code_triggered"].items():
                print(f"    {fc}: 近期{count}次")
        else:
            print(f"  失败码触发: 无")
        
        if r["failure_by_type"]:
            print(f"  失败类型分布:")
            for ft, count in r["failure_by_type"].items():
                print(f"    {ft}: {count}次")
        if r["failure_by_code"]:
            print(f"  失败码分布:")
            for fc, count in r["failure_by_code"].items():
                print(f"    {fc}: {count}次")
    
    print(f"\n{'=' * 60}")
    print(f"汇总: Bonus触发{total_bonus}个 | Hint触发{total_hint}个 | 失败码触发{total_hint_code}个")
    
    if total_bonus == 0 and total_hint == 0:
        print("  (进化闭环尚未积累足够数据，需要更多沙盒运行)")
    elif total_bonus > 0:
        print("  (成功谱已生效，系统正在复用成功策略)")
    if total_hint > 0:
        print("  (避坑提示已生效，系统正在规避高频失败模式)")


if __name__ == "__main__":
    results = []
    for scene in SCENES:
        results.append(analyze_scene(scene))
    print_report(results)
