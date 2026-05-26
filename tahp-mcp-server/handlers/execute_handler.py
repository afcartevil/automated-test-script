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
        document_content = arguments.get("document_content")  # 内联文档内容（adapt-debug 场景）
        extra_context = arguments.get("extra_context")        # 附加上下文说明

        if not document_path:
            raise ValueError("document_path is required")
        if not module:
            raise ValueError("module is required")
        if not domain:
            raise ValueError("domain is required")

        # 对于内联模式（document_path='__inline__'），跳过模块和域的严格校验
        # 允许动态域和自定义业务模块也能执行
        is_inline = document_path == "__inline__"
        if not is_inline:
            if not self._config.validate_module(module):
                raise ValueError(f"Invalid module: {module}. Valid: {self._config.modules}")
            if not self._config.validate_domain(domain):
                raise ValueError(f"Invalid domain: {domain}. Valid: {self._config.domains}")
        else:
            # 内联模式：尽量将模块映射到已知的可用模块，保证约束能正常加载
            if not self._config.validate_module(module):
                module = "shared"  # 回退到共享模块
            if not self._config.validate_domain(domain):
                domain = "code_adaptation"  # 回退到通用适配域

        return await self._execute_fn(
            config=self._config,
            document_path=document_path,
            module=module,
            domain=domain,
            constraints_extra=arguments.get("constraints_extra"),
            document_content_inline=document_content,
            extra_context=extra_context,
        )
