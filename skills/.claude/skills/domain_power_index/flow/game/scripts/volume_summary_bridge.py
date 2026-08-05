"""将 game_volume.json 的音量结论并入步骤 12/13 汇总与澄清报告。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_game_volume_doc(analysis_dir: Path) -> dict[str, Any]:
    path = analysis_dir / "game_volume.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _get_path_summary(ctx: dict[str, Any], path: str) -> Any:
    cur: Any = ctx.get("summary") or {}
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def volume_analysis_notes(gv: dict[str, Any]) -> list[str]:
    if not gv:
        return []
    notes: list[str] = []
    inv = gv.get("volume_investigation") or {}
    s1 = inv.get("step1_test_setting") or {}
    s2 = inv.get("step2_in_game_changes") or {}
    if s1.get("volume") is not None:
        line = f"测试前音量={s1['volume']}"
        if s1.get("device_label"):
            line += f" · {s1['device_label']}"
        if s1.get("adjustment_method"):
            line += f" · {s1['adjustment_method']}"
        notes.append(line)
    if s2.get("changed"):
        notes.append(
            f"游戏内变音量 {s2.get('change_count', 0)} 段 "
            f"{s2.get('volume_min')}~{s2.get('volume_max')}"
        )
    elif s2.get("volume_min") is not None:
        notes.append(f"游戏内音量恒定 volume={s2.get('volume_min')}")
    notes.extend(list(gv.get("notes") or []))
    notes.extend(list(inv.get("warnings") or []))
    return notes


def volume_findings_summary(ctx: dict[str, Any]) -> dict[str, Any]:
    """步骤 13 澄清报告用的结构化音量摘要（优先 game_volume.json）。"""
    gv = ctx.get("game_volume") or {}
    vol_stats = _get_path_summary(ctx, "comparison_outputs.volume_stats") or {}

    if not gv and not vol_stats:
        return {"coverage": "missing"}

    pre = gv.get("pre_test_volume") or {}
    baseline = pre.get("baseline") or vol_stats.get("baseline_before_game") or {}
    inv = gv.get("volume_investigation") or {}
    s1 = inv.get("step1_test_setting") or {}
    s2 = inv.get("step2_in_game_changes") or {}
    in_game = gv.get("in_game_volume") or vol_stats.get("game_window") or {}
    max_idx = (
        pre.get("max_index_assumed")
        or in_game.get("max_index_assumed")
        or 15
    )

    route = (gv.get("audio_route") or {}).get("tran_aura_volume_change") or {}
    transitions = in_game.get("transitions") or []
    brief_trans: list[dict[str, Any]] = []
    for tr in transitions[:5]:
        if not isinstance(tr, dict):
            continue
        brief_trans.append(
            {
                "time": tr.get("time"),
                "index_from": tr.get("index_from"),
                "index_to": tr.get("index_to"),
            }
        )

    coverage = pre.get("coverage") or in_game.get("coverage") or vol_stats.get("coverage") or "partial"
    if baseline.get("index") is None and in_game.get("index_min") is None:
        coverage = "missing"

    return {
        "coverage": coverage,
        "pre_test_setting": {
            "index": s1.get("volume") or baseline.get("index"),
            "index_pct": s1.get("volume_pct") or baseline.get("index_pct"),
            "time": s1.get("time") or baseline.get("time"),
            "device_label": s1.get("device_label"),
            "adjustment_method": s1.get("adjustment_method"),
            "max_index": max_idx,
            "raw_evidence": s1.get("raw_evidence") or baseline.get("raw_evidence"),
        },
        "in_game_volume": {
            "stable": s2.get("stable") if s2 else in_game.get("stable"),
            "changed": s2.get("changed") if s2 else in_game.get("changed"),
            "index_min": s2.get("volume_min") if s2 else in_game.get("index_min"),
            "index_max": s2.get("volume_max") if s2 else in_game.get("index_max"),
            "index_min_pct": s2.get("volume_min_pct") if s2 else in_game.get("index_min_pct"),
            "index_max_pct": s2.get("volume_max_pct") if s2 else in_game.get("index_max_pct"),
            "coverage": s2.get("coverage") if s2 else in_game.get("coverage"),
            "transition_count": s2.get("change_count") if s2 else len(transitions),
            "key_press_adjustments": s2.get("key_press_adjustments"),
            "transitions": brief_trans,
        },
        "volume_investigation": inv,
        "audio_route": {
            "dominant_device_label": route.get("dominant_device_label"),
            "device_labels": route.get("device_labels") or [],
        },
        "notes": volume_analysis_notes(gv) if gv else [],
    }
