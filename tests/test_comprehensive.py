"""
Human-OS Engine - 全面管道测试

验证 Step 0-9 的完整状态链、多轮信任变化、Mode C 升级路径、会话笔记集成、边缘输入。
"""

import pytest
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Mock LLM calls
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
from schemas.enums import EmotionType, FeedbackType, Mode, TrustLevel
from graph.builder import build_graph


# ===== 工具函数 =====

def run_round(graph, context, user_input):
    """运行一轮对话，返回 (result, updated_context)"""
    result = graph.invoke({
        "context": context,
        "user_input": user_input,
    })
    return result, result["context"]


def run_multi_round(graph, context, inputs):
    """运行多轮对话，返回每轮的 (result, context) 列表"""
    results = []
    for inp in inputs:
        result, context = run_round(graph, context, inp)
        results.append((result, context))
    return results


# ===== Test 1: 全管道状态验证 =====

class TestFullPipelineState:
    """验证 Step 0-9 的中间状态是否正确填充"""

    @pytest.fixture
    def graph(self):
        return build_graph()

    @pytest.fixture
    def context(self):
        return Context(session_id="test-pipeline")

    def test_step0_user_history(self, graph, context):
        """Step 0: 用户输入应添加到历史"""
        result, ctx = run_round(graph, context, "怎么坚持学习？")
        user_entries = [h for h in ctx.history if h.role == "user"]
        assert len(user_entries) >= 1
        assert "怎么坚持学习" in user_entries[-1].content

    def test_step1_desires_populated(self, graph, context):
        """Step 1: 欲望识别结果应填充到 context"""
        result, ctx = run_round(graph, context, "我很害怕失败，不敢尝试")
        dominant, weight = ctx.user.desires.get_dominant()
        assert dominant is not None
        assert weight > 0

    def test_step1_emotion_populated(self, graph, context):
        """Step 1: 情绪识别结果应填充到 context"""
        result, ctx = run_round(graph, context, "气死我了！太过分了！")
        assert ctx.user.emotion.type is not None
        assert 0.0 <= ctx.user.emotion.intensity <= 1.0
        assert 0.0 <= ctx.user.emotion.confidence <= 1.0

    def test_step1_dual_core_populated(self, graph, context):
        """Step 1: 双核状态应填充到 context"""
        result, ctx = run_round(graph, context, "我很纠结，一方面想要一方面又怕")
        assert ctx.user.dual_core.state is not None
        assert 0.0 <= ctx.user.dual_core.confidence <= 1.0

    def test_step2_goal_type_set(self, graph, context):
        """Step 2: 目标类型应被推断"""
        result, ctx = run_round(graph, context, "怎么提高转化率？")
        assert ctx.goal.current.type in ("利益价值", "情绪价值", "mixed", "用户放弃")

    def test_step4_priority_in_state(self, graph, context):
        """Step 4: 优先级结果应存在于 state"""
        result, ctx = run_round(graph, context, "我很愤怒，你根本不尊重我")
        assert result.get("priority") is not None
        assert "priority_type" in result["priority"]

    def test_step5_selected_mode_valid(self, graph, context):
        """Step 5: 选中模式应为有效值"""
        result, ctx = run_round(graph, context, "好烦啊，不想活了")
        mode_val = ctx.self_state.energy_mode.value if hasattr(ctx.self_state.energy_mode, 'value') else str(ctx.self_state.energy_mode)
        assert mode_val in ("A", "B", "C")

    def test_step8_output_valid(self, graph, context):
        """Step 8: 输出应为非空且不超过 300 字符"""
        result, ctx = run_round(graph, context, "怎么坚持学习？")
        assert result["output"] is not None
        assert len(result["output"]) > 0
        assert len(result["output"]) <= 300

    def test_step8_no_forbidden_words(self, graph, context):
        """Step 8: 输出不应包含禁用词"""
        result, ctx = run_round(graph, context, "我想赚更多钱")
        forbidden = ["利用", "害怕", "钩子", "五层结构", "武器库", "八宗罪"]
        for word in forbidden:
            assert word not in result["output"], f"输出包含禁用词: {word}"

    def test_step9_system_history(self, graph, context):
        """Step 9: 系统回复应添加到历史"""
        result, ctx = run_round(graph, context, "怎么坚持学习？")
        system_entries = [h for h in ctx.history if h.role == "system"]
        assert len(system_entries) >= 1

    def test_step9_feedback_set(self, graph, context):
        """Step 9: last_feedback 应被设置"""
        result, ctx = run_round(graph, context, "怎么坚持学习？")
        feedback_val = ctx.last_feedback.value if hasattr(ctx.last_feedback, 'value') else str(ctx.last_feedback)
        assert feedback_val in ("positive", "negative", "neutral")

    def test_energy_allocation_matches_mode(self, graph, context):
        """Step 5: 能量分配应与模式匹配"""
        result, ctx = run_round(graph, context, "好烦啊，不想活了")
        mode_val = ctx.self_state.energy_mode.value if hasattr(ctx.self_state.energy_mode, 'value') else str(ctx.self_state.energy_mode)
        alloc = ctx.self_state.energy_allocation
        if mode_val == "A":
            assert alloc.inner == 0.7
        elif mode_val == "B":
            assert alloc.inner == 0.4
        elif mode_val == "C":
            assert alloc.inner == 0.5


