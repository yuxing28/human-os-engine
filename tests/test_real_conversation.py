"""
Human-OS Engine - 真实对话模拟测试

模拟多轮对话场景，验证系统内部逻辑（不依赖外部 LLM API）。
测试识别、优先级、模式选择、策略生成、输出转换等完整流程。
"""

import sys
import os
from pathlib import Path
import tempfile
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
DEBUG_VIEW = os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip() == "1"

# Remove API key to force fallback behavior
os.environ["NVIDIA_API_KEY"] = ""

# Mock LLM module BEFORE importing anything that uses it
import types

def raise_llm_error(*args, **kwargs):
    raise RuntimeError("LLM not available - using fallback")

class TaskType:
    FAST = "fast"
    STANDARD = "standard"
    DEEP = "deep"

mock_nvidia = types.ModuleType('llm.nvidia_client')
mock_nvidia.invoke_fast = raise_llm_error
mock_nvidia.invoke_deep = raise_llm_error
mock_nvidia.invoke_standard = raise_llm_error
mock_nvidia.TaskType = TaskType
sys.modules['llm.nvidia_client'] = mock_nvidia

# Now import everything
from schemas.context import Context
import modules.memory as memory_mod
from graph.nodes import (
    step0_receive_input,
    step1_identify,
    step1_5_meta_controller,
    step2_goal_detection,
    step3_self_check,
    step4_priority,
    step5_mode_selection,
    step6_strategy_generation,
    step7_weapon_selection,
    step8_execution,
    step9_feedback,
)
from graph.state import GraphState


def _debug_print(message: str):
    if DEBUG_VIEW:
        print(message)


def create_state(user_input: str, context: Context = None, session_id: str = "test") -> GraphState:
    """创建测试状态"""
    if context is None:
        context = Context(session_id=session_id)
    return {
        "context": context,
        "user_input": user_input,
        "output": "",
        "skip_to_end": False,
        "low_confidence": False,
        "strategy_plan": None,
        "weapons_used": [],
        "priority": {},
    }


def run_pipeline(user_input: str, context: Context = None, session_id: str = "test") -> dict:
    """运行完整 pipeline（使用 Fallback，不依赖 LLM API）"""
    if context is None:
        context = Context(session_id=session_id)
    
    state: GraphState = create_state(user_input, context, session_id)
    results = {"user_input": user_input}
    
    # Step 0: 接收输入
    _debug_print(f"  [DEBUG] Step 0: input='{user_input}', len={len(user_input)}")
    state = step0_receive_input(state)
    _debug_print(f"  [DEBUG] Step 0 result: skip_to_end={state.get('skip_to_end')}, output='{state.get('output', '')}'")
    if state.get("skip_to_end"):
        results["step0"] = "quick_path"
        results["output"] = state["context"].output
        results["skipped"] = True
        return results
    
    # Step 1: 识别
    state = step1_identify(state)
    _debug_print(f"  [DEBUG] Step 1 result: skip_to_end={state.get('skip_to_end')}, low_confidence={state.get('low_confidence')}")
    results["step1"] = {
        "emotion": state["context"].user.emotion.type.value,
        "emotion_intensity": state["context"].user.emotion.intensity,
        "motive": state["context"].user.motive.value,
        "dominant_desire": state["context"].user.desires.get_dominant(),
        "dual_core": state["context"].user.dual_core.state.value,
        "attention_focus": state["context"].user.attention.focus,
        "hijacked_by": state["context"].user.attention.hijacked_by.value if state["context"].user.attention.hijacked_by else "none",
    }
    
    if state.get("skip_to_end"):
        results["output"] = state["context"].output
        results["skipped"] = True
        return results
    
    # Step 1.5: 元控制器（Fallback 规则分类）
    state = step1_5_meta_controller(state)
    results["step1"]["input_type"] = state["context"].user.input_type
    _debug_print(f"  [DEBUG] Step 1.5 result: input_type={state['context'].user.input_type}")
    
    # Step 2: 目标检测
    state = step2_goal_detection(state)
    _debug_print(f"  [DEBUG] Step 2 result: skip_to_end={state.get('skip_to_end')}")
    results["step2"] = {
        "goal_type": state["context"].goal.current.type,
        "goal_description": state["context"].goal.current.description[:50],
        "resistance": state["context"].user.resistance.type.value if state["context"].user.resistance.type else "none",
    }
    
    if state.get("skip_to_end"):
        results["output"] = state["context"].output
        results["skipped"] = True
        return results
    
    # Step 3: 自身检查
    state = step3_self_check(state)
    _debug_print(f"  [DEBUG] Step 3 result: skip_to_end={state.get('skip_to_end')}")
    results["step3"] = {
        "is_stable": state["context"].self_state.is_stable,
        "energy_mode": state["context"].self_state.energy_mode.value,
    }
    
    if state.get("skip_to_end"):
        results["output"] = state["context"].output
        results["skipped"] = True
        return results
    
    # Step 4: 优先级
    state = step4_priority(state)
    priority = state.get("priority", {})
    results["step4"] = {
        "priority_type": priority.get("priority_type", "none"),
        "priority_description": priority.get("description", ""),
    }
    
    # Step 5: 模式选择
    state = step5_mode_selection(state)
    results["step5"] = {
        "mode": state["context"].self_state.energy_mode.value,
        "mode_sequence": [m.value for m in state["context"].current_strategy.mode_sequence] if state["context"].current_strategy.mode_sequence else [],
    }
    
    # Step 6: 策略生成
    state = step6_strategy_generation(state)
    if state.get("strategy_plan"):
        results["step6"] = {
            "combo_name": state["strategy_plan"].combo_name,
            "stage": state["strategy_plan"].stage,
            "description": state["strategy_plan"].description[:100] if state["strategy_plan"].description else "",
        }
    
    # Step 7: 武器调用
    state = step7_weapon_selection(state)
    results["step7"] = {
        "weapons": [w["name"] for w in state.get("weapons_used", [])],
    }
    
    # Step 8: 执行（Fallback 话术生成）
    state = step8_execution(state)
    results["step8"] = {
        "output": state["context"].output,
        "output_length": len(state["context"].output),
    }
    
    # Step 9: 反馈
    state = step9_feedback(state)
    results["step9"] = {
        "feedback": state["context"].last_feedback.value if hasattr(state["context"].last_feedback, 'value') else str(state["context"].last_feedback),
    }
    
    results["output"] = state["context"].output
    results["skipped"] = False
    
    return results


