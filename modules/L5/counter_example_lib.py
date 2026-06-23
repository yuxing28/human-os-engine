"""
Human-OS Engine 3.0 — 反例库模块

负责记录失败策略，并在策略选择时提供惩罚因子，避免重复失败。
支持失败模式分类：识别错/情境错/身份错/层序错/叙事错/时机错/安全错。
"""

import os
import time
from enum import Enum
from pathlib import Path
from typing import Dict
from utils.file_lock import safe_json_read, safe_json_write


class FailureType(str, Enum):
    """失败模式分类 — 由 llm_judge 评分维度自动推断"""
    IDENTIFICATION_ERROR = "identification_error"   # 识别错（relevance低）
    SITUATION_ERROR = "situation_error"             # 情境判断错
    IDENTITY_ERROR = "identity_error"               # 身份位置错
    LAYER_ORDER_ERROR = "layer_order_error"         # 层顺序错
    NARRATIVE_ERROR = "narrative_error"             # 叙事送错（empathy低）
    TIMING_ERROR = "timing_error"                   # 推进时机错（guidance低）
    SAFETY_ERROR = "safety_error"                   # 安全违规


class FailureCode(str, Enum):
    """统一失败编号（对齐未来方向 F01~F10）"""
    F01_SURFACE_GOAL_BIAS = "F01"   # 目标识别偏表层
    F02_EARLY_PUSH = "F02"          # 时机误判，推进过早
    F03_MISSING_REPAIR = "F03"      # 关系脆弱但缺承接
    F04_MISSING_QUESTION = "F04"    # 信息缺口明显却直接给方案
    F05_HEAVY_RHYTHM = "F05"        # 输出节奏过重
    F06_LOOSE_RHYTHM = "F06"        # 输出节奏过散
    F07_INTERNAL_LEAK = "F07"       # 内部术语残留
    F08_SCENE_WEAPON_MISMATCH = "F08"  # 场景武器错配
    F09_OVER_EMPATHY = "F09"        # 过度共情，拖慢推进
    F10_OVER_PUSH = "F10"           # 过度推进，压坏关系


def infer_failure_type(judge_result: dict) -> FailureType:
    """根据 llm_judge 评分维度自动推断失败类型"""
    relevance = float(judge_result.get("relevance", 5))
    empathy = float(judge_result.get("empathy", 5))
    guidance = float(judge_result.get("guidance", 5))
    safety = float(judge_result.get("safety", 5))
    
    if safety < 5:
        return FailureType.SAFETY_ERROR
    if relevance < 5:
        return FailureType.IDENTIFICATION_ERROR
    if empathy < 5:
        return FailureType.NARRATIVE_ERROR
    if guidance < 5:
        return FailureType.TIMING_ERROR
    # 默认归为时机错
    return FailureType.TIMING_ERROR


def infer_failure_code(
    judge_result: dict,
    context: dict | None = None,
    output_text: str = "",
) -> FailureCode | None:
    """
    推断统一失败编号（F01~F10）。

    说明：
    - 先看硬风险（安全、相关性、引导、共情）
    - 再看文本迹象（内部术语、节奏问题）
    - 最后回落到时机/推进类
    """
    context = context or {}
    relevance = float(judge_result.get("relevance", 5))
    empathy = float(judge_result.get("empathy", 5))
    guidance = float(judge_result.get("guidance", 5))
    safety = float(judge_result.get("safety", 5))
    overall = float(judge_result.get("overall", 5))
    text = output_text or ""

    if safety < 5:
        return FailureCode.F10_OVER_PUSH
    if relevance < 4.5:
        return FailureCode.F01_SURFACE_GOAL_BIAS
    if guidance < 4.5:
        return FailureCode.F02_EARLY_PUSH
    if empathy < 4.5:
        return FailureCode.F03_MISSING_REPAIR

    if any(token in text for token in ["当前目标", "当前重点", "先别做", "知识参考", "案例参考", "表达模式"]):
        return FailureCode.F07_INTERNAL_LEAK

    compact_len = len(text.replace("\n", "").replace(" ", ""))
    # 只有当整体质量已出现下滑迹象时，才把长度问题判成失败码，
    # 避免把高分正常回复误标成 F05/F06。
    if compact_len > 260 and (overall < 8 or empathy < 7):
        return FailureCode.F05_HEAVY_RHYTHM
    if 0 < compact_len < 20 and (overall < 8 or guidance < 7):
        return FailureCode.F06_LOOSE_RHYTHM

    if context.get("missing_info", False):
        return FailureCode.F04_MISSING_QUESTION
    if context.get("scene_mismatch", False):
        return FailureCode.F08_SCENE_WEAPON_MISMATCH
    if context.get("over_empathy", False):
        return FailureCode.F09_OVER_EMPATHY
    if context.get("over_push", False):
        return FailureCode.F10_OVER_PUSH

    if overall <= 5:
        return FailureCode.F02_EARLY_PUSH
    return None