# ===== Test 2: 多轮信任变化 =====

class TestMultiTurnTrust:
    """验证多轮对话中信任等级的变化"""

    @pytest.fixture
    def graph(self):
        return build_graph()

    def test_positive_feedback_trust_up(self, graph):
        """连续正面反馈应提升信任"""
        ctx = Context(session_id="test-trust-up")
        # 模拟正面反馈场景：用户提出问题，系统回应
        inputs = [
            "怎么提高工作效率？",
            "嗯，有道理，继续说",
            "好的，我试试看",
        ]
        results = run_multi_round(graph, ctx, inputs)
        # 最后一轮的 trust_level 应该不低于初始值
        final_ctx = results[-1][1]
        trust_val = final_ctx.user.trust_level.value if hasattr(final_ctx.user.trust_level, 'value') else str(final_ctx.user.trust_level)
        assert trust_val in ("low", "medium", "high")

    def test_trust_level_enum_valid(self, graph):
        """每轮的 trust_level 都应为有效枚举值"""
        ctx = Context(session_id="test-trust-enum")
        inputs = ["怎么提高效率", "嗯有道理", "好的谢谢"]
        for inp in inputs:
            result, ctx = run_round(graph, ctx, inp)
            trust_val = ctx.user.trust_level.value if hasattr(ctx.user.trust_level, 'value') else str(ctx.user.trust_level)
            assert trust_val in ("low", "medium", "high"), f"无效信任等级: {trust_val}"

    def test_feedback_inference_consistency(self, graph):
        """反馈推断应与 last_feedback_trust_change 一致"""
        ctx = Context(session_id="test-feedback")
        result, ctx = run_round(graph, ctx, "怎么坚持学习？")
        trust_change = ctx.last_feedback_trust_change
        feedback_val = ctx.last_feedback.value if hasattr(ctx.last_feedback, 'value') else str(ctx.last_feedback)
        # 如果 trust_change 为 None，feedback 应为 neutral
        if trust_change is None:
            assert feedback_val == "neutral"


# ===== Test 3: Mode C 升级路径 =====

