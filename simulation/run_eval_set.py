"""
Human-OS Engine - 固定评测集运行脚本

用法: py -m simulation.run_eval_set [--report]

功能:
1. 加载 eval_set.json 中的固定评测条目
2. 对每条执行主链推理(通过sandbox_core的MultiTurnSandboxRunner)，获取实际 strategy_score 和 delivery_score
3. 与金标对比，输出差异报告
4. --report 时保存完整报告到 data/eval_report.json
"""

import json
import time
import sys
import argparse
import re
from statistics import median
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EVAL_SET_PATH = PROJECT_ROOT / "data" / "eval_set.json"
REPORT_PATH = PROJECT_ROOT / "data" / "eval_report.json"


def _is_progress_request(text: str) -> bool:
    content = (text or "").strip()
    if not content:
        return False
    markers = ["推进", "落地", "下一步", "接下来", "怎么做", "怎么走", "先做", "执行"]
    return any(marker in content for marker in markers)


def _has_order_markers(text: str) -> bool:
    content = (text or "").strip()
    if not content:
        return False
    return bool(re.search(r"(第一步|第二步|先.{0,18}(再|然后)|先做|后做|最后)", content))


def _extract_order_source(turn: object, progress_request: bool) -> str:
    output_layers = getattr(turn, "output_layers", {}) or {}
    if isinstance(output_layers, dict):
        source = (output_layers.get("order_source") or "").strip()
        if source:
            return source
    if not progress_request:
        return "not_progress_request"
    return "order_marker_present" if _has_order_markers(getattr(turn, "system_output", "")) else "no_order_marker"


def _extract_memory_hint_signals(turn: object) -> dict[str, bool]:
    output_layers = getattr(turn, "output_layers", {}) or {}
    if not isinstance(output_layers, dict):
        return {
            "failure_avoid_hint": False,
            "experience_digest_hint": False,
            "decision_experience_hint": False,
        }
    signals = output_layers.get("memory_hint_signals", {}) or {}
    if not isinstance(signals, dict):
        return {
            "failure_avoid_hint": False,
            "experience_digest_hint": False,
            "decision_experience_hint": False,
        }
    return {
        "failure_avoid_hint": bool(signals.get("failure_avoid_hint", False)),
        "experience_digest_hint": bool(signals.get("experience_digest_hint", False)),
        "decision_experience_hint": bool(signals.get("decision_experience_hint", False)),
    }


def load_eval_set() -> list[dict]:
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["entries"]


def pick_primary_failure_code(
    failure_code_runs: list[str],
    strategy_delta: float,
    delivery_delta: float,
    warn_threshold: float = -0.3,
) -> str:
    """
    只在中位数结果出现真实退化时，才给条目挂失败码。

    这样可以避免：
    - 单次异常 run 把高分样本也打上失败码
    - 报告里出现“整体涨分但带失败码”的噪音条目
    """
    if not failure_code_runs:
        return ""
    if strategy_delta >= warn_threshold and delivery_delta >= warn_threshold:
        return ""
    return Counter(failure_code_runs).most_common(1)[0][0]


