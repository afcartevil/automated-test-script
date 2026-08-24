#!/usr/bin/env python3
"""TAHP Bridge 兼容契约探针：校验 Hermes Agent 源码/运行时是否仍暴露所需 API。

无网络。优先真实 import；失败则回退到 AST 源码扫描，便于旁路目录尚未建 venv。
"""
from __future__ import annotations

import argparse
import ast
import importlib
import inspect
import json
import os
import sys
from pathlib import Path
from typing import Any


REQUIRED_IMPORTS = [
    ("run_agent", "AIAgent"),
    ("hermes_state", "SessionDB"),
    ("hermes_cli.runtime_provider", "resolve_runtime_provider"),
    ("hermes_cli.tools_config", "_get_platform_tools"),
    ("hermes_cli.config", "load_config"),
    ("hermes_cli.plugins", "PluginManager"),
    ("hermes_cli.plugins", "get_bundled_plugins_dir"),
    ("hermes_cli.plugins", "_get_disabled_plugins"),
    ("hermes_cli.plugins", "_get_enabled_plugins"),
    ("tools.terminal_tool", "set_approval_callback"),
    ("tools.terminal_tool", "_get_approval_callback"),
    ("tools.approval", "register_gateway_notify"),
    ("tools.approval", "set_current_session_key"),
]

AIAGENT_METHODS = ["run_conversation", "interrupt", "steer", "_compress_context"]
AIAGENT_INIT_PARAMS = [
    "model", "provider", "base_url", "api_key", "api_mode",
    "acp_command", "acp_args", "credential_pool", "quiet_mode",
    "enabled_toolsets", "platform", "session_id", "session_db",
    "ephemeral_system_prompt", "status_callback", "thinking_callback",
    "reasoning_callback", "tool_progress_callback", "tool_start_callback",
    "tool_complete_callback",
]
RUN_CONVERSATION_PARAMS = ["system_message", "conversation_history", "task_id", "stream_callback"]
SESSIONDB_METHODS = ["create_session", "append_message", "get_messages"]
RUNTIME_PROVIDER_FIELDS = ["provider", "base_url", "api_key", "api_mode", "command", "args", "credential_pool"]

MODULE_FILES = {
    "run_agent": "run_agent.py",
    "hermes_state": "hermes_state.py",
    "hermes_cli.runtime_provider": "hermes_cli/runtime_provider.py",
    "hermes_cli.tools_config": "hermes_cli/tools_config.py",
    "hermes_cli.config": "hermes_cli/config.py",
    "hermes_cli.plugins": "hermes_cli/plugins.py",
    "tools.terminal_tool": "tools/terminal_tool.py",
    "tools.approval": "tools/approval.py",
}


def _load_ast(path: Path) -> ast.AST | None:
    if not path.exists():
        return None
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _module_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
    return names


def _class_methods(tree: ast.AST, class_name: str) -> set[str]:
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return {
                item.name for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            }
    return set()


def _fn_args(tree: ast.AST, class_name: str | None, fn_name: str) -> list[str]:
    nodes: list[ast.AST] = list(tree.body) if isinstance(tree, ast.Module) else []
    if class_name:
        for node in nodes:
            if isinstance(node, ast.ClassDef) and node.name == class_name:
                nodes = list(node.body)
                break
        else:
            return []
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == fn_name:
            args = [a.arg for a in node.args.args]
            args += [a.arg for a in node.args.kwonlyargs]
            if node.args.vararg:
                args.append(f"*{node.args.vararg.arg}")
            if node.args.kwarg:
                args.append(f"**{node.args.kwarg.arg}")
            return [a for a in args if a != "self"]
    return []


