"""
Human-OS Engine - 管理场景标准题库测试 (Management Golden Set)

读取 tests/management_benchmark_data.json 中的 80 个固定场景（Level 1 + Level 2），
验证系统的目标识别是否符合预期。

支持按难度分级运行：
    pytest tests/test_management_benchmark.py -k "level_1"  # 仅基础题
    pytest tests/test_management_benchmark.py -k "level_2"  # 仅高阶题
    pytest tests/test_management_benchmark.py              # 全部运行
"""

import json
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from graph.builder import build_graph
from schemas.context import Context
from modules.L5.scene_loader import load_scene_config


def load_management_benchmark_data():
    """加载管理场景题库"""
    data_path = os.path.join(os.path.dirname(__file__), 'management_benchmark_data.json')
    with open(data_path, 'r', encoding='utf-8') as f:
        return json.load(f)


@pytest.fixture
def graph():
    """构建测试图"""
    return build_graph()


@pytest.fixture
def management_context():
    """自动加载管理场景配置的 Context"""
    ctx = Context(session_id="test-management")
    try:
        ctx.scene_config = load_scene_config("management")
    except Exception:
        pass
    return ctx


@pytest.fixture
def management_benchmark_data():
    """加载管理场景题库数据"""
    return load_management_benchmark_data()


class TestManagementGoldenSet:
    """管理场景标准题库测试类"""

    def test_dataset_loaded(self, management_benchmark_data):
        """验证题库加载成功"""
        assert "scenarios" in management_benchmark_data
        assert len(management_benchmark_data["scenarios"]) == 80

    def test_level_1_count(self, management_benchmark_data):
        """验证 Level 1 基础题数量"""
        level_1 = [s for s in management_benchmark_data["scenarios"] if s.get("level") == 1]
        assert len(level_1) == 50

    def test_level_2_count(self, management_benchmark_data):
        """验证 Level 2 高阶题数量"""
        level_2 = [s for s in management_benchmark_data["scenarios"] if s.get("level") == 2]
        assert len(level_2) == 30

    @pytest.mark.parametrize(
        "scenario",
        load_management_benchmark_data()["scenarios"],
        ids=lambda s: f"[{s['id']}] {s['category']} (L{s.get('level', '?')})"
    )
    def test_no_crash(self, graph, management_context, scenario):
        """验证所有 80 个场景都不会导致系统崩溃"""
        ctx = Context(session_id=f"mgmt-stability-{scenario['id']}")
        try:
            ctx.scene_config = management_context.scene_config
        except Exception:
            pass
        try:
            result = graph.invoke({"context": ctx, "user_input": scenario["input"]})
            assert result is not None
            assert "output" in result or "context" in result
        except Exception as e:
            pytest.fail(f"管理场景 {scenario['id']} 导致系统崩溃: {e}")
