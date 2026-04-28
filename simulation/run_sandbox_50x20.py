"""
Human-OS Engine 3.0 - 50场×20轮大规模沙盒测试

用法:
    python simulation/run_sandbox_50x20.py
    python simulation/run_sandbox_50x20.py --no-judge    # 关闭LLM Judge加速
    python simulation/run_sandbox_50x20.py --scenes sales emotion  # 只跑指定场景
"""

import argparse
import json
import random
import sys
import time
from pathlib import Path

# 确保项目根目录在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env")

from simulation.sandbox_core import (
    DEFAULT_SANDBOX_SEED,
    ConversationResult,
    MultiTurnSandboxRunner,
    SandboxSummary,
    TurnResult,
    check_guardrails,
    get_test_data,
    summarize_results,
)

# ===== 配置 =====
CONVERSATIONS_PER_SCENE = 13  # 4场景 × 13 ≈ 52场
MAX_ROUNDS = 20
ALL_SCENES = ["sales", "management", "negotiation", "emotion"]


def _collect_output_layer_metrics(results) -> dict:
    """把输出分层里和状态/记忆相关的信号压成可观察汇总。"""
    all_turns = [turn for result in results for turn in getattr(result, "turns", [])]
    total_turns = len(all_turns)
    memory_signal_keys = ["failure_avoid_hint", "experience_digest_hint", "decision_experience_hint"]
    memory_signal_counts = {key: 0 for key in memory_signal_keys}
    order_source_counts: dict[str, int] = {}
    turns_with_output_layers = 0

    for turn in all_turns:
        output_layers = getattr(turn, "output_layers", {}) or {}
        if not isinstance(output_layers, dict):
            continue
        turns_with_output_layers += 1

        signals = output_layers.get("memory_hint_signals", {}) or {}
        for key in memory_signal_keys:
            if signals.get(key, False):
                memory_signal_counts[key] += 1

        order_source = str(output_layers.get("order_source") or "").strip()
        if order_source:
            order_source_counts[order_source] = order_source_counts.get(order_source, 0) + 1

    memory_signal_rates = {
        key: round((count / total_turns) * 100, 1) if total_turns else 0.0
        for key, count in memory_signal_counts.items()
    }
    return {
        "turns_with_output_layers": turns_with_output_layers,
        "memory_hint_signal_counts": memory_signal_counts,
        "memory_hint_signal_rates": memory_signal_rates,
        "order_source_counts": order_source_counts,
    }


def _collect_world_state_metrics(results) -> dict:
    """把每轮的局面快照压成可观察汇总。"""
    all_turns = [turn for result in results for turn in getattr(result, "turns", [])]
    total_turns = len(all_turns)
    stage_counts: dict[str, int] = {}
    progress_counts: dict[str, int] = {}
    risk_counts: dict[str, int] = {}
    commitment_counts: dict[str, int] = {}
    turns_with_world_state = 0
    turns_with_action_loop = 0
    turns_with_next_turn_focus = 0

    def _bump(counter: dict[str, int], value: str) -> None:
        value = (value or "").strip()
        if not value or value in {"未识别", "unknown"}:
            return
        counter[value] = counter.get(value, 0) + 1

    for turn in all_turns:
        world_state = getattr(turn, "world_state_snapshot", {}) or {}
        if not isinstance(world_state, dict):
            continue
        meaningful = False
        for key in ("situation_stage", "progress_state", "risk_level", "commitment_state", "next_turn_focus"):
            value = str(world_state.get(key) or "").strip()
            if value and value not in {"未识别", "观察中", "low", "未形成"}:
                meaningful = True
                break
        if meaningful:
            turns_with_world_state += 1

        _bump(stage_counts, str(world_state.get("situation_stage") or ""))
        _bump(progress_counts, str(world_state.get("progress_state") or ""))
        _bump(risk_counts, str(world_state.get("risk_level") or ""))
        _bump(commitment_counts, str(world_state.get("commitment_state") or ""))

        action_loop_state = str(world_state.get("action_loop_state") or "").strip()
        if action_loop_state:
            turns_with_action_loop += 1

        next_turn_focus = str(world_state.get("next_turn_focus") or "").strip()
        if next_turn_focus:
            turns_with_next_turn_focus += 1

    return {
        "turns_with_world_state": turns_with_world_state,
        "world_state_coverage_rate": round((turns_with_world_state / total_turns) * 100, 1) if total_turns else 0.0,
        "stage_counts": stage_counts,
        "progress_counts": progress_counts,
        "risk_counts": risk_counts,
        "commitment_counts": commitment_counts,
        "turns_with_action_loop": turns_with_action_loop,
        "action_loop_coverage_rate": round((turns_with_action_loop / total_turns) * 100, 1) if total_turns else 0.0,
        "turns_with_next_turn_focus": turns_with_next_turn_focus,
        "next_turn_focus_rate": round((turns_with_next_turn_focus / total_turns) * 100, 1) if total_turns else 0.0,
    }


