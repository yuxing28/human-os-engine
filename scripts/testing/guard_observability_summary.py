"""
门禁三件套总览脚本

用途：
1. 汇总 eval_observability_report / merge_gate_report / release_guard_report
2. 输出一页终端摘要（可直接看是否可放行）
3. 生成结构化总览报告到 data/guard_overview_report.json
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"

DEFAULT_EVAL_REPORT = DATA_DIR / "eval_observability_report.json"
DEFAULT_MERGE_REPORT = DATA_DIR / "merge_gate_report.json"
DEFAULT_RELEASE_REPORT = DATA_DIR / "release_guard_report.json"
DEFAULT_OVERVIEW_OUTPUT = DATA_DIR / "guard_overview_report.json"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _extract_progress_order_summary(eval_report: dict[str, Any]) -> dict[str, float | int]:
    scene_summary = eval_report.get("scene_process_summary", {})
    if not isinstance(scene_summary, dict):
        return {
            "progress_entries": 0,
            "progress_entries_with_order": 0,
            "progress_entries_with_injected_order": 0,
            "progress_order_coverage": 0.0,
            "entries_with_failure_avoid": 0,
            "avg_failure_avoid_hit_rate": 0.0,
            "entries_with_memory_failure_hint": 0,
            "entries_with_memory_digest_hint": 0,
            "entries_with_memory_decision_hint": 0,
            "avg_memory_failure_hint_hit_rate": 0.0,
            "avg_memory_digest_hint_hit_rate": 0.0,
            "avg_memory_decision_hint_hit_rate": 0.0,
        }

    progress_entries = 0
    progress_entries_with_order = 0
    progress_entries_with_injected_order = 0
    entries_with_failure_avoid = 0
    entries_with_memory_failure_hint = 0
    entries_with_memory_digest_hint = 0
    entries_with_memory_decision_hint = 0
    avg_failure_avoid_hit_rate_numerator = 0.0
    avg_memory_failure_hint_hit_rate_numerator = 0.0
    avg_memory_digest_hint_hit_rate_numerator = 0.0
    avg_memory_decision_hint_hit_rate_numerator = 0.0
    scene_count = 0
    for item in scene_summary.values():
        if not isinstance(item, dict):
            continue
        scene_count += 1
        progress_entries += int(item.get("progress_entries", 0) or 0)
        progress_entries_with_order += int(item.get("progress_entries_with_order", 0) or 0)
        progress_entries_with_injected_order += int(
            item.get("progress_entries_with_injected_order", 0) or 0
        )
        entries_with_failure_avoid += int(item.get("entries_with_failure_avoid", 0) or 0)
        entries_with_memory_failure_hint += int(item.get("entries_with_memory_failure_hint", 0) or 0)
        entries_with_memory_digest_hint += int(item.get("entries_with_memory_digest_hint", 0) or 0)
        entries_with_memory_decision_hint += int(item.get("entries_with_memory_decision_hint", 0) or 0)
        avg_failure_avoid_hit_rate_numerator += float(item.get("avg_failure_avoid_hit_rate", 0.0) or 0.0)
        avg_memory_failure_hint_hit_rate_numerator += float(item.get("avg_memory_failure_hint_hit_rate", 0.0) or 0.0)
        avg_memory_digest_hint_hit_rate_numerator += float(item.get("avg_memory_digest_hint_hit_rate", 0.0) or 0.0)
        avg_memory_decision_hint_hit_rate_numerator += float(item.get("avg_memory_decision_hint_hit_rate", 0.0) or 0.0)

    coverage = (
        round(progress_entries_with_order / progress_entries, 2) if progress_entries > 0 else 0.0
    )
    avg_failure_avoid_hit_rate = (
        round(avg_failure_avoid_hit_rate_numerator / scene_count, 2) if scene_count > 0 else 0.0
    )
    avg_memory_failure_hint_hit_rate = (
        round(avg_memory_failure_hint_hit_rate_numerator / scene_count, 2) if scene_count > 0 else 0.0
    )
    avg_memory_digest_hint_hit_rate = (
        round(avg_memory_digest_hint_hit_rate_numerator / scene_count, 2) if scene_count > 0 else 0.0
    )
    avg_memory_decision_hint_hit_rate = (
        round(avg_memory_decision_hint_hit_rate_numerator / scene_count, 2) if scene_count > 0 else 0.0
    )
    return {
        "progress_entries": progress_entries,
        "progress_entries_with_order": progress_entries_with_order,
        "progress_entries_with_injected_order": progress_entries_with_injected_order,
        "progress_order_coverage": coverage,
        "entries_with_failure_avoid": entries_with_failure_avoid,
        "avg_failure_avoid_hit_rate": avg_failure_avoid_hit_rate,
        "entries_with_memory_failure_hint": entries_with_memory_failure_hint,
        "entries_with_memory_digest_hint": entries_with_memory_digest_hint,
        "entries_with_memory_decision_hint": entries_with_memory_decision_hint,
        "avg_memory_failure_hint_hit_rate": avg_memory_failure_hint_hit_rate,
        "avg_memory_digest_hint_hit_rate": avg_memory_digest_hint_hit_rate,
        "avg_memory_decision_hint_hit_rate": avg_memory_decision_hint_hit_rate,
    }


def _find_merge_step(merge_report: dict[str, Any], step_name: str) -> dict[str, Any] | None:
    steps = merge_report.get("steps", [])
    if not isinstance(steps, list):
        return None
    for step in steps:
        if isinstance(step, dict) and str(step.get("name") or "") == step_name:
            return step
    return None


def _extract_sandbox_trend_summary(merge_report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(merge_report, dict):
        return {
            "status": None,
            "slow_scene_count": None,
            "slow_scene_details": None,
            "scene_recent_samples": None,
            "is_red": None,
            "reasons": None,
        }

    trend_step = _find_merge_step(merge_report, "沙盒性能趋势门禁")
    if not isinstance(trend_step, dict):
        return {
            "status": None,
            "slow_scene_count": None,
            "slow_scene_details": None,
            "scene_recent_samples": None,
            "is_red": None,
            "reasons": None,
        }

    trend_status = str(trend_step.get("status") or "")
    trend_meta = trend_step.get("meta", {})
    if not isinstance(trend_meta, dict):
        trend_meta = {}
    slow_scene_count = int(trend_meta.get("slow_scene_count", 0) or 0)
    reasons = trend_step.get("reasons", [])
    if not isinstance(reasons, list):
        reasons = []
    return {
        "status": trend_status,
        "slow_scene_count": slow_scene_count,
        "slow_scene_details": trend_meta.get("slow_scene_details", []),
        "scene_recent_samples": trend_meta.get("scene_recent_samples", {}),
        "is_red": bool(trend_status in {"warn", "fail"} and slow_scene_count > 0),
        "reasons": reasons,
    }


def build_overview(
    eval_report: dict[str, Any] | None,
    merge_report: dict[str, Any] | None,
    release_report: dict[str, Any] | None,
) -> dict[str, Any]:
    eval_exists = eval_report is not None
    merge_exists = merge_report is not None
    release_exists = release_report is not None

    eval_ok = bool(eval_exists and not eval_report.get("regressions"))
    merge_ok = bool(merge_exists and merge_report.get("overall_passed") is True)
    release_ok = bool(release_exists and release_report.get("overall_passed") is True)

    progress_order_summary = (
        _extract_progress_order_summary(eval_report)
        if eval_exists
        else {
            "progress_entries": None,
            "progress_entries_with_order": None,
            "progress_entries_with_injected_order": None,
            "progress_order_coverage": None,
            "entries_with_failure_avoid": None,
            "avg_failure_avoid_hit_rate": None,
            "entries_with_memory_failure_hint": None,
            "entries_with_memory_digest_hint": None,
            "entries_with_memory_decision_hint": None,
            "avg_memory_failure_hint_hit_rate": None,
            "avg_memory_digest_hint_hit_rate": None,
            "avg_memory_decision_hint_hit_rate": None,
        }
    )

    steps = {
        "eval_observability": {
            "exists": eval_exists,
            "passed": eval_ok if eval_exists else None,
            "repeats": eval_report.get("repeats") if eval_exists else None,
            "sample_size": eval_report.get("sample_size") if eval_exists else None,
            "avg_strategy_delta": eval_report.get("avg_strategy_delta") if eval_exists else None,
            "avg_delivery_delta": eval_report.get("avg_delivery_delta") if eval_exists else None,
            "regressions": eval_report.get("regressions") if eval_exists else None,
            "progress_entries": progress_order_summary["progress_entries"],
            "progress_entries_with_order": progress_order_summary["progress_entries_with_order"],
            "progress_entries_with_injected_order": progress_order_summary["progress_entries_with_injected_order"],
            "progress_order_coverage": progress_order_summary["progress_order_coverage"],
            "entries_with_failure_avoid": progress_order_summary["entries_with_failure_avoid"],
            "avg_failure_avoid_hit_rate": progress_order_summary["avg_failure_avoid_hit_rate"],
            "entries_with_memory_failure_hint": progress_order_summary["entries_with_memory_failure_hint"],
            "entries_with_memory_digest_hint": progress_order_summary["entries_with_memory_digest_hint"],
            "entries_with_memory_decision_hint": progress_order_summary["entries_with_memory_decision_hint"],
            "avg_memory_failure_hint_hit_rate": progress_order_summary["avg_memory_failure_hint_hit_rate"],
            "avg_memory_digest_hint_hit_rate": progress_order_summary["avg_memory_digest_hint_hit_rate"],
            "avg_memory_decision_hint_hit_rate": progress_order_summary["avg_memory_decision_hint_hit_rate"],
        },
        "merge_gate": {
            "exists": merge_exists,
            "passed": merge_ok if merge_exists else None,
            "step_count": len(merge_report.get("steps", [])) if merge_exists else None,
            "sandbox_trend": _extract_sandbox_trend_summary(merge_report),
        },
        "release_guard": {
            "exists": release_exists,
            "passed": release_ok if release_exists else None,
            "step_count": len(release_report.get("steps", [])) if release_exists else None,
        },
    }

    ready_for_release = bool(eval_ok and merge_ok and release_ok)
    missing_reports = [
        name
        for name, exists in [
            ("eval_observability_report.json", eval_exists),
            ("merge_gate_report.json", merge_exists),
            ("release_guard_report.json", release_exists),
        ]
        if not exists
    ]

    return {
        "timestamp": time.time(),
        "ready_for_release": ready_for_release,
        "missing_reports": missing_reports,
        "steps": steps,
    }


def print_overview(overview: dict[str, Any]) -> None:
    print("=" * 60)
    print("Guard Overview")
    print("=" * 60)
    print(f"ready_for_release={overview['ready_for_release']}")
    if overview["missing_reports"]:
        print(f"missing_reports={overview['missing_reports']}")

    steps = overview["steps"]
    eval_step = steps["eval_observability"]
    print(
        "[eval] "
        f"exists={eval_step['exists']} "
        f"passed={eval_step['passed']} "
        f"repeats={eval_step['repeats']} "
        f"sample_size={eval_step['sample_size']} "
        f"avg_strategy_delta={eval_step['avg_strategy_delta']} "
        f"avg_delivery_delta={eval_step['avg_delivery_delta']} "
        f"progress_entries={eval_step['progress_entries']} "
        f"progress_injected_entries={eval_step['progress_entries_with_injected_order']} "
        f"progress_order_coverage={eval_step['progress_order_coverage']} "
        f"failure_avoid_entries={eval_step['entries_with_failure_avoid']} "
        f"failure_avoid_hit_rate={eval_step['avg_failure_avoid_hit_rate']} "
        f"memory_failure_hint_entries={eval_step['entries_with_memory_failure_hint']} "
        f"memory_digest_hint_entries={eval_step['entries_with_memory_digest_hint']} "
        f"memory_decision_hint_entries={eval_step['entries_with_memory_decision_hint']}"
    )
    print(
        "[merge] "
        f"exists={steps['merge_gate']['exists']} "
        f"passed={steps['merge_gate']['passed']} "
        f"step_count={steps['merge_gate']['step_count']}"
    )
    sandbox_trend = steps["merge_gate"].get("sandbox_trend", {}) or {}
    trend_prefix = "[RED] " if sandbox_trend.get("is_red") else ""
    print(
        f"{trend_prefix}[sandbox-trend] "
        f"status={sandbox_trend.get('status')} "
        f"slow_scene_count={sandbox_trend.get('slow_scene_count')} "
        f"is_red={sandbox_trend.get('is_red')}"
    )
    slow_scene_details = sandbox_trend.get("slow_scene_details", []) or []
    for detail in slow_scene_details:
        if not isinstance(detail, dict):
            continue
        triage_hint = detail.get("triage_hint", {}) or {}
        print(
            "[sandbox-trend-detail] "
            f"scene={detail.get('scene')} "
            f"current={detail.get('current_duration_seconds')} "
            f"baseline={detail.get('baseline_duration_seconds')} "
            f"recent_samples={detail.get('recent_samples_seconds')}"
        )
        if isinstance(triage_hint, dict) and triage_hint.get("probe_order"):
            print(
                "[sandbox-trend-triage] "
                f"scene={detail.get('scene')} "
                f"probe_order={triage_hint.get('probe_order')} "
                f"why={triage_hint.get('why')}"
            )
    print(
        "[release] "
        f"exists={steps['release_guard']['exists']} "
        f"passed={steps['release_guard']['passed']} "
        f"step_count={steps['release_guard']['step_count']}"
    )


def save_overview(overview: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(overview, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="门禁三件套总览")
    parser.add_argument("--eval-report", default=str(DEFAULT_EVAL_REPORT))
    parser.add_argument("--merge-report", default=str(DEFAULT_MERGE_REPORT))
    parser.add_argument("--release-report", default=str(DEFAULT_RELEASE_REPORT))
    parser.add_argument("--output", default=str(DEFAULT_OVERVIEW_OUTPUT))
    args = parser.parse_args()

    eval_report = _read_json(Path(args.eval_report))
    merge_report = _read_json(Path(args.merge_report))
    release_report = _read_json(Path(args.release_report))

    overview = build_overview(eval_report, merge_report, release_report)
    print_overview(overview)
    save_overview(overview, Path(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
