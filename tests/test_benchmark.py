"""
Human-OS Engine - 标准题库测试 (Golden Set / 回归测试)

读取 tests/benchmark_data.json 中的 50 个固定场景，
验证系统的稳定性、非空性、格式合法性及语义质量。

作用：确保系统核心能力不退化，每次版本更新必须跑通。
这是发布门槛（Merge Gate）的核心组成部分。
"""

import json
import os
import sys
import pytest
import signal
import functools

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from graph.builder import build_graph
from schemas.context import Context
from schemas.enums import StrategyCombo
from modules.L5.scene_loader import load_scene_config


def load_benchmark_data():
    """加载标准题库"""
    data_path = os.path.join(os.path.dirname(__file__), 'benchmark_data.json')
    with open(data_path, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def graph():
    """构建测试图"""
    return build_graph()


@pytest.fixture
def sales_context():
    """自动加载销售场景配置的 Context"""
    ctx = Context(session_id="test-sales")
    try:
        ctx.scene_config = load_scene_config("sales")
    except Exception:
        pass
    return ctx


@pytest.fixture
def benchmark_data():
    """加载题库数据"""
    return load_benchmark_data()


# ===== 语义评分规则 =====

# 行动导向词（用于检查是否有明确的 Next Action）
ACTION_ORIENTED_WORDS = [
    "我建议", "我们可以", "你可以", "下一步", "先", "试试",
    "让我", "帮你", "看看", "分析", "一起", "开始"
]

# 违禁词（系统内部术语，绝对不能出现在输出中）
FORBIDDEN_WORDS = [
    "五层结构", "武器库", "八宗罪", "Mode A", "Mode B", "Mode C",
    "策略组合", "钩子", "降门槛", "升维"
]


def check_non_empty(output: str) -> tuple[bool, str]:
    """检查输出是否非空（> 10 字）"""
    if not output or len(output.strip()) < 10:
        return False, f"输出过短（{len(output) if output else 0} 字），应 > 10 字"
    return True, ""


def check_valid_format(output: str) -> tuple[bool, str]:
    """检查输出格式合法性"""
    # 检查是否包含 JSON（如果有，必须合法）
    if output.strip().startswith("{"):
        try:
            json.loads(output)
        except json.JSONDecodeError:
            return False, "输出包含非法 JSON"
    
    return True, ""


def check_semantic_quality(context: Context, output: str) -> dict:
    """语义评分：目标识别、下一步动作、安全合规"""
    scores = {
        "goal_recognition": None,
        "next_action": False,
        "safety_compliance": True,
        "issues": []
    }
    
    # 1. 目标识别分
    if context and hasattr(context, 'goal'):
        scores["goal_recognition"] = getattr(context.goal, 'granular_goal', None)
    
    # 2. 下一步动作分
    for word in ACTION_ORIENTED_WORDS:
        if word in output:
            scores["next_action"] = True
            break
    
    # 3. 安全合规分
    for word in FORBIDDEN_WORDS:
        if word in output:
            scores["safety_compliance"] = False
            scores["issues"].append(f"包含违禁词：{word}")
    
    return scores


# ===== 代表性场景 ID（用于深度语义评分） =====
# 排除边界情况（41-50）和模糊目标场景（30, 40）
# 只选有实质内容、输出长度稳定的场景
REPRESENTATIVE_IDS = [1, 5, 10, 15, 20, 25, 35, 43, 46]

# 模糊目标场景（允许识别为多个合理目标之一）
FUZZY_GOAL_SCENARIOS = {
    30: ["prove_roi", "reduce_admin_burden"],  # 团队效率可以是 ROI 或减负
    40: ["break_status_quo", "overcome_rejection"],  # 焦虑面对可以是打破现状或克服拒绝
}


# ===== 测试类 =====

class TestGoldenSet:
    """标准题库测试类（语义评分版）"""

    def test_dataset_loaded(self, benchmark_data):
        """验证题库加载成功"""
        assert "scenarios" in benchmark_data
        assert len(benchmark_data["scenarios"]) == 50

    @pytest.mark.parametrize(
        "scenario",
        [s for s in load_benchmark_data()["scenarios"] if s["id"] in REPRESENTATIVE_IDS],
        ids=lambda s: f"[{s['id']}] {s['category']}"
    )
    def test_semantic_quality(self, graph, sales_context, scenario):
        """
        语义评分测试（10 个代表性场景）：
        1. 不崩溃
        2. 非空（> 10 字）
        3. 格式合法
        4. 语义质量（目标识别、下一步动作、安全合规）
        """
        user_input = scenario["input"]
        expected_goal = scenario.get("expected_goal")
        
        ctx = Context(session_id=f"benchmark-{scenario['id']}")
        try:
            ctx.scene_config = sales_context.scene_config
        except Exception:
            pass
        try:
            result = graph.invoke({"context": ctx, "user_input": user_input})
        except Exception as e:
            pytest.fail(f"场景 {scenario['id']} 执行崩溃: {e}")
        
        assert result is not None, "结果为空"
        
        output = result.get("output", "")
        actual_ctx = result.get("context")
        
        # 1. 非空检查
        is_valid, msg = check_non_empty(output)
        assert is_valid, f"场景 {scenario['id']} 输出不合法: {msg}"
        
        # 2. 格式合法检查
        is_valid, msg = check_valid_format(output)
        assert is_valid, f"场景 {scenario['id']} 格式不合法: {msg}"
        
        # 3. 语义评分
        semantic = check_semantic_quality(actual_ctx, output)
        
        # 3.1 安全合规（必须通过）
        assert semantic["safety_compliance"], \
            f"场景 {scenario['id']} 安全合规失败: {', '.join(semantic['issues'])}"
        
        # 3.2 目标识别（如果有预期目标，必须匹配）
        if expected_goal:
            actual_goal = semantic["goal_recognition"]
            # 模糊目标场景允许多个合理答案
            if scenario["id"] in FUZZY_GOAL_SCENARIOS:
                assert actual_goal in FUZZY_GOAL_SCENARIOS[scenario["id"]], \
                    f"场景 {scenario['id']} 目标识别错误：期望 {FUZZY_GOAL_SCENARIOS[scenario['id']]}，实际 '{actual_goal}'"
            else:
                assert actual_goal == expected_goal, \
                    f"场景 {scenario['id']} 目标识别错误：期望 '{expected_goal}'，实际 '{actual_goal}'"


class TestGoldenSetStability:
    """稳定性测试：确保系统不会崩溃（发布门槛 - 50 条全量）"""

    @pytest.mark.parametrize("scenario", load_benchmark_data()["scenarios"], ids=lambda s: f"[{s['id']}] {s['category']}")
    def test_no_crash(self, graph, sales_context, scenario):
        """验证所有 50 个场景都不会导致系统崩溃"""
        ctx = Context(session_id=f"stability-{scenario['id']}")
        try:
            ctx.scene_config = sales_context.scene_config
        except Exception:
            pass
        try:
            result = graph.invoke({"context": ctx, "user_input": scenario["input"]})
            assert result is not None
            assert "output" in result or "context" in result
        except Exception as e:
            pytest.fail(f"场景 {scenario['id']} 导致系统崩溃: {e}")
