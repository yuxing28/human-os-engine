"""
Step 2 目标识别层定向测试。
"""

import importlib
import sys
from types import SimpleNamespace

from graph.nodes.step2_goal import (
    _extract_goal_anchor,
    _should_invoke_goal_llm,
    _should_invoke_resistance_llm,
    step2_goal_detection,
)
from graph.nodes.contradiction_check import _check_logical_contradiction
from schemas.context import Context
from schemas.enums import ResistanceType


def _state(user_input: str, ctx: Context | None = None):
    return {
        "context": ctx or Context(session_id="test-step2"),
        "user_input": user_input,
    }


def test_extract_goal_anchor_should_capture_explicit_request():
    description, source, confidence = _extract_goal_anchor(
        "我想解决客户一直不签单的问题",
        previous_goal="",
    )
    assert "客户一直不签单" in description
    assert source == "user_explicit"
    assert confidence >= 0.8


def test_step2_should_keep_previous_goal_for_generic_short_reply():
    ctx = Context(session_id="test-step2-keep")
    ctx.goal.current.description = "客户一直不签单"
    ctx.goal.current.type = "利益价值"

    result = step2_goal_detection(_state("继续", ctx))

    assert result["context"].goal.current.description == "客户一直不签单"
    assert result["context"].goal.current.type == "利益价值"


def test_step2_should_mark_resistance_instead_of_overwriting_goal_on_price_giveup():
    ctx = Context(session_id="test-step2-resistance")
    ctx.goal.current.description = "推进客户成交"
    ctx.goal.current.type = "利益价值"

    result = step2_goal_detection(_state("算了，太贵了，不买了", ctx))

    assert result["context"].user.resistance.type == ResistanceType.GREED
    assert result["context"].goal.current.description == "推进客户成交"


def test_step2_should_switch_goal_when_user_changes_topic():
    ctx = Context(session_id="test-step2-switch")
    ctx.goal.current.description = "客户签单"
    ctx.goal.current.type = "利益价值"

    result = step2_goal_detection(_state("不想聊这个，我想说我和女朋友总吵架", ctx))

    assert result["context"].goal.drift_detected is True
    assert "女朋友总吵架" in result["context"].goal.current.description
    assert result["context"].goal.history[-1].description == "客户签单"


def test_extract_goal_anchor_should_capture_deeper_goal_after_surface_statement():
    description, source, confidence = _extract_goal_anchor(
        "我和老婆最近总吵架，我其实不是想吵赢，我是想让她愿意好好跟我说话",
        previous_goal="",
    )

    assert "让她愿意好好跟我说话" in description
    assert source == "user_explicit"
    assert confidence >= 0.9


def test_step2_should_use_deeper_goal_instead_of_surface_complaint():
    ctx = Context(session_id="test-step2-deeper-goal")

    result = step2_goal_detection(_state("客户一直说再考虑，我其实最想推进到成交", ctx))

    assert "推进到成交" in result["context"].goal.current.description
    assert result["context"].goal.current.type == "利益价值"
    assert result["context"].goal.current.confidence >= 0.9


def test_step2_should_fill_goal_layers_for_deeper_statement():
    ctx = Context(session_id="test-step2-goal-layers")

    result = step2_goal_detection(_state("我不是想吵赢，我只是想把关系稳住", ctx))
    layers = result["context"].goal.layers

    assert layers.surface_goal != ""
    assert "把关系稳住" in layers.active_goal
    assert "把关系稳住" in layers.underlying_goal


def test_step2_should_reflect_resistance_in_underlying_goal():
    ctx = Context(session_id="test-step2-underlying-resistance")
    ctx.goal.current.description = "推进客户成交"
    ctx.goal.current.type = "利益价值"

    result = step2_goal_detection(_state("算了，太贵了，不买了", ctx))
    layers = result["context"].goal.layers

    assert result["context"].user.resistance.type == ResistanceType.GREED
    assert layers.active_goal == "推进客户成交"
    assert "投入产出" in layers.underlying_goal


def test_identify_goal_with_llm_should_include_memory_hint(monkeypatch):
    from graph.nodes.step2_goal import _identify_goal_with_llm

    captured = {}

    def fake_invoke_fast(prompt: str, system_prompt: str):
        captured["prompt"] = prompt
        captured["system_prompt"] = system_prompt
        return '{"goal_id": "goal.sales", "confidence": 0.95}'

    # 某些测试会替换 sys.modules["llm.nvidia_client"]。
    # 这里直接锁定“当前实际生效”的模块对象，避免混跑时补丁打偏。
    nvidia_module = sys.modules.get("llm.nvidia_client") or importlib.import_module("llm.nvidia_client")
    monkeypatch.setattr(nvidia_module, "invoke_fast", fake_invoke_fast)

    goal_taxonomy = [
        SimpleNamespace(granular_goal="goal.sales", display_name="推进成交", description="推进成交"),
        SimpleNamespace(granular_goal="goal.relationship", display_name="修复关系", description="修复关系"),
    ]

    goal_id = _identify_goal_with_llm(
        "我现在有点卡，想推进下去",
        goal_taxonomy,
        memory_hint="职业: 运营\n偏好记忆: 先讲结论",
    )

    assert goal_id == "goal.sales"
    assert "补充记忆" in captured["prompt"]
    assert "偏好记忆: 先讲结论" in captured["prompt"]


