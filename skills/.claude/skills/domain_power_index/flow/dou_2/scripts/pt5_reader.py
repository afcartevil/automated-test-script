"""读取 meta_report 下 TPowerMonitor 导出的 .pt5 电流采样文件（经 pt5-mcp-server 官方解析器）。"""
from __future__ import annotations
def _setup_utf8_stdio() -> None:
    import sys
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any

import numpy as np

_DEFAULT_RATE_HZ = 32.0
_CLI_NAME = "pt5_mcp_cli.mjs"


def find_pt5_for_suffix(meta_report_dir: str, suffix: str) -> str | None:
    """按场景号在 meta_report 中查找 .pt5 / .pt 文件。"""
    if not meta_report_dir or not os.path.isdir(meta_report_dir):
        return None
    suf = str(suffix or "").strip().lstrip("_")
    if not suf:
        return None
    patterns = (
        re.compile(rf"dou3_{re.escape(suf)}\.(pt5|pt)$", re.I),
        re.compile(rf"_{re.escape(suf)}\.(pt5|pt)$", re.I),
        re.compile(rf"{re.escape(suf)}\.(pt5|pt)$", re.I),
    )
    candidates: list[str] = []
    for fn in os.listdir(meta_report_dir):
        low = fn.lower()
        if not (low.endswith(".pt5") or low.endswith(".pt")):
            continue
        if any(p.search(fn) for p in patterns):
            candidates.append(os.path.join(meta_report_dir, fn))
    if not candidates:
        return None
    return max(candidates, key=os.path.getmtime)


def _cli_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), _CLI_NAME)


def _node_exe() -> str:
    node = shutil.which("node")
    if not node:
        raise RuntimeError("未找到 node，无法调用 pt5-mcp-server 解析器")
    return node


def _run_pt5_mcp_series(
    path: str,
    duration_sec: float,
    *,
    rate_hz: float = _DEFAULT_RATE_HZ,
    channel: str = "main",
) -> dict[str, Any]:
    cli = _cli_path()
    if not os.path.isfile(cli):
        raise RuntimeError(f"缺少 PT5 CLI: {cli}")
    cmd = [
        _node_exe(),
        cli,
        "series",
        "--file",
        os.path.abspath(path),
        "--duration-sec",
        str(duration_sec),
        "--rate-hz",
        str(rate_hz),
        "--channel",
        channel,
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(err or f"pt5-mcp-server 解析失败: {path}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"pt5-mcp-server 输出非 JSON: {proc.stdout[:200]}") from exc


def extract_current_samples(path: str) -> np.ndarray:
    """从 pt5 提取电流序列（mA），使用 pt5-mcp-server 官方解析。"""
    data = _run_pt5_mcp_series(path, duration_sec=0, rate_hz=_DEFAULT_RATE_HZ)
    series = data.get("series") or []
    return np.array(series, dtype=float)


def resample_current(
    samples: np.ndarray,
    duration_sec: float,
    rate_hz: float = _DEFAULT_RATE_HZ,
) -> np.ndarray:
    """将样本均值重采样为固定采样率序列。"""
    if samples.size == 0 or duration_sec <= 0:
        return np.array([], dtype=float)
    n = max(1, int(duration_sec * rate_hz))
    if samples.size <= n:
        return samples.astype(float)
    chunk = samples.size / n
    out = np.empty(n, dtype=float)
    for i in range(n):
        s = int(i * chunk)
        e = max(s + 1, int((i + 1) * chunk))
        out[i] = float(samples[s:e].mean())
    return out


def load_pt5_series(
    path: str,
    duration_sec: float,
    *,
    calibrate_to_ma: float | None = None,
    rate_hz: float = _DEFAULT_RATE_HZ,
) -> dict[str, Any]:
    """加载并重采样单条 pt5 电流曲线（解析器与 MCP pt5 一致）。"""
    data = _run_pt5_mcp_series(path, duration_sec, rate_hz=rate_hz)
    series = np.array(data.get("series") or [], dtype=float)
    raw_mean = data.get("raw_mean_ma")
    if raw_mean is None and series.size:
        raw_mean = float(series.mean())
    if calibrate_to_ma is not None and series.size:
        series = series + (float(calibrate_to_ma) - float(series.mean()))
    return {
        "path": path,
        "raw_sample_count": int(data.get("raw_sample_count") or 0),
        "point_count": int(series.size),
        "raw_mean_ma": raw_mean,
        "mean_ma": float(series.mean()) if series.size else None,
        "series": series,
        "sample_rate_hz": float(data.get("sample_rate_hz") or rate_hz),
        "native_sample_rate_hz": data.get("native_sample_rate_hz"),
        "parser": "pt5-mcp-server",
    }


def _main() -> int:
    if len(sys.argv) < 2:
        print(f"用法: python {os.path.basename(__file__)} <pt5路径> [duration_sec]", file=sys.stderr)
        return 1
    path = sys.argv[1]
    dur = float(sys.argv[2]) if len(sys.argv) > 2 else 0.0
    try:
        if dur > 0:
            result = load_pt5_series(path, dur)
        else:
            samples = extract_current_samples(path)
            result = {"path": path, "raw_sample_count": int(samples.size), "mean_ma": float(samples.mean()) if samples.size else None}
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    _setup_utf8_stdio()
    raise SystemExit(_main())
