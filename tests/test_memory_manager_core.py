from types import SimpleNamespace

import pytest

import modules.memory as memory_mod


def test_search_memory_falls_back_to_keywords_and_applies_memory_type_filter(tmp_path, monkeypatch):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-fallback"
    manager._memories[user_id] = [
        memory_mod.Memory(content="用户喜欢编程", memory_type="fact", importance=0.8),
        memory_mod.Memory(content="用户偏好简洁表达", memory_type="preference", importance=0.6),
    ]

    captured = {}

    def fake_vector(_user_id, _query, _memories, _limit):
        return None

    def fake_keywords(query, memories, limit):
        captured["query"] = query
        captured["memories"] = memories
        captured["limit"] = limit
        return memories[:1]

    monkeypatch.setattr(manager, "_search_memory_vector", fake_vector)
    monkeypatch.setattr(manager, "_search_memory_keywords", fake_keywords)

    result = manager.search_memory(user_id, "编程", limit=3, memory_type="fact")

    assert len(result) == 1
    assert result[0].memory_type == "fact"
    assert captured["query"] == "编程"
    assert captured["limit"] == 3
    assert len(captured["memories"]) == 1
    assert captured["memories"][0].memory_type == "fact"


def test_update_profile_updates_known_fields_only(tmp_path):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-profile"

    manager.update_profile(
        user_id,
        occupation="产品经理",
        preferences=["结构化", "简洁"],
        unknown_field="should_ignore",
    )

    profile = manager.get_profile(user_id)
    assert profile is not None
    assert profile.occupation == "产品经理"
    assert profile.preferences == ["结构化", "简洁"]
    assert not hasattr(profile, "unknown_field")
    assert profile.updated_at > 0


def test_update_patterns_use_weighted_smoothing(tmp_path):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-pattern"

    manager.update_emotion_pattern(user_id, "焦虑", 1.0)
    manager.update_emotion_pattern(user_id, "焦虑", 0.0)

    manager.update_desire_pattern(user_id, "control", 0.2)
    manager.update_desire_pattern(user_id, "control", 1.0)

    profile = manager.get_profile(user_id)
    assert profile is not None
    assert profile.emotion_patterns["焦虑"] == pytest.approx(0.7, abs=1e-6)
    assert profile.desire_patterns["control"] == pytest.approx(0.44, abs=1e-6)


def test_get_unified_context_combines_core_sections(tmp_path, monkeypatch):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-context"

    manager.update_profile(user_id, occupation="创业者", preferences=["高效沟通"])

    related_memories = [memory_mod.Memory(content="用户正在准备融资路演", memory_type="fact", importance=0.9)]
    monkeypatch.setattr(manager, "search_memory", lambda *_args, **_kwargs: related_memories)

    fake_session_memory = SimpleNamespace(
        get_context_for_llm=lambda _session_id: "【本轮重要决策】\n【局面状态】\n- 场景: work_conflict | 关系: 对等-合作 | 阶段: 推进 | 信任: 中 | 张力: medium | 风险: low | 推进: 继续推进 | 承诺: 已形成跟进 | 下一轮: 明天我们再把条款对齐\n【关系闭环摘要】\n- 关系状态: 对等-合作 | 场景: work_conflict | 阶段: 推进\n- 闭环结果: 本轮结果: positive | 本轮闭环: 明天我们再把条款对齐。\n- 第2轮 [upgrade]: 明确先对齐目标"
    )
    monkeypatch.setattr(memory_mod, "get_session_memory", lambda: fake_session_memory)

    enum_like = lambda value: SimpleNamespace(value=value)
    fake_context = SimpleNamespace(
        scene_config=SimpleNamespace(scene_id="work_conflict"),
        goal=SimpleNamespace(granular_goal="", display_name=""),
        self_state=SimpleNamespace(energy_mode=enum_like("稳态")),
        user=SimpleNamespace(
            trust_level=enum_like("中"),
            emotion=SimpleNamespace(type=enum_like("紧张"), intensity=0.6),
        ),
    )

    text = manager.get_unified_context(user_id, "我该怎么推进沟通", context=fake_context)

    assert "【用户画像】" in text
    assert "【局面状态】" in text
    assert "【关系闭环摘要】" in text
    assert "【本轮重要决策】" in text
    assert "【当前状态】" in text
    assert "【相关记忆】" in text
    assert "用户正在准备融资路演" in text
    assert text.index("【关系闭环摘要】") < text.index("【相关记忆】")
    assert text.index("【本轮重要决策】") < text.index("【当前状态】")