def run_single_turn(entry: dict, repeats: int = 3) -> dict:
    """对单条评测条目执行主链推理，返回实际评分（支持多次取中位数）。"""
    from simulation.sandbox_core import MultiTurnSandboxRunner
    
    scene = entry["scene"]
    user_input = entry["input"]

    # 构造persona（根据场景和人格）
    persona_map = {
        "sales": {"理性型客户": {"personality": "理性，只看数据", "trust": 0.3, "emotion": 0.3},
                  "犹豫型客户": {"personality": "犹豫，怕担责", "trust": 0.4, "emotion": 0.5},
                  "攻击型客户": {"personality": "攻击，强势压价", "trust": 0.2, "emotion": 0.7}},
        "negotiation": {"竞争型对手": {"personality": "竞争，零和思维", "trust": 0.2, "emotion": 0.4},
                        "合作型对手": {"personality": "合作，寻求双赢", "trust": 0.5, "emotion": 0.3},
                        "回避型对手": {"personality": "回避，不愿冲突", "trust": 0.4, "emotion": 0.5}},
        "management": {"躺平员工": {"personality": "躺平，缺乏动力", "trust": 0.3, "emotion": 0.6},
                       "高绩效员工": {"personality": "高绩效，要求高", "trust": 0.6, "emotion": 0.4},
                       "问题员工": {"personality": "问题，态度恶劣", "trust": 0.2, "emotion": 0.7}},
        "emotion": {"焦虑型": {"personality": "焦虑，害怕被抛弃", "trust": 0.3, "emotion": 0.8},
                    "愤怒型": {"personality": "愤怒，被伤害爆发", "trust": 0.2, "emotion": 0.9},
                    "疲惫型": {"personality": "疲惫，资源耗尽", "trust": 0.3, "emotion": 0.6}},
    }
    persona = persona_map.get(scene, {}).get(entry["persona"], {"personality": "中性", "trust": 0.5, "emotion": 0.5})
    persona = {"name": entry["persona"], **persona}

    runs = max(1, int(repeats))
    progress_request = _is_progress_request(entry.get("input", ""))
    strategy_runs = []
    delivery_runs = []
    failure_code_runs: list[str] = []
    failure_avoid_code_runs: list[list[str]] = []
    output_order_marker_runs: list[bool] = []
    output_order_source_runs: list[str] = []
    memory_hint_signal_runs: list[dict[str, bool]] = []
    last_error = None

    for _ in range(runs):
        try:
            runner = MultiTurnSandboxRunner(scene_id=scene, max_rounds=1, use_llm_judge=True)
            result = runner.run_conversation(persona=persona, initial_input=user_input)
            if result.turns:
                turn = result.turns[0]
                strategy_runs.append(float(turn.strategy_score))
                delivery_runs.append(float(turn.delivery_score))
                output_order_marker_runs.append(_has_order_markers(getattr(turn, "system_output", "")))
                output_order_source_runs.append(_extract_order_source(turn, progress_request))
                memory_hint_signal_runs.append(_extract_memory_hint_signals(turn))
                output_layers = getattr(turn, "output_layers", {}) or {}
                if isinstance(output_layers, dict):
                    avoid_codes = output_layers.get("failure_avoid_codes", []) or []
                    if isinstance(avoid_codes, list):
                        failure_avoid_code_runs.append(
                            [str(code).strip() for code in avoid_codes if str(code).strip()]
                        )
                    else:
                        failure_avoid_code_runs.append([])
                else:
                    failure_avoid_code_runs.append([])

                judge_result = getattr(turn, "judge_result", {}) or {}
                if judge_result:
                    try:
                        from modules.L5.counter_example_lib import infer_failure_code

                        inferred_code = infer_failure_code(
                            judge_result=judge_result,
                            context={
                                "scene_id": scene,
                                "persona": entry["persona"],
                            },
                            output_text=getattr(turn, "system_output", ""),
                        )
                        if inferred_code:
                            failure_code_runs.append(inferred_code.value)
                    except Exception:
                        pass
        except Exception as e:
            last_error = str(e)

    if not strategy_runs or not delivery_runs:
        raise RuntimeError(last_error or "评测失败：无有效评分结果")

    actual_strategy = float(median(strategy_runs))
    actual_delivery = float(median(delivery_runs))
    strategy_delta = round(actual_strategy - entry["gold_strategy"], 1)
    delivery_delta = round(actual_delivery - entry["gold_delivery"], 1)
    order_hit_rate = (
        round(sum(1 for hit in output_order_marker_runs if hit) / len(output_order_marker_runs), 2)
        if output_order_marker_runs
        else 0.0
    )
    order_injected_hit_rate = (
        round(sum(1 for source in output_order_source_runs if source == "skeleton_injected") / len(output_order_source_runs), 2)
        if output_order_source_runs
        else 0.0
    )
    failure_avoid_hit_rate = (
        round(sum(1 for codes in failure_avoid_code_runs if isinstance(codes, list) and len(codes) > 0) / len(failure_avoid_code_runs), 2)
        if failure_avoid_code_runs
        else 0.0
    )
    memory_failure_hint_hit_rate = (
        round(
            sum(1 for item in memory_hint_signal_runs if item.get("failure_avoid_hint", False))
            / len(memory_hint_signal_runs),
            2,
        )
        if memory_hint_signal_runs
        else 0.0
    )
    memory_digest_hint_hit_rate = (
        round(
            sum(1 for item in memory_hint_signal_runs if item.get("experience_digest_hint", False))
            / len(memory_hint_signal_runs),
            2,
        )
        if memory_hint_signal_runs
        else 0.0
    )
    memory_decision_hint_hit_rate = (
        round(
            sum(1 for item in memory_hint_signal_runs if item.get("decision_experience_hint", False))
            / len(memory_hint_signal_runs),
            2,
        )
        if memory_hint_signal_runs
        else 0.0
    )
    primary_failure_code = pick_primary_failure_code(
        failure_code_runs=failure_code_runs,
        strategy_delta=strategy_delta,
        delivery_delta=delivery_delta,
    )
    
    return {
        "id": entry["id"],
        "scene": entry["scene"],
        "persona": entry["persona"],
        "round": entry["round"],
        "input": entry["input"],
        "gold_strategy": entry["gold_strategy"],
        "gold_delivery": entry["gold_delivery"],
        "actual_strategy": round(actual_strategy, 1),
        "actual_delivery": round(actual_delivery, 1),
        "actual_strategy_runs": [round(x, 1) for x in strategy_runs],
        "actual_delivery_runs": [round(x, 1) for x in delivery_runs],
        "progress_request": progress_request,
        "output_order_marker_runs": output_order_marker_runs,
        "output_order_source_runs": output_order_source_runs,
        "output_order_hit_rate": order_hit_rate,
        "output_order_injected_hit_rate": order_injected_hit_rate,
        "failure_avoid_code_runs": failure_avoid_code_runs,
        "failure_avoid_hit_rate": failure_avoid_hit_rate,
        "memory_hint_signal_runs": memory_hint_signal_runs,
        "memory_failure_hint_hit_rate": memory_failure_hint_hit_rate,
        "memory_digest_hint_hit_rate": memory_digest_hint_hit_rate,
        "memory_decision_hint_hit_rate": memory_decision_hint_hit_rate,
        "failure_code": primary_failure_code,
        "failure_code_runs": failure_code_runs,
        "repeats": runs,
        "strategy_delta": strategy_delta,
        "delivery_delta": delivery_delta,
        "tags": entry.get("tags", []),
    }


