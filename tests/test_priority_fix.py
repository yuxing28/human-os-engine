"""Test priority rule fix for aggressive opponent"""
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from schemas.user_state import UserState, Emotion, Desires, Attention, Resistance
from schemas.enums import EmotionType
from schemas.context import Goal
from modules.L1.priority_rules import get_priority

# Test aggressive opponent
user = UserState(
    emotion=Emotion(type=EmotionType.ANGRY, intensity=0.7),
    desires=Desires(pride=0.9, wrath=0.8, fear=0.3),
    attention=Attention(focus=0.4),
    resistance=Resistance(),
)
goal = Goal()
result = get_priority(user, goal)
print("Priority:", result["priority_type"])
print("Forced weapon type:", result.get("forced_weapon_type"))
print("Details:", result["details"])

# Test hesitant decision maker
user2 = UserState(
    emotion=Emotion(type=EmotionType.CALM, intensity=0.5),
    desires=Desires(fear=0.9, sloth=0.8, pride=0.2),
    attention=Attention(focus=0.5),
    resistance=Resistance(),
)
result2 = get_priority(user2, goal)
print("\nHesitant decision maker:")
print("Priority:", result2["priority_type"])
print("Forced weapon type:", result2.get("forced_weapon_type"))
print("Details:", result2["details"])

# Test picky customer
user3 = UserState(
    emotion=Emotion(type=EmotionType.CALM, intensity=0.6),
    desires=Desires(fear=0.8, greed=0.7, sloth=0.5, pride=0.3),
    attention=Attention(focus=0.6),
    resistance=Resistance(),
)
result3 = get_priority(user3, goal)
print("\nPicky customer:")
print("Priority:", result3["priority_type"])
print("Forced weapon type:", result3.get("forced_weapon_type"))
print("Details:", result3["details"])
