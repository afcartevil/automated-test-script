"""从 total_power.pt5 按 current 表时间段（仅用 starttime/endtime）重算电流，输出新 Excel。"""
from __future__ import annotations
def _setup_utf8_stdio() -> None:
    import sys
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


import argparse
import math
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

SAMPLE_OFFSET = 1024
STATUS_OFFSET = 272
MISSING_RAW_CURRENT_INT32 = 0x00008001
MISSING_RAW_VOLTAGE_UINT16 = 0xFFFF
MARKER_MASK = 0x3
CHAN_MAIN = 0x1000
CHAN_USB = 0x2000
CHAN_AUX = 0x4000
INT_TO_FLOAT = 1048576


class SeqReader:
    def __init__(self, data: bytes, pos: int = 0):
        self.data = data
        self.pos = pos

    def read_byte(self) -> int:
        v = self.data[self.pos]
        self.pos += 1
        return v

    def read_sbyte(self) -> int:
        v = struct.unpack_from("<b", self.data, self.pos)[0]
        self.pos += 1
        return v

    def read_int16(self) -> int:
        v = struct.unpack_from("<h", self.data, self.pos)[0]
        self.pos += 2
        return v

    def read_uint16(self) -> int:
        v = struct.unpack_from("<H", self.data, self.pos)[0]
        self.pos += 2
        return v

    def read_int32(self) -> int:
        v = struct.unpack_from("<i", self.data, self.pos)[0]
        self.pos += 4
        return v

    def read_int64(self) -> int:
        v = struct.unpack_from("<q", self.data, self.pos)[0]
        self.pos += 8
        return v

    def read_single(self) -> float:
        v = struct.unpack_from("<f", self.data, self.pos)[0]
        self.pos += 4
        return v

    def read_string(self) -> str:
        content_len = self.read_byte()
        raw = self.data[self.pos : self.pos + content_len]
        self.pos += content_len
        return raw.decode("ascii", errors="replace").strip()


def parse_header(reader: SeqReader) -> dict:
    reader.pos = 0
    reader.read_int32()
    reader.read_string()
    reader.read_int32()
    capture_date = reader.read_int64()
    reader.read_string()
    reader.read_int32()
    reader.read_int32()
    reader.read_single()
    reader.read_int32()
    reader.read_single()
    reader.read_int32()
    reader.read_int32()
    reader.read_int32()
    reader.read_string()
    reader.read_string()
    reader.read_int32()
    reader.read_int32()
    total_count = reader.read_int64()
    reader.read_uint16()
    reader.read_uint16()
    reader.read_uint16()
    reader.read_uint16()
    reader.read_uint16()
    reader.read_uint16()
    reader.read_uint16()
    capture_data_mask = reader.read_uint16()
    sample_count = reader.read_int64()
    missing_count = reader.read_int64()
    return {
        "capture_date": capture_date,
        "total_count": total_count,
        "capture_data_mask": capture_data_mask,
        "sample_count": sample_count,
        "missing_count": missing_count,
    }


def parse_status(reader: SeqReader) -> dict:
    reader.pos = STATUS_OFFSET
    for _ in range(4):
        reader.read_byte()
    for _ in range(4):
        reader.read_int16()
    for _ in range(4):
        reader.read_uint16()
    reader.read_byte()
    reader.read_sbyte()
    reader.read_byte()
    reader.read_byte()
    leds = reader.read_byte()
    reader.read_sbyte()
    reader.read_uint16()
    sample_rate = reader.read_byte()
    reader.read_uint16()
    reader.read_uint16()
    reader.read_uint16()
    reader.read_uint16()
    reader.read_byte()
    reader.read_sbyte()
    reader.read_sbyte()
    reader.read_uint16()
    reader.read_uint16()
    hardware_revision = reader.read_byte()
    reader.read_byte()
    reader.read_byte()
    for _ in range(9):
        reader.read_sbyte()
    reader.read_byte()
    reader.read_uint16()
    reader.read_byte()
    hv_main_voltage_setting = reader.read_int16()
    return {
        "sample_rate": sample_rate,
        "leds": leds,
        "hardware_revision": hardware_revision,
        "hv_main_voltage_setting": hv_main_voltage_setting,
    }


