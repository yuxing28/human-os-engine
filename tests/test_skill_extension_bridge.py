from schemas.context import Context

from modules.L5.skill_extension_bridge import compose_skill_prompt, extract_skill_flags


def test_extract_skill_flags_should_read_nested_skill_toggle():
    flags = extract_skill_flags({"skills": {"leijun": {"enabled": True}}})

    assert flags["leijun"]["enabled"] is True


def test_compose_skill_prompt_should_append_leijun_extension_when_enabled(monkeypatch):
    import modules.L5.skill_registry as skill_registry

    class FakeRegistry:
        def build_skill_prompt(self, skill_id, _world_state):
            return f"prompt:{skill_id}"

    monkeypatch.setattr(skill_registry, "get_registry", lambda: FakeRegistry())

    ctx = Context(session_id="skill-bridge-test")
    ctx.skill_flags = {"leijun": {"enabled": True}}

    prompt = compose_skill_prompt(ctx, "sales")

    assert "prompt:sales" in prompt
    assert "【可选人格扩展包】" in prompt
    assert "【雷军产品扩展禁区】" in prompt
