"""
Human-OS Engine 3.0 — 分层目标销售场景验证测试

测试场景：B2B 采购经理
用户输入：嫌贵（贪婪） + 怕担责（恐惧） + 态度强硬（傲慢）
预期行为：系统识别出核心阻力是“恐惧”，优先提供确定性，而非盲目降价。
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.'))

# Fix Windows console encoding
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from schemas.context import Context


def debug_enabled() -> bool:
    return os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip().lower() in {"1", "true", "yes", "on"}

def test_layered_goals_sales():
    debug_mode = debug_enabled()
    print("="*80)
    print("测试：B2B 采购经理（嫌贵 + 怕担责 + 傲慢）")
    print("="*80)
    if debug_mode:
        print("当前为调试模式，会显示分层识别和策略细节")
    
    # 1. 初始化
    context = Context(session_id="test-b2b-manager")
    # 加载销售场景配置（如果有的话）
    try:
        from modules.L5.scene_loader import load_scene_config
        context.scene_config = load_scene_config("sales")
    except:
        pass
    
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    
    # 2. 构造复杂输入
    user_input = "你们这个报价太高了，而且万一实施失败，这责任我可担不起，别拿那些虚头巴脑的来忽悠我。"
    print(f"\n[用户输入]: {user_input}")
    
    # 3. 运行系统
    try:
        engine_result = runtime.run_stream(
            EngineRequest(session_id=context.session_id, user_input=user_input, context=context)
        )
        result = engine_result.raw_result
        ctx = engine_result.context

        res_type = ctx.user.resistance.type.value if hasattr(ctx.user.resistance.type, 'value') else str(ctx.user.resistance.type)
        res_intensity = ctx.user.resistance.intensity
        if debug_mode:
            goal_type = ctx.goal.current.type
            print(f"\n[L1 价值层]: {goal_type}")
            print(f"[L2 阻力层]: {res_type} (强度: {res_intensity})")
        
        # 预期：恐惧优先
        if res_type in ["fear", "恐惧"]:
            print("✅ 阻力识别正确：系统识别出核心阻力是恐惧（怕担责）。")
        else:
            print(f"⚠️ 阻力识别偏差：识别为 {res_type}，预期为恐惧。")
        
        # 6. 检查 Step 6 策略
        strategy = result.get("strategy_plan")
        combo = strategy.combo_name if strategy else "None"
        stage = strategy.stage if strategy else "None"
        desc = strategy.description[:50] if strategy else "None"
        if debug_mode:
            print(f"[策略组合]: {combo} (阶段: {stage})")
            print(f"[输入类型]: {ctx.user.input_type.value if hasattr(ctx.user.input_type, 'value') else str(ctx.user.input_type)}")
            print(f"[策略描述]: {desc}")
        
        # 预期：匹配恐惧的策略（如“提供确定性”）
        if "确定性" in combo or "案例" in combo or "提供确定性" in combo:
            print("✅ 策略匹配正确：系统选择了针对恐惧的确定性策略。")
        else:
            print(f"⚠️ 策略匹配偏差：选择了 {combo}。")
        
        # 7. 检查输出话术
        output = engine_result.output
        print(f"\n💬 系统输出:\n{output}")
        
        # 验证话术内容
        has_guarantee = any(kw in output for kw in ["保障", "案例", "确定性", "风险", "成功", "放心", "免费", "协议", "承诺", "阶段", "目标"])
        has_discount = any(kw in output for kw in ["降价", "打折", "优惠", "便宜"])
        
        if has_guarantee and not has_discount:
            print("\n✅ 话术验证通过：系统提供了保障/确定性，未盲目降价。")
        elif has_discount:
            print("\n❌ 话术验证失败：系统错误地使用了降价策略。")
        else:
            print("\n⚠️ 话术验证警告：未检测到明显的保障关键词。")
            
    except Exception as e:
        print(f"\n❌ 测试执行异常: {e}")
        if debug_mode:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_layered_goals_sales()