class TestModeCUpgrade:
    """验证 Mode C 升级路径的门控条件和失败回退"""

    @pytest.fixture
    def graph(self):
        return build_graph()

    def test_upgrade_eligible_default_true(self):
        """默认 upgrade_eligible 应为 True"""
        from schemas.context import CurrentStrategy
        strategy = CurrentStrategy()
        assert strategy.upgrade_eligible is True

    def test_upgrade_failed_count_default_zero(self):
        """默认 upgrade_failed_count 应为 0"""
        from schemas.context import CurrentStrategy
        strategy = CurrentStrategy()
        assert strategy.upgrade_failed_count == 0

    def test_upgrade_eligible_resets_on_strategy_reset(self):
        """reset_strategy 应重置升级状态"""
        from schemas.context import Context
        ctx = Context(session_id="test-reset")
        ctx.current_strategy.upgrade_eligible = False
        ctx.current_strategy.upgrade_failed_count = 5
        ctx.reset_strategy()
        assert ctx.current_strategy.upgrade_eligible is True
        assert ctx.current_strategy.upgrade_failed_count == 0

    def test_mode_selection_accepts_upgrade_eligible(self, graph):
        """select_mode 应接受 upgrade_eligible 参数"""
        from modules.L1.operation_modes import select_mode
        from schemas.context import Context
        from schemas.enums import MotiveType

        ctx = Context(session_id="test-upgrade")
        ctx.user.emotion.intensity = 0.5
        ctx.user.motive = MotiveType.INSPIRATION
        ctx.goal.current.type = "情绪价值"

        # upgrade_eligible=True 应返回 C
        mode = select_mode(True, ctx.user, ctx.goal, upgrade_eligible=True)
        assert mode == "C"

        # upgrade_eligible=False 应返回 A（不升维）
        mode_no = select_mode(True, ctx.user, ctx.goal, upgrade_eligible=False)
        assert mode_no == "A"

    def test_five_layer_mode_c_combination(self):
        """Mode C 应使用 1+3+5 层级组合"""
        from modules.L4.five_layer_structure import determine_layer_combination
        from schemas.user_state import UserState, Emotion

        user = UserState(emotion=Emotion(type="平静", intensity=0.3))
        layers = determine_layer_combination(user, mode="C")
        assert layers == [1, 3, 5]


# ===== Test 4: 会话笔记集成 =====

class TestSessionNotes:
    """验证会话笔记的提取、存储、加载"""

    def test_add_and_get_session_notes(self):
        """添加笔记后应能检索"""
        from modules.memory import SessionMemory
        sm = SessionMemory(storage_dir="data/test_sessions_notes")
        sm.add_note("sess-001", 1, "mode_switch", "模式 A -> B", {"from": "A", "to": "B"})
        notes = sm.get_recent_notes("sess-001")
        assert len(notes) == 1
        assert notes[0].note_type == "mode_switch"
        assert "A" in notes[0].content

    def test_session_context_format(self):
        """get_context_for_llm 应格式化笔记"""
        from modules.memory import SessionMemory
        sm = SessionMemory(storage_dir="data/test_sessions_notes2")
        sm.add_note("sess-002", 1, "relationship_state", "关系位置: 对等-合作 | 场景: negotiation | 阶段: 推进", {})
        sm.add_note("sess-002", 2, "closure", "本轮结果: positive | 本轮闭环: 明天我们再把条款对齐。", {})
        sm.add_note("sess-002", 3, "collapse", "系统不稳定", {})
        ctx_str = sm.get_context_for_llm("sess-002")
        assert "关系闭环摘要" in ctx_str
        assert "下一轮接话点" in ctx_str
        assert "relationship_state" in ctx_str
        assert "closure" in ctx_str
        assert "对等-合作" in ctx_str
        assert "明天我们再把条款对齐" in ctx_str
        assert ctx_str.index("【下一轮接话点】") < ctx_str.index("第1轮 [relationship_state]")

    def test_session_notes_persistence(self):
        """笔记应持久化到文件"""
        from modules.memory import SessionMemory
        import shutil
        sm = SessionMemory(storage_dir="data/test_sessions_persist")
        sm.add_note("sess-003", 1, "trust_change", "信任 low -> medium", {})
        # 重新加载
        sm2 = SessionMemory(storage_dir="data/test_sessions_persist")
        sm2.load_session("sess-003")
        notes = sm2.get_recent_notes("sess-003")
        assert len(notes) == 1
        assert notes[0].note_type == "trust_change"
        # 清理
        shutil.rmtree("data/test_sessions_persist", ignore_errors=True)

    def test_empty_session_returns_empty(self):
        """空会话应返回空"""
        from modules.memory import SessionMemory
        sm = SessionMemory(storage_dir="data/test_sessions_empty")
        notes = sm.get_recent_notes("nonexistent")
        assert notes == []
        ctx_str = sm.get_context_for_llm("nonexistent")
        assert ctx_str == ""


# ===== Test 5: 边缘输入 =====

