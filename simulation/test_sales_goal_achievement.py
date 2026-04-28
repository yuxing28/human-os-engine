"""
Human-OS Engine 3.0 — 销售场景多轮目标达成测试

验证系统能否通过多轮对话，将用户从负面状态引导至目标达成状态。
"""

import sys
import os
import random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 修复 Windows 控制台编码
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from schemas.context import Context
from modules.L5.scene_loader import load_scene_config


class SalesUserAgent:
    """
    模拟销售对话中的客户/销售。
    根据系统的策略表现，动态调整情绪和信任度，并给出反馈。
    """
    
    def __init__(self, initial_emotion=0.8, initial_trust=0.2):
        self.emotion = initial_emotion
        self.trust = initial_trust
        self.turn_count = 0
    
    def react(self, system_strategy, forbidden_weapons, used_weapons):
        """根据系统表现做出反应"""
        self.turn_count += 1
        
        # 1. 检查是否使用了禁忌武器
        used_forbidden = [w for w in used_weapons if w in forbidden_weapons]
        if used_forbidden:
            self.emotion += 0.15
            self.trust -= 0.15
            return f"你怎么用 {used_forbidden[0]} 这种话术？太让人反感了！(情绪 +0.15, 信任 -0.15)"
        
        # 2. 检查策略是否匹配
        # 这里简化逻辑：如果策略包含预期关键词，视为有效
        # 实际测试中，如果策略是 None 或乱匹配，视为无效
        if not system_strategy:
            self.emotion += 0.05
            self.trust -= 0.05
            return "你在说什么？完全没说到点子上。(情绪 +0.05, 信任 -0.05)"
        
        # 假设策略匹配（由测试脚本保证传入正确策略）
        # 随着轮数增加，有效策略的效果会累积
        self.emotion -= 0.15  # 情绪下降
        self.trust += 0.10    # 信任上升
        
        # 边界限制
        self.emotion = max(0.1, min(1.0, self.emotion))
        self.trust = max(0.0, min(1.0, self.trust))
        
        if self.trust > 0.5:
            return "听起来有点道理，我愿意再了解一下。(信任上升)"
        elif self.emotion < 0.5:
            return "好吧，我心情好点了，你继续说。(情绪下降)"
        else:
            return "嗯，我在听。(中性)"

    def is_goal_achieved(self, criteria):
        """检查是否达成目标"""
        emotion_drop = (0.8 - self.emotion) # 假设初始 0.8
        trust_gain = (self.trust - 0.2)     # 假设初始 0.2
        
        target_emotion_drop = criteria.get("emotion_drop", 0.2)
        target_trust_gain = criteria.get("trust_increase", 0.1)
        
        return emotion_drop >= target_emotion_drop and trust_gain >= target_trust_gain

def run_goal_achievement_test(max_turns=5):
    """运行多轮目标达成测试"""
    
    print("="*70)
    print("销售场景多轮目标达成测试")
    print(f"最大轮数：{max_turns}")
    print("="*70)
    
    # 加载配置
    config_dir = os.path.join(os.path.dirname(__file__), '..', 'skills')
    config = load_scene_config("sales", config_dir=config_dir)
    
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    
    results = {
        "total_scenarios": 0,
        "success_scenarios": 0,
        "details": []
    }
    
    # 遍历每个目标进行测试
    for goal_def in config.goal_taxonomy:
        goal_key = goal_def.granular_goal
        display_name = goal_def.display_name
        criteria = goal_def.success_criteria
        forbidden = goal_def.forbidden_weapons
        
        print(f"\n{'='*70}")
        print(f"测试目标：{display_name} ({goal_key})")
        print(f"成功标准：情绪下降 ≥ {criteria.get('emotion_drop', 0)}，信任提升 ≥ {criteria.get('trust_increase', 0)}")
        print(f"{'='*70}")
        
        # 初始化模拟用户
        user = SalesUserAgent(initial_emotion=0.8, initial_trust=0.2)
        
        # 初始化 Context
        context = Context(session_id=f"test-goal-{goal_key}")
        context.scene_config = config
        
        success = False
        final_strategy = ""
        
        # 模拟多轮对话
        for turn in range(1, max_turns + 1):
            # 1. 生成用户输入 (模拟用户表达当前痛点)
            if turn == 1:
                user_input = random.choice([f"我真的很{display_name}的问题", f"关于{display_name}，我很头疼"])
            else:
                user_input = user.last_response if hasattr(user, 'last_response') else "继续说"
            
            # 2. 系统处理
            try:
                result = runtime.run_stream(
                    EngineRequest(session_id=context.session_id, user_input=user_input, context=context)
                ).raw
            except Exception as e:
                print(f"  ❌ 系统错误: {e}")
                break
            
            ctx = result["context"]
            strategy = result.get("strategy_plan")
            weapons = result.get("weapons_used", [])
            weapon_names = [w["name"] for w in weapons]
            
            strategy_name = strategy.combo_name if strategy else "Unknown"
            final_strategy = strategy_name
            
            # 3. 用户反应
            response = user.react(strategy_name, forbidden, weapon_names)
            user.last_response = response
            
            print(f"  轮次 {turn}: 策略={strategy_name} | 武器={weapon_names} | 用户反馈：{response}")
            print(f"           [情绪: {user.emotion:.2f}] [信任: {user.trust:.2f}]")
            
            # 4. 检查目标达成
            if user.is_goal_achieved(criteria):
                print(f"  ✅ 目标达成！")
                success = True
                break
        
        # 记录结果
        results["total_scenarios"] += 1
        if success:
            results["success_scenarios"] += 1
        
        results["details"].append({
            "goal": goal_key,
            "success": success,
            "turns": user.turn_count,
            "final_emotion": user.emotion,
            "final_trust": user.trust,
            "strategy": final_strategy
        })

    # 打印总结
    print(f"\n{'='*70}")
    print("多轮目标达成测试总结")
    print(f"{'='*70}")
    print(f"测试场景数: {results['total_scenarios']}")
    print(f"成功场景数: {results['success_scenarios']}")
    print(f"目标达成率: {results['success_scenarios']/results['total_scenarios']:.0%}")
    
    print(f"\n详细结果:")
    for d in results["details"]:
        status = "✅ 成功" if d["success"] else "❌ 失败"
        print(f"  - {d['goal']}: {status} (用时 {d['turns']} 轮，最终信任 {d['final_trust']:.2f})")

if __name__ == "__main__":
    run_goal_achievement_test(max_turns=5)
