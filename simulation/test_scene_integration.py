"""
Human-OS Engine 3.0 — 场景插件集成验证脚本

验证目标：
1. 场景配置是否成功加载。
2. 细粒度目标识别是否准确（基于关键词）。
3. 策略选择是否优先使用场景偏好。
4. 武器黑名单是否生效。
"""

import sys
import os
import json

# 设置路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 修复 Windows 控制台编码
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from schemas.context import Context
from modules.L5.scene_loader import load_scene_config

def run_test_case(runtime, context, user_input, expected_goal, expected_combo_keywords, forbidden_weapons):
    """运行单个测试用例"""
    print(f"\n{'='*60}")
    print(f"输入: {user_input}")
    print(f"期望目标: {expected_goal}")
    print(f"期望策略包含: {expected_combo_keywords}")
    print(f"禁止武器: {forbidden_weapons}")
    print("-" * 60)

    try:
        engine_result = runtime.run_stream(
            EngineRequest(session_id=context.session_id, user_input=user_input, context=context)
        )
        result = engine_result.raw_result
    except Exception as e:
        print(f"管道执行失败: {e}")
        return False

    ctx = engine_result.context
    strategy = result.get("strategy_plan")
    weapons = result.get("weapons_used", [])

    # 1. 验证目标识别
    actual_goal = getattr(ctx.goal, 'granular_goal', None)
    print(f"识别目标: {actual_goal}")
    if actual_goal == expected_goal:
        print("目标识别正确")
    else:
        print(f"目标识别失败 (期望: {expected_goal})")

    # 2. 验证策略选择
    actual_combo = strategy.combo_name if strategy else "None"
    print(f"选择策略: {actual_combo}")
    if any(kw in actual_combo for kw in expected_combo_keywords):
        print("策略匹配场景偏好")
    else:
        print(f"策略未匹配偏好 (可能是回退到全局策略)")

    # 3. 验证武器黑名单
    weapon_names = [w["name"] for w in weapons]
    print(f"使用武器: {weapon_names}")
    used_forbidden = [w for w in weapon_names if w in forbidden_weapons]
    if not used_forbidden:
        print("武器黑名单生效")
    else:
        print(f"使用了禁止武器: {used_forbidden}")

    return actual_goal == expected_goal and not used_forbidden

def main():
    print("开始场景插件集成验证...")
    
    # 加载销售场景配置
    try:
        # 确保路径正确 (脚本在 simulation/ 下)
        config_dir = os.path.join(os.path.dirname(__file__), '..', 'config', 'scenes')
        config = load_scene_config("sales", config_dir=config_dir)
        print(f"成功加载销售场景配置: {config.scene_id} v{config.version}")
    except Exception as e:
        print(f"加载配置失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 构建图
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    
    # ================= 测试用例 1 =================
    # 克服拒绝 (新手痛点)
    context = Context(session_id="test-sales-1")
    context.scene_config = config
    
    test1_passed = run_test_case(
        runtime, context,
        "今天又被挂了 10 个电话，我真的不想打了，太受挫了。",
        expected_goal="overcome_rejection",
        expected_combo_keywords=["共情", "正常化"],
        forbidden_weapons=["制造紧迫感", "威胁", "质疑"]
    )

    # ================= 测试用例 2 =================
    # 打破现状 (No Decision Loss)
    context = Context(session_id="test-sales-2")
    context.scene_config = config
    
    test2_passed = run_test_case(
        runtime, context,
        "客户说方案不错，但想再想想，怕选错供应商，想维持现状。",
        expected_goal="break_status_quo",
        expected_combo_keywords=["提供确定性", "案例证明"],
        forbidden_weapons=["描绘共同未来", "赋予身份"]
    )

    # ================= 测试用例 3 =================
    # 减少行政负担
    context = Context(session_id="test-sales-3")
    context.scene_config = config
    
    test3_passed = run_test_case(
        runtime, context,
        "每天填 CRM 报表太麻烦了，占了我大部分时间，根本没时间跑客户。",
        expected_goal="reduce_admin_burden",
        expected_combo_keywords=["懒惰", "互惠"],
        forbidden_weapons=["描绘共同未来", "授权"]
    )

    # ================= 总结 =================
    print(f"\n{'='*60}")
    print("验证总结:")
    print(f"测试 1 (克服拒绝): {'通过' if test1_passed else '失败'}")
    print(f"测试 2 (打破现状): {'通过' if test2_passed else '失败'}")
    print(f"测试 3 (减少行政): {'通过' if test3_passed else '失败'}")
    print(f"{'='*60}")
    
    if test1_passed and test2_passed and test3_passed:
        print("所有测试通过！场景插件集成成功。")
    else:
        print("部分测试未通过，请检查日志。")

if __name__ == "__main__":
    main()
