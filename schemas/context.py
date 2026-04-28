"""
Human-OS Engine - 全局 Context 数据结构

对应总控规格第二章的完整 Context 定义。
这是所有模块共享的"数据契约"。
"""

from typing import Any, List, Dict

from pydantic import BaseModel, Field
from schemas.enums import FeedbackType, Mode
from schemas.user_state import UserState


class GoalItem(BaseModel):
    """单个目标"""
    description: str = ""
    type: str = "利益价值"  # GoalType 的值
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    source: str = "system_inferred"  # GoalSource 的值


class GoalLayers(BaseModel):
    """三层目标结构（Step2 内部使用）"""
    surface_goal: str = ""      # 用户嘴上在说什么
    active_goal: str = ""       # 当前这轮真正想推进什么
    underlying_goal: str = ""   # 深层顾虑/底层想保住什么


class Goal(BaseModel):
    """目标状态 - goal"""
    current: GoalItem = Field(default_factory=GoalItem)
    history: list[GoalItem] = Field(default_factory=list)
    drift_detected: bool = False
    layers: GoalLayers = Field(default_factory=GoalLayers)
    granular_goal: str = ""  # 细粒度目标标识（场景插件）
    display_name: str = ""   # 细粒度目标显示名称（场景插件）


class EnergyAllocation(BaseModel):
    """能量分配 - self.energy_allocation"""
    inner: float = Field(default=0.7, ge=0.0, le=1.0)
    outer: float = Field(default=0.2, ge=0.0, le=1.0)
    environment: float = Field(default=0.1, ge=0.0, le=1.0)


class SelfState(BaseModel):
    """系统自身状态 - self"""
    is_stable: bool = True
    energy_mode: Mode = Mode.A
    energy_allocation: EnergyAllocation = Field(default_factory=EnergyAllocation)


class SelfCheckState(BaseModel):
    """Step3 稳态判断快照（标准字段，供后续节点直接读取）"""
    stability_trend: str = "stable"         # worsening / swinging / recovering / stable
    interaction_tension: str = "low"        # high / medium / low
    push_risk: str = "low"                  # high / medium / low
    repair_need: bool = False               # 当前是否应优先修复关系/节奏
    trend_focus: str = ""                   # 本轮趋势关注点文本
    collapse_stage: str = "stable"          # inner_exhaustion / outer_damage / attention_hijack / stable
    recovery_focus: str = ""                # 当前恢复重点
    recovery_actions: list[str] = Field(default_factory=list)
    energy_pressure: float = Field(default=0.0, ge=0.0, le=1.0)
    negative_streak: int = 0


class StrategySkeleton(BaseModel):
    """Step6 轻量策略骨架（先后顺序）"""
    do_now: list[str] = Field(default_factory=list)
    do_later: list[str] = Field(default_factory=list)
    avoid_now: list[str] = Field(default_factory=list)
    fallback_move: str = ""


class CurrentStrategy(BaseModel):
    """当前策略状态 - current_strategy"""
    mode_sequence: list[Mode] = Field(default_factory=list)
    current_step_index: int = 0
    stage: str = ""
    combo_name: str = ""  # 当前使用的策略组合名称
    skeleton: StrategySkeleton = Field(default_factory=StrategySkeleton)
    fallback_count: int = 0
    upgrade_failed_count: int = 0  # 升维失败计数（连续 2 轮标记不适合升维）
    upgrade_eligible: bool = True  # 是否允许升维


class WorldState(BaseModel):
    """轻量局面状态快照（供主线和沙盒共同读取）"""
    scene_id: str = "未识别"
    relationship_position: str = "未识别"
    situation_stage: str = "未识别"
    trust_level: str = "未识别"
    tension_level: str = "low"
    risk_level: str = "low"
    pressure_level: str = "low"
    progress_state: str = "观察中"
    commitment_state: str = "未形成"
    action_loop_state: str = ""
    active_goal: str = ""
    next_turn_focus: str = ""


