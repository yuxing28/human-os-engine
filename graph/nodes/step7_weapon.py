"""
Human-OS Engine - LangGraph 节点实现

对应总控规格的 Step 0-9。
"""

from graph.state import GraphState


def step7_weapon_selection(state: GraphState) -> GraphState:
    """Step 7：武器调用——从策略组合获取推荐武器，根据优先级强制过滤类型"""
    context = state["context"]
    if state.get("skip_to_end", False):
        return {**state, "context": context, "weapons_used": []}
    strategy_plan = state.get("strategy_plan")
    priority = state.get("priority", {})

    from modules.L3.strategy_combinations import get_combo_weapons, ALL_COMBOS
    from modules.L3.weapon_arsenal import get_weapon, ALL_WEAPONS, WeaponType

    weapons_used = []

    if strategy_plan:
        # 【BUG-1 修复】优先使用动态引擎生成的武器
        if strategy_plan.weapons:
            combo_weapons = list(strategy_plan.weapons)
        else:
            # 从静态策略组合获取推荐武器
            combo_weapons = get_combo_weapons(strategy_plan.combo_name)

            # Fallback：若组合不存在或为空，使用默认安全武器
            if not combo_weapons:
                combo_weapons = ["共情", "正常化", "好奇"]

        # 强制武器类型过滤（基于优先级）
        forced_type = priority.get("forced_weapon_type")

        # 【修复1】全程强制防御型武器：傲慢/愤怒场景无视 priority，强制 defensive
        user_emotion = context.user.emotion.type.value if hasattr(context.user.emotion.type, 'value') else str(context.user.emotion.type)
        if user_emotion in ["愤怒", "急躁"] or context.user.desires.pride > 0.5:
            forced_type = "defensive"

        if forced_type:
            type_map = {
                "defensive": WeaponType.DEFENSE,
                "gentle": WeaponType.MILD,
                "aggressive": WeaponType.ATTACK,
            }
            target_type = type_map.get(forced_type)
            if target_type:
                # 强制过滤：防御模式只选 DEFENSE 型（不混入温和型，避免触发对手负规则）
                if target_type == WeaponType.DEFENSE:
                    filtered = [
                        w for w in combo_weapons
                        if get_weapon(w) and get_weapon(w).type == WeaponType.DEFENSE
                    ]
                else:
                    filtered = [
                        w for w in combo_weapons
                        if get_weapon(w) and get_weapon(w).type == target_type
                    ]
                if filtered:
                    combo_weapons = filtered
                    # 【Phase 4】防御模式下优先纠正武器（14-武器库: "傲慢 → 优先攻击型（反问）或防御型（沉默），打破心理优势"）
                    if forced_type == "defensive":
                        # 优先选择纠正型武器
                        corrective_weapons = ["反问", "原则", "战略性无能"]
                        available_corrective = [w for w in corrective_weapons if w in combo_weapons]
                        if available_corrective:
                            # 将纠正武器移到最前面
                            others = [w for w in combo_weapons if w not in available_corrective]
                            combo_weapons = available_corrective + others

                    # 【修复1增强】确保至少3个防御武器
                    if len(combo_weapons) < 3 and forced_type == "defensive":
                        all_defensive = [w.name for w in ALL_WEAPONS.values() if w.type == WeaponType.DEFENSE]
                        priority_defensive = ["反问", "原则", "战略性无能", "沉默", "示弱", "装傻", "附和"]
                        for w in priority_defensive:
                            if w not in combo_weapons and w in all_defensive:
                                combo_weapons.append(w)
                                if len(combo_weapons) == 3:
                                    break
                elif forced_type == "defensive":
                    # 【Phase 2】根据用户状态动态选择防御武器，打破固定循环
                    import random
                    if user_emotion in ["愤怒", "急躁"]:
                        # 愤怒/急躁 → 纠正+设界，打破攻击节奏
                        priority_pool = ["反问", "原则", "战略性无能", "设定框架", "赋予身份"]
                        secondary_pool = ["沉默", "示弱", "物理隔离", "断开连接", "保持距离"]
                    elif context.user.desires.pride > 0.5:
                        # 傲慢 → 用反问+赞美打破心理优势
                        priority_pool = ["反问", "原则", "稀缺性赞美", "赋予身份", "设定框架"]
                        secondary_pool = ["沉默", "示弱", "附和", "保持距离"]
                    else:
                        # 其他防御场景
                        priority_pool = ["反问", "原则", "战略性无能", "沉默", "附和"]
                        secondary_pool = ["示弱", "装傻", "转移话题", "设定框架"]
                    # 从池中随机选 3 个可用武器
                    all_pool = priority_pool + [w for w in secondary_pool if w not in priority_pool]
                    available = [w for w in all_pool if get_weapon(w)]
                    combo_weapons = random.sample(available, min(3, len(available))) if available else ["沉默", "示弱", "装傻"]
                else:
                    # 其他类型：从该类型中随机选 3 个
                    import random
                    type_weapons = [
                        w.name for w in ALL_WEAPONS.values()
                        if w.type == target_type
                    ]
                    combo_weapons = random.sample(type_weapons, min(3, len(type_weapons)))

        for weapon_name in combo_weapons:
            weapon = get_weapon(weapon_name)
            if weapon:
                weapons_used.append({
                    "name": weapon.name,
                    "type": weapon.type.value,
                    "example": weapon.example,
                })
            # 注意：不在这里 increment_weapon，统一在 Step 8 计数

    # 存储到 state（Step 8 直接使用，不再重新选择）
    
    # 【规格 P0】表达多样性检查：同一武器不超 2 次
    if weapons_used:
        for w in weapons_used[:]:  # 使用副本迭代
            w_name = w["name"]
            if context.weapon_usage_count.get(w_name, 0) >= 2:
                # 武器已达上限，替换为同类其他武器
                w_type = w.get("type", "")
                all_same_type = [wn.name for wn in ALL_WEAPONS.values() if wn.type.value == w_type and wn.name != w_name]
                # 找一个使用次数最少的同类武器
                replacement = min(all_same_type, key=lambda x: context.weapon_usage_count.get(x, 0), default=None)
                if replacement:
                    w["name"] = replacement
                    w["replaced_from"] = w_name  # 记录替换来源

    # 【融合规则 A & B】应用武器黑名单（取并集）+ 武器池扩充
    if weapons_used:
        # 合并黑名单
        blacklist = []
        emotion_key = f"emotion_{context.user.emotion.type.value if hasattr(context.user.emotion.type, 'value') else str(context.user.emotion.type)}"
        
        # Primary blacklist
        if context.scene_config:
            blacklist.extend(context.scene_config.weapon_blacklist.get(emotion_key, []))
            granular_goal = getattr(context.goal, 'granular_goal', None)
            if granular_goal:
                blacklist.extend(context.scene_config.weapon_blacklist.get(f"goal_{granular_goal}", []))
        
        # Secondary blacklists (Union)
        for sec_cfg in context.secondary_configs.values():
            if sec_cfg.weapon_blacklist:
                blacklist.extend(sec_cfg.weapon_blacklist.get(emotion_key, []))
                granular_goal = getattr(context.goal, 'granular_goal', None)
                if granular_goal:
                    blacklist.extend(sec_cfg.weapon_blacklist.get(f"goal_{granular_goal}", []))

        if blacklist:
            weapons_used = [w for w in weapons_used if w["name"] not in blacklist]
    
    # 【BUG-2 修复】将最终武器列表存入 context，供 Step 9 评估器使用
    context._last_weapons_used = [w["name"] for w in weapons_used]
    
    return {**state, "context": context, "weapons_used": weapons_used}
