"""
Test speech generation directly to find the error
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ["NVIDIA_API_KEY"] = ""

from prompts.speech_generator import generate_speech

test_layers = [
    {"layer": 1, "name": "即时反应", "weapon": "共情", "purpose": "情绪共振"},
    {"layer": 2, "name": "理解确认", "weapon": "镜像模仿", "purpose": "确认理解"},
    {"layer": 5, "name": "方向引导", "weapon": "给予价值", "purpose": "给出选择"},
]

test_user_state = {
    "emotion_type": "愤怒",
    "emotion_intensity": 0.6,
    "motive": "生活期待",
    "dominant_desire": "wrath",
    "dominant_weight": 0.06,
    "dual_core_state": "对抗",
}

test_strategy = {
    "mode": "A",
    "stage": "钩子",
    "description": "先激发贪婪（展示机会），再用担忧（提示风险）推动决策",
}

test_weapons = [
    {"name": "共情", "type": "温和型", "example": "这压力确实大"},
    {"name": "给予价值", "type": "温和型", "example": "我帮你看看"},
]

test_style = {
    "professionalism": 0.2,
    "empathy_depth": 0.9,
    "logic_density": 0.2,
    "spoken_ratio": 0.85,
}

try:
    result = generate_speech(
        layers=test_layers,
        user_state=test_user_state,
        strategy_plan=test_strategy,
        weapons_used=test_weapons,
        memory_context="",
        knowledge_content="",
        style_params=test_style,
    )
    print(f"SUCCESS: {result}")
except Exception as e:
    import traceback
    print(f"ERROR: {e}")
    traceback.print_exc()