def bytes_per_sample(capture_data_mask: int) -> int:
    result = 2
    if capture_data_mask & CHAN_MAIN:
        result += 4
    if capture_data_mask & CHAN_USB:
        result += 4
    if capture_data_mask & CHAN_AUX:
        result += 4
    return result


def decode_sample_chunk(
    chunk: bytes,
    *,
    capture_data_mask: int,
    hardware_revision: int,
    leds: int,
    hv_main_voltage_setting: int,
) -> tuple[np.ndarray, np.ndarray]:
    bps = bytes_per_sample(capture_data_mask)
    n = len(chunk) // bps
    currents = np.empty(n, dtype=np.float64)
    voltages = np.empty(n, dtype=np.float64)
    default_v = hv_main_voltage_setting / INT_TO_FLOAT
    pos = 0
    for i in range(n):
        missing = False
        cur_ma = np.nan
        vol = default_v
        if capture_data_mask & CHAN_MAIN:
            raw = struct.unpack_from("<i", chunk, pos)[0]
            pos += 4
            if raw == MISSING_RAW_CURRENT_INT32:
                missing = True
            else:
                cur_ma = raw / 1000.0
        if capture_data_mask & CHAN_USB:
            pos += 4
        if capture_data_mask & CHAN_AUX:
            pos += 4
        uraw = struct.unpack_from("<H", chunk, pos)[0]
        pos += 2
        if uraw == MISSING_RAW_VOLTAGE_UINT16:
            missing = True
        else:
            stripped = uraw & ~MARKER_MASK
            voltage = stripped * 125 / 1e6 * 4
            if (leds & 0x08) != 0:
                if hardware_revision < 3:
                    voltage /= 2
            else:
                if hardware_revision < 2:
                    voltage /= 2
                vol = voltage
        currents[i] = cur_ma if not missing else np.nan
        voltages[i] = vol if not missing else np.nan
    return currents, voltages


def windows_ticks_to_datetime(ticks: int) -> datetime | None:
    actual = ticks & 0x3FFFFFFFFFFFFFFF
    ms = (actual - 621355968000000000) // 10000
    if ms < -8640000000000 or ms > 8640000000000:
        return None
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).replace(tzinfo=None)


def fmt_time(ts: datetime | pd.Timestamp) -> str:
    if isinstance(ts, pd.Timestamp):
        ts = ts.to_pydatetime()
    return ts.strftime("%Y-%m-%d %H:%M:%S.%f")


def load_pt5_meta(pt5_path: str | Path) -> dict:
    pt5_path = Path(pt5_path)
    head = pt5_path.read_bytes()[:SAMPLE_OFFSET]
    header = parse_header(SeqReader(head))
    status = parse_status(SeqReader(head))
    sample_rate_hz = status["sample_rate"] * 1000
    bps = bytes_per_sample(header["capture_data_mask"])
    sample_count = int(header["sample_count"])
    if sample_count <= 0:
        sample_count = int(header["total_count"])
    if sample_count <= 0:
        sample_count = (pt5_path.stat().st_size - SAMPLE_OFFSET) // bps
    return {
        "path": str(pt5_path),
        "capture_data_mask": header["capture_data_mask"],
        "sample_rate_hz": sample_rate_hz,
        "bytes_per_sample": bps,
        "sample_count": sample_count,
        "duration_sec": sample_count / sample_rate_hz,
        "capture_start": windows_ticks_to_datetime(int(header["capture_date"])),
        "hardware_revision": status["hardware_revision"],
        "leds": status["leds"],
        "hv_main_voltage_setting": status["hv_main_voltage_setting"],
    }


