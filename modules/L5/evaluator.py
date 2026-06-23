"""
Human-OS Engine - L5 离线评估器

[离线工具 - 不进主链] 本模块用于离线质量分析，不参与沙盒主线的运行时评估。
沙盒主线统一使用 simulation/llm_judge.py 的10分制评估。

基于 10-测试与质量模块.md 的内容。
实现 5 维度评分和策略库/反例库持久化。
"""

import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

from utils.file_lock import safe_json_read, safe_json_write
from utils.types import safe_enum_value


@dataclass
class EvaluationResult:
    """评估结果"""
    identification_accuracy: float = 0.0  # 识别准确性（25分）
    strategy_completeness: float = 0.0  # 策略完整性（25分）
    logical_consistency: float = 0.0  # 逻辑自洽性（20分）
    expression_normativity: float = 0.0  # 表达规范性（20分）
    executability: float = 0.0  # 可执行性（10分）
    total_score: float = 0.0  # 总分（100分）
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class StrategyRecord:
    """策略记录"""
    strategy_name: str
    mode: str
    stage: str
    context_summary: str
    output: str
    feedback: str  # positive/negative/neutral
    score: float
    timestamp: str = ""


# ===== 5 维度评分 =====

def evaluate_response(
    context: Any,
    output: str,
    user_input: str = "",
) -> EvaluationResult:
    """
    5 维度评分（100分制）

    维度：
    1. 识别准确性（25分）：是否正确识别主导欲望、恐惧、懒惰
    2. 策略完整性（25分）：是否有钩子设计、降低门槛、组合拳
    3. 逻辑自洽性（20分）：策略是否符合模式、优先级是否正确
    4. 表达规范性（20分）：禁用词汇是否为 0
    5. 可执行性（10分）：是否具体可操作

    Args:
        context: 当前上下文
        output: 系统输出
        user_input: 用户输入

    Returns:
        EvaluationResult: 评估结果
    """
    result = EvaluationResult()
    issues = []
    suggestions = []

    # ===== 维度 1：识别准确性（25分）=====
    id_score = 25.0

    # 检查是否识别到主导欲望
    dominant, weight = context.user.desires.get_dominant()
    if weight < 0.1:
        id_score -= 10
        issues.append("未识别到主导欲望")

    # 检查恐惧是否被考虑
    if context.user.desires.fear > 0.3:
        # 恐惧存在但未在策略中体现
        if "恐惧" not in output and "担忧" not in output and "风险" not in output:
            id_score -= 5
            issues.append("识别到恐惧但未在输出中体现")

    # 检查懒惰是否被考虑
    if context.user.desires.sloth > 0.3:
        if "简单" not in output and "容易" not in output and "快速" not in output:
            id_score -= 5
            issues.append("识别到懒惰但未在输出中降低门槛")

    result.identification_accuracy = max(0, id_score)

    # ===== 维度 2：策略完整性（25分）=====
    st_score = 25.0

    # 检查是否有方向引导（五层第5层）
    if "?" not in output and "？" not in output and "要不要" not in output:
        st_score -= 5
        issues.append("缺少方向引导（无提问或选项）")

    # 检查输出长度（太短可能策略不完整）
    if len(output) < 20:
        st_score -= 10
        issues.append("输出过短，策略可能不完整")

    result.strategy_completeness = max(0, st_score)

    # ===== 维度 3：逻辑自洽性（20分）=====
    lc_score = 20.0

    # 检查模式与策略是否匹配
    if context.current_strategy.mode_sequence:
        mode = safe_enum_value(context.current_strategy.mode_sequence[0])
        if mode == "A" and ("成交" in output or "购买" in output):
            lc_score -= 10
            issues.append("Mode A（稳定自身）不应直接推动成交")

    result.logical_consistency = max(0, lc_score)

    # ===== 维度 4：表达规范性（20分）=====
    en_score = 20.0

    # 禁用词汇检查（统一引用 constants.py）
    from utils.constants import PRIORITY_1_REPLACEMENTS, PRIORITY_2_REPLACEMENTS, INTERNAL_TERMS, CUSTOMER_SERVICE_WORDS

    forbidden = list(PRIORITY_1_REPLACEMENTS.keys()) + list(PRIORITY_2_REPLACEMENTS.keys())
    for word in forbidden:
        if word in output:
            en_score -= 5
            issues.append(f"包含禁用词: {word}")

    # 内部术语检查
    for term in INTERNAL_TERMS:
        if term in output:
            en_score -= 5
            issues.append(f"框架泄露: {term}")

    # 客服词汇检查
    for word in CUSTOMER_SERVICE_WORDS:
        if word in output:
            en_score -= 3
            issues.append(f"客服词汇: {word}")

    result.expression_normativity = max(0, en_score)

    # ===== 维度 5：可执行性（10分）=====
    ex_score = 10.0

    # 检查是否包含具体行动建议
    action_words = ["可以", "试试", "建议", "先", "第一步", "接下来"]
    has_action = any(w in output for w in action_words)
    if not has_action:
        ex_score -= 5
        issues.append("缺少具体行动建议")

    # 检查是否有明确方向
    if len(output) < 10:
        ex_score -= 5
        issues.append("输出过短，无法执行")

    result.executability = max(0, ex_score)

    # 计算总分
    result.total_score = (
        result.identification_accuracy
        + result.strategy_completeness
        + result.logical_consistency
        + result.expression_normativity
        + result.executability
    )

    result.issues = issues

    # 生成建议
    if result.identification_accuracy < 20:
        suggestions.append("加强识别模块的准确性，确保主导欲望被正确识别")
    if result.strategy_completeness < 20:
        suggestions.append("确保策略包含完整的钩子、降门槛和方向引导")
    if result.expression_normativity < 15:
        suggestions.append("严格检查禁用词汇和内部术语，避免框架泄露")
    if result.executability < 8:
        suggestions.append("增加具体的行动建议和可执行步骤")

    result.suggestions = suggestions

    return result


