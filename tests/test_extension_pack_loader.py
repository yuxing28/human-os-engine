from modules.L5.extension_pack_loader import build_extension_pack_prompt, load_extension_skill_prompt


def test_should_load_single_leijun_extension_prompt():
    prompt = load_extension_skill_prompt("leijun", "leijun_decision")

    assert "【雷军式判断】" in prompt
    assert "【扩展原则】" in prompt
    assert "重点：" in prompt or "判断：" in prompt
    assert "收主线" in prompt


def test_should_build_combined_extension_pack_prompt():
    prompt = build_extension_pack_prompt("leijun", ["leijun_persona_core", "leijun_communication"])

    assert "【可选人格扩展包】" in prompt
    assert "【雷军人格核心】" in prompt
    assert "【雷军式表达】" in prompt
    assert "只做辅助参考" in prompt
    assert "本轮已经明确启用这个扩展" in prompt


def test_should_keep_actionable_persona_core_cues():
    prompt = load_extension_skill_prompt("leijun", "leijun_persona_core")

    assert "雷军式口径" in prompt
    assert "先抓主线" in prompt
    assert "讲清楚为什么" in prompt


def test_should_add_product_guardrails_for_leijun_product_pack():
    prompt = build_extension_pack_prompt("leijun", ["leijun_persona_core", "leijun_product"])

    assert "【雷军产品扩展禁区】" in prompt
    assert "不要使用原价/现价" in prompt
    assert "销售压单技巧" in prompt
    assert "不要凭空编造具体功能" in prompt