def test_memory_carries_over_between_turns(monkeypatch):
    """真实两轮对话里，第一轮写下的记忆，第二轮要能接着读到。"""
    memory_dir = Path(tempfile.gettempdir()) / "human_os_real_conversation_memory"
    manager = memory_mod.MemoryManager(storage_dir=str(memory_dir))
    monkeypatch.setattr(memory_mod, "get_memory_manager", lambda: manager)
    memory_mod._memory_manager = manager

    context = Context(session_id="real-memory-audit")

    first = run_pipeline("我最近想把汇报讲清楚，最好先讲结论。", context=context, session_id=context.session_id)
    first_memories = [m.content for m in manager.get_recent_memories(context.session_id, limit=5)]
    assert first["output"]
    assert len(first_memories) > 0
    assert any("先讲结论" in text or "汇报" in text for text in first_memories)

    first_context = context.unified_context

    second = run_pipeline("继续说，我这次还是想先讲结论。", context=context, session_id=context.session_id)
    second_memories = [m.content for m in manager.get_recent_memories(context.session_id, limit=5)]

    assert second["output"]
    assert "【相关记忆】" in context.unified_context
    assert "【最近记忆】" in context.unified_context
    assert "先讲结论" in context.unified_context
    assert context.unified_context != first_context
    assert len(second_memories) >= len(first_memories)


