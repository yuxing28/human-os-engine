"""
Human-OS Engine 3.0 — 场景配置加载器测试

验证场景配置的加载、验证、合并逻辑。
"""

import pytest
import sys
import os
import json
import time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from schemas.scene import SceneConfig, GranularGoal, EvolvedConfig
from modules.L5.scene_loader import SceneLoader, load_scene_config


class TestSceneSchema:
    """测试 Pydantic Schema 验证"""
    
    def test_valid_granular_goal(self):
        goal = GranularGoal(
            granular_goal="test_goal",
            display_name="测试目标",
            keywords=["关键词1", "关键词2"],
            emotion_hints=["焦虑"],
            default_mode="B",
            strategy_preferences=[{"combo": "测试组合", "weight": 0.8}],
            forbidden_weapons=["禁止武器"],
            success_criteria={"user_says": ["成功"]}
        )
        assert goal.granular_goal == "test_goal"
        assert len(goal.keywords) == 2
        assert len(goal.forbidden_weapons) == 1
    
    def test_valid_scene_config(self):
        config = SceneConfig(
            scene_id="test",
            version="1.0.0",
            goal_taxonomy=[],
            default_strategy_weights={"A": 0.5},
            weapon_blacklist={"emotion_angry": ["武器1"]},
            eval_weights={"goal_achievement": 0.4}
        )
        assert config.scene_id == "test"
        assert config.version == "1.0.0"
    
    def test_valid_evolved_config(self):
        evolved = EvolvedConfig(
            base_version="1.0.0",
            evolved_at="2026-04-03T10:00:00Z",
            iterations=100,
            strategy_weights={"A": 0.6},
            weapon_blacklist_additions={"emotion_angry": ["武器2"]},
            performance_metrics={"success_rate": 0.75}
        )
        assert evolved.iterations == 100
        assert evolved.strategy_weights["A"] == 0.6


class TestSceneLoader:
    """测试场景配置加载器"""
    
    def test_load_sales_base(self):
        """测试加载销售场景基础配置"""
        loader = SceneLoader("sales")
        config = loader.get_config()
        
        assert config.scene_id == "sales"
        assert config.version == "1.2.4"
        assert len(config.goal_taxonomy) == 9  # 新增 crisis_management
        
        # 验证目标分类
        goals = {g.granular_goal: g for g in config.goal_taxonomy}
        assert "overcome_rejection" in goals
        assert "break_status_quo" in goals
        assert "reduce_admin_burden" in goals
        assert "multi_threading" in goals
        assert "value_differentiation" in goals
        assert "prove_roi" in goals
        assert "close_deal" in goals
        assert "lead_quality" in goals
        
        # 验证武器黑名单
        assert "emotion_愤怒" in config.weapon_blacklist
        assert len(config.weapon_blacklist["emotion_愤怒"]) > 0
        
        # 验证评估权重
        assert "goal_achievement" in config.eval_weights
    
    def test_get_goal(self):
        """测试获取特定目标配置"""
        loader = SceneLoader("sales")
        goal = loader.get_goal("overcome_rejection")
        
        assert goal is not None
        assert goal["display_name"] == "克服拒绝"
        assert len(goal["keywords"]) > 0
        assert len(goal["forbidden_weapons"]) > 0
    
    def test_get_goal_not_found(self):
        """测试获取不存在的目标"""
        loader = SceneLoader("sales")
        goal = loader.get_goal("nonexistent_goal")
        assert goal is None
    
    def test_get_forbidden_weapons(self):
        """测试获取武器黑名单"""
        loader = SceneLoader("sales")
        blacklist = loader.get_forbidden_weapons("emotion_愤怒")
        
        assert isinstance(blacklist, list)
        assert len(blacklist) > 0
        assert "描绘共同未来" in blacklist
    
    def test_get_forbidden_weapons_empty(self):
        """测试获取不存在的条件黑名单"""
        loader = SceneLoader("sales")
        blacklist = loader.get_forbidden_weapons("nonexistent_condition")
        assert blacklist == []
    
    def test_get_strategy_preferences(self):
        """测试获取策略偏好"""
        loader = SceneLoader("sales")
        prefs = loader.get_strategy_preferences("overcome_rejection")
        
        assert isinstance(prefs, list)
        assert len(prefs) > 0
        assert prefs[0]["combo"] == "共情+正常化"

    def test_default_skills_dir_not_dependent_on_cwd(self, monkeypatch, tmp_path):
        """默认 skills 目录应锚定到项目根，而不是当前工作目录"""
        monkeypatch.chdir(tmp_path)
        loader = SceneLoader("sales")
        config = loader.get_config()

        assert config.scene_id == "sales"
        assert loader.base_path.exists()
        assert loader.base_path.parent.name == "sales"
        assert loader.base_path.parent.parent.name == "skills"


