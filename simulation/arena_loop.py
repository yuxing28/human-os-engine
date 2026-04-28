"""
Human-OS Engine - 对抗主循环（MVP）

驱动系统与用户代理交替对话，记录每轮状态。
"""

import time
import random
import os
import sys
from typing import Optional

# 确保项目根目录在 sys.path 中（human-os-engine/ 是项目根目录）
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 如果 simulation/ 在 ninv/ 下，需要找到 human-os-engine/
for d in [_project_root, os.path.join(_project_root, 'human-os-engine')]:
    if os.path.isdir(os.path.join(d, 'schemas')):
        _project_root = d
        break
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

from simulation.user_agent import UserAgent
from simulation.recorder import Recorder
from simulation.sandbox_core import check_guardrails
from modules.engine_runtime import EngineRequest, EngineRuntime
from schemas.context import Context


def run_system_once(user_input: str, context: Context, runtime: EngineRuntime) -> dict:
    """
    调用系统核心（LangGraph），返回输出和上下文快照。
    使用快照对比法提取本轮使用的武器。
    """
    # 快照：调用前的武器计数
    weapons_before = dict(context.weapon_usage_count)
    engine_result = runtime.run_stream(
        EngineRequest(session_id=context.session_id, user_input=user_input, context=context)
    )
    result = engine_result.raw_result
    ctx = engine_result.context

    # 提取武器使用信息（对比快照）
    weapons_used = []
    weapons_after = ctx.weapon_usage_count
    for weapon_name, count_after in weapons_after.items():
        count_before = weapons_before.get(weapon_name, 0)
        if count_after > count_before:
            # 本轮使用了该武器
            # 从武器库获取类型信息
            try:
                from modules.L3.weapon_arsenal import get_weapon
                weapon = get_weapon(weapon_name)
                weapon_type = weapon.type.value if weapon and weapon.type else ""
            except:
                weapon_type = ""
            weapons_used.append({
                "name": weapon_name,
                "type": weapon_type,
                "count_delta": count_after - count_before,
            })

    # 构建上下文快照
    priority = result.get("priority", {})
    context_snapshot = {
        "goal_description": ctx.goal.current.description if ctx.goal.current else "",
        "mode": ctx.self_state.energy_mode.value if hasattr(ctx.self_state.energy_mode, 'value') else str(ctx.self_state.energy_mode),
        "priority": priority.get("priority_type", "") if priority else "",
        "output": result.get("output", ""),
    }

    return {
        "output": engine_result.output,
        "context": ctx,
        "context_snapshot": context_snapshot,
        "weapons_used": weapons_used,
    }


def run_arena(scenario: str, agent_config_path: str, max_rounds: int = 15,
              trace_id: Optional[str] = None) -> dict:
    """
    运行一场对抗，返回结果摘要。
    """
    if trace_id is None:
        trace_id = f"arena_{scenario}_{int(time.time())}_{random.randint(1000, 9999)}"

    # 初始化系统上下文（模拟模式）
    context = Context(session_id=trace_id)
    from graph.builder import build_graph
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)

    # 初始化代理和记录器
    agent = UserAgent(agent_config_path)
    recorder = Recorder(trace_id)

    # 系统开场
    system_output = f"你好，我是你的专属顾问。请问有什么可以帮你？"

    # 代理第一轮攻击（使用配置中的 first_input）
    agent_config_data = agent.config
    first_input = agent_config_data.get("first_input", "")

    prev_trust = agent.state["trust"]
    prev_emotion = agent.state["emotion"]["intensity"]

    # 统计数据收集
    all_weapons_used = []  # 所有使用的武器名称
    mode_sequence = []  # 模式切换序列
    corrections_triggered = 0  # 纠正权触发次数
    resistance_events = 0  # 阻力事件数
    resistance_resolved = 0  # 阻力成功应对数
    total_violations = 0  # 护栏违规总数
    critical_violations = 0  # 关键违规总数
    guardrail_terminated = False  # 是否因关键违规提前结束
    prev_mode = None
    guardrail_scene = _resolve_guardrail_scene(scenario)

    # 对抗循环
    for round_num in range(max_rounds):
        # 代理回应（第一轮使用配置中的 first_input）
        if round_num == 0 and first_input:
            agent_input = first_input
            agent_result = agent.generate_reply(system_output, [])
        else:
            agent_result = agent.generate_reply(system_output, [])
            agent_input = agent_result["reply"]

        # 系统决策
        try:
            sys_result = run_system_once(agent_input, context, runtime)
            system_output = sys_result["output"]
            weapons_used = sys_result["weapons_used"]
            context_snapshot = sys_result["context_snapshot"]
            context = sys_result["context"]
        except Exception as e:
            system_output = f"[系统错误: {str(e)[:100]}]"
            weapons_used = []
            context_snapshot = {"goal_description": "", "mode": "", "priority": "", "output": system_output}

        # 收集统计数据
        for w in weapons_used:
            all_weapons_used.append(w.get("name", ""))

        current_mode = context_snapshot.get("mode", "")
        if current_mode and current_mode != prev_mode:
            mode_sequence.append(current_mode)
            prev_mode = current_mode

        # 检测纠正权触发（系统输出包含纠正话术特征）
        correction_keywords = ["矛盾", "想清楚", "情绪激动", "聊不出结果", "停下来"]
        if any(kw in system_output for kw in correction_keywords):
            corrections_triggered += 1

        # 检测阻力事件和应对
        if agent_result["delta"].get("trust_change", 0) < -0.03:
            resistance_events += 1
            # 如果后续信任回升，视为成功应对（简化判断）
            if agent_result["delta"].get("trust_change", 0) > -0.02:
                resistance_resolved += 1

        # 重新计算 delta（因为 agent.generate_reply 已经更新了状态）
        delta = agent_result["delta"]

        # 护栏检查（与主沙盒同一套规则）
        violations = check_guardrails(system_output, scene_id=guardrail_scene)
        total_violations += len(violations)
        critical_hits = [v for v in violations if v.get("severity") == "critical"]
        critical_violations += len(critical_hits)
        if violations:
            delta = dict(delta)
            delta["violations"] = violations

        # 【修复2】将信任变化传递给 context，用于 feedback 推断
        context.last_feedback_trust_change = delta.get("trust_change", 0)

        # 记录
        recorder.record_step(
            round_num=round_num,
            agent_state=agent_result["state"],
            system_context=context_snapshot,
            agent_input=agent_input,
            system_output=system_output,
            weapons_used=weapons_used,
            delta=delta,
        )

        # 关键违规优先终止
        if critical_hits:
            guardrail_terminated = True
            break

        # 检查终止条件
        if _is_terminal(context, agent, round_num, max_rounds):
            break

    # 最终评估（传入统计数据）
    stats = {
        "weapons_used": all_weapons_used,
        "mode_sequence": mode_sequence,
        "corrections_triggered": corrections_triggered,
        "resistance_events": resistance_events,
        "resistance_resolved": resistance_resolved,
        "total_violations": total_violations,
        "critical_violations": critical_violations,
        "guardrail_terminated": guardrail_terminated,
    }
    result = _evaluate(context, agent, stats)
    result["trace_id"] = trace_id
    result["total_rounds"] = round_num + 1
    recorder.record_outcome(result)
    recorder.close()

    return result