def build_failure_code_distribution(results: list[dict], warn_threshold: float = -0.3) -> dict[str, int]:
    """
    统计失败码分布。

    口径：
    - 只统计有退化信号的条目（策略或成品 delta 低于 warn_threshold）
    - 只统计存在 failure_code 的条目
    """
    counter: Counter = Counter()
    for r in results:
        sd = float(r.get("strategy_delta", 0))
        dd = float(r.get("delivery_delta", 0))
        code = (r.get("failure_code") or "").strip()
        if code and (sd < warn_threshold or dd < warn_threshold):
            counter[code] += 1
    return dict(counter.most_common())


def build_scene_process_summary(results: list[dict], warn_threshold: float = -0.3) -> dict[str, dict]:
    """
    场景级过程汇总（不改变评分口径，仅补可观测信息）。

    每个场景输出：
    - entries: 条目数
    - avg_strategy_delta / avg_delivery_delta: 场景均值
    - avg_repeats: 平均重复次数
    - entries_with_failure_runs: 带 failure_code_runs 的条目数
    - entries_with_failure_avoid: 命中过 failure_avoid_codes 的条目数
    - avg_failure_avoid_hit_rate: 场景平均规避命中率（按条目）
    - entries_with_memory_failure_hint / entries_with_memory_digest_hint / entries_with_memory_decision_hint
    - avg_memory_failure_hint_hit_rate / avg_memory_digest_hint_hit_rate / avg_memory_decision_hint_hit_rate
    - degraded_entries: 退化条目数（任一 delta < warn_threshold）
    - regression_entries: 强回归条目数（任一 delta < -1.5）
    """
    grouped: dict[str, list[dict]] = {}
    for row in results:
        scene = row.get("scene", "unknown")
        grouped.setdefault(scene, []).append(row)

    summary: dict[str, dict] = {}
    for scene, rows in grouped.items():
        n = max(1, len(rows))
        avg_sd = sum(float(r.get("strategy_delta", 0)) for r in rows) / n
        avg_dd = sum(float(r.get("delivery_delta", 0)) for r in rows) / n
        avg_repeats = sum(int(r.get("repeats", 0) or 0) for r in rows) / n
        entries_with_failure_runs = sum(
            1 for r in rows if isinstance(r.get("failure_code_runs"), list) and len(r["failure_code_runs"]) > 0
        )
        entries_with_failure_avoid = sum(
            1
            for r in rows
            if isinstance(r.get("failure_avoid_code_runs"), list)
            and any(isinstance(item, list) and len(item) > 0 for item in r["failure_avoid_code_runs"])
        )
        avg_failure_avoid_hit_rate = (
            sum(float(r.get("failure_avoid_hit_rate", 0.0) or 0.0) for r in rows) / n
        )
        entries_with_memory_failure_hint = sum(
            1 for r in rows if float(r.get("memory_failure_hint_hit_rate", 0.0) or 0.0) > 0.0
        )
        entries_with_memory_digest_hint = sum(
            1 for r in rows if float(r.get("memory_digest_hint_hit_rate", 0.0) or 0.0) > 0.0
        )
        entries_with_memory_decision_hint = sum(
            1 for r in rows if float(r.get("memory_decision_hint_hit_rate", 0.0) or 0.0) > 0.0
        )
        avg_memory_failure_hint_hit_rate = (
            sum(float(r.get("memory_failure_hint_hit_rate", 0.0) or 0.0) for r in rows) / n
        )
        avg_memory_digest_hint_hit_rate = (
            sum(float(r.get("memory_digest_hint_hit_rate", 0.0) or 0.0) for r in rows) / n
        )
        avg_memory_decision_hint_hit_rate = (
            sum(float(r.get("memory_decision_hint_hit_rate", 0.0) or 0.0) for r in rows) / n
        )
        degraded_entries = sum(
            1
            for r in rows
            if float(r.get("strategy_delta", 0)) < warn_threshold
            or float(r.get("delivery_delta", 0)) < warn_threshold
        )
        regression_entries = sum(
            1
            for r in rows
            if float(r.get("strategy_delta", 0)) < -1.5
            or float(r.get("delivery_delta", 0)) < -1.5
        )
        progress_rows = [r for r in rows if bool(r.get("progress_request", False))]
        progress_entries = len(progress_rows)
        progress_entries_with_order = sum(
            1 for r in progress_rows if float(r.get("output_order_hit_rate", 0.0)) > 0.0
        )
        progress_entries_with_injected_order = sum(
            1 for r in progress_rows if float(r.get("output_order_injected_hit_rate", 0.0)) > 0.0
        )
        progress_order_coverage = (
            round(progress_entries_with_order / progress_entries, 2) if progress_entries > 0 else 0.0
        )
        summary[scene] = {
            "entries": n,
            "avg_strategy_delta": round(avg_sd, 2),
            "avg_delivery_delta": round(avg_dd, 2),
            "avg_repeats": round(avg_repeats, 2),
            "entries_with_failure_runs": entries_with_failure_runs,
            "entries_with_failure_avoid": entries_with_failure_avoid,
            "avg_failure_avoid_hit_rate": round(avg_failure_avoid_hit_rate, 2),
            "entries_with_memory_failure_hint": entries_with_memory_failure_hint,
            "entries_with_memory_digest_hint": entries_with_memory_digest_hint,
            "entries_with_memory_decision_hint": entries_with_memory_decision_hint,
            "avg_memory_failure_hint_hit_rate": round(avg_memory_failure_hint_hit_rate, 2),
            "avg_memory_digest_hint_hit_rate": round(avg_memory_digest_hint_hit_rate, 2),
            "avg_memory_decision_hint_hit_rate": round(avg_memory_decision_hint_hit_rate, 2),
            "degraded_entries": degraded_entries,
            "regression_entries": regression_entries,
            "progress_entries": progress_entries,
            "progress_entries_with_order": progress_entries_with_order,
            "progress_entries_with_injected_order": progress_entries_with_injected_order,
            "progress_order_coverage": progress_order_coverage,
        }

    return summary


