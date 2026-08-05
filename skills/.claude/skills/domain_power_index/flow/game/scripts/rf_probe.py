"""步骤 5：网络 / RF 独立排查。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

_EVIDENCE_CAP = 40
WEAK_RSRP_DBM = -100

_RF_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"netstats_wifi_sample:", re.I), "wifi_traffic"),
    (re.compile(r"WIFI_STATE_CHANGED|WifiController:\s*EnabledState", re.I), "wifi_on"),
    (re.compile(r"WifiController:\s*DisabledState", re.I), "wifi_off"),
    (re.compile(r"transportType=WLAN", re.I), "wifi_transport"),
    (re.compile(r"getRilDataRadioTechnology=(\d+)\(([^)]+)\)"), "cell_rat"),
    (re.compile(r"mDataRegState=(\d+)\(([^)]+)\)"), "data_reg"),
    (re.compile(r"RSRP[=\s:]+(-?\d+)", re.I), "rsrp"),
    (re.compile(r"RSRQ[=\s:]+(-?\d+)", re.I), "rsrq"),
    (re.compile(r"RSSI[=\s:]+(-?\d+)", re.I), "rssi"),
    (re.compile(r"WifiScanner|WifiConnectivityManager.*scan", re.I), "wifi_scan"),
    (re.compile(r"BluetoothLeScanner", re.I), "bt_scan"),
    (re.compile(r"disconnect|DISCONNECTED", re.I), "disconnect"),
]


def _evidence(path: Path, line_no: int, line: str) -> str:
    return f"{path.name}:{line_no}: {line.rstrip()[:240]}"


def _window_label(
    ts: datetime | None,
    game_start: datetime | None,
    game_end: datetime | None,
) -> str:
    if not ts or not game_start:
        return "unknown"
    if ts < game_start:
        return "T_pre"
    if game_end and ts <= game_end:
        return "T_game"
    if game_end and ts > game_end:
        return "T_post"
    return "T_game"


def probe_rf_stats(
    logs: dict[str, list[Path]],
    game_start: datetime | None,
    game_end: datetime | None,
    pre_seconds: int,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[..., Any],
    window_for: Callable[..., str | None] | None = None,
) -> dict[str, Any]:
    """T_pre~T_game 内统计 WiFi / 蜂窝 / 信号线索。"""
    scan_start = game_start
    if game_start:
        scan_start = game_start - timedelta(seconds=pre_seconds)

    files = (
        logs.get("radio_log", [])
        + logs.get("events_log", [])
        + logs.get("main_log", [])
        + logs.get("sys_log", [])
    )

    hits: list[dict[str, Any]] = []
    wifi_traffic_t_game = 0
    wifi_scan_t_game = 0
    disconnect_t_game = 0
    rsrp_values: list[int] = []
    rssi_values: list[int] = []
    cell_rats: list[str] = []
    wifi_on = False
    wifi_transport = False

    for path in files:
        for line_no, line in iter_lines(path):
            _, ts = extract_ts(line)
            if scan_start and ts and ts < scan_start:
                continue
            if game_end and ts and ts > game_end:
                continue
            window = (
                window_for(ts, game_start, game_end, pre_seconds, 0)
                if window_for and game_start
                else _window_label(ts, game_start, game_end)
            )
            for pat, kind in _RF_PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                item: dict[str, Any] = {
                    "kind": kind,
                    "window": window,
                    "time": str(ts) if ts else "",
                    "raw_evidence": _evidence(path, line_no, line),
                }
                if kind == "rsrp":
                    val = int(m.group(1))
                    item["rsrp_dbm"] = val
                    if window == "T_game":
                        rsrp_values.append(val)
                elif kind == "rssi":
                    val = int(m.group(1))
                    item["rssi_dbm"] = val
                    if window == "T_game":
                        rssi_values.append(val)
                elif kind == "cell_rat":
                    item["rat_code"] = int(m.group(1))
                    item["rat_name"] = m.group(2)
                    if window == "T_game":
                        cell_rats.append(m.group(2))
                elif kind == "data_reg":
                    item["reg_state"] = m.group(2)
                elif kind == "wifi_traffic" and window == "T_game":
                    wifi_traffic_t_game += 1
                elif kind == "wifi_scan" and window == "T_game":
                    wifi_scan_t_game += 1
                elif kind == "disconnect" and window == "T_game":
                    disconnect_t_game += 1
                elif kind == "wifi_on":
                    wifi_on = True
                elif kind == "wifi_transport":
                    wifi_transport = True
                hits.append(item)
                break

    game_hits = [h for h in hits if h.get("window") == "T_game"]
    network_type = "unknown"
    if wifi_traffic_t_game > 0 or wifi_on or wifi_transport:
        network_type = "wifi"
    elif cell_rats:
        network_type = "cellular"
    elif any(h["kind"] == "cell_rat" for h in game_hits):
        network_type = "cellular"

    level = "unknown"
    summary_parts: list[str] = []
    notes: list[str] = []

    if not files:
        notes.append("radio/events/main/sys 均无可用日志")
    elif not game_hits:
        notes.append("T_game 内未匹配到 RF 相关日志行")
    else:
        if network_type == "wifi":
            summary_parts.append(f"WiFi 活跃（netstats 采样 {wifi_traffic_t_game} 条）")
            level = "normal"
        elif network_type == "cellular":
            rat_top = max(set(cell_rats), key=cell_rats.count) if cell_rats else "unknown"
            summary_parts.append(f"蜂窝 RAT={rat_top}")
            level = "normal"
        if rsrp_values:
            rsrp_min = min(rsrp_values)
            summary_parts.append(f"RSRP {rsrp_min}~{max(rsrp_values)} dBm")
            if rsrp_min < WEAK_RSRP_DBM:
                level = "suspect"
                notes.append(f"弱信号 RSRP<{WEAK_RSRP_DBM} dBm")
        if wifi_scan_t_game >= 3:
            level = "suspect" if level == "normal" else level
            notes.append(f"T_game WiFi 扫描相关日志 {wifi_scan_t_game} 条")
        if disconnect_t_game >= 2:
            level = "suspect" if level != "abnormal" else level
            notes.append(f"T_game 断连相关日志 {disconnect_t_game} 条")

    evidence = [h["raw_evidence"] for h in game_hits[:_EVIDENCE_CAP]]

    return {
        "source": "radio_events_main_sys",
        "coverage": "ok" if game_hits else ("partial" if hits else "missing"),
        "network_type": network_type,
        "level": level,
        "summary": "；".join(summary_parts) if summary_parts else "",
        "game_window": {
            "wifi_traffic_samples": wifi_traffic_t_game,
            "wifi_scan_events": wifi_scan_t_game,
            "disconnect_events": disconnect_t_game,
            "rsrp_min": min(rsrp_values) if rsrp_values else None,
            "rsrp_max": max(rsrp_values) if rsrp_values else None,
            "rssi_min": min(rssi_values) if rssi_values else None,
            "rssi_max": max(rssi_values) if rssi_values else None,
            "cell_rat_samples": list(dict.fromkeys(cell_rats))[:10],
            "hit_count": len(game_hits),
        },
        "raw_evidence": evidence,
        "notes": notes,
    }
