"""游戏场景网络四步排查（与 game_network/SKILL.md §分析流程对齐）。"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from skill_references import load_analysis_standards, threshold

_WIFI_RSSI_RES = [
    # 优先 Transsion 专用埋点
    re.compile(
        r"TranWifiSmartAssistantController:.*?rssi\s*:\s*(?P<rssi>-?\d+)",
        re.IGNORECASE,
    ),
    re.compile(r"====>>rssi\s*:\s*(?P<rssi>-?\d+)", re.IGNORECASE),
    # main log 通用 rssi 搜索（避免匹配到 WIFI_FEATURE_* 等无数值行）
    re.compile(r"(?<![A-Za-z_])rssi\s*:\s*(?P<rssi>-?\d+)", re.IGNORECASE),
    re.compile(r"(?<![A-Za-z_])rssi\s*=\s*(?P<rssi>-?\d+)", re.IGNORECASE),
]
_WIFI_RSSI_DBM_MIN = -100
_WIFI_RSSI_DBM_MAX = 0

# TranWifiSmartAssistantController 成组埋点（每 ~3s 一批，字段分行）
_TRAN_WIFI_TAG = "TranWifiSmartAssistantController"
_TRAN_WIFI_MONITOR_RE = re.compile(r"start current network monitor", re.IGNORECASE)
_TRAN_WIFI_STOP_RE = re.compile(r"\bstop monitor\b", re.IGNORECASE)
_TRAN_WIFI_TOP_APP_RE = re.compile(
    r"top app:\s*(?P<pkg>\S+)\s+in white list:\s*(?P<wl>true|false)",
    re.IGNORECASE,
)
_TRAN_WIFI_LANDSCAPE_RE = re.compile(
    r"Landscape screen:\s*(?P<v>true|false)",
    re.IGNORECASE,
)
_TRAN_WIFI_SCORE_RE = re.compile(
    r"userIgnored\s*:\s*(?P<ignored>true|false)"
    r".*?isScoredCurrentNetwork\s*:\s*(?P<scored>true|false)",
    re.IGNORECASE,
)
_TRAN_WIFI_SSID_RE = re.compile(
    r"mCurrentNetwork\s*:\s*(?P<nid>-?\d+)\s+SSID\s*:\s*\"(?P<ssid>[^\"]*)\"",
    re.IGNORECASE,
)
_TRAN_WIFI_NO_CAND_RE = re.compile(
    r"mNoCandidateCount\s*:\s*(?P<cnt>-?\d+)",
    re.IGNORECASE,
)


def _match_wifi_rssi_dbm(line: str) -> int | None:
    """从 main 行提取 WiFi RSSI(dBm)；无有效数值返回 None。"""
    for cre in _WIFI_RSSI_RES:
        m = cre.search(line)
        if not m:
            continue
        try:
            val = int(m.group("rssi"))
        except (TypeError, ValueError):
            continue
        if _WIFI_RSSI_DBM_MIN <= val <= _WIFI_RSSI_DBM_MAX:
            return val
    return None


def _parse_tran_wifi_assistant_fields(line: str) -> dict[str, Any]:
    """解析 TranWifiSmartAssistantController 单行字段（可部分命中）。"""
    if _TRAN_WIFI_TAG not in line:
        return {}
    out: dict[str, Any] = {}
    if _TRAN_WIFI_MONITOR_RE.search(line):
        out["monitor_start"] = True
    if _TRAN_WIFI_STOP_RE.search(line):
        out["monitor_stop"] = True
    m = _TRAN_WIFI_TOP_APP_RE.search(line)
    if m:
        out["top_app"] = str(m.group("pkg") or "").strip()
        out["in_whitelist"] = m.group("wl").lower() == "true"
    m = _TRAN_WIFI_LANDSCAPE_RE.search(line)
    if m:
        out["landscape_screen"] = m.group("v").lower() == "true"
    m = _TRAN_WIFI_SCORE_RE.search(line)
    if m:
        out["user_ignored"] = m.group("ignored").lower() == "true"
        out["is_scored_current_network"] = m.group("scored").lower() == "true"
    m = _TRAN_WIFI_SSID_RE.search(line)
    if m:
        try:
            out["network_id"] = int(m.group("nid"))
        except (TypeError, ValueError):
            out["network_id"] = m.group("nid")
        out["ssid"] = str(m.group("ssid") or "").strip()
    m = _TRAN_WIFI_NO_CAND_RE.search(line)
    if m:
        try:
            out["no_candidate_count"] = int(m.group("cnt"))
        except (TypeError, ValueError):
            out["no_candidate_count"] = m.group("cnt")
    return out


def _fmt_rssi_time(dt: datetime) -> str:
    return dt.strftime("%m-%d %H:%M:%S.%f")[:-3]


_NSM_WIFI_RE = re.compile(
    r"NetworkStatusMonitor:\s*updateInterfaceNameMap,\s*wifi:(?P<wifi>[^,]*)\s*,\s*(?P<state>\w+)",
    re.IGNORECASE,
)
_NSM_MOBILE_RE = re.compile(
    r"NetworkStatusMonitor:.*?mobile:(?P<mobile>.*?)\s*$",
    re.IGNORECASE,
)
_RMM_NW_RE = re.compile(r"RmmNwHdlr:.*?(?:NR:|LTE:)", re.IGNORECASE)
_KV_RE = re.compile(r"(?P<key>\w+)\s*=\s*(?P<val>[^,\s]+)")
_CCMNI_RE = re.compile(
    r"ccmni(?P<id>\d+):.*?rx=\((?P<rx0>\d+),(?P<rx1>\d+),(?P<rx2>\d+)\).*?"
    r"tx=\((?P<tx0>\d+),(?P<tx1>\d+),(?P<tx2>\d+)\)",
    re.IGNORECASE,
)


def _ref_dir(from_file: Path) -> Path:
    return from_file.resolve().parent.parent / "references"


def _strip_dt(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_dt(v) for k, v in obj.items() if k != "dt"}
    if isinstance(obj, list):
        return [_strip_dt(x) for x in obj]
    return obj


def _rssi_bucket(rssi: int, thresholds: dict[str, int]) -> str:
    if rssi >= thresholds["excellent"]:
        return "excellent"
    if rssi >= thresholds["good"]:
        return "good"
    if rssi >= thresholds["fair"]:
        return "fair"
    if rssi >= thresholds["poor"]:
        return "poor"
    return "very_poor"


def _parse_rmm_fields(line: str) -> dict[str, Any] | None:
    if not _RMM_NW_RE.search(line):
        return None
    fields: dict[str, Any] = {}
    for m in _KV_RE.finditer(line):
        key = m.group("key").lower()
        val = m.group("val").strip()
        if key in ("rsrp", "rsrq", "sinr", "band", "nr_arfcn", "pscPci".lower()):
            try:
                fields[key] = int(val.lstrip("*"))
            except ValueError:
                fields[key] = val
        elif key in ("long_name", "short_name", "plmn"):
            fields[key] = val
        elif key in ("state", "registred", "registered"):
            fields[key] = val
    if "rsrp" not in fields and "rsrq" not in fields and "sinr" not in fields:
        return None
    return fields


def _pick_last_non_none(items: list[dict[str, Any]], key: str) -> Any:
    for item in reversed(items):
        if not isinstance(item, dict):
            continue
        val = item.get(key)
        if val is not None and val != "":
            return val
    return None


def _step1_wifi_rssi(
    main_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    rssi_thresholds: dict[str, int],
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    """WiFi RSSI + TranWifiSmartAssistantController 伴随字段。

    RSSI：main log 搜索 rssi 数值；T_game 采样稀疏时用开局前最后一次延续成曲线。
    伴随字段：SSID / mCurrentNetwork / userIgnored / isScoredCurrentNetwork /
    mNoCandidateCount / monitor start（同 tag 成组埋点）。
    """
    samples: list[dict[str, Any]] = []
    last_pre: dict[str, Any] | None = None
    assistant_state: dict[str, Any] = {}
    assistant_snapshots: list[dict[str, Any]] = []
    monitor_starts_by_win: dict[str, int] = defaultdict(int)
    monitor_stops_by_win: dict[str, int] = defaultdict(int)
    ssid_counts: dict[str, int] = defaultdict(int)
    policy_events: list[dict[str, Any]] = []
    whitelist_pkgs_t_game: list[str] = []
    landscape_t_game: bool | None = None

    def _snapshot_assistant(ts_raw: str, ts: datetime, win: str | None, path: Path, line_no: int) -> None:
        if win not in ("T_pre", "T_game", "T_post"):
            return
        if not any(
            k in assistant_state
            for k in (
                "ssid",
                "network_id",
                "user_ignored",
                "is_scored_current_network",
                "no_candidate_count",
            )
        ):
            return
        snap = {
            "time": ts_raw,
            "dt": ts,
            "window": win,
            "ssid": assistant_state.get("ssid"),
            "network_id": assistant_state.get("network_id"),
            "user_ignored": assistant_state.get("user_ignored"),
            "is_scored_current_network": assistant_state.get("is_scored_current_network"),
            "no_candidate_count": assistant_state.get("no_candidate_count"),
            "raw_evidence": f"{path.name}:{line_no}",
        }
        # 同一秒内字段陆续补齐：合并末条
        if (
            assistant_snapshots
            and assistant_snapshots[-1].get("window") == win
            and abs((ts - assistant_snapshots[-1]["dt"]).total_seconds()) <= 1.0
        ):
            prev = assistant_snapshots[-1]
            for k, v in snap.items():
                if k in ("dt", "time", "window", "raw_evidence"):
                    continue
                if v is not None and v != "":
                    prev[k] = v
            prev["time"] = ts_raw
            prev["dt"] = ts
            prev["raw_evidence"] = snap["raw_evidence"]
        else:
            assistant_snapshots.append(snap)
        ssid = assistant_state.get("ssid")
        if win == "T_game" and isinstance(ssid, str) and ssid:
            ssid_counts[ssid] += 1

    for path in main_files:
        for line_no, line in iter_lines(path):
            fields = _parse_tran_wifi_assistant_fields(line)
            if fields:
                ts_raw, ts = extract_ts(line)
                if ts:
                    win = window_for(ts, start, end, pre_s, post_s)
                    policy_hit = False
                    if fields.pop("monitor_start", False):
                        if win in ("T_pre", "T_game", "T_post"):
                            monitor_starts_by_win[str(win)] += 1
                        policy_hit = True
                    if fields.pop("monitor_stop", False):
                        if win in ("T_pre", "T_game", "T_post"):
                            monitor_stops_by_win[str(win)] += 1
                        if win == "T_game":
                            policy_events.append(
                                {
                                    "time": ts_raw,
                                    "kind": "stop_monitor",
                                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:220]}",
                                }
                            )
                        policy_hit = True
                    if "top_app" in fields:
                        pkg = str(fields.get("top_app") or "")
                        wl = bool(fields.get("in_whitelist"))
                        if win == "T_game":
                            policy_events.append(
                                {
                                    "time": ts_raw,
                                    "kind": "top_app_whitelist",
                                    "top_app": pkg,
                                    "in_whitelist": wl,
                                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:220]}",
                                }
                            )
                            if wl and pkg and pkg not in whitelist_pkgs_t_game:
                                whitelist_pkgs_t_game.append(pkg)
                        policy_hit = True
                    if "landscape_screen" in fields and win == "T_game":
                        landscape_t_game = bool(fields.get("landscape_screen"))
                        policy_events.append(
                            {
                                "time": ts_raw,
                                "kind": "landscape",
                                "landscape_screen": landscape_t_game,
                                "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:220]}",
                            }
                        )
                        policy_hit = True
                    for k, v in fields.items():
                        if k in ("top_app", "in_whitelist", "landscape_screen"):
                            continue
                        assistant_state[k] = v
                    # 快照仅对网络评分/SSID 字段；策略事件单独记
                    snap_fields = {
                        k: v
                        for k, v in fields.items()
                        if k
                        in (
                            "ssid",
                            "network_id",
                            "user_ignored",
                            "is_scored_current_network",
                            "no_candidate_count",
                        )
                    }
                    if snap_fields:
                        _snapshot_assistant(ts_raw, ts, win, path, line_no)
                    elif policy_hit:
                        pass

            rssi = _match_wifi_rssi_dbm(line)
            if rssi is None:
                continue
            ts_raw, ts = extract_ts(line)
            if not ts:
                continue
            win = window_for(ts, start, end, pre_s, post_s)
            if win not in ("T_pre", "T_game", "T_post"):
                # 仍记录 T_pre 之前最近一次，便于开局延续
                if ts < start:
                    last_pre = {
                        "time": ts_raw,
                        "dt": ts,
                        "rssi_dbm": rssi,
                        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:260]}",
                    }
                continue
            offset_s = round((ts - start).total_seconds(), 1)
            item = {
                "time": ts_raw,
                "dt": ts,
                "t_offset_seconds": offset_s,
                "rssi_dbm": rssi,
                "window": win,
                "quality_bucket": _rssi_bucket(rssi, rssi_thresholds),
                "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:260]}",
            }
            if assistant_state.get("ssid") is not None:
                item["ssid"] = assistant_state.get("ssid")
            if assistant_state.get("network_id") is not None:
                item["network_id"] = assistant_state.get("network_id")
            if assistant_state.get("user_ignored") is not None:
                item["user_ignored"] = assistant_state.get("user_ignored")
            if assistant_state.get("is_scored_current_network") is not None:
                item["is_scored_current_network"] = assistant_state.get(
                    "is_scored_current_network"
                )
            if assistant_state.get("no_candidate_count") is not None:
                item["no_candidate_count"] = assistant_state.get("no_candidate_count")
            samples.append(item)
            if win == "T_pre" or (win == "T_game" and ts <= start):
                last_pre = item
            elif ts < start and (last_pre is None or ts >= last_pre["dt"]):
                last_pre = item

    # 若 T_pre 窗口内没有、但窗口前有 last_pre，保留
    game_samples = [s for s in samples if s.get("window") == "T_game"]
    pre_samples = [s for s in samples if s.get("window") == "T_pre"]
    post_samples = [s for s in samples if s.get("window") == "T_post"]
    if pre_samples:
        last_pre = pre_samples[-1]

    # 曲线/统计：仅 T_game 实测（游戏场景外信号不输出）
    measured_for_curve = list(game_samples)
    curve: list[dict[str, Any]] = []
    for s in measured_for_curve:
        curve.append(
            {
                "time": s["time"],
                "t_offset_seconds": s["t_offset_seconds"],
                "rssi_dbm": s["rssi_dbm"],
                "window": "T_game",
            }
        )
    # 单点复制以便折线渲染（仍属 T_game，不引入局外点）
    if len(curve) == 1:
        curve.append(dict(curve[0]))

    game_vals = [int(s["rssi_dbm"]) for s in game_samples]
    stats_vals = list(game_vals)
    stats_scope = "T_game" if stats_vals else "missing"
    bucket_counts: dict[str, int] = defaultdict(int)
    for s in game_samples:
        bucket_counts[s["quality_bucket"]] += 1
    total = max(len(game_samples), 1 if stats_vals else 0)
    usage_pct = {
        k: round(v / total * 100, 1) for k, v in sorted(bucket_counts.items()) if total
    }

    game_assistant = [s for s in assistant_snapshots if s.get("window") == "T_game"]
    # SSID 等身份字段：优先局内；局内无快照时用开局前最后态（非信号曲线）
    pre_assistant = [s for s in assistant_snapshots if s.get("window") == "T_pre"]
    assistant_pool = game_assistant or pre_assistant
    primary_ssid = None
    if ssid_counts:
        primary_ssid = sorted(ssid_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    elif assistant_pool:
        primary_ssid = _pick_last_non_none(assistant_pool, "ssid")
    ssids_observed = sorted({s for s in ssid_counts.keys() if s}) or (
        [primary_ssid] if primary_ssid else []
    )
    wifi_assistant = {
        "coverage": "ok" if assistant_pool else "missing",
        "ssid": primary_ssid,
        "ssids_observed": ssids_observed,
        "network_id": _pick_last_non_none(assistant_pool, "network_id"),
        "user_ignored": _pick_last_non_none(assistant_pool, "user_ignored"),
        "is_scored_current_network": _pick_last_non_none(
            assistant_pool, "is_scored_current_network"
        ),
        "no_candidate_count": _pick_last_non_none(assistant_pool, "no_candidate_count"),
        "monitor_start_count_t_game": int(monitor_starts_by_win.get("T_game", 0)),
        "monitor_start_count_t_pre": int(monitor_starts_by_win.get("T_pre", 0)),
        "monitor_stop_count_t_game": int(monitor_stops_by_win.get("T_game", 0)),
        "whitelist_top_apps_t_game": whitelist_pkgs_t_game,
        "landscape_screen_t_game": landscape_t_game,
        "snapshot_count_t_game": len(game_assistant),
        "note": "TranWifiSmartAssistantController main log 成组字段（信号曲线仅 T_game）",
        "snapshots": _strip_dt(game_assistant[-12:] if game_assistant else []),
        "policy_events": policy_events[:20],
    }

    sparse_game = len(game_vals) <= 1
    stop_n = int(monitor_stops_by_win.get("T_game", 0))
    wl_pkgs = whitelist_pkgs_t_game
    if sparse_game and stop_n > 0 and wl_pkgs:
        pkg_txt = "、".join(wl_pkgs[:3])
        rssi_gap_reason = "whitelist_stop_monitor"
        rssi_gap_conclusion = (
            f"WiFi 助手对白名单游戏（{pkg_txt}）主动停 monitor，"
            f"故局内无周期性 RSSI 输出（≠断网/信号恒定）"
        )
    elif sparse_game and stop_n > 0:
        rssi_gap_reason = "stop_monitor"
        rssi_gap_conclusion = (
            "WiFi 助手局内 stop monitor，故无周期性 RSSI 输出（≠断网/信号恒定）"
        )
    elif sparse_game:
        rssi_gap_reason = "sparse_unknown"
        rssi_gap_conclusion = "局内 WiFi RSSI 埋点稀疏（未明确命中白名单停 monitor）"
    else:
        rssi_gap_reason = "none"
        rssi_gap_conclusion = None
    wifi_assistant["rssi_gap_reason"] = rssi_gap_reason
    wifi_assistant["rssi_gap_conclusion"] = rssi_gap_conclusion

    return {
        "coverage": "ok" if stats_vals else "missing",
        "sample_count": len(game_samples),
        "pre_sample_count": len(pre_samples),
        "post_sample_count": len(post_samples),
        "curve_sample_count": len(measured_for_curve),
        "stats_scope": stats_scope,
        "rssi_dbm_avg": round(sum(stats_vals) / len(stats_vals), 1) if stats_vals else None,
        "rssi_dbm_min": min(stats_vals) if stats_vals else None,
        "rssi_dbm_max": max(stats_vals) if stats_vals else None,
        "rssi_dbm_avg_t_game": (
            round(sum(game_vals) / len(game_vals), 1) if game_vals else None
        ),
        "rssi_curve": curve,
        "rssi_quality_usage_pct": usage_pct,
        "wifi_assistant": wifi_assistant,
        "carry_forward_from_pre": False,
        "t_game_rssi_sparse": sparse_game,
        "rssi_gap_conclusion": rssi_gap_conclusion,
        "note": (
            f"{rssi_gap_conclusion}；曲线仅输出 T_game 实测点"
            if rssi_gap_conclusion
            else "main log 搜索 rssi + TranWifiSmartAssistantController（仅 T_game）"
        ),
        "samples": game_samples[-20:],
    }


def _step2_wifi_scenario(
    log_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []
    wifi_changes = 0
    mobile_active_events = 0
    dual_iface_events = 0
    wifi_iface_seen = False

    for path in log_files:
        for line_no, line in iter_lines(path):
            if "NetworkStatusMonitor" not in line and "updateInterfaceNameMap" not in line:
                continue
            ts_raw, ts = extract_ts(line)
            if not ts or window_for(ts, start, end, pre_s, post_s) != "T_game":
                continue

            wifi_m = _NSM_WIFI_RE.search(line)
            mobile_m = _NSM_MOBILE_RE.search(line)
            if not wifi_m and not mobile_m:
                continue

            entry: dict[str, Any] = {
                "time": ts_raw,
                "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:280]}",
            }
            wifi_on = False
            mobile_on = False
            if wifi_m:
                wifi_iface = wifi_m.group("wifi").strip()
                state = wifi_m.group("state").strip()
                entry["wifi_interface"] = wifi_iface
                entry["wifi_state"] = state
                entry["wifi_changed"] = state.lower() == "changed"
                wifi_on = bool(wifi_iface)
                if wifi_on:
                    wifi_iface_seen = True
                if entry["wifi_changed"]:
                    wifi_changes += 1
            if mobile_m:
                mobile = mobile_m.group("mobile").strip()
                entry["mobile_interface"] = mobile
                entry["mobile_data_active"] = bool(mobile)
                mobile_on = bool(mobile)
                if mobile_on:
                    mobile_active_events += 1
            entry["dual_iface"] = bool(wifi_on and mobile_on)
            if entry["dual_iface"]:
                dual_iface_events += 1
            events.append(entry)

    return {
        "coverage": "ok" if events else "missing",
        "event_count": len(events),
        "wifi_interface_changes": wifi_changes,
        "wifi_interface_present": wifi_iface_seen,
        "mobile_data_active_events": mobile_active_events,
        "dual_iface_events": dual_iface_events,
        "cellular_data_during_game": mobile_active_events > 0,
        "events": events[:30],
    }


def _judge_dual_channel(
    step1: dict[str, Any],
    step2: dict[str, Any],
    step3: dict[str, Any],
    step4: dict[str, Any],
    *,
    ccmni_bytes_threshold: int = 10240,
) -> dict[str, Any]:
    """判断 T_game 是否 WiFi+蜂窝双通道（同时走业务数据）。"""
    wa = step1.get("wifi_assistant") if isinstance(step1.get("wifi_assistant"), dict) else {}
    wifi_rssi_ok = int(step1.get("sample_count") or 0) > 0 or int(
        step1.get("pre_sample_count") or 0
    ) > 0
    wifi_ssid = bool(wa.get("ssid"))
    wifi_iface = bool(step2.get("wifi_interface_present"))
    wifi_active = bool(wifi_rssi_ok or wifi_ssid or wifi_iface)

    cellular_iface = bool(step2.get("cellular_data_during_game"))
    dual_iface = int(step2.get("dual_iface_events") or 0) > 0
    rx = int(step4.get("primary_rx_bytes_delta") or 0)
    tx = int(step4.get("primary_tx_bytes_delta") or 0)
    cellular_traffic = (rx + tx) >= int(ccmni_bytes_threshold)
    cellular_signal = int(step3.get("sample_count") or 0) > 0

    cellular_data = bool(cellular_iface or cellular_traffic or dual_iface)
    is_dual = bool(wifi_active and cellular_data)

    if is_dual:
        verdict = "yes"
        summary = "WiFi 活跃且检测到蜂窝数据通道（接口或 ccmni 流量）→ 双通道"
    elif wifi_active and cellular_signal and not cellular_data:
        verdict = "no_signal_only"
        summary = "WiFi 活跃；仅有蜂窝信号采样，无蜂窝数传证据 → 非双通道（纯 WiFi）"
    elif wifi_active and not cellular_data:
        verdict = "no"
        summary = "WiFi 活跃，未发现蜂窝数传 → 非双通道"
    elif cellular_data and not wifi_active:
        verdict = "cellular_only"
        summary = "有蜂窝数传、未见 WiFi 活跃 → 非双通道（偏蜂窝）"
    else:
        verdict = "unknown"
        summary = "WiFi/蜂窝证据不足，无法判定双通道"

    evidence: list[str] = []
    if wifi_ssid:
        evidence.append(f"WiFi SSID={wa.get('ssid')}")
    if wifi_rssi_ok:
        evidence.append(
            f"WiFi RSSI samples(game/pre)="
            f"{step1.get('sample_count')}/{step1.get('pre_sample_count')}"
        )
    if wifi_iface:
        evidence.append("NetworkStatusMonitor wifi 接口非空")
    if cellular_iface:
        evidence.append(
            f"NetworkStatusMonitor mobile 活跃 "
            f"events={step2.get('mobile_data_active_events')}"
        )
    if dual_iface:
        evidence.append(f"同条日志 wifi+mobile 并存 events={step2.get('dual_iface_events')}")
    if cellular_traffic:
        evidence.append(
            f"ccmni 流量 rx+tx={rx + tx}B "
            f"iface={step4.get('primary_interface')}"
        )
    elif step4.get("coverage") == "ok":
        evidence.append(f"ccmni 流量增量不足（rx+tx={rx + tx}B < {ccmni_bytes_threshold}B）")
    if cellular_signal and not cellular_data:
        evidence.append(
            f"蜂窝信号采样={step3.get('sample_count')}（不等于数传）"
        )

    return {
        "verdict": verdict,
        "is_dual_channel": is_dual,
        "wifi_active": wifi_active,
        "cellular_data_active": cellular_data,
        "cellular_signal_only": bool(cellular_signal and not cellular_data),
        "dual_iface_events": int(step2.get("dual_iface_events") or 0),
        "ccmni_rx_tx_bytes": rx + tx,
        "ccmni_bytes_threshold": ccmni_bytes_threshold,
        "summary": summary,
        "evidence": evidence,
    }


def _step3_cellular_signal(
    radio_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    bands_seen: list[int] = []
    t0: datetime | None = None

    for path in radio_files:
        for line_no, line in iter_lines(path):
            fields = _parse_rmm_fields(line)
            if not fields:
                continue
            ts_raw, ts = extract_ts(line)
            if not ts or window_for(ts, start, end, pre_s, post_s) != "T_game":
                continue
            if t0 is None:
                t0 = ts
            offset_s = round((ts - t0).total_seconds(), 1) if t0 else 0.0
            band = fields.get("band")
            if isinstance(band, int):
                bands_seen.append(band)
            samples.append(
                {
                    "time": ts_raw,
                    "dt": ts,
                    "t_offset_seconds": offset_s,
                    "rsrp": fields.get("rsrp"),
                    "rsrq": fields.get("rsrq"),
                    "sinr": fields.get("sinr"),
                    "band": band,
                    "operator": fields.get("long_name") or fields.get("short_name"),
                    "plmn": fields.get("plmn"),
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:280]}",
                }
            )

    def _avg(key: str) -> float | None:
        vals = [s[key] for s in samples if isinstance(s.get(key), int)]
        return round(sum(vals) / len(vals), 1) if vals else None

    band_changes: list[dict[str, Any]] = []
    prev_band: int | None = None
    for s in samples:
        band = s.get("band")
        if not isinstance(band, int):
            continue
        if prev_band is not None and band != prev_band:
            band_changes.append({"time": s["time"], "from_band": prev_band, "to_band": band})
        prev_band = band

    return {
        "coverage": "ok" if samples else "missing",
        "sample_count": len(samples),
        "rsrp_avg": _avg("rsrp"),
        "rsrq_avg": _avg("rsrq"),
        "sinr_avg": _avg("sinr"),
        "bands_observed": sorted(set(bands_seen)),
        "band_changed": len(band_changes) > 0,
        "band_changes": band_changes,
        "rsrp_curve": [
            {"time": s["time"], "t_offset_seconds": s["t_offset_seconds"], "rsrp": s.get("rsrp")}
            for s in samples
            if s.get("rsrp") is not None
        ],
        "rsrq_curve": [
            {"time": s["time"], "t_offset_seconds": s["t_offset_seconds"], "rsrq": s.get("rsrq")}
            for s in samples
            if s.get("rsrq") is not None
        ],
        "sinr_curve": [
            {"time": s["time"], "t_offset_seconds": s["t_offset_seconds"], "sinr": s.get("sinr")}
            for s in samples
            if s.get("sinr") is not None
        ],
        "samples": samples[-15:],
    }


def _step4_ccmni_transfer(
    kernel_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    rx_field_index: int,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    by_iface: dict[str, list[dict[str, Any]]] = defaultdict(list)
    timed_samples = 0

    for path in kernel_files:
        for line_no, line in iter_lines(path):
            m = _CCMNI_RE.search(line)
            if not m:
                continue
            ts_raw, ts = extract_ts(line)
            in_window = False
            if ts:
                in_window = window_for(ts, start, end, pre_s, post_s) == "T_game"
                if in_window:
                    timed_samples += 1
            else:
                in_window = True
            if not in_window:
                continue

            iface = f"ccmni{m.group('id')}"
            rx_fields = [int(m.group("rx0")), int(m.group("rx1")), int(m.group("rx2"))]
            tx_fields = [int(m.group("tx0")), int(m.group("tx1")), int(m.group("tx2"))]
            rx_idx = min(max(rx_field_index, 0), 2)
            tx_idx = rx_idx
            by_iface[iface].append(
                {
                    "time": ts_raw,
                    "dt": ts,
                    "rx_bytes": rx_fields[rx_idx],
                    "tx_bytes": tx_fields[tx_idx],
                    "rx_triplet": rx_fields,
                    "tx_triplet": tx_fields,
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:260]}",
                }
            )

    interfaces: list[dict[str, Any]] = []
    active_ifaces: list[str] = []
    for iface, samples in sorted(by_iface.items()):
        if len(samples) < 2:
            delta_rx = 0
            delta_tx = 0
        else:
            delta_rx = samples[-1]["rx_bytes"] - samples[0]["rx_bytes"]
            delta_tx = samples[-1]["tx_bytes"] - samples[0]["tx_bytes"]
        row = {
            "interface": iface,
            "sample_count": len(samples),
            "rx_bytes_start": samples[0]["rx_bytes"] if samples else None,
            "rx_bytes_end": samples[-1]["rx_bytes"] if samples else None,
            "rx_bytes_delta": delta_rx,
            "tx_bytes_delta": delta_tx,
            "rx_increased": delta_rx > 0,
        }
        interfaces.append(row)
        if delta_rx > 0:
            active_ifaces.append(iface)

    primary = max(interfaces, key=lambda x: x["rx_bytes_delta"], default=None)
    time_alignment = "T_game" if timed_samples > 0 else ("kernel_file_scope" if interfaces else "missing")

    return {
        "coverage": "ok" if interfaces else "missing",
        "time_alignment": time_alignment,
        "timed_sample_count": timed_samples,
        "active_interfaces": active_ifaces,
        "primary_interface": primary["interface"] if primary and primary["rx_bytes_delta"] > 0 else None,
        "primary_rx_bytes_delta": primary["rx_bytes_delta"] if primary else 0,
        "primary_tx_bytes_delta": primary["tx_bytes_delta"] if primary else 0,
        "by_interface": interfaces,
        "note": (
            "kernel 日志无墙钟时间戳时，统计范围为日志文件内 ccmni 首尾差值"
            if time_alignment == "kernel_file_scope"
            else None
        ),
    }


def build_network_investigation(
    *,
    lib_file: Path,
    logs: dict[str, list[Path]],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    ref_dir = _ref_dir(lib_file)
    standards = load_analysis_standards(ref_dir)
    rssi_thresholds = {
        "excellent": int(threshold(standards, "wifi_rssi_excellent_dbm", -50)),
        "good": int(threshold(standards, "wifi_rssi_good_dbm", -60)),
        "fair": int(threshold(standards, "wifi_rssi_fair_dbm", -70)),
        "poor": int(threshold(standards, "wifi_rssi_poor_dbm", -80)),
    }
    rx_field_index = int(threshold(standards, "ccmni_rx_field_index", 1))
    ccmni_dual_threshold = int(threshold(standards, "dual_channel_ccmni_bytes_threshold", 10240))

    step1 = _step1_wifi_rssi(
        logs.get("main_log", []), start, end, pre_s, post_s, rssi_thresholds,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
    )
    step2_files = list(logs.get("radio_log") or []) + list(logs.get("main_log") or []) + list(
        logs.get("sys_log") or []
    )
    # 去重同路径
    seen: set[str] = set()
    step2_unique: list[Path] = []
    for p in step2_files:
        key = str(Path(p).resolve())
        if key in seen:
            continue
        seen.add(key)
        step2_unique.append(p)
    step2 = _step2_wifi_scenario(
        step2_unique, start, end, pre_s, post_s,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
    )
    step3 = _step3_cellular_signal(
        logs.get("radio_log", []), start, end, pre_s, post_s,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
    )
    step4 = _step4_ccmni_transfer(
        logs.get("kernel_log", []), start, end, pre_s, post_s, rx_field_index,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
    )
    dual = _judge_dual_channel(
        step1, step2, step3, step4, ccmni_bytes_threshold=ccmni_dual_threshold
    )

    warnings: list[str] = []
    if step1.get("coverage") != "ok":
        warnings.append("main log 未搜索到有效 WiFi RSSI（rssi:N / ====>>rssi）")
    elif step1.get("t_game_rssi_sparse"):
        gap = step1.get("rssi_gap_conclusion") or (
            (step1.get("wifi_assistant") or {}).get("rssi_gap_conclusion")
            if isinstance(step1.get("wifi_assistant"), dict)
            else None
        )
        warnings.append(
            str(gap)
            if gap
            else "T_game 内 WiFi RSSI 埋点稀疏（曲线仅输出局内实测）"
        )
    if step2.get("wifi_interface_changes", 0) >= 2:
        warnings.append(f"WiFi 接口切换 {step2.get('wifi_interface_changes')} 次")
    if step2.get("cellular_data_during_game"):
        warnings.append("游戏期间检测到蜂窝数据活跃（mobile 非空）")
    if dual.get("is_dual_channel"):
        warnings.append(f"双通道: {dual.get('summary')}")
    elif dual.get("verdict") == "no_signal_only":
        warnings.append(str(dual.get("summary") or "仅有蜂窝信号，非双通道"))
    if step3.get("band_changed"):
        warnings.append(f"驻网频段发生变化: {step3.get('band_changes')}")
    if step4.get("primary_interface") and step4.get("primary_rx_bytes_delta", 0) > 0:
        warnings.append(
            f"蜂窝数传活跃: {step4.get('primary_interface')} "
            f"rx_delta={step4.get('primary_rx_bytes_delta')} bytes"
        )

    return _strip_dt(
        {
            "flow_version": 1,
            "step1_wifi_rssi": step1,
            "step2_wifi_scenario": step2,
            "step3_cellular_signal": step3,
            "step4_ccmni_transfer": step4,
            "dual_channel": dual,
            "warnings": warnings,
        }
    )