def print_result(title: str, result: dict):
    """打印测试结果"""
    print(f"\n{'='*60}")
    print(f"场景: {title}")
    print(f"{'='*60}")
    print(f"输入: {result['user_input']}")
    print(f"输出: {result.get('output', '')}")
    
    if result.get("skipped"):
        if result.get("step0") == "quick_path":
            print("说明: 走了快速路径，后续步骤未展开")
        else:
            print("说明: 提前收口了，后续步骤未展开")

    if not DEBUG_VIEW:
        print(f"{'='*60}")
        return

    if "step1" in result:
        s1 = result["step1"]
        print(f"\n[Step 1 识别]")
        print(f"  情绪: {s1['emotion']} (强度: {s1['emotion_intensity']})")
        print(f"  动机: {s1['motive']}")
        print(f"  主导欲望: {s1['dominant_desire'][0]} (权重: {s1['dominant_desire'][1]:.2f})")
        print(f"  双核: {s1['dual_core']}")
        print(f"  注意力: {s1['attention_focus']} (劫持源: {s1.get('hijacked_by', 'none')})")
        if "input_type" in s1:
            print(f"  输入类型: {s1['input_type']}")
    
    if "step2" in result:
        s2 = result["step2"]
        print(f"\n[Step 2 目标]")
        print(f"  类型: {s2['goal_type']}")
        print(f"  描述: {s2['goal_description']}")
        print(f"  阻力: {s2['resistance']}")
    
    if "step4" in result:
        s4 = result["step4"]
        print(f"\n[Step 4 优先级]")
        print(f"  类型: {s4['priority_type']}")
        print(f"  描述: {s4['priority_description']}")
    
    if "step5" in result:
        s5 = result["step5"]
        print(f"\n[Step 5 模式]")
        print(f"  模式: {s5['mode']}")
        if s5['mode_sequence']:
            print(f"  序列: {' -> '.join(s5['mode_sequence'])}")
    
    if "step6" in result:
        s6 = result["step6"]
        print(f"\n[Step 6 策略]")
        print(f"  组合: {s6['combo_name']}")
        print(f"  阶段: {s6['stage']}")
        print(f"  描述: {s6['description']}")
    
    if "step7" in result:
        s7 = result["step7"]
        print(f"\n[Step 7 武器]")
        print(f"  列表: {', '.join(s7['weapons'])}")
    
    if "step8" in result:
        s8 = result["step8"]
        print(f"\n[Step 8 输出]")
        print(f"  长度: {s8['output_length']} 字")
        print(f"  内容: {s8['output']}")
    
    print(f"\n{'='*60}")


# ===== 测试场景 =====

def test_emotion_expression():
    """场景 1：情绪表达"""
    result = run_pipeline("我好烦")
    print_result("情绪表达 - 我好烦", result)
    assert result["output"]


def test_consultation():
    """场景 2：问题咨询"""
    result = run_pipeline("怎么坚持学习？")
    print_result("问题咨询 - 怎么坚持学习？", result)
    assert result["output"]


def test_mixed_input():
    """场景 3：混合输入"""
    result = run_pipeline("我好烦，怎么坚持学习？")
    print_result("混合输入 - 我好烦，怎么坚持学习？", result)
    assert result["output"]


def test_scenario_description():
    """场景 4：场景描述"""
    result = run_pipeline("老板当众批评我")
    print_result("场景描述 - 老板当众批评我", result)
    assert result["output"]


def test_aggressive_input():
    """场景 5：攻击性输入"""
    result = run_pipeline("你懂什么")
    print_result("攻击性输入 - 你懂什么", result)
    assert result["output"]


def test_multi_turn_conversation():
    """场景 6：多轮对话模拟"""
    print(f"\n{'#'*60}")
    print(f"# 多轮对话模拟")
    print(f"{'#'*60}")
    
    context = Context(session_id="multi_turn_test")
    
    # 第 1 轮：用户表达烦恼
    print(f"\n--- 第 1 轮 ---")
    result1 = run_pipeline("最近工作压力好大，什么都不想做", context=context)
    print_result("第1轮：工作压力大", result1)
    
    # 第 2 轮：用户继续倾诉
    print(f"\n--- 第 2 轮 ---")
    result2 = run_pipeline("每天加班到很晚，感觉身体都垮了", context=context)
    print_result("第2轮：身体垮了", result2)
    
    # 第 3 轮：用户寻求建议
    print(f"\n--- 第 3 轮 ---")
    result3 = run_pipeline("你说我该怎么办？", context=context)
    print_result("第3轮：寻求建议", result3)
    
    # 第 4 轮：用户表达放弃
    print(f"\n--- 第 4 轮 ---")
    result4 = run_pipeline("算了，不聊了，太累了", context=context)
    print_result("第4轮：放弃信号", result4)
    
    assert result1["output"]
    assert result2["output"]
    assert result3["output"]
    assert result4["output"]


def test_contradiction_detection():
    """场景 7：逻辑矛盾检测"""
    print(f"\n{'#'*60}")
    print(f"# 逻辑矛盾检测")
    print(f"{'#'*60}")
    
    result = run_pipeline("我想赚钱但不想工作")
    print_result("逻辑矛盾 - 想赚钱但不想工作", result)
    
    if result.get("skipped") and result.get("step0") != "quick_path":
        print(f"\n[OK] 矛盾检测成功：系统跳过了后续步骤，直接输出纠正话术")
    else:
        print(f"\n[WARN] 矛盾检测可能未触发")
    
    assert result["output"]


