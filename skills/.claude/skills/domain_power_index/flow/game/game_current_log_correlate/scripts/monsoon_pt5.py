"""Monsoon / TPowerTool .pt5 读取（内置，无外部 pt5_reader 依赖）。

样本格式：6 字节 `<iH`（int32 电流 µA，uint16 电压），电流 mA = raw/1000，
电压 V = raw * 500e-6。参考 current_analysis/pypowertool/pt5reader.py。
"""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Any


_MISSING_CURRENT = 0x8001
_MISSING_VOLTAGE = 0xFFFF


def is_monsoon_pt5(path: str | Path) -> bool:
    path = Path(path)
    if not path.is_file() or path.suffix.lower() != ".pt5":
        return False
    try:
        with path.open("rb") as f:
            head = f.read(24)
    except OSError:
        return False
    if len(head) < 24:
        return False
    name = head[4:24]
    return b"Power Tool" in name


def _read_header(path: Path) -> dict[str, Any]:
    with path.open("rb") as f:
        hb = f.read(212)
    if len(hb) < 160:
        raise ValueError(f"pt5 header 过短: {path}")
    head_size = struct.unpack_from("<I", hb, 0)[0]
    hardware_rate = struct.unpack_from("<I", hb, 68)[0] or 5000
    software_rate = float(struct.unpack_from("<f", hb, 72)[0] or hardware_rate)
    total_count = struct.unpack_from("<Q", hb, 136)[0]
    # extended fields may live past headSize; Monsoon layout uses fixed offsets
    sample_offset = struct.unpack_from("<H", hb, 148)[0] if len(hb) >= 150 else head_size
    sample_size = struct.unpack_from("<H", hb, 150)[0] if len(hb) >= 152 else 6
    if sample_offset <= 0:
        sample_offset = head_size or 1024
    if sample_size <= 0:
        sample_size = 6
    if total_count <= 0:
        file_size = path.stat().st_size
        total_count = max(0, (file_size - sample_offset) // sample_size)
    duration = float(total_count) / float(hardware_rate) if hardware_rate else 0.0
    return {
        "head_size": head_size,
        "hardware_rate_hz": int(hardware_rate),
        "software_rate_hz": software_rate,
        "total_count": int(total_count),
        "sample_offset": int(sample_offset),
        "sample_size": int(sample_size),
        "duration_sec": duration,
    }


def load_monsoon_pt5_series(
    path: str | Path,
    *,
    target_hz: float = 10.0,
    max_points: int = 12000,
) -> dict[str, Any]:
    """读取 pt5 并降采样为相对时间电流序列（抽点，非秒均值）。"""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    hdr = _read_header(path)
    rate = float(hdr["hardware_rate_hz"] or 1.0)
    total = int(hdr["total_count"])
    sample_offset = int(hdr["sample_offset"])
    sample_size = int(hdr["sample_size"])
    if total <= 0 or sample_size < 6:
        raise ValueError(f"无效 pt5 采样参数: {path}")

    # 降采样步长：优先 target_hz，再受 max_points 约束
    step = max(1, int(round(rate / max(target_hz, 0.1))))
    if total / step > max_points:
        step = max(step, int(total / max_points) + 1)

    t_sec: list[float] = []
    current_ma: list[float] = []
    voltage_v: list[float] = []
    missing = 0
    with path.open("rb") as f:
        for i in range(0, total, step):
            f.seek(sample_offset + i * sample_size)
            data = f.read(sample_size)
            if len(data) < 6:
                break
            cur_raw, vol_raw = struct.unpack_from("<iH", data, 0)
            if cur_raw == _MISSING_CURRENT or vol_raw == _MISSING_VOLTAGE:
                missing += 1
                continue
            t_sec.append(i / rate)
            current_ma.append(cur_raw / 1000.0)
            voltage_v.append(vol_raw * 500e-6)

    if not current_ma:
        raise ValueError(f"pt5 无有效电流样本: {path}")

    duration = float(hdr["duration_sec"] or (t_sec[-1] if t_sec else 0.0))
    n = len(current_ma)
    mean_ma = sum(current_ma) / n
    return {
        "t_sec": t_sec,
        "current_ma": current_ma,
        "voltage_v": voltage_v,
        "sample_rate_hz": rate / step,
        "source_rate_hz": rate,
        "duration_sec": duration,
        "n_samples": n,
        "n_raw_samples": total,
        "missing_samples": missing,
        "mean_ma": round(mean_ma, 2),
        "min_ma": round(min(current_ma), 2),
        "max_ma": round(max(current_ma), 2),
        "source_path": str(path),
        "source_format": "pt5",
        "reader": "monsoon_builtin",
        "header": hdr,
    }


def load_monsoon_pt5_per_second(path: str | Path) -> dict[str, Any]:
    """ms 级采样按整秒求均值 → 1Hz 序列（分析抬升用）。"""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(str(path))
    hdr = _read_header(path)
    rate = float(hdr["hardware_rate_hz"] or 1.0)
    total = int(hdr["total_count"])
    sample_offset = int(hdr["sample_offset"])
    sample_size = int(hdr["sample_size"])
    if total <= 0 or sample_size < 6:
        raise ValueError(f"无效 pt5 采样参数: {path}")

    # sec_idx -> [sum_i, sum_v, count]
    buckets: dict[int, list[float]] = {}
    missing = 0
    chunk = max(int(rate), 5000)  # 一次读约 1s
    with path.open("rb") as f:
        f.seek(sample_offset)
        idx = 0
        while idx < total:
            n_read = min(chunk, total - idx)
            data = f.read(n_read * sample_size)
            if len(data) < sample_size:
                break
            n_got = len(data) // sample_size
            for j in range(n_got):
                off = j * sample_size
                cur_raw, vol_raw = struct.unpack_from("<iH", data, off)
                if cur_raw == _MISSING_CURRENT or vol_raw == _MISSING_VOLTAGE:
                    missing += 1
                    continue
                sec = int((idx + j) / rate)
                b = buckets.get(sec)
                if b is None:
                    buckets[sec] = [cur_raw / 1000.0, vol_raw * 500e-6, 1.0]
                else:
                    b[0] += cur_raw / 1000.0
                    b[1] += vol_raw * 500e-6
                    b[2] += 1.0
            idx += n_got
            if n_got < n_read:
                break

    if not buckets:
        raise ValueError(f"pt5 无有效电流样本: {path}")

    secs = sorted(buckets.keys())
    t_sec = [float(s) for s in secs]
    current_ma = [buckets[s][0] / buckets[s][2] for s in secs]
    voltage_v = [buckets[s][1] / buckets[s][2] for s in secs]
    n = len(current_ma)
    mean_ma = sum(current_ma) / n
    duration = float(hdr["duration_sec"] or (t_sec[-1] + 1.0 if t_sec else 0.0))
    return {
        "t_sec": t_sec,
        "current_ma": current_ma,
        "voltage_v": voltage_v,
        "sample_rate_hz": 1.0,
        "source_rate_hz": rate,
        "duration_sec": duration,
        "n_samples": n,
        "n_raw_samples": total,
        "missing_samples": missing,
        "mean_ma": round(mean_ma, 2),
        "min_ma": round(min(current_ma), 2),
        "max_ma": round(max(current_ma), 2),
        "source_path": str(path),
        "source_format": "pt5",
        "reader": "monsoon_builtin_1s_mean",
        "aggregated": "1s_mean",
        "header": hdr,
    }
