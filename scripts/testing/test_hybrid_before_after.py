"""
混合调度 3.3C 前后对比测试

对比：
- BEFORE: 只有主场景 Prompt，副场景被忽略
- AFTER:  主场景 + 副场景策略指令注入到 Prompt

测试用例：混合场景输入（销售 + 情感）
"""

import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from prompts.speech_generator import build_speech_prompt


def debug_enabled() -> bool:
    return os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip().lower() in {"1", "true", "yes", "on"}

# ===== 测试数据 =====

TEST_LAYERS = [
    {"layer": 1, "name": "即时反应", "weapon": "共情", "purpose": "情绪共振"},
    {"layer": 2, "name": "理解确认", "weapon": "镜像模仿", "purpose": "确认理解"},
    {"layer": 3, "name": "共情支持", "weapon": "正常化", "purpose": "降低焦虑"},
    {"layer": 4, "name": "具体追问", "weapon": "好奇", "purpose": "聚焦问题"},
    {"layer": 5, "name": "方向引导", "weapon": "给予价值", "purpose": "给出选择"},
]

TEST_USER_STATE = {
    "emotion_type": "挫败",
    "emotion_intensity": 0.7,
    "motive": "回避恐惧",
    "dominant_desire": "fear",
    "dominant_weight": 0.8,
    "dual_core_state": "对抗",
}

TEST_STRATEGY = {
    "mode": "B",
    "stage": "钩子",
    "description": "消除恐惧+激活贪婪",
}

TEST_WEAPONS = [
    {"name": "共情", "type": "温和型"},
    {"name": "正常化", "type": "温和型"},
]

# 模拟副场景策略指令（由 Step 2 构建）
SECONDARY_STRATEGY = """检测到用户存在【emotion】诉求（匹配度 65%），请在推进sales目标时，适当使用以下策略进行缓冲：共情+正常化、赋予身份+鼓励。"""

# ===== 对比测试 =====

print("=" * 80)
print("混合调度 3.3C — 前后对比测试")
print("=" * 80)
DEBUG_MODE = debug_enabled()
if DEBUG_MODE:
    print("当前为调试模式，会显示 Prompt 细节")

# --- BEFORE: 无副场景策略 ---
print("\n【BEFORE】无副场景策略注入")
print("-" * 40)

system_before, user_before = build_speech_prompt(
    layers=TEST_LAYERS,
    user_state=TEST_USER_STATE,
    strategy_plan=TEST_STRATEGY,
    weapons_used=TEST_WEAPONS,
    skill_prompt="【销售技能】你的目标是推进合作，注意不要使用逼迫话术。",
    secondary_scene_strategy="",  # 空 = 旧行为
)

print(f"系统 Prompt 长度: {len(system_before)} 字符")
print(f"用户 Prompt 长度: {len(user_before)} 字符")
print(f"包含【副场景策略】: {'【副场景策略】' in user_before}")

# --- AFTER: 有副场景策略 ---
print("\n【AFTER】有副场景策略注入")
print("-" * 40)

system_after, user_after = build_speech_prompt(
    layers=TEST_LAYERS,
    user_state=TEST_USER_STATE,
    strategy_plan=TEST_STRATEGY,
    weapons_used=TEST_WEAPONS,
    skill_prompt="【销售技能】你的目标是推进合作，注意不要使用逼迫话术。",
    secondary_scene_strategy=SECONDARY_STRATEGY,
)

print(f"系统 Prompt 长度: {len(system_after)} 字符")
print(f"用户 Prompt 长度: {len(user_after)} 字符")
print(f"包含【副场景策略】: {'【副场景策略】' in user_after}")

# --- 差异分析 ---
print("\n【差异分析】")
print("-" * 40)

diff_len = len(user_after) - len(user_before)
print(f"用户 Prompt 长度变化: +{diff_len} 字符 ({diff_len/len(user_before)*100:.1f}% 增长)")

# 检查副场景指令是否被正确注入
if SECONDARY_STRATEGY in user_after:
    print("✅ 副场景策略指令已注入 Prompt")
    # 找到注入位置
    idx = user_after.find("【副场景策略】")
    print(f"   注入位置: 第 {idx} 字符处（在【技能专属指令】之后）")
    if DEBUG_MODE:
        injected = user_after[idx:idx+200]
        print(f"   注入内容预览: {injected[:150]}...")
else:
    print("❌ 副场景策略指令未注入")

# 检查 skill_prompt 是否也被正确传递（修复的 Bug）
if "【销售技能】" in user_after:
    print("✅ skill_prompt 已正确传递（Bug 已修复）")
else:
    print("❌ skill_prompt 未传递（Bug 仍存在）")

if DEBUG_MODE:
    print("\n【完整用户 Prompt 对比（节选）】")
    print("-" * 40)

    print("\n>>> BEFORE (末尾 300 字符):")
    print(user_before[-300:])

    print("\n>>> AFTER (末尾 500 字符):")
    print(user_after[-500:])

# --- 模拟真实场景 ---
print("\n" + "=" * 80)
print("真实场景模拟：用户输入 = '老板，我最近家里压力大，但这季度业绩我也做到了第一，能不能涨薪？'")
print("=" * 80)

# 模拟 Step 2 识别结果
print("\n【Step 2 识别结果】")
print("  Primary: sales (0.72)")
print("  Secondary: emotion (0.65), negotiation (0.48)")
print("  副场景策略指令: 已构建")
if DEBUG_MODE:
    print(f"  {SECONDARY_STRATEGY}")

if DEBUG_MODE:
    print("\n【注入到 LLM 的完整指令（AFTER）】")
    print("-" * 40)
    print(user_after[-400:])

print("\n" + "=" * 80)
print("结论：")
print("  BEFORE: LLM 只知道销售目标，不知道用户有情感诉求 → 回复可能冷漠、功利")
print("  AFTER:  LLM 知道销售是主线，但用户有情感焦虑 → 回复会兼顾推进目标和共情缓冲")
print("=" * 80)
