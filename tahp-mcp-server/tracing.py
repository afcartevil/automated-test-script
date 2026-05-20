"""MCP Server 交互追踪日志

记录每次工具调用的详细信息到 JSONL 文件，用于：
- 调试和问题排查
- 性能分析（工具调用耗时）
- 使用模式统计（哪个工具被调用最频繁）
- EvoSkill 进化数据采集

输出目录: reports/traces/
文件格式: trace-{YYYY-MM-DD}.jsonl
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class TraceRecord:
    """单次工具调用的追踪记录"""

    timestamp: str
    tool_name: str
    arguments_summary: str  # 参数摘要（截断敏感信息）
    duration_ms: float
    status: str  # 'success' | 'error' | 'not_found'
    result_summary: str  # 结果摘要
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "tool_name": self.tool_name,
            "arguments_summary": self.arguments_summary,
            "duration_ms": round(self.duration_ms, 2),
            "status": self.status,
            "result_summary": self.result_summary,
            "error_message": self.error_message,
        }


class InteractionTracer:
    """工具调用追踪器

    用法:
        tracer = InteractionTracer(base_dir=project_root)
        tracer.start("tahp_execute", {"module": "telephony"})
        # ... 执行工具 ...
        tracer.end(success=True, result={"status": "completed"})
    """

    def __init__(self, base_dir: Path | str, enabled: bool = True):
        self._base_dir = Path(base_dir)
        self._enabled = enabled
        self._start_time: float = 0.0
        self._current_tool: str = ""
        self._current_args: dict[str, Any] = {}

    @property
    def _output_dir(self) -> Path:
        d = self._base_dir / "reports" / "traces"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _today_file(self) -> Path:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._output_dir / f"trace-{today}.jsonl"

    def start(self, tool_name: str, arguments: dict[str, Any]) -> None:
        """开始追踪一个工具调用"""
        if not self._enabled:
            return
        self._start_time = time.perf_counter()
        self._current_tool = tool_name
        self._current_args = arguments

    def end(self, success: bool, result: dict[str, Any] | None = None,
            error_message: str = "") -> None:
        """结束追踪并写入记录"""
        if not self._enabled or not self._current_tool:
            return

        duration_ms = (time.perf_counter() - self._start_time) * 1000

        args_summary = self._summarize_args(self._current_args)
        result_summary = self._summarize_result(result or {})

        record = TraceRecord(
            timestamp=datetime.now(timezone.utc).isoformat(),
            tool_name=self._current_tool,
            arguments_summary=args_summary,
            duration_ms=duration_ms,
            status="success" if success else "error",
            result_summary=result_summary,
            error_message=error_message[:200] if error_message else "",
        )

        self._write_record(record)
        self._reset()

    def _write_record(self, record: TraceRecord) -> None:
        """追加写入一条追踪记录"""
        filepath = self._today_file()
        try:
            with open(filepath, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except OSError:
            pass  # 追踪记录写入失败不应影响主流程

    def _reset(self) -> None:
        self._start_time = 0.0
        self._current_tool = ""
        self._current_args = {}

    @staticmethod
    def _summarize_args(args: dict[str, Any]) -> str:
        """生成参数摘要（截断长字符串，过滤敏感信息）"""
        parts = []
        for k, v in args.items():
            if k.lower() in ("api_key", "password", "token", "secret"):
                parts.append(f"{k}=***")
                continue
            sv = str(v)
            if len(sv) > 100:
                sv = sv[:100] + "..."
            parts.append(f"{k}={sv}")
        return "; ".join(parts[:5])

    @staticmethod
    def _summarize_result(result: dict[str, Any]) -> str:
        """生成结果摘要"""
        if not result:
            return "{}"
        # 优先显示 status/result 字段
        for key in ("status", "result", "error"):
            if key in result:
                return f"{key}={result[key]}"
        # 显示键的数量
        return f"keys={list(result.keys())[:5]}"


# 全局追踪器实例（单例模式）
_tracer: InteractionTracer | None = None


def get_tracer(base_dir: Path | str | None = None) -> InteractionTracer:
    """获取全局追踪器实例"""
    global _tracer
    if _tracer is None:
        if base_dir is None:
            # 自动检测项目根目录
            base_dir = Path(__file__).resolve().parent.parent
        _tracer = InteractionTracer(base_dir)
    return _tracer