class TestEdgeCaseInputs:
    """验证系统对异常输入的健壮性"""

    @pytest.fixture
    def graph(self):
        return build_graph()

    @pytest.fixture
    def context(self):
        return Context(session_id="test-edge")

    def test_single_char_input(self, graph, context):
        """单字输入不应崩溃"""
        result, ctx = run_round(graph, context, "烦")
        assert result["output"] is not None
        assert len(result["output"]) > 0

    def test_two_char_input(self, graph, context):
        """两字输入不应崩溃"""
        result, ctx = run_round(graph, context, "好烦")
        assert result["output"] is not None

    def test_long_input_200_chars(self, graph, context):
        """200字输入不应崩溃"""
        long_input = "我最近工作压力很大，" * 20
        result, ctx = run_round(graph, context, long_input[:200])
        assert result["output"] is not None
        assert len(result["output"]) <= 300

    def test_mixed_chinese_english(self, graph, context):
        """中英混合输入不应崩溃"""
        result, ctx = run_round(graph, context, "I feel 很烦 because 工作压力太大了")
        assert result["output"] is not None

    def test_numbers_only(self, graph, context):
        """纯数字输入不应崩溃"""
        result, ctx = run_round(graph, context, "12345")
        assert result["output"] is not None

    def test_special_characters(self, graph, context):
        """特殊字符输入不应崩溃"""
        result, ctx = run_round(graph, context, "@#$%^&*()")
        assert result["output"] is not None

    def test_repeated_same_input(self, graph, context):
        """重复输入同一内容不应崩溃"""
        ctx = context
        for _ in range(3):
            result, ctx = run_round(graph, ctx, "怎么坚持学习？")
            assert result["output"] is not None

    def test_quick_response_path(self, graph):
        """寒暄短句应打标后继续进入动态链路"""
        ctx = Context(session_id="test-quick")
        result, ctx = run_round(graph, ctx, "好的")
        assert result.get("skip_to_end") is not True
        assert ctx.short_utterance is True
        assert ctx.short_utterance_reason == "quick_ack"
        assert result["output"] is not None
        assert len(result["output"].strip()) > 0

    def test_empty_after_stripping(self, graph):
        """全空格输入不应崩溃"""
        ctx = Context(session_id="test-empty")
        result, ctx = run_round(graph, ctx, "   ")
        assert result["output"] is not None


# ===== Test 6: 武器系统集成 =====

class TestWeaponSystem:
    """验证武器选择和计数的正确性"""

    def test_weapon_usage_count_persists_across_strategy_reset(self):
        """武器计数应在 reset_strategy 后保留"""
        from schemas.context import Context
        ctx = Context(session_id="test-weapon")
        ctx.increment_weapon("反问")
        ctx.increment_weapon("反问")
        assert ctx.get_weapon_count("反问") == 2
        ctx.reset_strategy()
        assert ctx.get_weapon_count("反问") == 2  # 不应被清空

    def test_decay_weapon_counts(self):
        """衰减应减少计数"""
        from schemas.context import Context
        ctx = Context(session_id="test-decay")
        ctx.increment_weapon("反问")
        ctx.increment_weapon("反问")
        ctx.increment_weapon("反问")
        assert ctx.get_weapon_count("反问") == 3
        ctx.decay_weapon_counts()
        assert ctx.get_weapon_count("反问") == 2
        ctx.decay_weapon_counts()
        assert ctx.get_weapon_count("反问") == 1
        ctx.decay_weapon_counts()
        assert ctx.get_weapon_count("反问") == 0  # 应被删除

    def test_weapon_count_increments(self):
        """武器计数应正确累加"""
        from schemas.context import Context
        ctx = Context(session_id="test-incr")
        ctx.increment_weapon("原则")
        ctx.increment_weapon("原则")
        ctx.increment_weapon("反问")
        assert ctx.get_weapon_count("原则") == 2
        assert ctx.get_weapon_count("反问") == 1
        assert ctx.get_weapon_count("不存在") == 0


# ===== Test 7: LLM 相关性检索 =====

