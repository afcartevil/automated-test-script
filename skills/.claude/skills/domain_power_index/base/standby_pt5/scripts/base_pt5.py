"""通过 Cursor 设置中的 PT5 MCP 服务读取并解析 .pt5 文件。"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

DEFAULT_MCP_CONFIG = Path.home() / ".cursor" / "mcp.json"
PT5_SERVER_NAME = "pt5"

_MAX_CHART_POINTS = 400
_MAX_LOAD_POINTS = 500_000
_DEFAULT_WINDOW_SEC = 10.0
_DEFAULT_WINDOW_STEP_SEC = 2.0
_DEFAULT_TOP_WINDOWS = 1
_BASELINE_PERCENTILE = 10.0
_BASELINE_TRIM_START_SEC = 10.0
_BASELINE_TRIM_END_SEC = 5.0


def load_pt5_server_params(config_path: Path | None = None) -> StdioServerParameters:
    """从 Cursor MCP 配置读取 PT5 服务启动参数。"""
    config_path = config_path or DEFAULT_MCP_CONFIG
    if not config_path.exists():
        raise FileNotFoundError(f"未找到 MCP 配置文件: {config_path}")

    with config_path.open(encoding="utf-8") as f:
        config = json.load(f)

    servers = config.get("mcpServers", {})
    if PT5_SERVER_NAME not in servers:
        raise KeyError(f"MCP 配置中未找到 '{PT5_SERVER_NAME}' 服务")

    server = servers[PT5_SERVER_NAME]
    command = server["command"]
    args = server.get("args", [])
    cwd = server.get("cwd")

    if not args and command.lower().endswith((".cmd", ".bat")):
        return StdioServerParameters(command=command, args=[], cwd=cwd)

    return StdioServerParameters(command=command, args=args, cwd=cwd)


def _tool_text(result: Any) -> str:
    parts: list[str] = []
    for block in result.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _tool_json(result: Any) -> dict[str, Any]:
    text = _tool_text(result)
    if not text:
        return {}
    return json.loads(text)


def _sec_to_rel_time(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def find_pt5_file(log_path: str | Path) -> Path | None:
    """从日志路径向上查找工作区 downloads/ 内的 .pt5，或直接接受 .pt5 文件路径。"""
    path = Path(log_path).resolve()
    if path.is_file() and path.suffix.lower() == ".pt5":
        return path
    if path.is_file():
        path = path.parent

    workspace = path
    for _ in range(8):
        downloads = workspace / "downloads"
        if downloads.is_dir():
            pt5_files = list(downloads.rglob("*.pt5"))
            if pt5_files:
                return max(pt5_files, key=lambda p: p.stat().st_mtime)
        if workspace.parent == workspace:
            break
        workspace = workspace.parent

    pt5_files = list(path.rglob("*.pt5"))
    if pt5_files:
        return max(pt5_files, key=lambda p: p.stat().st_mtime)
    return None


def _parse_capture_datetime(capture_date: str | None) -> datetime | None:
    if not capture_date or capture_date == "unknown":
        return None
    text = str(capture_date).split(" (")[0].strip().replace("T", " ")
    text = text.replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _format_datetime(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def _offset_to_abs_time(capture_start: datetime | None, offset_sec: float) -> str | None:
    if capture_start is None:
        return None
    return _format_datetime(capture_start + timedelta(seconds=float(offset_sec)))


def _find_yaml_for_pt5(pt5_path: Path) -> Path | None:
    test_id = pt5_path.name.split("_", 1)[0]
    for root in (pt5_path.parent, *pt5_path.parents):
        if not root.is_dir():
            continue
        exact = root / f"{pt5_path.stem}.yaml"
        if exact.is_file():
            return exact
        matches = sorted(root.glob(f"{test_id}*.yaml"))
        if matches:
            return matches[0]
    return None


def _load_yaml_collect_times(yaml_path: Path) -> dict[str, datetime] | None:
    text = yaml_path.read_text(encoding="utf-8", errors="ignore")
    out: dict[str, datetime] = {}
    for key in ("collect_start_time", "collect_end_time"):
        m = re.search(rf"^{key}:\s*['\"]?([^'\"\n]+)", text, re.MULTILINE)
        if not m:
            continue
        dt = _parse_capture_datetime(m.group(1).strip())
        if dt is not None:
            out[key] = dt
    return out or None


def _resolve_capture_times(
    *,
    summary: dict[str, Any],
    loaded: dict[str, Any],
    yaml_times: dict[str, datetime] | None,
) -> tuple[datetime | None, datetime | None]:
    if yaml_times and "collect_start_time" in yaml_times and "collect_end_time" in yaml_times:
        start = yaml_times["collect_start_time"]
        end = yaml_times["collect_end_time"]
        if end > start:
            return start, end

    capture_start = _parse_capture_datetime(summary.get("captureDate"))
    if capture_start is None:
        return None, None

    times = loaded.get("times")
    if isinstance(times, np.ndarray) and times.size > 0:
        end_offset = float(times[-1])
    else:
        end_offset = float(summary.get("durationSec") or loaded.get("duration_sec") or 0)

    if end_offset <= 0:
        end_offset = float(summary.get("durationSec") or 0)

    capture_end = capture_start + timedelta(seconds=end_offset)
    if capture_end <= capture_start and end_offset > 0:
        capture_end = capture_start + timedelta(seconds=end_offset)
    return capture_start, capture_end


def _window_abs_times(
    capture_start: datetime | None,
    window: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    if not window or capture_start is None:
        return None, None
    start_sec = float(window["start_sec"])
    end_sec = float(window.get("end_sec", start_sec))
    if end_sec <= start_sec:
        end_sec = start_sec + float(window.get("duration_sec") or _DEFAULT_WINDOW_SEC)
    return _offset_to_abs_time(capture_start, start_sec), _offset_to_abs_time(capture_start, end_sec)


def _first_window(windows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return windows[0] if windows else None


def _avg_current_from_summary(summary: dict[str, Any]) -> float | None:
    main = summary.get("mainChannel") or {}
    avg = main.get("avgCurrentMA")
    if avg is not None:
        return round(float(avg), 2)
    return None


def build_standby_output(
    *,
    pt5_file: str,
    summary: dict[str, Any],
    analysis: dict[str, Any],
    loaded: dict[str, Any],
    yaml_times: dict[str, datetime] | None = None,
) -> dict[str, Any]:
    """将 MCP 摘要与电流分析结果转为 standby flow 结构化字段。"""
    if not analysis.get("success"):
        return {"success": False, "pt5_file": pt5_file, "error": analysis.get("error", "分析失败")}

    current_summary = analysis.get("current_summary") or {}
    baseline = current_summary.get("baseline") or {}

    stdby_curr_ma = _avg_current_from_summary(summary)
    if stdby_curr_ma is None:
        stdby_curr_ma = current_summary.get("avg_ma")

    base_curr_ma = current_summary.get("avg_baseline_ma")
    if base_curr_ma is None:
        base_curr_ma = baseline.get("avg_baseline_ma") or baseline.get("min_ma")

    capture_start, capture_end = _resolve_capture_times(
        summary=summary,
        loaded=loaded,
        yaml_times=yaml_times,
    )
    capture_time_start = _format_datetime(capture_start)
    capture_time_end = _format_datetime(capture_end)

    min_win = _first_window(analysis.get("low_power_windows") or [])
    max_win = _first_window(analysis.get("high_power_windows") or [])
    min_start, min_end = _window_abs_times(capture_start, min_win)
    max_start, max_end = _window_abs_times(capture_start, max_win)

    out: dict[str, Any] = {
        "success": True,
        "pt5_file": pt5_file,
        "stdby_curr_ma": stdby_curr_ma,
        "stdby_curr_source": "pt5" if not yaml_times else "pt5+yaml",
        "base_curr_ma": base_curr_ma,
        "capture_time_start": capture_time_start,
        "capture_time_end": capture_time_end,
        "min_power_value": min_win.get("mean_ma") if min_win else None,
        "min_power_time_start": min_start,
        "min_power_time_end": min_end,
        "max_power_value": max_win.get("mean_ma") if max_win else None,
        "max_power_time_start": max_start,
        "max_power_time_end": max_end,
    }
    if capture_time_start is None:
        if min_win:
            out["min_power_time_start"] = _sec_to_rel_time(float(min_win["start_sec"]))
            out["min_power_time_end"] = _sec_to_rel_time(float(min_win["end_sec"]))
        if max_win:
            out["max_power_time_start"] = _sec_to_rel_time(float(max_win["start_sec"]))
            out["max_power_time_end"] = _sec_to_rel_time(float(max_win["end_sec"]))
    return out


def format_standby_text(result: dict[str, Any]) -> str:
    if not result.get("success"):
        return f"error: {result.get('error', 'unknown')}"
    keys = [
        "stdby_curr_ma",
        "base_curr_ma",
        "capture_time_start",
        "capture_time_end",
        "min_power_value",
        "min_power_time_start",
        "min_power_time_end",
        "max_power_value",
        "max_power_time_start",
        "max_power_time_end",
        "pt5_file",
    ]
    lines = [f"{key}: {result.get(key)}" for key in keys]
    return "\n".join(lines)


def _channel_current_key(channel: str) -> str:
    mapping = {"main": "main_current_mA", "usb": "usb_current_mA", "aux": "aux_current_mA"}
    return mapping.get(channel, "main_current_mA")


def _slice_for_baseline(
    arr: np.ndarray,
    sample_rate_hz: float,
    duration_sec: float,
    *,
    trim_start_sec: float = _BASELINE_TRIM_START_SEC,
    trim_end_sec: float = _BASELINE_TRIM_END_SEC,
) -> np.ndarray:
    """底电统计有效区间：忽略场景开始前 trim_start_sec 与结束前 trim_end_sec。"""
    if arr.size == 0:
        return arr
    start_idx = max(0, int(trim_start_sec * sample_rate_hz))
    end_idx = min(arr.size, max(start_idx, int((duration_sec - trim_end_sec) * sample_rate_hz)))
    if start_idx >= end_idx:
        return np.array([], dtype=float)
    return arr[start_idx:end_idx]


def _rolling_min_mean(arr: np.ndarray, sample_rate_hz: float, window_sec: float) -> float | None:
    """平均底电：在 window_sec 滑动窗口内取均值，再取全场景最小窗口均值。"""
    if arr.size == 0:
        return None
    win = max(1, int(window_sec * sample_rate_hz))
    if arr.size < win:
        return round(float(arr.mean()), 2)
    kernel = np.ones(win, dtype=float) / win
    rolling = np.convolve(arr, kernel, mode="valid")
    return round(float(rolling.min()), 2)


def _current_level_stats(
    arr: np.ndarray,
    *,
    sample_rate_hz: float = 1.0,
    baseline_window_sec: float = _DEFAULT_WINDOW_SEC,
    baseline_percentile: float = _BASELINE_PERCENTILE,
) -> dict[str, float]:
    """底电(min) / 平均底电(滑动窗口最低均值) / P10 等分位参考。"""
    if arr.size == 0:
        return {}
    avg_baseline = _rolling_min_mean(arr, sample_rate_hz, baseline_window_sec)
    out: dict[str, float] = {
        "min_ma": round(float(arr.min()), 2),
        "p10_ma": round(float(np.percentile(arr, baseline_percentile)), 2),
        "p25_ma": round(float(np.percentile(arr, 25)), 2),
        "median_ma": round(float(np.median(arr)), 2),
    }
    if avg_baseline is not None:
        out["avg_baseline_ma"] = avg_baseline
    out["baseline_ma"] = out["p10_ma"]
    return out


def _find_top_mean_windows(
    arr: np.ndarray,
    *,
    sample_rate_hz: float,
    window_sec: float,
    step_sec: float,
    top_n: int,
    highest: bool = True,
) -> list[dict[str, Any]]:
    """在电流序列上找平均电流最高或最低的滑窗时段。"""
    if arr.size == 0:
        return []
    win = max(1, int(window_sec * sample_rate_hz))
    step = max(1, int(step_sec * sample_rate_hz))
    if arr.size < win:
        mean_val = float(arr.mean())
        if not highest and mean_val == float(arr.max()):
            return []
        return [
            {
                "rank": 1,
                "start_sec": 0.0,
                "end_sec": arr.size / sample_rate_hz,
                "duration_sec": arr.size / sample_rate_hz,
                "mean_ma": round(mean_val, 2),
                "extreme_ma": round(float(arr.max() if highest else arr.min()), 2),
                "relative_time": f"00:00–{_sec_to_rel_time(arr.size / sample_rate_hz)}",
            }
        ]

    scored: list[tuple[float, int, float, float]] = []
    for i in range(0, arr.size - win + 1, step):
        seg = arr[i : i + win]
        scored.append((float(seg.mean()), i, float(seg.max() if highest else seg.min()), win / sample_rate_hz))
    scored.sort(key=lambda x: x[0], reverse=highest)

    windows: list[dict[str, Any]] = []
    used: list[tuple[float, float]] = []
    for mean_val, start_idx, extreme_val, dur in scored:
        start_sec = start_idx / sample_rate_hz
        end_sec = start_sec + dur
        overlap = any(not (end_sec <= s or start_sec >= e) for s, e in used)
        if overlap:
            continue
        used.append((start_sec, end_sec))
        windows.append(
            {
                "rank": len(windows) + 1,
                "start_sec": round(start_sec, 2),
                "end_sec": round(end_sec, 2),
                "duration_sec": round(dur, 2),
                "mean_ma": round(mean_val, 2),
                "extreme_ma": round(extreme_val, 2),
                "relative_time": f"{_sec_to_rel_time(start_sec)}–{_sec_to_rel_time(end_sec)}",
            }
        )
        if len(windows) >= top_n:
            break
    return windows


def _downsample_series(
    t: np.ndarray,
    current: np.ndarray,
    max_points: int,
) -> list[dict[str, float]]:
    n = len(t)
    step = 1 if n <= max_points else max(1, n // max_points)
    return [
        {
            "t_sec": round(float(t[i]), 2),
            "current_ma": round(float(current[i]), 2),
        }
        for i in range(0, n, step)
    ]


def _build_current_analysis(
    series: np.ndarray,
    *,
    sample_rate_hz: float,
    duration_sec: float,
    window_sec: float = _DEFAULT_WINDOW_SEC,
    step_sec: float = _DEFAULT_WINDOW_STEP_SEC,
    top_windows: int = _DEFAULT_TOP_WINDOWS,
    pt5_file: str = "",
) -> dict[str, Any]:
    """根据电流序列计算底电流、高/低功耗窗口及图表采样点。"""
    if series.size == 0:
        return {"success": False, "error": "电流序列为空"}

    t = np.arange(len(series), dtype=float) / sample_rate_hz
    baseline_stats = _current_level_stats(
        _slice_for_baseline(series, sample_rate_hz, duration_sec),
        sample_rate_hz=sample_rate_hz,
        baseline_window_sec=window_sec,
    )

    return {
        "success": True,
        "pt5_file": pt5_file,
        "duration_sec": duration_sec,
        "current_summary": {
            "avg_ma": round(float(series.mean()), 2),
            "floor_ma": baseline_stats.get("min_ma"),
            "avg_baseline_ma": baseline_stats.get("avg_baseline_ma"),
            "baseline_ma": baseline_stats.get("baseline_ma"),
            "baseline": baseline_stats,
            "avg_baseline_window_sec": window_sec,
            "baseline_trim_start_sec": _BASELINE_TRIM_START_SEC,
            "baseline_trim_end_sec": _BASELINE_TRIM_END_SEC,
            "baseline_percentile": _BASELINE_PERCENTILE,
        },
        "high_power_windows": _find_top_mean_windows(
            series,
            sample_rate_hz=sample_rate_hz,
            window_sec=window_sec,
            step_sec=step_sec,
            top_n=top_windows,
            highest=True,
        ),
        "low_power_windows": _find_top_mean_windows(
            series,
            sample_rate_hz=sample_rate_hz,
            window_sec=window_sec,
            step_sec=step_sec,
            top_n=top_windows,
            highest=False,
        ),
        "series": {
            "sample_rate_hz": sample_rate_hz,
            "point_count": len(series),
            "points": _downsample_series(t, series, _MAX_CHART_POINTS),
        },
        "window_sec": window_sec,
        "window_step_sec": step_sec,
        "top_windows": top_windows,
        "time_axis_note": "横轴为场景内相对时间(mm:ss)",
        "analyzed_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


class PT5McpClient:
    """PT5 MCP 客户端，封装常用工具调用。"""

    def __init__(self, server_params: StdioServerParameters | None = None):
        self.server_params = server_params or load_pt5_server_params()

    async def _run(self, callback):
        async with stdio_client(self.server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await callback(session)

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        async def _call(session: ClientSession) -> str:
            result = await session.call_tool(name, arguments)
            if result.isError:
                raise RuntimeError(_tool_text(result) or f"工具 {name} 调用失败")
            return _tool_text(result)

        return await self._run(_call)

    async def parse_pt5(self, file_path: str | Path) -> dict[str, Any]:
        result = await self.call_tool("parse_pt5", {"file_path": str(Path(file_path).resolve())})
        return json.loads(result)

    async def get_channels(self, file_path: str | Path) -> dict[str, Any]:
        result = await self.call_tool("get_pt5_channels", {"file_path": str(Path(file_path).resolve())})
        return json.loads(result)

    async def get_header(self, file_path: str | Path) -> dict[str, Any]:
        result = await self.call_tool("get_pt5_header", {"file_path": str(Path(file_path).resolve())})
        return json.loads(result)

    async def get_samples(
        self,
        file_path: str | Path,
        *,
        start_time_sec: float | None = None,
        end_time_sec: float | None = None,
        decimation: int | None = None,
        max_samples: int | None = None,
    ) -> dict[str, Any]:
        args: dict[str, Any] = {"file_path": str(Path(file_path).resolve())}
        if start_time_sec is not None:
            args["start_time_sec"] = start_time_sec
        if end_time_sec is not None:
            args["end_time_sec"] = end_time_sec
        if decimation is not None:
            args["decimation"] = decimation
        if max_samples is not None:
            args["max_samples"] = max_samples
        result = await self.call_tool("get_pt5_samples", args)
        return json.loads(result)

    async def analyze_trend(
        self,
        file_path: str | Path,
        *,
        channel: str = "main",
        peak_window_ms: float | None = None,
        min_peak_prominence_ma: float | None = None,
        anomaly_threshold_std: float | None = None,
        max_lag_sec: float | None = None,
    ) -> str:
        args: dict[str, Any] = {
            "file_path": str(Path(file_path).resolve()),
            "channel": channel,
        }
        if peak_window_ms is not None:
            args["peak_window_ms"] = peak_window_ms
        if min_peak_prominence_ma is not None:
            args["min_peak_prominence_ma"] = min_peak_prominence_ma
        if anomaly_threshold_std is not None:
            args["anomaly_threshold_std"] = anomaly_threshold_std
        if max_lag_sec is not None:
            args["max_lag_sec"] = max_lag_sec
        return await self.call_tool("analyze_pt5_trend", args)

    async def load_current_series(
        self,
        file_path: str | Path,
        *,
        channel: str = "main",
        max_points: int = _MAX_LOAD_POINTS,
    ) -> dict[str, Any]:
        """通过 MCP 加载电流序列（自动降采样/分块）。"""
        path = Path(file_path).resolve()
        summary = await self.parse_pt5(path)
        duration = float(summary["durationSec"])
        rate = float(summary["sampleRateHz"])
        total = int(summary["sampleCount"])
        dec = max(1, (total + max_points - 1) // max_points)
        current_key = _channel_current_key(channel)

        times: list[float] = []
        series: list[float] = []

        expected = (total + dec - 1) // dec
        if expected <= max_points:
            resp = await self.get_samples(path, decimation=dec, max_samples=max_points)
            for row in resp.get("data", []):
                times.append(float(row["time_s"]))
                series.append(float(row.get(current_key, row.get("main_current_mA", 0))))
        else:
            chunk_dur = max_points * dec / rate
            t0 = 0.0
            while t0 < duration:
                t1 = min(duration, t0 + chunk_dur)
                resp = await self.get_samples(
                    path,
                    start_time_sec=t0,
                    end_time_sec=t1,
                    decimation=dec,
                    max_samples=max_points,
                )
                for row in resp.get("data", []):
                    times.append(float(row["time_s"]))
                    series.append(float(row.get(current_key, row.get("main_current_mA", 0))))
                if t1 >= duration:
                    break
                t0 = t1

        arr = np.array(series, dtype=float)
        effective_rate = len(arr) / duration if duration > 0 else rate / dec
        return {
            "file": str(path),
            "series": arr,
            "times": np.array(times, dtype=float),
            "sample_rate_hz": effective_rate,
            "duration_sec": duration,
            "native_sample_rate_hz": rate,
            "decimation": dec,
            "point_count": len(arr),
            "summary": summary,
        }

    async def analyze_standby(
        self,
        log_path: str | Path,
        *,
        channel: str = "main",
        window_sec: float = _DEFAULT_WINDOW_SEC,
        step_sec: float = _DEFAULT_WINDOW_STEP_SEC,
        max_points: int = _MAX_LOAD_POINTS,
    ) -> dict[str, Any]:
        """从日志路径自动查找 .pt5，输出 standby flow 结构化字段。"""
        pt5_path = find_pt5_file(log_path)
        if pt5_path is None:
            return {
                "success": False,
                "log_path": str(Path(log_path).resolve()),
                "error": "未在日志路径或 downloads/ 下找到 .pt5 文件",
            }

        summary = await self.parse_pt5(pt5_path)
        yaml_path = _find_yaml_for_pt5(pt5_path)
        yaml_times = _load_yaml_collect_times(yaml_path) if yaml_path else None
        loaded = await self.load_current_series(pt5_path, channel=channel, max_points=max_points)
        analysis = _build_current_analysis(
            loaded["series"],
            sample_rate_hz=float(loaded["sample_rate_hz"]),
            duration_sec=float(loaded["duration_sec"]),
            window_sec=window_sec,
            step_sec=step_sec,
            top_windows=1,
            pt5_file=str(pt5_path),
        )
        result = build_standby_output(
            pt5_file=str(pt5_path),
            summary=summary,
            analysis=analysis,
            loaded=loaded,
            yaml_times=yaml_times,
        )
        result["log_path"] = str(Path(log_path).resolve())
        return result

    async def get_info(self, file_path: str | Path) -> dict[str, Any]:
        """汇总 PT5 文件的核心信息。"""
        path = Path(file_path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"PT5 文件不存在: {path}")

        summary, channels, header = await asyncio.gather(
            self.parse_pt5(path),
            self.get_channels(path),
            self.get_header(path),
        )

        return {
            "file": str(path),
            "summary": summary,
            "channels": channels,
            "header": header,
        }


async def get_pt5_info(file_path: str | Path, config_path: Path | None = None) -> dict[str, Any]:
    """读取 PT5 文件信息（便捷函数）。"""
    client = PT5McpClient(load_pt5_server_params(config_path))
    return await client.get_info(file_path)


async def analyze_standby_pt5(
    log_path: str | Path,
    *,
    config_path: Path | None = None,
    channel: str = "main",
    window_sec: float = _DEFAULT_WINDOW_SEC,
    step_sec: float = _DEFAULT_WINDOW_STEP_SEC,
) -> dict[str, Any]:
    """从日志路径解析 standby 结构化输出（便捷函数）。"""
    client = PT5McpClient(load_pt5_server_params(config_path))
    return await client.analyze_standby(
        log_path,
        channel=channel,
        window_sec=window_sec,
        step_sec=step_sec,
    )


async def analyze_pt5_current_graph(
    pt5_file: str | Path,
    *,
    config_path: Path | None = None,
    channel: str = "main",
    window_sec: float = _DEFAULT_WINDOW_SEC,
    step_sec: float = _DEFAULT_WINDOW_STEP_SEC,
    top_windows: int = _DEFAULT_TOP_WINDOWS,
) -> dict[str, Any]:
    """分析单个 .pt5 电流图（便捷函数）。"""
    client = PT5McpClient(load_pt5_server_params(config_path))
    path = Path(pt5_file).resolve()
    if not path.exists():
        return {"success": False, "error": f"PT5 文件不存在: {path}"}
    loaded = await client.load_current_series(path, channel=channel)
    return _build_current_analysis(
        loaded["series"],
        sample_rate_hz=float(loaded["sample_rate_hz"]),
        duration_sec=float(loaded["duration_sec"]),
        window_sec=window_sec,
        step_sec=step_sec,
        top_windows=top_windows,
        pt5_file=str(path),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="通过 PT5 MCP 解析待机电流（输入日志路径，自动查找 .pt5）")
    parser.add_argument("path", help="日志路径（APLog 目录或工作区根），也可直接传 .pt5 文件")
    parser.add_argument(
        "--config",
        default=str(DEFAULT_MCP_CONFIG),
        help=f"Cursor MCP 配置文件路径（默认: {DEFAULT_MCP_CONFIG}）",
    )
    parser.add_argument(
        "--tool",
        choices=["standby", "info", "parse", "channels", "header", "samples", "trend", "current"],
        default="standby",
        help="standby=结构化待机输出（默认）；其余为 MCP 原始工具",
    )
    parser.add_argument("--format", choices=["text", "json"], default="text", help="输出格式（默认 text，直接打印到终端）")
    parser.add_argument("--window-sec", type=float, default=_DEFAULT_WINDOW_SEC, help="滑窗长度（秒）")
    parser.add_argument("--step-sec", type=float, default=_DEFAULT_WINDOW_STEP_SEC, help="滑窗步长（秒）")
    parser.add_argument("--top-windows", type=int, default=_DEFAULT_TOP_WINDOWS, help="current 工具返回窗口数量")
    parser.add_argument("--decimation", type=int, default=100, help="samples 工具采样间隔")
    parser.add_argument("--max-samples", type=int, default=100, help="samples 工具最大返回条数")
    args = parser.parse_args()

    client = PT5McpClient(load_pt5_server_params(Path(args.config)))

    async def run() -> Any:
        path = args.path
        if args.tool == "standby":
            return await client.analyze_standby(
                path,
                window_sec=args.window_sec,
                step_sec=args.step_sec,
            )
        pt5_path = path
        if args.tool != "standby" and not str(path).lower().endswith(".pt5"):
            found = find_pt5_file(path)
            if found is None:
                return {"success": False, "error": f"未找到 .pt5，且 --tool {args.tool} 需要 .pt5 文件路径"}
            pt5_path = str(found)
        if args.tool == "info":
            return await client.get_info(pt5_path)
        if args.tool == "parse":
            return await client.parse_pt5(pt5_path)
        if args.tool == "channels":
            return await client.get_channels(pt5_path)
        if args.tool == "header":
            return await client.get_header(pt5_path)
        if args.tool == "samples":
            return await client.get_samples(
                pt5_path,
                decimation=args.decimation,
                max_samples=args.max_samples,
            )
        if args.tool == "current":
            return await analyze_pt5_current_graph(
                pt5_path,
                window_sec=args.window_sec,
                step_sec=args.step_sec,
                top_windows=args.top_windows,
            )
        return await client.analyze_trend(pt5_path)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    result = asyncio.run(run())
    if isinstance(result, str):
        print(result)
    elif args.tool == "standby" and args.format == "text":
        print(format_standby_text(result))
    elif args.format == "text" and isinstance(result, dict) and not result.get("success"):
        print(f"error: {result.get('error', 'unknown')}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