def probe_source(agent_root: Path) -> dict[str, Any]:
    missing: list[str] = []
    notes: list[str] = []
    details: dict[str, Any] = {}
    trees: dict[str, ast.AST] = {}
    for mod, rel in MODULE_FILES.items():
        tree = _load_ast(agent_root / rel)
        if tree is None:
            missing.append(f"file:{rel}")
        else:
            trees[mod] = tree

    for mod, name in REQUIRED_IMPORTS:
        tree = trees.get(mod)
        if tree is None:
            continue
        if name not in _module_names(tree) and name not in _class_methods(tree, name):
            missing.append(f"symbol:{mod}.{name}")

    run_tree = trees.get("run_agent")
    if run_tree:
        methods = _class_methods(run_tree, "AIAgent")
        details["aiagent_methods"] = sorted(methods)
        for method in AIAGENT_METHODS:
            if method not in methods:
                missing.append(f"AIAgent.{method}")
        init_args = _fn_args(run_tree, "AIAgent", "__init__")
        details["aiagent_init_params"] = init_args
        accepts_kwargs = any(a.startswith("**") for a in init_args)
        for param in AIAGENT_INIT_PARAMS:
            if param not in init_args and not accepts_kwargs:
                missing.append(f"AIAgent.__init__:{param}")
        conv_args = _fn_args(run_tree, "AIAgent", "run_conversation")
        details["run_conversation_params"] = conv_args
        conv_kwargs = any(a.startswith("**") for a in conv_args)
        for param in RUN_CONVERSATION_PARAMS:
            if param not in conv_args and not conv_kwargs:
                missing.append(f"AIAgent.run_conversation:{param}")
    else:
        notes.append("run_agent.py missing; skipped AIAgent signature checks")

    state_tree = trees.get("hermes_state")
    if state_tree:
        methods = _class_methods(state_tree, "SessionDB")
        details["sessiondb_methods"] = sorted(methods)
        for method in SESSIONDB_METHODS:
            if method not in methods:
                missing.append(f"SessionDB.{method}")

    return {"mode": "source", "missing": missing, "notes": notes, "details": details}


def probe_runtime(agent_root: Path) -> dict[str, Any]:
    sys.path = [p for p in sys.path if p not in ("", os.getcwd())]
    sys.path.insert(0, str(agent_root))
    missing: list[str] = []
    notes: list[str] = []
    details: dict[str, Any] = {}
    imported: dict[str, Any] = {}

    for mod, name in REQUIRED_IMPORTS:
        try:
            module = importlib.import_module(mod)
            imported[f"{mod}.{name}"] = getattr(module, name)
        except Exception as exc:
            missing.append(f"import:{mod}.{name}:{type(exc).__name__}:{exc}")

    agent_cls = imported.get("run_agent.AIAgent")
    if agent_cls:
        init_params = [p for p in inspect.signature(agent_cls.__init__).parameters if p != "self"]
        details["aiagent_init_params"] = init_params
        for param in AIAGENT_INIT_PARAMS:
            if param not in inspect.signature(agent_cls.__init__).parameters:
                missing.append(f"AIAgent.__init__:{param}")
        for method in AIAGENT_METHODS:
            if not callable(getattr(agent_cls, method, None)):
                missing.append(f"AIAgent.{method}")
        conv = getattr(agent_cls, "run_conversation", None)
        if callable(conv):
            conv_params = list(inspect.signature(conv).parameters)
            details["run_conversation_params"] = conv_params
            for param in RUN_CONVERSATION_PARAMS:
                if param not in inspect.signature(conv).parameters:
                    missing.append(f"AIAgent.run_conversation:{param}")

    session_cls = imported.get("hermes_state.SessionDB")
    if session_cls:
        for method in SESSIONDB_METHODS:
            if not callable(getattr(session_cls, method, None)):
                missing.append(f"SessionDB.{method}")

    resolve_runtime = imported.get("hermes_cli.runtime_provider.resolve_runtime_provider")
    if callable(resolve_runtime):
        notes.append("resolve_runtime_provider imported; return-field check is runtime-only and skipped without credentials")
        details["runtime_provider_expected_fields"] = RUNTIME_PROVIDER_FIELDS

    return {"mode": "runtime", "missing": missing, "notes": notes, "details": details}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent-root", required=True)
    parser.add_argument("--mode", choices=["auto", "source", "runtime"], default="auto")
    args = parser.parse_args()
    agent_root = Path(args.agent_root).resolve()
    if not agent_root.exists():
        print(json.dumps({"ok": False, "error": f"agent root not found: {agent_root}"}))
        return 2

    reports: list[dict[str, Any]] = []
    if args.mode in ("auto", "source"):
        reports.append(probe_source(agent_root))
    if args.mode in ("auto", "runtime"):
        try:
            reports.append(probe_runtime(agent_root))
        except Exception as exc:
            reports.append({"mode": "runtime", "missing": [f"runtime-probe:{exc}"], "notes": [], "details": {}})

    missing = []
    for report in reports:
        missing.extend(report.get("missing") or [])
    result = {
        "ok": not missing,
        "agentRoot": str(agent_root),
        "missing": missing,
        "reports": reports,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
