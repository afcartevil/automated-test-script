#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TAHP MCP Server 入口

基于 MCP Python SDK 实现的 Model Context Protocol Server，
将 TAHP 的约束驱动开发能力暴露为 MCP 工具，
供 Claude Code 等 AI Agent 调用。

使用方式：
    # 直接运行
    python tahp-mcp-server/server.py

    # 通过 Claude Code 的 .mcp.json 配置
    {
      "mcpServers": {
        "tahp": {
          "command": "python",
          "args": ["tahp-mcp-server/server.py"],
          "cwd": "${workspaceFolder}"
        }
      }
    }

工具列表：
    - tahp_execute: 按照设计文档执行开发任务
    - tahp_status: 查询任务执行状态
    - tahp_correct: 对正在执行的任务进行纠偏
    - tahp_gate_check: 执行质量门禁检查
    - tahp_list_tasks: 列出所有任务
    - tahp_query_knowledge: 查询知识库
    - tahp_analyze_log: 分析 Android 日志
    - tahp_diff_analyze: 分析 AOSP 版本差异
    - tahp_api_migration: 查询 API 迁移规则
    - tahp_code_review: 自动化代码审查
    - tahp_generate_patch: 生成适配 Patch
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

# 确保 tahp-mcp-server 目录在 sys.path 中
# 目录名含连字符(-)不能直接作为Python包导入，
# 所以将自身目录加入sys.path，然后用相对导入或直接导入子模块
_SERVER_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SERVER_DIR.parent

# 将 tahp-mcp-server 目录本身加入 sys.path
# 这样 config, progress, core, adapters 等子包可以直接导入
if str(_SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(_SERVER_DIR))
# 同时将项目根目录加入，以支持 db/ 等模块的导入
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from mcp.server.models import InitializationOptions
from mcp.server import Server
from mcp.types import (
    CallToolResult,
    TextContent,
    Tool,
    INVALID_PARAMS,
    INTERNAL_ERROR,
)

from config import MCPServerConfig
from progress.tracker import get_task_tracker, TaskPhase
from progress.emitter import get_progress_emitter
from core import (
    execute_tahp_task,
    get_tahp_status,
    correct_tahp_task,
    run_gate_check,
    list_tahp_tasks,
    query_knowledge,
)
from adapters import ToolRegistry
from handlers import ToolDispatcher, IToolHandler
from handlers.execute_handler import ExecuteHandler
from handlers.status_handler import StatusHandler
from handlers.correct_handler import CorrectHandler
from handlers.gate_check_handler import GateCheckHandler
from handlers.list_tasks_handler import ListTasksHandler
from handlers.query_knowledge_handler import QueryKnowledgeHandler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("tahp-mcp-server")


# ===== 全局配置 =====
_config = MCPServerConfig.from_yaml()
_tool_registry = ToolRegistry(_config)


# ---------------------------------------------------------------------------
# Adapter-based 工具处理器（委托给 ToolRegistry）
# ---------------------------------------------------------------------------

class _AdapterHandler:
    """通过 ToolRegistry 适配现有工具到 Handler 协议"""

    def __init__(self, tool_name: str, adapter_name: str):
        self._tool_name = tool_name
        self._adapter_name = adapter_name

    @property
    def tool_name(self) -> str:
        return self._tool_name

    async def handle(self, arguments: dict[str, Any]) -> dict[str, Any]:
        return _tool_registry.call(self._adapter_name, arguments)


# ===== 工具分发器 =====
_dispatcher = ToolDispatcher([
    ExecuteHandler(_config, execute_tahp_task),
    StatusHandler(get_tahp_status),
    CorrectHandler(correct_tahp_task),
    GateCheckHandler(_config, run_gate_check),
    ListTasksHandler(list_tahp_tasks),
    QueryKnowledgeHandler(_config, query_knowledge),
    _AdapterHandler("tahp_analyze_log", "android_log_analyzer"),
    _AdapterHandler("tahp_code_review", "code_review_checker"),
    _AdapterHandler("tahp_api_migration", "api_migration_db"),
])

