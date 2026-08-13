import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta


WAKEUP_FIELDS = (
    "AP_suspend_failed",
    "frequent_wakeup",
    "frequent_wakeup_reason",
    "26M_LPM_abnormal",
    "26M_LPM_reason",
    "screen_wakeup",
    "screen_wakeup_type",
    "screen_wakeup_detail",
    "power_button_evidence_count",
)

SUSPEND_FAIL_KEYS = ("aborting suspend", "abort suspend", "active wakeup source", "pending wakeup sources")
POWER_KEY_KEYS = ("power_button", "wake_reason_power_button", "android.policy:power")
SCREEN_OFF_KEYS = ("going to sleep", "go to sleep", "screenon=false", "screen on=false")
SCREEN_ON_KEYS = ("waking up", "screenon=true", "screen on=true")
NOTIFICATION_KEYS = ("wlan", "wifi", "rtc", "alarm", "timer", "sched", "modem", "ccif", "conn", "bt", "ble", "nfc")
LOCAL_TZ_OFFSET_HOURS = 8

R12_BIT_DEFINITIONS = {
    0: "R12_PCM_TIMER_EVENT",
    1: "R12_SPM_TWAM_IRQ_B",
    2: "R12_KP_IRQ_B",
    3: "R12_APWDT_EVENT_B",
    4: "R12_APXGPT1_EVENT_B",
    5: "R12_CONN2AP_SPM_WAKEUP_B",
    6: "R12_EINT_EVENT_B",
    7: "R12_CONN_WDT_IRQ_B",
    8: "R12_CCIF0_EVENT_B",
    9: "R12_LOWBATTERY_IRQ_B",
    10: "R12_SC_SSPM2SPM_WAKEUP",
    11: "R12_SC_SCP2SPM_WAKEUP",
    12: "R12_SC_ADSP2SPM_WAKEUP",
    13: "R12_PCM_WDT_EVENT_B",
    14: "R12_USBX_CDSC_B",
    15: "R12_USBX_POWERDWN_B",
    16: "R12_SYS_TIMER_EVENT_B",
    17: "R12_EINT_EVENT_SECURE_B",
    18: "R12_CCIF1_EVENT_B",
    19: "R12_UART0_IRQ_B",
    20: "R12_AFE_IRQ_MCU_B",
    21: "R12_THERMAL_CTRL_EVENT_B",
    22: "R12_SYS_CIRQ_IRQ_B",
    23: "R12_MD2AP_PEER_WAKEUP_EVENT",
    24: "R12_CSYSPWREQ_B",
    25: "R12_MD1_WDT_B",
    26: "R12_AP2AP_PEER_WAKEUPEVENT_B",
    27: "R12_SEJ_EVENT_B",
    28: "R12_SPM_CPU_WAKEUP_EVENT",
    29: "R12_CPU_IRQOUT",
    30: "R12_CPU_WFI",
    31: "R12_MCUSYS_IDLE_TO_EMI_ALL",
}

R13_BIT_DEFINITIONS = {
    0: "R13_SRCCLKENI0",
    1: "R13_SRCCLKENI1",
    2: "R13_MD_0_SRCCLKENA",
    3: "R13_MD_0_APSRC_REQ",
    4: "R13_CONN_DDREN",
    5: "R13_MD_1_SRCCLKENA",
    6: "R13_SSPM_SRCCLKENA",
    7: "R13_SSPM_APSRC_REQ",
    8: "R13_MD_1_STATE",
    9: "R13_RC_SRCCLKENO_ACK",
    10: "R13_MM_STATE",
    11: "R13_SSPM_STATE",
    12: "R13_MD_0_DDREN",
    13: "R13_CONN_STATE",
    14: "R13_CONN_SRCCLKENA",
    15: "R13_CONN_APSRC_REQ",
    16: "R13_SC_DDR_PST_ACK_ALL",
    17: "R13_SC_DDR_PST_ABORT_ACK_ALL",
    18: "R13_SCP_STATE",
    19: "R13_CSYSPWRUPREQ",
    20: "R13_PWRAP_SLEEP_ACK",
    21: "R13_SC_EMI_CLK_OFF_ACK_ALL",
    22: "R13_AUDIO_DSP_STATE",
    23: "R13_SC_DMDRAMCSHU_ACK_ALL",
    24: "R13_CONN_SRCCLKENB",
    25: "R13_SC_DR_SRAM_LOAD_ACK_ALL",
    26: "R13_SUBSYS_IDLE_SIGNALS0",
    27: "R13_DVFS_STATE",
    28: "R13_SC_DR_SRAM_PLL_LOAD_ACK_ALL",
    29: "R13_SC_DR_SRAM_RESTORE_ACK_ALL",
    30: "R13_MD_0_VRF18_REQ",
    31: "R13_DDR_EN_STATE",
}


