"""
Phase 2 验证测试：多维度上下文感知权重调整

测试场景：
1. 信任系数对成功步长的影响
2. 情绪×信任组合矩阵对失败步长的影响
3. 策略类型感知（共情/钩子/升维/防御）
4. 情绪强度系数
5. 信任趋势系数
6. 阻力系数
7. 能量模式系数
8. 边界值保护（权重不超 0.1-2.0）
9. 空上下文回退
"""
import sys
import os
import json
import tempfile
import shutil

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules.L5.scene_evolver import SceneEvolver


def create_test_evolver(tmp_dir: str) -> SceneEvolver:
    """创建一个临时目录的 evolver，避免污染真实配置"""
    scene_dir = os.path.join(tmp_dir, "test_scene")
    os.makedirs(scene_dir, exist_ok=True)
    
    # 创建 base.json
    with open(os.path.join(scene_dir, "base.json"), "w", encoding="utf-8") as f:
        json.dump({"version": "1.0", "scene_id": "test_scene"}, f)
    
    return SceneEvolver("test_scene", config_dir=tmp_dir)


def test_1_trust_multiplier_on_success():
    """测试1: 信任系数对成功步长的影响"""
    tmp = tempfile.mkdtemp()
    try:
        evolver = create_test_evolver(tmp)
        
        # 信任低时成功：步长应大幅降低 (0.05 * 0.4 = 0.02)
        ctx_low = {"emotion": "平静", "emotion_intensity": 0.3, "trust_level": "low", "trust_change": 0.0, "resistance_intensity": 0.0, "energy_mode": "A", "dual_core_state": "同频", "desires": {}}
        evolver.record_outcome("test_goal", "共情 + 正常化", success=True, context=ctx_low)
        weight_low = evolver.evolved_data["strategy_weights"].get("test_scene::test_goal::共情 + 正常化", 1.0)
        
        # 信任高时成功：步长应放大 (0.05 * 1.2 = 0.06)
        evolver2 = create_test_evolver(tmp)
        ctx_high = {"emotion": "平静", "emotion_intensity": 0.3, "trust_level": "high", "trust_change": 0.0, "resistance_intensity": 0.0, "energy_mode": "A", "dual_core_state": "同频", "desires": {}}
        evolver2.record_outcome("test_goal", "共情 + 正常化", success=True, context=ctx_high)
        weight_high = evolver2.evolved_data["strategy_weights"].get("test_scene::test_goal::共情 + 正常化", 1.0)
        
        assert weight_high > weight_low, f"信任高时成功权重({weight_high:.4f})应大于信任低时({weight_low:.4f})"
        print(f"  ✅ 信任低成功: 1.0 → {weight_low:.4f} (+{weight_low-1.0:.4f})")
        print(f"  ✅ 信任高成功: 1.0 → {weight_high:.4f} (+{weight_high-1.0:.4f})")
    finally:
        shutil.rmtree(tmp)


def test_2_emotion_trust_matrix_on_failure():
    """测试2: 情绪×信任组合矩阵对失败步长的影响"""
    tmp = tempfile.mkdtemp()
    try:
        # 愤怒+低信任：最严重 (0.03 * 3.0 = 0.09)
        evolver1 = create_test_evolver(tmp)
        ctx1 = {"emotion": "愤怒", "emotion_intensity": 0.5, "trust_level": "low", "trust_change": 0.0, "resistance_intensity": 0.0, "energy_mode": "B", "dual_core_state": "同频", "desires": {}}
        evolver1.record_outcome("test_goal", "钩子策略", success=False, context=ctx1)
        w1 = evolver1.evolved_data["strategy_weights"]["test_scene::test_goal::钩子策略"]
        
        # 平静+高信任：最轻微 (0.03 * 0.8 = 0.024)
        evolver2 = create_test_evolver(tmp)
        ctx2 = {"emotion": "平静", "emotion_intensity": 0.3, "trust_level": "high", "trust_change": 0.0, "resistance_intensity": 0.0, "energy_mode": "B", "dual_core_state": "同频", "desires": {}}
        evolver2.record_outcome("test_goal", "钩子策略", success=False, context=ctx2)
        w2 = evolver2.evolved_data["strategy_weights"]["test_scene::test_goal::钩子策略"]
        
        assert w1 < w2, f"愤怒+低信任失败权重({w1:.4f})应小于平静+高信任({w2:.4f})"
        print(f"  ✅ 愤怒+低信任失败: 1.0 → {w1:.4f} ({w1-1.0:.4f})")
        print(f"  ✅ 平静+高信任失败: 1.0 → {w2:.4f} ({w2-1.0:.4f})")
    finally:
        shutil.rmtree(tmp)


