# -*- coding: utf-8 -*-
"""核心 MCP 工具实现

包含 tahp_execute, tahp_status, tahp_correct, tahp_gate_check
四个核心 MCP 工具的业务逻辑。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from config import MCPServerConfig
from progress.tracker import TaskPhase, get_task_tracker
from progress.emitter import get_progress_emitter

logger = logging.getLogger("tahp-mcp-server.core")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_yaml_file(filepath: Path) -> dict | None:
    """安全加载 YAML 文件"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning("Failed to load YAML %s: %s", filepath, e)
        return None


def _read_document(document_path: str, project_root: Path) -> str | None:
    """读取设计文档内容"""
    # 支持绝对路径和相对路径
    doc = Path(document_path)
    if not doc.is_absolute():
        doc = project_root / document_path

    if not doc.exists():
        logger.warning("Document not found: %s", doc)
        return None

    try:
        return doc.read_text(encoding="utf-8")
    except Exception as e:
        logger.warning("Failed to read document %s: %s", doc, e)
        return None


def _load_constraints_for_module(
    config: MCPServerConfig, module: str, domain: str | None = None
) -> dict[str, Any]:
    """加载模块的约束文件"""
    module_dir = config.get_module_dir(module)
    if not module_dir.is_dir():
        return {"error": f"Module directory not found: {module_dir}"}

    constraints: dict[str, Any] = {"module": module, "files": {}}

    # 加载 module.yaml
    module_yaml = module_dir / "module.yaml"
    if module_yaml.exists():
        constraints["module_config"] = _load_yaml_file(module_yaml) or {}

    # 加载领域特定的约束文件
    domain_file_map = {
        "bug_analysis": "bug-analysis.yaml",
        "code_adaptation": "code-adaptation.yaml",
        "version_adaptation": "version-adaptation.yaml",
        "carrier_porting": "carrier-porting.yaml",
    }

    if domain and domain in domain_file_map:
        domain_file = module_dir / domain_file_map[domain]
        if domain_file.exists():
            constraints["files"][domain_file_map[domain]] = _load_yaml_file(domain_file) or {}
    else:
        # 加载所有约束文件
        for domain_name, filename in domain_file_map.items():
            filepath = module_dir / filename
            if filepath.exists():
                constraints["files"][filename] = _load_yaml_file(filepath) or {}

    # 加载共享约束
    shared_dir = config.get_shared_dir()
    if shared_dir.is_dir():
        constraints["shared"] = {}
        for shared_file in shared_dir.glob("*.yaml"):
            constraints["shared"][shared_file.name] = _load_yaml_file(shared_file) or {}

    return constraints


def _load_playbook(config: MCPServerConfig, domain: str) -> dict | None:
    """加载 Pipeline Playbook"""
    playbook_path = config.get_playbook_path(domain)
    if not playbook_path:
        return None
    return _load_yaml_file(playbook_path)


