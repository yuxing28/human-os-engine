"""
大循环大量测试

这条线不是日常锁门回归的替代，而是更重一点的长期观察：
1. 先跑一轮标准化锁门
2. 再跑更大样本的多场景基线
3. 再跑更长链路的连续样本
4. 最后补一轮边界压力混合包

重点不是“有没有一句话不好看”，而是看跑多了以后会不会变形。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from simulation.sandbox_insight_pipeline import (
    analyze_large_cycle_report,
    build_review_cards,
    build_validation_queue,
    save_insight_report,
    save_review_cards,
    save_validation_queue,
)

DEFAULT_REPORT_PATH = PROJECT_ROOT / "data" / "large_cycle_report.json"
DEFAULT_INSIGHT_PATH = PROJECT_ROOT / "data" / "sandbox_insight_report.json"
DEFAULT_QUEUE_PATH = PROJECT_ROOT / "data" / "sandbox_validation_queue.json"
DEFAULT_REVIEW_CARDS_PATH = PROJECT_ROOT / "data" / "sandbox_review_cards.md"
ARCHIVE_DIR = PROJECT_ROOT / "data" / "large_cycle_reports"
PARTS_DIR = PROJECT_ROOT / "data" / "large_cycle_parts"


def _python_cmd() -> str:
    return sys.executable


def _phase_plan(smoke: bool) -> list[dict]:
    if smoke:
        return [
            {
                "name": "gate",
                "label": "标准化锁门",
                "kind": "standardization",
                "timeout": 900,
            },
            {
                "name": "sandbox_probe",
                "label": "沙盒短探针",
                "kind": "sandbox",
                "timeout": 600,
                "scenes": ["management"],
                "conversations": 1,
                "rounds": 2,
            },
        ]

    return [
        {
            "name": "gate",
            "label": "标准化锁门",
            "kind": "standardization",
            "timeout": 1200,
        },
        {
            "name": "multi_scene",
            "label": "多场景基线",
            "kind": "sandbox",
            "timeout": 7200,
            "scenes": ["sales", "management", "negotiation", "emotion"],
            "conversations": 4,
            "rounds": 10,
        },
        {
            "name": "long_chain",
            "label": "长链路连续样本",
            "kind": "sandbox",
            "timeout": 7200,
            "scenes": ["management", "emotion"],
            "conversations": 3,
            "rounds": 14,
        },
        {
            "name": "boundary_mix",
            "label": "边界压力混合包",
            "kind": "sandbox",
            "timeout": 5400,
            "scenes": ["sales", "negotiation", "emotion"],
            "conversations": 2,
            "rounds": 12,
        },
    ]


def _run_command(cmd: list[str], timeout: int) -> tuple[int, str, str, float, bool]:
    started = time.time()
    stdout_path: Path | None = None
    stderr_path: Path | None = None

    def _read_text(path: Path | None) -> str:
        if not path or not path.exists():
            return ""
        return path.read_text(encoding="utf-8", errors="replace")

    try:
        # Windows 上用 PIPE 捕获长时间子进程输出时，偶发会因为继承管道句柄导致父进程卡在收尾。
        # 这里改成临时文件承接输出，子进程结束后父进程只读文件，避免 smoke 跑完却不产报告。
        with tempfile.NamedTemporaryFile("w+", encoding="utf-8", delete=False) as stdout_file, tempfile.NamedTemporaryFile(
            "w+", encoding="utf-8", delete=False
        ) as stderr_file:
            stdout_path = Path(stdout_file.name)
            stderr_path = Path(stderr_file.name)
            proc = subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            try:
                code = proc.wait(timeout=timeout)
                timed_out = False
            except subprocess.TimeoutExpired:
                proc.kill()
                code = 124
                timed_out = True

        elapsed = round(time.time() - started, 2)
        return code, _read_text(stdout_path), _read_text(stderr_path), elapsed, timed_out
    finally:
        for path in (stdout_path, stderr_path):
            if path and path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass


def _latest_new_summary_file(before: set[Path]) -> Path | None:
    after = set((PROJECT_ROOT / "data").glob("sandbox_50x20_*.json"))
    new_files = [
        item
        for item in after - before
        if item.name.startswith("sandbox_50x20_") and not item.name.startswith("sandbox_50x20_detail_")
    ]
    new_files = sorted(new_files, key=lambda item: item.stat().st_mtime, reverse=True)
    return new_files[0] if new_files else None


def _latest_new_detail_file(before: set[Path]) -> Path | None:
    after = set((PROJECT_ROOT / "data").glob("sandbox_50x20_detail_*.json"))
    new_files = sorted(after - before, key=lambda item: item.stat().st_mtime, reverse=True)
    return new_files[0] if new_files else None


def _summarize_standardization(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    result_map = {item["label"]: item for item in payload.get("results", [])}
    return {
        "report_path": str(path),
        "all_passed": payload.get("all_passed", False),
        "elapsed_seconds": payload.get("elapsed_seconds"),
        "output_passed": result_map.get("输出", {}).get("passed"),
        "memory_passed": result_map.get("记忆", {}).get("passed"),
        "evolution_passed": result_map.get("进化/场景加载", {}).get("passed"),
    }


def _summarize_sandbox(path: Path, detail_path: Path | None) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    global_block = payload.get("global", {})
    scene_block = payload.get("scenes", {})
    return {
        "report_path": str(path),
        "detail_path": str(detail_path) if detail_path else None,
        "elapsed_seconds": payload.get("total_elapsed_seconds"),
        "total_conversations": global_block.get("total_conversations"),
        "total_rounds": global_block.get("total_rounds"),
        "success_rate": global_block.get("success_rate"),
        "failure_rate": global_block.get("failure_rate"),
        "timeout_rate": global_block.get("timeout_rate"),
        "avg_rounds_per_conversation": global_block.get("avg_rounds_per_conversation"),
        "total_violations": global_block.get("total_violations"),
        "scenes": {
            scene_id: {
                "success": item.get("success"),
                "failure": item.get("failure"),
                "timeout": item.get("timeout"),
                "violations": item.get("total_violations"),
                "signal_metrics": item.get("signal_metrics", {}),
                "action_loop_metrics": item.get("action_loop_metrics", {}),
                "disturbance_metrics": item.get("disturbance_metrics", {}),
                "disturbance_response_metrics": item.get("disturbance_response_metrics", {}),
                "disturbance_recovery_metrics": item.get("disturbance_recovery_metrics", {}),
            }
            for scene_id, item in scene_block.items()
        },
        "signal_metrics": global_block.get("signal_metrics", {}),
        "world_state_metrics": global_block.get("world_state_metrics", {}),
        "action_loop_metrics": global_block.get("action_loop_metrics", {}),
        "disturbance_metrics": global_block.get("disturbance_metrics", {}),
        "disturbance_response_metrics": global_block.get("disturbance_response_metrics", {}),
        "disturbance_recovery_metrics": global_block.get("disturbance_recovery_metrics", {}),
        "world_state_transition_metrics": global_block.get("world_state_transition_metrics", {}),
    }


def _load_recent_archives(limit: int = 2) -> list[dict]:
    if not ARCHIVE_DIR.exists():
        return []

    reports = []
    for path in sorted(ARCHIVE_DIR.glob("large_cycle_report_*.json"), reverse=True)[:limit]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        payload["_path"] = str(path)
        reports.append(payload)
    return reports


def _consecutive_stable_rounds(current_all_passed: bool) -> int:
    if not current_all_passed:
        return 0

    stable = 1
    for previous in _load_recent_archives():
        if previous.get("all_passed"):
            stable += 1
        else:
            break
    return stable


def _round_rate(value: float | int | None) -> float:
    if value is None:
        return 0.0
    return round(float(value), 1)


def _build_scene_insights(phase_results: list[dict]) -> dict:
    scene_totals: dict[str, dict] = {}

    for phase in phase_results:
        if phase.get("kind") != "sandbox":
            continue
        summary = phase.get("summary") or {}
        for scene_id, scene_data in (summary.get("scenes") or {}).items():
            bucket = scene_totals.setdefault(
                scene_id,
                {
                    "phase_names": [],
                    "commitment_rates": [],
                    "focus_rates": [],
                    "disturbance_rates": [],
                    "recovery_commitment_rates": [],
                    "recovery_focus_rates": [],
                    "progress_counts": {},
                    "disturbed_progress_counts": {},
                    "recovery_progress_counts": {},
                },
            )
            bucket["phase_names"].append(phase.get("name"))

            action_loop = scene_data.get("action_loop_metrics") or {}
            disturbance = scene_data.get("disturbance_metrics") or {}
            disturbed = scene_data.get("disturbance_response_metrics") or {}
            recovery = scene_data.get("disturbance_recovery_metrics") or {}

            bucket["commitment_rates"].append(float(action_loop.get("commitment_rate") or 0.0))
            bucket["focus_rates"].append(float(action_loop.get("focus_rate") or 0.0))
            bucket["disturbance_rates"].append(float(disturbance.get("disturbance_rate") or 0.0))
            bucket["recovery_commitment_rates"].append(float(recovery.get("recovery_commitment_rate") or 0.0))
            bucket["recovery_focus_rates"].append(float(recovery.get("recovery_focus_rate") or 0.0))

            for source_key, target_key in (
                ("action_loop_state_counts", "progress_counts"),
                ("disturbed_progress_counts", "disturbed_progress_counts"),
                ("recovery_progress_counts", "recovery_progress_counts"),
            ):
                source = (
                    action_loop.get(source_key)
                    if source_key == "action_loop_state_counts"
                    else disturbed.get(source_key)
                    if source_key == "disturbed_progress_counts"
                    else recovery.get(source_key)
                ) or {}
                for label, count in source.items():
                    bucket[target_key][label] = bucket[target_key].get(label, 0) + int(count)

    insights: dict[str, dict] = {}
    scene_scores: list[tuple[str, float]] = []
    conservative_scenes: list[str] = []

    for scene_id, bucket in scene_totals.items():
        phase_count = max(len(bucket["phase_names"]), 1)
        avg_commitment = _round_rate(sum(bucket["commitment_rates"]) / phase_count)
        avg_focus = _round_rate(sum(bucket["focus_rates"]) / phase_count)
        avg_disturbance = _round_rate(sum(bucket["disturbance_rates"]) / phase_count)
        avg_recovery_commitment = _round_rate(sum(bucket["recovery_commitment_rates"]) / phase_count)
        avg_recovery_focus = _round_rate(sum(bucket["recovery_focus_rates"]) / phase_count)

        progress_counts = bucket["progress_counts"]
        observe_count = 0
        for label, count in progress_counts.items():
            if "观察" in label:
                observe_count += int(count)
        progress_total = sum(int(count) for count in progress_counts.values()) or 1
        observe_share = _round_rate(observe_count * 100 / progress_total)

        score = round(
            avg_commitment * 0.3
            + avg_focus * 0.3
            + avg_recovery_commitment * 0.2
            + avg_recovery_focus * 0.2
            - observe_share * 0.1,
            1,
        )
        scene_scores.append((scene_id, score))

        if observe_share >= 50.0 and avg_commitment <= 40.0 and avg_focus <= 40.0:
            status = "偏保守"
            conservative_scenes.append(scene_id)
        elif avg_recovery_focus >= 50.0 or avg_recovery_commitment >= 50.0:
            status = "恢复力较强"
        elif avg_commitment >= 50.0 and avg_focus >= 50.0:
            status = "推进较稳"
        else:
            status = "继续观察"

        insights[scene_id] = {
            "status": status,
            "avg_commitment_rate": avg_commitment,
            "avg_focus_rate": avg_focus,
            "avg_disturbance_rate": avg_disturbance,
            "avg_recovery_commitment_rate": avg_recovery_commitment,
            "avg_recovery_focus_rate": avg_recovery_focus,
            "observe_share": observe_share,
            "phase_names": bucket["phase_names"],
            "progress_counts": progress_counts,
            "disturbed_progress_counts": bucket["disturbed_progress_counts"],
            "recovery_progress_counts": bucket["recovery_progress_counts"],
        }

    ranked = [scene for scene, _ in sorted(scene_scores, key=lambda item: item[1], reverse=True)]
    return {
        "scene_insights": insights,
        "strongest_scene": ranked[0] if ranked else None,
        "needs_attention": conservative_scenes,
        "scene_rank": ranked,
    }


def _build_scene_trend(insights: dict, previous_report: dict | None) -> dict:
    previous_insights = (previous_report or {}).get("scene_insights") or {}
    trends: dict[str, dict] = {}

    for scene_id, current in (insights.get("scene_insights") or {}).items():
        previous = previous_insights.get(scene_id)
        if not previous:
            trends[scene_id] = {
                "summary": "首次进入趋势对比",
                "commitment_delta": None,
                "focus_delta": None,
                "recovery_commitment_delta": None,
                "recovery_focus_delta": None,
                "observe_share_delta": None,
            }
            continue

        commitment_delta = _round_rate(current.get("avg_commitment_rate", 0.0) - previous.get("avg_commitment_rate", 0.0))
        focus_delta = _round_rate(current.get("avg_focus_rate", 0.0) - previous.get("avg_focus_rate", 0.0))
        recovery_commitment_delta = _round_rate(
            current.get("avg_recovery_commitment_rate", 0.0) - previous.get("avg_recovery_commitment_rate", 0.0)
        )
        recovery_focus_delta = _round_rate(
            current.get("avg_recovery_focus_rate", 0.0) - previous.get("avg_recovery_focus_rate", 0.0)
        )
        observe_share_delta = _round_rate(current.get("observe_share", 0.0) - previous.get("observe_share", 0.0))

        positive = 0
        negative = 0
        for value in (commitment_delta, focus_delta, recovery_commitment_delta, recovery_focus_delta):
            if value > 0:
                positive += 1
            elif value < 0:
                negative += 1
        if observe_share_delta < 0:
            positive += 1
        elif observe_share_delta > 0:
            negative += 1

        if positive >= 3 and negative == 0:
            summary = "比上一轮更稳"
        elif negative >= 3 and positive == 0:
            summary = "比上一轮更保守"
        elif positive > negative:
            summary = "比上一轮略有改善"
        elif negative > positive:
            summary = "比上一轮略有回弹"
        else:
            summary = "和上一轮基本持平"

        trends[scene_id] = {
            "summary": summary,
            "commitment_delta": commitment_delta,
            "focus_delta": focus_delta,
            "recovery_commitment_delta": recovery_commitment_delta,
            "recovery_focus_delta": recovery_focus_delta,
            "observe_share_delta": observe_share_delta,
        }

    return trends


def run_large_cycle(report_path: Path, smoke: bool) -> dict:
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()
    started_at = datetime.now(timezone.utc).isoformat()
    phase_results: list[dict] = []

    for phase in _phase_plan(smoke):
        print(f"\n=== {phase['label']} ===")
        if phase["kind"] == "standardization":
            phase_report_path = PARTS_DIR / "large_cycle_standardization_report.json"
            cmd = [
                _python_cmd(),
                "scripts/testing/run_standardization_daily_loop.py",
                "--report-path",
                str(phase_report_path),
            ]
            code, stdout, stderr, elapsed, timed_out = _run_command(cmd, phase["timeout"])
            if stdout.strip():
                print(stdout.rstrip())
            if stderr.strip():
                print(stderr.rstrip(), file=sys.stderr)
            summary = _summarize_standardization(phase_report_path) if phase_report_path.exists() else None
            phase_results.append(
                {
                    "name": phase["name"],
                    "label": phase["label"],
                    "kind": phase["kind"],
                    "returncode": code,
                    "timed_out": timed_out,
                    "elapsed_seconds": elapsed,
                    "summary": summary,
                    "stdout_tail": stdout.strip().splitlines()[-5:] if stdout.strip() else [],
                    "stderr_tail": stderr.strip().splitlines()[-5:] if stderr.strip() else [],
                }
            )
        else:
            before_summary = set((PROJECT_ROOT / "data").glob("sandbox_50x20_*.json"))
            before_detail = set((PROJECT_ROOT / "data").glob("sandbox_50x20_detail_*.json"))
            cmd = [
                _python_cmd(),
                "simulation/run_sandbox_50x20.py",
                "--scenes",
                *phase["scenes"],
                "--conversations",
                str(phase["conversations"]),
                "--rounds",
                str(phase["rounds"]),
                "--no-judge",
            ]
            code, stdout, stderr, elapsed, timed_out = _run_command(cmd, phase["timeout"])
            if stdout.strip():
                print(stdout.rstrip())
            if stderr.strip():
                print(stderr.rstrip(), file=sys.stderr)
            report_file = _latest_new_summary_file(before_summary)
            detail_file = _latest_new_detail_file(before_detail)
            summary = _summarize_sandbox(report_file, detail_file) if report_file else None
            phase_results.append(
                {
                    "name": phase["name"],
                    "label": phase["label"],
                    "kind": phase["kind"],
                    "returncode": code,
                    "timed_out": timed_out,
                    "elapsed_seconds": elapsed,
                    "config": {
                        "scenes": phase["scenes"],
                        "conversations": phase["conversations"],
                        "rounds": phase["rounds"],
                    },
                    "summary": summary,
                    "stdout_tail": stdout.strip().splitlines()[-5:] if stdout.strip() else [],
                    "stderr_tail": stderr.strip().splitlines()[-5:] if stderr.strip() else [],
                }
            )

        if phase_results[-1]["returncode"] != 0:
            break

    all_passed = all(item["returncode"] == 0 for item in phase_results) and len(phase_results) == len(_phase_plan(smoke))
    stable_rounds = _consecutive_stable_rounds(all_passed)
    previous_reports = _load_recent_archives(limit=1)
    previous_report = previous_reports[0] if previous_reports else None
    scene_insight_block = _build_scene_insights(phase_results)
    scene_trends = _build_scene_trend(scene_insight_block, previous_report)

    report = {
        "timestamp": time.time(),
        "started_at": started_at,
        "elapsed_seconds": round(time.time() - started, 2),
        "all_passed": all_passed,
        "smoke_mode": smoke,
        "stable_rounds": stable_rounds,
        "stable_candidate": stable_rounds >= 2,
        "phases": phase_results,
        "scene_trends": scene_trends,
    }
    report.update(scene_insight_block)
    return report


def save_report(report: dict, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告已保存: {report_path}")

    started_at = report.get("started_at")
    if started_at:
        archived_at = datetime.fromisoformat(started_at).strftime("%Y%m%d_%H%M%S_%f")
    else:
        archived_at = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = ARCHIVE_DIR / f"large_cycle_report_{archived_at}.json"
    archive_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"归档报告已保存: {archive_path}")


def _load_json_if_exists(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def build_sandbox_review_outputs(
    report: dict,
    insight_path: Path = DEFAULT_INSIGHT_PATH,
    queue_path: Path = DEFAULT_QUEUE_PATH,
    review_cards_path: Path = DEFAULT_REVIEW_CARDS_PATH,
    previous_queue_path: Path | None = DEFAULT_QUEUE_PATH,
) -> dict:
    previous_queue = _load_json_if_exists(previous_queue_path) if previous_queue_path else None
    insight = analyze_large_cycle_report(report)
    save_insight_report(insight, insight_path)

    queue = build_validation_queue(insight, previous_queue=previous_queue)
    save_validation_queue(queue, queue_path)

    review_cards = build_review_cards(queue)
    save_review_cards(review_cards, review_cards_path)

    return {
        "insight_path": str(insight_path),
        "queue_path": str(queue_path),
        "review_cards_path": str(review_cards_path),
        "gate_summary": insight.get("gate_summary"),
        "candidate_count": queue.get("queue_size", 0),
        "ready_for_review_count": queue.get("ready_for_review_count", 0),
        "review_card_count": review_cards.get("card_count", 0),
        "main_system_write_allowed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="大循环大量测试")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--smoke", action="store_true", help="先跑一版更轻的小烟测")
    args = parser.parse_args()

    report_path = Path(args.report_path)
    report = run_large_cycle(report_path=report_path, smoke=args.smoke)

    print("\n=== 大循环大量测试汇总 ===")
    for phase in report["phases"]:
        label = phase["label"]
        if phase["returncode"] == 0:
            print(f"{label}: OK in {phase['elapsed_seconds']}s")
        elif phase["timed_out"]:
            print(f"{label}: TIMEOUT in {phase['elapsed_seconds']}s")
        else:
            print(f"{label}: FAIL")
    print(f"all_passed={report['all_passed']}")
    print(f"stable_rounds={report['stable_rounds']}")
    print(f"stable_candidate={report['stable_candidate']}")
    save_report(report, report_path)
    review_summary = build_sandbox_review_outputs(report)
    print("\n=== 沙盒自动复盘 ===")
    print(f"洞察状态={review_summary['gate_summary']}")
    print(f"候选问题={review_summary['candidate_count']}")
    print(f"需要你决策={review_summary['ready_for_review_count']}")
    print(f"决策卡={review_summary['review_cards_path']}")
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