def test_3_empathy_strategy_in_anger():
    """测试3: 共情策略在愤怒时成功，权重增加更大"""
    tmp = tempfile.mkdtemp()
    try:
        # 共情策略在愤怒时成功：0.05 * 0.8 * 1.3 = 0.052
        evolver1 = create_test_evolver(tmp)
        ctx1 = {"emotion": "愤怒", "emotion_intensity": 0.5, "trust_level": "medium", "trust_change": 0.0, "resistance_intensity": 0.0, "energy_mode": "A", "dual_core_state": "同频", "desires": {}}
        evolver1.record_outcome("test_goal", "共情 + 正常化", success=True, context=ctx1)
        w1 = evolver1.evolved_data["strategy_weights"]["test_scene::test_goal::共情 + 正常化"]
        
        # 普通策略在愤怒时成功（无策略类型加成）：0.05 * 0.8 = 0.04
        evolver2 = create_test_evolver(tmp)
        ctx2 = {"emotion": "愤怒", "emotion_intensity": 0.5, "trust_level": "medium", "trust_change": 0.0, "resistance_intensity": 0.0, "energy_mode": "A", "dual_core_state": "同频", "desires": {}}
        evolver2.record_outcome("test_goal", "直接指令", success=True, context=ctx2)
        w2 = evolver2.evolved_data["strategy_weights"]["test_scene::test_goal::直接指令"]
        
        assert w1 > w2, f"共情策略在愤怒时成功({w1:.4f})应大于普通策略({w2:.4f})"
        print(f"  ✅ 共情策略愤怒成功: 1.0 → {w1:.4f}")
        print(f"  ✅ 普通策略愤怒成功: 1.0 → {w2:.4f}")
    finally:
        shutil.rmtree(tmp)


def test_4_empathy_failure_in_anger():
    """测试4: 共情策略在愤怒时失败，惩罚加倍"""
    tmp = tempfile.mkdtemp()
    try:
        # 共情在愤怒时失败：基础 * 矩阵 * 策略类型(1.5)
        evolver1 = create_test_evolver(tmp)
        ctx1 = {"emotion": "愤怒", "emotion_intensity": 0.5, "trust_level": "medium", "trust_change": 0.0, "resistance_intensity": 0.0, "energy_mode": "B", "dual_core_state": "同频", "desires": {}}
        evolver1.record_outcome("test_goal", "共情 + 正常化", success=False, context=ctx1)
        w1 = evolver1.evolved_data["strategy_weights"]["test_scene::test_goal::共情 + 正常化"]
        
        # 普通策略在愤怒时失败（无策略类型加成）
        evolver2 = create_test_evolver(tmp)
        ctx2 = {"emotion": "愤怒", "emotion_intensity": 0.5, "trust_level": "medium", "trust_change": 0.0, "resistance_intensity": 0.0, "energy_mode": "B", "dual_core_state": "同频", "desires": {}}
        evolver2.record_outcome("test_goal", "直接指令", success=False, context=ctx2)
        w2 = evolver2.evolved_data["strategy_weights"]["test_scene::test_goal::直接指令"]
        
        assert w1 < w2, f"共情策略在愤怒时失败({w1:.4f})应惩罚更大于普通策略({w2:.4f})"
        print(f"  ✅ 共情策略愤怒失败: 1.0 → {w1:.4f}")
        print(f"  ✅ 普通策略愤怒失败: 1.0 → {w2:.4f}")
    finally:
        shutil.rmtree(tmp)


def test_5_emotion_intensity_multiplier():
    """测试5: 情绪强度对失败惩罚的放大"""
    tmp = tempfile.mkdtemp()
    try:
        # 极高情绪强度 (0.9 > 0.8 → ×1.4)
        evolver1 = create_test_evolver(tmp)
        ctx1 = {"emotion": "愤怒", "emotion_intensity": 0.9, "trust_level": "medium", "trust_change": 0.0, "resistance_intensity": 0.0, "energy_mode": "B", "dual_core_state": "同频", "desires": {}}
        evolver1.record_outcome("test_goal", "钩子策略", success=False, context=ctx1)
        w1 = evolver1.evolved_data["strategy_weights"]["test_scene::test_goal::钩子策略"]
        
        # 低情绪强度 (0.3，无额外系数)
        evolver2 = create_test_evolver(tmp)
        ctx2 = {"emotion": "愤怒", "emotion_intensity": 0.3, "trust_level": "medium", "trust_change": 0.0, "resistance_intensity": 0.0, "energy_mode": "B", "dual_core_state": "同频", "desires": {}}
        evolver2.record_outcome("test_goal", "钩子策略", success=False, context=ctx2)
        w2 = evolver2.evolved_data["strategy_weights"]["test_scene::test_goal::钩子策略"]
        
        assert w1 < w2, f"高情绪强度失败({w1:.4f})应惩罚更大于低情绪({w2:.4f})"
        print(f"  ✅ 高情绪强度(0.9)失败: 1.0 → {w1:.4f}")
        print(f"  ✅ 低情绪强度(0.3)失败: 1.0 → {w2:.4f}")
    finally:
        shutil.rmtree(tmp)