# ===== MCP Server 实例 =====
server = Server("tahp-mcp-server")


# ===== 工具定义 =====

TAHP_EXECUTE_TOOL = Tool(
    name="tahp_execute",
    description=(
        "按照设计文档执行TAHP开发任务。"
        "读取约束文件，分析设计文档，生成修改计划，执行Pipeline，运行质量门禁。"
        "返回任务ID和执行结果，可通过 tahp_status 查询进度。"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "document_path": {
                "type": "string",
                "description": "设计文档路径（相对于项目根目录或绝对路径）",
            },
            "module": {
                "type": "string",
                "description": "模块名: telephony, kernel-driver, power-mgmt",
                "enum": ["telephony", "kernel-driver", "power-mgmt"],
            },
            "domain": {
                "type": "string",
                "description": "领域: bug_analysis, code_adaptation, version_adaptation, carrier_porting",
                "enum": ["bug_analysis", "code_adaptation", "version_adaptation", "carrier_porting"],
            },
            "constraints_extra": {
                "type": "array",
                "items": {"type": "string"},
                "description": "额外的约束文件路径列表（可选）",
            },
        },
        "required": ["document_path", "module", "domain"],
    },
)

TAHP_STATUS_TOOL = Tool(
    name="tahp_status",
    description=(
        "查询TAHP任务执行状态。"
        "返回任务的当前阶段、进度百分比、步骤详情、门禁结果等。"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "任务ID（由 tahp_execute 返回）",
            },
        },
        "required": ["task_id"],
    },
)

TAHP_CORRECT_TOOL = Tool(
    name="tahp_correct",
    description=(
        "对正在执行的TAHP任务进行纠偏。"
        "Claude Code可以通过此工具向TAHP Agent发出修正指令，"
        "TAHP将根据反馈调整执行策略。"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "任务ID",
            },
            "feedback": {
                "type": "string",
                "description": "纠偏反馈内容（修改建议、错误修正等）",
            },
        },
        "required": ["task_id", "feedback"],
    },
)

TAHP_GATE_CHECK_TOOL = Tool(
    name="tahp_gate_check",
    description=(
        "对指定任务或模块执行TAHP质量门禁检查。"
        "支持P0(阻塞级)/P1(警告级)/P2(记录级)三级门禁。"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "任务ID（可选，与module二选一）",
            },
            "module": {
                "type": "string",
                "description": "模块名（可选，与task_id二选一）",
                "enum": ["telephony", "kernel-driver", "power-mgmt"],
            },
            "level": {
                "type": "string",
                "description": "门禁级别",
                "enum": ["P0", "P1", "P2", "all"],
                "default": "all",
            },
        },
    },
)

TAHP_LIST_TASKS_TOOL = Tool(
    name="tahp_list_tasks",
    description="列出所有TAHP任务及其状态",
    inputSchema={
        "type": "object",
        "properties": {
            "include_completed": {
                "type": "boolean",
                "description": "是否包含已完成的任务",
                "default": True,
            },
        },
    },
)

TAHP_QUERY_KNOWLEDGE_TOOL = Tool(
    name="tahp_query_knowledge",
    description=(
        "语义查询TAHP知识库。"
        "支持按模块过滤和跨模块搜索，返回相关知识条目。"
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索查询文本",
            },
            "module": {
                "type": "string",
                "description": "按模块过滤（可选）",
            },
            "cross_module": {
                "type": "boolean",
                "description": "是否跨模块搜索",
                "default": False,
            },
            "top_k": {
                "type": "integer",
                "description": "返回结果数量",
                "default": 5,
            },
        },
        "required": ["query"],
    },
)