COUNTER_EXAMPLES_DIR = "skills"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _resolve_counter_examples_dir() -> Path:
    """解析反例库根目录，默认锚定到项目根目录。"""
    path = Path(COUNTER_EXAMPLES_DIR)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()

def _get_path(scene_id: str) -> Path:
    """获取反例库文件路径"""
    return _resolve_counter_examples_dir() / scene_id / "counter_examples.json"


def _get_valid_targets(scene_id: str) -> tuple[set[str], set[str]]:
    """
    获取场景允许的目标和策略。

    目标按场景配置校验。
    策略按全局组合库和场景配置共同校验，避免把串场或脏数据写进惩罚逻辑。
    """
    valid_goals: set[str] = set()
    valid_strategies: set[str] = set()

    try:
        from modules.L5.scene_loader import load_scene_config

        scene_config = load_scene_config(scene_id)
        valid_goals = {goal.granular_goal for goal in scene_config.goal_taxonomy}
        valid_strategies.update(scene_config.default_strategy_weights.keys())

        for goal in scene_config.goal_taxonomy:
            valid_strategies.update(
                pref.get("combo", "")
                for pref in goal.strategy_preferences
                if pref.get("combo")
            )
            forced_combo = getattr(goal, "forced_combo", None)
            if forced_combo:
                valid_strategies.add(forced_combo)
            valid_strategies.update(getattr(goal, "banned_combos", []))
    except Exception:
        pass

    try:
        from modules.L3 import strategy_combinations as combos

        combo_groups = (
            combos.HOOK_COMBOS,
            combos.AMPLIFY_COMBOS,
            combos.LOWER_COMBOS,
            combos.UPGRADE_COMBOS,
            combos.DEFENSE_COMBOS,
            combos.ATTENTION_COMBOS,
            combos.SALES_COMBOS,
        )
        for group in combo_groups:
            valid_strategies.update(group.keys())
    except Exception:
        pass

    return valid_goals, valid_strategies


def _sanitize_examples(scene_id: str, examples: list) -> list[dict]:
    """过滤掉不合法或明显串场的反例数据。"""
    if not isinstance(examples, list):
        return []

    valid_goals, valid_strategies = _get_valid_targets(scene_id)
    cleaned: list[dict] = []

    for example in examples:
        if not isinstance(example, dict):
            continue

        goal = example.get("goal", "")
        strategy = example.get("strategy", "")
        context = example.get("context", {})
        timestamp = example.get("timestamp", 0)
        failure_type = example.get("failure_type", "")
        failure_code = example.get("failure_code", "")
        attribution = example.get("attribution", {})

        if not isinstance(goal, str) or not goal:
            continue
        if valid_goals and goal not in valid_goals:
            continue

        if not isinstance(strategy, str) or not strategy:
            continue
        if valid_strategies and strategy not in valid_strategies:
            continue

        if not isinstance(context, dict):
            context = {}

        if not isinstance(timestamp, (int, float)):
            timestamp = 0
        if not isinstance(failure_type, str):
            failure_type = ""
        if not isinstance(failure_code, str):
            failure_code = ""
        if not isinstance(attribution, dict):
            attribution = {}

        cleaned.append(
            {
                "goal": goal,
                "strategy": strategy,
                "context": context,
                "failure_type": failure_type,
                "failure_code": failure_code,
                "attribution": attribution,
                "timestamp": timestamp,
            }
        )

    return cleaned