def _collect_action_loop_metrics(results) -> dict:
    """看动作闭环和下一轮焦点是不是在多轮里真的在动。"""
    all_turns = [turn for result in results for turn in getattr(result, "turns", [])]
    total_turns = len(all_turns)
    action_loop_state_counts: dict[str, int] = {}
    active_goal_turns = 0
    commitment_turns = 0
    focus_turns = 0

    def _bump(counter: dict[str, int], value: str) -> None:
        value = (value or "").strip()
        if not value:
            return
        counter[value] = counter.get(value, 0) + 1

    for turn in all_turns:
        world_state = getattr(turn, "world_state_snapshot", {}) or {}
        if not isinstance(world_state, dict):
            continue

        action_loop_state = str(world_state.get("action_loop_state") or "").strip()
        if action_loop_state:
            _bump(action_loop_state_counts, action_loop_state)

        if str(world_state.get("active_goal") or "").strip():
            active_goal_turns += 1
        if str(world_state.get("commitment_state") or "").strip() not in {"", "未形成"}:
            commitment_turns += 1
        if str(world_state.get("next_turn_focus") or "").strip():
            focus_turns += 1

    return {
        "action_loop_state_counts": action_loop_state_counts,
        "active_goal_turns": active_goal_turns,
        "active_goal_rate": round((active_goal_turns / total_turns) * 100, 1) if total_turns else 0.0,
        "commitment_turns": commitment_turns,
        "commitment_rate": round((commitment_turns / total_turns) * 100, 1) if total_turns else 0.0,
        "focus_turns": focus_turns,
        "focus_rate": round((focus_turns / total_turns) * 100, 1) if total_turns else 0.0,
    }


def _collect_progress_balance_metrics(results) -> dict:
    """看推进/收口阶段里，是不是还过于停在观察。"""
    all_turns = [turn for result in results for turn in getattr(result, "turns", [])]
    forward_stages = {"推进", "收口"}
    passive_progress = {"继续观察", "先观察"}
    forward_stage_turns = 0
    passive_forward_turns = 0

    for turn in all_turns:
        world_state = getattr(turn, "world_state_snapshot", {}) or {}
        if not isinstance(world_state, dict):
            continue
        stage = str(world_state.get("situation_stage") or "").strip()
        progress = str(world_state.get("progress_state") or "").strip()
        if stage not in forward_stages:
            continue
        forward_stage_turns += 1
        if progress in passive_progress:
            passive_forward_turns += 1

    return {
        "forward_stage_turns": forward_stage_turns,
        "passive_forward_turns": passive_forward_turns,
        "passive_forward_rate": round((passive_forward_turns / forward_stage_turns) * 100, 1) if forward_stage_turns else 0.0,
    }