# ===== 策略库/反例库持久化 =====

STRATEGY_LIBRARY_PATH = "data/strategy_library.json"
COUNTER_EXAMPLES_PATH = "data/counter_examples.json"


def _ensure_data_dir():
    """确保数据目录存在"""
    Path("data").mkdir(exist_ok=True)


def _load_json(path: str) -> list[dict]:
    """加载 JSON 文件（安全读取）"""
    _ensure_data_dir()
    return safe_json_read(path, [])


def _save_json(path: str, data: list[dict]):
    """保存 JSON 文件（安全写入）"""
    _ensure_data_dir()
    safe_json_write(path, data)


def record_effective_strategy(record: StrategyRecord):
    """
    记录有效策略到策略库

    Args:
        record: 策略记录
    """
    _ensure_data_dir()
    library = _load_json(STRATEGY_LIBRARY_PATH)
    library.append(asdict(record))

    # 限制大小（保留最近 200 条）
    if len(library) > 200:
        library = library[-200:]

    _save_json(STRATEGY_LIBRARY_PATH, library)


def record_counter_example(record: StrategyRecord):
    """
    记录无效策略到反例库

    Args:
        record: 策略记录
    """
    _ensure_data_dir()
    examples = _load_json(COUNTER_EXAMPLES_PATH)
    examples.append(asdict(record))

    # 限制大小（保留最近 100 条）
    if len(examples) > 100:
        examples = examples[-100:]

    _save_json(COUNTER_EXAMPLES_PATH, examples)


def get_strategy_stats() -> dict:
    """
    获取策略库统计信息

    Returns:
        dict: 统计信息
    """
    library = _load_json(STRATEGY_LIBRARY_PATH)
    examples = _load_json(COUNTER_EXAMPLES_PATH)

    # 按反馈类型统计
    feedback_counts = {}
    for record in library:
        fb = record.get("feedback", "unknown")
        feedback_counts[fb] = feedback_counts.get(fb, 0) + 1

    # 按模式统计
    mode_counts = {}
    for record in library:
        mode = record.get("mode", "unknown")
        mode_counts[mode] = mode_counts.get(mode, 0) + 1

    return {
        "total_effective": len(library),
        "total_counter": len(examples),
        "feedback_distribution": feedback_counts,
        "mode_distribution": mode_counts,
        "avg_score": sum(r.get("score", 0) for r in library) / max(len(library), 1),
    }
