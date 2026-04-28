from simulation.customer_agent import CustomerAgent, CustomerState, Persona
from simulation.persona_factory import SCENE_PERSONA_CONFIGS, UniversalPersonaFactory
from simulation.user_agent import UserAgent


def _build_customer_agent() -> CustomerAgent:
    agent = CustomerAgent.__new__(CustomerAgent)
    agent.persona = Persona(
        name="张总",
        role="采购负责人",
        age=38,
        personality="谨慎、多疑，但会在看到确定性后松动",
        hidden_agenda="怕担责",
        budget_range="50-80万",
        pain_points=["上线失败风险"],
        trigger_words=["案例", "保障", "风险"],
        dealbreakers=["催促", "画大饼"],
        product="企业级系统",
    )
    agent.state = CustomerState(trust=0.28, emotion=0.55)
    return agent


def test_customer_agent_prompt_should_include_world_state_and_phase():
    agent = _build_customer_agent()
    prompt = agent._build_prompt(
        "我们先把最容易落地的一步对齐。",
        scene_signals={
            "world_state": {
                "progress_state": "继续对齐",
                "risk_level": "medium",
                "next_turn_focus": "先确认实施风险和谁来担责",
                "action_loop_state": "已形成下一步",
            },
            "disturbance_event": {"label": "预算突然收紧"},
        },
    )

    assert "【当前阶段】扰动后重估" in prompt
    assert "推进状态: 继续对齐" in prompt
    assert "当前扰动: 预算突然收紧" in prompt
    assert "先确认实施风险和谁来担责" in prompt


def test_user_agent_should_shift_default_reply_with_scene_signals(tmp_path):
    config_path = tmp_path / "agent.json"
    config_path.write_text(
        """
{
  "initial_state": {
    "emotion": {"type": "怀疑", "intensity": 0.6},
    "trust": 0.3
  },
  "response_rules": [],
  "resistance_injection": {
    "interval_rounds": 99,
    "replies": ["我还是不放心。"],
    "effect": {"emotion_intensity_delta": 0.05, "trust_delta": -0.02}
  }
}
""".strip(),
        encoding="utf-8",
    )

    agent = UserAgent(str(config_path))
    result = agent.generate_reply(
        "我们可以继续推进。",
        scene_signals={
            "world_state": {
                "progress_state": "继续推进",
                "next_turn_focus": "先把责任边界说清楚",
            }
        },
    )

    assert "先把责任边界说清楚" in result["reply"]
    assert agent.state["interaction_phase"] == "有限松动"


def test_user_agent_should_prefer_scene_rules_over_keyword_rules(tmp_path):
    config_path = tmp_path / "agent_scene.json"
    config_path.write_text(
        """
{
  "initial_state": {
    "emotion": {"type": "怀疑", "intensity": 0.6},
    "trust": 0.3
  },
  "scene_rules": [
    {
      "when": {
        "progress_state": "继续推进",
        "risk_level": "low"
      },
      "action": {
        "emotion_intensity_delta": -0.02,
        "trust_delta": 0.05,
        "reply": "先别催我成交，你先把验证方式说明白。"
      }
    }
  ],
  "response_rules": [
    {
      "trigger": "保证|承诺",
      "action": {
        "emotion_intensity_delta": 0.05,
        "trust_delta": -0.03,
        "reply": "话说太满了，我不信。"
      }
    }
  ],
  "resistance_injection": {
    "interval_rounds": 99,
    "replies": ["我还是不放心。"],
    "effect": {"emotion_intensity_delta": 0.05, "trust_delta": -0.02}
  }
}
""".strip(),
        encoding="utf-8",
    )

    agent = UserAgent(str(config_path))
    result = agent.generate_reply(
        "我保证这次肯定没问题。",
        scene_signals={
            "world_state": {
                "progress_state": "继续推进",
                "risk_level": "low",
            }
        },
    )

    assert result["reply"] == "先别催我成交，你先把验证方式说明白。"


def test_persona_factory_prompt_should_ask_for_current_situation_fields():
    factory = UniversalPersonaFactory.__new__(UniversalPersonaFactory)
    factory._configs = {"sales": SCENE_PERSONA_CONFIGS["sales"]}
    factory.model = "fake-model"

    captured = {}

    class _FakeResponse:
        class _Choice:
            class _Message:
                content = """
{"name":"张总","age":38,"hidden_agenda":"怕担责","budget_range":"50-80万","trigger_words":["案例","ROI"],"dealbreakers":["催促"],"current_stage":"试探观察","current_pressure":"预算被卡住","relationship_position":"礼貌疏离","current_blocker":"还没看到足够确定性"}
"""

            message = _Message()

        choices = [_Choice()]

    class _FakeCompletions:
        @staticmethod
        def create(**kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"]
            return _FakeResponse()

    class _FakeClient:
        chat = type("Chat", (), {"completions": _FakeCompletions()})()

    factory.client = _FakeClient()

    persona = factory.generate("sales", seed={
        "industry": "金融",
        "role": "CTO",
        "personality": "多疑，总觉得销售在忽悠，需要第三方证明",
    })

    assert "这不是只做一张人物名片" in captured["prompt"]
    assert "current_stage" in captured["prompt"]
    assert "current_pressure" in captured["prompt"]
    assert persona.current_stage == "试探观察"
    assert persona.current_pressure == "预算被卡住"
    assert persona.relationship_position == "礼貌疏离"
    assert persona.current_blocker == "还没看到足够确定性"