def record_failure(
    scene_id: str,
    goal: str,
    strategy: str,
    context: dict,
    failure_type: str = "",
    failure_code: str = "",
    attribution: dict | None = None,
):
    """
    记录策略失败
    
    Args:
        scene_id: 场景 ID
        goal: 细粒度目标
        strategy: 策略组合名称
        context: 上下文信息 (如情绪、信任等级)
        failure_type: 失败模式分类 (FailureType 枚举值)
        failure_code: 失败编号（F01~F10）
        attribution: 统一归因记录（改动-结果-归因结构）
    """
    path = _get_path(scene_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    examples = safe_json_read(str(path), [])
    examples = _sanitize_examples(scene_id, examples)
            
    examples.append({
        "goal": goal,
        "strategy": strategy,
        "context": context,
        "failure_type": failure_type,
        "failure_code": failure_code,
        "attribution": attribution or {},
        "timestamp": time.time()
    })
    examples = _sanitize_examples(scene_id, examples)
    
    # 限制大小，保留最近 100 条
    if len(examples) > 100:
        examples = examples[-100:]
        
    safe_json_write(str(path), examples)

def get_strategy_penalties(scene_id: str, goal: str, context: dict) -> Dict[str, float]:
    """
    获取策略惩罚因子
    
    Returns:
        dict: {strategy_name: penalty_factor}
        penalty_factor 范围 0.0 - 1.0。0.0 表示排除，1.0 表示无惩罚。
    """
    path = _get_path(scene_id)
    if not path.exists():
        return {}
        
    examples = safe_json_read(str(path), [])
    cleaned_examples = _sanitize_examples(scene_id, examples)
    if cleaned_examples != examples:
        safe_json_write(str(path), cleaned_examples)
    examples = cleaned_examples
    if not examples:
        return {}
        
    penalties = {}
    now = time.time()
    window = 3600 * 2  # 2 小时窗口视为“近期”
    
    # 统计近期失败次数
    failure_counts = {}
    
    for ex in examples:
        if ex.get("goal") != goal:
            continue
        ts = ex.get("timestamp", 0)
        if now - ts > window:
            continue
        ex_ctx = ex.get("context", {})
        ex_emotion = ex_ctx.get("emotion", "")
        ctx_emotion = context.get("emotion", "")
        if not ex_emotion or ex_emotion == ctx_emotion:
            strat = ex.get("strategy", "")
            if strat:
                failure_counts[strat] = failure_counts.get(strat, 0) + 1
    
    # 计算惩罚因子
    for strat, count in failure_counts.items():
        if count >= 3:
            penalties[strat] = 0.0  # 近期失败 3 次以上，强制排除
        elif count == 2:
            penalties[strat] = 0.2  # 失败 2 次，重度惩罚
        elif count == 1:
            penalties[strat] = 0.6  # 失败 1 次，轻度惩罚
            
    return penalties


# ============================================================
# 方向C-1: 成功策略谱沉淀
# ============================================================

def _get_success_path(scene_id: str) -> Path:
    """获取成功策略谱文件路径"""
    return _resolve_counter_examples_dir() / scene_id / "success_spectrum.json"


def record_success(scene_id: str, goal: str, strategy: str, context: dict, score: float = 0.0):
    """
    记录策略成功（方向C-1）
    
    Args:
        scene_id: 场景 ID
        goal: 细粒度目标
        strategy: 策略组合名称
        context: 上下文信息 (如情绪、信任等级)
        score: 评分 (0-10)
    """
    path = _get_success_path(scene_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    
    records = safe_json_read(str(path), [])
    
    records.append({
        "goal": goal,
        "strategy": strategy,
        "context": context,
        "score": score,
        "timestamp": time.time()
    })
    
    # 限制大小，保留最近 200 条
    if len(records) > 200:
        records = records[-200:]
    
    safe_json_write(str(path), records)


def get_strategy_bonuses(scene_id: str, goal: str, context: dict) -> Dict[str, float]:
    """
    获取策略奖励因子（方向C-1）
    
    Returns:
        dict: {strategy_name: bonus_factor}
        bonus_factor 范围 1.0 - 1.3。1.0 表示无奖励。
    """
    path = _get_success_path(scene_id)
    if not path.exists():
        return {}
    
    records = safe_json_read(str(path), [])
    if not records:
        return {}
    
    bonuses = {}
    now = time.time()
    window = 3600 * 4  # 4 小时窗口视为"近期"
    
    # 统计近期成功次数和平均分
    success_stats = {}  # {strategy: {"count": n, "total_score": s}}
    
    for rec in records:
        if rec.get("goal") != goal:
            continue
        ts = rec.get("timestamp", 0)
        if now - ts > window:
            continue
        ex_ctx = rec.get("context", {})
        ex_emotion = ex_ctx.get("emotion", "")
        ctx_emotion = context.get("emotion", "")
        # 情绪匹配或无情绪记录时都算
        if not ex_emotion or ex_emotion == ctx_emotion:
            strat = rec.get("strategy", "")
            if strat:
                if strat not in success_stats:
                    success_stats[strat] = {"count": 0, "total_score": 0.0}
                success_stats[strat]["count"] += 1
                success_stats[strat]["total_score"] += float(rec.get("score", 7.0))
    
    # 计算奖励因子
    for strat, stats in success_stats.items():
        count = stats["count"]
        avg_score = stats["total_score"] / count if count > 0 else 7.0
        # score=0视为成功谱默认分7.0（记录本身代表成功）
        if avg_score <= 0:
            avg_score = 7.0
        if count >= 3 and avg_score >= 7.0:
            bonuses[strat] = 1.3  # 近期成功3次+且均分7+，显著奖励
        elif count >= 2 and avg_score >= 7.0:
            bonuses[strat] = 1.15  # 成功2次+且均分7+，轻度奖励
        elif count >= 1 and avg_score >= 8.0:
            bonuses[strat] = 1.1  # 成功1次但高分，微弱奖励
    
    return bonuses


# ============================================================
# 方向C-2: 失败模式→自动补案例提示
# ============================================================

# 失败类型→避坑建议映射
FAILURE_TYPE_HINTS = {
    FailureType.IDENTIFICATION_ERROR: "识别偏差：用户真实需求与系统判断不一致，建议重新倾听、用提问确认而非假设",
    FailureType.SITUATION_ERROR: "情境误判：当前阶段判断可能有误，建议放缓节奏、先确认对方状态再推进",
    FailureType.IDENTITY_ERROR: "身份错位：关系位置判断偏差，建议调整语气和策略风格匹配真实关系",
    FailureType.LAYER_ORDER_ERROR: "层序混乱：安全/策略/成品层优先级错乱，建议先保安全再谈策略",
    FailureType.NARRATIVE_ERROR: "叙事偏差：共情不足或叙事方式不当，建议先接住情绪再引导",
    FailureType.TIMING_ERROR: "时机不当：推进节奏与用户准备度不匹配，建议等待信号再行动",
    FailureType.SAFETY_ERROR: "安全违规：触发了护栏红线，必须立刻修正输出",
}

FAILURE_CODE_HINTS = {
    FailureCode.F01_SURFACE_GOAL_BIAS: "目标识别偏表层：先确认真实诉求，再决定推进动作",
    FailureCode.F02_EARLY_PUSH: "推进过早：先降速，先确认对方准备度",
    FailureCode.F03_MISSING_REPAIR: "关系脆弱缺承接：先修复再推进",
    FailureCode.F04_MISSING_QUESTION: "信息缺口大：先补关键问题再给方案",
    FailureCode.F05_HEAVY_RHYTHM: "输出过重：拆短句、降密度、单点推进",
    FailureCode.F06_LOOSE_RHYTHM: "输出过散：收敛目标，给明确下一步",
    FailureCode.F07_INTERNAL_LEAK: "内部术语外露：继续清洗对外表达层",
    FailureCode.F08_SCENE_WEAPON_MISMATCH: "场景与武器错配：回到场景约束重选组合",
    FailureCode.F09_OVER_EMPATHY: "过度共情：保留承接，但增加推进动作",
    FailureCode.F10_OVER_PUSH: "过度推进：先保关系和边界，再谈结果",
}


def get_failure_hints(scene_id: str, goal: str = "") -> list[str]:
    """
    获取高频失败模式的避坑提示（方向C-2）
    
    当同一failure_type近期累计>=2次，返回对应的避坑建议。
    """
    path = _get_path(scene_id)
    if not path.exists():
        return []
    
    examples = safe_json_read(str(path), [])
    if not examples:
        return []
    
    now = time.time()
    window = 3600 * 4  # 4小时窗口
    
    # 统计近期各failure_type出现次数
    type_counts = {}
    for ex in examples:
        if goal and ex.get("goal") != goal:
            continue
        ts = ex.get("timestamp", 0)
        if now - ts > window:
            continue
        ft = ex.get("failure_type", "")
        if ft:
            type_counts[ft] = type_counts.get(ft, 0) + 1
    
    hints = []
    for ft, count in type_counts.items():
        if count >= 2:  # 同一失败模式出现2次+就提示
            try:
                ft_enum = FailureType(ft)
                hint = FAILURE_TYPE_HINTS.get(ft_enum, "")
                if hint:
                    hints.append(f"[避坑] {hint} (近期{count}次)")
            except ValueError:
                pass

    # 同时统计 failure_code（F01~F10）
    code_counts = {}
    for ex in examples:
        if goal and ex.get("goal") != goal:
            continue
        ts = ex.get("timestamp", 0)
        if now - ts > window:
            continue
        code = ex.get("failure_code", "")
        if code:
            code_counts[code] = code_counts.get(code, 0) + 1

    for code, count in code_counts.items():
        if count >= 2:
            try:
                code_enum = FailureCode(code)
                hint = FAILURE_CODE_HINTS.get(code_enum, "")
                if hint:
                    hints.append(f"[避坑] {code}: {hint} (近期{count}次)")
            except ValueError:
                pass

    return hints
