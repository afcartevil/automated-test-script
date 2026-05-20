"""MCP 工具处理器模块

每个 MCP 工具对应一个 Handler 实现，支持自注册到 ToolDispatcher。
新增工具只需添加 Handler 类，无需修改 server.py 的核心分发逻辑。

使用方式：
    dispatcher = ToolDispatcher()
    dispatcher.register(ExecuteHandler(config))
    result = await dispatcher.dispatch("tahp_execute", arguments)
"""

from __future__ import annotations

from typing import Any, Protocol


class IToolHandler(Protocol):
    """MCP 工具处理器协议

    每个 MCP 工具对应一个实现了此协议的 Handler 类。
    """

    @property
    def tool_name(self) -> str:
        """工具名称（如 'tahp_execute'）"""
        ...

    async def handle(self, arguments: dict[str, Any]) -> dict[str, Any]:
        """处理工具调用，返回结果字典"""
        ...


class ToolDispatcher:
    """工具分发器 — 基于注册表模式替代 if-elif 链

    用法:
        dispatcher = ToolDispatcher()
        dispatcher.register(ExecuteHandler(config))
        dispatcher.register(StatusHandler())
        # ...
        result = await dispatcher.dispatch(name, arguments)
    """

    def __init__(self, handlers: list[IToolHandler] | None = None):
        self._handlers: dict[str, IToolHandler] = {}
        if handlers:
            for h in handlers:
                self.register(h)

    def register(self, handler: IToolHandler) -> None:
        """注册一个工具处理器"""
        name = handler.tool_name
        if name in self._handlers:
            raise ValueError(f"Handler for '{name}' is already registered")
        self._handlers[name] = handler

    async def dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """分发工具调用到对应的 Handler

        Raises:
            ValueError: 工具名未注册
        """
        handler = self._handlers.get(name)
        if not handler:
            raise ValueError(f"Unknown tool: {name}")
        return await handler.handle(arguments)

    @property
    def tool_names(self) -> list[str]:
        """返回所有已注册的工具名"""
        return list(self._handlers.keys())
