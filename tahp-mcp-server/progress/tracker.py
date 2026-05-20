# -*- coding: utf-8 -*-
"""进度追踪模块

管理 TAHP 任务的执行状态、进度百分比、阶段信息，
支持外部轮询查询和事件驱动通知。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable


class TaskPhase(str, Enum):
    """任务执行阶段"""
    PENDING = "pending"
    LOADING_CONSTRAINTS = "loading_constraints"
    ANALYZING_DOCUMENT = "analyzing_document"
    GENERATING_PLAN = "generating_plan"
    EXECUTING_PIPELINE = "executing_pipeline"
    RUNNING_GATE_CHECK = "running_gate_check"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    CORRECTING = "correcting"


class TaskStatus(str, Enum):
    """MCP Tasks 兼容的状态枚举"""
    WORKING = "working"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INPUT_REQUIRED = "input_required"


# Phase 到 TaskStatus 的映射
_PHASE_TO_STATUS = {
    TaskPhase.PENDING: TaskStatus.WORKING,
    TaskPhase.LOADING_CONSTRAINTS: TaskStatus.WORKING,
    TaskPhase.ANALYZING_DOCUMENT: TaskStatus.WORKING,
    TaskPhase.GENERATING_PLAN: TaskStatus.WORKING,
    TaskPhase.EXECUTING_PIPELINE: TaskStatus.WORKING,
    TaskPhase.RUNNING_GATE_CHECK: TaskStatus.WORKING,
    TaskPhase.COMPLETED: TaskStatus.COMPLETED,
    TaskPhase.FAILED: TaskStatus.FAILED,
    TaskPhase.CANCELLED: TaskStatus.CANCELLED,
    TaskPhase.CORRECTING: TaskStatus.INPUT_REQUIRED,
}


# Phase 的中文描述
_PHASE_LABELS = {
    TaskPhase.PENDING: "等待执行",
    TaskPhase.LOADING_CONSTRAINTS: "正在加载约束文件",
    TaskPhase.ANALYZING_DOCUMENT: "正在分析设计文档",
    TaskPhase.GENERATING_PLAN: "正在生成修改计划",
    TaskPhase.EXECUTING_PIPELINE: "正在执行Pipeline",
    TaskPhase.RUNNING_GATE_CHECK: "正在运行质量门禁",
    TaskPhase.COMPLETED: "执行完成",
    TaskPhase.FAILED: "执行失败",
    TaskPhase.CANCELLED: "已取消",
    TaskPhase.CORRECTING: "等待纠偏输入",
}


@dataclass
class StepProgress:
    """单个步骤的进度"""
    step_id: str
    step_name: str
    status: str = "pending"  # pending, running, completed, failed, skipped
    detail: str = ""
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class TaskProgress:
    """任务进度追踪"""
    task_id: str
    module: str
    domain: str
    document_path: str

    # 当前状态
    phase: TaskPhase = TaskPhase.PENDING
    progress: float = 0.0  # 0.0 - 1.0
    status_message: str = ""

    # 时间戳
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    last_updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))

    # 步骤列表
    steps: list[StepProgress] = field(default_factory=list)

    # 执行结果
    result: dict[str, Any] | None = None
    error: str | None = None

    # 纠偏历史
    corrections: list[dict[str, Any]] = field(default_factory=list)

    # 门禁结果
    gate_result: dict[str, Any] | None = None

    # 轮询间隔（毫秒）
    poll_interval: int = 3000

    @property
    def status(self) -> TaskStatus:
        """获取MCP兼容的状态"""
        return _PHASE_TO_STATUS.get(self.phase, TaskStatus.WORKING)

    @property
    def phase_label(self) -> str:
        """获取阶段的中文标签"""
        return _PHASE_LABELS.get(self.phase, str(self.phase))

    @property
    def is_terminal(self) -> bool:
        """是否处于终态"""
        return self.phase in (TaskPhase.COMPLETED, TaskPhase.FAILED, TaskPhase.CANCELLED)

    def update_phase(self, phase: TaskPhase, message: str = "", progress_delta: float = 0.0) -> None:
        """更新任务阶段"""
        self.phase = phase
        if message:
            self.status_message = message
        elif not self.status_message:
            self.status_message = self.phase_label
        self.progress = min(1.0, self.progress + progress_delta)
        self.last_updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def add_step(self, step_id: str, step_name: str) -> StepProgress:
        """添加执行步骤"""
        step = StepProgress(step_id=step_id, step_name=step_name)
        self.steps.append(step)
        return step

    def update_step(self, step_id: str, status: str, detail: str = "") -> None:
        """更新步骤状态"""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for step in self.steps:
            if step.step_id == step_id:
                step.status = status
                if detail:
                    step.detail = detail
                if status == "running" and not step.started_at:
                    step.started_at = now
                if status in ("completed", "failed", "skipped"):
                    step.completed_at = now
                break
        self.last_updated_at = now

    def add_correction(self, feedback: str, result: str = "pending") -> None:
        """记录纠偏"""
        self.corrections.append({
            "feedback": feedback,
            "result": result,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        })

    def to_mcp_task_data(self) -> dict[str, Any]:
        """转为 MCP Tasks 协议格式"""
        return {
            "taskId": self.task_id,
            "status": self.status.value,
            "statusMessage": self.status_message or self.phase_label,
            "progress": self.progress,
            "createdAt": self.created_at,
            "lastUpdatedAt": self.last_updated_at,
            "pollInterval": self.poll_interval,
        }

    def to_detail_dict(self) -> dict[str, Any]:
        """转为详细信息字典"""
        return {
            "task_id": self.task_id,
            "module": self.module,
            "domain": self.domain,
            "document_path": self.document_path,
            "phase": self.phase.value,
            "phase_label": self.phase_label,
            "progress": self.progress,
            "status": self.status.value,
            "status_message": self.status_message,
            "created_at": self.created_at,
            "last_updated_at": self.last_updated_at,
            "steps": [
                {
                    "step_id": s.step_id,
                    "step_name": s.step_name,
                    "status": s.status,
                    "detail": s.detail,
                }
                for s in self.steps
            ],
            "corrections": self.corrections,
            "is_terminal": self.is_terminal,
            "error": self.error,
            "result": self.result,
            "gate_result": self.gate_result,
        }


class TaskTracker:
    """全局任务追踪器（线程安全）"""

    def __init__(self, max_tasks: int = 100):
        self._tasks: dict[str, TaskProgress] = {}
        self._lock = threading.Lock()
        self._max_tasks = max_tasks
        self._listeners: list[Callable[[str, TaskPhase, str], None]] = []

    def create_task(
        self,
        module: str,
        domain: str,
        document_path: str,
    ) -> TaskProgress:
        """创建新任务"""
        task_id = f"tahp-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"
        progress = TaskProgress(
            task_id=task_id,
            module=module,
            domain=domain,
            document_path=document_path,
        )
        with self._lock:
            if len(self._tasks) >= self._max_tasks:
                # 清理最早的已完成任务
                self._cleanup_old_tasks()
            self._tasks[task_id] = progress
        return progress

    def get_task(self, task_id: str) -> TaskProgress | None:
        """获取任务"""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, include_completed: bool = True) -> list[TaskProgress]:
        """列出所有任务"""
        with self._lock:
            tasks = list(self._tasks.values())
        if not include_completed:
            tasks = [t for t in tasks if not t.is_terminal]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def update_task_phase(
        self,
        task_id: str,
        phase: TaskPhase,
        message: str = "",
        progress_delta: float = 0.0,
    ) -> TaskProgress | None:
        """更新任务阶段"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.update_phase(phase, message, progress_delta)
                # 通知监听器
                for listener in self._listeners:
                    try:
                        listener(task_id, phase, message)
                    except Exception:
                        pass
                return task
        return None

    def update_task_step(
        self,
        task_id: str,
        step_id: str,
        status: str,
        detail: str = "",
    ) -> None:
        """更新任务步骤"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.update_step(step_id, status, detail)

    def fail_task(self, task_id: str, error: str) -> TaskProgress | None:
        """标记任务失败"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.phase = TaskPhase.FAILED
                task.error = error
                task.status_message = f"执行失败: {error}"
                task.last_updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                return task
        return None

    def complete_task(self, task_id: str, result: dict[str, Any]) -> TaskProgress | None:
        """标记任务完成"""
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.phase = TaskPhase.COMPLETED
                task.result = result
                task.progress = 1.0
                task.status_message = "执行完成"
                task.last_updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                return task
        return None

    def add_listener(self, listener: Callable[[str, TaskPhase, str], None]) -> None:
        """添加状态变更监听器"""
        self._listeners.append(listener)

    def _cleanup_old_tasks(self) -> None:
        """清理已完成的旧任务"""
        terminal_ids = [
            tid for tid, t in self._tasks.items() if t.is_terminal
        ]
        # 按时间排序，保留最新的
        terminal_ids.sort(
            key=lambda tid: self._tasks[tid].last_updated_at,
            reverse=True,
        )
        # 删除超过一半的旧任务
        for tid in terminal_ids[len(terminal_ids) // 2:]:
            del self._tasks[tid]


# 全局单例
_task_tracker: TaskTracker | None = None


def get_task_tracker() -> TaskTracker:
    """获取全局任务追踪器实例"""
    global _task_tracker
    if _task_tracker is None:
        _task_tracker = TaskTracker()
    return _task_tracker