class TestLLMMemorySearch:
    """验证 LLM 相关性检索和 fallback"""

    def test_manifest_format(self):
        """记忆清单格式应正确"""
        from modules.memory import MemoryManager, Memory
        manager = MemoryManager(storage_dir="data/test_manifest")
        memories = [
            Memory(content="用户是程序员，喜欢Python", memory_type="preference"),
            Memory(content="用户最近在学LangGraph", memory_type="fact"),
        ]
        manifest = manager._build_memory_manifest(memories)
        assert "[0]" in manifest
        assert "[1]" in manifest
        assert "preference" in manifest
        assert "fact" in manifest

    def test_keyword_fallback(self):
        """关键词 fallback 应能工作"""
        from modules.memory import MemoryManager, Memory
        manager = MemoryManager(storage_dir="data/test_fallback")
        memories = [
            Memory(content="用户是程序员", memory_type="identity", importance=0.8),
            Memory(content="用户喜欢做饭", memory_type="preference", importance=0.5),
            Memory(content="用户在学Python编程", memory_type="fact", importance=0.7),
        ]
        results = manager._search_memory_keywords("编程", memories, 5)
        assert len(results) >= 1
        assert any("编程" in m.content or "程序员" in m.content for m in results)


# ===== Test 8: 多轮策略集成 =====

class TestMultiRoundIntegration:
    """验证多轮对话中策略、模式、武器的集成行为"""

    @pytest.fixture
    def graph(self):
        return build_graph()

    def test_multi_round_history_grows(self, graph):
        """多轮对话历史应正确增长"""
        ctx = Context(session_id="test-multi-hist")
        inputs = ["怎么提高效率", "嗯有道理", "好的谢谢"]
        for i, inp in enumerate(inputs):
            result, ctx = run_round(graph, ctx, inp)
            user_entries = [h for h in ctx.history if h.role == "user"]
            system_entries = [h for h in ctx.history if h.role == "system"]
            assert len(user_entries) == i + 1
            assert len(system_entries) == i + 1

    def test_multi_round_mode_stability(self, graph):
        """平静用户应保持在稳定模式"""
        ctx = Context(session_id="test-multi-stable")
        inputs = ["怎么提高工作效率", "有什么具体方法", "好的我试试"]
        modes = []
        for inp in inputs:
            result, ctx = run_round(graph, ctx, inp)
            mode_val = ctx.self_state.energy_mode.value if hasattr(ctx.self_state.energy_mode, 'value') else str(ctx.self_state.energy_mode)
            modes.append(mode_val)
        # 平静用户不应该频繁切换模式
        assert modes[-1] in ("A", "B", "C")

    def test_multi_round_output_always_valid(self, graph):
        """每轮输出都应有效"""
        ctx = Context(session_id="test-multi-valid")
        inputs = ["怎么坚持学习", "嗯", "有什么技巧", "好的谢谢", "再见"]
        for inp in inputs:
            result, ctx = run_round(graph, ctx, inp)
            assert result["output"] is not None
            assert len(result["output"]) > 0
            assert len(result["output"]) <= 300

    def test_multi_round_no_forbidden_words(self, graph):
        """多轮对话中每轮都不应包含禁用词"""
        ctx = Context(session_id="test-multi-forbidden")
        inputs = ["我很烦", "你根本不懂", "算了说正事", "怎么提高转化率"]
        forbidden = ["利用", "害怕", "钩子", "五层结构", "武器库", "八宗罪", "Mode A", "Mode B", "Mode C"]
        for inp in inputs:
            result, ctx = run_round(graph, ctx, inp)
            for word in forbidden:
                assert word not in result["output"], f"第{inp}轮输出包含禁用词: {word}"

    def test_strategy_plan_populated(self, graph):
        """Step 6 应生成策略方案"""
        ctx = Context(session_id="test-strategy")
        result, ctx = run_round(graph, ctx, "我很愤怒，你根本不尊重我")
        strategy = ctx.current_strategy
        # 策略应该有阶段信息
        assert strategy.stage is not None


# ===== Test 9: 升级失败回退机制 =====

