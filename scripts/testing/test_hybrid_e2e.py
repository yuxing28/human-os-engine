"""
混合调度 3.3C — 端到端验证

对比完整图执行（Step 0-9）中，有/无副场景策略时，
context.secondary_scene_strategy 字段是否正确构建并传递。

不需要 LLM API Key，只验证数据流。
"""
import sys
import os
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from schemas.context import Context
from modules.L5.skill_registry import get_registry
from modules.L5.scene_loader import load_scene_config
from prompts.speech_generator import build_speech_prompt


def debug_enabled() -> bool:
    return os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip().lower() in {"1", "true", "yes", "on"}

print("=" * 80)
print("混合调度 3.3C — 端到端数据流验证")
print("=" * 80)
DEBUG_MODE = debug_enabled()
if DEBUG_MODE:
    print("当前为调试模式，会显示内部识别细节")

# 模拟混合场景输入
user_input = "老板，我最近家里压力很大，孩子生病要照顾，但这季度业绩我也做到了第一，能不能涨薪？"

print(f"\n用户输入: {user_input}")

# Step 2: 多标签识别
registry = get_registry()
primary_id, secondary_ids, scores = registry.match_scenes(user_input)

print(f"\n【识别结果】")
print(f"  Primary: {primary_id}")
print(f"  Secondary: {secondary_ids}")
if DEBUG_MODE:
    print(f"  所有场景分数: {scores}")

# 加载配置
primary_config = load_scene_config(primary_id)
secondary_configs = {}
for sec_id in secondary_ids:
    try:
        secondary_configs[sec_id] = load_scene_config(sec_id)
        if DEBUG_MODE:
            print(f"  副场景 {sec_id} 配置加载成功: goal_taxonomy={len(secondary_configs[sec_id].goal_taxonomy) if secondary_configs[sec_id].goal_taxonomy else 0} 个目标")
    except Exception as e:
        print(f"  副场景 {sec_id} 配置加载失败: {e}")

# 融合黑名单
merged_blacklist = {}
if primary_config.weapon_blacklist:
    for k, v in primary_config.weapon_blacklist.items():
        merged_blacklist.setdefault(k, []).extend(v)
for sec_cfg in secondary_configs.values():
    if sec_cfg.weapon_blacklist:
        for k, v in sec_cfg.weapon_blacklist.items():
            if k not in merged_blacklist:
                merged_blacklist[k] = []
            merged_blacklist[k].extend(v)
            merged_blacklist[k] = list(set(merged_blacklist[k]))

print(f"\n  融合黑名单: {len(merged_blacklist)} 个类别")
if DEBUG_MODE:
    for k, v in merged_blacklist.items():
        print(f"    {k}: {v}")

# 构建副场景策略指令
secondary_strategy_parts = []
for sec_id, sec_cfg in secondary_configs.items():
    sec_score = scores.get(sec_id, 0)
    sec_strategies = []
    if sec_cfg.goal_taxonomy:
        for g in sec_cfg.goal_taxonomy[:2]:
            for p in getattr(g, 'strategy_preferences', [])[:1]:
                sec_strategies.append(p.get('combo', ''))
    if sec_strategies:
        secondary_strategy_parts.append(
            f"检测到用户存在【{sec_id}】诉求（匹配度 {sec_score:.0%}），"
            f"请在推进{primary_id}目标时，适当使用以下策略进行缓冲："
            f"{', '.join(sec_strategies)}。"
        )
    else:
        secondary_strategy_parts.append(
            f"检测到用户存在【{sec_id}】诉求（匹配度 {sec_score:.0%}），"
            f"请在推进{primary_id}目标时，注意语气和表达方式的适配。"
        )

secondary_scene_strategy = '\n'.join(secondary_strategy_parts) if secondary_strategy_parts else ''

print(f"\n【副场景策略】")
print(f"  已构建: {'是' if secondary_scene_strategy else '否'}")
if DEBUG_MODE and secondary_scene_strategy:
    print(f"  {secondary_scene_strategy}")

# 验证 Prompt 注入
print(f"\n【Prompt 注入验证】")
test_layers = [{"layer": 1, "weapon": "共情"}, {"layer": 5, "weapon": "给予价值"}]
test_user_state = {
    "emotion_type": "挫败", "emotion_intensity": 0.7,
    "motive": "回避恐惧", "dominant_desire": "fear",
    "dominant_weight": 0.8, "dual_core_state": "对抗",
}
test_strategy = {"mode": "B", "stage": "钩子", "description": "消除恐惧+激活贪婪"}
test_weapons = [{"name": "共情", "type": "温和型"}]

skill_prompt = registry.get_skill_prompt(primary_id)

_, user_prompt_before = build_speech_prompt(
    layers=test_layers, user_state=test_user_state,
    strategy_plan=test_strategy, weapons_used=test_weapons,
    skill_prompt=skill_prompt, secondary_scene_strategy="",
)

_, user_prompt_after = build_speech_prompt(
    layers=test_layers, user_state=test_user_state,
    strategy_plan=test_strategy, weapons_used=test_weapons,
    skill_prompt=skill_prompt, secondary_scene_strategy=secondary_scene_strategy,
)

print(f"  BEFORE Prompt 长度: {len(user_prompt_before)} 字符")
print(f"  AFTER Prompt 长度: {len(user_prompt_after)} 字符")
print(f"  增量: +{len(user_prompt_after) - len(user_prompt_before)} 字符")
print(f"  包含副场景策略: {'【副场景策略】' in user_prompt_after}")

# 关键断言
print(f"\n【断言检查】")
assert len(scores) >= 2, f"❌ 应识别到至少2个场景，实际: {len(scores)}"
print(f"  ✅ 识别到 {len(scores)} 个场景")
assert primary_id == "sales", f"❌ 主场景应为 sales，实际: {primary_id}"
print(f"  ✅ 主场景正确: {primary_id}")
assert len(secondary_ids) >= 1, f"❌ 应识别到至少1个副场景"
print(f"  ✅ 副场景正确: {secondary_ids}")
assert len(merged_blacklist) > 0, "❌ 黑名单融合失败"
print(f"  ✅ 黑名单融合成功: {len(merged_blacklist)} 个类别")
assert secondary_scene_strategy != "", "❌ 副场景策略指令为空"
print(f"  ✅ 副场景策略指令已构建")
assert "【副场景策略】" in user_prompt_after, "❌ Prompt 中未注入副场景策略"
print(f"  ✅ Prompt 注入成功")
assert "共情" in secondary_scene_strategy or "emotion" in secondary_scene_strategy, "❌ 副场景策略中缺少情感相关内容"
print(f"  ✅ 副场景策略包含情感相关内容")

print(f"\n{'=' * 80}")
print(f"全部断言通过 ✅ 混合调度 3.3C 数据流验证成功")
print(f"{'=' * 80}")
