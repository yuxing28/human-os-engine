"""把大循环报告翻译成沙盒洞察报告。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulation.sandbox_insight_pipeline import (
    analyze_large_cycle_report_file,
    build_review_cards,
    build_validation_queue,
    save_insight_report,
    save_review_cards,
    save_validation_queue,
)


DEFAULT_INPUT = PROJECT_ROOT / "data" / "large_cycle_report.json"
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "sandbox_insight_report.json"
DEFAULT_QUEUE_OUTPUT = PROJECT_ROOT / "data" / "sandbox_validation_queue.json"
DEFAULT_REVIEW_OUTPUT = PROJECT_ROOT / "data" / "sandbox_review_cards.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="分析沙盒/大循环报告，输出候选洞察")
    parser.add_argument("--input", default=str(DEFAULT_INPUT))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--queue-output", default=str(DEFAULT_QUEUE_OUTPUT))
    parser.add_argument("--previous-queue", default="")
    parser.add_argument("--review-output", default=str(DEFAULT_REVIEW_OUTPUT))
    args = parser.parse_args()

    insight = analyze_large_cycle_report_file(args.input)
    save_insight_report(insight, args.output)
    previous_queue = None
    if args.previous_queue:
        previous_path = Path(args.previous_queue)
        if previous_path.exists():
            previous_queue = json.loads(previous_path.read_text(encoding="utf-8"))
    queue = build_validation_queue(insight, previous_queue=previous_queue)
    save_validation_queue(queue, args.queue_output)
    review_cards = build_review_cards(queue)
    save_review_cards(review_cards, args.review_output)

    print(json.dumps({
        "output": args.output,
        "queue_output": args.queue_output,
        "review_output": args.review_output,
        "gate_summary": insight.get("gate_summary"),
        "main_system_write_allowed": insight.get("main_system_write_allowed"),
        "insight_count": len(insight.get("insights", [])),
        "validation_queue_size": queue.get("queue_size"),
        "ready_for_review_count": queue.get("ready_for_review_count"),
        "review_card_count": review_cards.get("card_count"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
