"""
Human-OS Engine - 自动化合并闸门 (Automated Merge Gate)

功能：
1. 运行确定性测试（模式、优先级、加载器、进化器）。
2. 校验评测可观测报告（回归、失败码、均值 delta）。
3. 输出报告并返回状态码（0=通过，1=失败）。

用法：
    python scripts/run_merge_gate.py
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_REPORT_PATH = Path(BASE_DIR) / "data" / "eval_observability_report.json"
DEFAULT_GATE_OUTPUT_PATH = Path(BASE_DIR) / "data" / "merge_gate_report.json"
DEFAULT_SANDBOX_PERFORMANCE_HISTORY_PATH = Path(BASE_DIR) / "data" / "sandbox_performance_history.jsonl"
DEFAULT_SANDBOX_SEED = 20260410
DEFAULT_SANDBOX_ROUNDS = 1
SANDBOX_SCENES = ("sales", "management", "negotiation", "emotion")
DEFAULT_SANDBOX_SCENE_DURATION_SECONDS_BY_SCENE = {
    "sales": 60.0,
    "management": 70.0,
    "negotiation": 70.0,
    "emotion": 85.0,
}
DEFAULT_SANDBOX_TREND_WINDOW = 5
DEFAULT_SANDBOX_SLOWDOWN_RATIO = 0.2
DEFAULT_SANDBOX_SLOWDOWN_ABSOLUTE_SECONDS = 5.0
DEFAULT_SANDBOX_TRIAGE_PROBE_ORDER = ["step2_goal", "step8_execution", "step6_strategy"]


def _run_pytest_case(args: list[str], desc: str) -> bool:
    print(f"\n[RUN] {desc}")
    cmd = [sys.executable, "-m", "pytest"] + args
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=BASE_DIR)
    if result.returncode != 0:
        print("   [FAIL]")
        print(result.stdout[-300:])
        print(result.stderr[-300:])
        return False
    print("   [PASS]")
    return True


def _init_gate_report() -> dict[str, Any]:
    return {
        "timestamp": time.time(),
        "overall_passed": None,
        "steps": [],
    }


def _record_gate_step(
    report: dict[str, Any],
    *,
    name: str,
    passed: bool | None,
    status: str,
    reasons: list[str] | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    report["steps"].append(
        {
            "name": name,
            "status": status,  # pass/fail/skip/warn
            "passed": passed,
            "reasons": reasons or [],
            "meta": meta or {},
        }
    )


def _save_gate_report(report: dict[str, Any], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_scene_duration_map(run_meta: list[dict[str, Any]]) -> dict[str, float]:
    duration_map: dict[str, float] = {}
    for item in run_meta:
        scene = str(item.get("scene") or "")
        if not scene:
            continue
        duration_map[scene] = float(item.get("duration_seconds", 0.0) or 0.0)
    return duration_map


def _load_recent_sandbox_performance_history(
    history_path: Path,
    *,
    max_entries: int,
) -> list[dict[str, Any]]:
    if not history_path.exists() or max_entries <= 0:
        return []
    try:
        lines = history_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []

    history: list[dict[str, Any]] = []
    for line in lines[-max_entries:]:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if isinstance(item, dict):
            history.append(item)
    return history


def _append_sandbox_performance_history(
    history_path: Path,
    *,
    seed: int,
    rounds: int,
    run_meta: list[dict[str, Any]],
) -> None:
    entry = {
        "timestamp": time.time(),
        "seed": int(seed),
        "rounds": int(rounds),
        "scene_durations": _build_scene_duration_map(run_meta),
    }
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False))
        f.write("\n")


def evaluate_sandbox_performance_trend_gate(
    run_meta: list[dict[str, Any]],
    *,
    history_entries: list[dict[str, Any]],
    trend_window: int = DEFAULT_SANDBOX_TREND_WINDOW,
    slowdown_ratio: float = DEFAULT_SANDBOX_SLOWDOWN_RATIO,
    slowdown_absolute_seconds: float = DEFAULT_SANDBOX_SLOWDOWN_ABSOLUTE_SECONDS,
) -> tuple[bool, list[str], dict[str, Any]]:
    reasons: list[str] = []
    current_durations = _build_scene_duration_map(run_meta)
    scene_baselines: dict[str, float] = {}
    scene_sample_counts: dict[str, int] = {}
    scene_recent_samples: dict[str, list[float]] = {}
    slow_scene_details: list[dict[str, Any]] = []

    for scene, current_value in current_durations.items():
        samples: list[float] = []
        for entry in history_entries:
            scene_durations = entry.get("scene_durations", {})
            if not isinstance(scene_durations, dict):
                continue
            if scene not in scene_durations:
                continue
            try:
                sample_value = float(scene_durations.get(scene))
            except Exception:
                continue
            if sample_value > 0:
                samples.append(sample_value)

        if not samples:
            continue
        recent_samples = samples[-max(1, int(trend_window)):]
        baseline = sum(recent_samples) / len(recent_samples)
        scene_recent_samples[scene] = [round(float(value), 2) for value in recent_samples]
        scene_baselines[scene] = round(baseline, 2)
        scene_sample_counts[scene] = len(recent_samples)
        if baseline <= 0:
            continue

        slowdown_seconds = float(current_value) - float(baseline)
        slowdown_rate = slowdown_seconds / baseline
        if (
            slowdown_seconds >= float(slowdown_absolute_seconds)
            and slowdown_rate >= float(slowdown_ratio)
        ):
            triage_hint = {
                "probe_order": list(DEFAULT_SANDBOX_TRIAGE_PROBE_ORDER),
                "why": "按当前仓库实测基线，性能排查建议优先看 Step2，再看 Step8，最后看 Step6。",
            }
            slow_scene_details.append(
                {
                    "scene": scene,
                    "current_duration_seconds": round(float(current_value), 2),
                    "baseline_duration_seconds": round(float(baseline), 2),
                    "slowdown_seconds": round(float(slowdown_seconds), 2),
                    "slowdown_rate": round(float(slowdown_rate), 2),
                    "recent_samples_seconds": [round(float(value), 2) for value in recent_samples],
                    "triage_hint": triage_hint,
                }
            )
            reasons.append(
                f"场景 {scene} 相比近{len(recent_samples)}次基线明显变慢: "
                f"{float(current_value):.2f}s vs {float(baseline):.2f}s "
                f"(+{float(slowdown_seconds):.2f}s, +{float(slowdown_rate) * 100:.0f}%)"
            )

    meta = {
        "trend_window": int(trend_window),
        "slowdown_ratio": float(slowdown_ratio),
        "slowdown_absolute_seconds": float(slowdown_absolute_seconds),
        "history_sample_count": len(history_entries),
        "scene_baselines": scene_baselines,
        "scene_sample_counts": scene_sample_counts,
        "scene_recent_samples": scene_recent_samples,
        "slow_scene_count": len(slow_scene_details),
        "slow_scene_details": slow_scene_details,
        "default_triage_probe_order": list(DEFAULT_SANDBOX_TRIAGE_PROBE_ORDER),
    }
    return len(slow_scene_details) == 0, reasons, meta


def build_sandbox_smoke_commands(seed: int, rounds: int) -> list[list[str]]:
    commands: list[list[str]] = []
    for scene in SANDBOX_SCENES:
        commands.append(
            [
                sys.executable,
                "-m",
                "simulation.sandbox_v2",
                "--scene",
                scene,
                "--rounds",
                str(rounds),
                "--seed",
                str(seed),
                "--no-judge",
            ]
        )
    return commands


def evaluate_sandbox_smoke_gate(
    *,
    seed: int,
    rounds: int,
    run_cmd_fn: Any = subprocess.run,
) -> tuple[bool, list[str], list[dict[str, Any]]]:
    """
    最小沙盒回归门禁：
    - 固定 4 场景（sales/management/negotiation/emotion）
    - 固定 seed
    - 每场 1 轮（默认，可通过参数调整）
    - 关闭 LLM judge，确保门禁稳定可复跑
    """
    reasons: list[str] = []
    run_meta: list[dict[str, Any]] = []

    for cmd in build_sandbox_smoke_commands(seed=seed, rounds=rounds):
        scene = cmd[cmd.index("--scene") + 1]
        print(f"\n[RUN] 沙盒最小回归：{scene}")
        started = time.time()
        result = run_cmd_fn(cmd, capture_output=True, text=True, cwd=BASE_DIR)
        duration = round(time.time() - started, 2)
        exit_code = int(result.returncode)
        run_meta.append(
            {
                "scene": scene,
                "exit_code": exit_code,
                "duration_seconds": duration,
            }
        )
        if exit_code == 0:
            print(f"   [PASS] {duration:.2f}s")
            continue

        stdout_tail = (result.stdout or "")[-300:].strip()
        stderr_tail = (result.stderr or "")[-300:].strip()
        reason = f"场景 {scene} 运行失败(exit_code={exit_code})"
        reasons.append(reason)
        if stdout_tail:
            reasons.append(f"{scene} stdout_tail: {stdout_tail}")
        if stderr_tail:
            reasons.append(f"{scene} stderr_tail: {stderr_tail}")
        print(f"   [FAIL] {duration:.2f}s")

    return len(reasons) == 0, reasons, run_meta


def evaluate_sandbox_performance_gate(
    run_meta: list[dict[str, Any]],
    *,
    max_scene_duration_seconds: float = 45.0,
    max_scene_duration_seconds_by_scene: dict[str, float] | None = None,
) -> tuple[bool, list[str], dict[str, Any]]:
    reasons: list[str] = []
    scene_thresholds = {
        str(scene): float(value)
        for scene, value in (max_scene_duration_seconds_by_scene or {}).items()
    }
    slow_runs: list[dict[str, Any]] = []
    for item in run_meta:
        scene = str(item.get("scene") or "")
        observed_duration = float(item.get("duration_seconds", 0.0) or 0.0)
        threshold = float(scene_thresholds.get(scene, max_scene_duration_seconds))
        if observed_duration > threshold:
            slow_runs.append(
                {
                    **item,
                    "threshold_seconds": threshold,
                }
            )
    if slow_runs:
        for item in slow_runs:
            reasons.append(
                f"场景 {item.get('scene')} 运行耗时过长: "
                f"{float(item.get('duration_seconds', 0.0)):.2f}s > {float(item.get('threshold_seconds', max_scene_duration_seconds)):.2f}s"
            )

    max_duration = max((float(item.get("duration_seconds", 0.0) or 0.0) for item in run_meta), default=0.0)
    meta = {
        "max_scene_duration_seconds_default": float(max_scene_duration_seconds),
        "max_scene_duration_seconds_by_scene": scene_thresholds,
        "slow_scene_count": len(slow_runs),
        "max_observed_duration_seconds": round(max_duration, 2),
        "slow_scenes": [str(item.get("scene") or "") for item in slow_runs],
    }
    return len(slow_runs) == 0, reasons, meta


def _parse_sandbox_scene_thresholds(raw_text: str) -> dict[str, float]:
    if not raw_text.strip():
        return {}
    try:
        parsed = json.loads(raw_text)
    except Exception as exc:
        raise ValueError(f"按场景阈值 JSON 解析失败: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("按场景阈值必须是 JSON 对象，例如: {\"sales\":60,\"emotion\":80}")

    thresholds: dict[str, float] = {}
    allowed_scenes = set(SANDBOX_SCENES)
    for scene, value in parsed.items():
        scene_name = str(scene)
        if scene_name not in allowed_scenes:
            raise ValueError(f"未知场景: {scene_name}，可选: {', '.join(SANDBOX_SCENES)}")
        try:
            threshold_value = float(value)
        except Exception as exc:
            raise ValueError(f"场景 {scene_name} 阈值不是数字: {value}") from exc
        if threshold_value <= 0:
            raise ValueError(f"场景 {scene_name} 阈值必须 > 0")
        thresholds[scene_name] = threshold_value
    return thresholds


def evaluate_observability_report(
    report: dict[str, Any],
    *,
    max_report_age_hours: float = 36.0,
    min_repeats: int = 3,
    min_sample_size: int = 8,
    min_strategy_delta: float = -0.2,
    min_delivery_delta: float = -0.2,
    max_regressions: int = 0,
    max_failure_codes: int = 0,
) -> tuple[bool, list[str]]:
    """评测报告门禁：只看固定结构字段，不依赖人工解读。"""
    reasons: list[str] = []
    now = time.time()

    required_keys = {
        "timestamp",
        "repeats",
        "sample_size",
        "avg_strategy_delta",
        "avg_delivery_delta",
        "regressions",
        "failure_code_distribution",
        "scene_process_summary",
    }
    missing = sorted(list(required_keys - set(report.keys())))
    if missing:
        reasons.append(f"报告缺少字段: {missing}")
        return False, reasons

    ts = float(report.get("timestamp", 0))
    age_hours = (now - ts) / 3600.0 if ts > 0 else 9999.0
    if age_hours > max_report_age_hours:
        reasons.append(
            f"评测报告过旧: {age_hours:.1f}h > {max_report_age_hours:.1f}h"
        )

    repeats = int(report.get("repeats", 0) or 0)
    if repeats < min_repeats:
        reasons.append(f"repeats 不达标: {repeats} < {min_repeats}")

    sample_size = int(report.get("sample_size", 0) or 0)
    if sample_size < min_sample_size:
        reasons.append(f"sample_size 不达标: {sample_size} < {min_sample_size}")

    avg_strategy_delta = float(report.get("avg_strategy_delta", -999))
    if avg_strategy_delta < min_strategy_delta:
        reasons.append(
            f"avg_strategy_delta 低于门槛: {avg_strategy_delta:.2f} < {min_strategy_delta:.2f}"
        )

    avg_delivery_delta = float(report.get("avg_delivery_delta", -999))
    if avg_delivery_delta < min_delivery_delta:
        reasons.append(
            f"avg_delivery_delta 低于门槛: {avg_delivery_delta:.2f} < {min_delivery_delta:.2f}"
        )

    regressions = report.get("regressions", [])
    if not isinstance(regressions, list):
        reasons.append("regressions 字段格式错误（应为 list）")
    elif len(regressions) > max_regressions:
        reasons.append(f"回归条目超限: {len(regressions)} > {max_regressions}")

    failure_dist = report.get("failure_code_distribution", {})
    if not isinstance(failure_dist, dict):
        reasons.append("failure_code_distribution 字段格式错误（应为 dict）")
    else:
        failure_total = sum(int(v) for v in failure_dist.values())
        if failure_total > max_failure_codes:
            reasons.append(f"失败码总数超限: {failure_total} > {max_failure_codes}")

    return len(reasons) == 0, reasons


def _check_observability_gate(args: argparse.Namespace) -> bool:
    report_path = Path(args.report_path)
    print("\n[RUN] 评测可观测门禁")
    if not report_path.exists():
        print(f"   [FAIL] 报告不存在: {report_path}")
        return False

    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"   [FAIL] 报告解析失败: {exc}")
        return False

    passed, reasons = evaluate_observability_report(
        report,
        max_report_age_hours=args.max_report_age_hours,
        min_repeats=args.min_repeats,
        min_sample_size=args.min_sample_size,
        min_strategy_delta=args.min_strategy_delta,
        min_delivery_delta=args.min_delivery_delta,
        max_regressions=args.max_regressions,
        max_failure_codes=args.max_failure_codes,
    )
    if passed:
        print("   [PASS]")
        return True

    print("   [FAIL]")
    for r in reasons:
        print(f"   - {r}")
    return False


def evaluate_observability_gate(args: argparse.Namespace) -> tuple[bool, list[str]]:
    report_path = Path(args.report_path)
    if not report_path.exists():
        return False, [f"报告不存在: {report_path}"]
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return False, [f"报告解析失败: {exc}"]

    return evaluate_observability_report(
        report,
        max_report_age_hours=args.max_report_age_hours,
        min_repeats=args.min_repeats,
        min_sample_size=args.min_sample_size,
        min_strategy_delta=args.min_strategy_delta,
        min_delivery_delta=args.min_delivery_delta,
        max_regressions=args.max_regressions,
        max_failure_codes=args.max_failure_codes,
    )


def evaluate_progress_order_coverage(
    report: dict[str, Any],
    *,
    min_progress_entries: int = 2,
    min_progress_order_coverage: float = 0.5,
) -> tuple[bool, list[str], dict[str, float | int]]:
    """
    推进顺序覆盖率门禁（默认告警型）：
    - 样本够了才判覆盖率
    - 覆盖率不足会给出原因，是否拦截由 strict 开关决定
    """
    reasons: list[str] = []
    scene_summary = report.get("scene_process_summary", {})
    if not isinstance(scene_summary, dict):
        return False, ["scene_process_summary 字段格式错误（应为 dict）"], {
            "progress_entries": 0,
            "progress_entries_with_order": 0,
            "progress_order_coverage": 0.0,
        }

    progress_entries = 0
    progress_entries_with_order = 0
    for scene_item in scene_summary.values():
        if not isinstance(scene_item, dict):
            continue
        progress_entries += int(scene_item.get("progress_entries", 0) or 0)
        progress_entries_with_order += int(scene_item.get("progress_entries_with_order", 0) or 0)

    coverage = (
        round(progress_entries_with_order / progress_entries, 2) if progress_entries > 0 else 0.0
    )
    meta = {
        "progress_entries": progress_entries,
        "progress_entries_with_order": progress_entries_with_order,
        "progress_order_coverage": coverage,
    }

    if progress_entries < min_progress_entries:
        reasons.append(
            f"推进类样本不足，当前 {progress_entries} < {min_progress_entries}，本次只告警不判失败"
        )
        return True, reasons, meta

    if coverage < min_progress_order_coverage:
        reasons.append(
            f"推进顺序覆盖率偏低: {coverage:.2f} < {min_progress_order_coverage:.2f}"
        )
        return False, reasons, meta

    return True, reasons, meta


def evaluate_failure_avoid_coverage(
    report: dict[str, Any],
    *,
    min_failure_avoid_entries: int = 2,
    min_failure_avoid_hit_rate: float = 0.1,
) -> tuple[bool, list[str], dict[str, float | int]]:
    """
    failure_avoid 覆盖率门禁（默认告警型）：
    - 命中条目不足时只告警（样本不够）
    - 命中率不足时返回失败，由 strict 开关决定是否拦截
    """
    reasons: list[str] = []
    scene_summary = report.get("scene_process_summary", {})
    if not isinstance(scene_summary, dict):
        return False, ["scene_process_summary 字段格式错误（应为 dict）"], {
            "entries_with_failure_avoid": 0,
            "avg_failure_avoid_hit_rate": 0.0,
        }

    entries_with_failure_avoid = 0
    entries_with_failure_runs = 0
    degraded_entries = 0
    weighted_hit_total = 0.0
    total_entries = 0
    for scene_item in scene_summary.values():
        if not isinstance(scene_item, dict):
            continue
        scene_entries = int(scene_item.get("entries", 0) or 0)
        scene_hit_entries = int(scene_item.get("entries_with_failure_avoid", 0) or 0)
        scene_failure_runs_entries = int(scene_item.get("entries_with_failure_runs", 0) or 0)
        scene_degraded_entries = int(scene_item.get("degraded_entries", 0) or 0)
        scene_avg_hit_rate = float(scene_item.get("avg_failure_avoid_hit_rate", 0.0) or 0.0)
        total_entries += max(0, scene_entries)
        entries_with_failure_avoid += max(0, scene_hit_entries)
        entries_with_failure_runs += max(0, scene_failure_runs_entries)
        degraded_entries += max(0, scene_degraded_entries)
        weighted_hit_total += max(0.0, scene_avg_hit_rate) * max(0, scene_entries)

    global_hit_rate = (
        round(weighted_hit_total / total_entries, 2) if total_entries > 0 else 0.0
    )
    meta = {
        "entries_with_failure_avoid": entries_with_failure_avoid,
        "entries_with_failure_runs": entries_with_failure_runs,
        "degraded_entries": degraded_entries,
        "avg_failure_avoid_hit_rate": global_hit_rate,
        "total_entries": total_entries,
    }

    # 没有退化样本时不判覆盖率，避免健康主盘长期出现无意义告警。
    if degraded_entries <= 0:
        return True, [], meta

    if entries_with_failure_avoid < min_failure_avoid_entries:
        reasons.append(
            f"failure_avoid 命中条目不足，当前 {entries_with_failure_avoid} < {min_failure_avoid_entries}，本次只告警不判失败"
        )
        return True, reasons, meta

    if global_hit_rate < min_failure_avoid_hit_rate:
        reasons.append(
            f"failure_avoid 命中率偏低: {global_hit_rate:.2f} < {min_failure_avoid_hit_rate:.2f}"
        )
        return False, reasons, meta

    return True, reasons, meta


def evaluate_memory_hint_coverage(
    report: dict[str, Any],
    *,
    min_memory_hint_entries: int = 2,
    min_memory_decision_hit_rate: float = 0.1,
) -> tuple[bool, list[str], dict[str, float | int]]:
    """
    memory hints 覆盖率门禁（默认告警型）：
    - 看 Step6/Step8 记忆提示是否被稳定触发
    - 样本不足时只告警不拦截
    - 命中率不足时返回失败，由 strict 开关决定是否拦截
    """
    reasons: list[str] = []
    scene_summary = report.get("scene_process_summary", {})
    if not isinstance(scene_summary, dict):
        return False, ["scene_process_summary 字段格式错误（应为 dict）"], {
            "entries_with_memory_failure_hint": 0,
            "entries_with_memory_digest_hint": 0,
            "entries_with_memory_decision_hint": 0,
            "avg_memory_failure_hint_hit_rate": 0.0,
            "avg_memory_digest_hint_hit_rate": 0.0,
            "avg_memory_decision_hint_hit_rate": 0.0,
            "degraded_entries": 0,
            "total_entries": 0,
        }

    entries_with_memory_failure_hint = 0
    entries_with_memory_digest_hint = 0
    entries_with_memory_decision_hint = 0
    degraded_entries = 0
    weighted_failure_rate_total = 0.0
    weighted_digest_rate_total = 0.0
    weighted_decision_rate_total = 0.0
    total_entries = 0

    for scene_item in scene_summary.values():
        if not isinstance(scene_item, dict):
            continue
        scene_entries = int(scene_item.get("entries", 0) or 0)
        scene_degraded_entries = int(scene_item.get("degraded_entries", 0) or 0)
        total_entries += max(0, scene_entries)
        degraded_entries += max(0, scene_degraded_entries)
        entries_with_memory_failure_hint += int(scene_item.get("entries_with_memory_failure_hint", 0) or 0)
        entries_with_memory_digest_hint += int(scene_item.get("entries_with_memory_digest_hint", 0) or 0)
        entries_with_memory_decision_hint += int(scene_item.get("entries_with_memory_decision_hint", 0) or 0)
        weighted_failure_rate_total += float(scene_item.get("avg_memory_failure_hint_hit_rate", 0.0) or 0.0) * max(0, scene_entries)
        weighted_digest_rate_total += float(scene_item.get("avg_memory_digest_hint_hit_rate", 0.0) or 0.0) * max(0, scene_entries)
        weighted_decision_rate_total += float(scene_item.get("avg_memory_decision_hint_hit_rate", 0.0) or 0.0) * max(0, scene_entries)

    global_failure_rate = (
        round(weighted_failure_rate_total / total_entries, 2) if total_entries > 0 else 0.0
    )
    global_digest_rate = (
        round(weighted_digest_rate_total / total_entries, 2) if total_entries > 0 else 0.0
    )
    global_decision_rate = (
        round(weighted_decision_rate_total / total_entries, 2) if total_entries > 0 else 0.0
    )

    meta = {
        "entries_with_memory_failure_hint": entries_with_memory_failure_hint,
        "entries_with_memory_digest_hint": entries_with_memory_digest_hint,
        "entries_with_memory_decision_hint": entries_with_memory_decision_hint,
        "avg_memory_failure_hint_hit_rate": global_failure_rate,
        "avg_memory_digest_hint_hit_rate": global_digest_rate,
        "avg_memory_decision_hint_hit_rate": global_decision_rate,
        "degraded_entries": degraded_entries,
        "total_entries": total_entries,
    }

    # 没有退化样本时不判覆盖率，避免健康主盘长期出现无意义告警。
    if degraded_entries <= 0:
        return True, [], meta

    if entries_with_memory_decision_hint < min_memory_hint_entries:
        reasons.append(
            "memory 决策提示命中条目不足，"
            f"当前 {entries_with_memory_decision_hint} < {min_memory_hint_entries}，本次只告警不判失败"
        )
        return True, reasons, meta

    if global_decision_rate < min_memory_decision_hit_rate:
        reasons.append(
            f"memory 决策提示命中率偏低: {global_decision_rate:.2f} < {min_memory_decision_hit_rate:.2f}"
        )
        return False, reasons, meta

    return True, reasons, meta


def evaluate_doc_consistency(base_dir: Path) -> tuple[bool, list[str]]:
    """
    文档一致性门禁：
    1) README 测试/场景徽章数字要和目录真实数量一致。
    2) PROJECT_SUMMARY 中“测试文件/场景配置”统计要和目录真实数量一致。
    """
    reasons: list[str] = []

    readme_path = base_dir / "README.md"
    summary_path = base_dir / "docs" / "01_active" / "PROJECT_SUMMARY.md"
    tests_dir = base_dir / "tests"
    skills_dir = base_dir / "skills"

    if not readme_path.exists():
        reasons.append(f"README 不存在: {readme_path}")
        return False, reasons
    if not summary_path.exists():
        reasons.append(f"PROJECT_SUMMARY 不存在: {summary_path}")
        return False, reasons
    if not tests_dir.exists():
        reasons.append(f"tests 目录不存在: {tests_dir}")
        return False, reasons
    if not skills_dir.exists():
        reasons.append(f"skills 目录不存在: {skills_dir}")
        return False, reasons

    readme_text = readme_path.read_text(encoding="utf-8")
    summary_text = summary_path.read_text(encoding="utf-8")

    tests_count_actual = len([p for p in tests_dir.iterdir() if p.is_file()])
    scenes_count_actual = len([p for p in skills_dir.iterdir() if p.is_dir()])

    tests_badge_match = re.search(r"tests-(\d+)%20files", readme_text)
    if not tests_badge_match:
        reasons.append("README 缺少 tests 徽章数字（tests-XX%20files）")
    else:
        tests_badge = int(tests_badge_match.group(1))
        if tests_badge != tests_count_actual:
            reasons.append(f"README tests 徽章不一致: {tests_badge} != {tests_count_actual}")

    scenes_badge_match = re.search(r"scenes-(\d+)", readme_text)
    if not scenes_badge_match:
        reasons.append("README 缺少 scenes 徽章数字（scenes-XX）")
    else:
        scenes_badge = int(scenes_badge_match.group(1))
        if scenes_badge != scenes_count_actual:
            reasons.append(f"README scenes 徽章不一致: {scenes_badge} != {scenes_count_actual}")

    summary_tests_match = re.search(r"\|\s*测试文件\s*\|\s*(\d+)", summary_text)
    if not summary_tests_match:
        reasons.append("PROJECT_SUMMARY 缺少“测试文件”统计项")
    else:
        summary_tests = int(summary_tests_match.group(1))
        if summary_tests != tests_count_actual:
            reasons.append(f"PROJECT_SUMMARY 测试文件数不一致: {summary_tests} != {tests_count_actual}")

    summary_scenes_match = re.search(r"\|\s*场景配置\s*\|\s*(\d+)", summary_text)
    if not summary_scenes_match:
        reasons.append("PROJECT_SUMMARY 缺少“场景配置”统计项")
    else:
        summary_scenes = int(summary_scenes_match.group(1))
        if summary_scenes != scenes_count_actual:
            reasons.append(f"PROJECT_SUMMARY 场景配置数不一致: {summary_scenes} != {scenes_count_actual}")

    return len(reasons) == 0, reasons


def resolve_existing_path(candidates: list[str]) -> str:
    return next((p for p in candidates if os.path.exists(p)), "")


def _check_doc_consistency_gate() -> bool:
    print("\n[RUN] 文档一致性门禁")
    passed, reasons = evaluate_doc_consistency(Path(BASE_DIR))
    if passed:
        print("   [PASS]")
        return True
    print("   [FAIL]")
    for r in reasons:
        print(f"   - {r}")
    return False


def main():
    # 只在脚本直接运行时处理控制台编码，避免 import 阶段影响 pytest 捕获器。
    if sys.platform == "win32":
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    parser = argparse.ArgumentParser(description="自动化合并闸门")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH))
    parser.add_argument("--gate-output-path", default=str(DEFAULT_GATE_OUTPUT_PATH))
    parser.add_argument("--max-report-age-hours", type=float, default=36.0)
    parser.add_argument("--min-repeats", type=int, default=3)
    parser.add_argument("--min-sample-size", type=int, default=8)
    parser.add_argument("--min-strategy-delta", type=float, default=-0.2)
    parser.add_argument("--min-delivery-delta", type=float, default=-0.2)
    parser.add_argument("--max-regressions", type=int, default=0)
    parser.add_argument("--max-failure-codes", type=int, default=0)
    parser.add_argument("--min-progress-entries", type=int, default=2)
    parser.add_argument("--min-progress-order-coverage", type=float, default=0.5)
    parser.add_argument("--min-failure-avoid-entries", type=int, default=2)
    parser.add_argument("--min-failure-avoid-hit-rate", type=float, default=0.1)
    parser.add_argument("--min-memory-hint-entries", type=int, default=2)
    parser.add_argument("--min-memory-decision-hit-rate", type=float, default=0.1)
    parser.add_argument(
        "--strict-progress-order-gate",
        action="store_true",
        help="开启推进顺序覆盖率严格门禁（默认仅告警不拦截）",
    )
    parser.add_argument(
        "--strict-failure-avoid-gate",
        action="store_true",
        help="开启 failure_avoid 覆盖率严格门禁（默认仅告警不拦截）",
    )
    parser.add_argument(
        "--strict-memory-hint-gate",
        action="store_true",
        help="开启 memory hints 覆盖率严格门禁（默认仅告警不拦截）",
    )
    parser.add_argument(
        "--skip-report-gate",
        action="store_true",
        help="跳过评测报告门禁（不建议在正式放行使用）",
    )
    parser.add_argument(
        "--skip-doc-gate",
        action="store_true",
        help="跳过文档一致性门禁（不建议在正式放行使用）",
    )
    parser.add_argument(
        "--skip-sandbox-gate",
        action="store_true",
        help="跳过沙盒最小回归门禁（不建议在正式放行使用）",
    )
    parser.add_argument(
        "--sandbox-seed",
        type=int,
        default=DEFAULT_SANDBOX_SEED,
        help="沙盒最小回归固定种子",
    )
    parser.add_argument(
        "--sandbox-rounds",
        type=int,
        default=DEFAULT_SANDBOX_ROUNDS,
        help="沙盒最小回归每场轮数",
    )
    parser.add_argument(
        "--max-sandbox-scene-duration-seconds",
        type=float,
        default=45.0,
        help="沙盒单场景默认最大耗时阈值（可被按场景阈值覆盖）",
    )
    parser.add_argument(
        "--max-sandbox-scene-duration-seconds-by-scene",
        type=str,
        default=json.dumps(
            DEFAULT_SANDBOX_SCENE_DURATION_SECONDS_BY_SCENE,
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        help="按场景覆盖耗时阈值，JSON 格式，如 '{\"sales\":60,\"emotion\":80}'",
    )
    parser.add_argument(
        "--strict-sandbox-performance-gate",
        action="store_true",
        help="开启沙盒性能严格门禁（默认仅告警不拦截）",
    )
    parser.add_argument(
        "--sandbox-performance-history-path",
        type=str,
        default=str(DEFAULT_SANDBOX_PERFORMANCE_HISTORY_PATH),
        help="沙盒性能历史记录文件（JSONL）",
    )
    parser.add_argument(
        "--sandbox-trend-window",
        type=int,
        default=DEFAULT_SANDBOX_TREND_WINDOW,
        help="趋势比较窗口：对比最近 N 次历史基线",
    )
    parser.add_argument(
        "--sandbox-slowdown-ratio",
        type=float,
        default=DEFAULT_SANDBOX_SLOWDOWN_RATIO,
        help="判定“明显变慢”的相对阈值（如 0.2 = 慢 20%）",
    )
    parser.add_argument(
        "--sandbox-slowdown-absolute-seconds",
        type=float,
        default=DEFAULT_SANDBOX_SLOWDOWN_ABSOLUTE_SECONDS,
        help="判定“明显变慢”的绝对阈值（秒）",
    )
    parser.add_argument(
        "--strict-sandbox-performance-trend-gate",
        action="store_true",
        help="开启沙盒性能趋势严格门禁（默认仅告警不拦截）",
    )
    args = parser.parse_args()
    try:
        sandbox_scene_thresholds = _parse_sandbox_scene_thresholds(
            str(args.max_sandbox_scene_duration_seconds_by_scene or "")
        )
    except ValueError as exc:
        parser.error(str(exc))
    if int(args.sandbox_trend_window) <= 0:
        parser.error("--sandbox-trend-window 必须 > 0")
    if float(args.sandbox_slowdown_ratio) <= 0:
        parser.error("--sandbox-slowdown-ratio 必须 > 0")
    if float(args.sandbox_slowdown_absolute_seconds) <= 0:
        parser.error("--sandbox-slowdown-absolute-seconds 必须 > 0")

    print("=" * 60)
    print("[Gate] Human-OS Engine 自动化合并闸门")
    print("=" * 60)
    
    passed = True
    gate_report = _init_gate_report()
    
    # 1. 确定性测试（无 LLM 调用，快速）
    tests = [
        (["tests/test_modes.py", "-q"], "确定性测试：模式选择"),
        (["tests/test_priority.py", "-q"], "确定性测试：优先级规则"),
        (["tests/test_scene_loader.py", "-q"], "确定性测试：场景加载"),
        (["tests/test_scene_evolver.py", "-q"], "确定性测试：进化器"),
    ]
    
    for pytest_args, desc in tests:
        step_ok = _run_pytest_case(pytest_args, desc)
        _record_gate_step(gate_report, name=desc, passed=step_ok, status="pass" if step_ok else "fail")
        if not step_ok:
            passed = False

    # 2. 沙盒最小回归门禁（真跑主沙盒，无 LLM judge）
    if not args.skip_sandbox_gate:
        step_ok, reasons, run_meta = evaluate_sandbox_smoke_gate(
            seed=args.sandbox_seed,
            rounds=max(1, int(args.sandbox_rounds)),
        )
        _record_gate_step(
            gate_report,
            name="沙盒最小回归门禁",
            passed=step_ok,
            status="pass" if step_ok else "fail",
            reasons=reasons,
            meta={
                "seed": args.sandbox_seed,
                "rounds": max(1, int(args.sandbox_rounds)),
                "scenes": list(SANDBOX_SCENES),
                "runs": run_meta,
            },
        )
        if not step_ok:
            passed = False

        perf_ok, perf_reasons, perf_meta = evaluate_sandbox_performance_gate(
            run_meta,
            max_scene_duration_seconds=float(args.max_sandbox_scene_duration_seconds),
            max_scene_duration_seconds_by_scene=sandbox_scene_thresholds,
        )
        print("\n[RUN] 沙盒性能门禁")
        if perf_ok:
            print("   [PASS]")
        else:
            if args.strict_sandbox_performance_gate:
                print("   [FAIL]")
            else:
                print("   [WARN]")
            for r in perf_reasons:
                print(f"   - {r}")

        _record_gate_step(
            gate_report,
            name="沙盒性能门禁",
            passed=perf_ok if args.strict_sandbox_performance_gate else None,
            status=(
                "pass"
                if perf_ok
                else ("fail" if args.strict_sandbox_performance_gate else "warn")
            ),
            reasons=perf_reasons,
            meta={
                **perf_meta,
                "strict_mode": bool(args.strict_sandbox_performance_gate),
            },
        )
        if (not perf_ok) and args.strict_sandbox_performance_gate:
            passed = False

        history_path = Path(str(args.sandbox_performance_history_path))
        history_entries = _load_recent_sandbox_performance_history(
            history_path,
            max_entries=max(1, int(args.sandbox_trend_window)),
        )
        trend_ok, trend_reasons, trend_meta = evaluate_sandbox_performance_trend_gate(
            run_meta,
            history_entries=history_entries,
            trend_window=max(1, int(args.sandbox_trend_window)),
            slowdown_ratio=float(args.sandbox_slowdown_ratio),
            slowdown_absolute_seconds=float(args.sandbox_slowdown_absolute_seconds),
        )
        print("\n[RUN] 沙盒性能趋势门禁")
        if trend_ok:
            print("   [PASS]")
        else:
            if args.strict_sandbox_performance_trend_gate:
                print("   [FAIL]")
            else:
                print("   [WARN]")
            for r in trend_reasons:
                print(f"   - {r}")
        _record_gate_step(
            gate_report,
            name="沙盒性能趋势门禁",
            passed=trend_ok if args.strict_sandbox_performance_trend_gate else None,
            status=(
                "pass"
                if trend_ok
                else ("fail" if args.strict_sandbox_performance_trend_gate else "warn")
            ),
            reasons=trend_reasons,
            meta={
                **trend_meta,
                "strict_mode": bool(args.strict_sandbox_performance_trend_gate),
                "history_path": str(history_path),
            },
        )
        if (not trend_ok) and args.strict_sandbox_performance_trend_gate:
            passed = False
        _append_sandbox_performance_history(
            history_path,
            seed=args.sandbox_seed,
            rounds=max(1, int(args.sandbox_rounds)),
            run_meta=run_meta,
        )
    else:
        print("\n[SKIP] 沙盒最小回归门禁已跳过（--skip-sandbox-gate）")
        _record_gate_step(
            gate_report,
            name="沙盒最小回归门禁",
            passed=None,
            status="skip",
            reasons=["跳过（--skip-sandbox-gate）"],
            meta={
                "seed": args.sandbox_seed,
                "rounds": max(1, int(args.sandbox_rounds)),
                "scenes": list(SANDBOX_SCENES),
            },
        )
        _record_gate_step(
            gate_report,
            name="沙盒性能门禁",
            passed=None,
            status="skip",
            reasons=["跳过（--skip-sandbox-gate）"],
            meta={
                "max_scene_duration_seconds_default": float(args.max_sandbox_scene_duration_seconds),
                "max_scene_duration_seconds_by_scene": sandbox_scene_thresholds,
            },
        )
        _record_gate_step(
            gate_report,
            name="沙盒性能趋势门禁",
            passed=None,
            status="skip",
            reasons=["跳过（--skip-sandbox-gate）"],
            meta={
                "history_path": str(args.sandbox_performance_history_path),
                "trend_window": max(1, int(args.sandbox_trend_window)),
                "slowdown_ratio": float(args.sandbox_slowdown_ratio),
                "slowdown_absolute_seconds": float(args.sandbox_slowdown_absolute_seconds),
            },
        )

    # 3. 评测报告门禁（无 LLM 调用，读取最新可观测报告）
    if not args.skip_report_gate:
        step_ok, reasons = evaluate_observability_gate(args)
        print("\n[RUN] 评测可观测门禁")
        if step_ok:
            print("   [PASS]")
        else:
            print("   [FAIL]")
            for r in reasons:
                print(f"   - {r}")
        _record_gate_step(
            gate_report,
            name="评测可观测门禁",
            passed=step_ok,
            status="pass" if step_ok else "fail",
            reasons=reasons,
            meta={"report_path": str(args.report_path)},
        )
        if not step_ok:
            passed = False

        report = json.loads(Path(args.report_path).read_text(encoding="utf-8"))
        progress_ok, progress_reasons, progress_meta = evaluate_progress_order_coverage(
            report,
            min_progress_entries=max(0, int(args.min_progress_entries)),
            min_progress_order_coverage=float(args.min_progress_order_coverage),
        )
        print("\n[RUN] 推进顺序覆盖率门禁")
        if progress_ok:
            if progress_reasons:
                print("   [WARN]")
                for r in progress_reasons:
                    print(f"   - {r}")
            else:
                print("   [PASS]")
        else:
            if args.strict_progress_order_gate:
                print("   [FAIL]")
            else:
                print("   [WARN]")
            for r in progress_reasons:
                print(f"   - {r}")

        _record_gate_step(
            gate_report,
            name="推进顺序覆盖率门禁",
            passed=progress_ok if args.strict_progress_order_gate else None,
            status=(
                "pass"
                if progress_ok and not progress_reasons
                else ("fail" if (not progress_ok and args.strict_progress_order_gate) else "warn")
            ),
            reasons=progress_reasons,
            meta={
                **progress_meta,
                "min_progress_entries": max(0, int(args.min_progress_entries)),
                "min_progress_order_coverage": float(args.min_progress_order_coverage),
                "strict_mode": bool(args.strict_progress_order_gate),
            },
        )
        if (not progress_ok) and args.strict_progress_order_gate:
            passed = False

        failure_avoid_ok, failure_avoid_reasons, failure_avoid_meta = evaluate_failure_avoid_coverage(
            report,
            min_failure_avoid_entries=max(0, int(args.min_failure_avoid_entries)),
            min_failure_avoid_hit_rate=float(args.min_failure_avoid_hit_rate),
        )
        print("\n[RUN] failure_avoid 覆盖率门禁")
        if failure_avoid_ok:
            if failure_avoid_reasons:
                print("   [WARN]")
                for r in failure_avoid_reasons:
                    print(f"   - {r}")
            else:
                print("   [PASS]")
        else:
            if args.strict_failure_avoid_gate:
                print("   [FAIL]")
            else:
                print("   [WARN]")
            for r in failure_avoid_reasons:
                print(f"   - {r}")

        _record_gate_step(
            gate_report,
            name="failure_avoid 覆盖率门禁",
            passed=failure_avoid_ok if args.strict_failure_avoid_gate else None,
            status=(
                "pass"
                if failure_avoid_ok and not failure_avoid_reasons
                else ("fail" if (not failure_avoid_ok and args.strict_failure_avoid_gate) else "warn")
            ),
            reasons=failure_avoid_reasons,
            meta={
                **failure_avoid_meta,
                "min_failure_avoid_entries": max(0, int(args.min_failure_avoid_entries)),
                "min_failure_avoid_hit_rate": float(args.min_failure_avoid_hit_rate),
                "strict_mode": bool(args.strict_failure_avoid_gate),
            },
        )
        if (not failure_avoid_ok) and args.strict_failure_avoid_gate:
            passed = False

        memory_hint_ok, memory_hint_reasons, memory_hint_meta = evaluate_memory_hint_coverage(
            report,
            min_memory_hint_entries=max(0, int(args.min_memory_hint_entries)),
            min_memory_decision_hit_rate=float(args.min_memory_decision_hit_rate),
        )
        print("\n[RUN] memory hints 覆盖率门禁")
        if memory_hint_ok:
            if memory_hint_reasons:
                print("   [WARN]")
                for r in memory_hint_reasons:
                    print(f"   - {r}")
            else:
                print("   [PASS]")
        else:
            if args.strict_memory_hint_gate:
                print("   [FAIL]")
            else:
                print("   [WARN]")
            for r in memory_hint_reasons:
                print(f"   - {r}")

        _record_gate_step(
            gate_report,
            name="memory hints 覆盖率门禁",
            passed=memory_hint_ok if args.strict_memory_hint_gate else None,
            status=(
                "pass"
                if memory_hint_ok and not memory_hint_reasons
                else ("fail" if (not memory_hint_ok and args.strict_memory_hint_gate) else "warn")
            ),
            reasons=memory_hint_reasons,
            meta={
                **memory_hint_meta,
                "min_memory_hint_entries": max(0, int(args.min_memory_hint_entries)),
                "min_memory_decision_hit_rate": float(args.min_memory_decision_hit_rate),
                "strict_mode": bool(args.strict_memory_hint_gate),
            },
        )
        if (not memory_hint_ok) and args.strict_memory_hint_gate:
            passed = False
    else:
        print("\n[SKIP] 评测可观测门禁已跳过（--skip-report-gate）")
        _record_gate_step(
            gate_report,
            name="评测可观测门禁",
            passed=None,
            status="skip",
            reasons=["跳过（--skip-report-gate）"],
        )
        _record_gate_step(
            gate_report,
            name="推进顺序覆盖率门禁",
            passed=None,
            status="skip",
            reasons=["跳过（--skip-report-gate）"],
        )
        _record_gate_step(
            gate_report,
            name="failure_avoid 覆盖率门禁",
            passed=None,
            status="skip",
            reasons=["跳过（--skip-report-gate）"],
        )
        _record_gate_step(
            gate_report,
            name="memory hints 覆盖率门禁",
            passed=None,
            status="skip",
            reasons=["跳过（--skip-report-gate）"],
        )

    # 4. 文档一致性门禁（README/PROJECT_SUMMARY 数字口径）
    if not args.skip_doc_gate:
        step_ok, reasons = evaluate_doc_consistency(Path(BASE_DIR))
        print("\n[RUN] 文档一致性门禁")
        if step_ok:
            print("   [PASS]")
        else:
            print("   [FAIL]")
            for r in reasons:
                print(f"   - {r}")
        _record_gate_step(
            gate_report,
            name="文档一致性门禁",
            passed=step_ok,
            status="pass" if step_ok else "fail",
            reasons=reasons,
        )
        if not step_ok:
            passed = False
    else:
        print("\n[SKIP] 文档一致性门禁已跳过（--skip-doc-gate）")
        _record_gate_step(
            gate_report,
            name="文档一致性门禁",
            passed=None,
            status="skip",
            reasons=["跳过（--skip-doc-gate）"],
        )

    # 5. 管理场景（仅验证配置文件格式正确）
    print(f"\n[RUN] 管理场景配置验证")
    mgmt_config_candidates = [
        os.path.join(BASE_DIR, "config", "scenes", "management", "base.json"),
        os.path.join(BASE_DIR, "skills", "management", "base.json"),
    ]
    mgmt_data = os.path.join(BASE_DIR, "tests", "management_benchmark_data.json")
    existing_mgmt_config = resolve_existing_path(mgmt_config_candidates)
    if existing_mgmt_config and os.path.exists(mgmt_data):
        json.load(open(existing_mgmt_config, 'r', encoding='utf-8'))
        json.load(open(mgmt_data, 'r', encoding='utf-8'))
        print(f"   [PASS] 配置文件格式正确")
        _record_gate_step(
            gate_report,
            name="管理场景配置验证",
            passed=True,
            status="pass",
            meta={
                "management_config_path": existing_mgmt_config,
                "management_benchmark_path": mgmt_data,
            },
        )
    else:
        print(f"   [WARN] 跳过（管理场景配置文件不存在）")
        _record_gate_step(
            gate_report,
            name="管理场景配置验证",
            passed=None,
            status="warn",
            reasons=["跳过（管理场景配置文件不存在）"],
            meta={
                "management_config_candidates": mgmt_config_candidates,
                "management_benchmark_path": mgmt_data,
            },
        )

    # 6. 最终报告
    print("\n" + "="*60)
    gate_report["overall_passed"] = passed
    _save_gate_report(gate_report, Path(args.gate_output_path))
    print(f"[GateReport] 已写入: {args.gate_output_path}")
    if passed:
        print("[PASS] 合并闸门检查通过")
        print("="*60)
        print("\n[NOTE] LLM 重测仍建议定期手动跑")
        print("  - 题库稳定性: pytest tests/test_benchmark.py::TestGoldenSetStability -v")
        print("  - 基线对抗: python tests/test_baseline.py --runs 30")
        sys.exit(0)
    else:
        print("[FAIL] 合并闸门检查失败，请修复后重试")
        print("="*60)
        sys.exit(1)


if __name__ == "__main__":
    main()