def test_get_context_for_llm_structures_memory_by_bucket(tmp_path, monkeypatch):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-structured"

    manager.update_profile(user_id, occupation="运营", preferences=["先讲结论"])

    related_memories = [
        memory_mod.Memory(content="用户偏好先讲结论", memory_type="preference", importance=0.9),
        memory_mod.Memory(content="用户已经决定本周先试小步推进", memory_type="decision", importance=0.8),
        memory_mod.Memory(content="策略模板：先承接再推进", memory_type="strategy", importance=0.75),
        memory_mod.Memory(content="失败经验: 场景=sales | 失败码=F03 | 先别急着压结果", memory_type="failure", importance=0.72),
        memory_mod.Memory(content="用户正在准备一份汇报", memory_type="fact", importance=0.7),
        memory_mod.Memory(content="这次卡住后先别急着推", memory_type="experience", importance=0.6),
    ]
    monkeypatch.setattr(manager, "search_memory", lambda *_args, **_kwargs: related_memories)
    monkeypatch.setattr(manager, "get_recent_memories", lambda *_args, **_kwargs: [])

    text = manager.get_context_for_llm(user_id, "老板让我先汇报")

    assert "【用户画像】" in text
    assert "【相关记忆】" in text
    assert "偏好记忆:" in text
    assert "决策记忆:" in text
    assert "策略记忆:" in text
    assert "失败记忆:" in text
    assert "事实记忆:" in text
    assert "经验记忆:" in text
    assert "【经验索引】" in text
    assert "失败避坑:" in text
    assert text.index("【经验索引】") < text.index("【相关记忆】")


