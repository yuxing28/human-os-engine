"""
Human-OS Engine - Prompt 模板：元控制器（Step 1.5）

基于总控 v4.0 的元控制器规则。
判断用户输入类型：情绪表达 / 问题咨询 / 场景描述 / 混合
"""

from utils.types import sanitize_for_prompt

META_CONTROLLER_SYSTEM_PROMPT = """你是一个对话元控制器。你的任务是：
1) 判断用户输入类型
2) 粗识别用户当前身份线索
3) 粗识别当前互动情境

1. 情绪表达：用户在发泄情绪、求安慰、倾诉，核心诉求是"被听到、被理解"
   特征：情绪词密集、无具体问题、无具体场景
   例："好烦"、"不想活了"、"气死我了"、"我太难了"

2. 问题咨询：用户在求知、求方法、求理解，核心诉求是"获得答案或方法"
   特征：包含疑问词（怎么/如何/为什么/什么是）、明确的问题
   例："怎么才能坚持？"、"什么是战略视野"、"如何管理情绪"

3. 场景描述：用户在描述具体事件或人际冲突，核心诉求是"获得解决方案"
   特征：包含具体人物、事件、冲突、职场/社交场景
   例："我老板让我加班"、"客户说太贵了"、"朋友借钱不想借"

4. 混合：同时包含明显情绪且带具体事件或问题
   例："我好烦，不知道怎么坚持学习"（情绪+问题）
   例："气死我了，领导又批评我"（情绪+场景）

身份线索（identity_hint）可选值：
- 个人决策：用户在为自己做决定
- 团队决策：用户在代表团队/组织决策
- 关系沟通：用户在处理亲密关系/家庭/朋友关系
- 未识别

互动情境（situation_hint）可选值：
- 推进结果：目标是推进结果、拿到动作或结论
- 协商分歧：目标是协调分歧、谈条件或找平衡
- 稳定情绪：目标是先稳住情绪和关系
- 管理执行：目标是团队执行、节奏、协同
- 未识别

请根据用户输入输出 JSON，不要输出其他文本。
"""

META_CONTROLLER_USER_PROMPT = """请判断以下用户输入的类型：

用户输入：{user_input}
用户情绪：{emotion_type}（强度：{emotion_intensity}）

请返回JSON格式：
{{
    "input_type": "情绪表达|问题咨询|场景描述|混合",
    "confidence": 0.0-1.0,
    "reason": "简要说明判断理由",
    "identity_hint": "个人决策|团队决策|关系沟通|未识别",
    "identity_confidence": 0.0-1.0,
    "situation_hint": "推进结果|协商分歧|稳定情绪|管理执行|未识别",
    "situation_confidence": 0.0-1.0
}}
"""


def build_meta_controller_prompt(
    user_input: str,
    emotion_type: str = "平静",
    emotion_intensity: float = 0.5,
) -> tuple[str, str]:
    """
    构建元控制器的 Prompt

    Returns:
        tuple[str, str]: (system_prompt, user_prompt)
    """
    safe_user_input = sanitize_for_prompt(user_input, max_length=2000)
    system = META_CONTROLLER_SYSTEM_PROMPT
    user = META_CONTROLLER_USER_PROMPT.format(
        user_input=safe_user_input,
        emotion_type=emotion_type,
        emotion_intensity=emotion_intensity,
    )
    return system, user


# ===== Fallback 规则（LLM 不可用时）=====

EMOTION_KEYWORDS = [
    "烦", "气", "急", "怕", "恨", "难过", "伤心", "崩溃", "绝望",
    "开心", "高兴", "兴奋", "激动", "感动", "想哭", "生气", "愤怒",
    "焦虑", "紧张", "不安", "失落", "沮丧", "郁闷", "无语",
    "不想活", "死", "烦死了", "气死了", "受不了", "好烦", "太烦",
]