def run_eval_set(repeats: int = 3) -> list[dict]:
    """运行完整评测集"""
    entries = load_eval_set()
    results = []
    runs = max(1, int(repeats))
    
    print(f"评测集: {len(entries)} 条")
    if runs > 1:
        print(f"每条重复: {runs} 次（取中位数）")
    print("=" * 70)
    
    for i, entry in enumerate(entries):
        eid = entry["id"]
        print(f"  [{i+1}/{len(entries)}] {eid}...", end=" ", flush=True)
        
        try:
            result = run_single_turn(entry, repeats=runs)
            sd = result["strategy_delta"]
            dd = result["delivery_delta"]
            flag = ""
            if sd < -1.5 or dd < -1.5:
                flag = " [REGRESSION]"
            elif sd < -0.5 or dd < -0.5:
                flag = " [WARN]"
            print(f"S={result['actual_strategy']}(d{sd:+.1f}) D={result['actual_delivery']}(d{dd:+.1f}){flag}")
            results.append(result)
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "id": eid,
                "scene": entry["scene"],
                "persona": entry["persona"],
                "round": entry["round"],
                "input": entry["input"],
                "gold_strategy": entry["gold_strategy"],
                "gold_delivery": entry["gold_delivery"],
                "actual_strategy": 0.0,
                "actual_delivery": 0.0,
                "actual_strategy_runs": [],
                "actual_delivery_runs": [],
                "progress_request": _is_progress_request(entry.get("input", "")),
                "output_order_marker_runs": [],
                "output_order_source_runs": [],
                "output_order_hit_rate": 0.0,
                "output_order_injected_hit_rate": 0.0,
                "failure_avoid_code_runs": [],
                "failure_avoid_hit_rate": 0.0,
                "memory_hint_signal_runs": [],
                "memory_failure_hint_hit_rate": 0.0,
                "memory_digest_hint_hit_rate": 0.0,
                "memory_decision_hint_hit_rate": 0.0,
                "failure_code": "",
                "failure_code_runs": [],
                "repeats": runs,
                "strategy_delta": -entry["gold_strategy"],
                "delivery_delta": -entry["gold_delivery"],
                "tags": entry.get("tags", []),
                "error": str(e),
            })
    
    return results


