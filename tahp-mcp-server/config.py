# -*- coding: utf-8 -*-
"""TAHP MCP Server 配置管理

管理 MCP Server 的运行配置，包括项目根目录、端口、日志级别等。
支持从环境变量和配置文件加载。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _default_project_root() -> Path:
    """推断项目根目录"""
    # 优先使用环境变量
    env_root = os.environ.get("TAHP_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()

    # 向上查找包含 constraints/ 目录的父目录
    current = Path(__file__).resolve().parent
    for _ in range(5):
        if (current / "constraints").is_dir():
            return current
        current = current.parent

    # 兜底：使用当前工作目录
    return Path.cwd()


@dataclass
class MCPServerConfig:
    """MCP Server 配置"""

    # 项目根目录
    project_root: Path = field(default_factory=_default_project_root)

    # Server 名称
    server_name: str = "tahp-mcp-server"

    # Server 版本
    server_version: str = "0.1.0"

    # 日志级别
    log_level: str = "INFO"

    # 最大并发任务数
    max_concurrent_tasks: int = 5

    # 任务超时时间（秒）
    task_timeout_sec: int = 600

    # 已注册模块
    modules: list[str] = field(default_factory=lambda: [
        "telephony",
        "kernel-driver",
        "power-mgmt",
    ])

    # 支持的领域
    domains: list[str] = field(default_factory=lambda: [
        "bug_analysis",
        "code_adaptation",
        "version_adaptation",
        "carrier_porting",
    ])

    # Playbook 映射
    playbook_map: dict[str, str] = field(default_factory=lambda: {
        "bug_analysis": "bug-analysis-pipeline.yaml",
        "code_adaptation": "code-adaptation-pipeline.yaml",
        "version_adaptation": "version-upgrade-pipeline.yaml",
        "carrier_porting": "carrier-porting-pipeline.yaml",
    })

    @property
    def constraints_dir(self) -> Path:
        return self.project_root / "constraints"

    @property
    def playbooks_dir(self) -> Path:
        return self.project_root / "playbooks"

    @property
    def knowledge_base_dir(self) -> Path:
        return self.project_root / "knowledge-base"

    @property
    def tools_dir(self) -> Path:
        return self.project_root / "tools"

    @property
    def scripts_dir(self) -> Path:
        return self.project_root / "scripts"

    @property
    def reports_dir(self) -> Path:
        return self.project_root / "reports"

    def get_module_dir(self, module: str) -> Path:
        """获取模块约束目录"""
        return self.constraints_dir / module

    def get_shared_dir(self) -> Path:
        """获取共享约束目录"""
        return self.constraints_dir / "shared"

    def get_playbook_path(self, domain: str) -> Path | None:
        """获取领域对应的Playbook文件路径"""
        filename = self.playbook_map.get(domain)
        if filename:
            path = self.playbooks_dir / filename
            if path.exists():
                return path
        return None

    def validate_module(self, module: str) -> bool:
        """验证模块名是否合法"""
        return module in self.modules or (self.constraints_dir / module).is_dir()

    def validate_domain(self, domain: str) -> bool:
        """验证领域名是否合法"""
        return domain in self.domains

    @classmethod
    def from_yaml(cls, filepath: str | Path | None = None) -> "MCPServerConfig":
        """从 YAML 文件加载配置"""
        config = cls()

        if filepath is None:
            filepath = config.project_root / "tahp-mcp-server" / "config.yaml"
        filepath = Path(filepath)

        if not filepath.exists():
            return config

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        except Exception:
            return config

        if "project_root" in data:
            config.project_root = Path(data["project_root"]).resolve()
        if "log_level" in data:
            config.log_level = data["log_level"]
        if "max_concurrent_tasks" in data:
            config.max_concurrent_tasks = int(data["max_concurrent_tasks"])
        if "task_timeout_sec" in data:
            config.task_timeout_sec = int(data["task_timeout_sec"])
        if "modules" in data and isinstance(data["modules"], list):
            config.modules = data["modules"]
        if "playbook_map" in data and isinstance(data["playbook_map"], dict):
            config.playbook_map = data["playbook_map"]

        return config

    def to_dict(self) -> dict[str, Any]:
        """导出为字典"""
        return {
            "project_root": str(self.project_root),
            "server_name": self.server_name,
            "server_version": self.server_version,
            "log_level": self.log_level,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "task_timeout_sec": self.task_timeout_sec,
            "modules": self.modules,
            "domains": self.domains,
            "playbook_map": self.playbook_map,
        }
