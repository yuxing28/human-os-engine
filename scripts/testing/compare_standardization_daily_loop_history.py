"""
标准化日常循环历史对比

用途很简单：把最近两次结果放在一起看，别只看单次。
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = PROJECT_ROOT / "data" / "standardization_daily_loop_reports"


def _load_reports() -> list[dict]:
    if not ARCHIVE_DIR.exists():
        return []

    reports: list[dict] = []
    for path in sorted(ARCHIVE_DIR.glob("standardization_daily_loop_report_*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        reports.append(
            {
                "path": path,
                "started_at": payload.get("started_at", ""),
                "all_passed": payload.get("all_passed", False),
                "elapsed_seconds": payload.get("elapsed_seconds"),
                "results": payload.get("results", []),
            }
        )
    return reports


def _summarize(report: dict) -> dict:
    group_map = {item.get("label", item.get("name", "unknown")): item for item in report.get("results", [])}
    return {
        "path": report["path"].name,
        "all_passed": report.get("all_passed", False),
        "elapsed_seconds": report.get("elapsed_seconds"),
        "output": group_map.get("输出", {}).get("passed"),
        "memory": group_map.get("记忆", {}).get("passed"),
        "evolution": group_map.get("进化/场景加载", {}).get("passed"),
    }


def _delta(current: int | float | None, previous: int | float | None) -> str:
    if current is None or previous is None:
        return "NA"
    diff = current - previous
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff}"


def main() -> int:
    reports = _load_reports()
    if len(reports) < 2:
        print("历史归档还不够两次，先跑两轮再来对比。")
        return 0

    latest = _summarize(reports[0])
    previous = _summarize(reports[1])

    print("最近两次标准化日常循环对比：")
    print(f"- 最新: {latest['path']} | {'OK' if latest['all_passed'] else 'FAIL'} | {latest['elapsed_seconds']}s")
    print(f"- 上次: {previous['path']} | {'OK' if previous['all_passed'] else 'FAIL'} | {previous['elapsed_seconds']}s")
    print("差异：")
    print(f"- 输出: {_delta(latest['output'], previous['output'])}")
    print(f"- 记忆: {_delta(latest['memory'], previous['memory'])}")
    print(f"- 进化/场景加载: {_delta(latest['evolution'], previous['evolution'])}")
    print(f"- 总耗时: {_delta(latest['elapsed_seconds'], previous['elapsed_seconds'])}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
