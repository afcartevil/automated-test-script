"""游戏前置条件 YAML 探测（仅 flow/game 使用）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

from yaml_config import load_yaml_config

try:
    from auto_brightness_detect import resolve_auto_brightness_timeline
except ImportError:
    resolve_auto_brightness_timeline = None  # type: ignore[misc, assignment]

Mode = Literal["game"]


def _regex_flags(flags: str) -> int:
    f = 0
    if "ignorecase" in (flags or "").lower():
        f |= re.IGNORECASE
    return f


def _lookup_map(pat: dict[str, Any], captured: str) -> str | None:
    for key in (f"map_{captured}_game", f"map_{captured.lower()}_game", f"map_{captured.upper()}_game"):
        if key in pat:
            return str(pat[key])
    return None


def _game_wifi_map(item_cfg: dict[str, Any], token: str) -> str:
    return str(item_cfg.get(f"game_event_{token}", token))


def _game_event_map(item_cfg: dict[str, Any], token: str) -> str:
    mapped = item_cfg.get(f"game_event_{token}")
    if mapped is not None:
        return str(mapped)
    return _game_wifi_map(item_cfg, token)


def load_detection_patterns(ref_dir: Path, extra_path: Path | None = None) -> dict[str, Any]:
    cfg = load_yaml_config(ref_dir / "detection-patterns.yaml")
    items = dict(cfg.get("items") or {})
    if extra_path and extra_path.is_file():
        extra = load_yaml_config(extra_path)
        for key, body in (extra.get("game_patterns") or {}).items():
            items[key] = body
    return items


def _lines_for_pattern(
    pat: dict[str, Any],
    lines: list[str],
    kernel_lines: list[str] | None,
) -> list[str]:
    log_names = pat.get("logs") or ["main_log"]
    if kernel_lines is None:
        return lines
    out: list[str] = []
    if any(x in log_names for x in ("main_log", "main", "sys_log", "sys", "events_log", "radio_log")):
        out.extend(lines)
    if any(x in log_names for x in ("kernel_log", "kernel")):
        out.extend(kernel_lines)
    return out


def detect_item_from_lines(
    item_id: str,
    item_cfg: dict[str, Any],
    lines: list[str],
    *,
    kernel_lines: list[str] | None = None,
    game_package: str = "",
    lcm_max_level: int = 2047,
    volume_max_index: int = 15,
) -> dict[str, Any]:
    if item_cfg.get("resolve") == "timeline_last" and resolve_auto_brightness_timeline is not None:
        return resolve_auto_brightness_timeline(
            item_cfg,
            lines,
            kernel_lines,
            event_mapper=_game_event_map,
        )

    not_detected = "未检测到"
    patterns = item_cfg.get("patterns") or []
    events: list[str] = []
    groups: list[str] = []
    presence_hits: list[dict[str, Any]] = []
    evidence: list[str] = []
    numeric_raw: str | None = None
    kind: str | None = None
    matched_pattern: str | None = None

    for pat in patterns:
        regex = pat.get("regex", "")
        if not regex:
            continue
        keywords = [str(k) for k in (pat.get("keywords") or [])]
        pat_id = str(pat.get("id") or "")
        for line in _lines_for_pattern(pat, lines, kernel_lines):
            if pat.get("package_scoped") and game_package:
                pkg = game_package.split(":")[0]
                if pkg and pkg not in line:
                    continue
            if keywords and not all(kw in line for kw in keywords):
                continue
            m = re.search(regex, line, _regex_flags(pat.get("flags", "")))
            if not m:
                continue
            if len(evidence) < 30:
                evidence.append(line.rstrip())
            strategy = pat.get("strategy", "last_group")
            kind = pat.get("kind")
            if strategy == "presence":
                presence_hits.append({"pattern_id": pat_id, "line": line.rstrip()})
            elif strategy == "event":
                token = str(pat.get("event_game", ""))
                if token:
                    events.append(token)
            elif strategy == "last_group":
                gi = int(pat.get("group", 1))
                if m.lastindex and gi <= m.lastindex:
                    captured = m.group(gi)
                    mapped = _lookup_map(pat, captured)
                    groups.append(mapped if mapped is not None else captured)
                    if kind in ("numeric", "numeric_lcm", "volume_index", "refresh_hz"):
                        numeric_raw = captured

    value = not_detected
    numeric_pct: float | None = None

    if item_cfg.get("resolve") == "any_presence" and presence_hits:
        value = str(item_cfg.get("on_value", "ON"))
        matched_pattern = presence_hits[0].get("pattern_id")
    elif item_cfg.get("resolve") == "last_event" and events:
        last = events[-1]
        value = _game_wifi_map(item_cfg, last) if item_id == "wifi" else last
    elif groups:
        value = groups[-1]
    elif events:
        last = events[-1]
        value = _game_wifi_map(item_cfg, last) if item_id == "wifi" else last

    if value == not_detected:
        default_absent = item_cfg.get("default_when_absent")
        if default_absent:
            value = str(default_absent)

    if kind == "numeric" and numeric_raw:
        try:
            pct = round(100.0 * int(numeric_raw) / 255, 1)
            value = f"{pct}%"
            numeric_pct = pct
        except ValueError:
            pass
    elif kind == "numeric_lcm" and numeric_raw:
        try:
            pct = round(100.0 * int(numeric_raw) / lcm_max_level, 1)
            value = f"{pct}%"
            numeric_pct = pct
        except ValueError:
            pass
    elif kind == "volume_index" and numeric_raw:
        try:
            pct = round(100.0 * int(numeric_raw) / volume_max_index, 1)
            value = f"{pct}%"
            numeric_pct = pct
        except ValueError:
            pass
    elif kind == "refresh_hz" and numeric_raw:
        try:
            value = f"{float(numeric_raw):g}Hz"
        except ValueError:
            value = numeric_raw

    return {
        "value": value,
        "numeric_pct": numeric_pct,
        "matched_pattern": matched_pattern,
        "presence_hits": presence_hits,
        "raw_evidence": evidence,
        "matches": groups or events,
    }
