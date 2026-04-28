"""
Human-OS Engine - 记忆层（轻量级实现）

提供用户级长期记忆和短期记忆增强。

当前实现：
- 短期记忆：Redis 会话级存储（已有）
- 长期记忆：本地 JSON 文件存储 + 关键词检索
- 用户画像：结构化字段存储

后续可升级：
- 向量数据库（ChromaDB/Qdrant）实现语义检索
- Mem0 集成实现自动画像提取
"""

import json
import os
import re
import time
import atexit
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

from llm.nvidia_client import invoke_standard
from utils.file_lock import safe_json_read, safe_json_write
from utils.types import to_safe_storage_key

# ===== ChromaDB 向量检索 =====

_chroma_client = None
_chroma_collections = {}
_chroma_init_lock = None


def _ensure_chroma_client():
    """初始化 Chroma 客户端（线程安全）。"""
    global _chroma_client, _chroma_init_lock
    if _chroma_client is not None:
        return _chroma_client
    if _chroma_init_lock is None:
        import threading
        _chroma_init_lock = threading.Lock()
    with _chroma_init_lock:
        if _chroma_client is None:
            import chromadb
            _chroma_client = chromadb.PersistentClient(path="data/vector_memory")
    return _chroma_client


def _get_chroma_lock():
    global _chroma_init_lock
    if _chroma_init_lock is None:
        import threading
        _chroma_init_lock = threading.Lock()
    return _chroma_init_lock

def _get_chroma_collection(user_id: str):
    """获取用户的向量集合（懒加载）"""
    global _chroma_collections
    
    if user_id in _chroma_collections:
        return _chroma_collections[user_id]
    
    chroma_client = _ensure_chroma_client()
    
    # 集合名使用 user_id（ChromaDB 限制集合名只能包含字母数字下划线和连字符）
    safe_id = to_safe_storage_key(user_id, prefix="mem").replace("-", "_")
    collection = chroma_client.get_or_create_collection(
        name=f"memories_{safe_id}",
        metadata={"hnsw:space": "cosine"}
    )
    _chroma_collections[user_id] = collection
    return collection


def shutdown_memory_runtime(clear_system_cache: bool = True) -> bool:
    """释放记忆层全局运行时，避免测试和进程退出时遗留 SQLite 连接。"""
    global _chroma_client, _chroma_collections, _session_memory, _memory_manager

    with _get_chroma_lock():
        client = _chroma_client
        _chroma_client = None
        _chroma_collections = {}

    _session_memory = None
    _memory_manager = None

    if client is None:
        return True

    try:
        system = getattr(client, "_system", None)
    except Exception:
        system = None

    stopped = False
    stop = getattr(system, "stop", None)
    if callable(stop):
        try:
            stop()
            stopped = True
        except Exception:
            stopped = False

    reset_state = getattr(system, "reset_state", None)
    if callable(reset_state):
        try:
            reset_state()
        except Exception:
            pass

    if clear_system_cache:
        try:
            clear_cache = getattr(client, "clear_system_cache", None)
            if callable(clear_cache):
                clear_cache()
        except Exception:
            pass

    return stopped or client is not None


# ===== 数据结构 =====

@dataclass
class Memory:
    """单条记忆"""
    content: str
    timestamp: float = 0.0
    memory_type: str = "conversation"  # conversation/fact/event/profile
    metadata: dict[str, Any] = field(default_factory=dict)
    importance: float = 0.5  # 重要性 0-1

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()


@dataclass
class MemoryWriteEvent:
    """记忆写入事件（用于可观测性）"""
    user_id: str
    status: str  # stored / skipped
    reason: str
    memory_type: str
    bucket: str
    importance: float
    content_preview: str
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()


@dataclass
class UserProfile:
    """用户画像"""
    user_id: str
    name: str = ""
    occupation: str = ""
    preferences: list[str] = field(default_factory=list)
    key_events: list[str] = field(default_factory=list)
    emotion_patterns: dict[str, float] = field(default_factory=dict)  # 情绪模式统计
    desire_patterns: dict[str, float] = field(default_factory=dict)   # 欲望模式统计
    updated_at: float = 0.0


@dataclass
class SessionNote:
    """会话笔记（本轮重要决策的结构化记录）"""
    round_num: int
    note_type: str  # mode_switch / corrective_right / resistance / collapse / upgrade / trust_change
    content: str  # 一句话描述发生了什么
    detail: dict[str, Any] = field(default_factory=dict)  # 结构化细节
    timestamp: float = 0.0

    def __post_init__(self):
        if self.timestamp == 0:
            self.timestamp = time.time()