def _collect_disturbance_metrics(results) -> dict:
    """看扰动有没有打进来，以及都是什么类型。"""
    all_turns = [turn for result in results for turn in getattr(result, "turns", [])]
    total_turns = len(all_turns)
    disturbance_turns = 0
    disturbance_type_counts: dict[str, int] = {}

    for turn in all_turns:
        disturbance = getattr(turn, "disturbance_event", {}) or {}
        if not isinstance(disturbance, dict):
            continue
        event_id = str(disturbance.get("event_id") or "").strip()
        if not event_id:
            continue
        disturbance_turns += 1
        disturbance_type_counts[event_id] = disturbance_type_counts.get(event_id, 0) + 1

    return {
        "disturbance_turns": disturbance_turns,
        "disturbance_rate": round((disturbance_turns / total_turns) * 100, 1) if total_turns else 0.0,
        "disturbance_type_counts": disturbance_type_counts,
    }


def _collect_disturbance_response_metrics(results) -> dict:
    """看扰动打进来以后，系统更像在观察、修复，还是继续往前推。"""
    all_turns = [turn for result in results for turn in getattr(result, "turns", [])]
    disturbed_turns = 0
    progress_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}
    commitment_turns = 0
    focus_turns = 0

    def _bump(counter: dict[str, int], value: str) -> None:
        value = (value or "").strip()
        if not value:
            return
        counter[value] = counter.get(value, 0) + 1

    for turn in all_turns:
        disturbance = getattr(turn, "disturbance_event", {}) or {}
        if not isinstance(disturbance, dict) or not str(disturbance.get("event_id") or "").strip():
            continue
        disturbed_turns += 1
        world_state = getattr(turn, "world_state_snapshot", {}) or {}
        if not isinstance(world_state, dict):
            continue

        _bump(progress_counts, str(world_state.get("progress_state") or ""))
        _bump(stage_counts, str(world_state.get("situation_stage") or ""))

        if str(world_state.get("commitment_state") or "").strip() not in {"", "未形成"}:
            commitment_turns += 1
        if str(world_state.get("next_turn_focus") or "").strip():
            focus_turns += 1

    return {
        "disturbed_turns": disturbed_turns,
        "disturbed_progress_counts": progress_counts,
        "disturbed_stage_counts": stage_counts,
        "disturbed_commitment_turns": commitment_turns,
        "disturbed_commitment_rate": round((commitment_turns / disturbed_turns) * 100, 1) if disturbed_turns else 0.0,
        "disturbed_focus_turns": focus_turns,
        "disturbed_focus_rate": round((focus_turns / disturbed_turns) * 100, 1) if disturbed_turns else 0.0,
    }


def _collect_disturbance_recovery_metrics(results) -> dict:
    """看扰动后的下一轮，有没有把局面接回来。"""
    recovery_turns = 0
    progress_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}
    commitment_turns = 0
    focus_turns = 0

    def _bump(counter: dict[str, int], value: str) -> None:
        value = (value or "").strip()
        if not value:
            return
        counter[value] = counter.get(value, 0) + 1

    for result in results:
        turns = list(getattr(result, "turns", []) or [])
        for idx, turn in enumerate(turns[:-1]):
            disturbance = getattr(turn, "disturbance_event", {}) or {}
            if not isinstance(disturbance, dict) or not str(disturbance.get("event_id") or "").strip():
                continue
            next_turn = turns[idx + 1]
            recovery_turns += 1
            world_state = getattr(next_turn, "world_state_snapshot", {}) or {}
            if not isinstance(world_state, dict):
                continue

            _bump(progress_counts, str(world_state.get("progress_state") or ""))
            _bump(stage_counts, str(world_state.get("situation_stage") or ""))

            if str(world_state.get("commitment_state") or "").strip() not in {"", "未形成"}:
                commitment_turns += 1
            if str(world_state.get("next_turn_focus") or "").strip():
                focus_turns += 1

    return {
        "recovery_turns": recovery_turns,
        "recovery_progress_counts": progress_counts,
        "recovery_stage_counts": stage_counts,
        "recovery_commitment_turns": commitment_turns,
        "recovery_commitment_rate": round((commitment_turns / recovery_turns) * 100, 1) if recovery_turns else 0.0,
        "recovery_focus_turns": focus_turns,
        "recovery_focus_rate": round((focus_turns / recovery_turns) * 100, 1) if recovery_turns else 0.0,
    }


