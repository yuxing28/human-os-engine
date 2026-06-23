"""
Human-OS Engine - 结构化日志记录器（JSONL 格式）

每轮对抗一条记录，便于离线分析。
"""

import json
import os
import time
from pathlib import Path
from typing import Any


class Recorder:
    def __init__(self, trace_id: str, output_dir: str = "./simulation/logs"):
        self.trace_id = trace_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.file_path = self.output_dir / f"{trace_id}.jsonl"
        self._file = open(self.file_path, "w", encoding="utf-8")
        self._records = []
        self._include_internal_context = os.getenv("HUMAN_OS_DEBUG_VIEW", "").strip() == "1"

    def _build_system_context(self, system_context: dict, weapons_used: list) -> dict:
        """默认只保留离线分析需要的最小结果，细节仅在调试模式下写入。"""
        summary = {
            "weapons_used": weapons_used,
        }
        if self._include_internal_context:
            summary.update(
                {
                    "goal": system_context.get("goal_description", ""),
                    "mode": system_context.get("mode", ""),
                    "priority": system_context.get("priority", ""),
                }
            )
        return summary

    def record_step(self, round_num: int, agent_state: dict, system_context: dict,
                    agent_input: str, system_output: str, weapons_used: list,
                    delta: dict):
        record = {
            "trace_id": self.trace_id,
            "round": round_num,
            "timestamp": time.time(),
            "agent_input": agent_input,
            "system_output": system_output,
            "agent_state": agent_state,
            "system_context": self._build_system_context(system_context, weapons_used),
            "delta": delta,
        }
        self._records.append(record)
        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._file.flush()

    def record_outcome(self, outcome: dict):
        """记录最终评估结果"""
        record = {
            "trace_id": self.trace_id,
            "type": "outcome",
            "timestamp": time.time(),
            **outcome,
        }
        self._records.append(record)
        self._file.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._file.flush()

    def close(self):
        self._file.close()

    @property
    def records(self):
        return self._records
