"""
标准化日常循环

默认先跑三组回归：
1. 输出
2. 记忆
3. 进化 / 场景加载

这不是用来“炫流程”的，而是让标准化阶段以后每次都能先跑一遍，再决定要不要继续改。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_REPORT_PATH = PROJECT_ROOT / "data" / "standardization_daily_loop_report.json"
REPORT_PATH = DEFAULT_REPORT_PATH
ARCHIVE_DIR = PROJECT_ROOT / "data" / "standardization_daily_loop_reports"

GROUPS = [
    {
        "name": "output",
        "label": "输出",
        "tests": [
            "tests/test_step8_stability_templates.py",
            "tests/test_step8_output_layer.py",
            "tests/test_chain_invariants.py",
        ],
    },
    {
        "name": "memory",
        "label": "记忆",
        "tests": [
            "tests/test_memory_manager_core.py",
            "tests/test_step9_memory_write.py",
        ],
    },
    {
        "name": "evolution",
        "label": "进化/场景加载",
        "tests": [
            "tests/test_scene_loader.py",
            "tests/test_scene_evolver.py",
            "tests/test_step6_routing.py",
        ],
    },
]


def _extract_passed_count(stdout: str) -> int | None:
    matches = re.findall(r"(\d+)\s+passed", stdout)
    if not matches:
        return None
    try:
        return int(matches[-1])
    except ValueError:
        return None


def _run_pytest(tests: list[str]) -> tuple[int, str, str]:
    cmd = [sys.executable, "-m", "pytest", *tests, "-q", "--no-cov"]
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def run_daily_loop() -> dict:
    started = time.time()
    started_at = datetime.now(timezone.utc).isoformat()
    results: list[dict] = []

    for group in GROUPS:
        print(f"\n=== {group['label']} ===")
        group_started = time.time()
        code, stdout, stderr = _run_pytest(group["tests"])
        passed = _extract_passed_count(stdout)
        elapsed = round(time.time() - group_started, 2)

        if stdout.strip():
            print(stdout.rstrip())
        if stderr.strip():
            print(stderr.rstrip(), file=sys.stderr)

        if code == 0:
            print(f"[OK] {group['label']} 通过")
        else:
            print(f"[FAIL] {group['label']} 未通过")

        results.append(
            {
                "name": group["name"],
                "label": group["label"],
                "tests": group["tests"],
                "returncode": code,
                "passed": passed,
                "elapsed_seconds": elapsed,
                "stdout_tail": stdout.strip().splitlines()[-5:] if stdout.strip() else [],
                "stderr_tail": stderr.strip().splitlines()[-5:] if stderr.strip() else [],
            }
        )

    report = {
        "timestamp": time.time(),
        "started_at": started_at,
        "elapsed_seconds": round(time.time() - started, 2),
        "results": results,
        "all_passed": all(item["returncode"] == 0 for item in results),
    }
    return report


def save_report(report: dict) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {REPORT_PATH}")

    if REPORT_PATH == DEFAULT_REPORT_PATH:
        started_at = report.get("started_at")
        if started_at:
            archived_at = datetime.fromisoformat(started_at).strftime("%Y%m%d_%H%M%S_%f")
        else:
            archived_at = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        archive_path = ARCHIVE_DIR / f"standardization_daily_loop_report_{archived_at}.json"
        archive_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"归档报告已保存: {archive_path}")


def main() -> int:
    global REPORT_PATH
    parser = argparse.ArgumentParser(description="标准化日常循环")
    parser.add_argument("--report-path", default=str(REPORT_PATH))
    args = parser.parse_args()

    REPORT_PATH = Path(args.report_path)

    report = run_daily_loop()
    print("\n=== 标准化日常循环汇总 ===")
    for item in report["results"]:
        label = item["label"]
        if item["returncode"] == 0:
            suffix = f"{item['passed']} passed" if item["passed"] is not None else "OK"
            if item.get("elapsed_seconds") is not None:
                suffix = f"{suffix} in {item['elapsed_seconds']}s"
            print(f"{label}: {suffix}")
        else:
            print(f"{label}: FAIL")
    print(f"all_passed={report['all_passed']}")
    save_report(report)
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