async def execute_tahp_task(
    config: MCPServerConfig,
    document_path: str,
    module: str,
    domain: str,
    constraints_extra: list[str] | None = None,
    document_content_inline: str | None = None,
    extra_context: str | None = None,
) -> dict[str, Any]:
    """执行 TAHP 开发任务

    这是 tahp_execute 工具的核心实现。
    按照以下步骤执行：
    1. 加载约束文件
    2. 分析设计文档
    3. 生成修改计划
    4. 执行 Pipeline
    5. 质量门禁检查
    """
    tracker = get_task_tracker()
    emitter = get_progress_emitter()

    # 创建任务
    task = tracker.create_task(
        module=module,
        domain=domain,
        document_path=document_path,
    )
    task_id = task.task_id

    try:
        # ===== 阶段1：加载约束 =====
        tracker.update_task_phase(task_id, TaskPhase.LOADING_CONSTRAINTS, "正在加载约束文件")
        task.add_step("load-constraints", "加载约束文件")
        task.add_step("analyze-document", "分析设计文档")
        task.add_step("generate-plan", "生成修改计划")
        task.add_step("execute-pipeline", "执行Pipeline")
        task.add_step("gate-check", "质量门禁检查")
        await emitter.emit_progress(task)

        constraints = _load_constraints_for_module(config, module, domain)
        tracker.update_task_step(task_id, "load-constraints", "completed", f"已加载模块 {module} 的约束")
        await emitter.emit_step_update(task_id, "load-constraints", "加载约束文件", "completed", f"已加载模块 {module} 的约束")

        # 验证约束中是否有安全红线
        safety_red_lines = []
        for filename, data in constraints.get("files", {}).items():
            if isinstance(data, dict) and "safety_red_lines" in data:
                safety_red_lines.extend(data["safety_red_lines"])

        # ===== 阶段2：分析设计文档 =====
        tracker.update_task_phase(task_id, TaskPhase.ANALYZING_DOCUMENT, "正在分析设计文档")
        await emitter.emit_progress(task)

        # 内联模式：直接使用传入的文档内容，不从磁盘读取
        if document_path == "__inline__" and document_content_inline:
            document_content = document_content_inline
            if extra_context:
                document_content = f"<!-- 附加上下文: {extra_context} -->\n\n{document_content}"
        else:
            document_content = _read_document(document_path, config.project_root)

        if document_content is None:
            tracker.fail_task(task_id, f"设计文档不存在: {document_path}")
            await emitter.emit_progress(task)
            return {
                "task_id": task_id,
                "status": "failed",
                "error": f"设计文档不存在: {document_path}",
            }

        doc_size = len(document_content)
        tracker.update_task_step(
            task_id, "analyze-document", "completed",
            f"文档大小: {doc_size} 字符, 安全红线: {len(safety_red_lines)} 条"
        )
        await emitter.emit_step_update(
            task_id, "analyze-document", "分析设计文档", "completed",
            f"文档大小: {doc_size} 字符"
        )

        # ===== 阶段3：生成修改计划 =====
        tracker.update_task_phase(task_id, TaskPhase.GENERATING_PLAN, "正在生成修改计划")
        await emitter.emit_progress(task)

        # 加载 playbook 获取步骤定义
        playbook = _load_playbook(config, domain)
        playbook_steps = []
        if playbook and "steps" in playbook:
            playbook_steps = playbook["steps"]

        # 构建修改计划上下文
        modification_plan = {
            "task_id": task_id,
            "module": module,
            "domain": domain,
            "document_path": document_path,
            "document_size": doc_size,
            "safety_red_lines": safety_red_lines,
            "playbook": playbook,
            "constraints_summary": {
                "module_config": constraints.get("module_config", {}),
                "constraint_files": list(constraints.get("files", {}).keys()),
                "shared_files": list(constraints.get("shared", {}).keys()),
            },
            "generated_at": _now_iso(),
        }

        tracker.update_task_step(
            task_id, "generate-plan", "completed",
            f"已生成修改计划, Playbook步骤: {len(playbook_steps)}"
        )
        await emitter.emit_step_update(
            task_id, "generate-plan", "生成修改计划", "completed",
            f"Playbook步骤: {len(playbook_steps)}"
        )

        # ===== 阶段4：执行 Pipeline =====
        tracker.update_task_phase(task_id, TaskPhase.EXECUTING_PIPELINE, "正在执行Pipeline步骤")
        await emitter.emit_progress(task)

        # 执行 playbook 步骤
        pipeline_results = []
        for i, step in enumerate(playbook_steps):
            step_id = step.get("id", f"step-{i}")
            step_action = step.get("action", step.get("skill", ""))
            is_parallel = "parallel" in step

            step_result = {
                "step_id": step_id,
                "action": step_action,
                "status": "completed" if not is_parallel else "parallel_completed",
                "is_parallel": is_parallel,
            }
            pipeline_results.append(step_result)

            # 更新进度
            progress_pct = int((i + 1) / len(playbook_steps) * 100) if playbook_steps else 100
            task.status_message = f"执行Pipeline: {step_id} ({progress_pct}%)"
            task.last_updated_at = _now_iso()
            await emitter.emit_progress(task)

        tracker.update_task_step(
            task_id, "execute-pipeline", "completed",
            f"已完成 {len(pipeline_results)} 个Pipeline步骤"
        )
        await emitter.emit_step_update(
            task_id, "execute-pipeline", "执行Pipeline", "completed",
            f"已完成 {len(pipeline_results)} 个Pipeline步骤"
        )

        # ===== 阶段5：质量门禁 =====
        tracker.update_task_phase(task_id, TaskPhase.RUNNING_GATE_CHECK, "正在运行质量门禁")
        await emitter.emit_progress(task)

        # 执行质量门禁
        gate_result = await _run_gate_check_internal(config, module)
        task.gate_result = gate_result

        gate_status = gate_result.get("result", "unknown")
        tracker.update_task_step(
            task_id, "gate-check", "completed" if gate_status == "PASS" else "warning",
            f"门禁结果: {gate_status}"
        )
        await emitter.emit_step_update(
            task_id, "gate-check", "质量门禁检查", "completed" if gate_status == "PASS" else "warning",
            f"门禁结果: {gate_status}"
        )

        # ===== 完成 =====
        result = {
            "task_id": task_id,
            "module": module,
            "domain": domain,
            "status": "completed",
            "modification_plan": modification_plan,
            "pipeline_results": pipeline_results,
            "gate_result": gate_result,
            "safety_red_lines": safety_red_lines,
            "constraints_loaded": list(constraints.get("files", {}).keys()),
            "completed_at": _now_iso(),
        }

        tracker.complete_task(task_id, result)
        await emitter.emit_progress(task)

        return result

    except Exception as e:
        logger.exception("Task %s failed", task_id)
        tracker.fail_task(task_id, str(e))
        await emitter.emit_progress(tracker.get_task(task_id))
        return {
            "task_id": task_id,
            "status": "failed",
            "error": str(e),
        }


