"""tahp_execute 工具处理器

按照设计文档执行开发任务。
"""
from __future__ import annotations

from typing import Any

from handlers import IToolHandler


class ExecuteHandler:
    """处理 tahp_execute 工具调用"""

    def __init__(self, config: Any, execute_fn: Any):
        self._config = config
        self._execute_fn = execute_fn

    @property
    def tool_name(self) -> str:
        return "tahp_execute"

    async def handle(self, arguments: dict[str, Any]) -> dict[str, Any]:
        document_path = arguments.get("document_path", "")
        module = arguments.get("module", "")
        domain = arguments.get("domain", "")

        if not document_path:
            raise ValueError("document_path is required")
        if not module:
            raise ValueError("module is required")
        if not domain:
            raise ValueError("domain is required")
        if not self._config.validate_module(module):
            raise ValueError(f"Invalid module: {module}. Valid: {self._config.modules}")
        if not self._config.validate_domain(domain):
            raise ValueError(f"Invalid domain: {domain}. Valid: {self._config.domains}")

        return await self._execute_fn(
            config=self._config,
            document_path=document_path,
            module=module,
            domain=domain,
            constraints_extra=arguments.get("constraints_extra"),
        )