TAHP_ANALYZE_LOG_TOOL = Tool(
    name="tahp_analyze_log",
    description="解析Android logcat/ril/atcmd日志，提取错误事件和通信事件",
    inputSchema={
        "type": "object",
        "properties": {
            "log_content": {
                "type": "string",
                "description": "日志内容",
            },
            "log_type": {
                "type": "string",
                "description": "日志类型",
                "enum": ["logcat", "ril", "atcmd"],
                "default": "logcat",
            },
            "filters": {
                "type": "array",
                "items": {"type": "string"},
                "description": "过滤关键词列表（可选）",
            },
        },
        "required": ["log_content"],
    },
)

TAHP_CODE_REVIEW_TOOL = Tool(
    name="tahp_code_review",
    description="自动化代码审查，检查P0/P1/P2规则违规",
    inputSchema={
        "type": "object",
        "properties": {
            "patch_content": {
                "type": "string",
                "description": "Patch/代码差异内容",
            },
            "check_level": {
                "type": "string",
                "description": "检查级别",
                "enum": ["P0", "P1", "P2"],
                "default": "P0",
            },
        },
        "required": ["patch_content"],
    },
)

TAHP_API_MIGRATION_TOOL = Tool(
    name="tahp_api_migration",
    description="查询API迁移规则库，支持list/search/add操作",
    inputSchema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "操作类型",
                "enum": ["list", "search", "add"],
                "default": "list",
            },
            "module": {
                "type": "string",
                "description": "按模块过滤（list操作时使用）",
            },
            "old_api": {
                "type": "string",
                "description": "旧API名称（search操作时使用）",
            },
        },
    },
)


# ===== Server 事件处理 =====

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    """返回所有可用的 TAHP MCP 工具"""
    return [
        TAHP_EXECUTE_TOOL,
        TAHP_STATUS_TOOL,
        TAHP_CORRECT_TOOL,
        TAHP_GATE_CHECK_TOOL,
        TAHP_LIST_TASKS_TOOL,
        TAHP_QUERY_KNOWLEDGE_TOOL,
        TAHP_ANALYZE_LOG_TOOL,
        TAHP_CODE_REVIEW_TOOL,
        TAHP_API_MIGRATION_TOOL,
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict[str, Any] | None) -> list[TextContent]:
    """处理工具调用请求"""
    if arguments is None:
        arguments = {}

    logger.info("Tool call: %s with args: %s", name, json.dumps(arguments, ensure_ascii=False)[:200])

    try:
        result = await _dispatch_tool(name, arguments)
        result_str = json.dumps(result, ensure_ascii=False, indent=2, default=str)

        # 如果结果太长，截断并添加提示
        if len(result_str) > 50000:
            result_str = result_str[:50000] + "\n... (结果已截断，请使用 tahp_status 查看详细信息)"

        return [TextContent(type="text", text=result_str)]

    except ValueError as e:
        logger.warning("Invalid params for %s: %s", name, e)
        return [TextContent(type="text", text=json.dumps({"error": str(e)}, ensure_ascii=False))]
    except Exception as e:
        logger.exception("Tool %s execution failed", name)
        return [TextContent(type="text", text=json.dumps({"error": f"Internal error: {str(e)}"}, ensure_ascii=False))]


async def _dispatch_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """分发工具调用到对应的 Handler（基于 ToolDispatcher 注册表）"""
    return await _dispatcher.dispatch(name, arguments)


# ===== Server 生命周期 =====

async def _on_server_initialized():
    """Server 初始化完成后的回调"""
    emitter = get_progress_emitter()
    emitter.set_server(server)
    logger.info("TAHP MCP Server initialized with project root: %s", _config.project_root)
    logger.info("Available modules: %s", _config.modules)
    logger.info("Loaded tool adapters: %s", list(_tool_registry.to_dict().keys()))


async def main_async():
    """异步主入口"""
    from mcp.server.stdio import stdio_server

    logger.info("Starting TAHP MCP Server v%s", _config.server_version)

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=_config.server_name,
                server_version=_config.server_version,
            ),
        )


def main():
    """同步主入口"""
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