def _collect_world_state_transition_metrics(results) -> dict:
    """统计局面在连续多轮里有没有真的发生变化。"""
    tracked_fields = ["situation_stage", "progress_state", "commitment_state", "risk_level", "tension_level", "action_loop_state"]
    field_change_counts = {field: 0 for field in tracked_fields}
    conversations_with_transition = 0
    total_transition_steps = 0

    for result in results:
        prev_snapshot = None
        conversation_transition_steps = 0
        for turn in getattr(result, "turns", []):
            current_snapshot = getattr(turn, "world_state_snapshot", {}) or {}
            if not isinstance(current_snapshot, dict):
                continue
            if prev_snapshot:
                for field in tracked_fields:
                    prev_value = str(prev_snapshot.get(field) or "").strip()
                    current_value = str(current_snapshot.get(field) or "").strip()
                    if current_value and prev_value and current_value != prev_value:
                        field_change_counts[field] += 1
                        conversation_transition_steps += 1
            prev_snapshot = current_snapshot

        if conversation_transition_steps > 0:
            conversations_with_transition += 1
        total_transition_steps += conversation_transition_steps

    total_conversations = len(results)
    return {
        "conversations_with_transition": conversations_with_transition,
        "conversation_transition_rate": round((conversations_with_transition / total_conversations) * 100, 1) if total_conversations else 0.0,
        "total_transition_steps": total_transition_steps,
        "field_change_counts": field_change_counts,
    }

# ===== 扩展的初始输入（让50场更有区分度）=====
EXTRA_INPUTS = {
    "sales": [
        "你们的价格太贵了，竞品便宜 30%",
        "我需要跟老板汇报，让我等消息",
        "我现在用的系统挺好的，为什么要换？",
        "你们能保证实施不延期吗？上次被坑过",
        "我预算有限，能不能分期付款？",
        "你们和XX比到底强在哪？给我一个理由",
        "我之前用过类似产品，体验很差，不敢再试",
        "能不能先免费试用三个月？",
        "我们团队没人会用，培训成本太高",
        "合同条款太苛刻了，特别是违约金那块",
        "你们的数据安全怎么保证？我们有合规要求",
        "我需要看真实的客户案例，不是PPT那种",
        "这个方案听起来不错，但我需要时间消化",
    ],
    "management": [
        "我觉得自己不适合这份工作",
        "为什么总是给我安排这么多任务？",
        "我觉得团队氛围越来越差了",
        "我提了三次加薪申请都没回应",
        "跨部门协作太困难了，都在推诿",
        "新来的领导完全不懂业务，瞎指挥",
        "我想转岗，但HR说没有合适位置",
        "团队里有人摸鱼，但没人管",
        "加班太多了，我已经连续三个月没休息",
        "我觉得公司的战略方向有问题",
        "我的建议从来不被采纳，说了也没用",
        "绩效评估标准不公平，完全看领导喜好",
        "我想离职，但又怕找不到更好的",
    ],
    "negotiation": [
        "这个价格我们接受不了，最多只能给 70%",
        "如果你们不让步，我们就找别家了",
        "我们需要 90 天账期，否则不签",
        "你们的竞品报价比你们低 20%",
        "这个条款对我们太不利了，必须改",
        "我们要求独家代理权，否则免谈",
        "能不能把服务期从2年缩短到1年？",
        "我需要回去和合伙人商量，不能现在定",
        "你们的质量问题我们还没解决，先别谈新合同",
        "如果量再大一点，价格还能再降吗？",
        "我们更倾向按效果付费，而不是固定费用",
        "这个方案风险太大，我们需要更多保障",
        "先签个意向书吧，正式合同慢慢谈",
    ],
    "emotion": [
        "你根本就不爱我，否则怎么可能忘了纪念日？",
        "没有她我真的活不下去了",
        "我看着电脑就想吐，但我没法辞职",
        "我爸妈永远觉得我不够好，不管我怎么做",
        "我好像对什么都提不起兴趣了",
        "每次吵架他都冷暴力，好几天不说话",
        "我觉得自己是个失败者，什么都做不好",
        "朋友都比我过得好，我越来越不想社交",
        "我控制不住发脾气，发完又特别后悔",
        "孩子不跟我亲，我觉得自己是个糟糕的父母",
        "我总是讨好别人，但没人真正在乎我",
        "分手三个月了，我还是每天哭",
        "我害怕建立新关系，每次都被伤害",
    ],
}