class DialogueFrame(BaseModel):
    """当前多轮对话框架：稳定“正在聊什么”和“这一轮要怎么接”。"""
    active_topic: str = ""
    user_act: str = "new_topic"  # new_topic / followup_detail / repair_challenge / acknowledge / continue_same
    answer_contract: str = ""    # 本轮回复必须履行的承接要求
    last_system_move: str = ""


class HistoryItem(BaseModel):
    """历史记录项"""
    role: str  # "user" | "system"
    content: str
    timestamp: str = ""
    metadata: dict = Field(default_factory=dict)


class Context(BaseModel):
    """
    全局 Context - 总控大脑的核心数据结构

    这是 LangGraph 图状态的基础，所有节点共享。
    """
    # 基本信息
    session_id: str
    version: str = "3.0"

    # 目标
    goal: Goal = Field(default_factory=Goal)

    # 用户状态
    user: UserState = Field(default_factory=UserState)

    # 系统自身状态
    self_state: SelfState = Field(default_factory=lambda: SelfState())
    self_check: SelfCheckState = Field(default_factory=SelfCheckState)

    # 历史记录
    history: list[HistoryItem] = Field(default_factory=list)

    # 当前策略
    current_strategy: CurrentStrategy = Field(default_factory=CurrentStrategy)

    # 反馈
    last_feedback: FeedbackType = FeedbackType.NEUTRAL
    last_feedback_trust_change: float | None = None  # 【修复2】用于信任变化直接判定 feedback

    # 知识引用（L5 模块查阅记录）
    knowledge_refs: list[str] = Field(default_factory=list)

    # 武器使用计数（表达多样性检查）
    weapon_usage_count: dict[str, int] = Field(default_factory=dict)

    # 长期记忆上下文（从记忆层检索）
    long_term_memory: str = ""

    # 统一上下文（阶段一优化：合并画像/状态/笔记/记忆/经验）
    unified_context: str = ""

    # 历史摘要（阶段二：压缩后的中间上下文）
    history_summary: str = ""

    # 会话笔记上下文（本轮重要决策摘要）
    session_notes_context: str = ""

    # 轻量局面状态（状态世界层第一版）
    world_state: WorldState = Field(default_factory=WorldState)

    # 多轮对话框架：防止每轮重新开局
    dialogue_frame: DialogueFrame = Field(default_factory=DialogueFrame)

    # 记忆写入报告（可观测性：记录本轮写入/过滤结果）
    memory_write_report: list[dict] = Field(default_factory=list)

    # 七个维度识别结果（每轮更新，供 Step 6 升维使用）
    _dimension_result: Any = None

    # 欲望压制/转化关系分析结果（Step 1 识别后供 Step 4/6 使用）
    desire_relations: dict[str, list[dict]] = Field(default_factory=dict)

    # 场景配置（可选，用于销售等特定场景）
    scene_config: Any = None
    
    # 【新增】混合调度相关字段 (Phase 3.1)
    matched_scenes: Dict[str, float] = Field(default_factory=dict)  # e.g., {"sales": 0.8, "emotion": 0.6}
    primary_scene: str = ""
    secondary_scenes: List[str] = Field(default_factory=list)
    secondary_configs: Dict[str, Any] = Field(default_factory=dict)
    
    # 【新增】融合后的黑名单字典 (底线法则：取并集)
    merged_weapon_blacklist: Dict[str, List[str]] = Field(default_factory=dict)
    
    # 【新增】副场景策略指令 (混合调度 3.3C：注入到 Prompt 中)
    secondary_scene_strategy: str = ""

    # 技能 Prompt（从 SKILL.md 加载，供 Step 8 话术生成使用）
    skill_prompt: str = ""

    # 技能开关（每轮请求可单独带入，不和主系统场景混在一起）
    skill_flags: Dict[str, Any] = Field(default_factory=dict)

    # 提取失败计数（阶段三：熔断器）
    _extract_failure_count: int = 0
    _extract_disabled: bool = False

    # 输出（最终生成的话术）
    output: str = ""
    output_layers: dict[str, Any] = Field(default_factory=dict)

    # 回复模式：ordinary=普通模式，deep=深度模式
    response_mode: str = "ordinary"
    response_mode_reason: str = ""

    # 主任务：contain=先接住 clarify=先理清 advance=先推进 reflect=先复盘
    dialogue_task: str = "clarify"
    dialogue_task_reason: str = ""

    # 短句模式（用于“短输入也走动态链路”）
    short_utterance: bool = False
    info_density_low: bool = False
    short_utterance_reason: str = ""

    # 身份/情境识别（用于更贴身的动态代入）
    identity_hint: str = "未识别"
    identity_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    situation_hint: str = "未识别"
    situation_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    management_sub_intent: str = ""  # diagnose / action_request / upward_report / roi_justification / change_fatigue / cross_team_alignment
    management_sub_intent_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sales_sub_intent: str = ""  # diagnose / delay_followup / price_objection / switch_defense / soft_agreement
    sales_sub_intent_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    negotiation_sub_intent: str = ""  # diagnose / next_step_close / payment_term / soft_agreement
    negotiation_sub_intent_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    emotion_sub_intent: str = ""  # diagnose / accusation_repair / low_energy_support / somatic_relief / failure_containment
    emotion_sub_intent_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    # P1-6: 情境轴 — 阶段
    situation_stage: str = "未识别"  # 破冰 / 探索 / 推进 / 收口 / 修复 / 僵持

    # 信息不足时的温和引导状态（避免反复盘问）
    guidance_needed: bool = False
    guidance_focus: str = ""  # identity | situation | both | ""
    guidance_prompt: str = ""
    guidance_cooldown: int = 0

    def add_history(self, role: str, content: str):
        """添加历史记录（带滑动窗口，保留前3条+最近97条）"""
        from datetime import datetime
        self.history.append(HistoryItem(
            role=role,
            content=content,
            timestamp=datetime.now().isoformat()
        ))
        # 滑动窗口：保留前3条（建立对话基线）+ 最近97条
        MAX_HISTORY = 100
        if len(self.history) > MAX_HISTORY:
            # 保留前3条 + 最后97条
            self.history = self.history[:3] + self.history[-(MAX_HISTORY-3):]

    def reset_strategy(self):
        """重置策略状态（武器计数保留为会话级持久）"""
        self.current_strategy = CurrentStrategy()

    def get_weapon_count(self, weapon_name: str) -> int:
        """获取武器使用次数"""
        return self.weapon_usage_count.get(weapon_name, 0)

    def increment_weapon(self, weapon_name: str):
        """增加武器使用次数"""
        current = self.weapon_usage_count.get(weapon_name, 0)
        self.weapon_usage_count[weapon_name] = current + 1

    def decay_weapon_counts(self):
        """武器使用计数衰减（每 N 轮调用一次，防止老武器被永久锁定）"""
        for name in list(self.weapon_usage_count.keys()):
            self.weapon_usage_count[name] = max(0, self.weapon_usage_count[name] - 1)
            if self.weapon_usage_count[name] == 0:
                del self.weapon_usage_count[name]

    def update_energy_allocation(self, mode: str):
        """根据模式更新能量分配（24-能量系统模块）"""
        if mode == "A":
            self.self_state.energy_allocation.inner = 0.7
            self.self_state.energy_allocation.outer = 0.2
            self.self_state.energy_allocation.environment = 0.1
        elif mode == "B":
            self.self_state.energy_allocation.inner = 0.4
            self.self_state.energy_allocation.outer = 0.3
            self.self_state.energy_allocation.environment = 0.3
        elif mode == "C":
            self.self_state.energy_allocation.inner = 0.5
            self.self_state.energy_allocation.outer = 0.4
            self.self_state.energy_allocation.environment = 0.1