def test_6_trust_trend_coefficient():
    """测试6: 信任趋势对成功/失败的影响"""
    tmp = tempfile.mkdtemp()
    try:
        # 信任上升趋势 + 成功：×1.2
        evolver1 = create_test_evolver(tmp)
        ctx1 = {"emotion": "平静", "emotion_intensity": 0.3, "trust_level": "medium", "trust_change": 0.05, "resistance_intensity": 0.0, "energy_mode": "A", "dual_core_state": "同频", "desires": {}}
        evolver1.record_outcome("test_goal", "共情策略", success=True, context=ctx1)
        w1 = evolver1.evolved_data["strategy_weights"]["test_scene::test_goal::共情策略"]
        
        # 信任下降趋势 + 成功：×0.8
        evolver2 = create_test_evolver(tmp)
        ctx2 = {"emotion": "平静", "emotion_intensity": 0.3, "trust_level": "medium", "trust_change": -0.05, "resistance_intensity": 0.0, "energy_mode": "A", "dual_core_state": "同频", "desires": {}}
        evolver2.record_outcome("test_goal", "共情策略", success=True, context=ctx2)
        w2 = evolver2.evolved_data["strategy_weights"]["test_scene::test_goal::共情策略"]
        
        assert w1 > w2, f"信任上升时成功({w1:.4f})应大于信任下降时({w2:.4f})"
        print(f"  ✅ 信任上升(+0.05)成功: 1.0 → {w1:.4f}")
        print(f"  ✅ 信任下降(-0.05)成功: 1.0 → {w2:.4f}")
    finally:
        shutil.rmtree(tmp)


def test_7_energy_mode_coefficient():
    """测试7: 能量模式对失败惩罚的影响"""
    tmp = tempfile.mkdtemp()
    try:
        # Mode C 失败：×1.3
        evolver1 = create_test_evolver(tmp)
        ctx1 = {"emotion": "平静", "emotion_intensity": 0.3, "trust_level": "medium", "trust_change": 0.0, "resistance_intensity": 0.0, "energy_mode": "C", "dual_core_state": "同频", "desires": {}}
        evolver1.record_outcome("test_goal", "愿景 + 尊严", success=False, context=ctx1)
        w1 = evolver1.evolved_data["strategy_weights"]["test_scene::test_goal::愿景 + 尊严"]
        
        # Mode A 失败：×0.8
        evolver2 = create_test_evolver(tmp)
        ctx2 = {"emotion": "平静", "emotion_intensity": 0.3, "trust_level": "medium", "trust_change": 0.0, "resistance_intensity": 0.0, "energy_mode": "A", "dual_core_state": "同频", "desires": {}}
        evolver2.record_outcome("test_goal", "愿景 + 尊严", success=False, context=ctx2)
        w2 = evolver2.evolved_data["strategy_weights"]["test_scene::test_goal::愿景 + 尊严"]
        
        assert w1 < w2, f"Mode C失败({w1:.4f})应惩罚更大于Mode A({w2:.4f})"
        print(f"  ✅ Mode C失败: 1.0 → {w1:.4f}")
        print(f"  ✅ Mode A失败: 1.0 → {w2:.4f}")
    finally:
        shutil.rmtree(tmp)