def segment_stats(
    pt5_path: str | Path,
    meta: dict,
    start_sec: float,
    end_sec: float,
    *,
    chunk_samples: int = 200_000,
) -> tuple[float, float, int]:
    """按 PT5 绝对时间（秒，录制起点为 0）返回 (avg_cur_mA, avg_vol_V, valid_sample_count)。"""
    bps = meta["bytes_per_sample"]
    rate = meta["sample_rate_hz"]
    i0 = max(0, math.floor(start_sec * rate))
    i1 = min(meta["sample_count"], math.ceil(end_sec * rate))
    if i1 <= i0:
        return float("nan"), float("nan"), 0

    byte_start = SAMPLE_OFFSET + i0 * bps
    byte_end = SAMPLE_OFFSET + i1 * bps
    cur_sum = 0.0
    vol_sum = 0.0
    count = 0

    with open(pt5_path, "rb") as f:
        f.seek(byte_start)
        remaining = byte_end - byte_start
        block_bytes = chunk_samples * bps
        while remaining > 0:
            to_read = min(remaining, block_bytes)
            chunk = f.read(to_read)
            if not chunk:
                break
            currs, volts = decode_sample_chunk(
                chunk,
                capture_data_mask=meta["capture_data_mask"],
                hardware_revision=meta["hardware_revision"],
                leds=meta["leds"],
                hv_main_voltage_setting=meta["hv_main_voltage_setting"],
            )
            valid = np.isfinite(currs) & np.isfinite(volts)
            if valid.any():
                cur_sum += float(currs[valid].sum())
                vol_sum += float(volts[valid].sum())
                count += int(valid.sum())
            remaining -= len(chunk)
    if count == 0:
        return float("nan"), float("nan"), 0
    return cur_sum / count, vol_sum / count, count


