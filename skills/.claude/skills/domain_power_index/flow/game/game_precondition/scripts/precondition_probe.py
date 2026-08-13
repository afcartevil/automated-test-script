"""从日志探测游戏功耗测试前置条件（YAML 驱动，flow/game 内聚）。"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts"
if str(_GAME_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_GAME_SCRIPTS))

from game_skill_paths import ensure_game_scripts_on_path  # noqa: E402
from brightness_volume_table import compare_level, compare_nits, lookup_setting  # noqa: E402
from precondition_detect_lib import detect_item_from_lines, load_detection_patterns  # noqa: E402
from skill_references import load_reference_yaml  # noqa: E402

ensure_game_scripts_on_path(__file__)

_EVIDENCE_CAP = 30

_RE_BRIGHTNESS_COLLECTOR = re.compile(
    r"TAB\.BrightnessCollector:\s+brightness:\s*(?P<level>\d+)",
    re.IGNORECASE,
)
_RE_BRIGHTNESS_SYNC = re.compile(
    r"BrightnessSynchronizer:\s+Swallowing update of\s+(?P<level>\d+)",
    re.IGNORECASE,
)
_RE_DPC_BRIGHTNESS = re.compile(
    # 兼容 brt=0.70 (94.0%) 与 brt=0.5488983(user_set) (89.0%)
    r"DisplayPowerController\[\d+\]:\s+BrightnessEvent:\s+"
    r"brt=(?P<brt>[\d.]+)(?:\([^)]*\))?\s*\((?P<brt_pct>[\d.]+)%\),\s*"
    r"nits=\s*(?P<nits>[\d.]+)",
    re.IGNORECASE,
)
_RE_DPC_NITS = re.compile(
    r"DisplayPowerController\[\d+\]:\s+BrightnessEvent:.*?nits=\s*(?P<nits>[\d.]+)",
    re.IGNORECASE,
)
_RE_HWC_CURVE = re.compile(
    r"calculateBrightness:\s*brightness\((?P<ratio>[\d.]+)\)\s*brightness_val\((?P<curve>\d+)\)",
    re.IGNORECASE,
)
_RE_TRAN_AURA_VOLUME = re.compile(
    r"TranAuraController:\s+onAudioVolumeChange:\s+streamType=(?P<stream>\d+)\s*,\s*volume=(?P<volume>\d+)",
    re.IGNORECASE,
)

_GAME_ITEM_ORDER = [
    ("airplane", "airplane", "label_ok", "label_on"),
    ("data", "data", "label_ok", "label_off"),
    ("wifi", "wifi", "label_ok", "label_off"),
    ("bt", "bt", "label_ok", "label_on"),
    ("gps", "gps", "label_ok", "label_on"),
    ("nfc", "nfc", "label_ok", "label_on"),
    ("sim", "sim", "label_ok", "label_missing"),
    ("auto_rotate", "auto_rotate", "label_ok", "label_on"),
    ("auto_brightness", "auto_brightness", "label_ok", "label_on"),
    ("volume", "volume", None, None),
    ("brightness", "brightness", None, None),
    ("refresh_rate", "refresh_rate", None, None),
    ("gesture_nav", "gesture_nav", "label_ok", None),
    ("logger", "logger", "label_ok", "label_on"),
]

VOLUME_PATTERNS: list[tuple[str, str]] = [
    (r"AudioPolicyInterfaceImpl: setStreamVolumeIndex\(\), stream (\d+), index (\d+)", "policy"),
    (
        r"TrVolumeSliderController: checkVolumeIcon assetName: volume_change/volume_(?:up|down)_(\d+)\.png",
        "icon",
    ),
    (r"vol\.Events: writeEvent level_changed STREAM_MUSIC (\d+)", "event"),
]


def _evidence(path: Path | str, line_no: int, line: str) -> str:
    return f"{Path(path).name}:{line_no}: {line.rstrip()}"


def _load_standards_cfg(ref_dir: Path) -> dict[str, Any]:
    return load_reference_yaml(ref_dir, "test-condition-standards.yaml")


def _load_standards(ref_dir: Path) -> dict[str, Any]:
    cfg = _load_standards_cfg(ref_dir)
    return dict(cfg.get("standards") or {})


def _enabled_items(cfg: dict[str, Any]) -> set[str] | None:
    """返回启用检测项；None 表示全开（兼容旧配置）。"""
    scope = cfg.get("scope") or {}
    raw = scope.get("enabled_items")
    if raw is None:
        return None
    return {str(x).strip() for x in raw if str(x).strip()}


def _status_for_brightness(
    *,
    standards: dict[str, Any],
    compare_mode: str,
    expected_level: int | None,
    expected_nits: float | None,
    numeric_level: int | None,
    numeric_nits: float | None,
    numeric_curve: int | None = None,
    level_max: int = 255,
    curve_max: int = 4095,
) -> str:
    std = standards.get("brightness", {})
    if compare_mode == "nits":
        # 最大亮度：level(0-255) > 曲线(0-4095) > nits
        level_tol = int(std.get("level_tolerance", 0))
        if numeric_level is not None:
            target = int(expected_level) if expected_level is not None else int(level_max)
            return compare_level(numeric_level, target, tolerance=level_tol)
        if numeric_curve is not None:
            try:
                return "ok" if int(numeric_curve) >= int(curve_max) - 2 else "bad"
            except (TypeError, ValueError):
                return "unknown"
        tol = float(std.get("nits_tolerance", 20))
        return compare_nits(numeric_nits, expected_nits, tolerance=tol)
    tol = int(std.get("level_tolerance", 0))
    return compare_level(numeric_level, expected_level, tolerance=tol)


def _status_for_value(
    item_id: str,
    normalized: str,
    standards: dict[str, Any],
    numeric_pct: float | None = None,
    *,
    compare_mode: str = "level",
    expected_brightness_level: int | None = None,
    expected_brightness_nits: float | None = None,
    expected_volume_index: int | None = None,
    numeric_level: int | None = None,
    numeric_nits: float | None = None,
    numeric_curve: int | None = None,
    numeric_volume_index: int | None = None,
    level_max: int = 255,
    curve_max: int = 4095,
) -> str:
    std = standards.get(item_id, {})
    if item_id == "brightness":
        return _status_for_brightness(
            standards=standards,
            compare_mode=compare_mode,
            expected_level=expected_brightness_level,
            expected_nits=expected_brightness_nits,
            numeric_level=numeric_level,
            numeric_nits=numeric_nits,
            numeric_curve=numeric_curve,
            level_max=level_max,
            curve_max=curve_max,
        )
    if item_id == "volume":
        if expected_volume_index is None or numeric_volume_index is None:
            return "unknown"
        return "ok" if int(numeric_volume_index) == int(expected_volume_index) else "bad"
    if item_id == "refresh_rate":
        try:
            hz = float(re.search(r"[\d.]+", normalized).group())  # type: ignore[union-attr]
        except (AttributeError, ValueError):
            return "unknown"
        if hz in std.get("bad_fixed_hz", [120, 144]):
            return "bad"
        if hz <= std.get("ok_hz_max", 90):
            return "ok"
        return "warn"
    if item_id == "sim":
        match_vals = std.get("match", ["已插入"])
        if normalized in match_vals:
            return "ok"
        if normalized in ("未插入",):
            return "bad"
        return "unknown"
    match_vals = std.get("match", [])
    if isinstance(match_vals, str):
        match_vals = [match_vals]
    if not match_vals:
        return "unknown"
    if normalized.upper() in {str(m).upper() for m in match_vals}:
        return "ok"
    if normalized in ("未检测到", "unknown", ""):
        return "unknown"
    return "bad"


def _probe_dpc_nits(
    logs: dict[str, list[Path]],
    scan_start: datetime | None,
    game_start: datetime | None,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[..., Any],
    *,
    level_max: int = 255,
) -> dict[str, Any] | None:
    """从 DisplayPowerController BrightnessEvent 读 nits，并尽量解析 brt% → level。"""
    files = list(logs.get("sys_log", [])) + list(logs.get("main_log", []))
    hits: list[dict[str, Any]] = []
    for path in files:
        for line_no, line in iter_lines(path):
            m = _RE_DPC_BRIGHTNESS.search(line) or _RE_DPC_NITS.search(line)
            if not m:
                continue
            _, ts = extract_ts(line)
            if scan_start and ts and ts < scan_start:
                continue
            if game_start and ts and ts >= game_start:
                continue
            level = None
            brt_pct = None
            if "brt_pct" in m.groupdict() and m.group("brt_pct") is not None:
                try:
                    brt_pct = float(m.group("brt_pct"))
                    level = int(round(brt_pct / 100.0 * level_max))
                except (TypeError, ValueError):
                    level = None
            hits.append(
                {
                    "dt": ts,
                    "nits": float(m.group("nits")),
                    "brt_pct": brt_pct,
                    "level": level,
                    "raw_evidence": _evidence(path, line_no, line),
                    "source": "display_power_controller",
                    "log_kind": "sys_log" if "sys" in path.name.lower() else "main_log",
                }
            )
    if not hits:
        return None
    hits.sort(key=lambda r: r.get("dt") or datetime.min)
    return hits[-1]


def _probe_test_brightness(
    logs: dict[str, list[Path]],
    scan_start: datetime | None,
    game_start: datetime | None,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[..., Any],
    *,
    compare_mode: str = "level",
    level_max: int = 255,
    curve_max: int = 4095,
) -> dict[str, Any]:
    """探测测试亮度。最大亮度(nps)优先级：level(0-255) > 曲线(0-4095) > nits。"""
    dpc = _probe_dpc_nits(
        logs, scan_start, game_start, extract_ts, iter_lines, level_max=level_max
    )

    files = logs.get("main_log", []) + logs.get("sys_log", [])
    collectors: list[dict[str, Any]] = []
    syncs: list[dict[str, Any]] = []
    curves: list[dict[str, Any]] = []

    for path in files:
        for line_no, line in iter_lines(path):
            _, ts = extract_ts(line)
            if scan_start and ts and ts < scan_start:
                continue
            if game_start and ts and ts >= game_start:
                continue
            m_c = _RE_BRIGHTNESS_COLLECTOR.search(line)
            if m_c:
                level = int(m_c.group("level"))
                collectors.append(
                    {
                        "dt": ts,
                        "level": level,
                        "level_pct": round(100.0 * level / level_max, 1),
                        "raw_evidence": _evidence(path, line_no, line),
                        "source": "brightness_collector",
                    }
                )
                continue
            m_s = _RE_BRIGHTNESS_SYNC.search(line)
            if m_s:
                level = int(m_s.group("level"))
                syncs.append(
                    {
                        "dt": ts,
                        "level": level,
                        "level_pct": round(100.0 * level / level_max, 1),
                        "raw_evidence": _evidence(path, line_no, line),
                        "source": "brightness_synchronizer",
                    }
                )
                continue
            m_h = _RE_HWC_CURVE.search(line)
            if m_h:
                curve = int(m_h.group("curve"))
                curves.append(
                    {
                        "dt": ts,
                        "curve": curve,
                        "raw_evidence": _evidence(path, line_no, line),
                        "source": "hwc_brightness_val",
                    }
                )

    collectors.sort(key=lambda r: r.get("dt") or datetime.min)
    syncs.sort(key=lambda r: r.get("dt") or datetime.min)
    curves.sort(key=lambda r: r.get("dt") or datetime.min)
    last_level = collectors[-1] if collectors else (syncs[-1] if syncs else None)
    last_curve = curves[-1] if curves else None

    level = last_level["level"] if last_level else None
    # Collector/Sync 缺失时，用 DPC brt% 推导 level（与 game_brightness 一致）
    if level is None and dpc and dpc.get("level") is not None:
        level = int(dpc["level"])
        last_level = {
            "dt": dpc.get("dt"),
            "level": level,
            "level_pct": dpc.get("brt_pct"),
            "raw_evidence": dpc.get("raw_evidence"),
            "source": "display_power_controller",
        }
    curve = last_curve["curve"] if last_curve else None
    nits = float(dpc["nits"]) if dpc else None

    evidence: list[str] = []
    if last_level:
        evidence.append(last_level["raw_evidence"])
    if last_curve:
        evidence.append(last_curve["raw_evidence"])
    if dpc is not None and (not last_level or last_level.get("source") != "display_power_controller"):
        evidence.append(dpc["raw_evidence"])

    if compare_mode == "nits":
        # 最大亮度展示/主值：level > 曲线满量程认定 level > nits
        if level is not None:
            value = str(level)
            primary_source = last_level.get("source") if last_level else "level"
            metric = "level"
        elif curve is not None and int(curve) >= int(curve_max) - 2:
            level = int(level_max)
            value = str(level)
            primary_source = "hwc_brightness_val_max"
            metric = "curve"
        elif curve is not None:
            value = f"curve={curve}"
            primary_source = "hwc_brightness_val"
            metric = "curve"
        elif nits is not None:
            value = f"{nits:g}nit"
            primary_source = "display_power_controller"
            metric = "nits"
        else:
            value = "未检测到"
            primary_source = "missing"
            metric = None
        return {
            "value": value,
            "numeric_level": level,
            "numeric_curve": curve,
            "numeric_nits": nits,
            "numeric_pct": round(100.0 * level / level_max, 1) if level is not None else None,
            "primary_source": primary_source,
            "align_metric": metric,
            "brightness_collector": collectors[-1] if collectors else None,
            "brightness_synchronizer": syncs[-1] if syncs else None,
            "hwc_curve": last_curve,
            "dpc_nits": dpc,
            "raw_evidence": evidence[:_EVIDENCE_CAP],
            "matches": [str(level)] if level is not None else ([f"{nits:g}"] if nits is not None else []),
        }

    value = "未检测到" if level is None else str(level)
    return {
        "value": value,
        "numeric_level": level,
        "numeric_curve": curve,
        "numeric_nits": nits,
        "numeric_pct": last_level["level_pct"] if last_level else None,
        "primary_source": last_level.get("source") if last_level else "missing",
        "align_metric": "level" if level is not None else None,
        "brightness_collector": collectors[-1] if collectors else None,
        "brightness_synchronizer": syncs[-1] if syncs else None,
        "hwc_curve": last_curve,
        "dpc_nits": dpc,
        "raw_evidence": evidence[:_EVIDENCE_CAP],
        "matches": [str(level)] if level is not None else [],
    }


def _probe_test_volume(
    logs: dict[str, list[Path]],
    scan_start: datetime | None,
    game_start: datetime | None,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[..., Any],
    *,
    music_stream_id: int = 3,
    max_index: int = 15,
) -> dict[str, Any]:
    """读取测试音量：TranAuraController STREAM_MUSIC。"""
    files = logs.get("main_log", []) + logs.get("sys_log", [])
    hits: list[dict[str, Any]] = []
    for path in files:
        for line_no, line in iter_lines(path):
            m = _RE_TRAN_AURA_VOLUME.search(line)
            if not m:
                continue
            stream = int(m.group("stream"))
            if stream != music_stream_id:
                continue
            _, ts = extract_ts(line)
            if scan_start and ts and ts < scan_start:
                continue
            if game_start and ts and ts >= game_start:
                continue
            idx = int(m.group("volume"))
            hits.append(
                {
                    "dt": ts,
                    "index": idx,
                    "index_pct": round(100.0 * idx / max_index, 1),
                    "raw_evidence": _evidence(path, line_no, line),
                    "source": "tran_aura_volume_change",
                }
            )
    hits.sort(key=lambda r: r.get("dt") or datetime.min)
    last = hits[-1] if hits else None
    if last is None:
        return {
            "value": "未检测到",
            "numeric_volume_index": None,
            "numeric_pct": None,
            "primary_source": "missing",
            "raw_evidence": [],
            "matches": [],
        }
    return {
        "value": str(last["index"]),
        "numeric_volume_index": last["index"],
        "numeric_pct": last["index_pct"],
        "primary_source": last["source"],
        "raw_evidence": [last["raw_evidence"]],
        "matches": [str(last["index"])],
    }


def _collect_log_lines(
    files: Iterable[Path],
    start: datetime | None,
    end: datetime | None,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[..., Any],
) -> list[str]:
    lines: list[str] = []
    for path in files:
        for line_no, line in iter_lines(path):
            _, ts = extract_ts(line)
            if start and ts and ts < start:
                continue
            if end and ts and ts > end:
                continue
            lines.append(line)
    return lines


def _read_properties_lines(log_path: Path) -> list[str]:
    props = log_path / "properties"
    if not props.exists():
        for p in log_path.rglob("properties"):
            props = p
            break
    if not props.exists():
        return []
    return props.read_text(encoding="utf-8", errors="replace").splitlines()


def probe_test_conditions(
    log_path: Path,
    logs: dict[str, list[Path]],
    game_start: datetime | None,
    game_end: datetime | None,
    pre_seconds: int,
    brightness_summary: dict[str, Any],
    ref_dir: Path,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[..., Any],
    game_package: str = "",
    project: str = "",
    test_case: str = "",
) -> dict[str, Any]:
    cfg = _load_standards_cfg(ref_dir)
    standards = dict(cfg.get("standards") or {})
    enabled = _enabled_items(cfg)
    game_patterns_path = ref_dir / "game-detection-patterns.yaml"
    items = load_detection_patterns(ref_dir, game_patterns_path)

    setting = lookup_setting(ref_dir, project=project or None, test_case=test_case or None)
    compare_mode = str(setting.get("compare_mode") or "level")
    expected_level = setting.get("brightness_level")
    expected_nits = setting.get("brightness_nits")
    expected_volume = setting.get("volume_index")

    scan_start = game_start
    if game_start:
        scan_start = game_start - timedelta(seconds=pre_seconds)

    main_sys = logs.get("main_log", []) + logs.get("sys_log", [])
    events = logs.get("events_log", [])
    kernel = logs.get("kernel_log", [])
    all_log_files = main_sys + events + logs.get("radio_log", [])

    lines = _collect_log_lines(all_log_files, scan_start, game_end, extract_ts, iter_lines)
    kernel_lines = _collect_log_lines(kernel, scan_start, game_end, extract_ts, iter_lines)
    lines.extend(_read_properties_lines(log_path))

    br_std = standards.get("brightness", {})
    vol_std = standards.get("volume", {})
    lcm_max = int(br_std.get("lcm_max_level", 2047))
    vol_max = int(vol_std.get("max_index", 15))
    level_max = int(br_std.get("level_max", 255))
    curve_max = int(br_std.get("curve_max", 4095))

    normalized: dict[str, Any] = {}
    findings: dict[str, dict[str, Any]] = {}

    enabled_set = enabled or set()
    if enabled is None or "brightness" in enabled_set:
        br = _probe_test_brightness(
            logs,
            scan_start,
            game_start,
            extract_ts,
            iter_lines,
            compare_mode=compare_mode,
            level_max=level_max,
            curve_max=curve_max,
        )
        findings["brightness"] = br
        normalized["brightness"] = br["value"]

    if enabled is None or "volume" in enabled_set:
        vol = _probe_test_volume(
            logs,
            scan_start,
            game_start,
            extract_ts,
            iter_lines,
            max_index=vol_max,
        )
        findings["volume"] = vol
        normalized["volume"] = vol["value"]

    brightness_only = enabled is not None and enabled <= {"brightness", "volume"}
    if not brightness_only:
        for item_id, item_cfg in items.items():
            if enabled is not None and item_id not in enabled:
                continue
            if item_id in findings:
                continue
            result = detect_item_from_lines(
                item_id,
                item_cfg,
                lines,
                kernel_lines=kernel_lines,
                game_package=game_package,
                lcm_max_level=lcm_max,
                volume_max_index=vol_max,
            )
            findings[item_id] = result
            normalized[item_id] = result["value"]

        bl = brightness_summary.get("baseline_before_game", {}) or {}
        bl_level = bl.get("level")
        if bl_level is not None and "brightness" not in findings:
            pct = round(100.0 * float(bl_level) / lcm_max, 1)
            normalized["brightness"] = f"{pct}%"
            findings["brightness"] = {
                "value": f"{pct}%",
                "numeric_pct": pct,
                "raw_evidence": [str(bl.get("raw_evidence", ""))],
                "matches": [str(bl_level)],
            }

    if compare_mode == "nits":
        # 最大亮度目标：优先等级满量程，其次曲线，最后 nit 表
        if expected_level is not None:
            br_target_std = f"最大亮度 level={expected_level}"
        else:
            br_target_std = f"最大亮度 level={level_max} / 曲线={curve_max}"
            if expected_nits is not None:
                br_target_std += f" / {expected_nits:g}nit"
    else:
        br_target_std = (
            f"level={expected_level}"
            if expected_level is not None
            else "未匹配项目/基础场景亮度等级设定（见 brightness-volume-by-project.yaml）"
        )
    vol_target_std = (
        str(expected_volume)
        if expected_volume is not None
        else "未匹配项目音量设定（见 brightness-volume-by-project.yaml）"
    )

    tags: list[dict[str, Any]] = []
    missing: list[str] = []

    for tag_id, key, ok_lbl, on_lbl in _GAME_ITEM_ORDER:
        if enabled is not None and key not in enabled:
            continue
        if key not in items and key not in normalized:
            continue
        val = str(normalized.get(key, "未检测到"))
        std_block = standards.get(key, {})
        finding = findings.get(key) or {}
        numeric = finding.get("numeric_pct")
        status = _status_for_value(
            key,
            val,
            standards,
            numeric,
            compare_mode=compare_mode,
            expected_brightness_level=(
                (expected_level if expected_level is not None else level_max)
                if key == "brightness" and compare_mode == "nits"
                else (expected_level if key == "brightness" else None)
            ),
            expected_brightness_nits=expected_nits if key == "brightness" else None,
            expected_volume_index=expected_volume if key == "volume" else None,
            numeric_level=finding.get("numeric_level"),
            numeric_nits=finding.get("numeric_nits"),
            numeric_curve=finding.get("numeric_curve"),
            numeric_volume_index=finding.get("numeric_volume_index"),
            level_max=level_max,
            curve_max=curve_max,
        )

        expected_missing = False
        if key == "brightness":
            # 最大亮度：默认目标 level_max，不因项目表缺 nit 而判 unknown
            if compare_mode == "nits":
                expected_missing = False
            else:
                expected_missing = expected_level is None
        elif key == "volume":
            expected_missing = expected_volume is None

        if val == "未检测到":
            status = "unknown"
            missing.append(key)
        elif expected_missing:
            status = "unknown"

        if val == "未检测到":
            label = f"{tag_id.upper()} 未检测到"
        elif key == "brightness":
            if compare_mode == "nits":
                target_lv = expected_level if expected_level is not None else level_max
                label = f"Brightness {val} (目标最大亮度 level={target_lv})"
            elif expected_level is not None:
                label = f"Brightness {val} (目标 {expected_level})"
            else:
                label = f"Brightness {val}"
        elif key == "volume":
            if expected_volume is not None:
                label = f"Volume {val} (目标 {expected_volume})"
            else:
                label = f"Volume {val}"
        elif key == "refresh_rate":
            label = f"Refresh Rate {val}"
        elif key == "auto_brightness":
            if val == "ON":
                label = std_block.get("label_on", "Auto-brightness ON")
            elif val == "OFF":
                label = std_block.get("label_ok", "Auto-brightness OFF")
            else:
                label = f"Auto-brightness {val}"
        elif key == "sim":
            label = std_block.get("label_ok", "SIM") if val == "已插入" else std_block.get("label_missing", "SIM Missing")
        elif val == "ON" and ok_lbl and key in ("wifi", "gesture_nav", "data"):
            label = std_block.get(ok_lbl, f"{tag_id.upper()} ON")
        elif val == "OFF" and ok_lbl:
            label = std_block.get(ok_lbl, f"{tag_id.upper()} OFF")
        elif val == "ON" and on_lbl:
            label = std_block.get(on_lbl, f"{tag_id.upper()} ON")
        else:
            label = f"{tag_id.upper()} {val}"

        ev = finding.get("raw_evidence") or []
        if key == "brightness":
            standard = br_target_std
        elif key == "volume":
            standard = vol_target_std
        else:
            standard = std_block.get("standard", "")
        tag = {
            "id": tag_id,
            "label": label,
            "status": status,
            "value": val,
            "standard": standard,
            "raw_evidence": ev[:_EVIDENCE_CAP],
            "time": "",
        }
        if key == "brightness":
            tag["project"] = setting.get("project")
            tag["test_case"] = setting.get("test_case")
            tag["compare_mode"] = compare_mode
            tag["expected_level"] = (
                expected_level if expected_level is not None else (level_max if compare_mode == "nits" else None)
            )
            tag["expected_nits"] = expected_nits
            tag["numeric_level"] = finding.get("numeric_level")
            tag["numeric_curve"] = finding.get("numeric_curve")
            tag["numeric_nits"] = finding.get("numeric_nits")
            tag["align_metric"] = finding.get("align_metric")
            tag["physical_standard_nits"] = (setting.get("physical_standard") or {}).get("brightness_nits")
        if key == "volume":
            tag["project"] = setting.get("project")
            tag["test_case"] = setting.get("test_case")
            tag["expected_volume_index"] = expected_volume
            tag["numeric_volume_index"] = finding.get("numeric_volume_index")
            tag["physical_standard_db"] = (setting.get("physical_standard") or {}).get("volume_db")
        tags.append(tag)

    detected = sum(1 for t in tags if t["value"] != "未检测到")
    total = max(len(tags), 1)
    if enabled is not None:
        completeness = "good" if not missing and detected == total else ("partial" if detected else "poor")
    else:
        completeness = "good" if detected >= 9 and len(missing) <= 3 else "partial" if detected >= 5 else "poor"

    return {
        "completeness": completeness,
        "missing_items": missing,
        "logger_state": normalized.get("logger", ""),
        "scope": {
            "enabled_items": sorted(enabled) if enabled is not None else "all",
            "deferred_items": list((cfg.get("scope") or {}).get("deferred_items") or []),
            "note": "测试亮度+音量；基础场景比对等级；最大亮度优先 level(0-255)→曲线(0-4095)→nits",
        },
        "brightness_volume_setting": setting,
        "scenario": {
            "id": setting.get("test_case"),
            "label": setting.get("test_case_label"),
            "column_hint": setting.get("column_hint"),
            "project": setting.get("project"),
            "compare_mode": compare_mode,
            "target_brightness_level": (
                expected_level if expected_level is not None else (level_max if compare_mode == "nits" else None)
            ),
            "target_brightness_nits": expected_nits,
            "target_volume_index": expected_volume,
            "physical_standard_nits": (setting.get("physical_standard") or {}).get("brightness_nits"),
            "physical_standard_db": (setting.get("physical_standard") or {}).get("volume_db"),
        },
        "tags": tags,
    }


def probe_volume_stats(
    logs: dict[str, list[Path]],
    game_start: datetime | None,
    game_end: datetime | None,
    pre_seconds: int,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[..., Any],
    music_stream_id: int = 3,
    max_index: int = 15,
) -> dict[str, Any]:
    """T_pre 基线 + T_game 音量 min/max。"""
    import re

    scan_start = game_start
    if game_start:
        scan_start = game_start - timedelta(seconds=pre_seconds)

    files = logs.get("main_log", []) + logs.get("sys_log", [])
    readings: list[dict[str, Any]] = []

    for path in files:
        for line_no, line in iter_lines(path):
            _, ts = extract_ts(line)
            if scan_start and ts and ts < scan_start:
                continue
            if game_end and ts and ts > game_end:
                continue
            for pat, kind in VOLUME_PATTERNS:
                m = re.search(pat, line)
                if not m:
                    continue
                if kind == "policy":
                    stream = int(m.group(1))
                    index = int(m.group(2))
                elif kind == "icon":
                    stream = music_stream_id
                    index = int(m.group(1))
                else:
                    stream = music_stream_id
                    index = int(m.group(1))
                if stream != music_stream_id:
                    continue
                window = "unknown"
                if game_start and ts:
                    if ts < game_start:
                        window = "T_pre"
                    elif game_end and ts <= game_end:
                        window = "T_game"
                    elif game_end and ts > game_end:
                        window = "T_post"
                readings.append(
                    {
                        "time": str(ts) if ts else "",
                        "dt": ts,
                        "window": window,
                        "stream": stream,
                        "index": index,
                        "source_file": path.name,
                        "line_no": line_no,
                        "raw_evidence": _evidence(path, line_no, line),
                    }
                )
                break

    readings.sort(key=lambda r: r.get("dt") or datetime.min)
    pre_reads = [r for r in readings if r["window"] == "T_pre"]
    game_reads = [r for r in readings if r["window"] == "T_game"]

    baseline = None
    if pre_reads:
        last = pre_reads[-1]
        baseline = {
            "time": last["time"],
            "index": last["index"],
            "index_pct": round(100.0 * last["index"] / max_index, 1),
            "stream": last["stream"],
            "raw_evidence": last["raw_evidence"],
        }

    game_indexes = [r["index"] for r in game_reads]
    if not game_indexes and baseline:
        game_indexes = [baseline["index"]]
        game_reads = [pre_reads[-1]] if pre_reads else []
    idx_min = min(game_indexes) if game_indexes else None
    idx_max = max(game_indexes) if game_indexes else None
    min_read = next((r for r in reversed(game_reads) if r["index"] == idx_min), None) if idx_min is not None else None
    max_read = next((r for r in reversed(game_reads) if r["index"] == idx_max), None) if idx_max is not None else None

    coverage = "missing"
    if game_reads or pre_reads:
        coverage = "ok" if game_reads else "partial"

    return {
        "source": "main_sys_log",
        "stream": music_stream_id,
        "max_index_assumed": max_index,
        "coverage": coverage,
        "baseline_before_game": baseline,
        "game_window": {
            "sample_count": len(game_reads),
            "index_min": idx_min,
            "index_max": idx_max,
            "index_min_pct": round(100.0 * idx_min / max_index, 1) if idx_min is not None else None,
            "index_max_pct": round(100.0 * idx_max / max_index, 1) if idx_max is not None else None,
            "stable": idx_min == idx_max if idx_min is not None and idx_max is not None else None,
            "changed": idx_min != idx_max if idx_min is not None and idx_max is not None else False,
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
            "raw_evidence": [r["raw_evidence"] for r in game_reads[:_EVIDENCE_CAP]],
        },
    }