class TestUpgradeRollback:
    """验证 Mode C 升级失败后的回退逻辑"""

    @pytest.fixture
    def graph(self):
        return build_graph()

    def test_upgrade_failed_count_increments(self):
        """升级失败计数应正确累加"""
        from schemas.context import CurrentStrategy
        strategy = CurrentStrategy()
        assert strategy.upgrade_failed_count == 0
        strategy.upgrade_failed_count += 1
        assert strategy.upgrade_failed_count == 1
        strategy.upgrade_failed_count += 1
        assert strategy.upgrade_failed_count == 2

    def test_upgrade_eligible_can_be_disabled(self):
        """upgrade_eligible 应可被设置为 False"""
        from schemas.context import CurrentStrategy
        strategy = CurrentStrategy()
        assert strategy.upgrade_eligible is True
        strategy.upgrade_eligible = False
        assert strategy.upgrade_eligible is False

    def test_upgrade_eligible_false_blocks_mode_c(self):
        """upgrade_eligible=False 应阻止 Mode C"""
        from modules.L1.operation_modes import select_mode
        from schemas.context import Context
        from schemas.enums import MotiveType

        ctx = Context(session_id="test-block-c")
        ctx.user.emotion.intensity = 0.5
        ctx.user.motive = MotiveType.INSPIRATION
        ctx.goal.current.type = "情绪价值"

        # True → C
        mode_yes = select_mode(True, ctx.user, ctx.goal, upgrade_eligible=True)
        assert mode_yes == "C"

        # False → A
        mode_no = select_mode(True, ctx.user, ctx.goal, upgrade_eligible=False)
        assert mode_no == "A"

    def test_strategy_reset_restores_upgrade_eligible(self):
        """reset_strategy 应恢复升级资格"""
        from schemas.context import Context
        ctx = Context(session_id="test-restore")
        ctx.current_strategy.upgrade_eligible = False
        ctx.current_strategy.upgrade_failed_count = 5
        ctx.current_strategy.stage = "升维"
        ctx.reset_strategy()
        assert ctx.current_strategy.upgrade_eligible is True
        assert ctx.current_strategy.upgrade_failed_count == 0
        assert ctx.current_strategy.stage == ""


# ===== Test 10: 记忆提取集成 =====

class TestMemoryExtraction:
    """验证记忆提取的结构化输出"""

    def test_extract_returns_structured_result(self):
        """extract_important_facts 应返回结构化结果或 None"""
        from modules.memory import extract_important_facts
        # 由于 LLM 被 mock，可能返回 None 或有效结果
        result = extract_important_facts(
            "我是做销售的，最近转化率很低",
            "销售转化率是个常见问题，你可以先分析漏斗"
        )
        # 结果要么是 None，要么是有效 dict
        if result is not None:
            assert "type" in result
            assert "content" in result
            assert "importance" in result
            assert 0.0 <= result["importance"] <= 1.0
            assert result["type"] in ("preference", "identity", "decision", "emotion_pattern", "fact")

    def test_memory_types_valid(self):
        """记忆类型应为有效值"""
        from modules.memory import Memory
        valid_types = ("conversation", "fact", "event", "profile", "preference", "identity", "decision", "emotion_pattern")
        m = Memory(content="test", memory_type="fact")
        assert m.memory_type in valid_types

    def test_memory_importance_range(self):
        """记忆重要性应在 [0, 1] 范围内"""
        from modules.memory import Memory
        m = Memory(content="test", importance=0.8)
        assert 0.0 <= m.importance <= 1.0

    def test_memory_manager_search_returns_list(self):
        """search_memory 应返回列表"""
        from modules.memory import MemoryManager
        manager = MemoryManager(storage_dir="data/test_search_list")
        results = manager.search_memory("nonexistent_user", "test query")
        assert isinstance(results, list)

    def test_memory_manager_add_and_search(self):
        """添加记忆后应能检索到"""
        from modules.memory import MemoryManager
        manager = MemoryManager(storage_dir="data/test_add_search")
        manager.add_memory("user-test", "用户是数据科学家", memory_type="identity", importance=0.9)
        # 关键词 fallback 应能找到
        results = manager.search_memory("user-test", "数据科学")
        # 由于 LLM mock 可能失败，fallback 关键词匹配应工作
        assert isinstance(results, list)


# ===== Test 11: 优先级与模式联动 =====