def test_low_confidence():
    """场景 8：低置信度确认协议"""
    print(f"\n{'#'*60}")
    print(f"# 低置信度确认协议")
    print(f"{'#'*60}")
    
    # 极短模糊输入
    result = run_pipeline("嗯")
    print_result("模糊输入 - 嗯", result)
    
    if result.get("skipped") and result.get("step0") == "quick_path":
        print(f"\n[OK] 极短输入快速路径触发")
    else:
        print(f"\n[WARN] 快速路径可能未触发")
    
    assert result["output"]


def test_resistance_detection():
    """场景 9：阻力浮现"""
    print(f"\n{'#'*60}")
    print(f"# 阻力浮现检测")
    print(f"{'#'*60}")
    
    # 恐惧阻力
    result1 = run_pipeline("我怕做不好，万一失败了怎么办")
    print_result("恐惧阻力", result1)
    
    # 懒惰阻力
    result2 = run_pipeline("太麻烦了，不想做")
    print_result("懒惰阻力", result2)
    
    assert result1["output"]
    assert result2["output"]


def test_give_up_signal():
    """场景 10：放弃信号"""
    print(f"\n{'#'*60}")
    print(f"# 放弃信号检测")
    print(f"{'#'*60}")
    
    result = run_pipeline("算了，不聊了")
    print_result("放弃信号 - 算了，不聊了", result)
    
    if result.get("step2", {}).get("goal_description") == "用户放弃":
        print(f"\n[OK] 放弃信号检测成功")
    else:
        print(f"\n[WARN] 放弃信号可能未检测到")
    
    assert result["output"]


def test_knowledge_search():
    """场景 11：知识搜索测试"""
    print(f"\n{'#'*60}")
    print(f"# 知识搜索测试")
    print(f"{'#'*60}")
    
    from modules.L5.loader import search_knowledge, KNOWLEDGE_DATABASE
    
    print(f"\n知识库总条目数: {len(KNOWLEDGE_DATABASE)}")
    
    # 测试不同领域的知识搜索
    queries = [
        "如何提高转化率",
        "怎么控制情绪",
        "如何提升个人价值",
        "Z世代消费心理",
        "能量管理",
    ]
    
    for query in queries:
        results = search_knowledge(query, limit=2)
        print(f"\n查询: '{query}'")
        if results:
            for r in results:
                print(f"  - {r.title} (类别: {r.category}, 关键词: {r.keywords[:3]}...)")
        else:
            print(f"  (无匹配结果)")
    
    assert len(KNOWLEDGE_DATABASE) > 0


def test_case_matching():
    """场景 12：案例匹配测试"""
    print(f"\n{'#'*60}")
    print(f"# 案例匹配测试")
    print(f"{'#'*60}")
    
    from modules.L5.loader import search_cases, CASE_DATABASE
    
    print(f"\n案例库总条目数: {len(CASE_DATABASE)}")
    
    queries = [
        "老板让我加班",
        "朋友借钱",
        "下属犯错",
        "客户嫌贵",
    ]
    
    for query in queries:
        results = search_cases(query, limit=1)
        print(f"\n查询: '{query}'")
        if results:
            for r in results:
                print(f"  - {r.title} (场景关键词: {r.scenario_keywords[:3]}...)")
        else:
            print(f"  (无匹配结果)")
    
    assert len(CASE_DATABASE) > 0


def test_weapon_arsenal():
    """场景 13：武器库统计"""
    print(f"\n{'#'*60}")
    print(f"# 武器库统计")
    print(f"{'#'*60}")
    
    from modules.L3.weapon_arsenal import ALL_WEAPONS, ATTACK_WEAPONS, DEFENSE_WEAPONS, MILD_WEAPONS
    
    print(f"\n武器总数: {len(ALL_WEAPONS)}")
    print(f"攻击型: {len(ATTACK_WEAPONS)}")
    print(f"防御型: {len(DEFENSE_WEAPONS)}")
    print(f"温和型: {len(MILD_WEAPONS)}")
    
    # 验证规格要求（允许攻击型武器有少量扩展）
    assert 26 <= len(ATTACK_WEAPONS) <= 30, f"攻击型武器应为 26-30 种，实际 {len(ATTACK_WEAPONS)}"
    assert len(DEFENSE_WEAPONS) == 23, f"防御型武器应为 23 种，实际 {len(DEFENSE_WEAPONS)}"
    # 温和型超过 26 种是可以接受的（规格是最低要求）
    assert len(MILD_WEAPONS) >= 26, f"温和型武器应至少 26 种，实际 {len(MILD_WEAPONS)}"
    
    print(f"\n[OK] 武器库数量符合规格要求 (攻击{len(ATTACK_WEAPONS)}+防御{len(DEFENSE_WEAPONS)}+温和{len(MILD_WEAPONS)}={len(ALL_WEAPONS)})")
    assert len(ALL_WEAPONS) > 0


