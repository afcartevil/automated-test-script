"""游戏场景亮度排查六步分析（与 SKILL.md §2 分析流程对齐）。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from skill_references import load_reference_yaml, load_analysis_standards, threshold

# 复用 game_precondition 的项目×用例查表
import sys as _sys

_PRE_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "game_precondition" / "scripts"
if str(_PRE_SCRIPTS) not in _sys.path:
    _sys.path.insert(0, str(_PRE_SCRIPTS))
from brightness_volume_table import lookup_setting  # noqa: E402

_AUTO_BRIGHTNESS_CONTROLLER = "com.android.server.display.AutomaticBrightnessController"
_RE_SENSOR_ACTIVATE = re.compile(
    r"SensorService:\s+(?:enable|disable):.*?activate\s*=\s*(true|false)",
    re.IGNORECASE,
)
_RE_BRIGHTNESS_SYNC = re.compile(
    r"BrightnessSynchronizer:\s+Swallowing update of\s+(?P<level>\d+)",
    re.IGNORECASE,
)
_RE_DPC_BRIGHTNESS_EVENT = re.compile(
    # 兼容 brt=0.70 (94.0%) 与 brt=0.5488983(user_set) (89.0%)
    r"DisplayPowerController\[\d+\]:\s+BrightnessEvent:\s+"
    r"brt=(?P<brt>[\d.]+)(?:\([^)]*\))?\s*\((?P<brt_pct>[\d.]+)%\),\s*"
    r"nits=\s*(?P<nits>[\d.]+)",
    re.IGNORECASE,
)
_RE_DPC_REASON = re.compile(r"reason=(?P<reason>\w+)", re.IGNORECASE)
_RE_DPC_STATE = re.compile(r"\bstate=(?P<state>\w+)", re.IGNORECASE)
_RE_THERMAL_LIGHT = re.compile(
    r"thermalLightController:\s+Level-(?P<level>\d+)\s*:(?P<package>[^,]+),.*?temp=(?P<temp>[\d.]+),.*?brightnessNits=(?P<nits>\d+)",
    re.IGNORECASE,
)
_RE_AAL_BL = re.compile(
    r"AALService:.*?(?:BL|EL)=\s*(?P<curve>\d+)",
    re.IGNORECASE,
)
_RE_LOCAL_DISPLAY_ADAPTER_BL = re.compile(
    # 兼容不同字段名：仅做曲线值存在性提取；若无匹配仍保留时间证据
    r"LocalDisplayAdapter:.*?(?:BL|EL)=\s*(?P<curve>\d+)",
    re.IGNORECASE,
)
_RE_HWC_BRIGHTNESS = re.compile(
    r"calculateBrightness:\s*brightness\((?P<ratio>[\d.]+)\)\s*brightness_val\((?P<curve>\d+)\)",
    re.IGNORECASE,
)
_RE_POWERHAL_FPS = re.compile(r"PowerHalWrapper.*updateFps\(\):\s*(?P<hz>[\d.]+)", re.IGNORECASE)
_RE_HWC_FPS = re.compile(r"updateFps\(\):[\d]+.*?fps:(?P<hz>[\d.]+)", re.IGNORECASE)
_RE_CWB_ENABLE = re.compile(
    r"cwb_work_func \[tran_sensor\]cwb enable end \[(?:sucess|success)\].*?cwb_ctrl\.stat(?:ue|us) = 1",
    re.IGNORECASE,
)


def _strip_dt(obj: Any) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if k == "dt":
                continue
            if isinstance(v, datetime):
                out[k] = str(v)
            else:
                out[k] = _strip_dt(v)
        return out
    if isinstance(obj, list):
        return [_strip_dt(x) for x in obj]
    if isinstance(obj, datetime):
        return str(obj)
    return obj


def _references_dir(from_file: Path) -> Path:
    return from_file.resolve().parent.parent / "references"


def load_backlight_2_games(ref_dir: Path) -> list[dict[str, Any]]:
    data = load_reference_yaml(ref_dir, "backlight-2.0-games.yaml")
    return list(data.get("games") or [])


def _match_backlight_2_game(games: list[dict[str, Any]], package: str | None) -> dict[str, Any] | None:
    if not package:
        return None
    pkg = package.strip()
    for item in games:
        if str(item.get("package", "")).strip() == pkg:
            return item
    return None


def _is_max_brightness_scenario(
    *,
    flag: bool | None,
    brightness_level: int | None,
    max_level: int,
    curve_val: int | None = None,
    curve_max: int = 4095,
    measured_nits: float | None = None,
    expected_nits: float | None = None,
    nits_tolerance: float = 20.0,
) -> bool:
    """是否最大亮度：优先 level(0-255) → 曲线(0-4095) → nits；最后才用显式 flag。"""
    if brightness_level is not None:
        try:
            return int(brightness_level) >= int(max_level)
        except (TypeError, ValueError):
            pass
    if curve_val is not None and curve_max:
        try:
            return int(curve_val) >= int(curve_max) - 2
        except (TypeError, ValueError):
            pass
    if measured_nits is not None and expected_nits is not None:
        try:
            return abs(float(measured_nits) - float(expected_nits)) <= max(0.0, float(nits_tolerance))
        except (TypeError, ValueError):
            pass
    if flag is True:
        return True
    if flag is False:
        return False
    return False


def _align_max_brightness(
    *,
    brightness_level: int | None,
    level_max: int,
    level_tolerance: int,
    expected_level: int | None,
    hwc_curve: int | None,
    curve_max: int,
    measured_nits: float | None,
    expected_nits: float | None,
    nits_tolerance: float,
) -> tuple[bool | None, str, str | None]:
    """最大亮度对齐：level(0-255) > 曲线(0-4095) > nits。

    返回 (aligned, align_detail, metric) metric ∈ level|curve|nits|None。
    """
    # 1) 亮度 level
    if brightness_level is not None:
        target = int(expected_level) if expected_level is not None else int(level_max)
        try:
            measured = int(brightness_level)
        except (TypeError, ValueError):
            measured = None
        if measured is not None:
            # 最大亮度：达到目标等级（默认可视为 level_max）
            aligned = abs(measured - target) <= max(0, int(level_tolerance))
            if target >= int(level_max) and measured >= int(level_max) - max(0, int(level_tolerance)):
                aligned = True
            return (
                aligned,
                f"level={measured} expected={target} tol={level_tolerance}（优先等级 0-{level_max}）",
                "level",
            )

    # 2) 亮度曲线
    if hwc_curve is not None and curve_max:
        try:
            curve = int(hwc_curve)
            cmax = int(curve_max)
        except (TypeError, ValueError):
            curve, cmax = None, None
        if curve is not None and cmax is not None:
            aligned = curve >= cmax - 2
            return (
                aligned,
                f"curve={curve}/{cmax}（无 level，用曲线 0-{cmax}）",
                "curve",
            )

    # 3) nits
    if expected_nits is None:
        return None, "未读到 level/曲线，且未匹配项目 NPS「最大亮度」nit 设定", None
    if measured_nits is None:
        return None, "未读到 level/曲线/nits", None
    aligned = abs(float(measured_nits) - float(expected_nits)) <= max(0.0, float(nits_tolerance))
    return (
        aligned,
        f"nits={float(measured_nits):g} expected={float(expected_nits):g} tol={nits_tolerance:g}（无 level/曲线，用 nit）",
        "nits",
    )


def _step1_test_setting(
    readings: list[dict[str, Any]],
    logs: dict[str, list[Path]],
    game_start: datetime,
    *,
    level_max: int,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    compare_mode: str = "level",
    expected_level: int | None = None,
    expected_nits: float | None = None,
    level_tolerance: int = 0,
    nits_tolerance: float = 20.0,
    project: str | None = None,
    test_case: str | None = None,
    test_case_label: str | None = None,
    physical_nits: float | None = 350,
    pre_seconds: int = 300,
    hwc_pre_stable: dict[str, Any] | None = None,
    curve_max: int = 4095,
) -> dict[str, Any]:
    t_pre_start = game_start - timedelta(seconds=max(0, int(pre_seconds)))
    collector = [
        r
        for r in readings
        if r.get("pattern_id") == "brightness_collector"
        and r.get("dt")
        and t_pre_start <= r["dt"] < game_start
    ]
    synchronizer: list[dict[str, Any]] = []
    for path in logs.get("sys_log", []) + logs.get("main_log", []):
        for line_no, line in iter_lines(path):
            m = _RE_BRIGHTNESS_SYNC.search(line)
            if not m:
                continue
            ts_raw, dt = extract_ts(line)
            if not dt or not (t_pre_start <= dt < game_start):
                continue
            synchronizer.append(
                {
                    "brightness_level": int(m.group("level")),
                    "brightness_level_pct": round(100.0 * int(m.group("level")) / level_max, 1),
                    "time": ts_raw or str(dt),
                    "dt": dt,
                    "pattern_id": "brightness_synchronizer",
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:320]}",
                }
            )
    synchronizer.sort(key=lambda r: r.get("dt") or datetime.min)

    # 测试亮度：仅 sys log · DisplayPowerController；取 T_pre 内第一条有效（非熄屏）记录
    dpc_hits: list[dict[str, Any]] = []
    for path in list(logs.get("sys_log", [])):
        for line_no, line in iter_lines(path):
            if "DisplayPowerController" not in line or "BrightnessEvent" not in line:
                continue
            m = _RE_DPC_BRIGHTNESS_EVENT.search(line)
            if not m:
                continue
            ts_raw, dt = extract_ts(line)
            if not dt or not (t_pre_start <= dt < game_start):
                continue
            reason_m = _RE_DPC_REASON.search(line)
            state_m = _RE_DPC_STATE.search(line)
            reason = (reason_m.group("reason") if reason_m else "").lower()
            state = (state_m.group("state") if state_m else "").upper()
            if state == "OFF" or reason in ("screen_off", "doze"):
                continue
            brt_pct = float(m.group("brt_pct"))
            dpc_hits.append(
                {
                    "nits": float(m.group("nits")),
                    "brt": float(m.group("brt")),
                    "brt_pct": brt_pct,
                    "brightness_level": int(round(brt_pct / 100.0 * level_max)),
                    "brightness_level_pct": brt_pct,
                    "reason": reason or None,
                    "state": state or None,
                    "time": ts_raw or str(dt),
                    "dt": dt,
                    "pattern_id": "display_power_controller",
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:420]}",
                }
            )
    dpc_hits.sort(key=lambda r: r.get("dt") or datetime.min)
    # 游戏场景开始前的第一条有效 BrightnessEvent
    first_dpc = dpc_hits[0] if dpc_hits else None
    # 同时保留最后一条 manual/user 作对照
    last_manual = None
    for hit in reversed(dpc_hits):
        if str(hit.get("reason") or "") == "manual":
            last_manual = hit
            break
    last_dpc = dpc_hits[-1] if dpc_hits else None
    # 测试亮度主证据：优先第一条；若其后有更接近开局的 manual，仍以「第一条」为准（按需求）
    test_dpc = first_dpc
    measured_nits = float(test_dpc["nits"]) if test_dpc else None

    primary_source = "missing"
    value: int | None = None
    evidence: str | None = None
    level_evidence: str | None = None
    time_s: str | None = None

    # 优先 DisplayPowerController（sys）作为测试亮度来源
    if test_dpc:
        primary_source = "display_power_controller"
        evidence = test_dpc.get("raw_evidence")
        time_s = test_dpc.get("time")
        value = test_dpc.get("brightness_level")
        # Collector/Synchronizer 有更精确 0-255 等级时覆盖等级，并保留等级日志快照
        if collector:
            value = collector[-1].get("brightness_level")
            level_evidence = collector[-1].get("raw_evidence")
        elif synchronizer:
            value = synchronizer[-1].get("brightness_level")
            level_evidence = synchronizer[-1].get("raw_evidence")
    elif compare_mode == "nits":
        if collector:
            value = collector[-1].get("brightness_level")
            level_evidence = collector[-1].get("raw_evidence")
        elif synchronizer:
            value = synchronizer[-1].get("brightness_level")
            level_evidence = synchronizer[-1].get("raw_evidence")
    else:
        if collector:
            last = collector[-1]
            value = last.get("brightness_level")
            evidence = last.get("raw_evidence")
            level_evidence = last.get("raw_evidence")
            time_s = last.get("time")
            primary_source = "brightness_collector"
        elif synchronizer:
            last = synchronizer[-1]
            value = last.get("brightness_level")
            evidence = last.get("raw_evidence")
            level_evidence = last.get("raw_evidence")
            time_s = last.get("time")
            primary_source = "brightness_synchronizer"

    # main calculateBrightness：无 0-255 level 时，曲线达最大值可认定测试亮度为 255
    hwc_curve = None
    hwc_evidence = None
    hwc_time = None
    if hwc_pre_stable:
        try:
            hwc_curve = int(hwc_pre_stable.get("curve_val"))
        except (TypeError, ValueError):
            hwc_curve = None
        hwc_evidence = hwc_pre_stable.get("raw_evidence")
        hwc_time = hwc_pre_stable.get("time")
    if value is None and hwc_curve is not None and curve_max and hwc_curve >= int(curve_max) - 2:
        value = level_max
        primary_source = "hwc_brightness_val_max"
        evidence = hwc_evidence or evidence
        level_evidence = level_evidence or (
            f"main calculateBrightness brightness_val={hwc_curve}≈{curve_max} → 认定 level={level_max}"
        )
        time_s = time_s or hwc_time
    elif value is None and hwc_curve is not None:
        # 非满量程时仍记录曲线，不硬推 level
        if evidence is None:
            evidence = hwc_evidence
            primary_source = "hwc_brightness_val"
            time_s = hwc_time

    aligned: bool | None = None
    align_metric: str | None = None
    if compare_mode == "nits":
        # 最大亮度：level(0-255) > 曲线(0-4095) > nits
        aligned, align_detail, align_metric = _align_max_brightness(
            brightness_level=value,
            level_max=level_max,
            level_tolerance=level_tolerance,
            expected_level=expected_level,
            hwc_curve=hwc_curve,
            curve_max=curve_max,
            measured_nits=measured_nits,
            expected_nits=expected_nits,
            nits_tolerance=nits_tolerance,
        )
        coverage = "ok" if (value is not None or hwc_curve is not None or measured_nits is not None) else "missing"
        # 仅有曲线达满量程时，补记 level 便于下游展示
        if value is None and align_metric == "curve" and aligned:
            value = level_max
            primary_source = primary_source or "hwc_brightness_val_max"
            level_evidence = level_evidence or (
                f"main calculateBrightness brightness_val={hwc_curve}≈{curve_max} → 认定 level={level_max}"
            )
    else:
        if expected_level is None:
            align_detail = "未匹配项目基础场景 brightness_level 设定"
        elif value is None:
            align_detail = "未读到 DisplayPowerController / BrightnessCollector / Synchronizer"
        else:
            aligned = abs(int(value) - int(expected_level)) <= max(0, int(level_tolerance))
            align_detail = f"measured={value} expected={expected_level} tol={level_tolerance}"
            align_metric = "level"
        coverage = "ok" if value is not None else "missing"

    return {
        "brightness_level": value,
        "brightness_level_pct": round(100.0 * value / level_max, 1) if value is not None else None,
        "measured_nits": measured_nits,
        "nits_evidence": test_dpc.get("raw_evidence") if test_dpc else None,
        "level_evidence": level_evidence,
        "display_power_controller_first": test_dpc,
        "display_power_controller_last": last_dpc,
        "display_power_controller_last_manual": last_manual,
        "primary_source": primary_source,
        "time": time_s,
        "raw_evidence": evidence or (test_dpc.get("raw_evidence") if test_dpc else None),
        "brightness_collector_last": collector[-1] if collector else None,
        "brightness_synchronizer_last": synchronizer[-1] if synchronizer else None,
        "hwc_pre_stable": hwc_pre_stable,
        "hwc_curve_val": hwc_curve,
        "curve_max": curve_max,
        "coverage": coverage,
        "project": project,
        "test_case": test_case,
        "test_case_label": test_case_label,
        "compare_mode": compare_mode,
        "expected_level": expected_level if expected_level is not None else (level_max if compare_mode == "nits" else None),
        "expected_nits": expected_nits,
        "physical_standard_nits": physical_nits,
        "aligned_with_standard": aligned,
        "align_detail": align_detail,
        "align_metric": align_metric,
    }


def _step2_auto_backlight(
    auto_brightness_hits: list[dict[str, Any]],
    logs: dict[str, list[Path]],
    game_start: datetime,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
) -> dict[str, Any]:
    sensor_state: bool | None = None
    sensor_evidence: str | None = None
    sensor_time: str | None = None

    ordered = sorted(auto_brightness_hits, key=lambda s: (s.get("time") or "", s.get("line") or 0))
    for sample in ordered:
        pid = str(sample.get("pattern_id") or "")
        text = str(sample.get("raw_evidence") or "")
        if pid not in ("sensor_auto_brightness_enable", "sensor_auto_brightness_disable"):
            continue
        if _AUTO_BRIGHTNESS_CONTROLLER not in text:
            continue
        m = _RE_SENSOR_ACTIVATE.search(text)
        if m:
            sensor_state = m.group(1).lower() == "true"
        elif pid == "sensor_auto_brightness_enable":
            sensor_state = True
        elif pid == "sensor_auto_brightness_disable":
            sensor_state = False
        sensor_evidence = sample.get("raw_evidence")
        sensor_time = sample.get("time")

    kernel_cwb = False
    kernel_cwb_evidence: str | None = None
    for path in logs.get("kernel_log", []):
        for line_no, line in iter_lines(path):
            if "mtk_drm_cwb" not in line:
                continue
            kernel_cwb = True
            kernel_cwb_evidence = f"{path.name}:{line_no}: {line.strip()[:300]}"
            break
        if kernel_cwb:
            break

    kernel_cwb_work = False
    kernel_cwb_work_evidence: str | None = None
    for path in logs.get("kernel_log", []):
        for line_no, line in iter_lines(path):
            if not _RE_CWB_ENABLE.search(line):
                continue
            kernel_cwb_work = True
            kernel_cwb_work_evidence = f"{path.name}:{line_no}: {line.strip()[:300]}"
            break
        if kernel_cwb_work:
            break

    enabled: bool | None = sensor_state
    evidence_source = "sensor_service"
    if enabled is None and (kernel_cwb or kernel_cwb_work):
        enabled = True
        evidence_source = "kernel_cwb"
    elif enabled is None:
        evidence_source = "not_detected"

    final_evidence = sensor_evidence or kernel_cwb_work_evidence or kernel_cwb_evidence
    return {
        "enabled": enabled,
        "test_condition_misaligned": enabled is True,
        "evidence_source": evidence_source,
        "sensor_service": {
            "activate": sensor_state,
            "time": sensor_time,
            "raw_evidence": sensor_evidence,
        },
        "kernel_mtk_drm_cwb": {"present": kernel_cwb, "raw_evidence": kernel_cwb_evidence},
        "kernel_cwb_work_enable": {"present": kernel_cwb_work, "raw_evidence": kernel_cwb_work_evidence},
        "raw_evidence": final_evidence,
        "coverage": "ok" if enabled is not None else "missing",
    }


def _scan_dpc_brightness_events(
    logs: dict[str, list[Path]],
    game_start: datetime,
    game_end: datetime,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
) -> list[dict[str, Any]]:
    """main（优先）+ sys 搜索 DisplayPowerController BrightnessEvent。
    nits= 实时亮度；brt=(XX%) 为下降比例。
    """
    events: list[dict[str, Any]] = []
    # 原需求以 main 为主，同时覆盖 sys
    for log_key in ("main_log", "sys_log"):
        for path in logs.get(log_key, []):
            for line_no, line in iter_lines(path):
                if "DisplayPowerController" not in line or "BrightnessEvent" not in line:
                    continue
                m = _RE_DPC_BRIGHTNESS_EVENT.search(line)
                if not m:
                    continue
                ts_raw, dt = extract_ts(line)
                if not dt:
                    continue
                window = "T_pre"
                if game_start <= dt <= game_end:
                    window = "T_game"
                elif dt > game_end:
                    window = "T_post"
                reason_m = _RE_DPC_REASON.search(line)
                state_m = _RE_DPC_STATE.search(line)
                reason = (reason_m.group("reason") if reason_m else "").lower()
                state = (state_m.group("state") if state_m else "").upper()
                events.append(
                    {
                        "time": ts_raw or str(dt),
                        "dt": dt,
                        "window": window,
                        "log_source": log_key,
                        "brt": float(m.group("brt")),
                        "brt_pct": float(m.group("brt_pct")),
                        "drop_ratio_pct": float(m.group("brt_pct")),
                        "nits": float(m.group("nits")),
                        "realtime_nits": float(m.group("nits")),
                        "reason": reason or None,
                        "state": state or None,
                        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:420]}",
                    }
                )
    events.sort(key=lambda e: e.get("dt") or datetime.min)
    return events


def _step3_backlight_2_0(
    *,
    max_brightness_scenario: bool,
    game_package: str | None,
    ref_dir: Path,
    dpc_events: list[dict[str, Any]],
    game_start: datetime,
    game_end: datetime,
) -> dict[str, Any]:
    """最大亮度场景：用 DisplayPowerController 判定背光2.0是否生效。
    nits=实时亮度；brt=(XX%)=下降比例，对照 backlight-2.0-games.yaml。
    """
    if not max_brightness_scenario:
        return {
            "skipped": True,
            "reason": "非最大亮度场景，跳过背光2.0分析",
            "max_brightness_scenario": False,
            "coverage": "skipped",
            "applied": False,
            "effective": False,
            "status": "skipped",
        }

    games = load_backlight_2_games(ref_dir)
    matched = _match_backlight_2_game(games, game_package)
    if not matched:
        return {
            "skipped": False,
            "max_brightness_scenario": True,
            "game_package": game_package,
            "in_backlight_2_list": False,
            "message": "场景未添加背光2.0策略",
            "coverage": "not_in_list",
            "applied": False,
            "effective": False,
            "status": "not_in_list",
            "report_summary": "场景未添加背光2.0策略",
            "report_evidence": [],
        }

    # T_game 内 DPC：main 优先，再 sys
    t_game_events = [e for e in dpc_events if e.get("window") == "T_game"]
    main_events = [e for e in t_game_events if e.get("log_source") == "main_log"]
    sys_events = [e for e in t_game_events if e.get("log_source") == "sys_log"]
    sample_pool = main_events or sys_events or t_game_events
    if not sample_pool:
        # 回退 T_pre 末条（刚进游戏前）
        pre = [e for e in dpc_events if e.get("window") == "T_pre"]
        sample_pool = pre

    expected_drop = matched.get("brightness_drop_pct")
    brt_tol = float(threshold(load_analysis_standards(ref_dir), "backlight_2_brt_pct_tolerance", 5.0))

    # 优先选下降比例最接近期望的事件；否则取末条
    chosen: dict[str, Any] | None = None
    if sample_pool and expected_drop is not None:
        chosen = min(
            sample_pool,
            key=lambda e: abs(float(e.get("drop_ratio_pct") or e.get("brt_pct") or 0) - float(expected_drop)),
        )
    elif sample_pool:
        chosen = sample_pool[-1]

    realtime_nits = float(chosen["realtime_nits"]) if chosen and chosen.get("realtime_nits") is not None else None
    drop_ratio = float(chosen["drop_ratio_pct"]) if chosen and chosen.get("drop_ratio_pct") is not None else None

    effective = False
    note = ""
    if chosen and expected_drop is not None and drop_ratio is not None:
        delta = abs(drop_ratio - float(expected_drop))
        effective = delta <= brt_tol
        note = (
            f"实时nits={realtime_nits:g}，下降比例={drop_ratio:g}%（期望≈{expected_drop:g}%，容差±{brt_tol:g}）"
            if realtime_nits is not None
            else f"下降比例={drop_ratio:g}%（期望≈{expected_drop:g}%）"
        )
    elif chosen and realtime_nits is not None and drop_ratio is not None:
        note = f"实时nits={realtime_nits:g}，下降比例={drop_ratio:g}%（名单未配置期望下降比例）"
    elif not chosen:
        note = "T_game/T_pre 未读到 DisplayPowerController BrightnessEvent（main/sys）"

    if effective:
        report_summary = f"背光2.0已生效：{note}"
        status = "applied"
    elif chosen and expected_drop is not None:
        report_summary = f"背光2.0未按期望生效：{note}"
        status = "miss"
    elif chosen:
        report_summary = f"已采集 DisplayPowerController：{note}"
        status = "observed"
    else:
        report_summary = note or "未检测到背光2.0证据"
        status = "missing"

    evidence: list[str] = []
    if chosen and chosen.get("raw_evidence"):
        evidence.append(str(chosen["raw_evidence"]))
    # 再补 1～2 条同窗证据
    for ev in reversed(sample_pool[-3:]):
        raw = str(ev.get("raw_evidence") or "")
        if raw and raw not in evidence:
            evidence.append(raw)
        if len(evidence) >= 3:
            break

    return {
        "skipped": False,
        "max_brightness_scenario": True,
        "game_package": game_package,
        "in_backlight_2_list": True,
        "game_name": matched.get("name"),
        "expected_brightness_drop_pct": expected_drop,
        "realtime_nits": realtime_nits,
        "drop_ratio_pct": drop_ratio,
        "brt": chosen.get("brt") if chosen else None,
        "brt_pct": drop_ratio,
        "effective": effective if chosen else None,
        "applied": bool(effective),
        "status": status,
        "last_brightness_event": chosen,
        "t_game_events": t_game_events[-8:],
        "note": note,
        "report_summary": report_summary,
        "report_evidence": evidence,
        "coverage": "ok" if chosen else "missing",
    }


def _collect_hwc_brightness_samples(
    logs: dict[str, list[Path]],
    start: datetime,
    end: datetime,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
) -> list[dict[str, Any]]:
    """main log：hwcomposer [LEDDEV] calculateBrightness（关键词 brightness）。

    brightness(ratio)=打折率；brightness_val=曲线亮度（0-4095 或 0-5119）。
    连续数秒变化时，以停止变化后的最后一行为准确值。
    """
    samples: list[dict[str, Any]] = []
    for path in logs.get("main_log", []):
        for line_no, line in iter_lines(path):
            if "brightness" not in line.lower():
                continue
            if "calculateBrightness" not in line and "brightness_val" not in line:
                continue
            m = _RE_HWC_BRIGHTNESS.search(line)
            if not m:
                continue
            ts_raw, dt = extract_ts(line)
            if not dt or dt < start or dt > end:
                continue
            samples.append(
                {
                    "time": ts_raw or str(dt),
                    "dt": dt,
                    "curve_val": int(m.group("curve")),
                    "brightness_ratio": float(m.group("ratio")),
                    "pattern_id": "hwc_brightness_val",
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:420]}",
                }
            )
    samples.sort(key=lambda s: s.get("dt") or datetime.min)
    return samples


def _infer_curve_max(samples: list[dict[str, Any]], default: int = 4095) -> int:
    vals = [int(s["curve_val"]) for s in samples if s.get("curve_val") is not None]
    if not vals:
        return default
    peak = max(vals)
    if peak > 4095:
        return 5119
    return 4095 if peak <= 4095 else default


def _detect_hwc_brightness_ramps(
    samples: list[dict[str, Any]],
    *,
    burst_gap_seconds: float = 2.0,
    min_curve_delta: int = 20,
) -> list[dict[str, Any]]:
    """合并连续变光段；每段以停止变化的最后一行作为稳定准确值。"""
    if len(samples) < 2:
        return []
    ramps: list[dict[str, Any]] = []
    i = 0
    n = len(samples)
    while i < n - 1:
        j = i + 1
        while j < n:
            gap = (samples[j]["dt"] - samples[j - 1]["dt"]).total_seconds()
            if gap > burst_gap_seconds:
                break
            j += 1
        block = samples[i:j]
        if len(block) >= 2:
            v0 = int(block[0]["curve_val"])
            v1 = int(block[-1]["curve_val"])
            if abs(v1 - v0) >= min_curve_delta:
                dur = (block[-1]["dt"] - block[0]["dt"]).total_seconds()
                ramps.append(
                    {
                        "time_start": block[0].get("time"),
                        "time_end": block[-1].get("time"),
                        "dt_start": block[0].get("dt"),
                        "dt_end": block[-1].get("dt"),
                        "curve_from": v0,
                        "curve_to": v1,
                        "brightness_ratio_end": block[-1].get("brightness_ratio"),
                        "duration_seconds": round(dur, 3),
                        "sample_count": len(block),
                        "direction": "down" if v1 < v0 else "up",
                        "stable": block[-1],
                        "raw_evidence_start": block[0].get("raw_evidence"),
                        "raw_evidence_end": block[-1].get("raw_evidence"),
                    }
                )
        i = j if j > i else i + 1
    return ramps


def _nearest_by_time(
    items: list[dict[str, Any]],
    target: datetime | None,
    *,
    prefer: str = "nearest",
    max_skew_seconds: float = 120.0,
) -> dict[str, Any] | None:
    if not items or target is None:
        return None
    best: dict[str, Any] | None = None
    best_skew = 1e18
    for it in items:
        dt = it.get("dt")
        if not dt:
            continue
        skew = abs((dt - target).total_seconds())
        if prefer == "before" and dt > target:
            continue
        if prefer == "after" and dt < target:
            continue
        if skew < best_skew:
            best_skew = skew
            best = it
    if best is None or best_skew > max_skew_seconds:
        return None
    return best


def _collect_aal_samples(
    logs: dict[str, list[Path]],
    start: datetime,
    end: datetime,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
) -> list[dict[str, Any]]:
    """仅从 main log 收集 AAL 相关亮度证据（AALService / LocalDisplayAdapter）。"""
    samples: list[dict[str, Any]] = []
    for path in logs.get("main_log", []):
        for line_no, line in iter_lines(path):
            line_s = str(line)
            is_aal_service = "AALService" in line_s
            is_local_display_adapter = "LocalDisplayAdapter" in line_s
            if not is_aal_service and not is_local_display_adapter:
                continue

            m = _RE_AAL_BL.search(line_s) if is_aal_service else _RE_LOCAL_DISPLAY_ADAPTER_BL.search(line_s)
            pattern_id_base = "aal_service" if is_aal_service else "local_display_adapter"
            if not m:
                # 有 AAL 但无 BL/EL 数值时仍记一条（仅作存在性证据）
                ts_raw, dt = extract_ts(line)
                if not dt or dt < start or dt > end:
                    continue
                samples.append(
                    {
                        "time": ts_raw or str(dt),
                        "dt": dt,
                        "curve_val": None,
                        "pattern_id": f"{pattern_id_base}_present",
                        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:320]}",
                    }
                )
                continue
            ts_raw, dt = extract_ts(line)
            if not dt or dt < start or dt > end:
                continue
            samples.append(
                {
                    "time": ts_raw or str(dt),
                    "dt": dt,
                    "curve_val": int(m.group("curve")),
                    "pattern_id": f"{pattern_id_base}_bl",
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:320]}",
                }
            )
    samples.sort(key=lambda s: s.get("dt") or datetime.min)
    return samples


def _pick_aal_key_points(
    valued: list[dict[str, Any]],
    *,
    game_start: datetime,
    segment_gap_seconds: float,
) -> dict[str, Any]:
    """按最长间隔拆分：场景段末次 / 进游戏后首点 / 全窗末次。"""
    empty = {
        "scene_start": None,
        "in_game_start": None,
        "last": None,
        "segment_gap_seconds": None,
    }
    if not valued:
        return empty

    max_gap = 0.0
    split_i: int | None = None
    for i in range(1, len(valued)):
        gap = (valued[i]["dt"] - valued[i - 1]["dt"]).total_seconds()
        if gap > max_gap:
            max_gap = gap
            split_i = i

    if split_i is not None and max_gap >= segment_gap_seconds:
        scene = valued[split_i - 1]
        in_game = valued[split_i]
        gap_used = round(max_gap, 3)
    else:
        after = [s for s in valued if s.get("dt") and s["dt"] >= game_start]
        scene = valued[0]
        in_game = after[0] if after else valued[0]
        gap_used = None

    return {
        "scene_start": scene,
        "in_game_start": in_game,
        "last": valued[-1],
        "segment_gap_seconds": gap_used,
    }


def _aal_evidence_line(sample: dict[str, Any] | None) -> str | None:
    if not sample:
        return None
    raw = sample.get("raw_evidence")
    return str(raw) if raw else None


def _step4_aal_strategy(
    logs: dict[str, list[Path]],
    game_start: datetime,
    game_end: datetime,
    *,
    lookback_seconds: float,
    segment_gap_seconds: float,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
    dpc_events: list[dict[str, Any]] | None = None,
    burst_gap_seconds: float = 2.0,
    min_curve_delta: int = 20,
) -> dict[str, Any]:
    """步骤4：AAL / 降背光时间线。

    以 main `calculateBrightness` 变光停止末行为准，结合 AALService BL 与 sys BrightnessEvent nits。
    报告格式：`4095 700nit → 2881 450nit → 4095 700nit`；快照只保留各段停止最后一行。
    """
    lookback_start = game_start - timedelta(seconds=max(0.0, float(lookback_seconds)))
    # 覆盖进游戏前升亮、局内降亮、退出后回升
    scan_end = game_end + timedelta(seconds=120)
    hwc = _collect_hwc_brightness_samples(
        logs, lookback_start, scan_end, extract_ts=extract_ts, iter_lines=iter_lines
    )
    curve_max = _infer_curve_max(hwc)
    ramps = _detect_hwc_brightness_ramps(
        hwc, burst_gap_seconds=burst_gap_seconds, min_curve_delta=min_curve_delta
    )
    aal_samples = _collect_aal_samples(
        logs, lookback_start, scan_end, extract_ts=extract_ts, iter_lines=iter_lines
    )
    aal_valued = [s for s in aal_samples if s.get("curve_val") is not None]
    dpc = list(dpc_events or [])
    # 若未传入，补扫更宽窗的 DPC
    if not dpc:
        dpc = _scan_dpc_brightness_events(
            logs, lookback_start, scan_end, extract_ts=extract_ts, iter_lines=iter_lines
        )

    aal_present = bool(aal_samples)
    if not hwc and not aal_present:
        return {
            "coverage": "missing",
            "effective": False,
            "active": False,
            "effective_after_game_start": False,
            "sample_count": 0,
            "valued_sample_count": 0,
            "curve_max": curve_max,
            "report_summary": "main log 未检索到 calculateBrightness / AALService，判定 AAL/降背光未生效",
            "report_evidence": [],
            "note": "main log 未检索到 calculateBrightness / AALService，判定 AAL/降背光未生效",
        }

    def _nits_for(dt: datetime | None, *, prefer: str = "nearest") -> float | None:
        hit = _nearest_by_time(dpc, dt, prefer=prefer, max_skew_seconds=180.0)
        if hit and hit.get("nits") is not None:
            return float(hit["nits"])
        return None

    def _aal_stop_near(dt: datetime | None, curve: int | None) -> dict[str, Any] | None:
        """取目标时刻附近、同曲线值的 AAL 最后一行（变化停止点）。"""
        if not aal_valued or dt is None:
            return None
        # 同值窗口：dt 前后 3s 内同 BL 的最后一条
        window = [
            s
            for s in aal_valued
            if s.get("dt")
            and abs((s["dt"] - dt).total_seconds()) <= 5.0
            and (curve is None or int(s.get("curve_val") or -1) == int(curve))
        ]
        if window:
            return window[-1]
        return _nearest_by_time(aal_valued, dt, max_skew_seconds=30.0)

    # 关键稳定点：进游戏前末次升亮停止（多为最大值）
    pre_up = None
    for ramp in reversed(ramps):
        if ramp.get("dt_end") and ramp["dt_end"] <= game_start and ramp.get("direction") == "up":
            pre_up = ramp
            break
    if pre_up is None:
        pre_samples = [s for s in hwc if s.get("dt") and s["dt"] < game_start]
        if pre_samples:
            last = pre_samples[-1]
            pre_up = {
                "curve_to": last.get("curve_val"),
                "dt_end": last.get("dt"),
                "time_end": last.get("time"),
                "stable": last,
                "raw_evidence_end": last.get("raw_evidence"),
                "direction": "hold",
            }

    # 局内降亮：游戏开始后第一段显著下降的停止点
    in_game_down = None
    for ramp in ramps:
        if not ramp.get("dt_end"):
            continue
        if ramp["dt_end"] < game_start or ramp["dt_end"] > game_end:
            continue
        if ramp.get("direction") == "down":
            in_game_down = ramp
            break

    # 退出后回升：游戏结束后升亮停止点
    post_up = None
    for ramp in ramps:
        if ramp.get("dt_start") and ramp["dt_start"] >= game_end and ramp.get("direction") == "up":
            post_up = ramp
            break

    key_points: list[dict[str, Any]] = []

    def _add_point(label: str, ramp: dict[str, Any] | None, *, nits_prefer: str = "before") -> None:
        if not ramp:
            return
        stable = ramp.get("stable") or {}
        curve = ramp.get("curve_to")
        dt_end = ramp.get("dt_end") or stable.get("dt")
        # 降亮段：nits 取变光过程中/起点附近的 BrightnessEvent（目标 nit）
        if ramp.get("direction") == "down":
            nits = _nits_for(ramp.get("dt_start") or dt_end, prefer="after")
            if nits is None:
                nits = _nits_for(dt_end, prefer="nearest")
        else:
            nits = _nits_for(dt_end, prefer=nits_prefer)
            if nits is None:
                nits = _nits_for(dt_end, prefer="nearest")
        aal_hit = _aal_stop_near(dt_end, int(curve) if curve is not None else None)
        dpc_hit = _nearest_by_time(
            dpc,
            ramp.get("dt_start") if ramp.get("direction") == "down" else dt_end,
            prefer="nearest",
            max_skew_seconds=180.0,
        )
        key_points.append(
            {
                "label": label,
                "time": ramp.get("time_end") or stable.get("time"),
                "dt": dt_end,
                "curve_val": curve,
                "nits": nits,
                "brightness_ratio": ramp.get("brightness_ratio_end") or stable.get("brightness_ratio"),
                "hwc_raw": ramp.get("raw_evidence_end") or stable.get("raw_evidence"),
                "aal_raw": (aal_hit or {}).get("raw_evidence"),
                "aal_bl": (aal_hit or {}).get("curve_val"),
                "dpc_raw": (dpc_hit or {}).get("raw_evidence"),
                "dpc_nits": (dpc_hit or {}).get("nits"),
            }
        )

    _add_point("pre_max", pre_up, nits_prefer="before")
    _add_point("in_game_dim", in_game_down, nits_prefer="after")
    _add_point("post_restore", post_up, nits_prefer="nearest")

    # 若局内无 HWC 降亮但 AAL 有变化，回退旧 AAL 分段（仍取停止末值）
    if not in_game_down and aal_valued:
        points = _pick_aal_key_points(
            aal_valued, game_start=game_start, segment_gap_seconds=segment_gap_seconds
        )
        # 场景末次 / 进游戏后稳定末次
        scene = points.get("scene_start")
        in_game_vals = [s for s in aal_valued if s.get("dt") and s["dt"] >= game_start]
        last = in_game_vals[-1] if in_game_vals else points.get("last")
        if scene and not key_points:
            key_points.append(
                {
                    "label": "pre_max",
                    "time": scene.get("time"),
                    "dt": scene.get("dt"),
                    "curve_val": scene.get("curve_val"),
                    "nits": _nits_for(scene.get("dt"), prefer="before"),
                    "hwc_raw": None,
                    "aal_raw": scene.get("raw_evidence"),
                    "aal_bl": scene.get("curve_val"),
                    "dpc_raw": None,
                }
            )
        if last and (not key_points or key_points[-1].get("curve_val") != last.get("curve_val")):
            key_points.append(
                {
                    "label": "in_game_dim",
                    "time": last.get("time"),
                    "dt": last.get("dt"),
                    "curve_val": last.get("curve_val"),
                    "nits": _nits_for(last.get("dt"), prefer="nearest"),
                    "hwc_raw": None,
                    "aal_raw": last.get("raw_evidence"),
                    "aal_bl": last.get("curve_val"),
                    "dpc_raw": None,
                }
            )

    def _fmt_pt(pt: dict[str, Any]) -> str:
        curve = pt.get("curve_val")
        nits = pt.get("nits")
        if curve is None and nits is None:
            return "—"
        if nits is None:
            return f"曲线{curve}"
        try:
            nits_s = str(int(round(float(nits))))
        except (TypeError, ValueError):
            nits_s = str(nits)
        if curve is None:
            return f"{nits_s}nit"
        return f"{curve}（{nits_s}nit）"

    timeline_parts = [_fmt_pt(p) for p in key_points if p.get("curve_val") is not None or p.get("nits") is not None]
    timeline = " → ".join(timeline_parts) if timeline_parts else ""

    # 快照：每个关键点只留停止末行（main HWC + AAL + sys DPC）
    evidence_rows: list[str] = []
    for pt in key_points:
        for raw in (pt.get("hwc_raw"), pt.get("aal_raw"), pt.get("dpc_raw")):
            if raw and raw not in evidence_rows:
                evidence_rows.append(str(raw))

    pre_curve = key_points[0].get("curve_val") if key_points else None
    dim_curve = None
    for pt in key_points:
        if pt.get("label") == "in_game_dim":
            dim_curve = pt.get("curve_val")
            break
    last_curve = key_points[-1].get("curve_val") if key_points else None
    pre_nits = key_points[0].get("nits") if key_points else None
    dim_nits = next((p.get("nits") for p in key_points if p.get("label") == "in_game_dim"), None)

    effective = aal_present or bool(in_game_down)
    effective_after = bool(in_game_down) or any(
        p.get("label") == "in_game_dim" for p in key_points
    )
    if timeline:
        summary = f"AAL/降背光：{timeline}"
    elif aal_present:
        summary = "main log 命中 AALService，判定 AAL 生效"
    else:
        summary = "检测到 main calculateBrightness 变光，但未命中 AALService"

    # 推断最大亮度设定：进游戏前稳定曲线≈curve_max → level 255
    inferred_max_level = False
    if pre_curve is not None and curve_max and int(pre_curve) >= int(curve_max) - 2:
        inferred_max_level = True

    return {
        "coverage": "ok" if (hwc or aal_present) else "missing",
        "effective": effective,
        "active": effective,
        "effective_after_game_start": effective_after,
        "sample_count": len(aal_samples) + len(hwc),
        "valued_sample_count": len(aal_valued),
        "hwc_sample_count": len(hwc),
        "aal_sample_count": len(aal_samples),
        "curve_max": curve_max,
        "ramp_count": len(ramps),
        "ramps": [_strip_dt({k: v for k, v in r.items() if k != "stable"}) for r in ramps],
        "key_points": _strip_dt(key_points),
        "timeline": timeline,
        "first_bl": pre_curve,
        "last_bl": last_curve if last_curve is not None else dim_curve,
        "stable_bl": dim_curve if dim_curve is not None else last_curve,
        "representative_bl": dim_curve if dim_curve is not None else last_curve,
        "scene_start_bl": pre_curve,
        "in_game_bl_from": pre_curve,
        "in_game_bl_to": dim_curve,
        "pre_nits": pre_nits,
        "in_game_nits": dim_nits,
        "inferred_test_level_255": inferred_max_level,
        "change_count": 1 if (pre_curve is not None and dim_curve is not None and pre_curve != dim_curve) else 0,
        "report_summary": summary,
        "report_evidence": evidence_rows,
        "raw_evidence_scene_start": (key_points[0].get("hwc_raw") or key_points[0].get("aal_raw")) if key_points else None,
        "raw_evidence_in_game_start": next(
            (p.get("hwc_raw") or p.get("aal_raw") for p in key_points if p.get("label") == "in_game_dim"),
            None,
        ),
        "raw_evidence_last": (key_points[-1].get("hwc_raw") or key_points[-1].get("aal_raw")) if key_points else None,
        "note": summary,
    }


def _step5_thermal_control(
    logs: dict[str, list[Path]],
    game_start: datetime,
    game_end: datetime,
    pre_seconds: int,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
) -> dict[str, Any]:
    pre_start = game_start - timedelta(seconds=pre_seconds)
    hits: list[dict[str, Any]] = []
    for path in logs.get("main_log", []) + logs.get("sys_log", []):
        for line_no, line in iter_lines(path):
            m = _RE_THERMAL_LIGHT.search(line)
            if not m:
                continue
            ts_raw, dt = extract_ts(line)
            if not dt:
                continue
            window = "other"
            if pre_start <= dt < game_start:
                window = "T_pre"
            elif game_start <= dt <= game_end:
                window = "T_game"
            hits.append(
                {
                    "time": ts_raw or str(dt),
                    "dt": dt,
                    "window": window,
                    "level": int(m.group("level")),
                    "package": m.group("package").strip(),
                    "temp_c": float(m.group("temp")),
                    "brightness_nits": int(m.group("nits")),
                    "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:360]}",
                }
            )
    hits.sort(key=lambda h: h.get("dt") or datetime.min)
    relevant = [h for h in hits if h.get("window") in ("T_pre", "T_game")]
    dimming = bool(relevant)
    return {
        "coverage": "ok" if hits else "missing",
        "triggered": dimming,
        "test_methodology_issue": dimming,
        "hits": hits,
        "relevant_hits": relevant,
        "hit_count": len(hits),
    }


def _downsample_hz_samples(
    items: list[dict[str, Any]], *, max_points: int = 80
) -> list[dict[str, Any]]:
    """保留时间分布均匀的采样点，供刷新率曲线使用。"""
    if len(items) <= max_points:
        return list(items)
    n = len(items)
    idxs: set[int] = {0, n - 1}
    step = (n - 1) / max(1, max_points - 1)
    for i in range(max_points):
        idxs.add(min(n - 1, int(round(i * step))))
    # 极值点
    try:
        idxs.add(max(range(n), key=lambda i: float(items[i]["hz"])))
        idxs.add(min(range(n), key=lambda i: float(items[i]["hz"])))
    except (KeyError, TypeError, ValueError):
        pass
    return [items[i] for i in sorted(idxs)]


def _hz_timeline(items: list[dict[str, Any]], *, max_points: int = 80) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in _downsample_hz_samples(items, max_points=max_points):
        out.append({"time": it.get("time"), "hz": it.get("hz"), "fps": it.get("hz")})
    return out


def _step6_refresh_rate(
    logs: dict[str, list[Path]],
    game_start: datetime,
    game_end: datetime,
    *,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
) -> dict[str, Any]:
    powerhal: list[dict[str, Any]] = []
    hwc: list[dict[str, Any]] = []
    for path in logs.get("main_log", []) + logs.get("sys_log", []):
        for line_no, line in iter_lines(path):
            ts_raw, dt = extract_ts(line)
            if not dt or dt < game_start or dt > game_end:
                continue
            m_ph = _RE_POWERHAL_FPS.search(line)
            if m_ph:
                powerhal.append(
                    {
                        "time": ts_raw or str(dt),
                        "hz": float(m_ph.group("hz")),
                        "source": "PowerHalWrapper",
                        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:280]}",
                    }
                )
            m_hwc = _RE_HWC_FPS.search(line)
            if m_hwc and "hwcomposer" in line.lower():
                hwc.append(
                    {
                        "time": ts_raw or str(dt),
                        "hz": float(m_hwc.group("hz")),
                        "source": "hwcomposer",
                        "raw_evidence": f"{path.name}:{line_no}: {line.strip()[:280]}",
                    }
                )

    def _last_hz(items: list[dict[str, Any]]) -> float | None:
        return items[-1]["hz"] if items else None

    def _avg_hz(items: list[dict[str, Any]]) -> float | None:
        if not items:
            return None
        try:
            return round(sum(float(x["hz"]) for x in items) / len(items), 3)
        except (TypeError, ValueError, KeyError):
            return None

    supported_last = _last_hz(powerhal)
    actual_last = _last_hz(hwc)
    actual_avg = _avg_hz(hwc)
    coverage = "ok" if (powerhal or hwc) else "missing"

    bits: list[str] = []
    if supported_last is not None:
        bits.append(f"支持刷新率={supported_last:g}Hz（PowerHal）")
    if actual_last is not None:
        bits.append(f"实际送显≈{actual_last:g}Hz（hwcomposer）")
    if actual_avg is not None and actual_last is not None and abs(actual_avg - actual_last) >= 0.5:
        bits.append(f"均值={actual_avg:g}Hz")
    if coverage == "missing":
        summary = "屏幕刷新率：T_game 未解析到 PowerHal/hwcomposer 采样"
    else:
        summary = "屏幕刷新率：" + (" · ".join(bits) if bits else "已观测")

    evidence: list[str] = []
    for src in (powerhal[-3:], hwc[-3:]):
        for it in src:
            raw = str(it.get("raw_evidence") or "").strip()
            if raw and raw not in evidence:
                evidence.append(raw)

    # 曲线优先实际送显；无则用支持刷新率
    primary = hwc if hwc else powerhal
    return {
        "coverage": coverage,
        "supported_fps": {
            "last_hz": supported_last,
            "avg_hz": _avg_hz(powerhal),
            "samples": powerhal[-10:],
            "sample_count": len(powerhal),
            "timeline": _hz_timeline(powerhal),
        },
        "actual_fps": {
            "last_hz": actual_last,
            "avg_hz": actual_avg,
            "samples": hwc[-10:],
            "sample_count": len(hwc),
            "timeline": _hz_timeline(hwc),
        },
        "hz_timeline": _hz_timeline(primary, max_points=100),
        "report_summary": summary,
        "report_evidence": evidence[:6],
        "status": "observed" if coverage == "ok" else "missing",
    }


def build_brightness_investigation(
    *,
    lib_file: Path,
    logs: dict[str, list[Path]],
    readings: list[dict[str, Any]],
    auto_brightness_hits: list[dict[str, Any]],
    game_start: datetime,
    game_end: datetime,
    pre_seconds: int,
    game_package: str | None = None,
    max_brightness_scenario: bool | None = None,
    project: str | None = None,
    test_case: str | None = None,
    extract_ts: Callable[..., Any],
    iter_lines: Callable[[Path], Any],
) -> dict[str, Any]:
    ref_dir = _references_dir(lib_file)
    standards = load_analysis_standards(ref_dir)
    level_max = int(threshold(standards, "level_max", 255))
    aal_lookback = float(threshold(standards, "aal_lookback_seconds", 60))
    aal_segment_gap = float(threshold(standards, "aal_segment_gap_seconds", 5))
    level_tol = int(threshold(standards, "brightness_level_tolerance", 0))
    nits_tol = float(threshold(standards, "brightness_nits_tolerance", 20))
    burst_gap = float(threshold(standards, "merge_burst_seconds", 2.0))
    min_curve_delta = int(threshold(standards, "min_curve_delta", 20))

    precond_ref = lib_file.resolve().parent.parent.parent / "game_precondition" / "references"
    setting = lookup_setting(precond_ref, project=project, test_case=test_case)
    compare_mode = str(setting.get("compare_mode") or "level")
    expected_level = setting.get("brightness_level")
    expected_nits = setting.get("brightness_nits")

    dpc_events = _scan_dpc_brightness_events(
        logs,
        game_start - timedelta(seconds=max(pre_seconds, 120)),
        game_end + timedelta(seconds=120),
        extract_ts=extract_ts,
        iter_lines=iter_lines,
    )

    # main HWC：进游戏前变光停止末行，用于认定最大亮度 / 补充 step1
    hwc_scan_start = game_start - timedelta(seconds=max(pre_seconds, int(aal_lookback), 120))
    hwc_pre = _collect_hwc_brightness_samples(
        logs, hwc_scan_start, game_start, extract_ts=extract_ts, iter_lines=iter_lines
    )
    curve_max = _infer_curve_max(hwc_pre)
    hwc_pre_ramps = _detect_hwc_brightness_ramps(
        hwc_pre, burst_gap_seconds=burst_gap, min_curve_delta=min_curve_delta
    )
    hwc_pre_stable: dict[str, Any] | None = None
    for ramp in reversed(hwc_pre_ramps):
        if ramp.get("direction") == "up" and ramp.get("stable"):
            hwc_pre_stable = ramp["stable"]
            break
    if hwc_pre_stable is None and hwc_pre:
        hwc_pre_stable = hwc_pre[-1]

    collector_pre = [
        r
        for r in readings
        if r.get("pattern_id") == "brightness_collector" and r.get("dt") and r["dt"] < game_start
    ]
    provisional_level = collector_pre[-1].get("brightness_level") if collector_pre else None
    if provisional_level is None and hwc_pre_stable:
        try:
            cv = int(hwc_pre_stable.get("curve_val"))
            if cv >= int(curve_max) - 2:
                provisional_level = level_max
        except (TypeError, ValueError):
            pass
    # 背光2.0：最大亮度优先用 level → 曲线 → nits 判定；NPS 用例作 flag 兜底
    is_max = _is_max_brightness_scenario(
        flag=True if compare_mode == "nits" else max_brightness_scenario,
        brightness_level=provisional_level,
        max_level=level_max,
        curve_val=(hwc_pre_stable or {}).get("curve_val") if isinstance(hwc_pre_stable, dict) else None,
        curve_max=curve_max,
        expected_nits=expected_nits,
        nits_tolerance=nits_tol,
    )
    step1 = _step1_test_setting(
        readings,
        logs,
        game_start,
        level_max=level_max,
        extract_ts=extract_ts,
        iter_lines=iter_lines,
        compare_mode=compare_mode,
        expected_level=expected_level,
        expected_nits=expected_nits,
        level_tolerance=level_tol,
        nits_tolerance=nits_tol,
        project=setting.get("project") or project,
        test_case=setting.get("test_case"),
        test_case_label=setting.get("test_case_label"),
        physical_nits=(setting.get("physical_standard") or {}).get("brightness_nits", 350),
        pre_seconds=pre_seconds,
        hwc_pre_stable=hwc_pre_stable,
        curve_max=curve_max,
    )
    # 若 step1 刚推断出满量程 level/曲线，补开背光2.0
    if not is_max:
        is_max = _is_max_brightness_scenario(
            flag=max_brightness_scenario,
            brightness_level=step1.get("brightness_level"),
            max_level=level_max,
            curve_val=step1.get("hwc_curve_val"),
            curve_max=curve_max,
            measured_nits=step1.get("measured_nits"),
            expected_nits=expected_nits,
            nits_tolerance=nits_tol,
        )
    step2 = _step2_auto_backlight(
        auto_brightness_hits, logs, game_start, extract_ts=extract_ts, iter_lines=iter_lines
    )
    step3 = _step3_backlight_2_0(
        max_brightness_scenario=is_max,
        game_package=game_package,
        ref_dir=ref_dir,
        dpc_events=dpc_events,
        game_start=game_start,
        game_end=game_end,
    )
    step4 = _step4_aal_strategy(
        logs,
        game_start,
        game_end,
        lookback_seconds=max(aal_lookback, float(pre_seconds)),
        segment_gap_seconds=aal_segment_gap,
        extract_ts=extract_ts,
        iter_lines=iter_lines,
        dpc_events=dpc_events,
        burst_gap_seconds=burst_gap,
        min_curve_delta=min_curve_delta,
    )
    step5 = _step5_thermal_control(
        logs, game_start, game_end, pre_seconds,
        extract_ts=extract_ts,
        iter_lines=iter_lines,
    )
    step6 = _step6_refresh_rate(
        logs, game_start, game_end,
        extract_ts=extract_ts,
        iter_lines=iter_lines,
    )

    warnings: list[str] = []
    if step2.get("test_condition_misaligned"):
        warnings.append("自动背光已开启，测试条件未对齐")
    if step5.get("test_methodology_issue"):
        warnings.append("测试前或测试中触发温控降亮，归为测试手法问题")
    if step1.get("coverage") != "ok":
        if compare_mode == "nits":
            warnings.append("未获取到 DisplayPowerController BrightnessEvent nits（NPS/最大亮度）")
        else:
            warnings.append("未获取到测试设置亮度（BrightnessCollector / BrightnessSynchronizer）")
    if compare_mode == "nits" and expected_nits is None:
        warnings.append("未匹配项目 NPS「最大亮度」nit 设定（请补全 brightness-volume-by-project.yaml）")
    elif compare_mode != "nits" and expected_level is None:
        warnings.append("未匹配项目×用例亮度设定（请传 --project/--test-case 并补全 brightness-volume-by-project.yaml）")
    if step1.get("aligned_with_standard") is False:
        warnings.append(
            f"测试亮度未对齐项目设定（{step1.get('project')}/{step1.get('test_case_label')}: "
            f"{step1.get('align_detail')}）"
        )

    return _strip_dt(
        {
            "flow_version": 2,
            "brightness_volume_setting": setting,
            "step1_test_setting": step1,
            "step2_auto_backlight": step2,
            "step3_backlight_2_0": step3,
            "step4_aal_strategy": step4,
            "step5_thermal_control": step5,
            "step6_refresh_rate": step6,
            "warnings": warnings,
        }
    )
