from modules.L5.skill_registry import SkillRegistry
from schemas.context import WorldState


def test_skill_registry_default_dir_not_dependent_on_cwd(monkeypatch, tmp_path):
    """默认技能目录应锚定项目根目录，而不是当前工作目录"""
    monkeypatch.chdir(tmp_path)
    registry = SkillRegistry()

    assert registry.skills_dir.endswith("human-os-engine\\skills")
    assert "sales" in registry.skills
    assert "emotion" in registry.skills
    assert set(registry.skills.keys()) == {"sales", "management", "negotiation", "emotion"}
    assert "leijun_persona_core" not in registry.skills


def test_skill_prompt_should_be_summarized_principles():
    registry = SkillRegistry()

    prompt = registry.get_skill_prompt("sales")

    assert "【场景原则】" in prompt
    assert "场景：" in prompt
    assert "先看：" in prompt
    assert "禁区：" in prompt
    assert "话术模板" not in prompt
    assert "当用户说" not in prompt


def test_build_skill_prompt_should_include_world_state_brief():
    registry = SkillRegistry()
    world_state = WorldState(
        scene_id="sales",
        situation_stage="推进",
        risk_level="medium",
        tension_level="medium",
        progress_state="继续推进",
        commitment_state="已形成跟进",
        action_loop_state="推进: 继续推进 | 承诺: 已形成跟进",
        next_turn_focus="先对齐预算边界",
    )

    prompt = registry.build_skill_prompt("sales", world_state)

    assert "【场景原则】" in prompt
    assert "【当前局面】" in prompt
    assert "阶段=推进" in prompt
    assert "风险=medium" in prompt
    assert "动作=推进: 继续推进 | 承诺: 已形成跟进" in prompt
    assert "焦点=先对齐预算边界" in prompt


def test_build_skill_prompt_should_only_read_relevant_world_state_per_scene():
    registry = SkillRegistry()
    world_state = WorldState(
        scene_id="emotion",
        relationship_position="对方防御中",
        situation_stage="修复",
        trust_level="medium",
        tension_level="high",
        risk_level="medium",
        pressure_level="high",
        progress_state="继续推进",
        commitment_state="已形成跟进",
        action_loop_state="推进: 继续推进 | 承诺: 已形成跟进",
        next_turn_focus="先让对方把委屈说完",
    )

    emotion_prompt = registry.build_skill_prompt("emotion", world_state)
    sales_prompt = registry.build_skill_prompt("sales", world_state)

    assert "关系=对方防御中" in emotion_prompt
    assert "信任=medium" in emotion_prompt
    assert "压力=high" not in emotion_prompt
    assert "承诺=已形成跟进" not in emotion_prompt

    assert "推进=继续推进" in sales_prompt
    assert "承诺=已形成跟进" in sales_prompt
    assert "关系=对方防御中" not in sales_prompt
    assert "信任=medium" not in sales_prompt
