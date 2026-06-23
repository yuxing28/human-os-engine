"""
Human-OS Engine - L2 识别模块：双核状态识别

基于 双核状态识别.md 的内容。
识别用户的感性核/理性核交互状态。

输入：用户输入文本
输出：DualCoreResult（状态 + 主导核 + 置信度）
"""

from schemas.module_io import DualCoreResult


EMOTIONAL_MARKERS = {
    "情绪词": ["烦", "气", "急", "怕", "恨", "爱", "想", "要", "受不了", "崩溃", "开心", "难过", "纠结", "挣扎", "内耗", "痛苦"],
    "感叹词": ["啊", "呀", "吧", "嘛", "哦", "唉", "哎", "天呐", "我去"],
    "绝对化": ["一定", "必须", "绝对", "肯定", "永远", "从不", "所有", "全部", "完完全全"],
    "冲动性": ["控制不住", "忍不住", "停不下来", "就是想", "冲动", "上头"],
}

RATIONAL_MARKERS = {
    "逻辑词": ["因为", "所以", "但是", "然而", "因此", "首先", "其次", "最后", "总结"],
    "数据词": ["数据", "比例", "百分比", "统计", "分析", "研究", "证据"],
    "条件词": ["如果", "假设", "条件", "可能", "或许", "大概", "估计"],
    "疑问词": ["为什么", "怎么", "如何", "是什么", "哪个", "多少"],
    "执行词": ["方案", "步骤", "执行", "推进", "落实", "解决", "计划", "拆解"],
}

STATE_MARKERS = {
    "对抗": ["知道但做不到", "想做但不想动", "道理都懂但", "明知道", "就是做不到", "控制不住", "应该但不想", "纠结", "矛盾", "挣扎", "内耗", "拖延", "理智vs情感", "想要vs应该", "乱了", "混乱", "失控"],
    "协同": ["确定", "执行", "搞定", "完成", "拿下", "解决了", "投入", "专注", "沉浸", "心流", "忘我", "既想做又会做", "享受过程"],
    "同频": ["好的", "明白", "了解", "收到", "可以", "行", "毫不犹豫", "不用想", "果断", "确定", "清晰"],
    "合理化": ["没办法", "就是这样", "天生的", "改不了", "习惯了", "我就是这样的人", "这次不一样", "我需要", "犒劳自己", "找借口", "自我说服", "冲动购买"],
}


def identify_dual_core(user_input: str) -> DualCoreResult:
    """
    双核状态识别主函数
    """
    emotional_score = _count_markers(user_input, EMOTIONAL_MARKERS)
    rational_score = _count_markers(user_input, RATIONAL_MARKERS)
    state_scores = _count_state_markers(user_input)

    state = _determine_state(user_input, emotional_score, rational_score, state_scores)
    dominant = _determine_dominant(emotional_score, rational_score, state)
    evidence = _collect_evidence(user_input, state_scores)
    confidence = _calculate_confidence(emotional_score, rational_score, state, state_scores)

    return DualCoreResult(
        state=state,
        dominant=dominant,
        confidence=confidence,
        evidence=evidence,
    )


def _count_markers(user_input: str, markers: dict[str, list[str]]) -> int:
    count = 0
    for keywords in markers.values():
        for keyword in keywords:
            if keyword in user_input:
                count += 1
    return count


def _count_state_markers(user_input: str) -> dict[str, int]:
    return {
        state: sum(1 for keyword in keywords if keyword in user_input)
        for state, keywords in STATE_MARKERS.items()
    }


def _determine_dominant(emotional_score: int, rational_score: int, state: str) -> str:
    if state in {"对抗", "合理化"}:
        return "感性核"
    if emotional_score >= rational_score + 2:
        return "感性核"
    if rational_score >= emotional_score + 2:
        return "理性核"
    return "理性核"


def _determine_state(
    user_input: str,
    emotional_score: int,
    rational_score: int,
    state_scores: dict[str, int],
) -> str:
    explicit_state = max(state_scores, key=state_scores.get)
    explicit_hits = state_scores[explicit_state]
    if explicit_hits > 0:
        return explicit_state

    if emotional_score >= 2 and rational_score >= 2 and abs(emotional_score - rational_score) <= 1:
        return "对抗"
    if rational_score >= emotional_score + 2:
        return "协同"
    if emotional_score >= rational_score + 2:
        return "对抗"
    if len(user_input.strip()) <= 8:
        return "同频"
    return "同频"


def _collect_evidence(user_input: str, state_scores: dict[str, int]) -> list[str]:
    evidence = []

    for category, keywords in EMOTIONAL_MARKERS.items():
        matched = [kw for kw in keywords if kw in user_input]
        if matched:
            evidence.append(f"感性-{category}: {', '.join(matched[:3])}")

    for category, keywords in RATIONAL_MARKERS.items():
        matched = [kw for kw in keywords if kw in user_input]
        if matched:
            evidence.append(f"理性-{category}: {', '.join(matched[:3])}")

    for state, count in state_scores.items():
        if count > 0:
            evidence.append(f"状态-{state}: 命中 {count} 项")

    return evidence


def _calculate_confidence(
    emotional_score: int,
    rational_score: int,
    state: str,
    state_scores: dict[str, int],
) -> float:
    total = emotional_score + rational_score
    state_hits = state_scores.get(state, 0)

    if total == 0 and state_hits == 0:
        return 0.3

    confidence = 0.45
    confidence += min(total * 0.08, 0.25)
    confidence += min(state_hits * 0.12, 0.25)

    if state in {"对抗", "合理化"}:
        confidence += 0.1

    if emotional_score > 0 and rational_score > 0 and abs(emotional_score - rational_score) <= 1 and state == "同频":
        confidence -= 0.1

    return min(max(confidence, 0.1), 1.0)


if __name__ == "__main__":
    test_cases = [
        "我知道要减肥，但就是控制不住想吃",
        "因为数据显示，这个方案成功率更高，所以我准备这样执行",
        "好的，明白了，就这样做吧",
        "没办法，我就是这样的人，改不了",
        "我很纠结，理智告诉我别买，但我就是想买",
    ]

    for text in test_cases:
        result = identify_dual_core(text)
        print(f"\n输入: {text}")
        print(f"状态: {result.state}, 主导核: {result.dominant}")
        print(f"置信度: {result.confidence:.2f}")
        print(f"证据: {result.evidence}")
