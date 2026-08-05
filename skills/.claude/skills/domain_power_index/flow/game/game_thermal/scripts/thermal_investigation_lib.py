"""游戏场景温控两步排查（与 game_thermal/SKILL.md §分析流程对齐）。"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from skill_references import load_analysis_standards, threshold

_TRAN_THERMAL_MARKER = "[tran_thermal_engine]"
_KV_RE = re.compile(r"(\w+)=([^,]+)")
_SKIN_RE = re.compile(
    r"fill_temperatures.*?name:\s*SKIN.*?throttlingStatus:\s*(?P<throttle>\w+)\s+value:\s*(?P<temp>[\d.]+)",
    re.IGNORECASE,
)
_TYPE_DATA_RE = re.compile(
    r"ThermalEngineTypeData:\s*setTypePolicy\s+name[：:]\s*(?P<name>[\w_]+),\s*value:\s*(?P<value>.+?)\s*$",
    re.IGNORECASE,
)
_CPU_INTERVENTION_VALUE_RE = re.compile(r"^\d+(?:\.\d+)?(?:,\d+(?:\.\d+)?)+$")


def _ref_dir(from_file: Path) -> Path:
    return from_file.resolve().parent.parent / "references"


def _strip_dt(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _strip_dt(v) for k, v in obj.items() if k != "dt"}
    if isinstance(obj, list):
        return [_strip_dt(x) for x in obj]
    return obj


def _parse_tran_thermal_fields(line: str) -> dict[str, Any] | None:
    if _TRAN_THERMAL_MARKER not in line:
        return None
    body = line.split(_TRAN_THERMAL_MARKER, 1)[1]
    fields: dict[str, Any] = {}
    for m in _KV_RE.finditer(body):
        key = m.group(1)
        val = m.group(2).strip()
        if key == "temp":
            val = val.rstrip("C")
            try:
                fields["temp_c"] = round(float(val), 3)
            except ValueError:
                fields["temp_c"] = val
        elif key in ("level", "gameMode", "gameFuncMode", "curFps"):
            try:
                fields[key] = int(val)
            except ValueError:
                fields[key] = val
        elif key in ("touch", "screenOn", "multiWin", "vtShell"):
            fields[key] = val.lower() == "true"
        else:
            fields[key] = val

    limits_m = re.search(r"limits\{([^}]+)\}", body)
    if limits_m:
        limits: dict[str, int] = {}
        for lm in re.finditer(r"(\w+)=(\d+)", limits_m.group(1)):
            limits[lm.group(1)] = int(lm.group(2))
        fields["limits"] = limits
        fields["limits_active"] = any(v > 0 for v in limits.values())
    return fields if fields else None


def _temp_stats(samples: list[dict[str, Any]], key: str = "temp_c") -> dict[str, Any]:
    vals = [s[key] for s in samples if isinstance(s.get(key), (int, float))]
    if not vals:
        return {"min": None, "max": None, "avg": None, "first": None, "last": None, "delta": None}
    first, last = vals[0], vals[-1]
    return {
        "min": round(min(vals), 2),
        "max": round(max(vals), 2),
        "avg": round(sum(vals) / len(vals), 2),
        "first": round(first, 2),
        "last": round(last, 2),
        "delta": round(last - first, 2),
    }


def _is_cpu_intervention_value(value: str) -> bool:
    v = value.strip()
    if not v or v.lower() == "unknown":
        return False
    return bool(_CPU_INTERVENTION_VALUE_RE.match(v))


def _step1_thermal_info(
    main_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    game_package: str,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    engine_events: list[dict[str, Any]] = []
    skin_samples: list[dict[str, Any]] = []
    t0: datetime | None = None

    for path in main_files:
        for line_no, line in iter_lines(path):
            ts_raw, ts = extract_ts(line)
            if not ts:
                continue
            w = window_for(ts, start, end, pre_s, post_s)
            if w != "T_game":
                continue

            fields = _parse_tran_thermal_fields(line)
            if fields:
                if t0 is None:
                    t0 = ts
                offset_s = round((ts - t0).total_seconds(), 1) if t0 else 0.0
                engine_events.append(
                    {
                        "time": ts_raw,
                        "dt": ts,
                        "t_offset_seconds": offset_s,
                        "event": fields.get("event"),
                        "op": fields.get("op"),
                        "temp_c": fields.get("temp_c"),
                        "level": fields.get("level"),
                        "scene": fields.get("scene"),
                        "fg_pkg": fields.get("fgPkg"),
                        "fg_act": fields.get("fgAct"),
                        "game_mode": fields.get("gameMode"),
                        "game_func_mode": fields.get("gameFuncMode"),
                        "cur_fps": fields.get("curFps"),
                        "touch": fields.get("touch"),
                        "limits_active": fields.get("limits_active", False),
                        "limits": fields.get("limits"),
                        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:300]}",
                    }
                )

            skin_m = _SKIN_RE.search(line)
            if skin_m:
                if t0 is None:
                    t0 = ts
                offset_s = round((ts - t0).total_seconds(), 1) if t0 else 0.0
                skin_samples.append(
                    {
                        "time": ts_raw,
                        "dt": ts,
                        "t_offset_seconds": offset_s,
                        "skin_temp_c": round(float(skin_m.group("temp")), 2),
                        "throttling_status": skin_m.group("throttle"),
                        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:280]}",
                    }
                )

    scene_game = [e for e in engine_events if e.get("scene") == "scene_game"]
    if game_package:
        pkg_events = [e for e in engine_events if game_package in str(e.get("fg_pkg") or "")]
        if pkg_events:
            engine_events_pkg = pkg_events
        else:
            engine_events_pkg = engine_events
    else:
        engine_events_pkg = engine_events

    game_mode_on = [e for e in engine_events_pkg if e.get("game_mode") == 1]
    game_func_on = [e for e in engine_events_pkg if e.get("game_func_mode") == 1]

    engine_temps = [e for e in engine_events_pkg if e.get("temp_c") is not None]
    temp_curve = [
        {
            "time": e["time"],
            "t_offset_seconds": e["t_offset_seconds"],
            "temp_c": e["temp_c"],
            "source": "tran_thermal_engine",
        }
        for e in engine_temps
    ]
    skin_curve = [
        {
            "time": s["time"],
            "t_offset_seconds": s["t_offset_seconds"],
            "temp_c": s["skin_temp_c"],
            "source": "SKIN",
        }
        for s in skin_samples
    ]

    return {
        "coverage": "ok" if (engine_events or skin_samples) else "missing",
        "engine_sample_count": len(engine_events_pkg),
        "scene_game_count": len(scene_game),
        "game_mode_enabled_count": len(game_mode_on),
        "game_func_mode_enabled_count": len(game_func_on),
        "game_mode_enabled": bool(game_mode_on),
        "game_func_mode_enabled": bool(game_func_on),
        "engine_temp_stats": _temp_stats(engine_temps),
        "skin_temp_stats": _temp_stats(skin_samples, "skin_temp_c"),
        "temp_curve": temp_curve + skin_curve,
        "engine_events": engine_events_pkg[-20:],
        "skin_samples": skin_samples[-15:],
    }


def _step2_cpu_intervention(
    main_files: list[Path],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    policies: list[dict[str, Any]] = []
    cpu_policies: list[dict[str, Any]] = []

    for path in main_files:
        for line_no, line in iter_lines(path):
            if "ThermalEngineTypeData" not in line:
                continue
            m = _TYPE_DATA_RE.search(line)
            if not m:
                continue
            ts_raw, ts = extract_ts(line)
            if not ts or window_for(ts, start, end, pre_s, post_s) != "T_game":
                continue
            name = m.group("name").strip()
            value = m.group("value").strip()
            entry = {
                "time": ts_raw,
                "policy_name": name,
                "value": value,
                "cpu_intervention": name == "min_cpu_freq" and _is_cpu_intervention_value(value),
                "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:280]}",
            }
            policies.append(entry)
            if name == "min_cpu_freq":
                cpu_policies.append(entry)

    intervention_events = [p for p in cpu_policies if p.get("cpu_intervention")]
    intervention_values = sorted({p["value"] for p in intervention_events})

    return {
        "coverage": "ok" if policies else "missing",
        "policy_count": len(policies),
        "min_cpu_freq_count": len(cpu_policies),
        "cpu_intervention_detected": bool(intervention_events),
        "cpu_intervention_event_count": len(intervention_events),
        "intervention_values": intervention_values,
        "min_cpu_freq_events": cpu_policies[:20],
        "other_policies_sample": [p for p in policies if p["policy_name"] != "min_cpu_freq"][:10],
    }


def build_thermal_investigation(
    *,
    lib_file: Path,
    logs: dict[str, list[Path]],
    start: datetime,
    end: datetime,
    pre_s: int,
    post_s: int,
    game_package: str = "",
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    window_for: Callable[..., str | None],
) -> dict[str, Any]:
    main_files = logs.get("main_log", [])

    step1 = _step1_thermal_info(
        main_files, start, end, pre_s, post_s, game_package.strip(),
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
    )
    step2 = _step2_cpu_intervention(
        main_files, start, end, pre_s, post_s,
        extract_ts=extract_ts, iter_lines=iter_lines, window_for=window_for,
    )

    warnings: list[str] = []
    if step1.get("coverage") != "ok":
        warnings.append("T_game 内未采集到 tran_thermal_engine / SKIN 温度")
    eng = step1.get("engine_temp_stats") or {}
    if eng.get("delta") is not None and eng["delta"] >= float(
        threshold(load_analysis_standards(_ref_dir(lib_file)), "rise_delta_c_default", 3.0)
    ):
        warnings.append(f"tran_thermal_engine 壳温上升 delta={eng['delta']}°C")
    if step2.get("cpu_intervention_detected"):
        warnings.append(
            f"Thermal 介入降低 CPU 下限: min_cpu_freq={step2.get('intervention_values')}"
        )
    if step1.get("game_func_mode_enabled"):
        warnings.append("游戏功能模式已开启（录屏/直播）")

    return _strip_dt(
        {
            "flow_version": 1,
            "step1_thermal_info": step1,
            "step2_cpu_intervention": step2,
            "warnings": warnings,
        }
    )