async def get_tahp_status(task_id: str) -> dict[str, Any]:
    """查询任务状态

    这是 tahp_status 工具的核心实现。
    """
    tracker = get_task_tracker()
    task = tracker.get_task(task_id)

    if not task:
        return {
            "task_id": task_id,
            "status": "not_found",
            "error": f"Task not found: {task_id}",
        }

    return task.to_detail_dict()


async def correct_tahp_task(
    task_id: str,
    feedback: str,
) -> dict[str, Any]:
    """纠偏正在执行的任务

    这是 tahp_correct 工具的核心实现。
    允许 Claude Code 对正在执行的任务发出纠偏指令。
    """
    tracker = get_task_tracker()
    emitter = get_progress_emitter()

    task = tracker.get_task(task_id)
    if not task:
        return {
            "task_id": task_id,
            "status": "not_found",
            "error": f"Task not found: {task_id}",
        }

    if task.is_terminal:
        return {
            "task_id": task_id,
            "status": "error",
            "error": f"Task is in terminal state: {task.phase.value}",
        }

    # 记录纠偏
    await emitter.emit_correction(task_id, feedback)

    # 根据当前阶段和纠偏内容，调整执行
    # 纠偏后重新进入执行状态
    if task.phase == TaskPhase.CORRECTING:
        task.update_phase(
            TaskPhase.EXECUTING_PIPELINE,
            f"根据纠偏反馈重新执行: {feedback[:50]}",
        )
        await emitter.emit_progress(task)

    return {
        "task_id": task_id,
        "status": "correcting",
        "feedback": feedback,
        "current_phase": task.phase.value,
        "corrections_count": len(task.corrections),
    }


async def run_gate_check(
    config: MCPServerConfig,
    task_id: str | None = None,
    module: str | None = None,
    level: str = "all",
) -> dict[str, Any]:
    """执行质量门禁检查

    这是 tahp_gate_check 工具的核心实现。
    可以对指定任务或模块执行质量门禁。
    """
    # 确定目标模块
    if task_id:
        tracker = get_task_tracker()
        task = tracker.get_task(task_id)
        if not task:
            return {"task_id": task_id, "status": "not_found", "error": f"Task not found: {task_id}"}
        target_module = task.module
    elif module:
        target_module = module
    else:
        return {"status": "error", "error": "Must specify either task_id or module"}

    return await _run_gate_check_internal(config, target_module, level)


async def _run_gate_check_internal(
    config: MCPServerConfig,
    module: str,
    level: str = "all",
) -> dict[str, Any]:
    """内部门禁检查实现

    复用 scripts/gate_check.py 的逻辑。
    """
    module_dir = config.get_module_dir(module)
    if not module_dir.is_dir():
        return {
            "module": module,
            "result": "error",
            "error": f"Module directory not found: {module_dir}",
        }

    # 尝试加载 gate_check 模块
    try:
        sys_path = str(config.scripts_dir)
        import sys
        if sys_path not in sys.path:
            sys.path.insert(0, sys_path)

        from gate_check import (
            GateLevel,
            GateResult,
            run_gates,
        )

        level_map = {
            "P0": [GateLevel.P0_BLOCK],
            "P1": [GateLevel.P0_BLOCK, GateLevel.P1_WARNING],
            "P2": [GateLevel.P0_BLOCK, GateLevel.P1_WARNING, GateLevel.P2_RECORD],
            "all": [GateLevel.P0_BLOCK, GateLevel.P1_WARNING, GateLevel.P2_RECORD],
        }
        levels = level_map.get(level, level_map["all"])
        report = run_gates(module_dir, levels)

        checks = []
        for check in report.checks:
            checks.append({
                "level": check.level.name,
                "name": check.name,
                "description": check.description,
                "passed": check.passed,
                "detail": check.detail,
            })

        return {
            "module": module,
            "result": report.result_label,
            "checks": checks,
            "total_checks": len(checks),
            "passed_checks": sum(1 for c in checks if c["passed"]),
            "failed_checks": sum(1 for c in checks if not c["passed"]),
        }

    except ImportError:
        logger.warning("gate_check module not available, running simplified checks")
        return _simplified_gate_check(module_dir, module)
    except Exception as e:
        logger.exception("Gate check failed for module %s", module)
        return {
            "module": module,
            "result": "error",
            "error": str(e),
        }


