# -*- coding: utf-8 -*-
"""
Human-OS Engine 3.0 — 随机画像多轮对话测试

使用 LLM 生成随机用户画像，进行多轮对话测试。
"""
import sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import os
import time
import random
from schemas.context import Context
from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from modules.L5.scene_loader import load_scene_config
from llm.nvidia_client import invoke_deep

SCENES = {
    "sales": "销售场景",
    "management": "管理场景",
    "negotiation": "谈判场景",
    "emotion": "情感场景",
}


def debug_enabled() -> bool:
    return os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip().lower() in {"1", "true", "yes", "on"}

# 用户模拟回复模板
USER_REPLIES = {
    "positive": [
        "好的，我明白了。",
        "有道理，我确实是这样想的。",
        "你说得对，我需要再考虑一下。",
        "嗯，听起来不错。",
        "好，那接下来呢？",
    ],
    "neutral": [
        "我不太确定，能再说清楚一点吗？",
        "这个我不太了解，能举个例子吗？",
        "嗯...我再想想。",
        "好吧，但我还有疑问。",
    ],
    "negative": [
        "我还是觉得不太行。",
        "这听起来像套路，我不太相信。",
        "别人家可不是这么说的。",
        "我觉得你在敷衍我。",
    ],
    "challenging": [
        "你说的这些有数据支持吗？",
        "如果出了问题谁负责？",
        "价格能再低一点吗？",
        "我需要跟其他人商量一下。",
    ],
}


def generate_random_persona(scene_id: str) -> dict:
    """用 LLM 生成随机用户画像"""
    scene_desc = {
        "sales": "B2B 软件采购客户",
        "management": "企业员工或中层管理者",
        "negotiation": "商务谈判对手",
        "emotion": "有情感困扰的普通人",
    }
    
    prompt = f"""你是一个角色扮演专家。请为以下场景生成一个真实的用户画像。

场景：{scene_desc.get(scene_id, "通用对话")}

请输出 JSON 格式：
{{
  "name": "中文姓名",
  "age": 年龄数字,
  "role": "职业或身份",
  "personality": "性格描述（一句话）",
  "hidden_concern": "隐藏的担忧或动机（一句话）",
  "opening_line": "开场白（一句话，要真实自然）",
  "communication_style": "沟通风格（direct/emotional/analytical/avoidant 之一）"
}}

只输出 JSON，不要其他内容。"""

    try:
        result = invoke_deep(prompt, "你是一个专业的角色扮演专家。")
        result = result.strip()
        if result.startswith("```"):
            result = result.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        if result.startswith("json"):
            result = result[4:].strip()
        
        persona = json.loads(result)
        return {
            "name": persona.get("name", "匿名用户"),
            "age": persona.get("age", 30),
            "role": persona.get("role", "未知"),
            "personality": persona.get("personality", "普通"),
            "hidden_concern": persona.get("hidden_concern", "无"),
            "opening_line": persona.get("opening_line", "你好"),
            "communication_style": persona.get("communication_style", "direct"),
        }
    except Exception as e:
        # Fallback to template
        return {
            "name": "测试用户",
            "age": 30,
            "role": "未知",
            "personality": "普通",
            "hidden_concern": "无",
            "opening_line": "你好，我想咨询一下",
            "communication_style": "direct",
        }


def simulate_user_reply(system_output: str, style: str, round_num: int) -> str:
    """模拟用户回复"""
    templates = USER_REPLIES.get(style, USER_REPLIES["neutral"])
    
    if round_num <= 2:
        return random.choice(templates)
    
    # 根据系统回复质量调整
    if len(system_output) < 20 or "错误" in system_output:
        return random.choice(USER_REPLIES["negative"])
    if len(system_output) > 200:
        return random.choice(USER_REPLIES["challenging"])
    
    return random.choice(templates)


def run_random_test(scene_id: str, max_rounds: int = 5):
    """运行随机画像多轮对话测试"""
    debug_mode = debug_enabled()
    print(f"\n{'='*70}")
    print(f"  随机画像测试: {SCENES.get(scene_id, scene_id)}")
    print(f"{'='*70}")
    if debug_mode:
        print("  当前为调试模式，会显示内部状态")
    
    # 生成随机画像
    print("\n[生成随机画像中...]", end="", flush=True)
    persona = generate_random_persona(scene_id)
    print(f"\r{' ' * 30}\r")
    
    print(f"  姓名: {persona['name']}")
    print(f"  年龄: {persona['age']}")
    print(f"  身份: {persona['role']}")
    print(f"  性格: {persona['personality']}")
    print(f"  隐藏担忧: {persona['hidden_concern']}")
    print(f"  沟通风格: {persona['communication_style']}")
    print()
    
    # 初始化
    graph = build_graph()
    runtime = EngineRuntime(lambda: graph)
    ctx = Context(session_id=f"random-{scene_id}-{int(time.time())}")
    ctx.scene_config = load_scene_config(scene_id)
    
    current_input = persona["opening_line"]
    style = persona["communication_style"]
    
    for round_num in range(1, max_rounds + 1):
        print(f"{'─'*70}")
        print(f"  第 {round_num}/{max_rounds} 轮")
        print(f"{'─'*70}")
        print(f"\n[{persona['name']}] {current_input}")
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
            
        except Exception as e:
            print(f"\r{' ' * 20}\r")
            print(f"\n[错误] {e}")
            output = ""
        
        # 生成下一轮用户输入
        if round_num < max_rounds:
            current_input = simulate_user_reply(output, style, round_num)
        
        print()
    
    # 总结
    print(f"{'='*70}")
    print(f"  测试总结")
    print(f"{'='*70}")
    print(f"  画像: {persona['name']} ({persona['role']})")
    print(f"  总轮数: {max_rounds}")
    if debug_mode:
        print(f"  最终目标: {ctx.goal.granular_goal or '未识别'}")
        print(f"  最终情绪: {ctx.user.emotion.type}({ctx.user.emotion.intensity:.1f})")
        print(f"  最终信任: {ctx.user.trust_level}")
    print()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="随机画像多轮对话测试")
    parser.add_argument("--scene", default="all", choices=list(SCENES.keys()) + ["all"])
    parser.add_argument("--rounds", type=int, default=5, help="每场对话最大轮数")
    parser.add_argument("--count", type=int, default=1, help="每个场景生成几个画像")
    args = parser.parse_args()
    
    scenes = list(SCENES.keys()) if args.scene == "all" else [args.scene]
    
    for scene_id in scenes:
        for i in range(args.count):
            if args.count > 1:
                print(f"\n>>> 第 {i+1}/{args.count} 个画像")
            run_random_test(scene_id, args.rounds)
