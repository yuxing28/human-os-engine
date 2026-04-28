"""
混合调度沙盒测试 — 随机场景多轮对话

随机挑选场景，进行多轮对话，验证场景是否按用户输入正确切换。
"""
import io
import os
import random
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
# 预定义的多轮对话剧本（覆盖 4 个场景的混合切换）
# ============================================================

SCENARIOS = {
    "销售→情感→谈判→销售": [
        ("你好，我想了解一下你们的产品报价和合同条款。", "销售开场"),
        ("价格太贵了，而且我最近压力很大，家里出了点事，心情很糟糕。", "销售+情感混合"),
        ("你们是不是在耍我？我快崩溃了！每天失眠，什么都做不好！", "情绪爆发"),
        ("算了，不聊这个了。我真的很伤心绝望，感觉撑不下去了。", "情绪持续"),
        ("好吧，回到正题。这个合同能便宜点吗？谈判空间在哪里？", "回归商业"),
        ("这个价格我接受不了，你们底线在哪里？让步空间呢？", "谈判博弈"),
        ("行吧，那签合同吧。不过我还是有点担心，怕出问题没人管。", "签约+担忧"),
    ],
    "管理→情感→销售→管理": [
        ("我们团队最近绩效很差，下属都不配合工作。", "管理开场"),
        ("说实话，我现在每天都睡不着，压力太大了。", "管理+情感"),
        ("我觉得自己很失败，什么都做不好，客户也在流失。", "情绪崩溃"),
        ("算了，先不说这些。我想问问你们有没有什么好的销售方案能帮团队提升业绩？", "转向销售"),
        ("这个方案听起来不错，但预算有限，能便宜点吗？", "销售谈判"),
        ("我需要回去跟团队讨论一下，看看大家的反馈。", "回归管理"),
    ],
    "谈判→销售→情感→谈判": [
        ("我们已经在谈判桌上坐了三天了，还是没达成一致。", "谈判开场"),
        ("你们的报价太高了，我们预算有限，能不能再让一步？", "谈判+销售"),
        ("说实话，这个项目对我很重要，如果谈不成我压力会很大。", "情感流露"),
        ("我现在真的很焦虑，失眠好几天了。", "情绪持续"),
        ("好吧，我们回到谈判。如果你们能降到这个价格，我可以今天签。", "回归谈判"),
        ("成交。不过我希望后续服务能跟上。", "签约"),
    ],
    "情感→销售→管理→情感": [
        ("我最近真的很痛苦，感觉生活失去了方向。", "情感开场"),
        ("也许我应该找点事情做，比如学点新技能或者做点副业。你们有什么推荐的产品吗？", "情感→销售"),
        ("这个产品看起来不错，但我团队可能用不了，他们水平参差不齐。", "销售→管理"),
        ("算了，我现在没心情管这些。我还是先调整好自己的状态吧。", "管理→情感"),
        ("谢谢你听我说这些，我感觉好多了。", "情感收尾"),
    ],
}

print("=" * 80)
print("混合调度沙盒测试 — 随机场景多轮对话")
print("=" * 80)
DEBUG_MODE = debug_enabled()
if DEBUG_MODE:
    print("当前为调试模式，会显示内部状态")

# 随机挑选一个剧本
scenario_name = random.choice(list(SCENARIOS.keys()))
conversation = SCENARIOS[scenario_name]

print(f"\n🎲 随机选中剧本: {scenario_name}")
print(f"📋 共 {len(conversation)} 轮对话")
print("=" * 80)

registry = get_registry()
ctx = Context(session_id=f"sandbox-{int(time.time())}")
graph = build_graph()
runtime = EngineRuntime(lambda: graph)

prev_primary = ""
switches = []

for i, (user_input, desc) in enumerate(conversation, 1):
    print(f"\n{'═' * 80}")
    print(f"第 {i} 轮 | {desc}")
    print(f"{'─' * 80}")
    print(f"👤 用户: {user_input}")

    # 场景识别
    primary, secondaries, scores = registry.match_scenes(user_input)
    switched = prev_primary and primary != prev_primary
    if primary:
        if prev_primary and primary != prev_primary:
            switches.append(f"第{i}轮: {prev_primary} → {primary}")
        prev_primary = primary

    print(f"\n📡 场景路由:")
    print(f"   Primary:   {primary or 'None'}")
    print(f"   Secondary: {secondaries}")
    print(f"   Scores:    { {k: round(v, 4) for k, v in scores.items()} }")
    if switched:
        print(f"   ⚡ 换挡: {prev_primary if not switched else primary}")

    # 图执行
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
                print(f"   副场景策略: {ctx.secondary_scene_strategy[:100]}...")

    except Exception as e:
        print(f"\n❌ 错误: {e}")

# ============================================================
# 汇总
# ============================================================

print(f"\n{'═' * 80}")
print("沙盒测试汇总")
print(f"{'═' * 80}")
print(f"  剧本: {scenario_name}")
print(f"  总轮数: {len(conversation)}")
print(f"  场景切换次数: {len(switches)}")
if switches:
    print(f"  切换记录:")
    for s in switches:
        print(f"    {s}")
print(f"\n  ✅ 验证要点:")
print(f"    1. 情绪爆发时 emotion 是否抢占 Primary")
print(f"    2. 回归商业时 sales/negotiation 是否恢复")
print(f"    3. 副场景策略是否正确注入")
print(f"    4. 黑名单是否正确融合")
print(f"{'═' * 80}")
