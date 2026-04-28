"""
Human-OS Engine - 用户代理（规则版 MVP）

根据配置 JSON 生成回复，维护情绪/信任状态，支持强制阻力注入。
"""

import json
import random
from typing import Optional


class UserAgent:
    def __init__(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self.state = json.loads(json.dumps(self.config["initial_state"]))
        self.state.setdefault("interaction_phase", "初始防御")
        self.state.setdefault("current_focus", "")
        self.history: list = []
        self._rounds_since_last_resistance = 0
        self._prev_trust = self.state["trust"]
        self._prev_emotion = self.state["emotion"]["intensity"]

    def generate_reply(
        self,
        system_output: str,
        weapons_used: Optional[list] = None,
        scene_signals: Optional[dict] = None,
    ) -> dict:
        """
        生成代理回复

        Returns:
            dict: { "reply": str, "state": dict, "delta": dict }
        """
        self._rounds_since_last_resistance += 1
        self._apply_scene_signals(scene_signals)

        # 1. 强制阻力检查
        if self._should_inject_resistance():
            reply = self._inject_resistance()
            return self._build_result(reply)

        # 2. 局面规则匹配（优先于关键词）
        for rule in self.config.get("scene_rules", []):
            if self._match_scene_rule(rule, scene_signals):
                self._apply_action(rule["action"], weapons_used)
                reply = rule["action"]["reply"]
                return self._build_result(reply)

        # 3. 关键词规则匹配
        for rule in self.config["response_rules"]:
            if self._match_trigger(rule["trigger"], system_output):
                self._apply_action(rule["action"], weapons_used)
                reply = rule["action"]["reply"]
                return self._build_result(reply)

        # 4. 默认回复
        reply = self._build_default_reply()
        return self._build_result(reply)

    def _apply_scene_signals(self, scene_signals: Optional[dict]):
        if not scene_signals:
            return

        world_state = scene_signals.get("world_state", {}) or {}
        disturbance_event = scene_signals.get("disturbance_event", {}) or {}
        progress_state = str(world_state.get("progress_state", "")).strip()
        risk_level = str(world_state.get("risk_level", "")).strip()
        next_turn_focus = str(world_state.get("next_turn_focus", "")).strip()

        if next_turn_focus:
            self.state["current_focus"] = next_turn_focus

        if disturbance_event:
            self.state["interaction_phase"] = "扰动后重估"
            self.state["trust"] = max(0.0, self.state["trust"] - 0.03)
            self.state["emotion"]["intensity"] = min(1.0, self.state["emotion"]["intensity"] + 0.03)
            return

        if progress_state == "往收口走":
            self.state["interaction_phase"] = "收口确认"
        elif progress_state == "继续推进":
            self.state["interaction_phase"] = "有限松动"
        elif progress_state == "继续对齐":
            self.state["interaction_phase"] = "试探观察"
        elif risk_level in {"high", "critical"} or self.state["trust"] < 0.25:
            self.state["interaction_phase"] = "重新防御"
        else:
            self.state["interaction_phase"] = "初始防御"

    def _build_default_reply(self) -> str:
        phase = self.state.get("interaction_phase", "初始防御")
        focus = self.state.get("current_focus", "")
        if phase == "收口确认":
            return f"如果按这个方向继续，我更想先确认一下：{focus or '下一步到底怎么接'}。"
        if phase == "有限松动":
            return f"这方向有点意思，你先把 {focus or '最关键的一步'} 说清楚。"
        if phase == "试探观察":
            return f"我能继续听，但我更想知道 {focus or '这件事到底会不会落空'}。"
        if phase == "扰动后重估":
            return f"刚刚这个变化让我又得重新想一遍，先说说 {focus or '现在最大的变数'}。"
        return "我再考虑考虑。"

    def _should_inject_resistance(self) -> bool:
        interval = self.config["resistance_injection"]["interval_rounds"]
        if self._rounds_since_last_resistance >= interval:
            if self.state["emotion"]["intensity"] < 0.8:
                self._rounds_since_last_resistance = 0
                return True
        return False

    def _inject_resistance(self) -> str:
        replies = self.config["resistance_injection"]["replies"]
        effect = self.config["resistance_injection"]["effect"]
        self._apply_action(effect)
        return random.choice(replies)

    def _apply_action(self, action: dict, weapons_used: Optional[list] = None):
        if "emotion_intensity_delta" in action:
            self.state["emotion"]["intensity"] += action["emotion_intensity_delta"]
            self.state["emotion"]["intensity"] = max(0.0, min(1.0, self.state["emotion"]["intensity"]))
        if "trust_delta" in action:
            self.state["trust"] += action["trust_delta"]
            self.state["trust"] = max(0.0, min(1.0, self.state["trust"]))

        # 武器信任规则（支持按武器名和武器类型）
        if weapons_used:
            trust_rules = self.config.get("trust_rules", {})
            for weapon in weapons_used:
                weapon_name = weapon.get("name", "")
                weapon_type = weapon.get("type", "")
                # 优先按武器名查找（更精确），其次按类型查找
                if weapon_name in trust_rules:
                    self.state["trust"] += trust_rules[weapon_name]
                elif weapon_type in trust_rules:
                    self.state["trust"] += trust_rules[weapon_type]
                self.state["trust"] = max(0.0, min(1.0, self.state["trust"]))

    def _match_trigger(self, trigger: str, system_output: str) -> bool:
        conditions = [c.strip() for c in trigger.split("|")]
        return any(cond in system_output for cond in conditions)

    def _match_scene_rule(self, rule: dict, scene_signals: Optional[dict]) -> bool:
        if not scene_signals:
            return False

        world_state = scene_signals.get("world_state", {}) or {}
        disturbance_event = scene_signals.get("disturbance_event", {}) or {}
        when = rule.get("when", {}) or {}

        for key, expected in when.items():
            if key == "disturbance_present":
                actual = bool(disturbance_event)
            elif key == "interaction_phase":
                actual = self.state.get("interaction_phase", "")
            else:
                actual = str(world_state.get(key, "")).strip()

            if isinstance(expected, list):
                if actual not in expected:
                    return False
            else:
                if actual != expected:
                    return False
        return True

    def _build_result(self, reply: str) -> dict:
        delta = {
            "trust_change": self.state["trust"] - self._prev_trust,
            "emotion_change": self.state["emotion"]["intensity"] - self._prev_emotion,
        }
        self._prev_trust = self.state["trust"]
        self._prev_emotion = self.state["emotion"]["intensity"]
        return {
            "reply": reply,
            "state": dict(self.state),
            "delta": delta,
        }
