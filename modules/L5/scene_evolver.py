"""
Human-OS Engine 3.0 — 场景进化器

负责根据对话反馈，动态调整场景配置中的策略权重和武器黑名单。
进化数据存储在 skills/{scene_id}/evolved/ 目录下，与基础配置分离。
"""

import os
import json
import copy
import time
from pathlib import Path
from typing import Optional

from schemas.scene import SceneConfig, EvolvedConfig
from modules.L5.scene_loader import SceneLoader
from utils.file_lock import safe_json_read, safe_json_write


class SceneEvolver:
    """
    场景进化器
    
    用法:
        evolver = SceneEvolver("sales")
        evolver.record_outcome("overcome_rejection", "共情 + 正常化", success=True)
        evolver.save_evolved_version()
    """
    
    def __init__(self, scene_id: str, config_dir: str = "skills"):
        self.scene_id = scene_id
        self.config_dir = SceneLoader._resolve_config_dir(config_dir)
        self.scene_dir = self.config_dir / scene_id
        self.evolved_dir = self.scene_dir / "evolved"
        self.current_path = self.evolved_dir / "current.json"
        
        # 确保目录存在
        self.evolved_dir.mkdir(parents=True, exist_ok=True)
        
        # 先加载基础配置
        self.base_config = self._load_base_config()
        
        # 再加载当前进化数据（如果存在）
        self.evolved_data = self._load_evolved_data()
    
    def _load_base_config(self) -> dict:
        """加载基础配置"""
        base_path = self.scene_dir / "base.json"
        if base_path.exists():
            with open(base_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def _load_evolved_data(self) -> dict:
        """加载当前进化数据"""
        if self.current_path.exists():
            try:
                with open(self.current_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        
        # 初始化进化数据
        return {
            "base_version": self.base_config.get("version", "unknown"),
            "evolved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "iterations": 0,
            "strategy_weights": {},
            "weapon_blacklist_additions": {},
            "performance_metrics": {
                "total_interactions": 0,
                "success_count": 0,
                "success_rate": 0.0
            }
        }
    
    def record_outcome(self, granular_goal: str, strategy_combo: str, success: bool, context: Optional[dict] = None):
        """
        记录对话结果，调整策略权重（Phase 2: 多维度上下文感知动态衰减）
        
        Args:
            granular_goal: 细粒度目标标识
            strategy_combo: 使用的策略组合名称
            success: 是否成功
            context: 上下文信息，支持以下字段:
                - emotion: 情绪类型 (愤怒/急躁/挫败/恐惧/平静/迷茫)
                - emotion_intensity: 情绪强度 (0.0-1.0)
                - trust_level: 信任等级 (low/medium/high)
                - trust_change: 信任变化幅度 (-1.0 to 1.0)
                - resistance_type: 阻力类型 (恐惧/懒惰/傲慢/嫉妒/愤怒/贪婪/null)
                - resistance_intensity: 阻力强度 (0.0-1.0)
                - energy_mode: 能量模式 (A/B/C)
                - dual_core_state: 双核状态 (对抗/协同/同频/合理化)
                - desires: 八宗罪权重字典
        """
        self.evolved_data["iterations"] += 1
        self.evolved_data["performance_metrics"]["total_interactions"] += 1
        
        if success:
            self.evolved_data["performance_metrics"]["success_count"] += 1
        
        # 更新成功率
        total = self.evolved_data["performance_metrics"]["total_interactions"]
        success_count = self.evolved_data["performance_metrics"]["success_count"]
        self.evolved_data["performance_metrics"]["success_rate"] = success_count / total if total > 0 else 0.0
        
        # 调整策略权重（Key 格式：scene_id::granular_goal::combo_name）
        key = f"{self.scene_id}::{granular_goal}::{strategy_combo}"
        current_weight = self.evolved_data["strategy_weights"].get(key, 1.0)
        
        # 【Phase 2】多维度上下文感知动态步长
        emotion = context.get("emotion", "平静") if context else "平静"
        emotion_intensity = context.get("emotion_intensity", 0.5) if context else 0.5
        trust = context.get("trust_level", "medium") if context else "medium"
        trust_change = context.get("trust_change", 0.0) if context else 0.0
        resistance_type = context.get("resistance_type", "null") if context else "null"
        resistance_intensity = context.get("resistance_intensity", 0.0) if context else 0.0
        energy_mode = context.get("energy_mode", "A") if context else "A"
        dual_core_state = context.get("dual_core_state", "同频") if context else "同频"
        desires = context.get("desires", {}) if context else {}
        
        # 基础步长
        base_success_step = 0.05
        base_failure_step = 0.03
        
        # ===== 成功时的上下文感知调整 =====
        if success:
            step = base_success_step
            
            # 1. 信任系数：信任越低，成功权重增加越难（信任难建）
            trust_multiplier = {
                "low": 0.4,      # 信任低时，成功收益大幅降低
                "medium": 0.8,   # 信任中等时，正常收益
                "high": 1.2,     # 信任高时，成功收益放大（马太效应）
            }.get(trust, 0.8)
            step *= trust_multiplier
            
            # 2. 情绪系数：高情绪强度时，成功权重增加受抑制
            if emotion_intensity > 0.7:
                step *= 0.7  # 高情绪时成功可能是运气，权重增加保守
            
            # 3. 策略类型系数：根据策略组合名称判断类型
            strategy_type = self._classify_strategy_type(strategy_combo)
            if strategy_type == "empathy":
                # 共情类策略在愤怒/急躁时成功，权重增加更大
                if emotion in ["愤怒", "急躁"]:
                    step *= 1.3
            elif strategy_type == "hook":
                # 钩子类在贪婪/恐惧欲望高时成功，权重增加更大
                if desires.get("greed", 0) > 0.5 or desires.get("fear", 0) > 0.5:
                    step *= 1.2
            elif strategy_type == "upgrade":
                # 升维类在平静/协同时成功，权重增加更大
                if emotion == "平静" or dual_core_state == "协同":
                    step *= 1.3
            
            # 4. 信任趋势系数：信任在上升时，成功权重增加放大
            if trust_change > 0.03:
                step *= 1.2  # 信任上升趋势，成功更可信
            elif trust_change < -0.03:
                step *= 0.8  # 信任下降趋势，成功可能是偶然
            
            # 5. 阻力系数：阻力高时成功，权重增加更大（克服困难的成功更有价值）
            if resistance_intensity > 0.6:
                step *= 1.2
            
            new_weight = min(current_weight + step, 2.0)
        
        # ===== 失败时的上下文感知调整 =====
        else:
            step = base_failure_step
            
            # 1. 情绪 × 信任组合矩阵：核心衰减逻辑
            emotion_trust_matrix = {
                # (emotion, trust) -> failure_step_multiplier
                ("愤怒", "low"): 3.0,     # 愤怒+低信任：最严重，快速衰减
                ("愤怒", "medium"): 2.5,   # 愤怒+中信任：严重
                ("愤怒", "high"): 1.8,     # 愤怒+高信任：较严重
                ("急躁", "low"): 2.8,      # 急躁+低信任：严重
                ("急躁", "medium"): 2.2,   # 急躁+中信任：较严重
                ("急躁", "high"): 1.5,     # 急躁+高信任：一般
                ("挫败", "low"): 2.5,      # 挫败+低信任：严重
                ("挫败", "medium"): 2.0,   # 挫败+中信任：较严重
                ("挫败", "high"): 1.3,     # 挫败+高信任：一般
                ("恐惧", "low"): 2.2,      # 恐惧+低信任：较严重
                ("恐惧", "medium"): 1.8,   # 恐惧+中信任：一般
                ("恐惧", "high"): 1.2,     # 恐惧+高信任：轻微
                ("迷茫", "low"): 1.8,      # 迷茫+低信任：一般
                ("迷茫", "medium"): 1.5,   # 迷茫+中信任：一般
                ("迷茫", "high"): 1.0,     # 迷茫+高信任：正常
                ("平静", "low"): 1.5,      # 平静+低信任：一般
                ("平静", "medium"): 1.0,   # 平静+中信任：正常
                ("平静", "high"): 0.8,     # 平静+高信任：轻微
            }
            combo_key = (emotion, trust)
            step *= emotion_trust_matrix.get(combo_key, 1.0)
            
            # 2. 情绪强度系数：情绪越强烈，失败惩罚越大
            if emotion_intensity > 0.8:
                step *= 1.4  # 极高情绪强度
            elif emotion_intensity > 0.6:
                step *= 1.2  # 高情绪强度
            
            # 3. 策略类型系数：不同类型策略在不同情绪下失败惩罚不同
            strategy_type = self._classify_strategy_type(strategy_combo)
            if strategy_type == "empathy":
                # 共情类在愤怒时失败，惩罚加倍（共情失效是严重信号）
                if emotion in ["愤怒", "急躁"]:
                    step *= 1.5
            elif strategy_type == "hook":
                # 钩子类在低信任时失败，惩罚加大
                if trust == "low":
                    step *= 1.4
            elif strategy_type == "upgrade":
                # 升维类在傲慢/对抗时失败，惩罚加大
                if desires.get("pride", 0) > 0.5 or dual_core_state == "对抗":
                    step *= 1.3
            
            # 4. 信任趋势系数：信任骤降时失败，惩罚加大
            if trust_change < -0.05:
                step *= 1.5  # 信任骤降
            elif trust_change < -0.02:
                step *= 1.2  # 信任下降
            
            # 5. 阻力系数：阻力高时失败，惩罚加大
            if resistance_intensity > 0.6:
                step *= 1.3
            
            # 6. 能量模式系数：Mode A（向内）时失败，惩罚稍小（探索性）
            #    Mode B（向外）时失败，惩罚正常
            #    Mode C（共创）时失败，惩罚加大（共创失败说明不匹配）
            mode_multiplier = {
                "A": 0.8,  # 向内探索，允许失败
                "B": 1.0,  # 正常
                "C": 1.3,  # 共创失败，说明不匹配
            }.get(energy_mode, 1.0)
            step *= mode_multiplier
            
            new_weight = max(current_weight - step, 0.1)
        
        self.evolved_data["strategy_weights"][key] = new_weight
    
    def _classify_strategy_type(self, strategy_combo: str) -> str:
        """
        根据策略组合名称分类策略类型
        
        Returns:
            "empathy" - 共情/情感重塑类
            "hook" - 钩子/吸引类
            "upgrade" - 升维/超越类
            "defense" - 防御/设界类
            "normal" - 普通/其他
        """
        empathy_keywords = ["共情", "重塑", "正常化", "情感", "理解", "接纳"]
        hook_keywords = ["好奇", "稀缺", "贪婪", "恐惧", "互惠", "权威", "从众", "钩子"]
        upgrade_keywords = ["升维", "愿景", "尊严", "大爱", "宁静", "卓越", "革命", "共创"]
        defense_keywords = ["沉默", "示弱", "设界", "纠正", "转移", "防御", "反问", "贴标签"]
        
        for kw in empathy_keywords:
            if kw in strategy_combo:
                return "empathy"
        for kw in hook_keywords:
            if kw in strategy_combo:
                return "hook"
        for kw in upgrade_keywords:
            if kw in strategy_combo:
                return "upgrade"
        for kw in defense_keywords:
            if kw in strategy_combo:
                return "defense"
        
        return "normal"
    
    def add_to_blacklist(self, weapon: str, context_key: str):
        """
        将武器加入黑名单（基于失败模式）
        
        Args:
            weapon: 武器名称
            context_key: 失败上下文 (如 "emotion_angry")
        """
        if context_key not in self.evolved_data["weapon_blacklist_additions"]:
            self.evolved_data["weapon_blacklist_additions"][context_key] = []
        
        if weapon not in self.evolved_data["weapon_blacklist_additions"][context_key]:
            self.evolved_data["weapon_blacklist_additions"][context_key].append(weapon)
    
    def save_evolved_version(self):
        """保存进化数据到 current.json（安全写入）"""
        self.evolved_data["evolved_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        
        # 先备份当前版本，再覆盖写入，避免“先 rename 后写入失败”导致 current.json 消失
        existing = safe_json_read(str(self.current_path), None)
        if existing is not None:
            backup_path = self.evolved_dir / f"backup_{int(time.time() * 1000)}.json"
            safe_json_write(str(backup_path), existing)
        
        # 安全写入
        safe_json_write(str(self.current_path), self.evolved_data)
    
    def get_merged_config(self) -> dict:
        """
        获取合并后的配置（基础 + 进化）
        
        Returns:
            合并后的配置字典
        """
        return self.evolved_data
