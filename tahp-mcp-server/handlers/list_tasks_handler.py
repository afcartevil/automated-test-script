"""tahp_list_tasks 工具处理器

列出所有任务。
"""
from __future__ import annotations

from typing import Any

from handlers import IToolHandler


class ListTasksHandler:
    """处理 tahp_list_tasks 工具调用"""

    def __init__(self, list_fn: Any):
        self._list_fn = list_fn

    @property
    def tool_name(self) -> str:
        return "tahp_list_tasks"

    async def handle(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self._list_fn(
            include_completed=arguments.get("include_completed", True),
        )