def _setup_utf8_stdio() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _extract_year_from_filename(path: str) -> int:
    match = re.search(r"_(\d{4})_\d{4}_", os.path.basename(path))
    if match:
        year = int(match.group(1))
        if 2000 <= year <= 2100:
            return year
    return 2026


def _parse_time_literal(value: str | None, base_year: int) -> datetime | None:
    s = (value or "").strip()
    if not s:
        return None

    # 支持带时区标识的字符串（如 "... UTC" / "...Z"），按 UTC 转到本地时区（UTC+8）
    is_utc = bool(re.search(r"\bUTC\b", s, flags=re.IGNORECASE) or re.search(r"Z$", s, flags=re.IGNORECASE))
    s = re.sub(r"\bUTC\b", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"Z$", "", s, flags=re.IGNORECASE).strip()

    m = re.match(r"^(\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})(\.\d+)?$", s)
    if m:
        frac = m.group(3) or ""
        new_s = f"{base_year}-{m.group(1)} {m.group(2)}{frac}"
        fmt = "%Y-%m-%d %H:%M:%S.%f" if frac else "%Y-%m-%d %H:%M:%S"
        try:
            dt = datetime.strptime(new_s, fmt)
            return dt + timedelta(hours=LOCAL_TZ_OFFSET_HOURS) if is_utc else dt
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt + timedelta(hours=LOCAL_TZ_OFFSET_HOURS) if is_utc else dt
        except ValueError:
            continue
    return None


def _extract_android_time(line: str) -> str | None:
    """提取 Android 时间关键字对应的时间串。

    支持：
    - 行首 Android log 时间：MM-DD HH:MM:SS(.f)
    - 显式关键字：android time=YYYY-MM-DD HH:MM:SS(.f) [UTC]
    - 显式关键字：android time: MM-DD HH:MM:SS(.f) [UTC]
    - 显式关键字：android time YYYY-MM-DD HH:MM:SS(.f) [UTC]
    """
    if not line:
        return None

    # 1) 显式关键字：android time <...> / android time=<...> / android time:<...>
    kw_m = re.search(
        r"android\s*time(?:\s*[:=]|\s+)\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\s*UTC|Z)?|\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:\s*UTC|Z)?)",
        line,
        flags=re.IGNORECASE,
    )
    if kw_m:
        return kw_m.group(1)

    # 2) 行首 Android 时间
    head_m = re.match(r"^\s*(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)", line)
    if head_m:
        return head_m.group(1)

    return None


def _line_dt(line: str, base_year: int) -> datetime | None:
    # 优先使用 Android time（用户要求：获取时间关键字 android time）
    android_time = _extract_android_time(line)
    if android_time:
        dt = _parse_time_literal(android_time, base_year)
        if dt is not None:
            return dt

    abs_m = re.search(r"\[(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)\]", line)
    if abs_m:
        return _parse_time_literal(abs_m.group(1), base_year)
    return None


def _in_window(dt: datetime | None, start_dt: datetime | None, end_dt: datetime | None) -> bool:
    if dt is None:
        return True
    if start_dt and dt < start_dt:
        return False
    if end_dt and dt > end_dt:
        return False
    return True


