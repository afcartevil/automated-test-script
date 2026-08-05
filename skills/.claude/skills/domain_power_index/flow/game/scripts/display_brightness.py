"""步骤 3：亮度（Display）— kernel LCM 背光解析。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

LCM_BACKLIGHT_RE = re.compile(
    r"lcm_setbacklight(?:_cmdq(?:_v2)?)?\s+level\s*=\s*(?P<level>\d+)\s*,\s*mapped_level\s*=\s*(?P<mapped>\d+)",
    re.IGNORECASE,
)
HWC_BRIGHTNESS_VAL_RE = re.compile(
    r"\[LEDDEV\]\s+calculateBrightness:\s*brightness\((?P<ratio>[\d.]+)\)\s*brightness_val\((?P<val>\d+)\)"
)
HWC_MAX_BRIGHTNESS_RE = re.compile(r"max_brightness\((?P<max>\d+)\)")
KERNEL_BOOT_SEC_RE = re.compile(r"^\s*<\d+>\[\s*(?P<boot>[\d.]+)\]")
KERNEL_ANDROID_TIME_RE = re.compile(
    r"android time (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)"
)
TIMEZONE_HEADER_RE = re.compile(r"----- timezone:(?P<tz>[^\n]+)")

TZ_UTC_OFFSET_HOURS: dict[str, float] = {
    "Africa/Nairobi": 3.0,
    "Asia/Shanghai": 8.0,
    "Asia/Kolkata": 5.5,
    "Europe/Berlin": 1.0,
    "America/New_York": -5.0,
}

RAMP_GAP_SECONDS = 10
MIN_TRANSITION_LEVEL_DELTA = 20
MAX_TRANSITIONS_IN_SUMMARY = 50
LCM_LEVEL_MAX = 2047


def _level_pct(level: int | None, level_max: int = LCM_LEVEL_MAX) -> float | None:
    if level is None:
        return None
    return round(100.0 * level / level_max, 1)


def _ratio_pct(ratio: float | None) -> float | None:
    if ratio is None:
        return None
    return round(ratio * 100.0, 1)


def _dedupe_consecutive_vals(samples: list[dict[str, Any]], key: str = "level") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sample in samples:
        if out and out[-1][key] == sample[key]:
            continue
        out.append(sample)
    return out


def _sample_evidence(sample: dict[str, Any]) -> str:
    return f"{sample['source_file']}:{sample['line_no']}: {sample['raw_line']}"


def _pick_level_sample(samples: list[dict[str, Any]], level: int) -> dict[str, Any] | None:
    for sample in reversed(samples):
        if sample.get("level") == level:
            return sample
    return None


def _parse_android_time_utc(text: str) -> datetime | None:
    m = KERNEL_ANDROID_TIME_RE.search(text)
    if not m:
        return None
    raw = m.group(1)
    try:
        return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return None


def _utc_to_local(dt_utc: datetime, timezone_name: str) -> datetime:
    offset = TZ_UTC_OFFSET_HOURS.get(timezone_name.strip(), 0.0)
    return dt_utc + timedelta(hours=offset)


def _boot_sec_from_line(line: str) -> float | None:
    m = KERNEL_BOOT_SEC_RE.search(line)
    if not m:
        return None
    try:
        return float(m.group("boot"))
    except ValueError:
        return None


class _BootTimeCalibrator:
    def __init__(self, timezone_name: str = "") -> None:
        self.timezone_name = timezone_name
        self.anchors: list[tuple[float, datetime]] = []

    def feed_anchor_line(self, line: str) -> None:
        boot = _boot_sec_from_line(line)
        utc = _parse_android_time_utc(line)
        if boot is None or utc is None:
            return
        local = _utc_to_local(utc, self.timezone_name)
        if self.anchors and boot <= self.anchors[-1][0]:
            return
        self.anchors.append((boot, local))

    def boot_to_local(self, boot_sec: float) -> datetime | None:
        if not self.anchors:
            return None
        if boot_sec <= self.anchors[0][0]:
            b0, t0 = self.anchors[0]
            return t0 - timedelta(seconds=b0 - boot_sec)
        for i in range(1, len(self.anchors)):
            b0, t0 = self.anchors[i - 1]
            b1, t1 = self.anchors[i]
            if b0 <= boot_sec <= b1:
                ratio = (boot_sec - b0) / (b1 - b0) if b1 > b0 else 0.0
                return t0 + (t1 - t0) * ratio
        b0, t0 = self.anchors[-1]
        return t0 + timedelta(seconds=boot_sec - b0)


def _read_timezone(path: Path, iter_lines: Callable[[Path], Any]) -> str:
    for _, line in iter_lines(path):
        m = TIMEZONE_HEADER_RE.search(line)
        if m:
            return m.group("tz").strip()
        if line.strip() and not line.startswith("-----"):
            break
    return ""


def _collapse_same_timestamp(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """linli_666 同一时间戳常批量打印多档；保留该时刻最后一档。"""
    out: list[dict[str, Any]] = []
    for sample in samples:
        if out and out[-1]["dt"] == sample["dt"]:
            out[-1] = sample
        else:
            out.append(sample)
    return out


def _dedupe_consecutive_levels(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """去掉连续相同 level，消除逐步调光中的重复采样。"""
    out: list[dict[str, Any]] = []
    for sample in samples:
        if out and out[-1]["level"] == sample["level"]:
            continue
        out.append(sample)
    return out


def _collapse_ramps(
    samples: list[dict[str, Any]],
    gap_seconds: int = RAMP_GAP_SECONDS,
    min_level_delta: int = MIN_TRANSITION_LEVEL_DELTA,
) -> list[dict[str, Any]]:
    """10 秒内同向阶梯调光合并；净变化 < min_level_delta 的抖动段丢弃。"""
    if len(samples) < 2:
        return []
    ramps: list[dict[str, Any]] = []
    i = 0
    n = len(samples)
    while i < n - 1:
        start = samples[i]
        direction: int | None = None
        j = i + 1
        while j < n:
            gap = (samples[j]["dt"] - samples[j - 1]["dt"]).total_seconds()
            if gap > gap_seconds:
                break
            delta = samples[j]["level"] - samples[j - 1]["level"]
            if delta == 0:
                j += 1
                continue
            step_dir = 1 if delta > 0 else -1
            if direction is None:
                direction = step_dir
            elif step_dir != direction:
                break
            j += 1
        end = samples[j - 1]
        level_delta = abs(end["level"] - start["level"])
        if level_delta >= min_level_delta:
            ramps.append(
                {
                    "time_start": start["time"],
                    "time_end": end["time"],
                    "level_from": start["level"],
                    "level_to": end["level"],
                    "mapped_from": start["mapped_level"],
                    "mapped_to": end["mapped_level"],
                    "direction": "up" if end["level"] > start["level"] else "down",
                    "level_delta": level_delta,
                    "sample_count": j - i,
                    "duration_seconds": round((end["dt"] - start["dt"]).total_seconds(), 2),
                }
            )
        i = j if j > i + 1 else i + 1
    return ramps


def _significant_step_transitions(
    samples: list[dict[str, Any]],
    min_level_delta: int = MIN_TRANSITION_LEVEL_DELTA,
) -> list[dict[str, Any]]:
    """linli 粗时间轴：相邻去重点净变化 >= min_level_delta 记为一次变光。"""
    ramps: list[dict[str, Any]] = []
    for i in range(1, len(samples)):
        prev = samples[i - 1]
        cur = samples[i]
        level_delta = abs(cur["level"] - prev["level"])
        if level_delta < min_level_delta:
            continue
        ramps.append(
            {
                "time_start": prev["time"],
                "time_end": cur["time"],
                "level_from": prev["level"],
                "level_to": cur["level"],
                "mapped_from": prev["mapped_level"],
                "mapped_to": cur["mapped_level"],
                "direction": "up" if cur["level"] > prev["level"] else "down",
                "level_delta": level_delta,
                "sample_count": 2,
                "duration_seconds": round((cur["dt"] - prev["dt"]).total_seconds(), 2),
            }
        )
    return ramps


def _pick_transitions(
    raw_count: int,
    deduped: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """原始行远多于去重点时用阶梯变光；否则用 10s 同向 ramp 合并。"""
    if raw_count > len(deduped) * 50:
        return _significant_step_transitions(deduped)
    return _collapse_ramps(deduped)


HWC_MIN_TRANSITION_DELTA = 20
HWC_RAMP_GAP_SECONDS = 30
NEAR_GAME_END_SECONDS = 90
DIP_RECOVER_WINDOW_SECONDS = 120
SCREEN_BRIGHTNESS_MODE_RE = re.compile(r"screen_brightness_mode", re.IGNORECASE)


def _collapse_val_ramps(
    samples: list[dict[str, Any]],
    gap_seconds: int = HWC_RAMP_GAP_SECONDS,
    min_delta: int = HWC_MIN_TRANSITION_DELTA,
) -> list[dict[str, Any]]:
    """hwcomposer：30s 内同向阶梯调光合并为一段。"""
    if len(samples) < 2:
        return []
    ramps: list[dict[str, Any]] = []
    i = 0
    n = len(samples)
    while i < n - 1:
        start = samples[i]
        direction: int | None = None
        j = i + 1
        while j < n:
            gap = (samples[j]["dt"] - samples[j - 1]["dt"]).total_seconds()
            if gap > gap_seconds:
                break
            delta = samples[j]["brightness_val"] - samples[j - 1]["brightness_val"]
            if delta == 0:
                j += 1
                continue
            step_dir = 1 if delta > 0 else -1
            if direction is None:
                direction = step_dir
            elif step_dir != direction:
                break
            j += 1
        end = samples[j - 1]
        val_delta = abs(end["brightness_val"] - start["brightness_val"])
        if val_delta >= min_delta:
            ramps.append(
                {
                    "time_start": start["time"],
                    "time_end": end["time"],
                    "dt_start": start["dt"],
                    "dt_end": end["dt"],
                    "brightness_val_from": start["brightness_val"],
                    "brightness_val_to": end["brightness_val"],
                    "direction": "up" if end["brightness_val"] > start["brightness_val"] else "down",
                    "brightness_val_delta": val_delta,
                    "sample_count": j - i,
                    "duration_seconds": round((end["dt"] - start["dt"]).total_seconds(), 2),
                }
            )
        i = j if j > i + 1 else i + 1
    return ramps


def _classify_hwc_ramps(
    ramps: list[dict[str, Any]],
    game_end: datetime | None,
) -> list[dict[str, Any]]:
    """区分游戏中事件调光、临近结束、dip-recover 等语义。"""
    out: list[dict[str, Any]] = []
    for i, ramp in enumerate(ramps):
        item = dict(ramp)
        dt_start = ramp.get("dt_start")
        secs_to_end = (
            (game_end - dt_start).total_seconds()
            if game_end and dt_start
            else None
        )
        kind = "in_game_change"
        hint = "游戏内背光变化"

        if ramp["direction"] == "down" and ramp["duration_seconds"] <= HWC_RAMP_GAP_SECONDS:
            kind = "event_dim_ramp"
            hint = "短时阶梯降亮（常见于阵亡遮罩/弹窗/温控降亮）"
            if i + 1 < len(ramps):
                nxt = ramps[i + 1]
                gap = (nxt["dt_start"] - ramp["dt_end"]).total_seconds()
                if (
                    nxt["direction"] == "up"
                    and gap <= DIP_RECOVER_WINDOW_SECONDS
                    and nxt["brightness_val_to"] >= ramp["brightness_val_from"] - HWC_MIN_TRANSITION_DELTA
                ):
                    kind = "dip_recover"
                    hint = "先降后升（阵亡变暗后恢复等短暂遮罩）"
        elif secs_to_end is not None and 0 <= secs_to_end <= NEAR_GAME_END_SECONDS:
            kind = "near_game_end"
            hint = "临近游戏结束时的变光（可能为退出/切前台）"
        elif ramp["direction"] == "up" and i > 0:
            prev = ramps[i - 1]
            gap = (ramp["dt_start"] - prev["dt_end"]).total_seconds()
            if prev["direction"] == "down" and gap <= DIP_RECOVER_WINDOW_SECONDS:
                kind = "event_recover_ramp"
                hint = "事件遮罩结束后的亮度恢复"
        elif ramp["direction"] == "down":
            kind = "sustained_dim"
            hint = "持续降亮且未在短时间内恢复"

        item["kind"] = kind
        item["hint"] = hint
        if secs_to_end is not None:
            item["seconds_before_game_end"] = round(secs_to_end, 1)
        item.pop("dt_start", None)
        item.pop("dt_end", None)
        out.append(item)
    return out


def _analyze_hwc_phases(
    game_deduped: list[dict[str, Any]],
    game_raw_count: int,
    baseline_val: int | None,
    game_start: datetime | None,
    game_end: datetime | None,
    post_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    """按时间窗区分：游戏前基线 / 游戏内稳定 / 变光段 / 稳定尾部 / 游戏后。"""
    ramp_samples = list(game_deduped)
    if baseline_val is not None and game_start and ramp_samples and ramp_samples[0]["dt"] > game_start:
        ramp_samples.insert(
            0,
            {
                "time": game_start.strftime("%m-%d %H:%M:%S.%f"),
                "dt": game_start,
                "brightness_val": baseline_val,
            },
        )
    ramps_all = _collapse_val_ramps(ramp_samples) if len(ramp_samples) >= 2 else []
    ramps = ramps_all[:MAX_TRANSITIONS_IN_SUMMARY]
    classified = _classify_hwc_ramps(ramps_all, game_end)

    stable_plateau: dict[str, Any] | None = None
    stable_tail: dict[str, Any] | None = None
    if game_start and game_end:
        plateau_val = baseline_val
        plateau_end = game_end
        if game_deduped:
            plateau_end = game_deduped[0]["dt"]
            if plateau_val is None:
                plateau_val = game_deduped[0]["brightness_val"]
        duration = max(0.0, (plateau_end - game_start).total_seconds())
        if duration >= 1.0 and plateau_val is not None:
            stable_plateau = {
                "brightness_val": plateau_val,
                "time_start": game_start.strftime("%m-%d %H:%M:%S.%f") if hasattr(game_start, "strftime") else None,
                "time_end": game_deduped[0]["time"] if game_deduped else None,
                "duration_seconds": round(duration, 1),
                "inferred_no_logs": len(game_deduped) == 0 or duration > 5,
                "note": "hwcomposer 仅在变光时打印；无采样段视为与基线相同",
            }
        if ramps_all and game_deduped:
            last_ramp = ramps_all[-1]
            tail_start = last_ramp["dt_end"]
            tail_val = last_ramp["brightness_val_to"]
            tail_dur = max(0.0, (game_end - tail_start).total_seconds())
            if tail_dur >= 1.0:
                stable_tail = {
                    "brightness_val": tail_val,
                    "time_start": last_ramp["time_end"],
                    "duration_seconds": round(tail_dur, 1),
                    "note": "最后一次变光后至游戏结束保持稳定",
                }

    post_window: dict[str, Any] | None = None
    if post_samples:
        post_deduped = _dedupe_consecutive_vals(post_samples, "brightness_val")
        vals = [s["brightness_val"] for s in post_deduped]
        post_window = {
            "sample_count": len(post_samples),
            "brightness_val_min": min(vals) if vals else None,
            "brightness_val_max": max(vals) if vals else None,
            "first_sample": {
                "time": post_deduped[0]["time"],
                "brightness_val": post_deduped[0]["brightness_val"],
                "raw_evidence": _sample_evidence(post_deduped[0]),
            }
            if post_deduped
            else None,
            "note": "T_post 变光不归入 T_game 功耗归因",
        }

    return {
        "stable_plateau": stable_plateau,
        "stable_tail": stable_tail,
        "transition_count": len(ramps_all),
        "transitions": classified[:MAX_TRANSITIONS_IN_SUMMARY],
        "post_game_window": post_window,
    }


def _probe_screen_brightness_mode(main_sys_files: list[Path], iter_lines: Callable[[Path], Any]) -> dict[str, Any] | None:
    """检测自动背光模式注册行（排除 okhttp 等误匹配）。"""
    for path in main_sys_files:
        for line_no, line in iter_lines(path):
            if "okhttp" in line.lower() or "dimensionList" in line:
                continue
            if not SCREEN_BRIGHTNESS_MODE_RE.search(line):
                continue
            return {
                "detected": True,
                "auto_brightness_likely": True,
                "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:200]}",
            }
    return None


def parse_kernel_backlight(
    kernel_files: list[Path],
    events: list[dict[str, Any]],
    add_event: Callable[[list[dict[str, Any]], dict[str, Any]], None],
    extract_ts: Callable[[str], tuple[str | None, datetime | None]],
    window_for: Callable[..., str | None],
    iter_lines: Callable[[Path], Any],
    fmt_time: Callable[[datetime | None], str],
    game_start: datetime | None,
    game_end: datetime | None,
    pre_s: int,
    post_s: int,
) -> dict[str, Any]:
    raw_samples: list[dict[str, Any]] = []

    for path in kernel_files:
        use_linli = "linli_666" in path.name.lower()
        tz = _read_timezone(path, iter_lines) if not use_linli else ""
        cal = _BootTimeCalibrator(tz)
        for line_no, line in iter_lines(path):
            if not use_linli and "android time" in line:
                cal.feed_anchor_line(line)
            m = LCM_BACKLIGHT_RE.search(line)
            if not m:
                continue

            level = int(m.group("level"))
            mapped = int(m.group("mapped"))
            ts_raw, dt = extract_ts(line)
            if dt is None and not use_linli:
                boot = _boot_sec_from_line(line)
                if boot is not None:
                    dt = cal.boot_to_local(boot)
                    if dt:
                        ts_raw = fmt_time(dt)
            if dt is None:
                continue

            window = window_for(dt, game_start, game_end, pre_s, post_s) or "unknown"
            raw_samples.append(
                {
                    "time": ts_raw or "",
                    "dt": dt,
                    "window": window,
                    "level": level,
                    "mapped_level": mapped,
                    "source_file": path.name,
                    "line_no": line_no,
                    "raw_line": line.strip()[:220],
                }
            )

    raw_samples.sort(key=lambda s: s["dt"])
    samples = _dedupe_consecutive_levels(_collapse_same_timestamp(raw_samples))

    for sample in samples:
        add_event(
            events,
            {
                "time": sample["time"],
                "window": sample["window"],
                "source": "kernel",
                "category": "display_brightness",
                "level": sample["level"],
                "mapped_level": sample["mapped_level"],
                "raw_evidence": f"{sample['source_file']}:{sample['line_no']}: {sample['raw_line']}",
            },
        )

    baseline: dict[str, Any] | None = None
    pre_samples = [s for s in samples if game_start and s["dt"] < game_start]
    if pre_samples:
        last = pre_samples[-1]
        baseline = {
            "time": last["time"],
            "level": last["level"],
            "mapped_level": last["mapped_level"],
            "level_pct": _level_pct(last["level"]),
            "window": last["window"],
            "source": "kernel_lcm",
            "raw_evidence": _sample_evidence(last),
        }
    elif samples and game_start:
        baseline = {
            "time": None,
            "level": None,
            "mapped_level": None,
            "window": "T_pre",
            "source": "kernel_lcm",
            "note": "T_pre 无 lcm 采样，游戏开始前无可用基线",
        }

    game_samples = [
        s for s in samples if game_start and game_end and game_start <= s["dt"] <= game_end
    ]
    game_raw = [s for s in raw_samples if s.get("window") == "T_game"]
    game_deduped = _dedupe_consecutive_levels(game_samples)
    levels = [s["level"] for s in game_deduped]
    mapped_levels = [s["mapped_level"] for s in game_deduped]

    game_raw_count = len([s for s in raw_samples if s.get("window") == "T_game"])
    ramps_all = _pick_transitions(game_raw_count, game_deduped) if game_deduped else []
    ramps = ramps_all[:MAX_TRANSITIONS_IN_SUMMARY]
    significant_change = bool(ramps) or (
        levels and (max(levels) - min(levels) >= MIN_TRANSITION_LEVEL_DELTA)
    )

    coverage = "missing"
    notes: list[str] = []
    if not raw_samples:
        notes.append("kernel 日志中未找到 lcm_setbacklight(_cmdq/_v2) 行")
    elif not baseline or baseline.get("level") is None:
        coverage = "partial"
        notes.append("游戏开始前无 lcm 背光基线（kernel 时间覆盖不足或未对齐）")
    elif not game_samples:
        coverage = "partial"
        notes.append("T_game 内无 lcm 背光采样")
    else:
        coverage = "ok"

    if significant_change and ramps:
        extra = len(ramps_all) - len(ramps)
        notes.append(
            f"T_game 内有效背光变光 {len(ramps_all)} 段（≥{MIN_TRANSITION_LEVEL_DELTA} level，"
            f"{RAMP_GAP_SECONDS}s 同向合并；原始 {len(raw_samples)} 条→去重 {len(samples)} 条）"
        )
        if extra > 0:
            notes.append(f"transitions 摘要仅保留前 {MAX_TRANSITIONS_IN_SUMMARY} 段（共 {len(ramps_all)} 段）")
    elif game_deduped and not significant_change:
        notes.append(
            f"T_game 内背光波动 <{MIN_TRANSITION_LEVEL_DELTA} level，视为恒定 "
            f"level={game_deduped[0]['level']}"
        )

    level_min = min(levels) if levels else None
    level_max = max(levels) if levels else None
    raw_levels = [s["level"] for s in game_raw] if game_raw else []
    raw_level_min = min(raw_levels) if raw_levels else level_min
    raw_level_max = max(raw_levels) if raw_levels else level_max
    min_sample = _pick_level_sample(game_raw or game_deduped, raw_level_min) if raw_level_min is not None else None
    max_sample = _pick_level_sample(game_raw or game_deduped, raw_level_max) if raw_level_max is not None else None

    game_stats: dict[str, Any] = {
        "sample_count_raw": len(game_raw),
        "sample_count_deduped": len(game_deduped),
        "changed": significant_change,
        "level_min": level_min,
        "level_max": level_max,
        "level_min_raw": raw_level_min,
        "level_max_raw": raw_level_max,
        "level_min_pct": _level_pct(raw_level_min),
        "level_max_pct": _level_pct(raw_level_max),
        "mapped_level_min": min(mapped_levels) if mapped_levels else None,
        "mapped_level_max": max(mapped_levels) if mapped_levels else None,
        "start_level": game_deduped[0]["level"] if game_deduped else None,
        "end_level": game_deduped[-1]["level"] if game_deduped else None,
        "level_min_sample": (
            {
                "time": min_sample["time"],
                "level": min_sample["level"],
                "mapped_level": min_sample["mapped_level"],
                "raw_evidence": _sample_evidence(min_sample),
            }
            if min_sample
            else None
        ),
        "level_max_sample": (
            {
                "time": max_sample["time"],
                "level": max_sample["level"],
                "mapped_level": max_sample["mapped_level"],
                "raw_evidence": _sample_evidence(max_sample),
            }
            if max_sample
            else None
        ),
        "transition_count": len(ramps_all),
        "transition_count_in_summary": len(ramps),
        "transitions": ramps,
        "stable": not significant_change,
    }

    if baseline and baseline.get("level") is not None and game_deduped:
        delta = game_deduped[-1]["level"] - baseline["level"]
        game_stats["delta_from_baseline"] = delta
        game_stats["baseline_match"] = abs(delta) < MIN_TRANSITION_LEVEL_DELTA

    return {
        "source": "kernel_lcm",
        "pattern": "lcm_setbacklight(_cmdq/_v2)",
        "coverage": coverage,
        "total_samples_raw": len(raw_samples),
        "total_samples_deduped": len(samples),
        "filter": {
            "min_transition_level_delta": MIN_TRANSITION_LEVEL_DELTA,
            "ramp_gap_seconds": RAMP_GAP_SECONDS,
            "max_transitions_in_summary": MAX_TRANSITIONS_IN_SUMMARY,
        },
        "baseline_before_game": baseline,
        "game_window": game_stats,
        "notes": notes,
    }


def parse_hwcomposer_brightness(
    main_sys_files: list[Path],
    events: list[dict[str, Any]],
    add_event: Callable[[list[dict[str, Any]], dict[str, Any]], None],
    extract_ts: Callable[[str], tuple[str | None, datetime | None]],
    window_for: Callable[..., str | None],
    iter_lines: Callable[[Path], Any],
    game_start: datetime | None,
    game_end: datetime | None,
    pre_s: int,
    post_s: int,
) -> dict[str, Any]:
    """步骤 3 补充源：main/sys hwcomposer [LEDDEV] calculateBrightness。"""
    raw_samples: list[dict[str, Any]] = []
    max_brightness_seen = 5119

    for path in main_sys_files:
        for line_no, line in iter_lines(path):
            max_m = HWC_MAX_BRIGHTNESS_RE.search(line)
            if max_m:
                max_brightness_seen = int(max_m.group("max"))
            m = HWC_BRIGHTNESS_VAL_RE.search(line)
            if not m:
                continue
            ts_raw, dt = extract_ts(line)
            if not dt:
                continue
            val = int(m.group("val"))
            ratio = float(m.group("ratio"))
            window = window_for(dt, game_start, game_end, pre_s, post_s) or "unknown"
            raw_samples.append(
                {
                    "time": ts_raw or "",
                    "dt": dt,
                    "window": window,
                    "level": val,
                    "brightness_val": val,
                    "brightness_ratio": ratio,
                    "max_brightness": max_brightness_seen,
                    "source_file": path.name,
                    "line_no": line_no,
                    "raw_line": line.strip()[:240],
                }
            )

    raw_samples.sort(key=lambda s: s["dt"])
    samples = _dedupe_consecutive_vals(raw_samples, "brightness_val")

    for sample in samples:
        add_event(
            events,
            {
                "time": sample["time"],
                "window": sample["window"],
                "source": "main",
                "category": "display_brightness_hwc",
                "brightness_val": sample["brightness_val"],
                "brightness_ratio": sample["brightness_ratio"],
                "max_brightness": sample["max_brightness"],
                "raw_evidence": _sample_evidence(sample),
            },
        )

    pre_samples = [s for s in samples if game_start and s["dt"] < game_start]
    baseline: dict[str, Any] | None = None
    if pre_samples:
        last = pre_samples[-1]
        baseline = {
            "time": last["time"],
            "brightness_val": last["brightness_val"],
            "brightness_ratio": last["brightness_ratio"],
            "brightness_val_pct": _level_pct(last["brightness_val"], last["max_brightness"]),
            "brightness_ratio_pct": _ratio_pct(last["brightness_ratio"]),
            "max_brightness": last["max_brightness"],
            "window": last["window"],
            "source": "hwcomposer_leddev",
            "raw_evidence": _sample_evidence(last),
        }

    game_samples = [
        s for s in samples if game_start and game_end and game_start <= s["dt"] <= game_end
    ]
    game_raw = [s for s in raw_samples if s.get("window") == "T_game"]
    game_deduped = _dedupe_consecutive_vals(game_samples, "brightness_val")
    vals = [s["brightness_val"] for s in game_deduped]
    raw_vals = [s["brightness_val"] for s in game_raw]
    ratios = [s["brightness_ratio"] for s in game_raw]

    val_min = min(raw_vals) if raw_vals else (min(vals) if vals else None)
    val_max = max(raw_vals) if raw_vals else (max(vals) if vals else None)
    min_sample = _pick_level_sample(game_raw or game_deduped, val_min) if val_min is not None else None
    max_sample = _pick_level_sample(game_raw or game_deduped, val_max) if val_max is not None else None
    max_b = (min_sample or max_sample or {}).get("max_brightness") or max_brightness_seen

    coverage = "missing"
    notes: list[str] = []
    if not raw_samples:
        notes.append("main/sys 中未找到 hwcomposer [LEDDEV] calculateBrightness brightness_val 行")
    elif not game_raw:
        coverage = "partial"
        notes.append("T_game 内无 hwcomposer 亮度采样")
    else:
        coverage = "ok"
        if val_min == val_max:
            notes.append(f"T_game hwcomposer brightness_val 恒定={val_min}")
        else:
            notes.append(f"T_game hwcomposer brightness_val 范围 {val_min}~{val_max}（原始 {len(game_raw)} 条）")

    baseline_val = (baseline or {}).get("brightness_val")
    post_samples = [
        s for s in samples if game_end and s["dt"] > game_end
    ]
    phases = _analyze_hwc_phases(
        game_deduped,
        len(game_raw),
        baseline_val,
        game_start,
        game_end,
        post_samples,
    )
    brightness_mode = _probe_screen_brightness_mode(main_sys_files, iter_lines)

    game_stats: dict[str, Any] = {
        "sample_count_raw": len(game_raw),
        "sample_count_deduped": len(game_deduped),
        "max_brightness": max_b,
        "brightness_val_min": val_min,
        "brightness_val_max": val_max,
        "brightness_val_min_pct": _level_pct(val_min, max_b),
        "brightness_val_max_pct": _level_pct(val_max, max_b),
        "brightness_ratio_min": round(min(ratios), 6) if ratios else None,
        "brightness_ratio_max": round(max(ratios), 6) if ratios else None,
        "brightness_ratio_min_pct": _ratio_pct(min(ratios)) if ratios else None,
        "brightness_ratio_max_pct": _ratio_pct(max(ratios)) if ratios else None,
        "changed": val_min != val_max if val_min is not None and val_max is not None else False,
        "brightness_val_min_sample": (
            {
                "time": min_sample["time"],
                "brightness_val": min_sample["brightness_val"],
                "brightness_ratio": min_sample["brightness_ratio"],
                "raw_evidence": _sample_evidence(min_sample),
            }
            if min_sample
            else None
        ),
        "brightness_val_max_sample": (
            {
                "time": max_sample["time"],
                "brightness_val": max_sample["brightness_val"],
                "brightness_ratio": max_sample["brightness_ratio"],
                "raw_evidence": _sample_evidence(max_sample),
            }
            if max_sample
            else None
        ),
        **phases,
    }

    if phases.get("stable_plateau"):
        sp = phases["stable_plateau"]
        notes.append(
            f"T_game 开局稳定 {sp['duration_seconds']}s @ brightness_val={sp['brightness_val']}（无 hwc 采样=未变光）"
        )
    if phases.get("transition_count"):
        notes.append(f"T_game 有效变光 {phases['transition_count']} 段（30s 同向合并）")
        for tr in phases.get("transitions") or []:
            notes.append(
                f"  [{tr.get('kind')}] {tr.get('time_start')}→{tr.get('time_end')} "
                f"{tr.get('brightness_val_from')}→{tr.get('brightness_val_to')} ({tr.get('hint')})"
            )
    if phases.get("stable_tail"):
        st = phases["stable_tail"]
        notes.append(
            f"变光后稳定 {st['duration_seconds']}s @ brightness_val={st['brightness_val']} 至游戏结束"
        )
    if phases.get("post_game_window"):
        pg = phases["post_game_window"]
        if pg.get("brightness_val_min") is not None:
            notes.append(
                f"T_post 亮度 {pg['brightness_val_min']}~{pg['brightness_val_max']}（不计入 T_game）"
            )
    if brightness_mode:
        notes.append("检测到 screen_brightness_mode（自动背光可能开启）")

    return {
        "source": "hwcomposer_leddev",
        "pattern": "hwcomposer [LEDDEV] calculateBrightness",
        "coverage": coverage,
        "total_samples_raw": len(raw_samples),
        "total_samples_deduped": len(samples),
        "baseline_before_game": baseline,
        "screen_brightness_mode": brightness_mode,
        "game_window": game_stats,
        "notes": notes,
    }
