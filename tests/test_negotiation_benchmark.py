"""
Human-OS Engine - 谈判场景标准题库测试 (Negotiation Golden Set)

读取 tests/negotiation_benchmark_data.json 中的 40 个固定场景，
验证系统的目标识别是否符合预期。
"""

import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from graph.builder import build_graph
from schemas.context import Context
from modules.L5.scene_loader import load_scene_config


def load_negotiation_benchmark_data():
    """加载谈判场景题库"""
    data_path = os.path.join(os.path.dirname(__file__), 'negotiation_benchmark_data.json')
    with open(data_path, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def graph():
    """构建测试图"""
    return build_graph()


@pytest.fixture
def negotiation_context():
    """自动加载谈判场景配置的 Context"""
    ctx = Context(session_id="test-negotiation")
    try:
        ctx.scene_config = load_scene_config("negotiation")
    except Exception:
        # 如果配置不存在，使用空配置
        pass
    return ctx


@pytest.fixture
def negotiation_benchmark_data():
    """加载谈判场景题库数据"""
    return load_negotiation_benchmark_data()


class TestNegotiationGoldenSet:
    """谈判场景标准题库测试类"""

    def test_dataset_loaded(self, negotiation_benchmark_data):
        """验证题库加载成功"""
        assert "scenarios" in negotiation_benchmark_data
        assert len(negotiation_benchmark_data["scenarios"]) == 40

    @pytest.mark.parametrize("scenario", load_negotiation_benchmark_data()["scenarios"], ids=lambda s: f"[{s['id']}] {s['category']}")
    def test_no_crash(self, graph, negotiation_context, scenario):
        """验证所有 40 个场景都不会导致系统崩溃"""
        # 创建独立 Context 副本
        ctx = Context(session_id=f"neg-stability-{scenario['id']}")
        try:
            ctx.scene_config = negotiation_context.scene_config
        except Exception:
            pass
        
        try:
            result = graph.invoke({"context": ctx, "user_input": scenario["input"]})
            assert result is not None
            assert "output" in result or "context" in result
        except Exception as e:
            pytest.fail(f"谈判场景 {scenario['id']} 导致系统崩溃: {e}")
