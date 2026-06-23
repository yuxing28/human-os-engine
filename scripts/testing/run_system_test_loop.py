"""
系统测试总控脚本

作用：
1) 先做 LLM 配置体检
2) 再跑记忆 / 场景 / 主链回归
3) 按 quick/full/night 三档执行
4) 输出一份统一总报告，便于自动化持续跑
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _run_step(name: str, cmd: list[str], timeout: int) -> dict:
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=False,
        timeout=timeout,
    )
    stdout_text = _decode_output(proc.stdout)
    stderr_text = _decode_output(proc.stderr)
    return {
        "name": name,
        "command": cmd,
        "returncode": int(proc.returncode),
        "elapsed_seconds": round(time.time() - started, 2),
        "stdout_tail": stdout_text.strip().splitlines()[-10:],
        "stderr_tail": stderr_text.strip().splitlines()[-10:],
    }


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


def _build_plan(profile: str, strict_config: bool) -> list[dict]:
    py = sys.executable
    cfg_cmd = [py, "scripts/testing/llm_config_check.py"]
    if strict_config:
        cfg_cmd.append("--strict")

    base = [
        {"name": "llm_config_check", "cmd": cfg_cmd, "timeout": 120},
        {
            "name": "standardization_daily_loop",
            "cmd": [py, "scripts/testing/run_standardization_daily_loop.py"],
            "timeout": 1800,
        },
        {
            "name": "memory_observability",
            "cmd": [py, "scripts/testing/memory_observability_daily_check.py", "--repeats", "1", "--limit", "12"],
            "timeout": 1800,
        },
        {
            "name": "mainline_capability",
            "cmd": [py, "scripts/testing/mainline_capability_check.py", "--scene", "all"],
            "timeout": 1200,
        },
    ]

    if profile == "quick":
        base.append(
            {
                "name": "large_cycle_smoke",
                "cmd": [py, "scripts/testing/run_large_cycle_loop.py", "--smoke"],
                "timeout": 1800,
            }
        )
        return base

    if profile == "full":
        base.extend(
            [
                {
                    "name": "pytest_core_pack",
                    "cmd": [
                        py,
                        "-m",
                        "pytest",
                        "tests/test_scene_routing.py",
                        "tests/test_step1_memory_context.py",
                        "tests/test_step6_step8_memory_flow.py",
                        "tests/test_memory_write_integration.py",
                        "-q",
                        "--no-cov",
                    ],
                    "timeout": 2400,
                },
                {
                    "name": "large_cycle_smoke",
                    "cmd": [py, "scripts/testing/run_large_cycle_loop.py", "--smoke"],
                    "timeout": 2400,
                },
            ]
        )
        return base

    # night
    base.extend(
        [
            {
                "name": "pytest_core_pack",
                "cmd": [
                    py,
                    "-m",
                    "pytest",
                    "tests/test_scene_routing.py",
                    "tests/test_step1_memory_context.py",
                    "tests/test_step6_step8_memory_flow.py",
                    "tests/test_memory_write_integration.py",
                    "tests/test_sandbox_signal_metrics.py",
                    "tests/test_sandbox_insight_pipeline.py",
                    "-q",
                    "--no-cov",
                ],
                "timeout": 3600,
            },
            {
                "name": "large_cycle_full",
                "cmd": [py, "scripts/testing/run_large_cycle_loop.py"],
                "timeout": 21600,
            },
        ]
    )
    return base


def _save_report(report: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="系统测试总控（quick/full/night）")
    parser.add_argument("--profile", choices=["quick", "full", "night"], default="quick")
    parser.add_argument("--strict-config", action="store_true", help="严格模式：要求 DEEPSEEK 主 key 存在")
    parser.add_argument(
        "--output-path",
        default="",
        help="总报告输出路径，默认 data/system_test_reports/system_test_<时间>.json",
    )
    args = parser.parse_args()

    plan = _build_plan(profile=args.profile, strict_config=args.strict_config)
    started = time.time()
    started_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output_path:
        output_path = Path(args.output_path)
    else:
        output_path = PROJECT_ROOT / "data" / "system_test_reports" / f"system_test_{started_at}.json"

    steps: list[dict] = []
    overall_ok = True

    print(f"=== 系统测试启动：{args.profile} ===")
    for step in plan:
        print(f"\n[RUN] {step['name']}")
        print(" ".join(step["cmd"]))
        try:
            result = _run_step(step["name"], step["cmd"], timeout=step["timeout"])
        except subprocess.TimeoutExpired:
            result = {
                "name": step["name"],
                "command": step["cmd"],
                "returncode": 124,
                "elapsed_seconds": step["timeout"],
                "stdout_tail": [],
                "stderr_tail": [f"timeout>{step['timeout']}s"],
            }

        steps.append(result)
        if result["returncode"] != 0:
            overall_ok = False
            print(f"[FAIL] {step['name']} rc={result['returncode']}")
            break
        print(f"[OK] {step['name']} ({result['elapsed_seconds']}s)")

    report = {
        "timestamp": time.time(),
        "profile": args.profile,
        "strict_config": bool(args.strict_config),
        "elapsed_seconds": round(time.time() - started, 2),
        "overall_ok": overall_ok and len(steps) == len(plan),
        "total_steps": len(plan),
        "completed_steps": len(steps),
        "steps": steps,
    }
    _save_report(report, output_path)

    print("\n=== 系统测试汇总 ===")
    print(f"profile={report['profile']}")
    print(f"overall_ok={report['overall_ok']}")
    print(f"completed_steps={report['completed_steps']}/{report['total_steps']}")
    print(f"report={output_path}")
    return 0 if report["overall_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
