"""Test weapon type filtering for aggressive opponent"""
import sys
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

from modules.L3.weapon_arsenal import ALL_WEAPONS, WeaponType

# Test defensive weapons for aggressive opponent
defensive_weapons = [
    w.name for w in ALL_WEAPONS.values()
    if w.type == WeaponType.DEFENSE
]
print(f"Defensive weapons ({len(defensive_weapons)}):")
for w in defensive_weapons[:10]:
    print(f"  - {w}")

# Test gentle weapons for hesitant/picky
gentle_weapons = [
    w.name for w in ALL_WEAPONS.values()
    if w.type == WeaponType.MILD
]
print(f"\nGentle weapons ({len(gentle_weapons)}):")
for w in gentle_weapons[:10]:
    print(f"  - {w}")

# Simulate filtering logic
combo_weapons = ["给予价值", "制造紧迫感", "描绘共同未来"]
target_type = WeaponType.DEFENSE

filtered = [
    w for w in combo_weapons
    if ALL_WEAPONS.get(w) and ALL_WEAPONS[w].type == target_type
]
print(f"\nOriginal combo: {combo_weapons}")
print(f"Filtered (defensive only): {filtered}")

if not filtered:
    import random
    type_weapons = [w.name for w in ALL_WEAPONS.values() if w.type == target_type]
    filtered = random.sample(type_weapons, min(3, len(type_weapons)))
    print(f"Fallback (random defensive): {filtered}")
