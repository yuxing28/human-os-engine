"""
记忆可观测日检脚本（首版）

用途：
1. 在统一口径下跑一批固定评测样本
2. 输出记忆写入全局分布（stored/skipped/skip_reasons/by_type）
3. 生成可追溯报告到 data/memory_observability_report.json
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

from modules.memory import (
    get_global_memory_write_summary,
    reset_memory_write_events,
)
from simulation.run_eval_set import load_eval_set, run_single_turn

REPORT_PATH = PROJECT_ROOT / "data" / "memory_observability_report.json"


def run_check(repeats: int = 1, limit: int = 12) -> dict:
    entries = load_eval_set()
    sample = entries[: max(1, min(limit, len(entries)))]

    reset_memory_write_events()

    results = []
    start = time.time()
    for i, entry in enumerate(sample, 1):
        try:
            r = run_single_turn(entry, repeats=repeats)
            results.append({
                "id": r["id"],
                "scene": r["scene"],
                "strategy_delta": r["strategy_delta"],
                "delivery_delta": r["delivery_delta"],
                "failure_code": r.get("failure_code", ""),
            })
            print(f"[{i}/{len(sample)}] {entry['id']} OK")
        except Exception as e:
            results.append({
                "id": entry["id"],
                "scene": entry["scene"],
                "error": str(e),
            })
            print(f"[{i}/{len(sample)}] {entry['id']} ERROR: {e}")

    summary = get_global_memory_write_summary(limit_per_user=200)
    report = {
        "timestamp": time.time(),
        "elapsed_seconds": round(time.time() - start, 2),
        "repeats": repeats,
        "sample_size": len(sample),
        "global_memory_write_summary": summary,
        "entries": results,
    }
    return report


def save_report(report: dict):
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {REPORT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="记忆可观测日检")
    parser.add_argument("--repeats", type=int, default=1, help="每条样本重复次数，默认1")
    parser.add_argument("--limit", type=int, default=12, help="抽检样本数，默认12")
    args = parser.parse_args()

    report = run_check(repeats=max(1, args.repeats), limit=max(1, args.limit))
    summary = report["global_memory_write_summary"]
    print("\n=== 记忆写入汇总 ===")
    print(f"sample_size={report['sample_size']} repeats={report['repeats']}")
    print(f"user_count={summary.get('user_count', 0)} total_events={summary.get('total_events', 0)}")
    print(f"stored={summary.get('stored', 0)} skipped={summary.get('skipped', 0)}")
    print(f"skip_reasons={summary.get('skip_reasons', {})}")
    print(f"by_type={summary.get('by_type', {})}")
    print(f"by_bucket={summary.get('by_bucket', {})}")
    print(f"health={summary.get('health', {})}")
    save_report(report)