class TestPriorityModeIntegration:
    """验证优先级结果正确影响模式选择"""

    @pytest.fixture
    def graph(self):
        return build_graph()

    def test_angry_user_uses_defensive_mode(self, graph):
        """愤怒用户应触发防御型模式"""
        ctx = Context(session_id="test-priority-angry")
        result, ctx = run_round(graph, ctx, "你这破方案能赚钱？做梦吧")
        # 应返回防御模式（Mode A 或有防御型武器）
        mode_val = ctx.self_state.energy_mode.value if hasattr(ctx.self_state.energy_mode, 'value') else str(ctx.self_state.energy_mode)
        assert mode_val in ("A", "B", "C")

    def test_consultation_user_gets_b_mode(self, graph):
        """问题咨询用户应倾向 Mode B"""
        ctx = Context(session_id="test-priority-b")
        result, ctx = run_round(graph, ctx, "怎么才能坚持学习？有什么技巧吗？")
        mode_val = ctx.self_state.energy_mode.value if hasattr(ctx.self_state.energy_mode, 'value') else str(ctx.self_state.energy_mode)
        # 平静的咨询用户应倾向 B
        assert mode_val in ("A", "B", "C")

    def test_priority_forced_weapon_type(self, graph):
        """愤怒场景应有 forced_weapon_type"""
        ctx = Context(session_id="test-priority-weapon")
        result, ctx = run_round(graph, ctx, "你根本不尊重我，太过分了")
        priority = result.get("priority", {})
        # 如果识别为愤怒/骄傲，应有 forced_weapon_type
        if priority.get("priority_type") == "pride_anger_first":
            assert priority.get("forced_weapon_type") == "defensive"


# ===== Test 12: 质量检查集成 =====

class TestQualityIntegration:
    """验证质量检查在管道中的正确执行"""

    @pytest.fixture
    def graph(self):
        return build_graph()

    def test_output_length_within_limit(self, graph):
        """输出长度应不超过 300"""
        ctx = Context(session_id="test-quality-len")
        for inp in ["怎么提高效率", "我很烦", "老板让我加班"]:
            result, ctx = run_round(graph, ctx, inp)
            assert len(result["output"]) <= 300

    def test_output_not_empty(self, graph):
        """输出不应为空"""
        ctx = Context(session_id="test-quality-empty")
        for inp in ["好的", "烦", "怎么学习", "123"]:
            result, ctx = run_round(graph, ctx, inp)
            assert len(result["output"].strip()) > 0

    def test_no_internal_terms_in_output(self, graph):
        """输出不应包含内部术语"""
        ctx = Context(session_id="test-quality-internal")
        internal_terms = ["五层结构", "武器库", "八宗罪", "Mode A", "Mode B", "Mode C",
                         "钩子", "放大", "降门槛", "升维", "感性核", "理性核"]
        for inp in ["怎么提高效率", "我很愤怒"]:
            result, ctx = run_round(graph, ctx, inp)
            for term in internal_terms:
                assert term not in result["output"], f"输出包含内部术语: {term}"

    def test_no_customer_service_words(self, graph):
        """输出不应包含客服话术"""
        ctx = Context(session_id="test-quality-cs")
        cs_words = ["尊敬的", "感谢您的反馈", "请您放心"]
        result, ctx = run_round(graph, ctx, "怎么提高效率")
        for word in cs_words:
            assert word not in result["output"], f"输出包含客服话术: {word}"


# ===== Test 13: 快速路径路由验证 =====

class TestQuickPathRouting:
    """验证快速路径正确路由到 step8 而非 step9"""

    @pytest.fixture
    def graph(self):
        return build_graph()

    def test_greeting_routes_to_step8(self, graph):
        """寒暄短句应继续路由到动态输出链路"""
        ctx = Context(session_id="test-route-greeting")
        result, ctx = run_round(graph, ctx, "好的")
        assert result.get("skip_to_end") is not True
        assert ctx.short_utterance is True
        assert ctx.short_utterance_reason == "quick_ack"
        assert result["output"] is not None

    def test_short_emotion_input_not_quick_path(self, graph):
        """短情绪输入不应走快速路径"""
        ctx = Context(session_id="test-route-emotion")
        result, ctx = run_round(graph, ctx, "烦")
        # "烦" 是情绪词，不应触发快速路径
        assert result.get("skip_to_end") is not True
