"""自动背光探测：SensorService 时间线 + kernel 辅助源。"""

from __future__ import annotations

import re
from typing import Any, Callable

_DEFAULT_CONTROLLER = "com.android.server.display.AutomaticBrightnessController"
_SENSOR_ENABLE = re.compile(r"SensorService:\s+enable:", re.IGNORECASE)
_SENSOR_DISABLE = re.compile(r"SensorService:\s+disable:", re.IGNORECASE)


def _regex_flags(flags: str) -> int:
    f = 0
    if "ignorecase" in (flags or "").lower():
        f |= re.IGNORECASE
    return f


def _line_matches_pattern(
    line: str,
    pat: dict[str, Any],
    controller_marker: str,
) -> re.Match[str] | None:
    keywords = [str(k) for k in (pat.get("keywords") or [])]
    if keywords and not all(kw in line for kw in keywords):
        return None
    strategy = pat.get("strategy", "last_group")
    if strategy in ("event", "presence"):
        marker = str(pat.get("controller_marker") or controller_marker or "")
        if marker and strategy == "event" and marker not in line:
            return None
    regex = str(pat.get("regex") or "")
    if not regex:
        return None
    return re.search(regex, line, _regex_flags(str(pat.get("flags") or "")))


def resolve_auto_brightness_timeline(
    item_cfg: dict[str, Any],
    main_lines: list[str],
    kernel_lines: list[str] | None = None,
    *,
    event_mapper: Callable[[dict[str, Any], str], str] | None = None,
) -> dict[str, Any]:
    """按日志行顺序取最后一次状态。"""
    not_detected = "未检测到"
    patterns = item_cfg.get("patterns") or []
    controller_marker = str(item_cfg.get("controller_marker") or _DEFAULT_CONTROLLER)
    on_value = str(item_cfg.get("on_value", "开启"))
    off_value = str(item_cfg.get("off_value", "关闭"))

    merged: list[tuple[str, str]] = []
    for line in main_lines:
        merged.append(("main", line))
    for line in kernel_lines or []:
        merged.append(("kernel", line))

    timeline: list[dict[str, Any]] = []
    evidence: list[str] = []

    for _, line in merged:
        for pat in patterns:
            log_names = pat.get("logs") or ["main_log"]
            if _ == "main" and not any(
                x in log_names for x in ("main_log", "main", "sys_log", "sys", "events_log", "radio_log")
            ):
                continue
            if _ == "kernel" and not any(x in log_names for x in ("kernel_log", "kernel")):
                continue
            m = _line_matches_pattern(line, pat, controller_marker)
            if not m:
                continue
            pat_id = str(pat.get("id") or "")
            strategy = pat.get("strategy", "last_group")
            if strategy == "event":
                token = str(pat.get("event_game") or pat.get("event_value") or "")
                if event_mapper:
                    value = event_mapper(item_cfg, token)
                elif token in ("auto_brightness_on", "开启"):
                    value = on_value
                elif token in ("auto_brightness_off", "关闭"):
                    value = off_value
                else:
                    value = token or on_value
            else:
                value = on_value
            entry = {"value": value, "pattern_id": pat_id, "line": line.rstrip()}
            timeline.append(entry)
            if len(evidence) < 30:
                evidence.append(line.rstrip())

    if not timeline:
        return {
            "value": not_detected,
            "matched_pattern": None,
            "timeline": [],
            "raw_evidence": evidence,
            "presence_hits": [],
        }

    last = timeline[-1]
    return {
        "value": last["value"],
        "matched_pattern": last.get("pattern_id"),
        "timeline": timeline,
        "raw_evidence": evidence,
        "presence_hits": [t for t in timeline if t.get("pattern_id", "").startswith("kernel_")],
    }


def sensor_auto_brightness_last_bool(samples: list[dict[str, Any]]) -> bool | None:
    """仅 SensorService + AutomaticBrightnessController：最后一次 enable/disable。"""
    last: bool | None = None
    ordered = sorted(samples, key=lambda s: (s.get("time") or "", s.get("line") or 0))
    for sample in ordered:
        pid = str(sample.get("pattern_id") or "")
        if pid not in ("sensor_auto_brightness_enable", "sensor_auto_brightness_disable"):
            continue
        text = str(sample.get("raw_evidence") or "")
        if _DEFAULT_CONTROLLER not in text or "SensorService" not in text:
            continue
        if _SENSOR_ENABLE.search(text):
            last = True
        elif _SENSOR_DISABLE.search(text):
            last = False
    return last


def auto_brightness_likely_from_samples(samples: list[dict[str, Any]]) -> tuple[bool, str | None]:
    """按样本时间线取最后一次自动背光状态。"""
    ordered = sorted(samples, key=lambda s: (s.get("time") or "", s.get("line") or 0))
    last_value: bool | None = None
    evidence: str | None = None
    for sample in ordered:
        pid = str(sample.get("pattern_id") or "")
        text = str(sample.get("raw_evidence") or "")
        if pid == "sensor_auto_brightness_enable":
            if _DEFAULT_CONTROLLER not in text or not _SENSOR_ENABLE.search(text):
                continue
            last_value = True
            evidence = sample.get("raw_evidence")
        elif pid == "sensor_auto_brightness_disable":
            if _DEFAULT_CONTROLLER not in text or not _SENSOR_DISABLE.search(text):
                continue
            last_value = False
            evidence = sample.get("raw_evidence")
        elif pid in ("kernel_mtk_drm_cwb", "kernel_cwb_work_enable"):
            last_value = True
            evidence = sample.get("raw_evidence")
    if last_value is None:
        return False, None
    return last_value, evidence
