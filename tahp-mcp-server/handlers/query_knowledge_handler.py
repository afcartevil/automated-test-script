"""tahp_query_knowledge 工具处理器

查询知识库。
"""
from __future__ import annotations

from typing import Any

from handlers import IToolHandler


class QueryKnowledgeHandler:
    """处理 tahp_query_knowledge 工具调用"""

    def __init__(self, config: Any, query_fn: Any):
        self._config = config
        self._query_fn = query_fn

    @property
    def tool_name(self) -> str:
        return "tahp_query_knowledge"

    async def handle(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query_text = arguments.get("query", "")
        if not query_text:
            raise ValueError("query is required")
        return await self._query_fn(
            config=self._config,
            query=query_text,
            module=arguments.get("module"),
            cross_module=arguments.get("cross_module", False),
            top_k=arguments.get("top_k", 5),
        )
