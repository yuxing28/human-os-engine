"""
Human-OS Engine 3.0 — 证据注入器 (Evidence Injector)
根据客户的异议类型，生成逼真的脱敏数据、SLA 条款或案例指标，供话术生成使用。
"""

import random

def generate_evidence(objection_type: str, industry: str = "通用") -> str:
    """
    生成针对特定异议的证据数据。
    """
    if objection_type == "SLA":
        return (
            "SLA 核心指标：\n"
            "1. 可用性承诺：99.95%（全年停机不超过 4.38 小时）。\n"
            "2. 响应时效：P1 级故障 15 分钟内响应，2 小时内恢复。\n"
            "3. 赔偿条款：每低于承诺 0.01%，赔偿当月服务费的 10%，上限 100%。"
        )
    elif objection_type == "Competitor":
        return (
            "竞品对比实测数据（第三方机构认证）：\n"
            "1. 延迟表现：同等并发下，我们比行业平均低 30%（28ms vs 40ms）。\n"
            "2. 稳定性：过去一年 P99 可用性 99.97%，优于头部云厂商 0.02%。\n"
            "3. 客户留存：年度续约率 98%，流失率 < 2%。"
        )
    elif objection_type == "Raw Data":
        return (
            "脱敏监控数据摘要（过去 12 个月）：\n"
            "1. 延迟分布：0-20ms (85%), 20-50ms (12%), >50ms (3%)。\n"
            "2. 故障恢复：平均 MTTR 45 分钟，最长 2.5 小时。\n"
            "3. 峰值承载：双十一期间 QPS 峰值 50 万，系统零宕机。"
        )
    elif objection_type == "Case":
        return (
            "同行业标杆案例（已脱敏）：\n"
            "1. 客户背景：某 Top 10 制造企业，员工数 5000+。\n"
            "2. 实施效果：上线 3 个月后，供应链协同效率提升 35%，库存成本降低 20%。\n"
            "3. 客户评价：'系统稳定性超出预期，售后响应速度是行业最快的。'"
        )
    else:
        return (
            "行业通用基准：\n"
            "1. 部署周期：标准方案 4-6 周，定制化 8-12 周。\n"
            "2. 投资回报：平均 6-9 个月收回成本。\n"
            "3. 服务支持：7x24 小时专属技术顾问。"
        )

def detect_objection_type(user_input: str) -> str:
    """
    检测用户异议类型。
    """
    input_lower = user_input.lower()
    if any(kw in input_lower for kw in ["sla", "可用性", "停机", "赔偿", "响应时间"]):
        return "SLA"
    elif any(kw in input_lower for kw in ["对比", "竞品", "比...强", "差异", "优势"]):
        return "Competitor"
    elif any(kw in input_lower for kw in ["原始数据", "日志", "明细", "分布", "p99", "统计"]):
        return "Raw Data"
    elif any(kw in input_lower for kw in ["案例", "同行", "类似", "标杆", "谁用过"]):
        return "Case"
    return "General"