def test_identify_goal_with_llm_should_hit_cache_for_same_input(monkeypatch):
    from graph.nodes import step2_goal as step2_module

    call_counter = {"count": 0}

    def fake_invoke_fast(_prompt: str, _system_prompt: str):
        call_counter["count"] += 1
        return '{"goal_id": "goal.sales", "confidence": 0.95}'

    nvidia_module = sys.modules.get("llm.nvidia_client") or importlib.import_module("llm.nvidia_client")
    monkeypatch.setattr(nvidia_module, "invoke_fast", fake_invoke_fast)
    step2_module._GOAL_LLM_CACHE.clear()

    goal_taxonomy = [
        SimpleNamespace(granular_goal="goal.sales", display_name="推进成交", description="推进成交"),
    ]
    user_text = "我现在有点卡，想推进下去"
    memory_hint = "偏好记忆: 先讲结论"

    first = step2_module._identify_goal_with_llm(user_text, goal_taxonomy, memory_hint=memory_hint)
    second = step2_module._identify_goal_with_llm(user_text, goal_taxonomy, memory_hint=memory_hint)

    assert first == "goal.sales"
    assert second == "goal.sales"
    assert call_counter["count"] == 1


def test_should_invoke_goal_llm_should_be_false_for_non_goal_smalltalk():
    assert _should_invoke_goal_llm("今天太阳挺好，我们继续。") is False


def test_should_invoke_goal_llm_should_be_true_for_goal_question():
    assert _should_invoke_goal_llm("我现在卡住了，接下来怎么办？") is True


def test_should_invoke_resistance_llm_should_be_false_for_plain_statement():
    assert _should_invoke_resistance_llm("收到，我们继续推进。") is False


def test_should_invoke_resistance_llm_should_be_true_for_objection_signal():
    assert _should_invoke_resistance_llm("我有点担心风险，预算也不够。") is True


def test_step2_should_skip_dynamic_scene_match_for_sandbox_with_fixed_scene(monkeypatch):
    import modules.L5.skill_registry as skill_registry

    def _should_not_call_registry():
        raise AssertionError("sandbox fixed-scene flow should not call dynamic scene registry")

    monkeypatch.setattr(skill_registry, "get_registry", _should_not_call_registry)

    ctx = Context(session_id="sandbox-mt-sales-fixed")
    ctx.scene_config = SimpleNamespace(
        scene_id="sales",
        goal_taxonomy=[],
        weapon_blacklist={},
    )

    result = step2_goal_detection(_state("继续", ctx))
    new_ctx = result["context"]

    assert new_ctx.primary_scene == "sales"
    assert new_ctx.secondary_scenes == []


def test_step2_should_keep_management_scene_for_fatigue_input(monkeypatch):
    import modules.L5.skill_registry as skill_registry

    class FakeRegistry:
        def match_scenes(self, _user_input):
            return "emotion", ["management"], {"emotion": 0.92, "management": 0.84}

        def build_skill_prompt(self, scene_id, _world_state):
            return f"prompt:{scene_id}"

    monkeypatch.setattr(skill_registry, "get_registry", lambda: FakeRegistry())

    ctx = Context(session_id="test-step2-mgmt-fatigue")
    ctx.primary_scene = "management"
    ctx.scene_config = SimpleNamespace(
        scene_id="management",
        goal_taxonomy=[],
        weapon_blacklist={},
    )

    result = step2_goal_detection(_state("又是新工具，能不能消停会？", ctx))
    new_ctx = result["context"]

    assert new_ctx.primary_scene == "management"
    assert new_ctx.scene_config.scene_id == "management"
    assert new_ctx.matched_scenes["emotion"] > new_ctx.matched_scenes["management"]


def test_contradiction_check_should_not_treat_rewrite_request_as_giveup():
    ctx = Context(session_id="test-contradiction-rewrite")
    ctx.goal.current.description = "把团队节奏稳住"

    result = _check_logical_contradiction(
        ctx,
        "我不想再靠加班硬扛，想要一个可执行节奏。",
    )

    assert result is None


def test_contradiction_check_should_still_catch_real_giveup_signal():
    ctx = Context(session_id="test-contradiction-giveup")
    ctx.goal.current.description = "推进客户成交"

    result = _check_logical_contradiction(
        ctx,
        "我不想做了，算了。",
    )

    assert result is not None
    assert "想放弃" in result