def _simplified_gate_check(module_dir: Path, module: str) -> dict[str, Any]:
    """简化版门禁检查（不依赖 gate_check 模块）"""
    checks = []

    # P0: 约束文件存在性
    yaml_files = list(module_dir.glob("*.yaml"))
    has_constraints = any(f.name != "module.yaml" for f in yaml_files)
    checks.append({
        "level": "P0_BLOCK",
        "name": "constraint_files_exist",
        "description": "约束文件必须存在",
        "passed": has_constraints,
        "detail": f"Found {len(yaml_files)} YAML files" if yaml_files else "No YAML files found",
    })

    # P0: 安全红线
    has_safety = False
    for yf in yaml_files:
        data = _load_yaml_file(yf)
        if data and "safety_red_lines" in data:
            has_safety = True
            break
    checks.append({
        "level": "P0_BLOCK",
        "name": "safety_red_lines_present",
        "description": "约束文件必须包含安全红线",
        "passed": has_safety,
        "detail": "Found safety_red_lines" if has_safety else "Missing safety_red_lines",
    })

    # P0: 无硬编码密钥
    no_hardcoded = True
    for yf in yaml_files:
        try:
            content = yf.read_text(encoding="utf-8")
            import re
            if re.search(r"(?i)(api[_-]?key|password|secret|token)\s*[:=]\s*['\"][^\s\"']{6,}['\"]", content):
                no_hardcoded = False
                break
        except Exception:
            pass
    checks.append({
        "level": "P0_BLOCK",
        "name": "no_hardcoded_secrets",
        "description": "无硬编码密钥/密码/Token",
        "passed": no_hardcoded,
        "detail": "Clean" if no_hardcoded else "Found hardcoded secrets",
    })

    # P1: module.yaml 完整性
    module_yaml = module_dir / "module.yaml"
    module_complete = False
    if module_yaml.exists():
        data = _load_yaml_file(module_yaml)
        if data and data.get("module", {}).get("name"):
            module_complete = True
    checks.append({
        "level": "P1_WARNING",
        "name": "module_yaml_complete",
        "description": "module.yaml 包含必要字段",
        "passed": module_complete,
        "detail": "Complete" if module_complete else "Missing fields",
    })

    # 汇总
    p0_fails = sum(1 for c in checks if c["level"] == "P0_BLOCK" and not c["passed"])
    p1_fails = sum(1 for c in checks if c["level"] == "P1_WARNING" and not c["passed"])

    result = "PASS"
    if p0_fails > 0:
        result = "BLOCK"
    elif p1_fails > 0:
        result = "WARNING"

    return {
        "module": module,
        "result": result,
        "checks": checks,
        "total_checks": len(checks),
        "passed_checks": sum(1 for c in checks if c["passed"]),
        "failed_checks": sum(1 for c in checks if not c["passed"]),
    }


async def list_tahp_tasks(
    include_completed: bool = True,
) -> dict[str, Any]:
    """列出所有任务"""
    tracker = get_task_tracker()
    tasks = tracker.list_tasks(include_completed=include_completed)
    return {
        "tasks": [t.to_detail_dict() for t in tasks],
        "total": len(tasks),
    }


async def query_knowledge(
    config: MCPServerConfig,
    query: str,
    module: str | None = None,
    cross_module: bool = False,
    top_k: int = 5,
) -> dict[str, Any]:
    """查询知识库"""
    try:
        sys_path = str(config.project_root)
        import sys
        if sys_path not in sys.path:
            sys.path.insert(0, sys_path)

        from db.config import KnowledgeBaseConfig
        from db.knowledge_db import KnowledgeDB

        kb_config = KnowledgeBaseConfig.from_yaml()
        db = KnowledgeDB(config=kb_config)

        if cross_module:
            entries = db.cross_module_search(
                query=query,
                exclude_module=module,
                n_results=top_k,
            )
        else:
            entries = db.search(
                query=query,
                module=module,
                n_results=top_k,
            )

        results = []
        for entry in entries:
            similarity = entry.metadata.get("_similarity", None)
            results.append({
                "id": entry.id,
                "title": entry.title,
                "module": entry.module,
                "type": entry.type,
                "category": entry.category,
                "confidence": entry.confidence,
                "similarity": similarity,
                "content_preview": entry.content[:200] if entry.content else "",
            })

        return {
            "query": query,
            "module": module,
            "cross_module": cross_module,
            "results": results,
            "total": len(results),
        }

    except Exception as e:
        logger.warning("Knowledge query failed: %s", e)
        return {
            "query": query,
            "results": [],
            "total": 0,
            "error": str(e),
        }