def _is_terminal(context: Context, agent: UserAgent, round_num: int, max_rounds: int) -> bool:
    """检查是否达到终止条件"""
    # 达到最大轮数
    if round_num >= max_rounds - 1:
        return True
    # 代理情绪崩溃且信任极低
    if agent.state["emotion"]["intensity"] > 0.95 and agent.state["trust"] < 0.1:
        return True
    return False


def _resolve_guardrail_scene(scenario: str) -> str:
    """将历史场景名归一到主沙盒四大场景。"""
    value = (scenario or "").lower()
    if "emotion" in value:
        return "emotion"
    if "negotiation" in value:
        return "negotiation"
    if "manage" in value:
        return "management"
    return "sales"


def _evaluate(context: Context, agent: UserAgent, stats: dict = None) -> dict:
    """
    评估对抗结果（增强版）
    
    Args:
        context: 系统上下文
        agent: 用户代理
        stats: 统计数据（武器使用、模式切换、纠正权触发等）
    """
    if stats is None:
        stats = {}

    trust_final = agent.state["trust"]
    emotion_final = agent.state["emotion"]["intensity"]
    trust_initial = 0.3  # 默认初始信任
    emotion_initial = 0.6  # 默认初始情绪

    # 简单胜负判定（校准版：更接近真实对话效果）
    if trust_final > 0.4 and emotion_final < 0.6:
        outcome = "system_win"
    elif emotion_final > 0.95 and trust_final < 0.1:
        outcome = "agent_win"
    else:
        outcome = "draw"

    # 武器多样性统计
    weapons_used = stats.get("weapons_used", [])
    unique_weapons = set(weapons_used)
    weapon_diversity = len(unique_weapons)

    # 武器使用分布
    weapon_counts = {}
    for w in weapons_used:
        weapon_counts[w] = weapon_counts.get(w, 0) + 1

    # 模式切换次数
    mode_sequence = stats.get("mode_sequence", [])
    mode_switches = max(0, len(mode_sequence) - 1)

    # 纠正权触发次数
    corrections = stats.get("corrections_triggered", 0)
    total_violations = stats.get("total_violations", 0)
    critical_violations = stats.get("critical_violations", 0)
    guardrail_terminated = stats.get("guardrail_terminated", False)

    # 阻力应对成功率
    resistance_events = stats.get("resistance_events", 0)
    resistance_resolved = stats.get("resistance_resolved", 0)
    resistance_success_rate = resistance_resolved / max(resistance_events, 1)

    # 单轮平均武器数
    total_rounds = max(len(weapons_used), 1)
    avg_weapons_per_round = len(weapons_used) / total_rounds

    return {
        "outcome": outcome,
        "trust_final": round(trust_final, 3),
        "trust_initial": trust_initial,
        "trust_change": round(trust_final - trust_initial, 3),
        "emotion_final": round(emotion_final, 3),
        "emotion_initial": emotion_initial,
        "emotion_change": round(emotion_final - emotion_initial, 3),
        "weapon_diversity": weapon_diversity,
        "weapon_counts": weapon_counts,
        "mode_sequence": mode_sequence,
        "mode_switches": mode_switches,
        "corrections_triggered": corrections,
        "resistance_events": resistance_events,
        "resistance_resolved": resistance_resolved,
        "resistance_success_rate": round(resistance_success_rate, 3),
        "avg_weapons_per_round": round(avg_weapons_per_round, 2),
        "total_violations": total_violations,
        "critical_violations": critical_violations,
        "guardrail_terminated": guardrail_terminated,
    }