def fix_current_sheet(
    excel_path: str | Path,
    pt5_path: str | Path,
    output_path: str | Path | None = None,
    *,
    time_offset_sec: float = 0.0,
) -> Path:
    excel_path = Path(excel_path)
    pt5_path = Path(pt5_path)
    output_path = Path(output_path) if output_path else excel_path.with_name("testReport_current_fixed.xlsx")

    meta = load_pt5_meta(pt5_path)
    capture_start = meta["capture_start"]
    if capture_start is None:
        raise RuntimeError("无法从 PT5 文件头解析录制起点 captureDate")

    # 只读取时间相关列，不使用原表电流
    time_cols = ["id", "starttime", "endtime", "duration_sec", "screen"]
    current = pd.read_excel(excel_path, sheet_name="current", usecols=lambda c: c in time_cols)
    current["starttime"] = pd.to_datetime(current["starttime"])
    current["endtime"] = pd.to_datetime(current["endtime"])

    rows = []
    offset = timedelta(seconds=float(time_offset_sec))
    for _, row in current.iterrows():
        st = row["starttime"].to_pydatetime() + offset
        en = row["endtime"].to_pydatetime() + offset
        dur = (en - st).total_seconds()
        t0 = max(0.0, (st - capture_start).total_seconds())
        t1 = min(meta["duration_sec"], (en - capture_start).total_seconds())
        avg_cur, avg_vol, n_valid = segment_stats(pt5_path, meta, t0, t1)
        avg_cur_4v = avg_cur * avg_vol / 4.0 if np.isfinite(avg_cur) and np.isfinite(avg_vol) else np.nan
        rows.append(
            {
                "id": row["id"],
                "starttime": fmt_time(st),
                "endtime": fmt_time(en),
                "duration_sec": round(dur, 6),
                "screen": row["screen"],
                "avg_cur": round(avg_cur, 6) if np.isfinite(avg_cur) else np.nan,
                "avg_vol": round(avg_vol, 6) if np.isfinite(avg_vol) else np.nan,
                "avg_cur_4v": round(avg_cur_4v, 6) if np.isfinite(avg_cur_4v) else np.nan,
                "pt5_sample_count": n_valid,
                "pt5_t0_sec": round(t0, 6),
                "pt5_t1_sec": round(t1, 6),
            }
        )

    fixed = pd.DataFrame(rows)

    def weighted_avg(col: str, screen: str | None = None) -> float:
        sub = fixed if screen is None else fixed[fixed["screen"].astype(str).str.lower() == screen]
        if sub.empty or sub["duration_sec"].sum() == 0:
            return float("nan")
        return float((sub[col] * sub["duration_sec"]).sum() / sub["duration_sec"].sum())

    summary = pd.DataFrame(
        [
            {"项目": "PT5 文件", "值": str(pt5_path)},
            {"项目": "PT5 录制起点", "值": fmt_time(capture_start)},
            {"项目": "时间偏移 (s)", "值": time_offset_sec},
            {"项目": "PT5 采样率 (Hz)", "值": meta["sample_rate_hz"]},
            {"项目": "PT5 总时长 (s)", "值": round(meta["duration_sec"], 3)},
            {"项目": "片段数", "值": len(fixed)},
            {"项目": "加权 avg_cur_4v 全部 (mA)", "值": round(weighted_avg("avg_cur_4v"), 6)},
            {"项目": "加权 avg_cur_4v 亮屏 on (mA)", "值": round(weighted_avg("avg_cur_4v", "on"), 6)},
            {"项目": "加权 avg_cur_4v 灭屏 off (mA)", "值": round(weighted_avg("avg_cur_4v", "off"), 6)},
            {"项目": "加权 avg_cur 全部 (mA)", "值": round(weighted_avg("avg_cur"), 6)},
            {"项目": "加权 avg_cur 亮屏 on (mA)", "值": round(weighted_avg("avg_cur", "on"), 6)},
            {"项目": "加权 avg_cur 灭屏 off (mA)", "值": round(weighted_avg("avg_cur", "off"), 6)},
        ]
    )

    out_current = fixed[
        ["id", "starttime", "endtime", "duration_sec", "screen", "avg_cur", "avg_vol", "avg_cur_4v"]
    ].copy()

    xl = pd.ExcelFile(excel_path)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for sheet in xl.sheet_names:
            if sheet == "current":
                out_current.to_excel(writer, sheet_name="current", index=False)
            else:
                pd.read_excel(excel_path, sheet_name=sheet).to_excel(writer, sheet_name=sheet, index=False)
        fixed.to_excel(writer, sheet_name="current_pt5_detail", index=False)
        summary.to_excel(writer, sheet_name="current_汇总", index=False)

    print(f"PT5 录制起点: {fmt_time(capture_start)}")
    print(f"时间偏移: +{time_offset_sec}s")
    print(f"sample_rate_hz={meta['sample_rate_hz']}, samples={meta['sample_count']}")
    print(f"输出: {output_path}")
    print(out_current.head(8).to_string(index=False))
    return output_path


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="仅按 current 表时间从 total_power.pt5 重算电流")
    parser.add_argument("meta_report_dir", help="meta_report 目录路径")
    parser.add_argument("-o", "--output", help="输出 Excel 路径")
    parser.add_argument(
        "--offset-sec",
        type=float,
        default=0.0,
        help="将所有片段 starttime/endtime 整体后移的秒数（默认 0）",
    )
    args = parser.parse_args()
    meta_dir = Path(args.meta_report_dir)
    excel_path = meta_dir / "testReport.xlsx"
    pt5_path = meta_dir / "total_power.pt5"
    if not excel_path.is_file():
        raise SystemExit(f"未找到 {excel_path}")
    if not pt5_path.is_file():
        raise SystemExit(f"未找到 {pt5_path}")
    out = args.output or str(meta_dir / "testReport_current_fixed.xlsx")
    fix_current_sheet(excel_path, pt5_path, out, time_offset_sec=args.offset_sec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
