"""
评测可观测日检脚本（首版）

用途：
1. 在统一口径下跑固定评测样本（默认 repeats=3，中位数）
2. 输出全局与场景过程汇总
3. 生成可追溯报告到 data/eval_observability_report.json
"""

from __future__ import annotations

import argparse
import json
import time
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulation.run_eval_set import (
    load_eval_set,
    run_single_turn,
    build_failure_code_distribution,
    build_scene_process_summary,
)

REPORT_PATH = PROJECT_ROOT / "data" / "eval_observability_report.json"


def run_check(repeats: int = 3, limit: int = 0) -> dict:
    entries = load_eval_set()
    if limit > 0:
        sample = entries[: min(limit, len(entries))]
    else:
        sample = entries

    results = []
    start = time.time()
    for i, entry in enumerate(sample, 1):
        try:
            r = run_single_turn(entry, repeats=repeats)
            results.append(r)
            print(
                f"[{i}/{len(sample)}] {entry['id']} OK "
                f"S={r['actual_strategy']}(d{r['strategy_delta']:+.1f}) "
                f"D={r['actual_delivery']}(d{r['delivery_delta']:+.1f})"
            )
        except Exception as e:
            results.append({
                "id": entry["id"],
                "scene": entry["scene"],
                "persona": entry["persona"],
                "round": entry["round"],
                "input": entry["input"],
                "gold_strategy": entry["gold_strategy"],
                "gold_delivery": entry["gold_delivery"],
                "actual_strategy": 0.0,
                "actual_delivery": 0.0,
                "actual_strategy_runs": [],
                "actual_delivery_runs": [],
                "progress_request": False,
                "output_order_marker_runs": [],
                "output_order_source_runs": [],
                "output_order_hit_rate": 0.0,
                "output_order_injected_hit_rate": 0.0,
                "failure_avoid_code_runs": [],
                "failure_avoid_hit_rate": 0.0,
                "memory_hint_signal_runs": [],
                "memory_failure_hint_hit_rate": 0.0,
                "memory_digest_hint_hit_rate": 0.0,
                "memory_decision_hint_hit_rate": 0.0,
                "failure_code": "",
                "failure_code_runs": [],
                "repeats": repeats,
                "strategy_delta": -entry["gold_strategy"],
                "delivery_delta": -entry["gold_delivery"],
                "tags": entry.get("tags", []),
                "error": str(e),
            })
            print(f"[{i}/{len(sample)}] {entry['id']} ERROR: {e}")

    total = max(1, len(results))
    regressions = [
        r["id"]
        for r in results
        if float(r.get("strategy_delta", 0)) < -1.5 or float(r.get("delivery_delta", 0)) < -1.5
    ]
    report = {
        "timestamp": time.time(),
        "elapsed_seconds": round(time.time() - start, 2),
        "repeats": repeats,
        "sample_size": len(sample),
        "avg_strategy_delta": round(sum(float(r.get("strategy_delta", 0)) for r in results) / total, 2),
        "avg_delivery_delta": round(sum(float(r.get("delivery_delta", 0)) for r in results) / total, 2),
        "regressions": regressions,
        "failure_code_distribution": build_failure_code_distribution(results),
        "scene_process_summary": build_scene_process_summary(results),
        "results": results,
    }
    return report


def save_report(report: dict):
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {REPORT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="评测可观测日检")
    parser.add_argument("--repeats", type=int, default=3, help="每条样本重复次数，默认3")
    parser.add_argument("--limit", type=int, default=0, help="抽检样本数，默认0=全量")
    args = parser.parse_args()

    repeats = max(1, int(args.repeats))
    limit = max(0, int(args.limit))
    report = run_check(repeats=repeats, limit=limit)
    print("\n=== 评测可观测汇总 ===")
    print(f"sample_size={report['sample_size']} repeats={report['repeats']}")
    print(
        f"avg_strategy_delta={report['avg_strategy_delta']:+.2f} "
        f"avg_delivery_delta={report['avg_delivery_delta']:+.2f}"
    )
    print(f"regressions={report['regressions']}")
    print(f"failure_code_distribution={report['failure_code_distribution']}")
    print(f"scene_process_summary={report['scene_process_summary']}")
    save_report(report)
