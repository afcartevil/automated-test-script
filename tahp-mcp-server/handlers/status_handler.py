"""tahp_status 工具处理器

查询任务执行状态。
"""
from __future__ import annotations

from typing import Any

from handlers import IToolHandler


class StatusHandler:
    """处理 tahp_status 工具调用"""

    def __init__(self, status_fn: Any):
        self._status_fn = status_fn

    @property
    def tool_name(self) -> str:
        return "tahp_status"

    async def handle(self, arguments: dict[str, Any]) -> dict[str, Any]:
        task_id = arguments.get("task_id", "")
        if not task_id:
            raise ValueError("task_id is required")
        return await self._status_fn(task_id)