class SessionMemory:
    """
    会话级记忆管理器

    存储单次会话中的重要决策笔记，供下一轮参考。
    与长期记忆（MemoryManager）分离：会话结束后可丢弃。
    """

    def __init__(self, storage_dir: str = "data/sessions"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._notes: dict[str, list[SessionNote]] = {}  # session_id -> notes

    def _get_session_dir(self, session_id: str) -> Path:
        session_dir = self.storage_dir / to_safe_storage_key(session_id, prefix="session")
        session_dir.mkdir(exist_ok=True)
        return session_dir

    def load_session(self, session_id: str):
        """加载已有会话笔记（安全读取）"""
        notes_file = self._get_session_dir(session_id) / "notes.json"
        if notes_file.exists():
            data = safe_json_read(str(notes_file), [])
            self._notes[session_id] = [SessionNote(**n) for n in data]

    def add_note(
        self,
        session_id: str,
        round_num: int,
        note_type: str,
        content: str,
        detail: dict | None = None,
    ):
        """添加一条会话笔记"""
        if session_id not in self._notes:
            self._notes[session_id] = []

        note = SessionNote(
            round_num=round_num,
            note_type=note_type,
            content=content,
            detail=detail or {},
        )
        self._notes[session_id].append(note)

        # 持久化
        self._save_session(session_id)

    def get_recent_notes(self, session_id: str, limit: int = 5) -> list[SessionNote]:
        """获取最近的会话笔记"""
        if session_id not in self._notes:
            return []
        return self._notes[session_id][-limit:]

    def get_note_stats(self, session_id: str) -> dict[str, int]:
        """返回会话笔记数量和估算字符数。"""
        if session_id not in self._notes:
            self.load_session(session_id)
        notes = self._notes.get(session_id, [])
        chars = sum(len(getattr(note, "content", "") or "") for note in notes)
        return {"count": len(notes), "chars": chars}

    def get_context_for_llm(self, session_id: str, limit: int = 5) -> str:
        """生成会话笔记上下文（供 Prompt 注入）"""
        notes = self.get_recent_notes(session_id, limit=max(1, limit))
        if not notes:
            return ""

        lines = ["【本轮重要决策】"]

        world_state_notes = [n for n in notes if n.note_type == "world_state"]
        state_evolution_notes = [n for n in notes if n.note_type == "state_evolution"]
        relationship_notes = [n for n in notes if n.note_type == "relationship_state"]
        action_loop_notes = [n for n in notes if n.note_type == "action_loop"]
        closure_notes = [n for n in notes if n.note_type == "closure"]
        if state_evolution_notes:
            lines.append("【状态演化】")
            lines.append(f"- {state_evolution_notes[-1].content}")

        if world_state_notes:
            lines.append("【局面状态】")
            lines.append(f"- {world_state_notes[-1].content}")

        if action_loop_notes:
            lines.append("【动作闭环】")
            lines.append(f"- {action_loop_notes[-1].content}")

        if relationship_notes or closure_notes:
            lines.append("【关系闭环摘要】")
            if relationship_notes:
                lines.append(f"- 关系状态: {relationship_notes[-1].content}")
            if closure_notes:
                latest_closure = closure_notes[-1].content
                lines.append(f"- 闭环结果: {latest_closure}")

                next_step_markers = ["下一步", "明天", "跟进", "对齐", "回看", "继续", "再聊", "确认"]
                next_step_hint = ""
                for marker in next_step_markers:
                    idx = latest_closure.find(marker)
                    if idx >= 0:
                        next_step_hint = latest_closure[max(0, idx - 4): idx + 16].strip(" ，。！？：:")
                        break
                if next_step_hint:
                    lines.append(f"【下一轮接话点】")
                    lines.append(f"- {next_step_hint}")

        for n in notes:
            lines.append(f"- 第{n.round_num}轮 [{n.note_type}]: {n.content}")

        return "\n".join(lines)

    def _save_session(self, session_id: str):
        """持久化会话笔记（安全写入）"""
        if session_id not in self._notes:
            return
        notes_file = self._get_session_dir(session_id) / "notes.json"
        safe_json_write(str(notes_file), [asdict(n) for n in self._notes[session_id]])


# ===== 长期记忆管理器 =====

class MemoryManager:
    """
    用户级长期记忆管理器

    存储跨会话的记忆（事实、偏好、模式），持久化到 JSON 文件。
    """

    def __init__(self, storage_dir: str = "data/memory"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._memories: dict[str, list[Memory]] = {}
        self._profiles: dict[str, UserProfile] = {}
        self._write_events: dict[str, list[MemoryWriteEvent]] = {}
        self._write_event_limit = 200
        # 长期记忆写入防抖参数
        self._min_importance_threshold = 0.15
        self._duplicate_check_window = 20

    @staticmethod
    def _normalize_memory_text(content: str) -> str:
        """归一化记忆文本，便于做重复检测。"""
        return " ".join((content or "").strip().lower().split())

    @staticmethod
    def _bucket_label(bucket: str) -> str:
        """把内部分类转成更好读的中文标题。"""
        return {
            "profile": "用户画像",
            "preference": "偏好记忆",
            "fact": "事实记忆",
            "decision": "决策记忆",
            "strategy": "策略记忆",
            "failure": "失败记忆",
            "experience": "经验记忆",
            "conversation": "对话记忆",
            "other": "其他记忆",
        }.get(bucket, "其他记忆")

    def _infer_memory_bucket(self, memory: Memory) -> str:
        """
        给单条记忆分一个更适合展示和检索的桶。

        这里不做重模型判断，只做轻量归类，目标是让上下文更清楚：
        画像/偏好/事实/决策/经验/对话，后续节点一眼能读懂。
        """
        memory_type = (memory.memory_type or "").strip().lower()
        content = self._normalize_memory_text(memory.content)

        metadata_bucket = (memory.metadata or {}).get("bucket")
        if isinstance(metadata_bucket, str) and metadata_bucket.strip():
            return metadata_bucket.strip().lower()

        if memory_type in {"profile", "identity"}:
            return "profile"
        if memory_type in {"preference"}:
            return "preference"
        if memory_type in {"decision"}:
            return "decision"
        if memory_type in {"strategy"}:
            return "strategy"
        if memory_type in {"failure"}:
            return "failure"
        if memory_type in {"experience", "strategy", "failure"}:
            return "experience"
        if memory_type in {"fact", "event", "relation"}:
            return "fact"

        if memory_type == "conversation":
            if any(token in content for token in ("喜欢", "偏好", "更想", "不喜欢", "习惯", "倾向")):
                return "preference"
            if any(token in content for token in ("决定", "选择", "定了", "同意", "拒绝", "最后")):
                return "decision"
            if any(token in content for token in ("策略", "打法", "连招", "模板", "路径")):
                return "strategy"
            if any(token in content for token in ("失败码", "失败经验", "踩坑", "回退", "教训")):
                return "failure"
            if any(token in content for token in ("失败", "回退", "报错", "卡住", "踩坑", "经验", "教训")):
                return "experience"
            if any(token in content for token in ("职业", "身份", "背景", "老板", "团队", "公司", "关系")):
                return "fact"
            return "conversation"

        return "other"

    def _group_memories_by_bucket(self, memories: list[Memory]) -> dict[str, list[Memory]]:
        """按结构化桶分组记忆。"""
        grouped: dict[str, list[Memory]] = {
            "profile": [],
            "preference": [],
            "fact": [],
            "decision": [],
            "strategy": [],
            "failure": [],
            "experience": [],
            "conversation": [],
            "other": [],
        }
        for memory in memories:
            bucket = self._infer_memory_bucket(memory)
            grouped.setdefault(bucket, []).append(memory)
        return grouped

    @staticmethod
    def _format_memory_lines(memories: list[Memory], limit: int = 3) -> list[str]:
        """把记忆列表整理成便于展示的短行。"""
        lines: list[str] = []
        for i, memory in enumerate(memories[:limit], 1):
            snippet = memory.content[:100].replace("\n", " ")
            lines.append(f"{i}. {snippet}")
        return lines

    def _build_structured_memory_snapshot(
        self,
        user_id: str,
        current_input: str,
        context=None,
        related_limit: int = 3,
        recent_limit: int = 3,
    ) -> dict[str, Any]:
        """构建结构化记忆快照，供统一上下文和调试使用。"""
        snapshot: dict[str, Any] = {
            "profile": {},
            "current_state": {},
            "session_notes": "",
            "related": {},
            "recent": {},
            "experience": [],
            "experience_digest": [],
        }

        profile = self.get_profile(user_id)
        if profile:
            snapshot["profile"] = {
                "occupation": profile.occupation,
                "preferences": profile.preferences[:3],
                "top_emotions": sorted(
                    profile.emotion_patterns.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:2],
                "top_desires": sorted(
                    profile.desire_patterns.items(),
                    key=lambda x: x[1],
                    reverse=True,
                )[:2],
            }

        session_notes = get_session_memory().get_context_for_llm(user_id)
        snapshot["session_notes"] = session_notes

        if context:
            scene_id = context.scene_config.scene_id if context.scene_config else "未识别"
            goal = getattr(context.goal, "granular_goal", "") or "未识别"
            display = getattr(context.goal, "display_name", "") or ""
            mode = context.self_state.energy_mode
            trust = context.user.trust_level
            emotion = context.user.emotion
            world_state = getattr(context, "world_state", None)
            snapshot["current_state"] = {
                "scene": scene_id,
                "goal": goal,
                "display_name": display,
                "mode": mode.value if hasattr(mode, "value") else str(mode),
                "trust": trust.value if hasattr(trust, "value") else str(trust),
                "emotion": emotion.type.value if hasattr(emotion.type, "value") else str(emotion.type),
                "emotion_intensity": getattr(emotion, "intensity", 0.0),
                "stage": getattr(world_state, "situation_stage", "") if world_state else "",
                "risk": getattr(world_state, "risk_level", "") if world_state else "",
                "tension": getattr(world_state, "tension_level", "") if world_state else "",
                "progress": getattr(world_state, "progress_state", "") if world_state else "",
                "commitment": getattr(world_state, "commitment_state", "") if world_state else "",
                "action_loop": getattr(world_state, "action_loop_state", "") if world_state else "",
                "next_turn_focus": getattr(world_state, "next_turn_focus", "") if world_state else "",
            }

        related_memories = self.search_memory(user_id, current_input, limit=max(1, related_limit))
        grouped_related = self._group_memories_by_bucket(related_memories)
        snapshot["related"] = {
            bucket: self._format_memory_lines(items, limit=related_limit)
            for bucket, items in grouped_related.items()
            if items
        }

        grouped_recent: dict[str, list[Memory]] = {}
        if recent_limit > 0:
            recent_memories = self.get_recent_memories(user_id, limit=max(1, recent_limit))
            grouped_recent = self._group_memories_by_bucket(recent_memories)
            snapshot["recent"] = {
                bucket: self._format_memory_lines(items, limit=recent_limit)
                for bucket, items in grouped_recent.items()
                if items
            }

            for memory in recent_memories:
                if self._infer_memory_bucket(memory) in {"experience", "strategy", "failure"}:
                    snapshot["experience"].append(memory.content[:100].replace("\n", " "))

        # 经验索引：把“失败/策略/决策”压成短提示，供策略层快速读取。
        def _first_line(grouped: dict[str, list[Memory]], bucket: str) -> str:
            items = grouped.get(bucket) or []
            if not items:
                return ""
            return items[0].content[:100].replace("\n", " ").strip()

        failure_hint = _first_line(grouped_related, "failure") or _first_line(grouped_recent, "failure")
        strategy_hint = _first_line(grouped_related, "strategy") or _first_line(grouped_recent, "strategy")
        decision_hint = _first_line(grouped_related, "decision") or _first_line(grouped_recent, "decision")
        experience_hint = _first_line(grouped_related, "experience") or _first_line(grouped_recent, "experience")

        digest_lines: list[str] = []
        if failure_hint:
            digest_lines.append(f"失败避坑: {failure_hint}")
        if strategy_hint:
            digest_lines.append(f"策略参考: {strategy_hint}")
        if decision_hint:
            digest_lines.append(f"决策线索: {decision_hint}")
        if not digest_lines and experience_hint:
            digest_lines.append(f"经验线索: {experience_hint}")
        snapshot["experience_digest"] = digest_lines[:3]

        return snapshot

    def _format_structured_memory_snapshot(self, snapshot: dict[str, Any]) -> str:
        """把结构化记忆快照转成适合注入 LLM 的文本。"""
        parts: list[str] = []

        profile = snapshot.get("profile") or {}
        if profile:
            profile_lines = []
            occupation = profile.get("occupation")
            preferences = profile.get("preferences") or []
            top_emotions = profile.get("top_emotions") or []
            top_desires = profile.get("top_desires") or []
            if occupation:
                profile_lines.append(f"职业: {occupation}")
            if preferences:
                profile_lines.append(f"偏好: {', '.join(preferences[:3])}")
            if top_emotions:
                profile_lines.append(
                    "常见情绪: " + ", ".join(f"{name}" for name, _ in top_emotions[:2])
                )
            if top_desires:
                profile_lines.append(
                    "常见欲望: " + ", ".join(f"{name}" for name, _ in top_desires[:2])
                )
            if profile_lines:
                parts.append("【用户画像】\n" + " | ".join(profile_lines))

        session_notes = snapshot.get("session_notes") or ""
        if session_notes:
            parts.append(session_notes)

        current_state = snapshot.get("current_state") or {}
        if current_state:
            state_lines = []
            scene = current_state.get("scene")
            goal = current_state.get("goal")
            display_name = current_state.get("display_name")
            mode = current_state.get("mode")
            trust = current_state.get("trust")
            emotion = current_state.get("emotion")
            emotion_intensity = current_state.get("emotion_intensity")
            stage = current_state.get("stage")
            risk = current_state.get("risk")
            tension = current_state.get("tension")
            progress = current_state.get("progress")
            commitment = current_state.get("commitment")
            action_loop = current_state.get("action_loop")
            next_turn_focus = current_state.get("next_turn_focus")
            if scene:
                state_lines.append(f"场景: {scene}")
            if goal:
                state_lines.append(f"目标: {goal}" + (f" ({display_name})" if display_name else ""))
            if stage:
                state_lines.append(f"阶段: {stage}")
            if mode:
                state_lines.append(f"模式: {mode}")
            if trust:
                state_lines.append(f"信任: {trust}")
            if emotion:
                state_lines.append(f"情绪: {emotion}({emotion_intensity:.1f})")
            if risk:
                state_lines.append(f"风险: {risk}")
            if tension:
                state_lines.append(f"张力: {tension}")
            if progress:
                state_lines.append(f"推进: {progress}")
            if commitment:
                state_lines.append(f"承诺: {commitment}")
            if action_loop:
                state_lines.append(f"动作: {action_loop}")
            if state_lines:
                parts.append("【当前状态】\n" + " | ".join(state_lines))
            if next_turn_focus:
                parts.append("【下一轮焦点】\n" + next_turn_focus)

        experience = snapshot.get("experience") or []
        if experience:
            experience_lines = ["【经验提示】"]
            for item in experience[:3]:
                experience_lines.append(f"  - {item}")
            parts.append("\n".join(experience_lines))

        experience_digest = snapshot.get("experience_digest") or []
        if experience_digest:
            digest_lines = ["【经验索引】"]
            for line in experience_digest[:3]:
                digest_lines.append(f"  - {line}")
            parts.append("\n".join(digest_lines))

        related = snapshot.get("related") or {}
        if related:
            related_lines = ["【相关记忆】"]
            for bucket in ("preference", "decision", "strategy", "failure", "fact", "experience", "conversation", "other"):
                items = related.get(bucket)
                if not items:
                    continue
                related_lines.append(f"{self._bucket_label(bucket)}:")
                for line in items:
                    related_lines.append(f"  - {line}")
            parts.append("\n".join(related_lines))

        recent = snapshot.get("recent") or {}
        if recent:
            recent_lines = ["【最近记忆】"]
            for bucket in ("failure", "strategy", "experience", "decision", "preference", "fact", "conversation", "other"):
                items = recent.get(bucket)
                if not items:
                    continue
                recent_lines.append(f"{self._bucket_label(bucket)}:")
                for line in items:
                    recent_lines.append(f"  - {line}")
            parts.append("\n".join(recent_lines))

        return "\n\n".join(parts) if parts else ""

    def _is_duplicate_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str,
    ) -> bool:
        """判断近期是否已经写过同类型同内容记忆。"""
        existing = self._memories.get(user_id, [])
        if not existing:
            return False

        target = self._normalize_memory_text(content)
        if not target:
            return True

        recent = existing[-self._duplicate_check_window :]
        for m in recent:
            if m.memory_type != memory_type:
                continue
            if self._normalize_memory_text(m.content) == target:
                return True
        return False

    def _get_user_dir(self, user_id: str) -> Path:
        user_dir = self.storage_dir / to_safe_storage_key(user_id, prefix="user")
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _load_user_data(self, user_id: str):
        """懒加载用户数据"""
        if user_id in self._memories:
            return

        user_dir = self._get_user_dir(user_id)

        # 加载记忆
        memories_file = user_dir / "memories.json"
        if memories_file.exists():
            data = safe_json_read(str(memories_file), [])
            self._memories[user_id] = [Memory(**m) for m in data]
        else:
            self._memories[user_id] = []

        # 加载画像
        profile_file = user_dir / "profile.json"
        if profile_file.exists():
            data = safe_json_read(str(profile_file))
            if data:
                self._profiles[user_id] = UserProfile(**data)

    def _save_user_data(self, user_id: str):
        """保存用户数据（仅在记忆数量达到阈值时保存）"""
        if user_id in self._memories and len(self._memories[user_id]) % 10 == 0:
            user_dir = self._get_user_dir(user_id)
            memories_file = user_dir / "memories.json"
            safe_json_write(str(memories_file), [asdict(m) for m in self._memories[user_id]])

        if user_id in self._profiles:
            user_dir = self._get_user_dir(user_id)
            profile_file = user_dir / "profile.json"
            safe_json_write(str(profile_file), asdict(self._profiles[user_id]))

    def _record_write_event(
        self,
        user_id: str,
        status: str,
        reason: str,
        memory_type: str,
        importance: float,
        content: str,
        bucket: str | None = None,
    ) -> dict[str, Any]:
        """记录写入事件并返回结构化结果。"""
        preview = (content or "").strip().replace("\n", " ")[:80]
        resolved_bucket = (bucket or "").strip().lower()
        if not resolved_bucket:
            probe = Memory(content=content, memory_type=memory_type, metadata={})
            resolved_bucket = self._infer_memory_bucket(probe)
        event = MemoryWriteEvent(
            user_id=user_id,
            status=status,
            reason=reason,
            memory_type=memory_type,
            bucket=resolved_bucket,
            importance=importance,
            content_preview=preview,
        )
        events = self._write_events.setdefault(user_id, [])
        events.append(event)
        if len(events) > self._write_event_limit:
            self._write_events[user_id] = events[-self._write_event_limit :]
        return asdict(event)

    def get_recent_write_events(self, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
        """获取最近写入事件。"""
        if user_id not in self._write_events:
            return []
        return [asdict(e) for e in self._write_events[user_id][-max(1, limit) :]]

    @staticmethod
    def _build_health_signal(
        stored: int,
        skipped: int,
        by_bucket: dict[str, int],
        skip_reasons: dict[str, int],
    ) -> dict[str, Any]:
        """
        基于写入分布给一个可读的健康信号。

        目标不是替代人工判断，而是给日检一个“先看哪里”的快速提示。
        """
        total = max(1, int(stored) + int(skipped))
        skip_ratio = skipped / total
        conversation_ratio = by_bucket.get("conversation", 0) / total
        decision_experience_ratio = (
            by_bucket.get("decision", 0)
            + by_bucket.get("strategy", 0)
            + by_bucket.get("failure", 0)
            + by_bucket.get("experience", 0)
        ) / total
        low_importance_ratio = skip_reasons.get("low_importance", 0) / max(1, skipped)

        status = "healthy"
        signals: list[str] = []

        if stored == 0 and skipped > 0:
            status = "blocked"
            signals.append("没有写入成功，先看阈值和去重门限")
        elif skip_ratio >= 0.85 and low_importance_ratio >= 0.6:
            status = "strict"
            signals.append("过滤偏严，low_importance 占比高")
        elif skip_ratio <= 0.05 and conversation_ratio >= 0.75 and total >= 6:
            status = "noisy"
            signals.append("过滤偏松，对话型记忆占比过高")
        elif conversation_ratio >= 0.75 and decision_experience_ratio <= 0.1 and total >= 6:
            status = "shallow"
            signals.append("经验沉淀偏浅，decision/experience 占比偏低")
        else:
            signals.append("分布正常")

        return {
            "status": status,
            "signals": signals,
            "metrics": {
                "skip_ratio": round(skip_ratio, 3),
                "conversation_ratio": round(conversation_ratio, 3),
                "decision_experience_ratio": round(decision_experience_ratio, 3),
                "low_importance_ratio": round(low_importance_ratio, 3),
            },
        }

    def get_write_summary(self, user_id: str, limit: int = 50) -> dict[str, Any]:
        """获取写入汇总（用于 debug 面板/接口）。"""
        events = self.get_recent_write_events(user_id, limit=limit)
        summary = {
            "window_size": len(events),
            "stored": 0,
            "skipped": 0,
            "skip_reasons": {},
            "by_type": {},
            "by_bucket": {},
            "latest": events[-1] if events else None,
            "health": {},
        }
        for e in events:
            status = e.get("status", "unknown")
            summary[status] = summary.get(status, 0) + 1
            mtype = e.get("memory_type", "unknown")
            summary["by_type"][mtype] = summary["by_type"].get(mtype, 0) + 1
            bucket = e.get("bucket", "other")
            summary["by_bucket"][bucket] = summary["by_bucket"].get(bucket, 0) + 1
            if status == "skipped":
                reason = e.get("reason", "unknown")
                summary["skip_reasons"][reason] = summary["skip_reasons"].get(reason, 0) + 1
        summary["health"] = self._build_health_signal(
            stored=summary.get("stored", 0),
            skipped=summary.get("skipped", 0),
            by_bucket=summary.get("by_bucket", {}),
            skip_reasons=summary.get("skip_reasons", {}),
        )
        return summary

    def reset_write_events(self):
        """清空写入事件（用于观测窗口重置）。"""
        self._write_events = {}

    def get_global_write_summary(self, limit_per_user: int = 50) -> dict[str, Any]:
        """获取全局写入汇总（跨会话/跨用户）。"""
        limit = max(1, int(limit_per_user))
        global_summary = {
            "user_count": 0,
            "total_events": 0,
            "stored": 0,
            "skipped": 0,
            "skip_reasons": {},
            "by_type": {},
            "by_bucket": {},
            "top_sessions": [],
            "health": {},
        }
        session_event_counts: list[tuple[str, int]] = []

        for user_id in list(self._write_events.keys()):
            events = self.get_recent_write_events(user_id, limit=limit)
            if not events:
                continue
            global_summary["user_count"] += 1
            global_summary["total_events"] += len(events)
            session_event_counts.append((user_id, len(events)))
            for e in events:
                status = e.get("status", "unknown")
                global_summary[status] = global_summary.get(status, 0) + 1
                mtype = e.get("memory_type", "unknown")
                global_summary["by_type"][mtype] = global_summary["by_type"].get(mtype, 0) + 1
                bucket = e.get("bucket", "other")
                global_summary["by_bucket"][bucket] = global_summary["by_bucket"].get(bucket, 0) + 1
                if status == "skipped":
                    reason = e.get("reason", "unknown")
                    global_summary["skip_reasons"][reason] = global_summary["skip_reasons"].get(reason, 0) + 1

        session_event_counts.sort(key=lambda item: item[1], reverse=True)
        global_summary["top_sessions"] = [
            {"session_id": sid, "event_count": count}
            for sid, count in session_event_counts[:10]
        ]
        global_summary["health"] = self._build_health_signal(
            stored=global_summary.get("stored", 0),
            skipped=global_summary.get("skipped", 0),
            by_bucket=global_summary.get("by_bucket", {}),
            skip_reasons=global_summary.get("skip_reasons", {}),
        )
        return global_summary

    def add_memory(
        self,
        user_id: str,
        content: str,
        memory_type: str = "conversation",
        metadata: dict | None = None,
        importance: float = 0.5,
    ):
        """添加记忆"""
        self._load_user_data(user_id)

        content = (content or "").strip()
        if not content:
            return self._record_write_event(
                user_id=user_id,
                status="skipped",
                reason="empty_content",
                memory_type=memory_type,
                importance=0.0,
                content=content,
            )

        importance = max(0.0, min(1.0, float(importance)))
        if importance < self._min_importance_threshold:
            return self._record_write_event(
                user_id=user_id,
                status="skipped",
                reason="low_importance",
                memory_type=memory_type,
                importance=importance,
                content=content,
            )

        if self._is_duplicate_memory(user_id, content, memory_type):
            return self._record_write_event(
                user_id=user_id,
                status="skipped",
                reason="duplicate_recent",
                memory_type=memory_type,
                importance=importance,
                content=content,
            )

        if user_id not in self._memories:
            self._memories[user_id] = []

        base_metadata = dict(metadata or {})
        memory = Memory(
            content=content,
            memory_type=memory_type,
            metadata=base_metadata,
            importance=importance,
        )
        bucket = self._infer_memory_bucket(memory)
        memory.metadata["bucket"] = bucket

        self._memories[user_id].append(memory)

        # 同步索引到向量数据库
        try:
            collection = _get_chroma_collection(user_id)
            doc_id = str(len(self._memories[user_id]) - 1)
            collection.add(
                ids=[doc_id],
                documents=[content],
                metadatas=[{
                    "type": memory_type,
                    "bucket": bucket,
                    "importance": importance,
                    "timestamp": memory.timestamp,
                }],
            )
        except Exception:
            pass  # 向量索引失败不影响主流程

        # 限制记忆数量（保留最重要的 100 条）
        if len(self._memories[user_id]) > 100:
            self._memories[user_id].sort(key=lambda m: m.importance, reverse=True)
            self._memories[user_id] = self._memories[user_id][:100]

        self._save_user_data(user_id)
        return self._record_write_event(
            user_id=user_id,
            status="stored",
            reason="ok",
            memory_type=memory_type,
            importance=importance,
            content=content,
            bucket=bucket,
        )

    def search_memory(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        memory_type: str | None = None,
    ) -> list[Memory]:
        """检索记忆（向量语义检索 + 关键词 fallback）。"""
        self._load_user_data(user_id)
        if user_id not in self._memories:
            return []

        memories = self._memories[user_id]
        if memory_type:
            memories = [m for m in memories if m.memory_type == memory_type]

        if not memories:
            return []

        # 1. 优先使用向量语义检索
        try:
            vector_results = self._search_memory_vector(user_id, query, memories, limit)
            if vector_results:
                return vector_results
        except Exception:
            pass

        # 2. 关键词匹配 fallback（避免额外 LLM 延迟叠加）
        return self._search_memory_keywords(query, memories, limit)

    def _build_memory_manifest(self, memories: list[Memory]) -> str:
        """构建记忆清单（供 LLM 选择）"""
        lines = []
        for i, m in enumerate(memories):
            desc = m.content[:40].replace("\n", " ")
            lines.append(f"[{i}] ({m.memory_type}) {desc}")
        return "\n".join(lines)

    def _search_memory_llm(
        self,
        user_id: str,
        query: str,
        memories: list[Memory],
        limit: int,
    ) -> list[Memory]:
        """LLM 相关性选择"""
        from llm.nvidia_client import invoke_fast
        from utils.types import sanitize_for_prompt
        query = sanitize_for_prompt(query, max_length=500)

        manifest = self._build_memory_manifest(memories)

        system_prompt = """你是记忆选择助手。根据用户当前输入，从记忆清单中选择最相关的记忆条目。

规则：
1. 选择最相关的 3-5 条记忆
2. 返回 JSON 数组，包含选中记忆的索引号
3. 如果没有相关记忆，返回空数组 []
4. 优先选择：与当前话题直接相关的、包含用户偏好的、包含重要决策的"""

        user_prompt = f"""当前用户输入：{query}

记忆清单：
{manifest}

请返回最相关记忆的索引号 JSON 数组（如 [0, 3, 5]）。"""

        response = invoke_fast(user_prompt, system_prompt)

        response = response.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        indices = json.loads(response)

        if not isinstance(indices, list):
            return []

        selected = []
        for idx in indices:
            if isinstance(idx, int) and 0 <= idx < len(memories):
                selected.append(memories[idx])

        return selected[:limit]

    def _search_memory_vector(
        self,
        user_id: str,
        query: str,
        memories: list[Memory],
        limit: int,
    ) -> list[Memory] | None:
        """向量语义检索（ChromaDB）"""
        collection = _get_chroma_collection(user_id)
        
        # 如果集合为空，先索引所有记忆
        if collection.count() == 0:
            self._index_memories_to_vector(user_id, memories)
        
        # 向量查询
        results = collection.query(
            query_texts=[query],
            n_results=min(limit * 2, collection.count()),
            include=["metadatas", "distances"]
        )
        
        if not results or not results.get("ids") or not results["ids"][0]:
            return None
        
        # 根据 ID 映射回 Memory 对象
        memory_map = {str(i): m for i, m in enumerate(memories)}
        selected = []
        for doc_id in results["ids"][0]:
            if doc_id in memory_map:
                selected.append(memory_map[doc_id])
        
        return selected[:limit] if selected else None

    def _index_memories_to_vector(self, user_id: str, memories: list[Memory]):
        """将记忆索引到向量数据库"""
        collection = _get_chroma_collection(user_id)
        
        ids = [str(i) for i in range(len(memories))]
        documents = [m.content for m in memories]
        metadatas = [
            {
                "type": m.memory_type,
                "importance": m.importance,
                "timestamp": m.timestamp,
            }
            for m in memories
        ]
        
        # ChromaDB 批量添加限制
        batch_size = 100
        for i in range(0, len(ids), batch_size):
            collection.add(
                ids=ids[i:i+batch_size],
                documents=documents[i:i+batch_size],
                metadatas=metadatas[i:i+batch_size],
            )

    def _search_memory_keywords(
        self,
        query: str,
        memories: list[Memory],
        limit: int,
    ) -> list[Memory]:
        """关键词匹配（fallback）"""
        query_words = set(query.lower())
        scored = []

        for memory in memories:
            content_words = set(memory.content.lower())
            overlap = len(query_words & content_words)
            score = overlap * memory.importance
            if score > 0:
                scored.append((score, memory))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def get_recent_memories(
        self,
        user_id: str,
        limit: int = 10,
    ) -> list[Memory]:
        """获取最近的记忆"""
        self._load_user_data(user_id)
        if user_id not in self._memories:
            return []

        memories = sorted(
            self._memories[user_id],
            key=lambda m: m.timestamp,
            reverse=True,
        )

        return memories[:limit]

    def get_long_term_stats(self, user_id: str) -> dict[str, int]:
        """返回长期记忆数量和估算字符数。"""
        self._load_user_data(user_id)
        memories = self._memories.get(user_id, [])
        chars = sum(len(getattr(memory, "content", "") or "") for memory in memories)
        return {"count": len(memories), "chars": chars}

    # ===== 用户画像操作 =====

    def get_profile(self, user_id: str) -> UserProfile | None:
        """获取用户画像"""
        self._load_user_data(user_id)
        return self._profiles.get(user_id)

    def update_profile(
        self,
        user_id: str,
        **kwargs,
    ):
        """更新用户画像"""
        self._load_user_data(user_id)
        if user_id not in self._profiles:
            self._profiles[user_id] = UserProfile(user_id=user_id)

        profile = self._profiles[user_id]

        for key, value in kwargs.items():
            if hasattr(profile, key):
                setattr(profile, key, value)

        profile.updated_at = time.time()
        self._save_user_data(user_id)

    def update_emotion_pattern(self, user_id: str, emotion: str, intensity: float):
        """更新情绪模式统计"""
        self._load_user_data(user_id)
        if user_id not in self._profiles:
            self._profiles[user_id] = UserProfile(user_id=user_id)

        profile = self._profiles[user_id]

        if emotion in profile.emotion_patterns:
            profile.emotion_patterns[emotion] = (
                profile.emotion_patterns[emotion] * 0.7 + intensity * 0.3
            )
        else:
            profile.emotion_patterns[emotion] = intensity

        profile.updated_at = time.time()
        self._save_user_data(user_id)

    def update_desire_pattern(self, user_id: str, desire: str, weight: float):
        """更新欲望模式统计"""
        self._load_user_data(user_id)
        if user_id not in self._profiles:
            self._profiles[user_id] = UserProfile(user_id=user_id)

        profile = self._profiles[user_id]

        if desire in profile.desire_patterns:
            profile.desire_patterns[desire] = (
                profile.desire_patterns[desire] * 0.7 + weight * 0.3
            )
        else:
            profile.desire_patterns[desire] = weight

        profile.updated_at = time.time()
        self._save_user_data(user_id)

    # ===== 上下文生成 =====

    def get_context_for_llm(self, user_id: str, current_input: str) -> str:
        """
        为 LLM 生成记忆上下文

        返回格式化的记忆摘要，可注入到 Prompt 中。
        """
        snapshot = self._build_structured_memory_snapshot(
            user_id=user_id,
            current_input=current_input,
            context=None,
            related_limit=3,
            recent_limit=3,
        )
        return self._format_structured_memory_snapshot(snapshot)

    def get_unified_context(
        self,
        user_id: str,
        current_input: str,
        context=None,
        related_limit: int = 3,
        recent_limit: int = 3,
        include_experience: bool = True,
        return_meta: bool = False,
    ) -> str | tuple[str, dict[str, Any]]:
        """
        统一上下文生成（打通 5 套存储系统）

        合并：用户画像 + 当前状态 + 会话笔记 + 相关记忆 + 策略经验
        """
        snapshot = self._build_structured_memory_snapshot(
            user_id=user_id,
            current_input=current_input,
            context=context,
            related_limit=max(0, related_limit),
            recent_limit=max(0, recent_limit),
        )

        # 6. 策略经验参考（尽量前置，让经验先说话）
        if include_experience and context and getattr(context.goal, "granular_goal", None):
            try:
                from modules.L3.dynamic_strategy_engine import DynamicStrategyEngine

                engine = DynamicStrategyEngine()
                goal = context.goal.granular_goal
                emotion_type = context.user.emotion.type
                emotion_str = emotion_type.value if hasattr(emotion_type, "value") else str(emotion_type)
                experiences = engine._retrieve_experience(goal, emotion_str)
                if experiences:
                    exp_lines = []
                    for i, exp in enumerate(experiences, 1):
                        exp_lines.append(
                            f"{i}. [{exp.get('strategy', '?')}] 评分 {exp.get('score', '?')}/5 "
                            f"分析：{exp.get('analysis', '')[:80]}"
                        )
                    snapshot["experience"].extend(exp_lines)
            except Exception:
                pass  # 经验检索失败不影响主流程

        text = self._format_structured_memory_snapshot(snapshot)
        if not return_meta:
            return text

        session_notes_text = snapshot.get("session_notes") or ""
        session_note_stats = get_session_memory().get_note_stats(user_id)
        related_count = sum(len(items) for items in (snapshot.get("related") or {}).values())
        recent_count = sum(len(items) for items in (snapshot.get("recent") or {}).values())
        experience_count = len(snapshot.get("experience_digest") or [])
        memory_sources = []
        if session_notes_text:
            memory_sources.append("session_notes")
        if related_count:
            memory_sources.append("related_memory")
        if recent_count:
            memory_sources.append("recent_memory")
        if experience_count:
            memory_sources.append("experience_digest")

        meta = {
            "memory_mode": "full",
            "loaded_memory_count": related_count + recent_count + experience_count,
            "memory_sources": memory_sources,
            "unified_context_loaded": True,
            "session_note_count": session_note_stats.get("count", 0),
            "session_note_chars": len(session_notes_text),
            "related_count": related_count,
            "recent_count": recent_count,
            "experience_digest_count": experience_count,
            "unified_context_chars": len(text or ""),
        }
        return text, meta


# ===== 全局实例 =====

_session_memory: SessionMemory | None = None
_memory_manager: MemoryManager | None = None


def get_session_memory() -> SessionMemory:
    """获取会话记忆管理器单例"""
    global _session_memory
    if _session_memory is None:
        _session_memory = SessionMemory()
    return _session_memory


def get_memory_manager() -> MemoryManager:
    """获取记忆管理器单例"""
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = MemoryManager()
    return _memory_manager


def warmup_vector_store() -> bool:
    """
    后台预热向量存储，避免首个用户请求同步初始化阻塞。

    Returns:
        bool: 预热是否成功
    """
    try:
        _ensure_chroma_client()
        return True
    except Exception:
        return False


atexit.register(shutdown_memory_runtime)


# ===== 便捷函数 =====

def retrieve_memory(user_id: str, query: str, limit: int = 5) -> list[Memory]:
    """检索记忆"""
    return get_memory_manager().search_memory(user_id, query, limit)


def store_memory(
    user_id: str,
    content: str,
    memory_type: str = "conversation",
    importance: float = 0.5,
):
    """存储记忆"""
    return get_memory_manager().add_memory(
        user_id,
        content,
        memory_type=memory_type,
        importance=importance,
    )


def get_memory_write_summary(user_id: str, limit: int = 50) -> dict[str, Any]:
    """获取记忆写入汇总。"""
    return get_memory_manager().get_write_summary(user_id, limit=limit)


def get_global_memory_write_summary(limit_per_user: int = 50) -> dict[str, Any]:
    """获取全局记忆写入汇总。"""
    return get_memory_manager().get_global_write_summary(limit_per_user=limit_per_user)


def reset_memory_write_events():
    """重置记忆写入事件窗口。"""
    get_memory_manager().reset_write_events()


def get_memory_context(user_id: str, current_input: str) -> str:
    """获取记忆上下文"""
    return get_memory_manager().get_context_for_llm(user_id, current_input)


def extract_structured_memory_hints(unified_context: str, limit_per_section: int = 3) -> str:
    """
    从统一记忆里提取适合塞进 prompt 的重点提示。

    目标不是把整段上下文原样贴进去，而是让后续节点能快速看到
    用户画像、相关记忆和最近经验里最关键的几行。
    """
    if not unified_context:
        return ""

    wanted_sections = {"用户画像", "当前状态", "相关记忆", "最近记忆", "经验提示", "经验索引"}
    collected: list[str] = []
    active_section = ""
    section_counts: dict[str, int] = {name: 0 for name in wanted_sections}

    for raw_line in unified_context.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("【") and line.endswith("】"):
            active_section = line.strip("【】")
            continue

        if active_section not in wanted_sections:
            continue

        if line.endswith("：") and line.count("：") == 1:
            # 保留像“偏好记忆：”这种小标题，但不无限展开。
            collected.append(line)
            continue

        if section_counts[active_section] >= limit_per_section:
            continue

        collected.append(line)
        section_counts[active_section] += 1

    return "\n".join(collected)


def extract_world_state_hints(unified_context: str, limit: int = 4) -> str:
    """
    从统一记忆里提取“局面承接”提示。

    目标是把当前状态、局面状态、闭环和下一轮焦点压成更短的一小段，
    让输出层先看到“现在局面走到哪了”，再决定怎么接。
    """
    if not unified_context:
        return ""

    wanted_sections = {"当前状态", "局面状态", "状态演化", "动作闭环", "关系闭环摘要", "下一轮焦点"}
    collected: list[str] = []
    active_section = ""

    for raw_line in unified_context.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("【") and line.endswith("】"):
            active_section = line.strip("【】")
            continue

        if active_section not in wanted_sections:
            continue

        if line.endswith("：") and line.count("：") == 1:
            continue

        cleaned = re.sub(r"^[-*]\s*", "", line).strip()
        if not cleaned:
            continue
        if cleaned not in collected:
            collected.append(cleaned)
        if len(collected) >= max(1, limit):
            break

    return "\n".join(collected)


def extract_turn_progress_hints(unified_context: str, limit: int = 6) -> str:
    """
    把局面推进相关信息收成一个更根上的入口。

    目标不是分开看状态演化、动作闭环和当前局面，而是先拼成一条
    “这一轮怎么往前走”的短线索，让输出层少接几段分散提示。
    """
    if not unified_context:
        return ""

    wanted_sections = {
        "状态演化": "状态演化",
        "动作闭环": "动作闭环",
        "局面状态": "局面状态",
        "关系闭环摘要": "关系闭环",
        "下一轮焦点": "下一轮焦点",
        "本轮重要决策": "本轮重要决策",
    }
    section_items: dict[str, list[str]] = {name: [] for name in wanted_sections.values()}
    active_section = ""

    for raw_line in unified_context.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("【") and line.endswith("】"):
            active_section = line.strip("【】")
            continue

        if active_section not in wanted_sections:
            continue

        if line.endswith("：") and line.count("：") == 1:
            continue

        cleaned = re.sub(r"^[-*]\s*", "", line).strip()
        if not cleaned:
            continue

        bucket = wanted_sections[active_section]
        if cleaned not in section_items[bucket]:
            section_items[bucket].append(cleaned)

    ordered_buckets = ["状态演化", "动作闭环", "局面状态", "关系闭环", "下一轮焦点", "本轮重要决策"]
    collected: list[str] = []
    for bucket in ordered_buckets:
        items = section_items.get(bucket) or []
        if not items:
            continue
        collected.append(f"{bucket}: {items[0]}")
        if len(collected) >= max(1, limit):
            break

    if not collected:
        return ""
    return "【局面推进】\n- " + "\n- ".join(collected)


def extract_state_evolution_hints(unified_context: str, limit: int = 4) -> str:
    """
    从统一记忆里提取“这一轮怎么变过来”的承接提示。

    目标是把状态演化、动作闭环和关系闭环里的变化浓缩成短句，
    让下一轮先看到“刚刚发生了什么变化”，再接着往前说。
    """
    if not unified_context:
        return ""

    wanted_sections = {"状态演化", "动作闭环", "关系闭环摘要", "本轮重要决策"}
    collected: list[str] = []
    active_section = ""

    for raw_line in unified_context.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith("【") and line.endswith("】"):
            active_section = line.strip("【】")
            continue

        if active_section not in wanted_sections:
            continue

        if line.endswith("：") and line.count("：") == 1:
            continue

        cleaned = re.sub(r"^[-*]\s*", "", line).strip()
        if not cleaned:
            continue
        if cleaned not in collected:
            collected.append(cleaned)
        if len(collected) >= max(1, limit):
            break

    return "\n".join(collected)


def extract_decision_experience_hints(unified_context: str, limit: int = 4) -> str:
    """
    从统一记忆里优先提取“决策/经验”线索。

    用途：
    - 给 Step6 这种策略节点补“先做什么、别做什么”的历史依据
    - 避免策略层只看通用对话记忆，忽略关键决策和经验教训
    """
    if not unified_context:
        return ""

    lines = [line.strip() for line in unified_context.splitlines() if line.strip()]
    collected: list[str] = []
    high_priority_lines: list[str] = []
    normal_lines: list[str] = []
    active_section = ""
    include_block = False

    keyword_hits = ("决策记忆", "策略记忆", "失败记忆", "经验记忆", "经验提示", "教训", "踩坑", "回退", "先", "再", "最后")
    high_priority_hits = ("失败经验", "失败记忆", "失败码", "教训", "踩坑", "回退", "先别", "避免")

    for line in lines:
        if line.startswith("【") and line.endswith("】"):
            active_section = line.strip("【】")
            include_block = active_section in {"经验提示"}
            continue

        if "决策记忆" in line or "策略记忆" in line or "失败记忆" in line or "经验记忆" in line:
            include_block = True
            if any(k in line for k in high_priority_hits):
                if line not in high_priority_lines:
                    high_priority_lines.append(line)
            elif line not in normal_lines:
                normal_lines.append(line)
            continue

        if active_section == "经验提示":
            include_block = True

        if include_block and any(k in line for k in keyword_hits):
            if any(k in line for k in high_priority_hits):
                if line not in high_priority_lines:
                    high_priority_lines.append(line)
            elif line not in normal_lines:
                normal_lines.append(line)

    merged = high_priority_lines + normal_lines
    for line in merged[: max(1, limit)]:
        if line not in collected:
            collected.append(line)

    return "\n".join(collected)


def extract_failure_experience_hints(unified_context: str, limit: int = 2) -> str:
    """
    从统一记忆中优先提取“失败经验/避坑”线索。

    目的：
    - 让策略层先看到最近踩坑和失败码，不要被普通经验淹没
    - 给 Step6 的“先别做”提供更直接的来源
    """
    if not unified_context:
        return ""

    lines = [line.strip() for line in unified_context.splitlines() if line.strip()]
    failure_hits = ("失败经验", "失败记忆", "失败码", "踩坑", "教训", "回退", "先别", "避免")
    collected: list[str] = []

    for line in lines:
        if line.startswith("【") and line.endswith("】"):
            continue
        if any(token in line for token in failure_hits):
            if line not in collected:
                collected.append(line)
        if len(collected) >= max(1, limit):
            break

    return "\n".join(collected)


def extract_experience_digest_hints(unified_context: str, limit: int = 2) -> str:
    """
    提取“经验索引”段，给策略层快速读取。

    只拿短索引，不展开长段落，目的是让 Step6 先看到
    “失败避坑/策略参考/决策线索”。
    """
    if not unified_context:
        return ""

    lines = [line.strip() for line in unified_context.splitlines() if line.strip()]
    collected: list[str] = []
    in_digest = False
    digest_hits = ("失败避坑", "策略参考", "决策线索", "经验线索")

    for line in lines:
        if line.startswith("【") and line.endswith("】"):
            in_digest = line.strip("【】") == "经验索引"
            continue

        if not in_digest:
            continue

        cleaned = re.sub(r"^[-*]\s*", "", line).strip()
        if any(token in cleaned for token in digest_hits):
            if cleaned not in collected:
                collected.append(cleaned)
        if len(collected) >= max(1, limit):
            break

    return "\n".join(collected)


def update_user_profile(user_id: str, **kwargs):
    """更新用户画像"""
    get_memory_manager().update_profile(user_id, **kwargs)


def add_session_note(
    session_id: str,
    round_num: int,
    note_type: str,
    content: str,
    detail: dict | None = None,
):
    """添加会话笔记"""
    get_session_memory().add_note(session_id, round_num, note_type, content, detail)


def get_session_context(session_id: str, limit: int = 5) -> str:
    """获取会话笔记上下文"""
    return get_session_memory().get_context_for_llm(session_id, limit=limit)


def load_session_notes(session_id: str):
    """加载已有会话笔记"""
    get_session_memory().load_session(session_id)


def get_session_note_stats(session_id: str) -> dict[str, int]:
    """获取会话笔记数量和字符量。"""
    return get_session_memory().get_note_stats(session_id)


def get_long_term_memory_stats(user_id: str) -> dict[str, int]:
    """获取长期记忆数量和字符量。"""
    return get_memory_manager().get_long_term_stats(user_id)


# ===== 后台语义提取（extractMemories 轻量版） =====

EXTRACT_SYSTEM_PROMPT = """你是记忆提取助手。分析本轮对话，判断是否有值得长期记住的信息。

值得记住的信息类型：
1. 用户偏好（如"用户喜欢简洁回答"、"用户对某话题敏感"）
2. 用户身份信息（职业、背景、目标）
3. 重要决策（如"用户最终选择了方案A"）
4. 情绪模式（如"用户提到XX话题时容易愤怒"）
5. 关系事实（如"用户的老板经常贬低他"）

不值得记住的：
- 普通寒暄（"好的"、"收到"）
- 重复信息（已存在于记忆中的事实）
- 系统内部状态（模式、武器、优先级等）

返回规则：
- 如果有值得记住的信息：返回 JSON 对象 {"extract": true, "type": "preference/identity/decision/emotion_pattern/fact", "content": "一句话提炼", "importance": 0.0-1.0}
- 如果没有值得记住的信息：返回 {"extract": false}
- 只返回 JSON，不要其他文字"""


def extract_important_facts(
    user_input: str,
    system_output: str,
    existing_memories: list[Memory] | None = None,
) -> dict | None:
    """
    从本轮对话中提取值得长期记住的事实（extractMemories 轻量版）

    Args:
        user_input: 用户输入
        system_output: 系统输出
        existing_memories: 已有记忆（用于避免重复）

    Returns:
        dict: 提取结果 {"type", "content", "importance"} 或 None
    """
    from llm.nvidia_client import invoke_fast
    import json
    from utils.types import sanitize_for_prompt

    # 构建已有记忆摘要（避免重复提取）
    existing_summary = ""
    if existing_memories:
        existing_summary = "已有记忆:\n" + "\n".join(
            f"- {m.content[:50]}" for m in existing_memories[:5]
        )

    safe_user_input = sanitize_for_prompt(user_input, max_length=2000)
    safe_system_output = sanitize_for_prompt(system_output, max_length=2000)

    user_prompt = f"""本轮对话：
用户: {safe_user_input}
系统: {safe_system_output}

{existing_summary}

请判断是否有值得长期记住的信息。返回 JSON。"""

    try:
        response = invoke_fast(user_prompt, EXTRACT_SYSTEM_PROMPT)
        response = response.strip()
        if response.startswith("```"):
            response = response.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        result = json.loads(response)
        if result.get("extract"):
            return {
                "type": result.get("type", "fact"),
                "content": result.get("content", ""),
                "importance": min(max(result.get("importance", 0.5), 0.0), 1.0),
            }
    except Exception:
        pass

    return None


# ===== 测试入口 =====

if __name__ == "__main__":
    debug_view = os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip() == "1"

    # 测试记忆系统
    manager = MemoryManager(storage_dir="data/test_memory")

    user_id = "test_user_001"

    # 添加记忆
    manager.add_memory(user_id, "用户是一名程序员，喜欢 Python", importance=0.8)
    manager.add_memory(user_id, "用户最近在学习 LangGraph", importance=0.7)
    manager.add_memory(user_id, "用户对 AI Agent 很感兴趣", importance=0.6)

    # 更新画像
    manager.update_profile(user_id, occupation="程序员", preferences=["Python", "AI"])
    manager.update_emotion_pattern(user_id, "挫败", 0.6)
    manager.update_desire_pattern(user_id, "greed", 0.7)

    # 检索记忆
    results = manager.search_memory(user_id, "编程")
    print(f"检索到 {len(results)} 条相关记忆")
    if debug_view:
        for m in results:
            print(f"  - {m.content}")

    # 获取上下文
    context = manager.get_context_for_llm(user_id, "如何学习编程？")
    print(f"记忆上下文长度: {len(context)}")
    if debug_view:
        print(f"\n记忆上下文:\n{context}")

    print("测试完成！")
