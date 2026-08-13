"""游戏场景音量日志解析（STREAM_MUSIC 基线 + 游戏内变音量）。

配置: references/keyword-patterns.yaml, analysis-standards.yaml
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from game_skill_paths import ensure_game_scripts_on_path  # noqa: E402

ensure_game_scripts_on_path(__file__)
from skill_references import (  # noqa: E402
    evidence_cap,
    load_analysis_standards,
    load_keyword_patterns,
    threshold,
)


def skill_root() -> Path:
    return Path(__file__).resolve().parent.parent


def references_dir() -> Path:
    return skill_root() / "references"


def _standards() -> dict[str, Any]:
    return load_analysis_standards(references_dir())


MERGE_BURST_SECONDS = int(threshold(_standards(), "merge_burst_seconds", 10))
ENTRY_WINDOW_SECONDS = int(threshold(_standards(), "entry_window_seconds", 60))
_EVIDENCE_CAP = evidence_cap(_standards())


def _log_key_for_files(logs: dict[str, list[Path]], log_names: list[str]) -> list[Path]:
    out: list[Path] = []
    for name in log_names:
        out.extend(logs.get(name, []))
    return out


def _window_label(
    dt: datetime,
    game_start: datetime | None,
    game_end: datetime | None,
    pre_s: int,
    post_s: int,
    window_for: Callable[..., str | None],
) -> str:
    return window_for(dt, game_start, game_end, pre_s, post_s) or "unknown"


def _index_pct(index: int, max_index: int) -> float:
    if max_index <= 0:
        return 0.0
    return round(100.0 * index / max_index, 1)


def _parse_reading_from_match(
    pat: dict[str, Any],
    m: re.Match[str],
    music_stream_id: int,
) -> tuple[int, int, dict[str, Any]] | None:
    fields = {k: v for k, v in m.groupdict().items() if v is not None}
    index_key = str(pat.get("volume_field") or "index")
    stream_key = str(pat.get("stream_field") or "stream")
    index_raw = fields.get(index_key) or fields.get("index") or fields.get("volume")
    if index_raw is None:
        return None
    try:
        index = int(index_raw)
    except (TypeError, ValueError):
        return None
    stream_raw = fields.get(stream_key) or fields.get("stream") or fields.get("streamType")
    if stream_raw is not None:
        try:
            stream = int(stream_raw)
        except (TypeError, ValueError):
            return None
    else:
        stream = int(pat.get("assume_stream") or music_stream_id)

    meta: dict[str, Any] = {}
    if fields.get("device") is not None:
        try:
            meta["device"] = int(fields["device"])
        except (TypeError, ValueError):
            pass
    if fields.get("packageName") is not None:
        pkg = str(fields["packageName"]).strip()
        meta["package_name"] = None if pkg.lower() == "null" else pkg
        if pkg.lower() == "null":
            meta["adjustment_source"] = "key_press"
            meta["adjustment_method"] = "按键调音"
        else:
            meta["adjustment_source"] = "app"
            meta["adjustment_method"] = f"应用调音({pkg})"
    if fields.get("flags") is not None:
        try:
            meta["flags"] = int(fields["flags"])
        except (TypeError, ValueError):
            pass
    if fields.get("old_volume") is not None:
        try:
            meta["old_volume"] = int(fields["old_volume"])
        except (TypeError, ValueError):
            pass
    if fields.get("max_index") is not None:
        try:
            meta["max_index"] = int(fields["max_index"])
        except (TypeError, ValueError):
            pass
    return stream, index, meta


def _contributes_index(pat: dict[str, Any], cat_name: str) -> bool:
    if pat.get("contributes_index") is False:
        return False
    return cat_name in ("volume_index", "volume_setting")


def _dedupe_readings(readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    out: list[dict[str, Any]] = []
    for r in sorted(readings, key=lambda x: x.get("dt") or datetime.min):
        key = (r.get("dt"), r.get("stream"), r.get("index"), r.get("pattern_id"))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _scan_volume_patterns(
    logs: dict[str, list[Path]],
    patterns_cfg: dict[str, Any],
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
    game_start: datetime | None,
    game_end: datetime | None,
    pre_s: int,
    post_s: int,
    music_stream_id: int,
) -> tuple[
    list[dict[str, Any]],
    dict[str, list[dict[str, Any]]],
    dict[str, list[dict[str, Any]]],
    dict[str, dict[str, Any]],
]:
    """返回 (volume_readings, keyword_hits, by_category_samples, setting_context_last)。"""
    readings: list[dict[str, Any]] = []
    hits: dict[str, list[dict[str, Any]]] = {}
    by_cat: dict[str, list[dict[str, Any]]] = {}
    setting_context_last: dict[str, dict[str, Any]] = {}
    categories = patterns_cfg.get("categories") or {}

    for cat_name, cat_body in categories.items():
        if not isinstance(cat_body, dict):
            continue
        cat_hits: list[dict[str, Any]] = []
        for pat in cat_body.get("patterns") or []:
            if not isinstance(pat, dict):
                continue
            pat_id = str(pat.get("id", ""))
            status = str(pat.get("status", "active"))
            log_names = pat.get("logs") or []
            keywords = [str(k) for k in (pat.get("keywords") or [])]
            regex_s = str(pat.get("regex") or "").strip()
            compiled = re.compile(regex_s) if regex_s else None

            files = _log_key_for_files(logs, log_names)
            for path in files:
                for line_no, line in iter_lines(path):
                    if keywords and not all(kw in line for kw in keywords):
                        continue
                    ts_raw, dt = extract_ts(line)
                    if not dt:
                        continue
                    window = _window_label(dt, game_start, game_end, pre_s, post_s, window_for)
                    entry: dict[str, Any] = {
                        "category": cat_name,
                        "pattern_id": pat_id,
                        "status": status,
                        "window": window,
                        "time": ts_raw or "",
                        "file": path.name,
                        "line": line_no,
                        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:300]}",
                    }
                    if compiled:
                        m = compiled.search(line)
                        if not m:
                            if status == "active":
                                continue
                        else:
                            fields = {k: v for k, v in m.groupdict().items() if v is not None}
                            entry["fields"] = fields
                            if _contributes_index(pat, cat_name):
                                parsed = _parse_reading_from_match(pat, m, music_stream_id)
                                if parsed:
                                    stream, index, meta = parsed
                                    entry["stream"] = stream
                                    entry["index"] = index
                                    entry.update(meta)
                                    reading: dict[str, Any] = {
                                        "dt": dt,
                                        "time": ts_raw or str(dt),
                                        "window": window,
                                        "stream": stream,
                                        "index": index,
                                        "pattern_id": pat_id,
                                        "raw_evidence": entry["raw_evidence"],
                                    }
                                    reading.update(meta)
                                    readings.append(reading)
                            elif cat_name == "volume_setting" and pat_id == "event_volume_framerate_vote":
                                entry["refresh_rate"] = fields.get("refresh_rate")
                                entry["peak_refresh_rate"] = fields.get("peak")
                                entry["top_app"] = fields.get("mTopApp")
                                entry["title"] = fields.get("title")
                            elif cat_name == "volume_setting" and pat_id == "thermal_volume_range":
                                entry["volume_min"] = fields.get("volume_min")
                                entry["volume_max"] = fields.get("volume_max")
                    elif status == "active":
                        continue
                    cat_hits.append(entry)
                    if (
                        cat_name == "volume_setting"
                        and pat.get("contributes_index") is False
                        and window == "T_pre"
                    ):
                        setting_context_last[pat_id] = entry
                    if len(cat_hits) <= _EVIDENCE_CAP:
                        by_cat.setdefault(cat_name, []).append(entry)
        if cat_hits:
            hits[cat_name] = cat_hits[:_EVIDENCE_CAP]

    readings = _dedupe_readings(readings)
    readings.sort(key=lambda r: r.get("dt") or datetime.min)
    return readings, hits, by_cat, setting_context_last


def _dedupe_consecutive(readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    prev_index: int | None = None
    for r in readings:
        idx = r.get("index")
        if idx is None:
            continue
        if prev_index is not None and idx == prev_index:
            continue
        out.append(r)
        prev_index = idx
    return out


def _collapse_transitions(
    readings: list[dict[str, Any]],
    baseline_index: int | None,
    game_start: datetime | None,
    merge_seconds: int = MERGE_BURST_SECONDS,
) -> list[dict[str, Any]]:
    if len(readings) < 2:
        return []
    deduped = _dedupe_consecutive(readings)
    if len(deduped) < 2:
        return []

    bursts: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = [deduped[0]]
    for r in deduped[1:]:
        prev = current[-1]
        prev_dt = prev.get("dt")
        cur_dt = r.get("dt")
        gap_ok = False
        if prev_dt and cur_dt:
            gap_ok = (cur_dt - prev_dt).total_seconds() <= merge_seconds
        if gap_ok:
            current.append(r)
        else:
            bursts.append(current)
            current = [r]
    bursts.append(current)

    transitions: list[dict[str, Any]] = []
    for burst in bursts:
        if len(burst) < 2:
            continue
        first, last = burst[0], burst[-1]
        idx_from = first.get("index")
        idx_to = last.get("index")
        if idx_from is None or idx_to is None or idx_from == idx_to:
            continue
        direction = "up" if idx_to > idx_from else "down"
        kind = "in_game_change"
        if game_start and first.get("dt") and first["dt"] <= game_start + timedelta(seconds=ENTRY_WINDOW_SECONDS):
            if baseline_index is not None and idx_from == baseline_index:
                kind = "entry_adjust"
        if abs(idx_to - idx_from) <= 1 and len(burst) > 2:
            kind = "micro_adjust"
        transitions.append(
            {
                "kind": kind,
                "index_from": idx_from,
                "index_to": idx_to,
                "direction": direction,
                "time_from": first.get("time", ""),
                "time_to": last.get("time", ""),
                "merged_samples": len(burst),
                "pattern_id": last.get("pattern_id"),
                "raw_evidence": last.get("raw_evidence", ""),
            }
        )
    return transitions


def _device_label(device_id: int | None, patterns_cfg: dict[str, Any]) -> str | None:
    if device_id is None:
        return None
    device_map = patterns_cfg.get("audio_output_devices") or {}
    return device_map.get(str(device_id)) or device_map.get(device_id)


def _aura_readings(
    readings: list[dict[str, Any]],
    music_stream_id: int,
    window: str | None = None,
) -> list[dict[str, Any]]:
    out = [
        r
        for r in readings
        if r.get("pattern_id") == "tran_aura_volume_change" and r.get("stream") == music_stream_id
    ]
    if window:
        out = [r for r in out if r.get("window") == window]
    return out


def _format_aura_event(r: dict[str, Any], patterns_cfg: dict[str, Any]) -> dict[str, Any]:
    device = r.get("device")
    return {
        "time": r.get("time", ""),
        "window": r.get("window", ""),
        "stream_type": r.get("stream"),
        "volume": r.get("index"),
        "device": device,
        "device_label": _device_label(device, patterns_cfg),
        "package_name": r.get("package_name"),
        "adjustment_source": r.get("adjustment_source"),
        "adjustment_method": r.get("adjustment_method"),
        "flags": r.get("flags"),
        "raw_evidence": r.get("raw_evidence", ""),
    }


def _build_volume_investigation(
    readings: list[dict[str, Any]],
    patterns_cfg: dict[str, Any],
    music_stream_id: int,
    max_index: int,
    game_start: datetime | None,
) -> dict[str, Any]:
    """TranAuraController 主路径：测试前音量 + 游戏内是否变音量。"""
    t_pre = _aura_readings(readings, music_stream_id, "T_pre")
    t_game = _aura_readings(readings, music_stream_id, "T_game")

    step1: dict[str, Any] = {"coverage": "missing", "primary_source": "tran_aura_volume_change"}
    if t_pre:
        last = t_pre[-1]
        event = _format_aura_event(last, patterns_cfg)
        step1 = {
            "coverage": "ok",
            "primary_source": "tran_aura_volume_change",
            "volume": last.get("index"),
            "volume_pct": _index_pct(last["index"], max_index),
            "stream_type": last.get("stream"),
            "device": last.get("device"),
            "device_label": event.get("device_label"),
            "package_name": last.get("package_name"),
            "adjustment_method": last.get("adjustment_method"),
            "flags": last.get("flags"),
            "time": last.get("time"),
            "raw_evidence": last.get("raw_evidence"),
            "samples_in_T_pre": len(t_pre),
        }

    baseline_index = step1.get("volume")
    game_volumes = [r["index"] for r in t_game if r.get("index") is not None]
    idx_min = min(game_volumes) if game_volumes else None
    idx_max = max(game_volumes) if game_volumes else None
    stable = idx_min == idx_max if idx_min is not None and idx_max is not None else None
    changed = bool(game_volumes and baseline_index is not None and (idx_min != baseline_index or idx_max != baseline_index))
    if game_volumes and baseline_index is None:
        changed = idx_min != idx_max if idx_min is not None and idx_max is not None else False
    transitions = _collapse_transitions(t_game, baseline_index, game_start)

    key_press_count = sum(1 for r in t_game if r.get("adjustment_source") == "key_press")
    app_adjust_count = sum(1 for r in t_game if r.get("adjustment_source") == "app")

    step2: dict[str, Any] = {
        "coverage": "ok" if t_game else ("partial" if step1.get("coverage") == "ok" else "missing"),
        "changed": changed,
        "stable": stable if game_volumes else (True if step1.get("volume") is not None else None),
        "volume_min": idx_min,
        "volume_max": idx_max,
        "volume_min_pct": _index_pct(idx_min, max_index) if idx_min is not None else None,
        "volume_max_pct": _index_pct(idx_max, max_index) if idx_max is not None else None,
        "baseline_volume": baseline_index,
        "sample_count": len(t_game),
        "change_count": len(transitions),
        "key_press_adjustments": key_press_count,
        "app_adjustments": app_adjust_count,
        "transitions": transitions,
        "samples": [_format_aura_event(r, patterns_cfg) for r in t_game[:_EVIDENCE_CAP]],
    }
    if not t_game and step1.get("volume") is not None:
        step2["note"] = "T_game 内无 TranAuraController 采样，沿用测试前档位视为恒定"
        step2["changed"] = False
        step2["stable"] = True
        step2["volume_min"] = step1.get("volume")
        step2["volume_max"] = step1.get("volume")
        step2["volume_min_pct"] = step1.get("volume_pct")
        step2["volume_max_pct"] = step1.get("volume_pct")

    warnings: list[str] = []
    if step1.get("coverage") != "ok":
        warnings.append("T_pre 内未找到 TranAuraController STREAM_MUSIC 音量")
    if step2.get("changed"):
        warnings.append(
            f"测试过程中音量发生变化：{step2.get('volume_min')}~{step2.get('volume_max')} "
            f"（{step2.get('change_count')} 段）"
        )
    if step2.get("key_press_adjustments", 0) > 0:
        warnings.append(f"游戏内检测到按键调音 {step2['key_press_adjustments']} 次")

    return {
        "flow_version": 1,
        "step1_test_setting": step1,
        "step2_in_game_changes": step2,
        "warnings": warnings,
    }


def _build_audio_route_section(
    readings: list[dict[str, Any]],
    by_cat: dict[str, list[dict[str, Any]]],
    patterns_cfg: dict[str, Any],
    music_stream_id: int,
) -> dict[str, Any]:
    aura_reads = [r for r in readings if r.get("pattern_id") == "tran_aura_volume_change"]
    music_aura = [r for r in aura_reads if r.get("stream") == music_stream_id]

    def _aura_event(r: dict[str, Any]) -> dict[str, Any]:
        return _format_aura_event(r, patterns_cfg)

    t_game = [r for r in music_aura if r.get("window") == "T_game"]
    t_pre = [r for r in music_aura if r.get("window") == "T_pre"]
    devices = sorted({r.get("device") for r in music_aura if r.get("device") is not None})
    device_labels = [_device_label(d, patterns_cfg) for d in devices if d is not None]

    out: dict[str, Any] = {
        "tran_aura_volume_change": {
            "status": "active" if aura_reads else "not_found",
            "T_pre_sample_count": len(t_pre),
            "T_game_sample_count": len(t_game),
            "devices_seen": devices,
            "device_labels": [d for d in device_labels if d],
            "dominant_device": devices[-1] if devices else None,
            "dominant_device_label": _device_label(devices[-1], patterns_cfg) if devices else None,
            "key_press_adjustments": sum(
                1 for r in music_aura if r.get("adjustment_source") == "key_press"
            ),
            "app_adjustments": sum(1 for r in music_aura if r.get("adjustment_source") == "app"),
            "samples": [_aura_event(r) for r in music_aura[:_EVIDENCE_CAP]],
        }
    }
    for pid in ("apm_set_output_devices", "audio_device_route"):
        out[pid] = _collect_placeholder_samples(by_cat, "audio_route", [pid]).get(pid, {})
    return out


def _collect_placeholder_samples(
    by_cat: dict[str, list[dict[str, Any]]],
    category: str,
    pattern_ids: list[str],
) -> dict[str, Any]:
    samples = by_cat.get(category, [])
    out: dict[str, Any] = {}
    for pid in pattern_ids:
        matched = [s for s in samples if s.get("pattern_id") == pid]
        out[pid] = {
            "status": "placeholder" if matched else "not_found",
            "samples": matched[:10],
        }
    return out


def _summarize_in_game(
    readings: list[dict[str, Any]],
    music_stream_id: int,
    max_index: int,
    baseline_index: int | None,
    game_start: datetime | None,
    patterns_cfg: dict[str, Any],
) -> dict[str, Any]:
    music_reads = [r for r in readings if r.get("stream") == music_stream_id and r.get("window") == "T_game"]
    other_reads = [r for r in readings if r.get("stream") != music_stream_id and r.get("window") == "T_game"]

    if not music_reads and baseline_index is not None:
        coverage = "partial"
        indexes = [baseline_index]
    elif music_reads:
        coverage = "ok"
        indexes = [r["index"] for r in music_reads]
    else:
        coverage = "missing"
        indexes = []

    idx_min = min(indexes) if indexes else None
    idx_max = max(indexes) if indexes else None
    stable = idx_min == idx_max if idx_min is not None and idx_max is not None else None
    changed = bool(stable is False)

    transitions = _collapse_transitions(music_reads, baseline_index, game_start)

    min_read = next((r for r in reversed(music_reads) if r["index"] == idx_min), None) if idx_min is not None else None
    max_read = next((r for r in reversed(music_reads) if r["index"] == idx_max), None) if idx_max is not None else None

    return {
        "stream": music_stream_id,
        "max_index_assumed": max_index,
        "coverage": coverage,
        "sample_count": len(music_reads),
        "index_min": idx_min,
        "index_max": idx_max,
        "index_min_pct": _index_pct(idx_min, max_index) if idx_min is not None else None,
        "index_max_pct": _index_pct(idx_max, max_index) if idx_max is not None else None,
        "stable": stable,
        "changed": changed,
        "index_min_sample": (
            {"time": min_read["time"], "index": min_read["index"], "raw_evidence": min_read["raw_evidence"]}
            if min_read
            else None
        ),
        "index_max_sample": (
            {"time": max_read["time"], "index": max_read["index"], "raw_evidence": max_read["raw_evidence"]}
            if max_read
            else None
        ),
        "transitions": transitions,
        "samples": [
            {
                "time": r["time"],
                "index": r["index"],
                "pattern_id": r.get("pattern_id"),
                "device": r.get("device"),
                "device_label": _device_label(r.get("device"), patterns_cfg) if r.get("device") is not None else None,
                "adjustment_source": r.get("adjustment_source"),
                "raw_evidence": r.get("raw_evidence"),
            }
            for r in music_reads[:_EVIDENCE_CAP]
        ],
        "other_stream_samples": [
            {
                "stream": r.get("stream"),
                "index": r.get("index"),
                "time": r.get("time"),
                "raw_evidence": r.get("raw_evidence"),
            }
            for r in other_reads[:10]
        ],
    }


def _build_volume_setting_summary(
    readings: list[dict[str, Any]],
    by_cat: dict[str, list[dict[str, Any]]],
    setting_context_last: dict[str, dict[str, Any]],
    music_stream_id: int,
    max_index: int,
) -> dict[str, Any]:
    """四源音量：T_pre 合并时间线后取最后一次 STREAM_MUSIC 档位。"""
    pre_music = [r for r in readings if r.get("window") == "T_pre" and r.get("stream") == music_stream_id]
    last_setting = None
    if pre_music:
        last = pre_music[-1]
        last_setting = {
            "time": last.get("time"),
            "index": last.get("index"),
            "index_pct": _index_pct(last["index"], max_index),
            "stream": last.get("stream"),
            "pattern_id": last.get("pattern_id"),
            "old_volume": last.get("old_volume"),
            "raw_evidence": last.get("raw_evidence"),
        }

    by_source: dict[str, Any] = {}
    for pid in ("event_volume_changed", "tran_aura_volume_change", "policy_set_stream_volume", "vol_events_stream_music"):
        matched = [r for r in pre_music if r.get("pattern_id") == pid]
        if matched:
            item = matched[-1]
            by_source[pid] = {
                "time": item.get("time"),
                "index": item.get("index"),
                "index_pct": _index_pct(item["index"], max_index),
                "raw_evidence": item.get("raw_evidence"),
            }

    setting_samples = by_cat.get("volume_setting", [])
    fr_last = setting_context_last.get("event_volume_framerate_vote")
    if not fr_last:
        fr_votes = [s for s in setting_samples if s.get("pattern_id") == "event_volume_framerate_vote" and s.get("window") == "T_pre"]
        fr_last = fr_votes[-1] if fr_votes else None
    thermal_last = setting_context_last.get("thermal_volume_range")
    if not thermal_last:
        thermal = [s for s in setting_samples if s.get("pattern_id") == "thermal_volume_range" and s.get("window") == "T_pre"]
        thermal_last = thermal[-1] if thermal else None

    return {
        "strategy": "last_in_T_pre",
        "last_setting": last_setting,
        "by_source": by_source,
        "event_volume_changed_count": len([r for r in pre_music if r.get("pattern_id") == "event_volume_changed"]),
        "tran_aura_count": len([r for r in pre_music if r.get("pattern_id") == "tran_aura_volume_change"]),
        "framerate_vote_last": (
            {
                "time": fr_last.get("time"),
                "refresh_rate_hz": fr_last.get("fields", {}).get("refresh_rate") or fr_last.get("refresh_rate"),
                "peak_refresh_rate_hz": fr_last.get("fields", {}).get("peak") or fr_last.get("peak_refresh_rate"),
                "top_app": fr_last.get("fields", {}).get("mTopApp") or fr_last.get("top_app"),
                "title": fr_last.get("fields", {}).get("title") or fr_last.get("title"),
                "raw_evidence": fr_last.get("raw_evidence"),
            }
            if fr_last
            else None
        ),
        "thermal_volume_range_last": (
            {
                "time": thermal_last.get("time"),
                "volume_min": thermal_last.get("fields", {}).get("volume_min") or thermal_last.get("volume_min"),
                "volume_max": thermal_last.get("fields", {}).get("volume_max") or thermal_last.get("volume_max"),
                "raw_evidence": thermal_last.get("raw_evidence"),
            }
            if thermal_last
            else None
        ),
    }


def _build_pre_test_volume(
    readings: list[dict[str, Any]],
    music_stream_id: int,
    max_index: int,
    setting_summary: dict[str, Any] | None = None,
    volume_investigation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pre_reads = [r for r in readings if r.get("stream") == music_stream_id and r.get("window") == "T_pre"]
    aura_pre = _aura_readings(readings, music_stream_id, "T_pre")
    baseline = None
    coverage = "missing"

    step1 = (volume_investigation or {}).get("step1_test_setting") or {}
    if step1.get("coverage") == "ok" and step1.get("volume") is not None:
        baseline = {
            "time": step1.get("time"),
            "index": step1.get("volume"),
            "index_pct": step1.get("volume_pct"),
            "pattern_id": "tran_aura_volume_change",
            "device": step1.get("device"),
            "device_label": step1.get("device_label"),
            "adjustment_method": step1.get("adjustment_method"),
            "raw_evidence": step1.get("raw_evidence"),
        }
        coverage = "ok"
    else:
        last_setting = (setting_summary or {}).get("last_setting")
        if last_setting:
            baseline = {
                "time": last_setting.get("time"),
                "index": last_setting.get("index"),
                "index_pct": last_setting.get("index_pct"),
                "pattern_id": last_setting.get("pattern_id"),
                "old_volume": last_setting.get("old_volume"),
                "raw_evidence": last_setting.get("raw_evidence"),
            }
            coverage = "ok"
        elif aura_pre:
            last = aura_pre[-1]
            baseline = {
                "time": last["time"],
                "index": last["index"],
                "index_pct": _index_pct(last["index"], max_index),
                "pattern_id": last.get("pattern_id"),
                "raw_evidence": last.get("raw_evidence"),
            }
            coverage = "ok"
        elif pre_reads:
            last = pre_reads[-1]
            baseline = {
                "time": last["time"],
                "index": last["index"],
                "index_pct": _index_pct(last["index"], max_index),
                "pattern_id": last.get("pattern_id"),
                "raw_evidence": last.get("raw_evidence"),
            }
            coverage = "ok"
    return {
        "stream": music_stream_id,
        "max_index_assumed": max_index,
        "coverage": coverage,
        "baseline": baseline,
        "sample_count": len(aura_pre) or len(pre_reads),
        "samples": [
            {"time": r["time"], "index": r["index"], "pattern_id": r.get("pattern_id"), "raw_evidence": r.get("raw_evidence")}
            for r in (aura_pre or pre_reads)[-5:]
        ],
    }


def analyze_game_volume(
    log_path: Path,
    game_start: datetime,
    game_end: datetime,
    *,
    pre_minutes: int = 5,
    post_minutes: int = 3,
    music_stream_id: int | None = None,
    max_index: int | None = None,
    discover_logs: Callable[[Path], dict[str, list[Path]]],
    extract_ts: Callable[..., Any],
    window_for: Callable[..., str | None],
    iter_lines: Callable[[Path], Any],
    fmt_time: Callable[[datetime | None], str],
) -> dict[str, Any]:
    patterns_cfg = load_keyword_patterns(references_dir())
    music_stream_id = music_stream_id if music_stream_id is not None else int(
        patterns_cfg.get("default_music_stream_id", 3)
    )
    max_index = max_index if max_index is not None else int(patterns_cfg.get("max_index_assumed", 15))

    logs = discover_logs(log_path)
    pre_s = max(60, pre_minutes * 60)
    post_s = max(60, post_minutes * 60)
    warnings: list[str] = []
    notes: list[str] = []

    if not logs.get("main_log") and not logs.get("sys_log") and not logs.get("events_log"):
        return {
            "status": "failed",
            "warnings": ["main/sys/events 日志均缺失"],
            "log_availability": {"main_log": False, "sys_log": False, "events_log": False},
        }

    readings, keyword_hits, by_cat, setting_context_last = _scan_volume_patterns(
        logs,
        patterns_cfg,
        extract_ts,
        iter_lines,
        window_for,
        game_start,
        game_end,
        pre_s,
        post_s,
        music_stream_id,
    )

    setting_summary = _build_volume_setting_summary(
        readings, by_cat, setting_context_last, music_stream_id, max_index
    )
    volume_investigation = _build_volume_investigation(
        readings,
        patterns_cfg,
        music_stream_id,
        max_index,
        game_start,
    )
    pre_test = _build_pre_test_volume(
        readings, music_stream_id, max_index, setting_summary, volume_investigation
    )
    baseline_index = (pre_test.get("baseline") or {}).get("index")
    in_game = _summarize_in_game(
        readings, music_stream_id, max_index, baseline_index, game_start, patterns_cfg
    )

    audio_route = _build_audio_route_section(readings, by_cat, patterns_cfg, music_stream_id)
    mute_policy = _collect_placeholder_samples(by_cat, "mute_and_policy", ["mute_stream", "safe_volume"])
    background = _collect_placeholder_samples(
        by_cat, "background_audio", ["audio_flinger_track", "audio_service_focus"]
    )

    if pre_test.get("coverage") == "missing":
        warnings.append("T_pre 内未找到 STREAM_MUSIC 音量采样")
    if in_game.get("coverage") == "missing":
        warnings.append("T_game 内未找到 STREAM_MUSIC 音量采样")
    elif in_game.get("coverage") == "partial":
        notes.append("T_game 无采样，沿用 T_pre 基线作为游戏内恒定档位")
    if in_game.get("changed"):
        notes.append(
            f"T_game 音量 index 范围 {in_game.get('index_min')}~{in_game.get('index_max')}，"
            f"变音量段 {len(in_game.get('transitions') or [])} 条"
        )
    elif in_game.get("index_min") is not None:
        notes.append(f"T_game 音量恒定 index={in_game.get('index_min')}")
    notes.extend(volume_investigation.get("warnings") or [])

    status = "ok"
    if pre_test.get("coverage") == "missing" and in_game.get("coverage") == "missing":
        status = "failed"
    elif warnings:
        status = "partial"

    return {
        "status": status,
        "log_path": str(log_path),
        "game_window": {
            "start": fmt_time(game_start),
            "end": fmt_time(game_end),
            "duration_seconds": int((game_end - game_start).total_seconds()),
        },
        "time_windows": {
            "T_pre": {"start": fmt_time(game_start - timedelta(seconds=pre_s)), "end": fmt_time(game_start)},
            "T_game": {"start": fmt_time(game_start), "end": fmt_time(game_end)},
            "T_post": {"start": fmt_time(game_end), "end": fmt_time(game_end + timedelta(seconds=post_s))},
        },
        "pre_test_volume": pre_test,
        "volume_investigation": volume_investigation,
        "volume_setting_summary": setting_summary,
        "in_game_volume": in_game,
        "audio_route": audio_route,
        "mute_and_policy": mute_policy,
        "background_audio": background,
        "keyword_hits": keyword_hits,
        "log_availability": {
            "events_log": bool(logs.get("events_log")),
            "main_log": bool(logs.get("main_log")),
            "sys_log": bool(logs.get("sys_log")),
        },
        "warnings": warnings,
        "notes": notes,
    }
