# -*- coding: utf-8 -*-
"""
Human-OS Engine 3.0 — 随机画像多轮对话测试（复用现有 simulation 模块）

使用：
- simulation.persona_factory.PersonaFactory (LLM 生成随机画像)
- simulation.customer_agent.CustomerAgent (LLM 模拟用户回复)
- graph.builder.build_graph (系统回复)
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import os
import time
import random
from schemas.context import Context
from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from modules.L5.scene_loader import load_scene_config
from simulation.customer_agent import CustomerAgent, Persona
from simulation.persona_factory import UniversalPersonaFactory

SCENES = {
    "sales": "销售场景",
    "management": "管理场景",
    "negotiation": "谈判场景",
    "emotion": "情感场景",
}


def debug_enabled() -> bool:
    return os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip().lower() in {"1", "true", "yes", "on"}


def run_llm_persona_test(scene_id: str, max_rounds: int = 6):
    """用 LLM 生成随机画像 + LLM 模拟用户回复的多轮对话测试"""
    debug_mode = debug_enabled()
    print(f"\n{'='*70}")
    print(f"  LLM 随机画像测试: {SCENES.get(scene_id, scene_id)}")
    print(f"{'='*70}")
    if debug_mode:
        print("  当前为调试模式，会显示内部状态")
    
    # 1. 用 LLM 生成随机画像
    print("\n[LLM 生成随机画像中...]", end="", flush=True)
    factory = UniversalPersonaFactory()
    scenes = factory.get_available_scenes()
    if scene_id not in scenes:
        print(f"场景 '{scene_id}' 不可用，可用: {scenes}")
        return
    
    persona = factory.generate(scene_id)
    print(f"\r{' ' * 30}\r")
    
    print(f"  姓名: {persona.name}")
    print(f"  年龄: {persona.age}")
    print(f"  身份: {persona.role}")
    print(f"  性格: {persona.personality}")
    print(f"  隐藏议程: {persona.hidden_agenda}")
    print(f"  痛点: {persona.pain_points}")
    print(f"  触发词: {persona.trigger_words}")
    print(f"  底线: {persona.dealbreakers}")
    print()
    
    # 2. 初始化
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    ctx = Context(session_id=f"llm-persona-{scene_id}-{int(time.time())}")
    ctx.scene_config = load_scene_config(scene_id)
    
    customer = CustomerAgent(persona)
    
    # 客户开场
    current_input = f"你好，我想了解一下你们的{persona.product}。"
    
    for round_num in range(1, max_rounds + 1):
        print(f"{'─'*70}")
        print(f"  第 {round_num}/{max_rounds} 轮")
        print(f"{'─'*70}")
        print(f"\n[{persona.name}] {current_input}")
        print(f"\n[系统思考中...]", end="", flush=True)
        
        start = time.time()
        try:
            engine_result = runtime.run_stream(
                EngineRequest(session_id=ctx.session_id, user_input=current_input, context=ctx)
            )
            result = engine_result.raw_result
            output = engine_result.output
            ctx = engine_result.context
            elapsed = time.time() - start
            
            print(f"\r{' ' * 20}\r")
            print(f"\n[系统回复] ({elapsed:.1f}s)")
            for line in output.split('\n'):
                print(f"  {line}")
            
            if debug_mode:
                print(f"\n[内部状态]")
                print(f"  目标: {ctx.goal.granular_goal or '未识别'} ({ctx.goal.display_name or ''})")
                print(f"  模式: {result.get('selected_mode', '')}")
                print(f"  情绪: {ctx.user.emotion.type}({ctx.user.emotion.intensity:.1f})")
                print(f"  信任: {ctx.user.trust_level}")
                print(f"  客户信任: {customer.state.trust:.2f}")
                print(f"  客户情绪: {customer.state.emotion:.2f}")
            
        except Exception as e:
            print(f"\r{' ' * 20}\r")
            print(f"\n[错误] {e}")
            output = "抱歉，系统暂时无法回复。"
        
        # 检查终止条件
        if any(kw in current_input for kw in ["再见", "不需要了", "不聊了", "没兴趣"]):
            print(f"\n  [客户离开]")
            break
        if any(kw in current_input for kw in ["下单", "购买", "签合同", "成交"]):
            print(f"\n  [成交!]")
            break
        
        # 3. 用 LLM 生成客户下一轮回复
        if round_num < max_rounds:
            print(f"\n[客户思考中...]", end="", flush=True)
            current_input = customer.generate_reply(output)
            print(f"\r{' ' * 20}\r")
        
        print()
    
    # 总结
    print(f"{'='*70}")
    print(f"  测试总结")
    print(f"{'='*70}")
    print(f"  画像: {persona.name} ({persona.role})")
    print(f"  总轮数: {round_num}")
    if debug_mode:
        print(f"  最终目标: {ctx.goal.granular_goal or '未识别'}")
        print(f"  最终情绪: {ctx.user.emotion.type}({ctx.user.emotion.intensity:.1f})")
        print(f"  最终信任: {ctx.user.trust_level}")
        print(f"  客户最终信任: {customer.state.trust:.2f}")
        print(f"  客户最终情绪: {customer.state.emotion:.2f}")
    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LLM 随机画像多轮对话测试")
    parser.add_argument("--scene", default="all", choices=list(SCENES.keys()) + ["all"])
    parser.add_argument("--rounds", type=int, default=6, help="每场对话最大轮数")
    args = parser.parse_args()
    
    scenes = list(SCENES.keys()) if args.scene == "all" else [args.scene]
    
    for scene_id in scenes:
        run_llm_persona_test(scene_id, args.rounds)