QUESTION_KEYWORDS = [
    "怎么", "如何", "为什么", "什么是", "怎样", "哪个", "多少",
    "能不能", "可以吗", "有什么方法", "有什么办法", "怎么做到",
]

SCENARIO_KEYWORDS = [
    "老板", "领导", "同事", "客户", "朋友", "家人", "父母", "老公", "老婆",
    "公司", "工作", "项目", "谈判", "会议", "汇报", "面试", "加班",
    "借钱", "吵架", "批评", "拒绝", "投诉", "合作",
]

TEAM_IDENTITY_KEYWORDS = [
    "团队", "下属", "部门", "老板", "公司", "项目组", "成员", "绩效", "汇报", "跨部门",
]

RELATION_IDENTITY_KEYWORDS = [
    "父亲", "母亲", "孩子", "儿子", "女儿", "家人", "伴侣", "老公", "老婆", "朋友",
]

NEGOTIATION_SITUATION_KEYWORDS = [
    "底线", "条款", "让步", "谈", "协商", "风险", "条件", "折中", "博弈",
]

EXECUTION_SITUATION_KEYWORDS = [
    "本周", "落地", "动作", "执行", "推进", "计划", "安排", "节奏", "任务",
]


def fallback_classify(user_input: str) -> dict:
    """
    Fallback 分类规则（LLM 不可用时）

    基于关键词密度公式。
    """
    total_words = len(user_input)

    # 计算各类关键词密度
    emotion_count = sum(1 for kw in EMOTION_KEYWORDS if kw in user_input)
    question_count = sum(1 for kw in QUESTION_KEYWORDS if kw in user_input)
    scenario_count = sum(1 for kw in SCENARIO_KEYWORDS if kw in user_input)

    emotion_density = emotion_count / max(total_words, 1)

    # 分类逻辑
    # 混合：同时有情绪词和疑问词/场景词
    if emotion_count > 0 and (question_count > 0 or scenario_count > 0):
        input_type = "混合"
        confidence = 0.6
        reason = "情绪+问题/场景混合"
    elif question_count > 0 and emotion_density < 0.1:
        input_type = "问题咨询"
        confidence = 0.7
        reason = "包含疑问词且情绪密度低"
    elif scenario_count >= 2 and emotion_density < 0.1:
        input_type = "场景描述"
        confidence = 0.6
        reason = "包含多个场景关键词"
    elif emotion_count > 0:
        input_type = "情绪表达"
        confidence = 0.6
        reason = "包含情绪词"
    else:
        input_type = "混合"
        confidence = 0.4
        reason = "无法明确分类"

    # 身份粗识别
    if any(kw in user_input for kw in RELATION_IDENTITY_KEYWORDS):
        identity_hint = "关系沟通"
        identity_confidence = 0.7
    elif any(kw in user_input for kw in TEAM_IDENTITY_KEYWORDS):
        identity_hint = "团队决策"
        identity_confidence = 0.7
    elif len(user_input.strip()) > 0:
        identity_hint = "个人决策"
        identity_confidence = 0.45
    else:
        identity_hint = "未识别"
        identity_confidence = 0.2

    # 情境粗识别
    if any(kw in user_input for kw in NEGOTIATION_SITUATION_KEYWORDS):
        situation_hint = "协商分歧"
        situation_confidence = 0.75
    elif any(kw in user_input for kw in EXECUTION_SITUATION_KEYWORDS):
        situation_hint = "管理执行"
        situation_confidence = 0.7
    elif emotion_count > 0 and emotion_density >= 0.1:
        situation_hint = "稳定情绪"
        situation_confidence = 0.65
    elif question_count > 0:
        situation_hint = "推进结果"
        situation_confidence = 0.55
    else:
        situation_hint = "未识别"
        situation_confidence = 0.3

    return {
        "input_type": input_type,
        "confidence": confidence,
        "reason": reason,
        "identity_hint": identity_hint,
        "identity_confidence": identity_confidence,
        "situation_hint": situation_hint,
        "situation_confidence": situation_confidence,
    }
