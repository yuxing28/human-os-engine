"""
混合调度多轮对话演练 — 真实 LLM 调用

模拟 7 轮真实对话，验证场景识别、主从切换、黑名单融合、副场景策略注入。
每轮输出场景路由结果 + 系统回复。
"""
import io
import os
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from graph.builder import build_graph
from modules.engine_runtime import EngineRequest, EngineRuntime
from schemas.context import Context
from modules.L5.skill_registry import get_registry


def debug_enabled() -> bool:
    return os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip().lower() in {"1", "true", "yes", "on"}

# ============================================================
# 7 轮对话剧本：销售 → 情绪混合 → 情绪爆发 → 情绪持续 → 回归商业 → 谈判 → 签约+担忧
# ============================================================

CONVERSATION = [
    ("你好，我想了解一下你们的产品报价和合同条款。", "开场：纯商业咨询"),
    ("价格太贵了，而且我最近压力很大，家里出了点事，心情很糟糕。", "混合：商业+情绪"),
    ("你们是不是在耍我？我快崩溃了！每天失眠，什么都做不好！", "情绪爆发"),
    ("算了，不聊这个了。我真的很伤心绝望，感觉撑不下去了。", "情绪持续"),
    ("好吧，回到正题。这个合同能便宜点吗？谈判空间在哪里？", "回归商业"),
    ("这个价格我接受不了，你们底线在哪里？让步空间呢？", "谈判博弈"),
    ("行吧，那签合同吧。不过我还是有点担心，怕出问题没人管。", "签约+担忧"),
]

print("=" * 80)
print("混合调度多轮对话演练 — 真实 LLM 调用")
print("=" * 80)
DEBUG_MODE = debug_enabled()
if DEBUG_MODE:
    print("当前为调试模式，会显示内部状态")

ctx = Context(session_id="hybrid-multiturn-demo")
graph = build_graph()
runtime = EngineRuntime(lambda: graph)
registry = get_registry()

prev_primary = ""

for i, (user_input, desc) in enumerate(CONVERSATION, 1):
    print(f"\n{'═' * 80}")
    print(f"第 {i} 轮 | {desc}")
    print(f"{'─' * 80}")
    print(f"👤 用户: {user_input}")

    # 1. 场景识别（不依赖图执行）
    primary, secondaries, scores = registry.match_scenes(user_input)
    switched = prev_primary and primary != prev_primary
    if primary:
        prev_primary = primary

    print(f"\n📡 场景路由:")
    print(f"   Primary:   {primary or 'None'}")
    print(f"   Secondary: {secondaries}")
    print(f"   Scores:    { {k: round(v, 4) for k, v in scores.items()} }")
    if switched:
        print(f"   ⚡ 换挡: {prev_primary if not switched else primary}")

    # 2. 图执行（真实 LLM 调用）
    start = time.time()
    try:
        result = runtime.run_stream(
            EngineRequest(session_id=ctx.session_id, user_input=user_input, context=ctx)
        )
        elapsed = time.time() - start
        output = result.output or "无输出"
        print(f"\n🤖 系统: {output}")
        if DEBUG_MODE:
            mode = result.raw.get("selected_mode", "")
            emotion = ctx.user.emotion.type.value if hasattr(ctx.user.emotion.type, 'value') else str(ctx.user.emotion.type)
            intensity = ctx.user.emotion.intensity
            print(f"\n📊 内部状态:")
            print(f"   模式: {mode} | 情绪: {emotion}({intensity:.2f}) | 耗时: {elapsed:.1f}s")
            print(f"   Primary: {ctx.primary_scene} | Secondary: {ctx.secondary_scenes}")
            if ctx.secondary_scene_strategy:
                print(f"   副场景策略: {ctx.secondary_scene_strategy[:120]}...")
            if ctx.merged_weapon_blacklist:
                print(f"   黑名单: {len(ctx.merged_weapon_blacklist)} 个类别")

    except Exception as e:
        print(f"\n❌ 错误: {e}")

print(f"\n{'═' * 80}")
print("演练完成")
print(f"{'═' * 80}")
