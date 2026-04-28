"""
Human-OS Engine 3.0 — 场景配置加载器

负责加载、验证、合并场景配置（基础配置 + 进化数据）。
支持热加载：检测文件变化自动重新加载。
"""

import os
import json
import copy
from pathlib import Path
from typing import Optional

from schemas.scene import SceneConfig, EvolvedConfig


class SceneLoader:
    """
    场景配置加载器
    
    用法:
        loader = SceneLoader("sales")
        config = loader.get_config()
    """
    
    ALLOWED_SCENES = {"sales", "emotion", "negotiation", "management"}
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    
    def __init__(self, scene_id: str, config_dir: str = "skills"):
        if not scene_id or not scene_id.replace("_", "").replace("-", "").isalnum():
            raise ValueError(f"无效的场景ID: {scene_id}")
        if ".." in scene_id or "/" in scene_id or "\\" in scene_id:
            raise ValueError(f"场景ID包含非法字符: {scene_id}")
        if config_dir == "skills" and scene_id not in self.ALLOWED_SCENES:
            raise ValueError(f"未知场景ID: {scene_id}，允许的: {self.ALLOWED_SCENES}")
        
        self.scene_id = scene_id
        self.config_dir = self._resolve_config_dir(config_dir)
        self.scene_dir = self.config_dir / scene_id
        resolved_scene = (self.config_dir / scene_id).resolve()
        try:
            resolved_scene.relative_to(self.config_dir)
        except ValueError:
            raise ValueError(f"路径遍历检测: {scene_id}")
        self.base_path = self.scene_dir / "base.json"
        self.evolved_dir = self.scene_dir / "evolved"
        self.current_path = self.evolved_dir / "current.json"
        
        self._base_config: Optional[SceneConfig] = None
        self._evolved_config: Optional[EvolvedConfig] = None
        self._merged_config: Optional[SceneConfig] = None
        self._last_modified: float = 0
        self._last_evolved_modified: Optional[float] = None
        
        self._load()

    @classmethod
    def _resolve_config_dir(cls, config_dir: str) -> Path:
        """
        解析配置目录。

        默认的 skills 目录固定锚定到项目根目录，避免受当前工作目录影响。
        自定义路径仍按调用方传入内容解析。
        """
        path = Path(config_dir)
        if not path.is_absolute() and config_dir == "skills":
            path = cls.PROJECT_ROOT / path
        return path.resolve()
    
    def _load(self):
        """加载基础配置和进化数据"""
        # 加载基础配置
        if not self.base_path.exists():
            raise FileNotFoundError(f"基础配置不存在: {self.base_path}")
        
        with open(self.base_path, "r", encoding="utf-8") as f:
            base_data = json.load(f)
        self._base_config = SceneConfig(**base_data)
        self._last_modified = os.path.getmtime(self.base_path)
        
        # 加载进化数据（如果存在）
        if self.current_path.exists():
            with open(self.current_path, "r", encoding="utf-8") as f:
                evolved_data = json.load(f)
            self._evolved_config = EvolvedConfig(**evolved_data)
            self._last_evolved_modified = os.path.getmtime(self.current_path)
        else:
            self._evolved_config = None
            self._last_evolved_modified = None
        
        # 合并配置
        self._merged_config = self._merge_configs()
    
    def _merge_configs(self) -> SceneConfig:
        """合并基础配置和进化数据"""
        if not self._evolved_config:
            return copy.deepcopy(self._base_config)
        
        merged = copy.deepcopy(self._base_config)
        evolved = self._evolved_config
        
        # 合并策略权重（进化数据中的 Key 格式可能为：
        # 1. scene_id::granular_goal::combo_name
        # 2. granular_goal::combo_name
        # 3. combo_name (直接匹配默认权重)
        if evolved.strategy_weights:
            prefix = f"{self.scene_id}::"
            
            # 更新 goal_taxonomy 中的 strategy_preferences 权重
            for goal in merged.goal_taxonomy:
                for pref in goal.strategy_preferences:
                    # 尝试多种 Key 格式匹配
                    possible_keys = [
                        f"{prefix}{goal.granular_goal}::{pref['combo']}",
                        f"{goal.granular_goal}::{pref['combo']}",
                        f"{goal.granular_goal}::{pref['combo']}",  # 处理空 combo 情况
                        f"{goal.granular_goal}::",  # 进化器可能只存了 goal::
                    ]
                    for key in possible_keys:
                        if key in evolved.strategy_weights:
                            pref['weight'] = evolved.strategy_weights[key]
                            break
            
            # 更新默认策略权重
            for combo_name in merged.default_strategy_weights:
                direct_key = combo_name
                prefixed_key = f"{prefix}{combo_name}"
                if direct_key in evolved.strategy_weights:
                    merged.default_strategy_weights[combo_name] = evolved.strategy_weights[direct_key]
                elif prefixed_key in evolved.strategy_weights:
                    merged.default_strategy_weights[combo_name] = evolved.strategy_weights[prefixed_key] 

        # 合并武器黑名单（进化数据中的新增项）
        if evolved.weapon_blacklist_additions:
            for condition, weapons in evolved.weapon_blacklist_additions.items():
                if condition not in merged.weapon_blacklist:
                    merged.weapon_blacklist[condition] = []
                for w in weapons:
                    if w not in merged.weapon_blacklist[condition]:
                        merged.weapon_blacklist[condition].append(w)
        
        return merged
    
    def _is_modified(self) -> bool:
        """检查配置文件是否已修改"""
        if not self.base_path.exists():
            return False
        if os.path.getmtime(self.base_path) != self._last_modified:
            return True

        current_exists = self.current_path.exists()
        if current_exists != (self._last_evolved_modified is not None):
            return True
        if current_exists and self._last_evolved_modified is not None:
            return os.path.getmtime(self.current_path) != self._last_evolved_modified
        return False
    
    def get_config(self, force_reload: bool = False) -> SceneConfig:
        """
        获取场景配置（支持热加载）
        
        Args:
            force_reload: 是否强制重新加载
        
        Returns:
            合并后的场景配置
        """
        if force_reload or self._is_modified():
            self._load()
        return self._merged_config
    
    def get_goal(self, granular_goal: str) -> Optional[dict]:
        """
        获取特定细粒度目标的配置
        
        Args:
            granular_goal: 目标标识
        
        Returns:
            目标配置字典，如果不存在则返回 None
        """
        config = self.get_config()
        for goal in config.goal_taxonomy:
            if goal.granular_goal == granular_goal:
                return goal.model_dump()
        return None
    
    def get_forbidden_weapons(self, condition: str) -> list[str]:
        """
        获取特定条件下的武器黑名单
        
        Args:
            condition: 条件键，如 'emotion_angry'
        
        Returns:
            武器黑名单列表
        """
        config = self.get_config()
        return config.weapon_blacklist.get(condition, [])
    
    def get_strategy_preferences(self, granular_goal: str) -> list[dict]:
        """
        获取特定目标的策略偏好
        
        Args:
            granular_goal: 目标标识
        
        Returns:
            策略偏好列表
        """
        goal = self.get_goal(granular_goal)
        if goal:
            return goal.get("strategy_preferences", [])
        return self.get_config().default_strategy_weights


def load_scene_config(scene_id: str, config_dir: str = "skills") -> SceneConfig:
    """
    便捷函数：加载场景配置
    
    Args:
        scene_id: 场景标识
        config_dir: 配置目录
    
    Returns:
        场景配置
    """
    loader = SceneLoader(scene_id, config_dir)
    return loader.get_config()
