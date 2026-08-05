"""flow/game 子 skill 调试日志：作用 / 输入 / 输出 → game_test.log。

开关（任一开启即可）：
  - 环境变量 GAME_SKILL_DEBUG=1|true|yes|on
  - CLI 参数 --debug-log
关闭：
  - GAME_SKILL_DEBUG=0|false|no|off
  - CLI --no-debug-log（优先级高于开启）

日志路径：
  - 环境变量 GAME_SKILL_DEBUG_LOG（可选）
  - 默认：flow/game/game_test.log
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


_LOCK = threading.Lock()
_ENABLED: bool | None = None
_LOG_PATH: Path | None = None

_FLOW_GAME_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LOG = _FLOW_GAME_ROOT / "game_test.log"

# skill 作用说明（调试用）
SKILL_PURPOSE: dict[str, str] = {
    "mtk_kernellog_convert": "将 kernel 相对时间转为绝对时间 *_linli_666.txt，供后续对齐",
    "game_time_window": "识别游戏前台 T_game / T_pre / T_post，检查 kernel/main/sys 覆盖",
    "game_precondition": "对照测试用例检测前置条件（网络/亮度/音量等）",
    "game_power_model": "输出游戏功耗拆解模型框架（子系统与归因分类）",
    "game_brightness": "亮度/自动背光/背光2.0/AAL/温控降亮/刷新率分析",
    "game_volume": "测试音量与游戏内音量变化分析",
    "game_cpu_gpu_ddr": "CPU/GPU/DDR/帧率/perfLock 等分析（可含 trace）",
    "game_kernel_cpu": "Kernel [K] CPU 与异常线程统计",
    "game_background": "后台自启动/下载/GC/服务唤醒分析",
    "game_network": "WiFi/蜂窝信号与数传/RF 排查",
    "game_thermal": "温升、降背光、限频等 thermal 影响分析",
    "game_trace": "解析 perf-statistic.html / trace 频率与限频线索",
    "game_summary": "合并各维证据，输出 compare_summary 与 game_power_report.html",
    "game_current_log_correlate": "pt5/电流抬高窗与日志关联归因（无 pt5 可 skipped）",
    "game_current_waveform": "（已移除）请用 DOU current_cpu_spike / run_game_current_cpu_spike",
    "game_current_cpu_spike": "电流图双机对比（接入 DOU current_cpu_spike，嵌入异常问题第1项）",
    "game_diagnosis_report": "确认功耗差 + 初步诊断 + AI 建议，写入澄清报告",
    "game_root_cause": "按 YAML 五类规则判断原因并渲染澄清报告",
    "game_power_delta": "确认 I1 / 已知差 / 电流图分流（diagnosis 子模块）",
    "game_ai_insights": "基于证据合成 AI 判断与下一步建议（diagnosis 子模块）",
}


def _env_bool(name: str) -> bool | None:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return None
    return str(raw).strip().lower() in {"1", "true", "yes", "on", "y"}


def default_log_path() -> Path:
    custom = os.environ.get("GAME_SKILL_DEBUG_LOG", "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    return _DEFAULT_LOG.resolve()


def is_debug_enabled() -> bool:
    global _ENABLED
    if _ENABLED is not None:
        return _ENABLED
    env = _env_bool("GAME_SKILL_DEBUG")
    return bool(env) if env is not None else False


def configure_debug(
    *,
    enabled: bool | None = None,
    log_path: str | Path | None = None,
    reset_file: bool = False,
) -> None:
    """配置调试开关与日志文件。reset_file=True 时清空已有 game_test.log。"""
    global _ENABLED, _LOG_PATH
    if enabled is not None:
        _ENABLED = bool(enabled)
    if log_path is not None:
        _LOG_PATH = Path(log_path).expanduser().resolve()
    elif _LOG_PATH is None:
        _LOG_PATH = default_log_path()
    if reset_file and is_debug_enabled():
        path = _LOG_PATH or default_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# game skill debug log\n# started {datetime.now().isoformat(timespec='seconds')}\n\n",
            encoding="utf-8",
        )


def add_debug_log_arguments(parser: argparse.ArgumentParser) -> None:
    g = parser.add_argument_group("debug log")
    g.add_argument(
        "--debug-log",
        action="store_true",
        help="开启 skill 调试日志（写入 game_test.log；也可用环境变量 GAME_SKILL_DEBUG=1）",
    )
    g.add_argument(
        "--no-debug-log",
        action="store_true",
        help="关闭 skill 调试日志（覆盖 GAME_SKILL_DEBUG）",
    )
    g.add_argument(
        "--debug-log-file",
        default="",
        help="调试日志路径，默认 flow/game/game_test.log",
    )


def apply_debug_from_args(args: argparse.Namespace, *, reset_file: bool = False) -> bool:
    """根据 CLI 参数应用调试配置，返回是否开启。"""
    enabled: bool | None = None
    if getattr(args, "no_debug_log", False):
        enabled = False
    elif getattr(args, "debug_log", False):
        enabled = True
    log_file = getattr(args, "debug_log_file", "") or None
    configure_debug(enabled=enabled, log_path=log_file, reset_file=reset_file and bool(enabled or is_debug_enabled()))
    # if only --debug-log-file given, keep env/default enabled state
    if enabled is None and log_file:
        configure_debug(log_path=log_file)
    return is_debug_enabled()


def _log_path() -> Path:
    global _LOG_PATH
    if _LOG_PATH is None:
        _LOG_PATH = default_log_path()
    return _LOG_PATH


def _safe_json(obj: Any, *, max_chars: int = 12000) -> str:
    try:
        text = json.dumps(obj, ensure_ascii=False, indent=2, default=str)
    except Exception as exc:  # noqa: BLE001
        text = f"<unserializable: {exc}; repr={obj!r:.500}>"
    if len(text) > max_chars:
        return text[: max_chars - 20] + f"\n... <truncated {len(text) - max_chars + 20} chars>"
    return text


def _summarize_output(obj: Any) -> Any:
    """压缩大体量输出，保留关键字段便于调试。"""
    if not isinstance(obj, dict):
        return obj
    out: dict[str, Any] = {}
    for key in (
        "status",
        "skill",
        "game_name",
        "game_package",
        "log_path",
        "analysis_dir",
        "html_output",
        "triggered_count",
        "total_rules",
        "summary",
    ):
        if key in obj:
            out[key] = obj.get(key)
    if "game_window" in obj:
        out["game_window"] = obj.get("game_window")
    if "time_windows" in obj:
        out["time_windows"] = obj.get("time_windows")
    if "primary_causes" in obj:
        out["primary_causes"] = obj.get("primary_causes")
    if "routing" in obj:
        out["routing"] = obj.get("routing")
    if "delta_power_ma_i1" in obj:
        out["delta_power_ma_i1"] = obj.get("delta_power_ma_i1")
    # always include top-level keys inventory
    out["_keys"] = sorted(obj.keys())
    out["_approx_json_bytes"] = len(json.dumps(obj, ensure_ascii=False, default=str))
    return out


def write_debug(message: str) -> None:
    if not is_debug_enabled():
        return
    path = _log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = message if message.endswith("\n") else message + "\n"
    with _LOCK:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line)


def log_skill_start(
    skill_name: str,
    *,
    purpose: str | None = None,
    inputs: Any = None,
) -> None:
    if not is_debug_enabled():
        return
    purpose_text = purpose or SKILL_PURPOSE.get(skill_name, "")
    ts = datetime.now().isoformat(timespec="seconds")
    write_debug("=" * 88)
    write_debug(f"[{ts}] SKILL START: {skill_name}")
    write_debug(f"PURPOSE: {purpose_text}")
    write_debug("INPUT:")
    write_debug(_safe_json(inputs if inputs is not None else {}))


def log_skill_end(
    skill_name: str,
    outputs: Any = None,
    *,
    output_path: str | Path | None = None,
    ok: bool = True,
    full_output: bool = False,
) -> None:
    if not is_debug_enabled():
        return
    ts = datetime.now().isoformat(timespec="seconds")
    write_debug(f"[{ts}] SKILL END: {skill_name} ok={ok}")
    if output_path:
        write_debug(f"OUTPUT_PATH: {output_path}")
    payload = outputs if full_output else _summarize_output(outputs) if isinstance(outputs, dict) else outputs
    write_debug("OUTPUT:")
    write_debug(_safe_json(payload if payload is not None else {}))
    write_debug("")


def log_skill_note(skill_name: str, note: str) -> None:
    if not is_debug_enabled():
        return
    write_debug(f"NOTE[{skill_name}]: {note}")


def debug_begin(args: argparse.Namespace, skill_name: str, *, inputs: Any = None, reset_file: bool = False) -> bool:
    """CLI 入口：应用开关并打印 START。"""
    enabled = apply_debug_from_args(args, reset_file=reset_file)
    payload = inputs if inputs is not None else {k: getattr(args, k) for k in vars(args)}
    log_skill_start(skill_name, inputs=payload)
    return enabled


def debug_end(
    skill_name: str,
    outputs: Any = None,
    *,
    output_path: str | Path | None = None,
    ok: bool = True,
    full_output: bool = False,
) -> None:
    """CLI 出口：打印 END。"""
    log_skill_end(
        skill_name,
        outputs=outputs,
        output_path=output_path,
        ok=ok,
        full_output=full_output,
    )


class SkillDebugSession:
    """with SkillDebugSession(...): ... ; session.finish(result)"""

    def __init__(
        self,
        skill_name: str,
        *,
        purpose: str | None = None,
        inputs: Any = None,
        output_path: str | Path | None = None,
        full_output: bool = False,
    ) -> None:
        self.skill_name = skill_name
        self.purpose = purpose
        self.inputs = inputs
        self.output_path = output_path
        self.full_output = full_output
        self._ok = True
        self._outputs: Any = None

    def __enter__(self) -> "SkillDebugSession":
        log_skill_start(self.skill_name, purpose=self.purpose, inputs=self.inputs)
        return self

    def finish(self, outputs: Any = None, *, ok: bool = True, output_path: str | Path | None = None) -> None:
        self._outputs = outputs
        self._ok = ok
        if output_path is not None:
            self.output_path = output_path

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        ok = self._ok and exc_type is None
        outputs = self._outputs
        if exc_type is not None:
            outputs = {
                "error_type": getattr(exc_type, "__name__", str(exc_type)),
                "error": str(exc),
                "partial_output": _summarize_output(outputs) if isinstance(outputs, dict) else outputs,
            }
        log_skill_end(
            self.skill_name,
            outputs=outputs,
            output_path=self.output_path,
            ok=ok,
            full_output=self.full_output,
        )
        return False