def test_get_unified_context_should_include_world_state_fields(tmp_path, monkeypatch):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-world-state"

    monkeypatch.setattr(manager, "search_memory", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(manager, "get_recent_memories", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(memory_mod, "get_session_memory", lambda: SimpleNamespace(get_context_for_llm=lambda _sid: ""))

    enum_like = lambda value: SimpleNamespace(value=value)
    fake_context = SimpleNamespace(
        scene_config=SimpleNamespace(scene_id="sales"),
        goal=SimpleNamespace(granular_goal="sales_followup", display_name="推进成交"),
        self_state=SimpleNamespace(energy_mode=enum_like("稳态")),
        user=SimpleNamespace(
            trust_level=enum_like("中"),
            emotion=SimpleNamespace(type=enum_like("紧张"), intensity=0.6),
        ),
        world_state=SimpleNamespace(
            situation_stage="推进",
            risk_level="medium",
            tension_level="medium",
            progress_state="继续推进",
            commitment_state="已形成跟进",
            action_loop_state="推进: 继续推进 | 承诺: 已形成跟进 | 下一轮: 明天继续对齐价格和条款",
            next_turn_focus="明天继续对齐价格和条款",
        ),
    )

    text = manager.get_unified_context(user_id, "客户已经松动", context=fake_context)

    assert "阶段: 推进" in text
    assert "风险: medium" in text
    assert "推进: 继续推进" in text
    assert "承诺: 已形成跟进" in text
    assert "动作:" in text
    assert "【下一轮焦点】" in text
    assert "明天继续对齐价格和条款" in text


def test_extract_turn_progress_hints_should_prioritize_evolution_and_action_loop():
    unified_context = """【本轮重要决策】
【状态演化】
- 信任 low→medium | 阶段 观察→推进 | 承诺 未形成→已形成跟进
【动作闭环】
- 本轮结果: positive | 动作闭环: 推进: 继续推进 | 承诺: 已形成跟进 | 下一轮: 明天再对齐 | 当前目标: 谈判推进
【局面状态】
- 场景: negotiation | 关系: 对等-合作 | 阶段: 推进 | 信任: medium | 张力: medium | 风险: low | 推进: 继续推进 | 承诺: 已形成跟进 | 下一轮: 明天再对齐
"""

    text = memory_mod.extract_turn_progress_hints(unified_context, limit=4)

    assert "【局面推进】" in text
    assert "状态演化:" in text
    assert "动作闭环:" in text
    assert "局面状态:" in text
    assert text.index("状态演化:") < text.index("动作闭环:")
    assert text.index("动作闭环:") < text.index("局面状态:")


def test_add_memory_skips_too_low_importance(tmp_path):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-low-importance"

    manager.add_memory(user_id, "这条不该入库", memory_type="fact", importance=0.1)
    memories = manager.get_recent_memories(user_id, limit=5)

    assert memories == []


def test_add_memory_deduplicates_same_content_same_type(tmp_path):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-duplicate"

    manager.add_memory(user_id, "用户偏好先讲结论", memory_type="preference", importance=0.8)
    manager.add_memory(user_id, "用户偏好先讲结论", memory_type="preference", importance=0.9)

    memories = manager.get_recent_memories(user_id, limit=10)
    assert len(memories) == 1
    assert memories[0].content == "用户偏好先讲结论"


def test_add_memory_allows_same_content_with_different_type(tmp_path):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-duplicate-type"

    manager.add_memory(user_id, "用户正在准备融资", memory_type="fact", importance=0.8)
    manager.add_memory(user_id, "用户正在准备融资", memory_type="conversation", importance=0.8)

    memories = manager.get_recent_memories(user_id, limit=10)
    assert len(memories) == 2


def test_add_memory_records_structured_bucket_metadata(tmp_path):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-bucket"

    manager.add_memory(user_id, "用户偏好先讲结论", memory_type="conversation", importance=0.8)

    memories = manager.get_recent_memories(user_id, limit=5)
    assert len(memories) == 1
    assert memories[0].metadata.get("bucket") == "preference"


def test_extract_structured_memory_hints_keeps_key_sections():
    unified_context = """【用户画像】
职业: 运营
偏好: 先讲结论
【相关记忆】
偏好记忆: 用户习惯先听结论
事实记忆: 用户正在准备汇报
经验记忆: 上次先收口更顺
【经验提示】
1. 先对齐重点
2. 再给动作"""

    text = memory_mod.extract_structured_memory_hints(unified_context, limit_per_section=3)

    assert "职业: 运营" in text
    assert "偏好记忆:" in text
    assert "事实记忆:" in text
    assert "经验记忆:" in text
    assert "先对齐重点" in text


def test_extract_decision_experience_hints_should_prioritize_key_lines():
    unified_context = """【用户画像】
职业: 运营
【相关记忆】
偏好记忆: 用户习惯先听结论
决策记忆: 上轮决定先收口再推进
经验记忆: 上次直接强推导致对抗升级
【经验提示】
1. 先对齐目标
2. 再推进动作"""

    text = memory_mod.extract_decision_experience_hints(unified_context, limit=4)

    assert "决策记忆: 上轮决定先收口再推进" in text
    assert "经验记忆: 上次直接强推导致对抗升级" in text
    assert "先对齐目标" in text or "再推进动作" in text


def test_extract_decision_experience_hints_should_prioritize_failure_experience_lines():
    unified_context = """【相关记忆】
经验记忆: 正常经验，先沟通再推进
经验记忆: 失败经验: 场景=sales | 失败码=F03 | 先别急着压结果
决策记忆: 上轮决定先对齐风险边界
【经验提示】
1. 先别扩话题
2. 再推进一个动作"""

    text = memory_mod.extract_decision_experience_hints(unified_context, limit=2)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    assert lines
    assert "失败经验" in lines[0] or "失败码" in lines[0]


def test_extract_failure_experience_hints_should_pick_failure_lines_first():
    unified_context = """【相关记忆】
经验记忆: 正常经验，先沟通再推进
经验记忆: 失败经验: 场景=sales | 失败码=F03 | 先别急着压结果
决策记忆: 上轮决定先对齐风险边界
【经验提示】
1. 避免一次谈多个变量
2. 再推进一个动作"""

    text = memory_mod.extract_failure_experience_hints(unified_context, limit=2)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    assert len(lines) >= 1
    assert any("失败经验" in line or "失败码" in line for line in lines)


def test_extract_experience_digest_hints_should_pick_digest_lines():
    unified_context = """【相关记忆】
经验记忆: 正常经验，先沟通再推进
【经验索引】
- 失败避坑: 失败经验: 场景=sales | 失败码=F03 | 先别急着压结果
- 策略参考: 策略模板：先承接再推进
- 决策线索: 上轮决定先收口再推进
【经验提示】
1. 先对齐目标"""

    text = memory_mod.extract_experience_digest_hints(unified_context, limit=2)
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    assert len(lines) == 2
    assert "失败避坑" in lines[0]
    assert "策略参考" in lines[1] or "决策线索" in lines[1]


def test_get_write_summary_should_include_bucket_distribution(tmp_path):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-summary-bucket"

    manager.add_memory(user_id, "用户偏好先看结论", memory_type="preference", importance=0.8)
    manager.add_memory(user_id, "用户决定先做小范围试点", memory_type="decision", importance=0.8)
    manager.add_memory(user_id, "好的", memory_type="conversation", importance=0.1)  # low_importance -> skipped

    summary = manager.get_write_summary(user_id, limit=20)

    assert "by_bucket" in summary
    assert summary["by_bucket"].get("preference", 0) >= 1
    assert summary["by_bucket"].get("decision", 0) >= 1
    assert summary["by_bucket"].get("conversation", 0) >= 1
    assert summary["health"]["status"] in {"healthy", "strict", "noisy", "shallow", "blocked"}


def test_get_global_write_summary_should_aggregate_bucket_distribution(tmp_path):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))

    manager.add_memory("user-global-1", "用户偏好先讲结论", memory_type="preference", importance=0.8)
    manager.add_memory("user-global-2", "用户正在准备汇报", memory_type="fact", importance=0.8)

    summary = manager.get_global_write_summary(limit_per_user=20)

    assert "by_bucket" in summary
    assert summary["by_bucket"].get("preference", 0) >= 1
    assert summary["by_bucket"].get("fact", 0) >= 1
    assert summary["health"]["status"] in {"healthy", "strict", "noisy", "shallow", "blocked"}


def test_get_write_summary_health_should_detect_strict_mode(tmp_path):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-health-strict"

    for i in range(8):
        manager.add_memory(user_id, f"短句{i}", memory_type="conversation", importance=0.1)

    summary = manager.get_write_summary(user_id, limit=20)
    assert summary["health"]["status"] in {"strict", "blocked"}


def test_get_write_summary_health_should_detect_shallow_mode(tmp_path):
    manager = memory_mod.MemoryManager(storage_dir=str(tmp_path / "memory"))
    user_id = "user-health-shallow"

    for i in range(8):
        manager.add_memory(
            user_id,
            f"用户: 正常对话内容{i}",
            memory_type="conversation",
            importance=0.4,
        )

    summary = manager.get_write_summary(user_id, limit=20)
    assert summary["health"]["status"] in {"shallow", "noisy"}
