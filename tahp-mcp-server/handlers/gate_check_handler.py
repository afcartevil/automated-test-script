"""tahp_gate_check 工具处理器

执行质量门禁检查。
"""
from __future__ import annotations

from typing import Any

from handlers import IToolHandler


class GateCheckHandler:
    """处理 tahp_gate_check 工具调用"""

    def __init__(self, config: Any, gate_check_fn: Any):
        self._config = config
        self._gate_check_fn = gate_check_fn

    @property
    def tool_name(self) -> str:
        return "tahp_gate_check"

    async def handle(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self._gate_check_fn(
            config=self._config,
            task_id=arguments.get("task_id"),
            module=arguments.get("module"),
            level=arguments.get("level", "all"),
        )
