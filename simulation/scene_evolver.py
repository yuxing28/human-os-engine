"""
Human-OS Engine 3.0 — 场景进化器（兼容层）

simulation 目录下这份保留旧接口，方便老脚本继续调用：
- evolve_strategy(...)
- save()

真正的目录定位、数据加载和安全写入，统一复用 modules.L5.scene_evolver。
"""

from __future__ import annotations

from pathlib import Path

from modules.L5.scene_evolver import SceneEvolver as CoreSceneEvolver


class SceneEvolver:
    """给 simulation 下的旧脚本留一个稳定入口。"""

    PROJECT_ROOT = Path(__file__).resolve().parents[1]

    def __init__(self, scene_id: str = "sales", config_dir: str = "skills"):
        self._core = CoreSceneEvolver(scene_id, config_dir=config_dir)
        self.scene_id = scene_id

        # 旧脚本里很多地方把这些字段当字符串用，这里保留兼容。
        self.config_dir = str(self._core.config_dir)
        self.scene_dir = str(self._core.scene_dir)
        self.evolved_dir = str(self._core.evolved_dir)
        self.current_path = str(self._core.current_path)
        self.base_path = str(self._core.scene_dir / "base.json")

        # evolved_data 是共享字典，外层改动会直接反映到底层对象。
        self.evolved_data = self._core.evolved_data

    @classmethod
    def _resolve_config_dir(cls, config_dir: str) -> Path:
        return CoreSceneEvolver._resolve_config_dir(config_dir)

    def evolve_strategy(
        self,
        goal_key: str,
        combo_name: str,
        avg_trust_delta: float,
        avg_action_locked: float = 0.0,
        scenario_id: str = "sales",
    ):
        """
        旧版模拟器的轻量进化规则。

        这里保留原先的 reward 算法，避免影响历史脚本表现；
        但真正的存储、路径和保存动作都复用主实现。
        """
        key = f"{scenario_id}::{goal_key}::{combo_name}"
        current_weight = self.evolved_data["strategy_weights"].get(key, 0.5)

        reward = avg_trust_delta + (0.1 if avg_action_locked > 0.5 else 0.0)

        if reward > 0.05:
            delta = 0.05
        elif reward < -0.05:
            delta = -0.05
        else:
            delta = 0.0

        new_weight = max(0.1, min(1.0, current_weight + delta))
        self.evolved_data["strategy_weights"][key] = new_weight

        self.evolved_data["iterations"] += 1
        self.evolved_data["performance_metrics"]["total_interactions"] += 1
        if reward > 0:
            self.evolved_data["performance_metrics"]["success_count"] += 1

        total = self.evolved_data["performance_metrics"]["total_interactions"]
        success = self.evolved_data["performance_metrics"]["success_count"]
        self.evolved_data["performance_metrics"]["success_rate"] = success / total if total > 0 else 0.0

        self.save()

    def save(self):
        """沿用旧方法名，底层统一走安全写入。"""
        self._core.evolved_data = self.evolved_data
        self._core.save_evolved_version()

    def __getattr__(self, name):
        """其余能力直接透传给主实现，避免再长出第二套方法。"""
        return getattr(self._core, name)