def print_summary(results: list[dict]):
    """打印汇总报告"""
    print("\n" + "=" * 70)
    print("评测汇总")
    print("=" * 70)
    
    # 按场景分组
    scenes = {}
    for r in results:
        s = r["scene"]
        if s not in scenes:
            scenes[s] = []
        scenes[s].append(r)
    
    total_strategy_delta = 0.0
    total_delivery_delta = 0.0
    regressions = []
    
    for scene, items in scenes.items():
        avg_sd = sum(r["strategy_delta"] for r in items) / len(items)
        avg_dd = sum(r["delivery_delta"] for r in items) / len(items)
        total_strategy_delta += sum(r["strategy_delta"] for r in items)
        total_delivery_delta += sum(r["delivery_delta"] for r in items)
        
        status = "OK"
        if avg_sd < -1.0 or avg_dd < -1.0:
            status = "REGRESSION"
        elif avg_sd < -0.3 or avg_dd < -0.3:
            status = "WARN"
        
        print(f"  {scene:12s} | 策略delta={avg_sd:+.2f} | 成品delta={avg_dd:+.2f} | {status}")
        
        for r in items:
            if r["strategy_delta"] < -1.5 or r["delivery_delta"] < -1.5:
                regressions.append(r["id"])
    
    n = len(results)
    print(f"\n  总计: 策略delta={total_strategy_delta/n:+.2f} | 成品delta={total_delivery_delta/n:+.2f}")
    
    if regressions:
        print(f"\n  [!] 回归条目 ({len(regressions)}): {', '.join(regressions)}")
    else:
        print(f"\n  [OK] 无回归")

    failure_code_distribution = build_failure_code_distribution(results)
    if failure_code_distribution:
        print("\n  失败码分布（按退化条目统计）:")
        for code, count in failure_code_distribution.items():
            print(f"    {code}: {count}")
    else:
        print("\n  失败码分布: 无（未检测到退化失败码）")

    scene_process_summary = build_scene_process_summary(results)
    if scene_process_summary:
        print("\n  场景过程汇总:")
        for scene, item in scene_process_summary.items():
            print(
                "    "
                f"{scene}: entries={item['entries']}, "
                f"avg_repeats={item['avg_repeats']:.2f}, "
                f"failure_runs_entries={item['entries_with_failure_runs']}, "
                f"failure_avoid_entries={item['entries_with_failure_avoid']}, "
                f"failure_avoid_hit_rate={item['avg_failure_avoid_hit_rate']:.2f}, "
                f"memory_failure_hint_entries={item['entries_with_memory_failure_hint']}, "
                f"memory_digest_hint_entries={item['entries_with_memory_digest_hint']}, "
                f"memory_decision_hint_entries={item['entries_with_memory_decision_hint']}, "
                f"degraded={item['degraded_entries']}, "
                f"regressions={item['regression_entries']}, "
                f"progress_injected_entries={item['progress_entries_with_injected_order']}"
            )


def save_report(results: list[dict], repeats: int = 3):
    """保存完整报告"""
    report = {
        "timestamp": time.time(),
        "repeats": max(1, int(repeats)),
        "total_entries": len(results),
        "avg_strategy_delta": round(sum(r["strategy_delta"] for r in results) / len(results), 2),
        "avg_delivery_delta": round(sum(r["delivery_delta"] for r in results) / len(results), 2),
        "regressions": [r["id"] for r in results if r["strategy_delta"] < -1.5 or r["delivery_delta"] < -1.5],
        "failure_code_distribution": build_failure_code_distribution(results),
        "scene_process_summary": build_scene_process_summary(results),
        "results": results,
    }
    
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    
    print(f"\n报告已保存: {REPORT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="运行固定评测集")
    parser.add_argument("--report", action="store_true", help="保存评测报告到 data/eval_report.json")
    parser.add_argument("--repeats", type=int, default=3, help="每条样本重复运行次数（默认3次，取中位数）")
    args = parser.parse_args()

    results = run_eval_set(repeats=args.repeats)
    print_summary(results)
    
    if args.report:
        save_report(results, repeats=args.repeats)
