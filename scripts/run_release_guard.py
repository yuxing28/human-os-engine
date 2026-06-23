"""
Human-OS Engine - 一键发布门禁脚本

流程：
1. 先跑评测可观测日检（生成最新 eval_observability_report.json）
2. 再跑合并闸门（包含确定性测试 + 评测报告门禁）

用法：
    python scripts/run_release_guard.py
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RELEASE_OUTPUT_PATH = PROJECT_ROOT / "data" / "release_guard_report.json"
DEFAULT_MERGE_GATE_OUTPUT_PATH = PROJECT_ROOT / "data" / "merge_gate_report.json"


def build_eval_command(repeats: int, limit: int) -> list[str]:
    return [
        sys.executable,
        "scripts/testing/eval_observability_daily_check.py",
        "--repeats",
        str(repeats),
        "--limit",
        str(limit),
    ]


def build_gate_command(args: argparse.Namespace) -> list[str]:
    cmd = [
        sys.executable,
        "scripts/run_merge_gate.py",
        "--gate-output-path",
        str(args.merge_gate_output_path),
        "--max-report-age-hours",
        str(args.max_report_age_hours),
        "--min-repeats",
        str(args.min_repeats),
        "--min-sample-size",
        str(args.min_sample_size),
        "--min-strategy-delta",
        str(args.min_strategy_delta),
        "--min-delivery-delta",
        str(args.min_delivery_delta),
        "--max-regressions",
        str(args.max_regressions),
        "--max-failure-codes",
        str(args.max_failure_codes),
        "--min-progress-entries",
        str(args.min_progress_entries),
        "--min-progress-order-coverage",
        str(args.min_progress_order_coverage),
        "--min-failure-avoid-entries",
        str(args.min_failure_avoid_entries),
        "--min-failure-avoid-hit-rate",
        str(args.min_failure_avoid_hit_rate),
        "--min-memory-hint-entries",
        str(args.min_memory_hint_entries),
        "--min-memory-decision-hit-rate",
        str(args.min_memory_decision_hit_rate),
        "--sandbox-seed",
        str(args.sandbox_seed),
        "--sandbox-rounds",
        str(args.sandbox_rounds),
        "--max-sandbox-scene-duration-seconds",
        str(args.max_sandbox_scene_duration_seconds),
        "--sandbox-performance-history-path",
        str(args.sandbox_performance_history_path),
        "--sandbox-trend-window",
        str(args.sandbox_trend_window),
        "--sandbox-slowdown-ratio",
        str(args.sandbox_slowdown_ratio),
        "--sandbox-slowdown-absolute-seconds",
        str(args.sandbox_slowdown_absolute_seconds),
    ]
    if args.max_sandbox_scene_duration_seconds_by_scene:
        cmd.extend(
            [
                "--max-sandbox-scene-duration-seconds-by-scene",
                str(args.max_sandbox_scene_duration_seconds_by_scene),
            ]
        )
    if args.skip_report_gate:
        cmd.append("--skip-report-gate")
    if args.skip_doc_gate:
        cmd.append("--skip-doc-gate")
    if args.skip_sandbox_gate:
        cmd.append("--skip-sandbox-gate")
    if args.strict_progress_order_gate:
        cmd.append("--strict-progress-order-gate")
    if args.strict_failure_avoid_gate:
        cmd.append("--strict-failure-avoid-gate")
    if args.strict_memory_hint_gate:
        cmd.append("--strict-memory-hint-gate")
    if args.strict_sandbox_performance_gate:
        cmd.append("--strict-sandbox-performance-gate")
    if args.strict_sandbox_performance_trend_gate:
        cmd.append("--strict-sandbox-performance-trend-gate")
    return cmd


def _init_release_report() -> dict[str, Any]:
    return {
        "timestamp": time.time(),
        "overall_passed": None,
        "steps": [],
    }


def _record_release_step(
    report: dict[str, Any],
    *,
    name: str,
    status: str,
    exit_code: int | None,
    command: list[str] | None = None,
    reason: str = "",
) -> None:
    report["steps"].append(
        {
            "name": name,
            "status": status,  # pass/fail/skip
            "exit_code": exit_code,
            "command": command or [],
            "reason": reason,
        }
    )


def _save_release_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _decode_output(raw: bytes) -> str:
    if not raw:
        return ""
    for encoding in ("utf-8", "gbk"):
        try:
            text = raw.decode(encoding)
            return text.replace("\r\n", "\n").replace("\r", "\n")
        except UnicodeDecodeError:
            continue
    text = raw.decode("utf-8", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def run_command(cmd: list[str]) -> int:
    printable = " ".join(cmd)
    print(f"\n[RUN] {printable}")
    result = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=False,
    )
    stdout_text = _decode_output(result.stdout)
    stderr_text = _decode_output(result.stderr)
    if stdout_text:
        print(stdout_text, end="" if stdout_text.endswith("\n") else "\n")
    if stderr_text:
        print(stderr_text, end="" if stderr_text.endswith("\n") else "\n", file=sys.stderr)
    return int(result.returncode)


def main() -> int:
    parser = argparse.ArgumentParser(description="一键发布门禁")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--skip-eval", action="store_true")
    parser.add_argument("--skip-report-gate", action="store_true")
    parser.add_argument("--skip-doc-gate", action="store_true")
    parser.add_argument("--skip-sandbox-gate", action="store_true")
    parser.add_argument("--merge-gate-output-path", default=str(DEFAULT_MERGE_GATE_OUTPUT_PATH))
    parser.add_argument("--release-output-path", default=str(DEFAULT_RELEASE_OUTPUT_PATH))
    parser.add_argument("--max-report-age-hours", type=float, default=36.0)
    parser.add_argument("--min-repeats", type=int, default=3)
    parser.add_argument("--min-sample-size", type=int, default=8)
    parser.add_argument("--min-strategy-delta", type=float, default=-0.2)
    parser.add_argument("--min-delivery-delta", type=float, default=-0.2)
    parser.add_argument("--max-regressions", type=int, default=0)
    parser.add_argument("--max-failure-codes", type=int, default=0)
    parser.add_argument("--min-progress-entries", type=int, default=2)
    parser.add_argument("--min-progress-order-coverage", type=float, default=0.5)
    parser.add_argument("--strict-progress-order-gate", action="store_true")
    parser.add_argument("--min-failure-avoid-entries", type=int, default=2)
    parser.add_argument("--min-failure-avoid-hit-rate", type=float, default=0.1)
    parser.add_argument("--strict-failure-avoid-gate", action="store_true")
    parser.add_argument("--min-memory-hint-entries", type=int, default=2)
    parser.add_argument("--min-memory-decision-hit-rate", type=float, default=0.1)
    parser.add_argument("--strict-memory-hint-gate", action="store_true")
    parser.add_argument("--sandbox-seed", type=int, default=20260410)
    parser.add_argument("--sandbox-rounds", type=int, default=1)
    parser.add_argument("--max-sandbox-scene-duration-seconds", type=float, default=45.0)
    parser.add_argument("--max-sandbox-scene-duration-seconds-by-scene", type=str, default="")
    parser.add_argument(
        "--sandbox-performance-history-path",
        type=str,
        default=str(PROJECT_ROOT / "data" / "sandbox_performance_history.jsonl"),
    )
    parser.add_argument("--sandbox-trend-window", type=int, default=5)
    parser.add_argument("--sandbox-slowdown-ratio", type=float, default=0.2)
    parser.add_argument("--sandbox-slowdown-absolute-seconds", type=float, default=5.0)
    parser.add_argument("--strict-sandbox-performance-gate", action="store_true")
    parser.add_argument("--strict-sandbox-performance-trend-gate", action="store_true")
    args = parser.parse_args()

    print("=" * 60)
    print("[ReleaseGuard] Human-OS 一键发布门禁")
    print("=" * 60)

    release_report = _init_release_report()

    if not args.skip_eval:
        eval_cmd = build_eval_command(args.repeats, args.limit)
        eval_code = run_command(eval_cmd)
        if eval_code != 0:
            _record_release_step(
                release_report,
                name="评测可观测日检",
                status="fail",
                exit_code=eval_code,
                command=eval_cmd,
                reason="评测可观测日检失败，发布门禁中止",
            )
            release_report["overall_passed"] = False
            _save_release_report(release_report, Path(args.release_output_path))
            print(f"[ReleaseReport] 已写入: {args.release_output_path}")
            print("\n[FAIL] 评测可观测日检失败，发布门禁中止")
            return eval_code
        _record_release_step(
            release_report,
            name="评测可观测日检",
            status="pass",
            exit_code=eval_code,
            command=eval_cmd,
        )
    else:
        print("\n[SKIP] 已跳过评测日检（--skip-eval）")
        _record_release_step(
            release_report,
            name="评测可观测日检",
            status="skip",
            exit_code=None,
            reason="跳过（--skip-eval）",
        )

    gate_cmd = build_gate_command(args)
    gate_code = run_command(gate_cmd)
    if gate_code != 0:
        _record_release_step(
            release_report,
            name="合并闸门",
            status="fail",
            exit_code=gate_code,
            command=gate_cmd,
            reason="合并闸门失败",
        )
        release_report["overall_passed"] = False
        _save_release_report(release_report, Path(args.release_output_path))
        print(f"[ReleaseReport] 已写入: {args.release_output_path}")
        print("\n[FAIL] 合并闸门失败")
        return gate_code
    _record_release_step(
        release_report,
        name="合并闸门",
        status="pass",
        exit_code=gate_code,
        command=gate_cmd,
    )

    release_report["overall_passed"] = True
    _save_release_report(release_report, Path(args.release_output_path))
    print(f"[ReleaseReport] 已写入: {args.release_output_path}")
    print("\n[PASS] 一键发布门禁通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