def run_large_scale_sandbox(
    scenes: list[str],
    conversations_per_scene: int,
    max_rounds: int,
    use_llm_judge: bool,
    seed: int,
) -> dict:
    """运行大规模沙盒测试"""
    
    all_results: dict[str, list[ConversationResult]] = {}
    total_start = time.time()
    
    total_conversations = len(scenes) * conversations_per_scene
    completed = 0
    
    print(f"\n{'='*70}")
    print(f"  Human-OS Engine 大规模沙盒测试")
    print(f"  场景: {', '.join(scenes)}")
    print(f"  每场景对话数: {conversations_per_scene}")
    print(f"  每对话最大轮数: {max_rounds}")
    print(f"  总对话数: {total_conversations}")
    print(f"  LLM Judge: {'开启' if use_llm_judge else '关闭'}")
    print(f"  随机种子: {seed}")
    print(f"{'='*70}\n")
    
    for scene_id in scenes:
        scene_start = time.time()
        test_data = get_test_data(scene_id)
        personas = test_data["personas"]
        
        # 使用扩展输入（如果有的话），否则用原始输入
        inputs = EXTRA_INPUTS.get(scene_id, test_data["inputs"])
        
        runner = MultiTurnSandboxRunner(
            scene_id=scene_id,
            max_rounds=max_rounds,
            use_llm_judge=use_llm_judge,
            seed=seed,
        )
        
        scene_results: list[ConversationResult] = []
        
        for conv_idx in range(conversations_per_scene):
            # 循环选择 persona 和 input
            persona = personas[conv_idx % len(personas)]
            initial_input = inputs[conv_idx % len(inputs)]
            
            conv_start = time.time()
            result = runner.run_conversation(persona, initial_input)
            conv_elapsed = time.time() - conv_start
            
            scene_results.append(result)
            completed += 1
            
            # 实时进度
            avg_score = result.avg_llm_score
            outcome_icon = "OK" if result.outcome == "success" else "FAIL"
            violations_str = f" | 护栏:{result.total_violations}" if result.total_violations > 0 else ""
            print(
                f"  [{completed:3d}/{total_conversations}] "
                f"{scene_id:12s} | {persona['name']:8s} | "
                f"{result.total_rounds:2d}轮 | "
                f"评分:{avg_score:4.1f} | "
                f"{outcome_icon}{violations_str} | "
                f"耗时:{conv_elapsed:.1f}s"
            )
        
        all_results[scene_id] = scene_results
        scene_elapsed = time.time() - scene_start
        summary = summarize_results(scene_id, scene_results)
        
        print(f"\n  --- {scene_id} 场景汇总 ---")
        print(f"  成功: {summary.success_count}/{summary.total_conversations}")
        print(f"  失败: {summary.failure_count}")
        print(f"  超时: {summary.timeout_count}")
        print(f"  平均评分: {summary.avg_score:.1f}/10")
        print(f"  护栏违规: {summary.total_violations}")
        print(f"  场景耗时: {scene_elapsed:.1f}s\n")
    
    total_elapsed = time.time() - total_start
    
    # ===== 全局汇总 =====
    print(f"\n{'='*70}")
    print(f"  全局汇总")
    print(f"{'='*70}")
    
    global_summary = {
        "config": {
            "scenes": scenes,
            "conversations_per_scene": conversations_per_scene,
            "max_rounds": max_rounds,
            "use_llm_judge": use_llm_judge,
            "seed": seed,
            "total_conversations": total_conversations,
        },
        "scenes": {},
        "global": {},
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_elapsed_seconds": round(total_elapsed, 1),
    }
    
    all_scores = []
    all_violations = 0
    all_success = 0
    all_failure = 0
    all_timeout = 0
    all_rounds = 0
    
    for scene_id, results in all_results.items():
        summary = summarize_results(scene_id, results)
        
        # 按persona细分
        persona_stats = {}
        for r in results:
            name = r.persona_name
            if name not in persona_stats:
                persona_stats[name] = {"count": 0, "scores": [], "violations": 0, "rounds": []}
            persona_stats[name]["count"] += 1
            persona_stats[name]["scores"].append(r.avg_llm_score)
            persona_stats[name]["violations"] += r.total_violations
            persona_stats[name]["rounds"].append(r.total_rounds)
        
        scene_detail = {
            "success": summary.success_count,
            "failure": summary.failure_count,
            "timeout": summary.timeout_count,
            "avg_score": round(summary.avg_score, 2),
            "total_violations": summary.total_violations,
            "signal_metrics": _collect_output_layer_metrics(results),
            "world_state_metrics": _collect_world_state_metrics(results),
            "action_loop_metrics": _collect_action_loop_metrics(results),
            "world_state_transition_metrics": _collect_world_state_transition_metrics(results),
            "progress_balance_metrics": _collect_progress_balance_metrics(results),
            "disturbance_metrics": _collect_disturbance_metrics(results),
            "disturbance_response_metrics": _collect_disturbance_response_metrics(results),
            "disturbance_recovery_metrics": _collect_disturbance_recovery_metrics(results),
            "personas": {},
        }
        
        for pname, pstat in persona_stats.items():
            scene_detail["personas"][pname] = {
                "count": pstat["count"],
                "avg_score": round(sum(pstat["scores"]) / len(pstat["scores"]), 2),
                "avg_rounds": round(sum(pstat["rounds"]) / len(pstat["rounds"]), 1),
                "violations": pstat["violations"],
            }
        
        global_summary["scenes"][scene_id] = scene_detail
        
        all_scores.extend(r.avg_llm_score for r in results)
        all_violations += summary.total_violations
        all_success += summary.success_count
        all_failure += summary.failure_count
        all_timeout += summary.timeout_count
        all_rounds += sum(r.total_rounds for r in results)
    
    global_summary["global"] = {
        "total_conversations": total_conversations,
        "total_rounds": all_rounds,
        "success_rate": round(all_success / total_conversations * 100, 1),
        "failure_rate": round(all_failure / total_conversations * 100, 1),
        "timeout_rate": round(all_timeout / total_conversations * 100, 1),
        "avg_score": round(sum(all_scores) / len(all_scores), 2) if all_scores else 0,
        "total_violations": all_violations,
        "avg_rounds_per_conversation": round(all_rounds / total_conversations, 1),
        "signal_metrics": _collect_output_layer_metrics(
            [result for results in all_results.values() for result in results]
        ),
        "world_state_metrics": _collect_world_state_metrics(
            [result for results in all_results.values() for result in results]
        ),
        "action_loop_metrics": _collect_action_loop_metrics(
            [result for results in all_results.values() for result in results]
        ),
        "world_state_transition_metrics": _collect_world_state_transition_metrics(
            [result for results in all_results.values() for result in results]
        ),
        "progress_balance_metrics": _collect_progress_balance_metrics(
            [result for results in all_results.values() for result in results]
        ),
        "disturbance_metrics": _collect_disturbance_metrics(
            [result for results in all_results.values() for result in results]
        ),
        "disturbance_response_metrics": _collect_disturbance_response_metrics(
            [result for results in all_results.values() for result in results]
        ),
        "disturbance_recovery_metrics": _collect_disturbance_recovery_metrics(
            [result for results in all_results.values() for result in results]
        ),
    }
    
    # 打印全局汇总
    g = global_summary["global"]
    print(f"  总对话数: {g['total_conversations']}")
    print(f"  总轮次数: {g['total_rounds']}")
    print(f"  成功率: {g['success_rate']}%")
    print(f"  失败率: {g['failure_rate']}%")
    print(f"  超时率: {g['timeout_rate']}%")
    print(f"  平均评分: {g['avg_score']}/10")
    print(f"  平均轮次: {g['avg_rounds_per_conversation']}")
    print(f"  护栏违规总数: {g['total_violations']}")
    print(f"  总耗时: {total_elapsed:.1f}s ({total_elapsed/60:.1f}min)")
    
    # 按场景打印
    print(f"\n  各场景详情:")
    for scene_id, detail in global_summary["scenes"].items():
        print(f"    {scene_id:12s} | 评分:{detail['avg_score']:4.2f} | "
              f"成功:{detail['success']}/{detail['success']+detail['failure']+detail['timeout']} | "
              f"违规:{detail['total_violations']}")
        for pname, pstat in detail["personas"].items():
            print(f"      {pname:10s} | 评分:{pstat['avg_score']:4.2f} | "
                  f"平均{pstat['avg_rounds']:4.1f}轮 | 违规:{pstat['violations']}")
    
    # ===== 保存结果 =====
    output_dir = PROJECT_ROOT / "data"
    output_dir.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"sandbox_50x20_{timestamp}.json"
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(global_summary, f, ensure_ascii=False, indent=2)
    print(f"\n  结果已保存: {output_file}")
    
    # 保存详细对话记录
    detail_file = output_dir / f"sandbox_50x20_detail_{timestamp}.json"
    detail_data = {}
    for scene_id, results in all_results.items():
        detail_data[scene_id] = []
        for r in results:
            conv = {
                "persona": r.persona_name,
                "outcome": r.outcome,
                "avg_score": r.avg_llm_score,
                "total_rounds": r.total_rounds,
                "violations": r.total_violations,
                "turns": [
                    {
                        "round": t.round_num,
                        "user": t.user_input[:100],
                        "system": t.system_output[:200],
                        "score": t.llm_score,
                        "strategy": t.strategy_score,
                        "delivery": t.delivery_score,
                        "violations": len(t.guardrail_violations),
                        "output_layers": {
                            "order_source": (t.output_layers or {}).get("order_source", ""),
                            "memory_hint_signals": (t.output_layers or {}).get("memory_hint_signals", {}),
                            "failure_avoid_codes": (t.output_layers or {}).get("failure_avoid_codes", []),
                        } if isinstance(t.output_layers, dict) else {},
                        "world_state_snapshot": getattr(t, "world_state_snapshot", {}) if isinstance(getattr(t, "world_state_snapshot", {}), dict) else {},
                    }
                    for t in r.turns
                ],
            }
            detail_data[scene_id].append(conv)
    
    with open(detail_file, "w", encoding="utf-8") as f:
        json.dump(detail_data, f, ensure_ascii=False, indent=2)
    print(f"  详细记录已保存: {detail_file}")
    
    return global_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Human-OS Engine 50×20 大规模沙盒")
    parser.add_argument(
        "--scenes",
        nargs="*",
        default=ALL_SCENES,
        choices=ALL_SCENES,
        help="要测试的场景（默认全部）",
    )
    parser.add_argument(
        "--conversations",
        type=int,
        default=CONVERSATIONS_PER_SCENE,
        help=f"每场景对话数（默认{CONVERSATIONS_PER_SCENE}）",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=MAX_ROUNDS,
        help=f"每对话最大轮数（默认{MAX_ROUNDS}）",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="关闭 LLM Judge（加速约2倍）",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=DEFAULT_SANDBOX_SEED,
        help="随机种子",
    )
    args = parser.parse_args()
    
    run_large_scale_sandbox(
        scenes=args.scenes,
        conversations_per_scene=args.conversations,
        max_rounds=args.rounds,
        use_llm_judge=not args.no_judge,
        seed=args.seed,
    )
