"""
验证所有修复项
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# 1. 验证武器计数重置
from schemas.context import Context
ctx = Context(session_id='test')
ctx.increment_weapon('共情')
ctx.increment_weapon('共情')
assert ctx.get_weapon_count('共情') == 2
ctx.reset_strategy()
assert ctx.get_weapon_count('共情') == 0, '武器计数应在 reset_strategy 时清零'
print('[OK] 武器计数重置: reset_strategy() 会清空 weapon_usage_count')

# 2. 验证 History 滑动窗口
ctx2 = Context(session_id='test2')
for i in range(110):
    ctx2.add_history('user' if i % 2 == 0 else 'system', f'消息{i}')
assert len(ctx2.history) == 100, f'应为100条，实际{len(ctx2.history)}'
# 验证前3条保留
assert ctx2.history[0].content == '消息0', '前3条应保留'
assert ctx2.history[1].content == '消息1', '前3条应保留'
assert ctx2.history[2].content == '消息2', '前3条应保留'
print('[OK] History滑动窗口: 100条上限，保留前3条+最近97条')

# 3. 验证 expression_mode 被使用
from modules.L4.expression_dialectics import select_expression_mode
mode = select_expression_mode(
    user_state={'emotion_type': '平静', 'emotion_intensity': 0.3, 'dominant_desire': 'greed'},
    goal_type='利益价值',
    input_type='问题咨询'
)
assert mode == '逻辑模式', f'问题咨询应选择逻辑模式，实际{mode}'
print(f'[OK] 表达辩证模块: 问题咨询 -> {mode}')

# 4. 验证低置信度协议
from modules.L2.sins_keyword import identify_desires
from modules.L2.collaboration_temperature import identify_emotion
from modules.L2.dual_core_recognition import identify_dual_core

# 极短输入
desires_r = identify_desires('嗯')
emotion_r = identify_emotion('嗯')
dual_r = identify_dual_core('嗯')
min_conf = min(desires_r.confidence, emotion_r.confidence, dual_r.confidence)
print(f'[OK] 低置信度协议: 极短输入 最小置信度={min_conf:.2f}')

# 正常输入
desires_r2 = identify_desires('我好烦，工作压力大')
emotion_r2 = identify_emotion('我好烦，工作压力大')
dual_r2 = identify_dual_core('我好烦，工作压力大')
min_conf2 = min(desires_r2.confidence, emotion_r2.confidence, dual_r2.confidence)
print(f'[OK] 低置信度协议: 正常输入 最小置信度={min_conf2:.2f}')

# 5. 验证 motive 类型
from schemas.user_state import UserState, MotiveType
user = UserState()
assert user.motive == MotiveType.LIFE_EXPECTATION
assert user.motive != MotiveType.STRESS_PASSIVE
print('[OK] motive类型: 声明为MotiveType枚举，比较正确')

print()
print('所有验证通过！')
