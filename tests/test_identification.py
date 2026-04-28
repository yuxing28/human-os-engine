"""
Human-OS Engine - 测试：识别模块
"""

import pytest
from modules.L2.sins_keyword import identify_desires
from modules.L2.collaboration_temperature import identify_emotion
from modules.L2.dual_core_recognition import identify_dual_core


# ===== 八宗罪关键词识别测试 =====

class TestSinsKeyword:
    """八宗罪关键词识别测试"""

    def test_fear_detection(self):
        """测试恐惧识别"""
        result = identify_desires("我好害怕失败，担心会损失很多钱")
        dominant, score = result.desires.get_dominant()
        assert dominant == "fear"
        assert score > 0

    def test_greed_detection(self):
        """测试贪婪识别"""
        result = identify_desires("我想赚钱，有什么好机会吗")
        dominant, score = result.desires.get_dominant()
        assert dominant == "greed"
        assert score > 0

    def test_sloth_detection(self):
        """测试懒惰识别"""
        result = identify_desires("太麻烦了，不想做，有没有更简单的办法")
        dominant, score = result.desires.get_dominant()
        assert dominant == "sloth"
        assert score > 0

    def test_wrath_detection(self):
        """测试愤怒识别"""
        result = identify_desires("气死我了，太过分了，受不了")
        dominant, score = result.desires.get_dominant()
        assert dominant == "wrath"
        assert score > 0

    def test_confidence_range(self):
        """测试置信度范围"""
        result = identify_desires("我想赚钱")
        assert 0.0 <= result.confidence <= 1.0

    def test_empty_input(self):
        """测试空输入"""
        result = identify_desires("")
        assert result.confidence >= 0.0


# ===== 协作温度识别测试 =====

class TestCollaborationTemperature:
    """协作温度识别测试"""

    def test_frustrated_detection(self):
        """测试挫败识别"""
        result = identify_emotion("我太难了，学编程学不会，想放弃")
        assert result.type == "挫败"
        assert result.intensity > 0

    def test_impatient_detection(self):
        """测试急躁识别"""
        result = identify_emotion("急死了，下周就要交报告了")
        assert result.type == "急躁"

    def test_angry_detection(self):
        """测试愤怒识别"""
        result = identify_emotion("气死我了，这人太过分了")
        assert result.type == "愤怒"

    def test_calm_default(self):
        """测试平静默认"""
        result = identify_emotion("随便聊聊")
        # 无明显情绪词，默认平静
        assert result.confidence >= 0.0

    def test_motive_detection(self):
        """测试动机识别"""
        result = identify_emotion("我害怕失败，担心会出问题")
        assert result.motive == "回避恐惧"


# ===== 双核状态识别测试 =====

class TestDualCoreRecognition:
    """双核状态识别测试"""

    def test_conflict_detection(self):
        """测试对抗状态识别"""
        result = identify_dual_core("我知道要减肥，但就是控制不住想吃")
        assert result.state == "对抗"

    def test_rationalization_detection(self):
        """测试合理化状态识别"""
        result = identify_dual_core("没办法，我天生就懒，改不了")
        assert result.state == "合理化"

    def test_sync_detection(self):
        """测试同频状态识别"""
        result = identify_dual_core("好的，明白了，就这样做吧")
        assert result.state == "同频"

    def test_dominant_core(self):
        """测试主导核判断"""
        # 感性核主导
        result = identify_dual_core("气死了！太过分了！烦死了！")
        assert result.dominant == "感性核"

    def test_evidence_collection(self):
        """测试证据收集"""
        result = identify_dual_core("因为数据显示，这个方案有70%成功率")
        assert len(result.evidence) > 0


# ===== 元控制器 Fallback 测试 =====

class TestMetaControllerFallback:
    """元控制器 Fallback 规则测试"""

    def test_emotion_classification(self):
        """测试情绪表达分类"""
        from prompts.meta_controller import fallback_classify
        result = fallback_classify("好烦啊，不想活了")
        assert result["input_type"] == "情绪表达"

    def test_consultation_classification(self):
        """测试问题咨询分类"""
        from prompts.meta_controller import fallback_classify
        result = fallback_classify("怎么才能坚持学习？有什么方法吗？")
        assert result["input_type"] == "问题咨询"

    def test_scenario_classification(self):
        """测试场景描述分类"""
        from prompts.meta_controller import fallback_classify
        result = fallback_classify("我老板让我加班，同事还不配合")
        assert result["input_type"] == "场景描述"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
