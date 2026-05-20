"""tahp_correct 工具处理器

对正在执行的任务进行纠偏。
"""
from __future__ import annotations

from typing import Any

from handlers import IToolHandler


class CorrectHandler:
    """处理 tahp_correct 工具调用"""

    def __init__(self, correct_fn: Any):
        self._correct_fn = correct_fn

    @property
    def tool_name(self) -> str:
        return "tahp_correct"

    async def handle(self, arguments: dict[str, Any]) -> dict[str, Any]:
        task_id = arguments.get("task_id", "")
        feedback = arguments.get("feedback", "")
        if not task_id:
            raise ValueError("task_id is required")
        if not feedback:
            raise ValueError("feedback is required")
        return await self._correct_fn(task_id, feedback)
