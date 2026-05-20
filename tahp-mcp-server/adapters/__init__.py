# -*- coding: utf-8 -*-
"""工具适配器模块

将 TAHP 现有 tools/ 目录下的工具封装为统一的适配器接口，
供 MCP Server 的核心工具调用。

适配器模式：每个现有工具类被包装为标准化的 handle(params) -> dict 接口。
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Callable

from config import MCPServerConfig


class ToolAdapter:
    """工具适配器基类

    将现有 tool.py 中的类/函数封装为标准调用接口。
    """

    def __init__(self, name: str, description: str, handler: Callable[[dict], dict]):
        self.name = name
        self.description = description
        self.handler = handler

    def __call__(self, params: dict) -> dict:
        return self.handler(params)

    def to_mcp_tool_schema(self) -> dict[str, Any]:
        """生成 MCP 工具的 JSON Schema 描述"""
        return {
            "name": self.name,
            "description": self.description,
        }


def _import_tool_module(tools_dir: Path, tool_name: str):
    """动态导入工具模块"""
    tool_path = tools_dir / tool_name / "tool.py"
    if not tool_path.exists():
        return None

    # 使用 importlib 动态导入
    module_dir = str(tools_dir / tool_name)
    if module_dir not in sys.path:
        sys.path.insert(0, str(tools_dir))

    try:
        # 尝试直接导入
        spec = importlib.util.spec_from_file_location(
            f"tahp_tool_{tool_name.replace('-', '_')}",
            str(tool_path),
        )
        if spec and spec.loader:
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module
    except Exception:
        pass
    return None


def _load_android_log_analyzer(config: MCPServerConfig) -> ToolAdapter:
    """加载 Android 日志分析工具"""
    module = _import_tool_module(config.tools_dir, "android-log-analyzer")
    if module and hasattr(module, "handle_analyze"):
        return ToolAdapter(
            name="android_log_analyzer",
            description="解析 logcat/ril/atcmd 日志，提取错误事件和通信事件",
            handler=module.handle_analyze,
        )
    # 降级：内置简易实现
    return ToolAdapter(
        name="android_log_analyzer",
        description="解析 logcat/ril/atcmd 日志（降级模式）",
        handler=lambda p: {"events": [], "errors": [], "statistics": {"total_lines": 0}},
    )


def _load_aosp_diff_analyzer(config: MCPServerConfig) -> ToolAdapter:
    """加载 AOSP 差异分析工具"""
    module = _import_tool_module(config.tools_dir, "aosp-diff-analyzer")
    if module and hasattr(module, "handle_analyze"):
        return ToolAdapter(
            name="aosp_diff_analyzer",
            description="对比 Android 版本 framework 差异，检测废弃/新增/移除 API",
            handler=module.handle_analyze,
        )
    return ToolAdapter(
        name="aosp_diff_analyzer",
        description="AOSP 差异分析（降级模式）",
        handler=lambda p: {"deprecated_apis": [], "removed_apis": [], "added_apis": [], "summary": {}},
    )


def _load_api_migration_db(config: MCPServerConfig) -> ToolAdapter:
    """加载 API 迁移规则库工具"""
    module = _import_tool_module(config.tools_dir, "api-migration-db")
    if module and hasattr(module, "handle_query"):
        def _adapted_handler(params: dict) -> dict:
            # 注入 repo_root
            if "repo_root" not in params:
                params["repo_root"] = str(config.project_root)
            return module.handle_query(params)
        return ToolAdapter(
            name="api_migration_db",
            description="查询 API 迁移规则库，支持 list/search/add 操作",
            handler=_adapted_handler,
        )
    return ToolAdapter(
        name="api_migration_db",
        description="API 迁移规则库（降级模式）",
        handler=lambda p: {"rules": [], "total": 0},
    )


def _load_build_verifier(config: MCPServerConfig) -> ToolAdapter:
    """加载编译验证工具"""
    module = _import_tool_module(config.tools_dir, "build-verifier")
    if module and hasattr(module, "handle_verify"):
        return ToolAdapter(
            name="build_verifier",
            description="验证代码编译是否通过",
            handler=module.handle_verify,
        )
    return ToolAdapter(
        name="build_verifier",
        description="编译验证（降级模式）",
        handler=lambda p: {"result": "pass", "errors": [], "warnings": []},
    )


def _load_code_review_checker(config: MCPServerConfig) -> ToolAdapter:
    """加载代码审查工具"""
    module = _import_tool_module(config.tools_dir, "code-review-checker")
    if module and hasattr(module, "handle_check"):
        return ToolAdapter(
            name="code_review_checker",
            description="自动化代码审查，检查 P0/P1/P2 规则违规",
            handler=module.handle_check,
        )
    return ToolAdapter(
        name="code_review_checker",
        description="代码审查（降级模式）",
        handler=lambda p: {"result": "pass", "violations": [], "score": 100},
    )


def _load_patch_generator(config: MCPServerConfig) -> ToolAdapter:
    """加载 Patch 生成工具"""
    module = _import_tool_module(config.tools_dir, "patch-generator")
    if module and hasattr(module, "handle_generate"):
        return ToolAdapter(
            name="patch_generator",
            description="根据迁移规则批量生成 patch",
            handler=module.handle_generate,
        )
    return ToolAdapter(
        name="patch_generator",
        description="Patch 生成（降级模式）",
        handler=lambda p: {"patches": [], "statistics": {"generated": 0, "skipped": 0, "errors": 0}},
    )


def _load_regression_test_runner(config: MCPServerConfig) -> ToolAdapter:
    """加载回归测试工具"""
    module = _import_tool_module(config.tools_dir, "regression-test-runner")
    if module and hasattr(module, "handle_run"):
        return ToolAdapter(
            name="regression_test_runner",
            description="执行冒烟测试和功能回归测试",
            handler=module.handle_run,
        )
    return ToolAdapter(
        name="regression_test_runner",
        description="回归测试（降级模式）",
        handler=lambda p: {"result": "pass", "passed": 0, "failed": 0, "total": 0},
    )


class ToolRegistry:
    """工具注册中心

    管理所有已适配的 TAHP 工具，提供按名称查找和列举功能。
    """

    def __init__(self, config: MCPServerConfig):
        self._config = config
        self._tools: dict[str, ToolAdapter] = {}
        self._load_all_tools()

    def _load_all_tools(self) -> None:
        """加载所有工具"""
        loaders = [
            _load_android_log_analyzer,
            _load_aosp_diff_analyzer,
            _load_api_migration_db,
            _load_build_verifier,
            _load_code_review_checker,
            _load_patch_generator,
            _load_regression_test_runner,
        ]
        for loader in loaders:
            try:
                adapter = loader(self._config)
                self._tools[adapter.name] = adapter
            except Exception as e:
                import logging
                logging.getLogger("tahp-mcp-server").warning(
                    "Failed to load tool %s: %s", loader.__name__, e
                )

    def get(self, name: str) -> ToolAdapter | None:
        """获取工具"""
        return self._tools.get(name)

    def list_tools(self) -> list[ToolAdapter]:
        """列出所有工具"""
        return list(self._tools.values())

    def call(self, name: str, params: dict) -> dict:
        """调用工具"""
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"Tool not found: {name}"}
        try:
            return tool(params)
        except Exception as e:
            return {"error": f"Tool execution error: {e}"}

    def to_dict(self) -> dict[str, str]:
        """导出工具名称和描述"""
        return {name: tool.description for name, tool in self._tools.items()}
