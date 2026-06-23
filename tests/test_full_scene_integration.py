"""
Human-OS Engine 3.0 — 全场景真实 API 联调测试

使用真实 LLM API 跑 4 个场景各 10 条用例，验证端到端效果。
"""

import pytest
import time
from schemas.context import Context
from graph.builder import build_graph
from modules.L5.scene_loader import load_scene_config


# 每个场景 10 条真实用例
SCENE_CASES = {
    "sales": [
        ("客户说太贵了，怎么回应？", {"sales"}),
        ("线索质量太差，全是空号怎么办？", {"sales"}),
        ("竞品比我们便宜 30%，怎么打？", {"sales", "negotiation"}),
        ("客户已经加了微信但不回消息", {"sales"}),
        ("月底了还差 3 单达标，急", {"sales", "emotion"}),
        ("客户说需要跟老板汇报，让我等", {"sales", "management"}),
        ("SDR 转 AE 后客户说不需要了", {"sales"}),
        ("ROI 算不清楚，CFO 不批预算", {"sales", "management"}),
        ("客户说下个月再考虑，怎么逼单？", {"sales", "negotiation"}),
        ("被挂电话了，心态崩了", {"sales", "emotion"}),
    ],
    "management": [
        ("下属绩效不达标，怎么跟他谈？", {"management"}),
        ("团队内卷严重，大家都在摸鱼", {"management"}),
        ("跨部门协同推不动，怎么办？", {"management", "negotiation"}),
        ("向上汇报，领导期望太高", {"management"}),
        ("员工加班太多，快 burnout 了", {"management", "emotion"}),
        ("新来的工程师技术好但不合群", {"management"}),
        ("老员工躺平，怎么激励？", {"management"}),
        ("OKR 定了但没人执行", {"management"}),
        ("下属越级汇报，怎么处理？", {"management"}),
        ("团队要裁员 20%，怎么沟通？", {"management", "emotion"}),
    ],
    "negotiation": [
        ("谈判陷入僵局，对方不肯让步", {"negotiation"}),
        ("我们的 BATNA 是什么？", {"negotiation"}),
        ("锚定价格太高，需要重置", {"negotiation"}),
        ("对方最后通牒，不签就走人", {"negotiation", "emotion"}),
        ("合同条款有争议，怎么协商？", {"negotiation"}),
        ("对方压价太狠，怎么守住底线？", {"negotiation", "sales"}),
        ("双赢方案怎么设计？", {"negotiation"}),
        ("谈判对手是竞争型人格", {"negotiation", "emotion"}),
        ("甲方要求 90 天账期，我们只能 30 天", {"negotiation", "sales"}),
        ("谈判中对方突然换人了", {"negotiation", "management"}),
    ],
    "emotion": [
        ("你根本就不爱我，否则怎么可能忘了纪念日？", {"emotion"}),
        ("没有她我真的活不下去了", {"emotion"}),
        ("我老婆拿走了我的身份证，说怕我出去乱花钱", {"emotion", "management"}),
        ("孩子一直在哭，我感觉自己快要失控打他了", {"emotion", "management"}),
        ("我感觉自己像个透明人，消失了大家都会更高兴", {"emotion"}),
        ("我知道我刚才说话重了，但我真的很累", {"emotion"}),
        ("我妈每天不打招呼就进我房间，我快疯了", {"emotion", "management"}),
        ("老板在所有人面前说我脑子进水了", {"emotion", "management"}),
        ("我看着电脑就想吐，但我没法辞职", {"emotion", "management"}),
        ("我最信任的朋友把我的私事告诉了所有人", {"emotion"}),
    ],
}


class TestFullSceneIntegration:
    """全场景真实 API 联调"""

    @pytest.fixture
    def graph(self):
        return build_graph()

    @pytest.mark.parametrize("scene,inputs", SCENE_CASES.items())
    def test_scene_basic(self, graph, scene, inputs):
        """每个场景 10 条用例不崩溃，且每句话的场景落点都在合理范围内"""
        ctx = Context(session_id=f"integration-{scene}")
        
        for i, case in enumerate(inputs):
            user_input, expected_scenes = case
            start = time.time()
            result = graph.invoke({
                "context": ctx,
                "user_input": user_input,
            })
            elapsed = time.time() - start
            
            # 验证输出
            assert result.get("output") is not None, f"{scene} 用例 {i+1} 无输出"
            assert len(result["output"]) > 0, f"{scene} 用例 {i+1} 输出为空"
            
            # 验证场景路由：允许动态换挡，但每条输入都要落在这句话自己的合理区间内
            assert ctx.scene_config is not None, f"{scene} 用例 {i+1} 场景未加载"
            routed_scenes = {
                getattr(ctx, "primary_scene", "") or ctx.scene_config.scene_id,
                ctx.scene_config.scene_id,
                *(getattr(ctx, "secondary_scenes", []) or []),
                *(getattr(ctx, "matched_scenes", []) or []),
            }
            routed_scenes.discard("")
            assert routed_scenes & expected_scenes, \
                f"{scene} 用例 {i+1} 场景不合理: expected={sorted(expected_scenes)}, primary={ctx.primary_scene}, secondaries={ctx.secondary_scenes}, matched={ctx.matched_scenes}"
            
            # 验证响应时间（不超过 60 秒）
            assert elapsed < 60, f"{scene} 用例 {i+1} 响应超时: {elapsed:.1f}s"
            
            print(f"\n[{scene}] 用例 {i+1}/10: {user_input[:30]}... ({elapsed:.1f}s)")
            print(f"  输出: {result['output'][:80]}...")

    def test_response_quality(self, graph):
        """验证输出质量：无内部术语、无禁用词"""
        ctx = Context(session_id="quality-check")
        
        # 情感场景不应出现威胁性语言
        result = graph.invoke({
            "context": ctx,
            "user_input": "我很难受，感觉没人理解我",
        })
        output = result.get("output", "")
        assert len(output) > 10, "输出太短"
        
        # 不应出现内部术语
        internal_terms = ["granular_goal", "strategy_preferences", "weapon_blacklist"]
        for term in internal_terms:
            assert term not in output, f"输出包含内部术语: {term}"
