"""
Phase2 Sprint 评测脚本（固定样本包）

用途：
1. 跑固定 sprint 样本包（默认 12 条）
2. 输出每条得分与 delta
3. 自动给出最弱 TOP3（按 strategy+delivery 总 delta）
4. 落盘结构化报告
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulation.run_eval_set import (
    build_failure_code_distribution,
    build_scene_process_summary,
    run_single_turn,
)

DEFAULT_EVAL_SET_PATH = PROJECT_ROOT / "data" / "eval_set_phase2_sprint1.json"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "eval_phase2_sprint1_baseline.json"


def _load_entries(eval_set_path: Path) -> list[dict]:
    payload = json.loads(eval_set_path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    if not isinstance(entries, list) or not entries:
        raise ValueError(f"评测集为空或格式不对: {eval_set_path}")
    return entries


def _calc_rank_score(item: dict) -> float:
    return float(item.get("strategy_delta", 0.0) or 0.0) + float(item.get("delivery_delta", 0.0) or 0.0)


def run_phase2_sprint(entries: list[dict], repeats: int) -> dict:
    started = time.time()
    results: list[dict] = []
    for idx, entry in enumerate(entries, 1):
        result = run_single_turn(entry, repeats=max(1, int(repeats)))
        results.append(result)
        print(
            f"[{idx}/{len(entries)}] {entry['id']} "
            f"S={result['actual_strategy']}(d{result['strategy_delta']:+.1f}) "
            f"D={result['actual_delivery']}(d{result['delivery_delta']:+.1f})"
        )

    total = max(1, len(results))
    avg_strategy_delta = round(sum(float(r.get("strategy_delta", 0.0) or 0.0) for r in results) / total, 2)
    avg_delivery_delta = round(sum(float(r.get("delivery_delta", 0.0) or 0.0) for r in results) / total, 2)
    regressions = [
        r["id"]
        for r in results
        if float(r.get("strategy_delta", 0.0) or 0.0) < -1.5
        or float(r.get("delivery_delta", 0.0) or 0.0) < -1.5
    ]
    weakest_top3 = sorted(results, key=_calc_rank_score)[:3]
    weakest_top3_brief = [
        {
            "id": item.get("id"),
            "scene": item.get("scene"),
            "strategy_delta": item.get("strategy_delta"),
            "delivery_delta": item.get("delivery_delta"),
            "rank_score": round(_calc_rank_score(item), 2),
            "failure_code": item.get("failure_code", ""),
        }
        for item in weakest_top3
    ]

    return {
        "timestamp": time.time(),
        "elapsed_seconds": round(time.time() - started, 2),
        "repeats": max(1, int(repeats)),
        "sample_size": len(results),
        "avg_strategy_delta": avg_strategy_delta,
        "avg_delivery_delta": avg_delivery_delta,
        "regressions": regressions,
        "failure_code_distribution": build_failure_code_distribution(results),
        "scene_process_summary": build_scene_process_summary(results),
        "weakest_top3": weakest_top3_brief,
        "results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase2 Sprint 固定样本评测")
    parser.add_argument("--eval-set-path", default=str(DEFAULT_EVAL_SET_PATH))
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--output-path", default=str(DEFAULT_OUTPUT_PATH))
    args = parser.parse_args()

    eval_set_path = Path(args.eval_set_path)
    output_path = Path(args.output_path)
    entries = _load_entries(eval_set_path)
    report = run_phase2_sprint(entries, repeats=max(1, int(args.repeats)))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n=== Phase2 Sprint 基线汇总 ===")
    print(
        f"sample_size={report['sample_size']} repeats={report['repeats']} "
        f"avg_strategy_delta={report['avg_strategy_delta']:+.2f} "
        f"avg_delivery_delta={report['avg_delivery_delta']:+.2f}"
    )
    print(f"regressions={report['regressions']}")
    print(f"failure_code_distribution={report['failure_code_distribution']}")
    print("weakest_top3=" + json.dumps(report["weakest_top3"], ensure_ascii=False))
    print(f"\n报告已保存: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