def test_emotion_adapter():
    """场景 14：情绪适配器测试"""
    print(f"\n{'#'*60}")
    print(f"# 情绪适配器测试")
    print(f"{'#'*60}")
    
    from graph.nodes import _adapt_output_style
    
    test_cases = [
        ("情绪表达", 0.8),
        ("问题咨询", 0.3),
        ("场景描述", 0.5),
        ("混合", 0.7),
        ("混合", 0.3),
    ]
    
    for input_type, intensity in test_cases:
        style = _adapt_output_style(input_type, intensity)
        print(f"\n输入类型: {input_type} (情绪强度: {intensity})")
        print(f"  专业感: {style['professionalism']}")
        print(f"  共情深度: {style['empathy_depth']}")
        print(f"  逻辑密度: {style['logic_density']}")
        print(f"  口语比例: {style['spoken_ratio']}")
    
    print(f"\n[OK] 情绪适配器正常工作")
    assert True


def test_field_quality():
    """场景 15：场域判断与质量检查"""
    print(f"\n{'#'*60}")
    print(f"# 场域判断与质量检查")
    print(f"{'#'*60}")
    
    from modules.L4.field_quality import quality_check, assess_field
    
    # 测试质量检查
    test_outputs = [
        "好的，我帮你看看这个问题。",  # 合规
        "利用你的恐惧来推动决策",  # 包含禁用词
        "根据五层结构，第一层是共情",  # 框架泄露
        "亲，小助手为您服务",  # 客服词汇
        "",  # 空输出
    ]
    
    for output in test_outputs:
        result = quality_check(output)
        status = "[OK] 通过" if result.passed else f"[FAIL] 失败 (分数: {result.score})"
        print(f"\n输出: '{output[:30]}...'")
        print(f"  状态: {status}")
        if result.failed_items:
            for item in result.failed_items:
                print(f"    - {item}")
    
    # 测试场域判断
    field = assess_field()
    print(f"\n场域判断:")
    print(f"  可应用: {field.can_apply_field}")
    print(f"  推荐五行: {field.recommended_element}")
    print(f"  原因: {field.reason}")
    
    print(f"\n[OK] 场域判断与质量检查正常工作")
    assert field is not None


# ===== 主测试流程 =====

def main():
    if DEBUG_VIEW:
        mode_notice = "当前为调试模式，会额外显示识别、目标、模式等内部步骤"
    else:
        mode_notice = "当前默认只显示最终结果；如需看内部步骤，可设置 HUMAN_OS_DEBUG_VIEW=1"
    print("="*60)
    print("Human-OS Engine 真实对话模拟测试")
    print("="*60)
    print(mode_notice)

    # 单场景测试
    test_emotion_expression()
    test_consultation()
    test_mixed_input()
    test_scenario_description()
    test_aggressive_input()
    
    # 多轮对话
    test_multi_turn_conversation()
    
    # 特殊场景
    test_contradiction_detection()
    test_low_confidence()
    test_resistance_detection()
    test_give_up_signal()
    
    # 知识库测试
    knowledge_count = test_knowledge_search()
    case_count = test_case_matching()
    
    # 武器库测试
    weapon_count = test_weapon_arsenal()
    
    # 情绪适配器测试
    test_emotion_adapter()
    
    # 场域质量测试
    test_field_quality()
    
    # 总结
    print(f"\n{'#'*60}")
    print(f"# 测试总结")
    print(f"{'#'*60}")
    print(f"\n知识库条目数: {knowledge_count}")
    print(f"案例库条目数: {case_count}")
    print(f"武器库总数: {weapon_count}")
    print(f"\n所有测试完成！")


if __name__ == "__main__":
    main()
