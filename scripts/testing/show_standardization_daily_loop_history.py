"""
标准化日常循环历史查看

用途很简单：快速看最近几次日常循环的结果，不用手动进目录翻文件。
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
                "summary": [
                    f"{item.get('label', item.get('name', 'unknown'))}: {item.get('passed', 'NA')} passed"
                    for item in payload.get("results", [])
                ],
            }
        )
    return reports


def main() -> int:
    reports = _load_reports()
    if not reports:
        print("还没有找到历史归档。")
        return 0

    print("最近的标准化日常循环历史：")
    for item in reports[:5]:
        status = "OK" if item["all_passed"] else "FAIL"
        elapsed = item["elapsed_seconds"]
        elapsed_text = f"{elapsed}s" if elapsed is not None else "NA"
        print(f"- {item['path'].name} | {status} | {elapsed_text}")
        for line in item["summary"]:
            print(f"  - {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
