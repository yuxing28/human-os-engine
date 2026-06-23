# -*- coding: utf-8 -*-

from scripts.testing.run_leijun_ab_test import _build_markdown_report, _normalize_judge_payload


def test_should_normalize_llm_judge_payload():
    raw = {
        "preferred_version": "experiment",
        "score_baseline": 72,
        "score_experiment": 84,
        "more_like_leijun": True,
        "too_hard_or_performance_like": False,
        "steals_main_system_judgment": False,
        "summary": "更像抓主线，但还没抢系统判断。",
        "strengths": ["更会收主线", "说法更直接"],
        "risks": ["略偏硬"],
        "suggestion": "把语气再放松一点。",
    }

    result = _normalize_judge_payload(raw)
    assert result["preferred_version"] == "experiment"
    assert result["score_baseline"] == 72
    assert result["score_experiment"] == 84
    assert result["more_like_leijun"] is True
    assert result["strengths"] == ["更会收主线", "说法更直接"]
    assert result["risks"] == ["略偏硬"]


def test_markdown_report_should_include_judge_section():
    payload = {
        "timestamp": "2026-04-19T14:00:00",
        "scene": "management",
        "case_id": "decision_anchor",
        "case_desc": "测试",
        "packs": ["leijun_persona_core", "leijun_decision"],
        "user_input": "我到底先抓哪件事？",
        "baseline": {"elapsed_ms": 100, "output": "默认输出", "scene": "management", "skill_prompt": ""},
        "experiment": {"elapsed_ms": 120, "output": "雷军输出", "scene": "management", "skill_prompt": ""},
        "experiment_extension_prompt": "【可选人格扩展包】",
        "llm_judge": {
            "preferred_version": "experiment",
            "score_baseline": 70,
            "score_experiment": 83,
            "more_like_leijun": True,
            "too_hard_or_performance_like": False,
            "steals_main_system_judgment": False,
            "summary": "更像雷军式抓主线。",
            "strengths": ["更聚焦"],
            "risks": ["语气略硬"],
            "suggestion": "把第一句再放松一点。",
            "raw_text": "",
        },
    }

    report = _build_markdown_report(payload)
    assert "## LLM 评审结论" in report
    assert "更像雷军式抓主线" in report
    assert "### 优点" in report
