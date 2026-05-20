# -*- coding: utf-8 -*-
"""进度事件发射模块

将任务进度变更事件通过 MCP 协议的 logging 通知机制
实时推送给客户端（如 Claude Code）。
"""

from __future__ import annotations

import logging
from typing import Any

from .tracker import TaskPhase, TaskProgress, get_task_tracker

logger = logging.getLogger("tahp-mcp-server.progress")


# 阶段到进度百分比的映射
_PHASE_PROGRESS_MAP = {
    TaskPhase.PENDING: 0.0,
    TaskPhase.LOADING_CONSTRAINTS: 0.15,
    TaskPhase.ANALYZING_DOCUMENT: 0.30,
    TaskPhase.GENERATING_PLAN: 0.45,
    TaskPhase.EXECUTING_PIPELINE: 0.75,
    TaskPhase.RUNNING_GATE_CHECK: 0.90,
    TaskPhase.COMPLETED: 1.0,
    TaskPhase.FAILED: 1.0,
    TaskPhase.CANCELLED: 1.0,
    TaskPhase.CORRECTING: 0.45,
}


class ProgressEmitter:
    """进度事件发射器

    通过 MCP logging 通知将进度推送给客户端。
    支持 Claude Code 的 stream-json 模式下的实时进度展示。
    """

    def __init__(self, mcp_server=None):
        self._server = mcp_server

    def set_server(self, server) -> None:
        """设置 MCP Server 实例（用于发送通知）"""
        self._server = server

    async def emit_progress(self, task: TaskProgress) -> None:
        """发射进度更新事件"""
        progress_data = {
            "type": "tahp_progress",
            "task_id": task.task_id,
            "phase": task.phase.value,
            "phase_label": task.phase_label,
            "progress": task.progress,
            "status_message": task.status_message,
            "steps": [
                {
                    "step_id": s.step_id,
                    "step_name": s.step_name,
                    "status": s.status,
                    "detail": s.detail,
                }
                for s in task.steps
            ],
        }

        # 通过 MCP logging 通知发送
        if self._server:
            try:
                await self._server.request_context.session.send_log_message(
                    level="info",
                    data=f"[TAHP] {task.phase_label} ({task.progress:.0%}) - {task.status_message}",
                )
            except Exception as e:
                logger.debug("Failed to send MCP log message: %s", e)

        logger.info(
            "Task %s: %s (%.0f%%) - %s",
            task.task_id,
            task.phase.value,
            task.progress * 100,
            task.status_message,
        )

    async def emit_step_update(
        self,
        task_id: str,
        step_id: str,
        step_name: str,
        status: str,
        detail: str = "",
    ) -> None:
        """发射步骤更新事件"""
        tracker = get_task_tracker()
        tracker.update_task_step(task_id, step_id, status, detail)

        task = tracker.get_task(task_id)
        if task:
            # 根据步骤完成情况更新整体进度
            completed_steps = sum(1 for s in task.steps if s.status == "completed")
            total_steps = len(task.steps)
            if total_steps > 0:
                step_progress = completed_steps / total_steps
                # 映射到整体进度范围
                base = _PHASE_PROGRESS_MAP.get(task.phase, 0.0)
                next_base = _get_next_phase_progress(task.phase)
                task.progress = base + (next_base - base) * step_progress
                task.last_updated_at = _now_iso()

            await self.emit_progress(task)

    async def emit_correction(self, task_id: str, feedback: str) -> None:
        """发射纠偏事件"""
        tracker = get_task_tracker()
        task = tracker.get_task(task_id)
        if task:
            task.add_correction(feedback)
            task.update_phase(TaskPhase.CORRECTING, f"收到纠偏: {feedback[:50]}")

            if self._server:
                try:
                    await self._server.request_context.session.send_log_message(
                        level="warning",
                        data=f"[TAHP] 纠偏请求: {feedback[:100]}",
                    )
                except Exception:
                    pass

            await self.emit_progress(task)

    def format_progress_table(self, task: TaskProgress) -> str:
        """格式化进度为 Markdown 表格"""
        lines = [
            f"## TAHP 任务进度",
            f"",
            f"- **任务ID**: {task.task_id}",
            f"- **模块**: {task.module}",
            f"- **领域**: {task.domain}",
            f"- **当前阶段**: {task.phase_label}",
            f"- **整体进度**: {task.progress:.0%}",
            f"",
            f"| 步骤 | 状态 | 说明 |",
            f"|------|------|------|",
        ]
        for step in task.steps:
            status_icon = {
                "pending": "⏳",
                "running": "🔄",
                "completed": "✅",
                "failed": "❌",
                "skipped": "⏭️",
            }.get(step.status, "❓")
            lines.append(f"| {step.step_name} | {status_icon} {step.status} | {step.detail} |")

        if task.error:
            lines.append(f"")
            lines.append(f"**错误**: {task.error}")

        if task.gate_result:
            lines.append(f"")
            lines.append(f"**门禁结果**: {task.gate_result.get('result', 'unknown')}")

        return "\n".join(lines)


def _get_next_phase_progress(phase: TaskPhase) -> float:
    """获取下一个阶段的基准进度"""
    phases = list(_PHASE_PROGRESS_MAP.keys())
    try:
        idx = phases.index(phase)
        if idx + 1 < len(phases):
            return _PHASE_PROGRESS_MAP[phases[idx + 1]]
    except ValueError:
        pass
    return 1.0


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# 全局单例
_progress_emitter: ProgressEmitter | None = None


def get_progress_emitter() -> ProgressEmitter:
    """获取全局进度发射器实例"""
    global _progress_emitter
    if _progress_emitter is None:
        _progress_emitter = ProgressEmitter()
    return _progress_emitter
