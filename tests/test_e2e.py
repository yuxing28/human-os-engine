"""
Human-OS Engine - 端到端测试

验证完整的 Step 0-9 流程能够正常运行。
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock LLM calls to avoid API timeout
import types
mock_nvidia = types.ModuleType('llm.nvidia_client')
mock_nvidia.invoke_fast = lambda *a, **k: '{"input_type": "问题咨询", "confidence": 0.7}'
mock_nvidia.invoke_deep = lambda *a, **k: "这确实不容易。很多人都会遇到类似的情况。你可以先从最简单的步骤开始试试，要不要我帮你拆解一下？"
mock_nvidia.invoke_standard = lambda *a, **k: '{"input_type": "问题咨询", "confidence": 0.7}'
class TaskType:
    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"
mock_nvidia.TaskType = TaskType
sys.modules['llm.nvidia_client'] = mock_nvidia

from schemas.context import Context
from graph.builder import build_graph


class TestEndToEnd:
    """端到端测试"""

    @pytest.fixture
    def graph(self):
        """构建图"""
        return build_graph()

    @pytest.fixture
    def context(self):
        """创建测试上下文"""
        return Context(session_id="test-001")

    def test_consultation_path(self, graph, context):
        """测试路径 B：问题咨询"""
        result = graph.invoke({
            "context": context,
            "user_input": "如何坚持学习？有什么方法吗？",
        })

        # 验证输出存在
        assert result["output"] is not None
        assert len(result["output"]) > 0

        # 验证不包含禁用词
        assert "利用" not in result["output"]
        assert "害怕" not in result["output"]
        assert "钩子" not in result["output"]

        # 验证长度合理
        assert len(result["output"]) <= 300

        print(f"\n[问题咨询] 输出: {result['output']}")

    def test_emotion_path(self, graph, context):
        """测试路径 A：情绪表达"""
        result = graph.invoke({
            "context": context,
            "user_input": "好烦啊，不想活了",
        })

        assert result["output"] is not None
        assert len(result["output"]) > 0
        print(f"\n[情绪表达] 输出: {result['output']}")

    def test_scenario_path(self, graph, context):
        """测试路径 C：场景描述"""
        result = graph.invoke({
            "context": context,
            "user_input": "我老板让我加班，同事还不配合，烦死了",
        })

        assert result["output"] is not None
        assert len(result["output"]) > 0
        print(f"\n[场景描述] 输出: {result['output']}")

    def test_high_emotion(self, graph, context):
        """测试高情绪用户"""
        result = graph.invoke({
            "context": context,
            "user_input": "气死我了！太过分了！受不了了！",
        })

        assert result["output"] is not None
        print(f"\n[高情绪] 输出: {result['output']}")

    def test_impatient_user(self, graph, context):
        """测试急躁用户"""
        result = graph.invoke({
            "context": context,
            "user_input": "急死了，快点说，没时间了",
        })

        assert result["output"] is not None
        print(f"\n[急躁] 输出: {result['output']}")

    def test_give_up_signal(self, graph, context):
        """测试放弃信号"""
        result = graph.invoke({
            "context": context,
            "user_input": "算了，太麻烦了，不聊了",
        })

        assert result["output"] is not None
        # 检查是否检测到阻力
        assert result["context"].user.resistance.type is not None or \
               result["context"].goal.current.description == "用户放弃"
        print(f"\n[放弃信号] 输出: {result['output']}")

    def test_forbidden_words_check(self, graph, context):
        """测试禁用词过滤"""
        result = graph.invoke({
            "context": context,
            "user_input": "我想利用这个机会，但害怕失败",
        })

        output = result["output"]
        # 确保输出不包含禁用词
        forbidden = ["利用", "害怕", "畏惧", "钩子", "恐惧"]
        for word in forbidden:
            assert word not in output, f"输出包含禁用词: {word}"

        print(f"\n[禁用词检查] 输出: {output}")


class TestFeedbackInference:
    """反馈推断测试"""

    def test_positive_feedback(self):
        """测试正面反馈"""
        from utils.feedback import infer_feedback
        from schemas.context import Context

        context = Context(session_id="test")
        feedback = infer_feedback("谢谢，明白了，很有用", 0.5, context)
        assert feedback == "positive"

    def test_negative_feedback(self):
        """测试负面反馈"""
        from utils.feedback import infer_feedback
        from schemas.context import Context

        context = Context(session_id="test")
        feedback = infer_feedback("没用，废话，别说了", 0.5, context)
        assert feedback == "negative"

    def test_neutral_feedback(self):
        """测试中性反馈"""
        from utils.feedback import infer_feedback
        from schemas.context import Context

        context = Context(session_id="test")
        feedback = infer_feedback("那具体怎么做呢？", 0.5, context)
        assert feedback == "neutral"


class TestGoalDetection:
    """目标检测测试"""

    def test_give_up_with_resistance(self):
        """测试放弃信号+阻力浮现"""
        from schemas.context import Context
        from graph.nodes import step2_goal_detection
        from graph.state import GraphState

        context = Context(session_id="test")
        state: GraphState = {
            "context": context,
            "user_input": "算了，太贵了，不买了",
            "output": "",
            "error": None,
            "priority": None,
            "selected_mode": None,
            "strategy_plan": None,
            "weapons_used": None,
            "skip_to_end": False,
        }

        result = step2_goal_detection(state)
        # 应该检测到阻力（贪婪-太贵）
        assert result["context"].user.resistance.type is not None

    def test_goal_switch(self):
        """测试目标切换"""
        from schemas.context import Context
        from graph.nodes import step2_goal_detection
        from graph.state import GraphState

        context = Context(session_id="test")
        context.goal.current.description = "学英语"
        state: GraphState = {
            "context": context,
            "user_input": "不想聊这个了，我想说说工作的事",
            "output": "",
            "error": None,
            "priority": None,
            "selected_mode": None,
            "strategy_plan": None,
            "weapons_used": None,
            "skip_to_end": False,
        }

        result = step2_goal_detection(state)
        # 应该检测到目标漂移
        assert result["context"].goal.drift_detected is True
        assert len(result["context"].goal.history) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
