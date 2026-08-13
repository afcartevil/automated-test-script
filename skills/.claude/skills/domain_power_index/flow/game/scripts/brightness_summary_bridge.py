"""将 game_brightness.json 的三段亮度结论并入步骤 12/13 汇总与报告。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_game_brightness_doc(analysis_dir: Path) -> dict[str, Any]:
    path = analysis_dir / "game_brightness.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def enrich_brightness_stats(
    brightness_summary: dict[str, Any],
    game_brightness: dict[str, Any],
) -> dict[str, Any]:
    """把 brightness_analysis 合并进步骤 12 的 brightness_stats。"""
    ba = game_brightness.get("brightness_analysis")
    if not ba and not game_brightness.get("brightness_investigation"):
        return brightness_summary
    out = dict(brightness_summary)
    if ba:
        out["brightness_analysis"] = ba
    if game_brightness.get("brightness_investigation"):
        out["brightness_investigation"] = game_brightness["brightness_investigation"]
    if game_brightness.get("pre_test_brightness"):
        out["pre_test_brightness"] = game_brightness["pre_test_brightness"]
    out["game_brightness_status"] = game_brightness.get("status")
    out["game_brightness_skill"] = game_brightness.get("skill", "game_brightness")
    return out


def _pre_game_level(ba: dict[str, Any]) -> int | None:
    pg = ba.get("pre_game_setting") or {}
    by_src = pg.get("by_source") or {}
    bc = by_src.get("brightness_collector") or {}
    if bc.get("brightness_level") is not None:
        return int(bc["brightness_level"])
    if pg.get("brightness_level") is not None:
        return int(pg["brightness_level"])
    return None


def _pre_game_curve(ba: dict[str, Any]) -> int | None:
    pg = ba.get("pre_game_setting") or {}
    if pg.get("curve_val") is not None:
        return int(pg["curve_val"])
    return None


def brightness_analysis_notes(ba: dict[str, Any], investigation: dict[str, Any] | None = None) -> list[str]:
    """供 summary.notes / subsystems 使用的简短结论行。"""
    notes: list[str] = []
    inv = investigation or {}
    s1 = inv.get("step1_test_setting") or {}
    if s1.get("compare_mode") == "nits":
        notes.append(
            f"NPS测试亮度 nits={s1.get('measured_nits')} expected={s1.get('expected_nits')} "
            f"aligned={s1.get('aligned_with_standard')} ({s1.get('project')}/{s1.get('test_case_label')})"
        )
    elif s1.get("brightness_level") is not None:
        notes.append(
            f"测试前设置亮度={s1['brightness_level']}/255 expected={s1.get('expected_level')} "
            f"aligned={s1.get('aligned_with_standard')} ({s1.get('primary_source')})"
        )
    s2 = inv.get("step2_auto_backlight") or {}
    if s2.get("test_condition_misaligned"):
        notes.append("自动背光开启，测试条件未对齐")
    s5 = inv.get("step5_thermal_control") or {}
    if s5.get("test_methodology_issue"):
        notes.append("温控降亮触发（测试手法问题）")

    if not ba:
        return notes
    level = _pre_game_level(ba)
    curve = _pre_game_curve(ba)
    if level is not None:
        notes.append(f"测试前亮度等级(0-255)={level}")
    if curve is not None:
        notes.append(f"测试前背光曲线(0-4095)={curve}")
    launch = ba.get("launch_window") or {}
    if launch.get("phase_count"):
        stats = launch.get("stats") or {}
        notes.append(
            f"启动后 {launch.get('window_seconds', 20)}s 背光变光 "
            f"{launch['phase_count']} 段 "
            f"({stats.get('curve_min')}~{stats.get('curve_max')})"
        )
    in_game = ba.get("in_game_changes") or {}
    if in_game.get("phase_count"):
        stats = in_game.get("stats") or {}
        notes.append(
            f"游戏内背光变光 {in_game['phase_count']} 段 "
            f"({stats.get('curve_min')}~{stats.get('curve_max')})"
        )
    return notes


def brightness_kpi_from_stats(brightness_stats: dict[str, Any]) -> dict[str, Any]:
    """Dashboard KPI：val / sub / evidence / warn（优先 brightness_analysis）。"""
    ba = brightness_stats.get("brightness_analysis") or {}
    evidence: list[str] = []
    warn = False

    if ba:
        pg = ba.get("pre_game_setting") or {}
        level = _pre_game_level(ba)
        curve = _pre_game_curve(ba)
        val_parts: list[str] = []
        if level is not None:
            val_parts.append(f"等级 {level}")
        if curve is not None:
            val_parts.append(f"曲线 {curve}")
        val = " · ".join(val_parts) if val_parts else "N/A"

        sub_parts: list[str] = []
        if pg.get("coverage") == "ok" and pg.get("time"):
            sub_parts.append(f"测试前末值 @ {pg['time']}")
        launch = ba.get("launch_window") or {}
        in_game = ba.get("in_game_changes") or {}
        if launch.get("phase_count"):
            stats = launch.get("stats") or {}
            sub_parts.append(
                f"启动{launch.get('window_seconds', 20)}s: "
                f"{stats.get('curve_min')}~{stats.get('curve_max')} "
                f"({launch['phase_count']}段)"
            )
            warn = True
        if in_game.get("phase_count"):
            stats = in_game.get("stats") or {}
            sub_parts.append(
                f"游戏内: {stats.get('curve_min')}~{stats.get('curve_max')} "
                f"({in_game['phase_count']}段)"
            )
            warn = True
        sub = " · ".join(sub_parts) if sub_parts else brightness_stats.get("coverage", "")

        if pg.get("raw_evidence"):
            evidence.append(f"[测试前设置] {pg['raw_evidence']}")
        by_src = pg.get("by_source") or {}
        bc = by_src.get("brightness_collector") or {}
        if bc.get("raw_evidence") and bc.get("raw_evidence") != pg.get("raw_evidence"):
            evidence.append(f"[BrightnessCollector] {bc['raw_evidence']}")
        for idx, phase in enumerate(launch.get("phases") or [], start=1):
            evidence.append(
                f"[启动变光 段{idx}] {phase.get('time_start')}→{phase.get('time_end')} "
                f"curve {phase.get('curve_min')}~{phase.get('curve_max')} "
                f"时长 {phase.get('duration_seconds')}s"
            )
        for idx, phase in enumerate(in_game.get("phases") or [], start=1):
            evidence.append(
                f"[游戏内变光 段{idx}] {phase.get('time_start')}→{phase.get('time_end')} "
                f"curve {phase.get('curve_min')}~{phase.get('curve_max')} "
                f"时长 {phase.get('duration_seconds')}s"
            )
        return {
            "val": val,
            "sub": sub,
            "evidence": evidence,
            "coverage": pg.get("coverage", brightness_stats.get("coverage")),
            "warn": warn,
            "source": "brightness_analysis",
        }

    return {"source": "legacy"}


def brightness_findings_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    """步骤 13 用的结构化亮度三段摘要。"""
    gb = ctx.get("game_brightness") or {}
    ba = gb.get("brightness_analysis") or {}
    inv = gb.get("brightness_investigation") or {}
    stats = _get_path_summary(ctx, "comparison_outputs.brightness_stats.brightness_analysis") or ba
    if not stats:
        stats = ba
    if not stats:
        return {"coverage": "missing"}

    pg = stats.get("pre_game_setting") or {}
    launch = stats.get("launch_window") or {}
    in_game = stats.get("in_game_changes") or {}

    def _phase_brief(phases: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for p in phases or []:
            out.append(
                {
                    "time_start": p.get("time_start"),
                    "time_end": p.get("time_end"),
                    "duration_seconds": p.get("duration_seconds"),
                    "curve_min": p.get("curve_min"),
                    "curve_max": p.get("curve_max"),
                    "curve_delta": p.get("curve_delta"),
                    "phase_type": p.get("phase_type"),
                }
            )
        return out

    return {
        "coverage": pg.get("coverage", "partial" if stats else "missing"),
        "pre_game_setting": {
            "brightness_level": _pre_game_level(stats),
            "curve_val": _pre_game_curve(stats),
            "time": pg.get("time"),
            "by_source": pg.get("by_source"),
        },
        "launch_window": {
            "window_seconds": launch.get("window_seconds"),
            "phase_count": launch.get("phase_count", 0),
            "stats": launch.get("stats"),
            "phases": _phase_brief(launch.get("phases") or []),
        },
        "in_game_changes": {
            "phase_count": in_game.get("phase_count", 0),
            "stats": in_game.get("stats"),
            "phases": _phase_brief(in_game.get("phases") or []),
        },
        "notes": brightness_analysis_notes(stats, inv),
        "investigation": inv,
    }


def _get_path_summary(ctx: dict[str, Any], path: str) -> Any:
    cur: Any = ctx.get("summary") or {}
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def display_subsystem_from_brightness(brightness_summary: dict[str, Any]) -> dict[str, Any]:
    """供 _build_subsystems display 通道使用。"""
    ba = brightness_summary.get("brightness_analysis") or {}
    if not ba:
        return {}
    pg = ba.get("pre_game_setting") or {}
    launch = ba.get("launch_window") or {}
    in_game = ba.get("in_game_changes") or {}
    parts: list[str] = []
    level = _pre_game_level(ba)
    curve = _pre_game_curve(ba)
    if level is not None:
        parts.append(f"测试前等级={level}/255")
    if curve is not None:
        parts.append(f"测试前曲线={curve}/4095")
    if launch.get("phase_count"):
        st = launch.get("stats") or {}
        parts.append(
            f"启动变光 {st.get('curve_min')}~{st.get('curve_max')} "
            f"({launch['phase_count']}段)"
        )
    if in_game.get("phase_count"):
        st = in_game.get("stats") or {}
        parts.append(
            f"游戏内变光 {st.get('curve_min')}~{st.get('curve_max')} "
            f"({in_game['phase_count']}段)"
        )
    level_flag = "suspect" if launch.get("phase_count") or in_game.get("phase_count") else "normal"
    if pg.get("coverage") != "ok" and not launch.get("phase_count"):
        level_flag = "unknown"
    return {
        "level": level_flag,
        "confidence": "medium" if pg.get("coverage") == "ok" else "low",
        "summary": "；".join(parts) if parts else "亮度三段分析无有效采样",
        "evidence": brightness_analysis_notes(ba),
    }
