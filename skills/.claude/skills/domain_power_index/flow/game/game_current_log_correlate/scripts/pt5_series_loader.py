"""电流序列加载：pt5 / csv / json；可选外部 pt5_reader。"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import numpy as np

_PT5_EXTS = {".pt5", ".csv", ".json", ".jsonl"}
_AUTO_DISCOVER_EXTS = {".pt5", ".csv"}
# 文件名提示（避免子串误伤：ma∈summary / thermal）
_CURRENT_NAME_TOKENS = (
    "current",
    "电流",
    "pt5",
    "waveform",
    "ampere",
    "i_ma",
    "current_ma",
    "avg_cur",
)


_SKIP_NAMES = {
    "current_cpu_spike_game.json",
    "game_current_log_correlate.json",
    "game_current_log_correlate_report.html",
    "game_power_compare_summary.json",
    "game_power_delta.json",
    "game_ai_insights.json",
    "game_preliminary_diagnosis.json",
    "game_diagnosis_report.json",
    "game_root_cause.json",
}


def _name_looks_like_current(name: str) -> bool:
    n = name.lower()
    if n in _SKIP_NAMES or (n.startswith("game_") and n.endswith(".json")):
        return False
    stem = Path(name).stem.lower()
    if any(tok in n for tok in _CURRENT_NAME_TOKENS):
        return True
    if stem.endswith("_cur") or stem.endswith("_ima") or stem.endswith("-cur"):
        return True
    return False


def _as_float_arr(vals: list[Any]) -> np.ndarray:
    out: list[float] = []
    for v in vals:
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            continue
    return np.asarray(out, dtype=float)


def _series_from_pairs(t_sec: np.ndarray, current_ma: np.ndarray) -> dict[str, Any]:
    if t_sec.size == 0 or current_ma.size == 0:
        raise ValueError("空电流序列")
    n = min(t_sec.size, current_ma.size)
    t = np.asarray(t_sec[:n], dtype=float)
    cur = np.asarray(current_ma[:n], dtype=float)
    # 若时间非从 0 起，归一到相对起点
    if t.size and float(t[0]) != 0.0:
        t = t - float(t[0])
    duration = float(t[-1] - t[0]) if t.size > 1 else 0.0
    if duration <= 0 and n > 1:
        duration = float(n - 1)
        t = np.arange(n, dtype=float)
    sample_rate_hz = (n - 1) / duration if duration > 0 else 1.0
    return {
        "t_sec": t,
        "current_ma": cur,
        "sample_rate_hz": float(sample_rate_hz),
        "duration_sec": float(duration if duration > 0 else n / max(sample_rate_hz, 1e-9)),
        "n_samples": int(n),
    }


def _load_csv(path: Path) -> dict[str, Any]:
    import csv

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError(f"CSV 无表头: {path}")
        fields = [str(x).strip() for x in reader.fieldnames]
        lower = {c.lower(): c for c in fields}

        def pick(*names: str) -> str | None:
            for n in names:
                if n in lower:
                    return lower[n]
            for c in fields:
                cl = c.lower()
                if any(h in cl for h in names):
                    return c
            return None

        t_col = pick("t_sec", "t", "time_sec", "time", "sec", "相对时间")
        i_col = pick("current_ma", "current", "i_ma", "ma", "avg_cur", "电流")
        rows = list(reader)
    if not rows:
        raise ValueError(f"CSV 无数据: {path}")

    if t_col and i_col:
        t = _as_float_arr([r.get(t_col) for r in rows])
        cur = _as_float_arr([r.get(i_col) for r in rows])
        return _series_from_pairs(t, cur)

    # 单列电流
    if i_col:
        cur = _as_float_arr([r.get(i_col) for r in rows])
        t = np.arange(cur.size, dtype=float)
        return _series_from_pairs(t, cur)

    # 无表头语义：取第 1/2 列
    keys = fields
    if len(keys) >= 2:
        t = _as_float_arr([r.get(keys[0]) for r in rows])
        cur = _as_float_arr([r.get(keys[1]) for r in rows])
        return _series_from_pairs(t, cur)
    raise ValueError(f"无法识别 CSV 列: {fields}")


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        if "t_sec" in data and ("current_ma" in data or "current" in data):
            t = _as_float_arr(list(data.get("t_sec") or []))
            cur = _as_float_arr(list(data.get("current_ma") or data.get("current") or []))
            return _series_from_pairs(t, cur)
        series = data.get("series") or data.get("points") or data.get("samples")
        if isinstance(series, list):
            data = series
    if isinstance(data, list) and data:
        if isinstance(data[0], dict):
            t = _as_float_arr([x.get("t_sec", x.get("t", x.get("time"))) for x in data])
            cur = _as_float_arr(
                [x.get("current_ma", x.get("current", x.get("ma"))) for x in data]
            )
            return _series_from_pairs(t, cur)
        if isinstance(data[0], (list, tuple)) and len(data[0]) >= 2:
            t = _as_float_arr([x[0] for x in data])
            cur = _as_float_arr([x[1] for x in data])
            return _series_from_pairs(t, cur)
    raise ValueError(f"无法解析 JSON 电流序列: {path}")


def _try_pt5_reader(path: Path) -> dict[str, Any] | None:
    # 1) 内置 Monsoon / TPowerTool 解析
    try:
        _wf = Path(__file__).resolve().parent
        if str(_wf) not in sys.path:
            sys.path.insert(0, str(_wf))
        from monsoon_pt5 import is_monsoon_pt5, load_monsoon_pt5_series  # type: ignore

        if is_monsoon_pt5(path):
            return load_monsoon_pt5_series(path)
    except Exception:
        pass
    # 2) 外部 pt5_reader（可选）
    try:
        from pt5_reader import load_pt5_series  # type: ignore
    except Exception:
        return None
    try:
        series = load_pt5_series(str(path))
    except Exception:
        return None
    if series is None:
        return None
    if isinstance(series, dict):
        t = series.get("t_sec") or series.get("t") or series.get("time")
        cur = series.get("current_ma") or series.get("current") or series.get("i_ma")
        if t is not None and cur is not None:
            return _series_from_pairs(np.asarray(t, dtype=float), np.asarray(cur, dtype=float))
        arr = series.get("current_ma") or series.get("data")
        rate = float(series.get("sample_rate_hz") or series.get("fs") or 1.0)
        if arr is not None:
            cur = np.asarray(arr, dtype=float).reshape(-1)
            t = np.arange(cur.size, dtype=float) / max(rate, 1e-9)
            out = _series_from_pairs(t, cur)
            out["sample_rate_hz"] = rate
            return out
    if isinstance(series, (list, tuple, np.ndarray)):
        cur = np.asarray(series, dtype=float).reshape(-1)
        t = np.arange(cur.size, dtype=float)
        return _series_from_pairs(t, cur)
    return None


def load_current_series(path: str | Path) -> dict[str, Any]:
    """加载电流序列，返回 t_sec / current_ma / sample_rate_hz / duration_sec。"""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    suffix = path.suffix.lower()
    if suffix == ".csv":
        out = _load_csv(path)
    elif suffix in {".json", ".jsonl"}:
        out = _load_json(path)
    elif suffix == ".pt5":
        out = _try_pt5_reader(path)
        if out is None:
            raise ValueError(
                f"无法读取二进制 pt5（未安装可用的 pt5_reader）: {path}；"
                "请导出 CSV（列 t_sec,current_ma）后重试"
            )
    else:
        # 尝试按 CSV/JSON
        try:
            out = _load_csv(path)
        except Exception:
            out = _load_json(path)
    out["source_path"] = str(path)
    out["source_format"] = suffix.lstrip(".") or "unknown"
    return out


def find_pt5_candidates(
    *,
    explicit: str | Path | None = None,
    search_dirs: list[str | Path] | None = None,
    jira_key: str = "",
) -> list[Path]:
    """按优先级收集候选电流文件。"""
    found: list[Path] = []
    seen: set[str] = set()

    def add(p: Path) -> None:
        try:
            rp = p.resolve()
        except OSError:
            return
        if not rp.is_file():
            return
        # 分析产物 / 报告禁止当电流源
        if rp.name.lower() in _SKIP_NAMES:
            return
        if rp.suffix.lower() == ".json" and rp.name.lower().startswith("game_"):
            return
        if rp.suffix.lower() == ".html":
            return
        key = str(rp).lower()
        if key in seen:
            return
        seen.add(key)
        found.append(rp)

    if explicit:
        add(Path(explicit))
        return found

    key_l = (jira_key or "").strip().lower()
    for d in search_dirs or []:
        root = Path(d)
        if not root.exists():
            continue
        if root.is_file():
            add(root)
            continue
        # 直接子文件优先
        for pat in ("*.pt5", "*current*.csv", "*电流*.csv", "*pt5*.csv", "*waveform*.csv"):
            for p in sorted(root.glob(pat)):
                add(p)
        # 浅层递归（2 层）
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in _AUTO_DISCOVER_EXTS:
                continue
            name = p.name.lower()
            is_pt5 = p.suffix.lower() == ".pt5"
            looks_current = _name_looks_like_current(name)
            if key_l:
                in_key_path = key_l in name or key_l in str(p.parent).lower()
                if not is_pt5 and not looks_current and not in_key_path:
                    continue
                if not is_pt5 and not looks_current:
                    continue
            elif not is_pt5 and not looks_current:
                continue
            # 限制深度
            try:
                depth = len(p.relative_to(root).parts)
            except ValueError:
                depth = 99
            if depth <= 3:
                add(p)
    # pt5 优先
    found.sort(key=lambda p: (0 if p.suffix.lower() == ".pt5" else 1, p.name.lower()))
    return found