def test_8_boundary_protection():
    """测试8: 权重边界保护 (0.1-2.0)"""
    tmp = tempfile.mkdtemp()
    try:
        # 极端失败 → 权重不应低于 0.1
        evolver1 = create_test_evolver(tmp)
        ctx1 = {"emotion": "愤怒", "emotion_intensity": 0.95, "trust_level": "low", "trust_change": -0.1, "resistance_intensity": 0.8, "energy_mode": "C", "dual_core_state": "对抗", "desires": {"pride": 0.8}}
        evolver1.record_outcome("test_goal", "共情策略", success=False, context=ctx1)
        w1 = evolver1.evolved_data["strategy_weights"]["test_scene::test_goal::共情策略"]
        assert w1 >= 0.1, f"权重不应低于0.1，实际: {w1}"
        
        # 极端成功 → 权重不应超过 2.0
        evolver2 = create_test_evolver(tmp)
        ctx2 = {"emotion": "平静", "emotion_intensity": 0.3, "trust_level": "high", "trust_change": 0.1, "resistance_intensity": 0.8, "energy_mode": "A", "dual_core_state": "协同", "desires": {"greed": 0.8}}
        # 多次成功
        for _ in range(50):
            evolver2.record_outcome("test_goal", "贪婪+恐惧", success=True, context=ctx2)
        w2 = evolver2.evolved_data["strategy_weights"]["test_scene::test_goal::贪婪+恐惧"]
        assert w2 <= 2.0, f"权重不应超过2.0，实际: {w2}"
        
        print(f"  ✅ 极端失败权重: {w1:.4f} (≥0.1)")
        print(f"  ✅ 多次成功权重: {w2:.4f} (≤2.0)")
    finally:
        shutil.rmtree(tmp)


def test_9_empty_context_fallback():
    """测试9: 空上下文回退到默认值"""
    tmp = tempfile.mkdtemp()
    try:
        evolver = create_test_evolver(tmp)
        
        # 无上下文成功
        evolver.record_outcome("test_goal", "直接指令", success=True, context=None)
        w1 = evolver.evolved_data["strategy_weights"]["test_scene::test_goal::直接指令"]
        
        # 空字典上下文失败
        evolver.record_outcome("test_goal", "直接指令", success=False, context={})
        w2 = evolver.evolved_data["strategy_weights"]["test_scene::test_goal::直接指令"]
        
        assert w1 > 1.0, f"无上下文成功权重应增加，实际: {w1}"
        assert w2 < w1, f"失败后权重应减少，实际: {w2} (之前: {w1})"
        print(f"  ✅ 无上下文成功: 1.0 → {w1:.4f}")
        print(f"  ✅ 空字典失败: {w1:.4f} → {w2:.4f}")
    finally:
        shutil.rmtree(tmp)


def test_10_strategy_classification():
    """测试10: 策略分类准确性"""
    tmp = tempfile.mkdtemp()
    try:
        evolver = create_test_evolver(tmp)
        
        assert evolver._classify_strategy_type("共情 + 正常化") == "empathy"
        assert evolver._classify_strategy_type("好奇+稀缺") == "hook"
        assert evolver._classify_strategy_type("愿景 + 尊严") == "upgrade"
        assert evolver._classify_strategy_type("沉默+示弱") == "defense"
        assert evolver._classify_strategy_type("直接指令") == "normal"
        assert evolver._classify_strategy_type("贪婪+恐惧") == "hook"
        assert evolver._classify_strategy_type("升维对话") == "upgrade"
        print("  ✅ 所有策略分类正确")
    finally:
        shutil.rmtree(tmp)


if __name__ == "__main__":
    print("=" * 60)
    print("Phase 2 多维度上下文感知权重调整 - 验证测试")
    print("=" * 60)
    
    tests = [
        ("测试1: 信任系数对成功步长", test_1_trust_multiplier_on_success),
        ("测试2: 情绪×信任组合矩阵", test_2_emotion_trust_matrix_on_failure),
        ("测试3: 共情策略在愤怒时成功", test_3_empathy_strategy_in_anger),
        ("测试4: 共情策略在愤怒时失败", test_4_empathy_failure_in_anger),
        ("测试5: 情绪强度系数", test_5_emotion_intensity_multiplier),
        ("测试6: 信任趋势系数", test_6_trust_trend_coefficient),
        ("测试7: 能量模式系数", test_7_energy_mode_coefficient),
        ("测试8: 权重边界保护", test_8_boundary_protection),
        ("测试9: 空上下文回退", test_9_empty_context_fallback),
        ("测试10: 策略分类准确性", test_10_strategy_classification),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_fn in tests:
        print(f"\n{name}")
        try:
            test_fn()
            passed += 1
        except AssertionError as e:
            print(f"  ❌ 失败: {e}")
            failed += 1
        except Exception as e:
            print(f"  ❌ 异常: {e}")
            failed += 1
    
    print(f"\n{'=' * 60}")
    print(f"结果: {passed} 通过, {failed} 失败")
    print(f"{'=' * 60}")
    
    if failed > 0:
        sys.exit(1)