class TestConfigMerge:
    """测试配置合并逻辑"""
    
    def test_merge_with_evolved(self, tmp_path):
        """测试基础配置与进化数据合并"""
        # 创建临时目录结构
        scene_dir = tmp_path / "test_merge" / "evolved"
        scene_dir.mkdir(parents=True)
        
        # 写入基础配置
        base_data = {
            "scene_id": "test_merge",
            "version": "1.0.0",
            "goal_taxonomy": [],
            "default_strategy_weights": {"A": 0.5, "B": 0.5},
            "weapon_blacklist": {"emotion_angry": ["武器1"]},
            "eval_weights": {"goal_achievement": 0.5}
        }
        with open(tmp_path / "test_merge" / "base.json", "w") as f:
            json.dump(base_data, f)
        
        # 写入进化数据
        evolved_data = {
            "base_version": "1.0.0",
            "evolved_at": "2026-04-03T10:00:00Z",
            "iterations": 50,
            "strategy_weights": {"A": 0.7},
            "weapon_blacklist_additions": {"emotion_angry": ["武器2"]},
            "performance_metrics": {"success_rate": 0.8}
        }
        with open(scene_dir / "current.json", "w") as f:
            json.dump(evolved_data, f)
        
        # 加载并验证合并
        loader = SceneLoader("test_merge", config_dir=str(tmp_path))
        config = loader.get_config()
        
        # 策略权重应被进化数据覆盖
        assert config.default_strategy_weights["A"] == 0.7
        assert config.default_strategy_weights["B"] == 0.5
        
        # 武器黑名单应合并
        assert "武器1" in config.weapon_blacklist["emotion_angry"]
        assert "武器2" in config.weapon_blacklist["emotion_angry"]

    def test_reload_when_evolved_file_changes(self, tmp_path):
        scene_dir = tmp_path / "reload_scene" / "evolved"
        scene_dir.mkdir(parents=True)

        base_data = {
            "scene_id": "reload_scene",
            "version": "1.0.0",
            "goal_taxonomy": [],
            "default_strategy_weights": {"A": 0.5},
            "weapon_blacklist": {},
            "eval_weights": {},
        }
        with open(tmp_path / "reload_scene" / "base.json", "w", encoding="utf-8") as f:
            json.dump(base_data, f)

        evolved_path = scene_dir / "current.json"
        with open(evolved_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "base_version": "1.0.0",
                    "evolved_at": "2026-04-03T10:00:00Z",
                    "iterations": 1,
                    "strategy_weights": {"A": 0.7},
                    "weapon_blacklist_additions": {},
                    "performance_metrics": {"success_rate": 0.8},
                },
                f,
            )

        loader = SceneLoader("reload_scene", config_dir=str(tmp_path))
        assert loader.get_config().default_strategy_weights["A"] == 0.7

        time.sleep(0.02)
        with open(evolved_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "base_version": "1.0.0",
                    "evolved_at": "2026-04-03T10:05:00Z",
                    "iterations": 2,
                    "strategy_weights": {"A": 0.9},
                    "weapon_blacklist_additions": {},
                    "performance_metrics": {"success_rate": 0.9},
                },
                f,
            )

        assert loader.get_config().default_strategy_weights["A"] == 0.9


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