def _to_str(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def _split_tokens(raw: str) -> list[str]:
    return [x for x in re.split(r"[\s,/|]+", (raw or "").strip()) if x]


def _top3(counter: dict[str, int]) -> str:
    if not counter:
        return "No"
    items = sorted(counter.items(), key=lambda x: x[1], reverse=True)
    total = sum(v for _, v in items)
    if total <= 0:
        return "No"
    top = items[:3]
    body = ", ".join(f"{k}({v},{v/total*100:.2f}%)" for k, v in top)
    return f"Top3={body}; total={total}"


def _hex_to_int(value: str) -> int | None:
    s = (value or "").strip().lower()
    if not s:
        return None
    if s.startswith("0x"):
        s = s[2:]
    s = re.sub(r"[^0-9a-f]", "", s)
    if not s:
        return None
    try:
        return int(s, 16)
    except ValueError:
        return None


def _int_to_bin_grouped(value: int | None) -> str:
    if value is None:
        return ""
    bits = bin(value)[2:].zfill(32)
    return "0b " + "  ".join(bits[i : i + 4] for i in range(0, len(bits), 4))


def _decode_set_bits(value: int | None) -> list[int]:
    if value is None:
        return []
    return [b for b in range(31, -1, -1) if (value >> b) & 1]


def _r13_module_from_bit_name(bit_name: str) -> str:
    n = (bit_name or "").upper()
    if "MD_" in n or "MD1_" in n:
        return "MD"
    if "CONN_" in n:
        return "CONN"
    if "SCP_" in n:
        return "SCP"
    if "SSPM_" in n:
        return "SSPM"
    if "AUDIO_DSP" in n:
        return "AUDIO_DSP"
    if "MM_" in n:
        return "MM"
    if "DVFS" in n:
        return "DVFS"
    if "DDR" in n or "DRAM" in n:
        return "DDR"
    if "PWRAP" in n:
        return "PMIC"
    if "SRCCLKENI" in n or "APSRC" in n or "CSYSPWRUPREQ" in n:
        return "AP"
    if "SUBSYS_IDLE" in n:
        return "SUBSYS"
    return "OTHER"


def _build_r13_module_count(r13_bit_count: dict[str, int]) -> dict[str, int]:
    module_count: dict[str, int] = {}
    for bit_name, cnt in (r13_bit_count or {}).items():
        module = _r13_module_from_bit_name(bit_name)
        module_count[module] = module_count.get(module, 0) + cnt
    return module_count


def _load_lines_from_directory(directory: str) -> tuple[list[str], int]:
    merged_files = []
    kernel_files = []
    sys_files = []
    for root, _, names in os.walk(directory):
        for name in names:
            path = os.path.join(root, name)
            mtime = os.path.getmtime(path)
            if "linli_666" in name:
                merged_files.append((mtime, path))
            elif name.startswith("kernel_log_"):
                kernel_files.append((mtime, path))
            elif name.startswith("sys_log_"):
                sys_files.append((mtime, path))
    # If merged kernel logs are present, do not mix with raw kernel_log_* to avoid duplicated events.
    files = list(merged_files if merged_files else kernel_files) + list(sys_files)
    if not files:
        raise ValueError("未找到可用日志（kernel_log_* / sys_log_* / *linli_666*）")
    files.sort(key=lambda x: x[0])
    base_year = _extract_year_from_filename(files[0][1])
    joined = []
    for _, path in files:
        joined.append(_read_text(path))
    return "\n".join(joined).splitlines(), base_year


def _build_segments(screen_off: list[tuple[datetime, str]], screen_on: list[tuple[datetime, str]]) -> list[dict]:
    # Deduplicate exact duplicated screen state events (common when logs are merged/copied).
    off_sorted = sorted(set(screen_off), key=lambda x: x[0])
    on_sorted = sorted(set(screen_on), key=lambda x: x[0])
    segments = []
    off_idx = 0
    last_off = None
    for on_dt, on_raw in on_sorted:
        while off_idx < len(off_sorted) and off_sorted[off_idx][0] <= on_dt:
            last_off = off_sorted[off_idx]
            off_idx += 1
        if not last_off:
            continue
        off_dt, off_raw = last_off
        if on_dt <= off_dt:
            continue
        segments.append(
            {
                "start_off": off_dt,
                "end_on": on_dt,
                "duration_s": int((on_dt - off_dt).total_seconds()),
                "off_raw": off_raw,
                "on_raw": on_raw,
            }
        )
    # Merge near-duplicate segments generated from repeated screen-on lines:
    # same screen-off start, and screen-on end differs only by a few seconds.
    merged_segments = []
    for seg in segments:
        if not merged_segments:
            merged_segments.append(seg)
            continue
        prev = merged_segments[-1]
        same_start = seg["start_off"] == prev["start_off"]
        near_end = abs(int((seg["end_on"] - prev["end_on"]).total_seconds())) <= 2
        if same_start and near_end:
            if seg["end_on"] > prev["end_on"]:
                prev["end_on"] = seg["end_on"]
                prev["duration_s"] = int((prev["end_on"] - prev["start_off"]).total_seconds())
                prev["on_raw"] = seg["on_raw"]
            continue
        merged_segments.append(seg)
    return merged_segments


def _analyze_lines(lines: list[str], start_time: str | None, end_time: str | None, base_year: int) -> dict:
    start_dt = _parse_time_literal(start_time, base_year) if start_time else None
    end_dt = _parse_time_literal(end_time, base_year) if end_time else None

    wakeup_info = []
    suspend_evidence = {"suspend_entry": [], "pending_wakeup_sources": [], "aborting_suspend": [], "active_wakeup_source": [], "suspend_failed": [], "power_button": []}
    lpm_raw = []
    ccif_count: dict[str, int] = {}
    source_count: dict[str, int] = {}
    source_pct: dict[str, list[float]] = {}
    r12_bit_count: dict[str, int] = {}
    r13_bit_count: dict[str, int] = {}
    debug_r13_bit_count: dict[str, int] = {}
    debug_r13_module_count: dict[str, int] = {}
    debug_flag_total = 0
    debug_flag_non_0f = 0
    pct_values: list[float] = []
    screen_off_hits: list[tuple[datetime, str]] = []
    screen_on_hits: list[tuple[datetime, str]] = []

    for idx, line in enumerate(lines, 1):
        lower = line.lower()
        dt = _line_dt(line, base_year)
        if not _in_window(dt, start_dt, end_dt):
            continue

        if "pm: suspend entry" in lower:
            suspend_evidence["suspend_entry"].append((idx, line[:400]))
        if "pending wakeup sources" in lower:
            suspend_evidence["pending_wakeup_sources"].append((idx, line[:400]))
        if "aborting suspend" in lower or "abort suspend" in lower:
            suspend_evidence["aborting_suspend"].append((idx, line[:400]))
        if "active wakeup source" in lower:
            suspend_evidence["active_wakeup_source"].append((idx, line[:400]))
        if "suspend" in lower and ("fail" in lower or "-ebusy" in lower):
            suspend_evidence["suspend_failed"].append((idx, line[:400]))

        has_power_key = any(key in lower for key in POWER_KEY_KEYS)
        if has_power_key and re.match(r"^\s*\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", line):
            suspend_evidence["power_button"].append((idx, line[:400]))

        if any(k in lower for k in SCREEN_OFF_KEYS) or ("tc_screen_notifier_callback" in lower and "screen off" in lower):
            if dt:
                screen_off_hits.append((dt, line[:300]))
        if any(k in lower for k in SCREEN_ON_KEYS) or ("tc_screen_notifier_callback" in lower and "screen on" in lower):
            if dt:
                screen_on_hits.append((dt, line[:300]))

        wakeup_m = re.search(r"suspend wake up by\s+(.*?)(?:,|\.|$)", line, flags=re.IGNORECASE)
        if wakeup_m:
            wakeup_source = wakeup_m.group(1).strip()
            pct_m = re.search(r"26m_off_pct\s*=\s*([0-9.]+)", line, flags=re.IGNORECASE)
            r12_m = re.search(r"r12\s*=\s*([0-9a-fx]+)", line, flags=re.IGNORECASE)
            r13_m = re.search(r"r13\s*=\s*([0-9a-fx]+)", line, flags=re.IGNORECASE)
            debug_m = re.search(r"debug_flag\s*[:=]\s*([0-9a-fx]+)", line, flags=re.IGNORECASE)
            pct_raw = pct_m.group(1) if pct_m else ""
            r12_raw = r12_m.group(1) if r12_m else ""
            r13_raw = r13_m.group(1) if r13_m else ""
            debug_raw = debug_m.group(1) if debug_m else ""
            r12_int = _hex_to_int(r12_raw)
            r13_int = _hex_to_int(r13_raw)
            debug_int = _hex_to_int(debug_raw)
            r12_bits = _decode_set_bits(r12_int)
            r13_bits = _decode_set_bits(r13_int)
            r12_bit_names = [R12_BIT_DEFINITIONS.get(bit, f"R12_BIT{bit}") for bit in r12_bits]
            r13_bit_names = [R13_BIT_DEFINITIONS.get(bit, f"R13_BIT{bit}") for bit in r13_bits]

            for name in r12_bit_names:
                r12_bit_count[name] = r12_bit_count.get(name, 0) + 1
            for name in r13_bit_names:
                r13_bit_count[name] = r13_bit_count.get(name, 0) + 1

            debug_non_0f = False
            if debug_int is not None:
                debug_flag_total += 1
                debug_non_0f = debug_int != 0xF
                if debug_non_0f:
                    debug_flag_non_0f += 1
                    for name in r13_bit_names:
                        debug_r13_bit_count[name] = debug_r13_bit_count.get(name, 0) + 1
                        module = _r13_module_from_bit_name(name)
                        debug_r13_module_count[module] = debug_r13_module_count.get(module, 0) + 1

            pct_float = None
            if pct_raw:
                try:
                    pct_float = float(pct_raw)
                    pct_values.append(pct_float)
                except ValueError:
                    pct_float = None
            wakeup_info.append(
                {
                    "line": idx,
                    "time": _to_str(dt),
                    "wakeup_source": wakeup_source,
                    "r12": r12_raw,
                    "r12_bin": _int_to_bin_grouped(r12_int),
                    "r12_bits": r12_bit_names,
                    "r13": r13_raw,
                    "r13_bin": _int_to_bin_grouped(r13_int),
                    "r13_bits": r13_bit_names,
                    "debug_flag": debug_raw,
                    "debug_flag_non_0f": debug_non_0f,
                    "pct": pct_raw,
                    "raw_line": line[:800],
                }
            )
            for token in _split_tokens(wakeup_source):
                source_count[token] = source_count.get(token, 0) + 1
                if pct_float is not None:
                    source_pct.setdefault(token, []).append(pct_float)

        lpm_m = re.search(r"System LPM is blocked by\s+(.*)$", line, flags=re.IGNORECASE)
        if lpm_m:
            module_raw = lpm_m.group(1).strip()
            lpm_raw.append({"line": idx, "time": _to_str(dt), "blocked_module": module_raw, "raw_line": line[:800]})

        ccif_m = re.search(r"CCIF_MD wakeup source:\([^)]+\)\([^)]+\)\s*(.*)", line, flags=re.IGNORECASE)
        if ccif_m:
            src = ccif_m.group(1).strip()
            if src:
                ccif_count[src] = ccif_count.get(src, 0) + 1

    wakeup_count = len(wakeup_info)
    wakeup_dt = sorted([_parse_time_literal(w.get("time"), base_year) for w in wakeup_info if w.get("time")])
    wakeup_dt = [x for x in wakeup_dt if x is not None]
    duration_hours = None
    if len(wakeup_dt) >= 2:
        delta_s = (wakeup_dt[-1] - wakeup_dt[0]).total_seconds()
        if delta_s > 0:
            duration_hours = delta_s / 3600.0

    frequent_wakeup = "No"
    if wakeup_count > 0:
        if duration_hours and duration_hours >= 0.25:
            if wakeup_count >= 20 and (wakeup_count / duration_hours) >= 10:
                frequent_wakeup = "Yes"
        elif wakeup_count >= 50:
            frequent_wakeup = "Yes"

    has_suspend_entry = len(suspend_evidence["suspend_entry"]) > 0
    has_suspend_wakeup_by = wakeup_count > 0
    entered_suspend_flow = has_suspend_entry and has_suspend_wakeup_by
    suspend_fail_exists = bool(suspend_evidence["aborting_suspend"] or suspend_evidence["active_wakeup_source"] or suspend_evidence["pending_wakeup_sources"] or suspend_evidence["suspend_failed"])
    # 仅在同时看到 "PM: suspend entry" 与 "suspend wake up by" 时，
    # 才认为日志具备进入 suspend 流程的完整证据，再进一步判断是否 suspend fail。
    ap_suspend_failed = "Yes" if (entered_suspend_flow and suspend_fail_exists and wakeup_count == 0) else "No"

    lpm_count: dict[str, int] = {}
    for item in lpm_raw:
        for token in _split_tokens(item.get("blocked_module", "")):
            lpm_count[token] = lpm_count.get(token, 0) + 1
    lpm_anomaly = "No"
    lpm_reason = "No"
    if lpm_raw:
        lpm_anomaly = "Yes"
        lpm_reason = f"Top3={_top3(lpm_count).replace('Top3=', '')}" if lpm_count else "System LPM is blocked by"
    elif pct_values:
        zero_samples = [p for p in pct_values if p == 0.0]
        if len(zero_samples) / len(pct_values) > 0.5:
            lpm_anomaly = "Yes"
            lpm_reason = f"26m_off_pct=0占比{len(zero_samples)}/{len(pct_values)}"

    wakeup_tokens = list(source_count.keys())
    has_power_kw = any(("pwr" in t.lower()) or ("key" in t.lower()) or ("kp" in t.lower()) for t in wakeup_tokens)
    has_notification_kw = any(any(k in t.lower() for k in NOTIFICATION_KEYS) for t in wakeup_tokens)
    has_power_evidence = len(suspend_evidence["power_button"]) > 0
    screen_wakeup = "Yes" if (has_power_evidence or has_power_kw or has_notification_kw) else "No"
    if screen_wakeup == "No":
        screen_wakeup_type = "No"
        screen_wakeup_detail = "No"
    elif has_power_evidence or has_power_kw:
        screen_wakeup_type = "power_key"
        screen_wakeup_detail = f"POWER_BUTTON evidence count={len(suspend_evidence['power_button'])}" if has_power_evidence else _top3(source_count)
    elif has_notification_kw:
        screen_wakeup_type = "notification"
        screen_wakeup_detail = _top3(source_count)
    else:
        screen_wakeup_type = "unknown"
        screen_wakeup_detail = _top3(source_count)

    frequent_reason = None
    if frequent_wakeup == "Yes" and source_count:
        top_items = sorted(source_count.items(), key=lambda x: x[1], reverse=True)[:3]
        frequent_reason = {"top3": [{"name": k, "count": v, "ratio": (v / wakeup_count) if wakeup_count else 0.0} for k, v in top_items], "total": wakeup_count}

    pct_stats = None
    if pct_values:
        pct_stats = {
            "avg": round(sum(pct_values) / len(pct_values), 4),
            "min": round(min(pct_values), 4),
            "max": round(max(pct_values), 4),
            "min_count": pct_values.count(min(pct_values)),
            "max_count": pct_values.count(max(pct_values)),
            "samples": len(pct_values),
        }

    r13_module_count = _build_r13_module_count(r13_bit_count)

    segments = _build_segments(screen_off_hits, screen_on_hits)
    derived_start_time = None
    derived_end_time = None
    if segments:
        derived_start_time = _to_str(segments[0]["start_off"])
        derived_end_time = _to_str(segments[-1]["end_on"])

    seg_stats = []
    for seg in segments:
        sdt = seg["start_off"]
        edt = seg["end_on"]
        seg_wakeup = [w for w in wakeup_info if (lambda d: d and sdt <= d <= edt)(_parse_time_literal(w.get("time"), base_year))]
        seg_lpm = [x for x in lpm_raw if (lambda d: d and sdt <= d <= edt)(_parse_time_literal(x.get("time"), base_year))]
        seg_power = [x for x in suspend_evidence["power_button"] if (lambda d: d and sdt <= d <= edt)(_line_dt(x[1], base_year))]
        seg_fail = [x for x in suspend_evidence["suspend_failed"] if (lambda d: d and sdt <= d <= edt)(_line_dt(x[1], base_year))]
        seg_stats.append(
            {
                "start_off": _to_str(sdt),
                "end_on": _to_str(edt),
                "duration_s": seg["duration_s"],
                "power_button_evidence_count": len(seg_power),
                "AP_suspend_failed": "Yes" if (len(seg_fail) > 0 and len(seg_wakeup) == 0) else "No",
                "frequent_wakeup": "Yes" if len(seg_wakeup) >= 20 else "No",
                "wakeup_count": len(seg_wakeup),
                "26M_LPM_abnormal": "Yes" if len(seg_lpm) > 0 else "No",
                "26M_LPM_reason": "System LPM is blocked by" if len(seg_lpm) > 0 else "No",
            }
        )

    return {
        "summary": {
            "AP_suspend_failed": ap_suspend_failed,
            "frequent_wakeup": frequent_wakeup,
            "frequent_wakeup_reason": frequent_reason,
            "26M_LPM_abnormal": lpm_anomaly,
            "26M_LPM_reason": lpm_reason,
            "screen_wakeup": screen_wakeup,
            "screen_wakeup_type": screen_wakeup_type,
            "screen_wakeup_detail": screen_wakeup_detail,
            "power_button_evidence_count": len(suspend_evidence["power_button"]),
        },
        "stats": {
            "wakeup_count": wakeup_count,
            "duration_hours": duration_hours,
            "wakeup_sources": {
                "count": source_count,
                "avg_26m_off_pct": {k: round(sum(v) / len(v), 4) for k, v in source_pct.items() if v},
            },
            "pct_stats": pct_stats,
            "ccif_md_wakeup_source": ccif_count,
            "system_lpm_blocked": {"count": lpm_count, "raw": lpm_raw},
            "r12_bits": {"count": r12_bit_count},
            "r13_bits": {"count": r13_bit_count},
            "r13_modules": {"count": r13_module_count},
            "debug_flag": {
                "total": debug_flag_total,
                "non_0f": debug_flag_non_0f,
                "non_0f_ratio": (debug_flag_non_0f / debug_flag_total) if debug_flag_total else 0.0,
                "r13_bits_when_non_0f": debug_r13_bit_count,
                "r13_modules_when_non_0f": debug_r13_module_count,
            },
            "screen_segments": seg_stats,
        },
        "evidence": {"suspend_evidence": suspend_evidence, "wakeup_info": wakeup_info},
        "meta": {
            "base_year": base_year,
            # Prefer actual analyzed screen segment boundaries for downstream stability.
            "start_time": derived_start_time if derived_start_time else start_time,
            "end_time": derived_end_time if derived_end_time else end_time,
        },
    }


def _print_text_report(result: dict) -> None:
    summary = result.get("summary", {})
    stats = result.get("stats", {})
    wakeup_sources = (stats.get("wakeup_sources") or {}).get("count") or {}
    lpm_count = ((stats.get("system_lpm_blocked") or {}).get("count")) or {}
    r12_count = ((stats.get("r12_bits") or {}).get("count")) or {}
    r13_count = ((stats.get("r13_bits") or {}).get("count")) or {}
    r13_modules = ((stats.get("r13_modules") or {}).get("count")) or {}
    debug_stats = stats.get("debug_flag") or {}
    debug_total = int(debug_stats.get("total") or 0)
    debug_non_0f = int(debug_stats.get("non_0f") or 0)
    debug_ratio = float(debug_stats.get("non_0f_ratio") or 0.0)
    debug_r13_bits = debug_stats.get("r13_bits_when_non_0f") or {}
    debug_r13_modules = debug_stats.get("r13_modules_when_non_0f") or {}

    print("===== 详细唤醒信息 =====")
    print("-" * 150)
    print("开始时间                  结束时间                  屏幕  时长(s)    电源键    休眠状态     频繁唤醒      26M/LPM异常     26M/LPM异常原因")
    print("-" * 150)
    segments = stats.get("screen_segments") or []
    if not segments:
        print("（未在当前时间窗解析到 灭屏->亮屏 片段）")
    else:
        for seg in segments:
            start_s = (seg.get("start_off") or "").ljust(24)
            end_s = (seg.get("end_on") or "").ljust(24)
            power_key = "Yes" if (seg.get("power_button_evidence_count") or 0) > 0 else "No"
            sleep_ok = "No" if seg.get("AP_suspend_failed") == "Yes" else "Yes"
            print(
                f"{start_s}  {end_s}  OFF  {str(seg.get('duration_s', 0)).rjust(7)}    "
                f"{power_key.ljust(8)} {sleep_ok.ljust(10)}  "
                f"{str(seg.get('frequent_wakeup', 'No')).ljust(10)}  "
                f"{str(seg.get('26M_LPM_abnormal', 'No')).ljust(12)}  {seg.get('26M_LPM_reason', 'No')}"
            )
    print("")

    print("=== 结构化分析摘要(供下游SKILL输入) ===")
    print("[META]")
    print(f"analysis_base_year={result.get('meta', {}).get('base_year', '')}")
    print(f"analysis_start={result.get('meta', {}).get('start_time') or ''}")
    print(f"analysis_end={result.get('meta', {}).get('end_time') or ''}")
    dh = stats.get("duration_hours")
    print(f"analysis_duration_h={'' if dh is None else int(round(dh))}")
    print("")

    print("[THRESHOLD]")
    print("standby_26m_off_pct_threshold=70")
    print("hardware_discharge_abnormal_threshold_ma=3000")
    print("")

    print("[SUMMARY]")
    print(f"AP_suspend_failed={summary.get('AP_suspend_failed', 'No')}")
    print(f"frequent_wakeup={summary.get('frequent_wakeup', 'No')}")
    if summary.get("frequent_wakeup") == "Yes" and summary.get("frequent_wakeup_reason"):
        top3 = summary.get("frequent_wakeup_reason", {}).get("top3") or []
        total = summary.get("frequent_wakeup_reason", {}).get("total") or 0
        if top3 and total:
            top_s = ", ".join([f"{x.get('name')}({x.get('count')},{x.get('ratio', 0.0) * 100:.2f}%)" for x in top3])
            print(f"frequent_wakeup_reason=Top3={top_s}; total={total}")
        else:
            print("frequent_wakeup_reason=No")
    else:
        print("frequent_wakeup_reason=No")
    print(f"26M_LPM_abnormal={summary.get('26M_LPM_abnormal', 'No')}")
    print(
        f"26M_LPM_reason={summary.get('26M_LPM_reason', 'No') if summary.get('26M_LPM_abnormal') == 'Yes' else 'No'}"
    )
    print(f"screen_wakeup={summary.get('screen_wakeup', 'No')}")
    print(f"screen_wakeup_type={summary.get('screen_wakeup_type', 'No')}")
    print(f"screen_wakeup_detail={summary.get('screen_wakeup_detail', 'No')}")
    print(f"power_button_evidence_count={summary.get('power_button_evidence_count', 0)}")
    print("")

    print("[STATS]")
    print(f"wakeup_count={stats.get('wakeup_count', 0)}")
    pct_stats = stats.get("pct_stats") or {}
    pct_avg = pct_stats.get("avg")
    print(f"26M_off_pct_avg={'' if pct_avg is None else f'{float(pct_avg):.2f}%'}")
    print(f"top_wakeup_sources={_top3(wakeup_sources)}")
    print(f"ccif_md_top={_top3(stats.get('ccif_md_wakeup_source') or {})}")
    print(f"system_lpm_blocked_top={_top3(lpm_count)}")
    print(f"r12_bits_top={_top3(r12_count)}")
    print(f"r13_bits_top={_top3(r13_count)}")
    print(f"r13_modules_top={_top3(r13_modules)}")
    print(f"debug_flag_non_0f={debug_non_0f}/{debug_total}({debug_ratio * 100:.2f}%)")
    print(f"debug_non_0f_r13_bits_top={_top3(debug_r13_bits)}")
    print(f"debug_non_0f_r13_modules_top={_top3(debug_r13_modules)}")
    print("")


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="查询并统计 kernel standby 唤醒源信息（text/json）")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("-d", "--directory", metavar="DIR", help="日志目录（支持 kernel_log_* / sys_log_* / *linli_666*）")
    src.add_argument("--file", dest="file_path", metavar="FILE", help="单个日志文件路径")
    src.add_argument("--stdin", action="store_true", help="从标准输入读取日志内容")
    p.add_argument("-t", "--time", nargs="*", metavar=("START", "END"), help="时间窗，格式 YYYY-MM-DD HH:MM:SS；可只给 START 或仅给 END")
    p.add_argument("--format", choices=("text", "json"), default="text", help="输出格式，默认 text")
    p.add_argument("--field", action="append", dest="fields", choices=WAKEUP_FIELDS, metavar="FIELD", help="仅在 json 模式下生效，可重复")
    return p


def _parse_time_args(time_args: list[str] | None) -> tuple[str | None, str | None]:
    if not time_args:
        return None, None
    if len(time_args) == 1:
        return time_args[0], None
    start = time_args[0] or None
    end = time_args[1] if len(time_args) >= 2 else None
    return start, end


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    args = _build_arg_parser().parse_args(argv)
    start_time, end_time = _parse_time_args(args.time)

    try:
        if args.stdin:
            lines = sys.stdin.read().splitlines()
            base_year = 2026
        elif args.file_path:
            if not os.path.exists(args.file_path):
                print(f"错误：文件不存在: {args.file_path}")
                return 1
            base_year = _extract_year_from_filename(args.file_path)
            lines = _read_text(args.file_path).splitlines()
        else:
            if not os.path.exists(args.directory):
                print(f"错误：目录不存在: {args.directory}")
                return 1
            lines, base_year = _load_lines_from_directory(args.directory)
    except Exception as exc:
        print(f"读取日志失败: {exc}")
        return 1

    result = _analyze_lines(lines, start_time, end_time, base_year)

    if args.format == "json":
        if args.fields:
            output = {name: (result.get("summary") or {}).get(name) for name in args.fields}
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    _print_text_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())