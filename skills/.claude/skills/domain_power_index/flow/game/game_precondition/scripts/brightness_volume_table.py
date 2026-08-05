"""按飞书「亮度和音量表」解析项目×测试用例的亮度/音量设定。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from skill_references import load_reference_yaml

_TEST_CASE_ALIASES = {
    "basic": "basic",
    "基础": "basic",
    "基础场景": "basic",
    "350nit": "basic",
    "nps": "nps",
    "NPS": "nps",
    "nps场景": "nps",
    "NPS场景": "nps",
    "最大亮度": "nps",
    "最大亮度场景": "nps",
}


def normalize_test_case(raw: str | None, default: str = "basic") -> str:
    text = (raw or "").strip()
    if not text:
        return default
    return _TEST_CASE_ALIASES.get(text, _TEST_CASE_ALIASES.get(text.lower(), text.lower()))


def load_brightness_volume_table(ref_dir: Path) -> dict[str, Any]:
    return load_reference_yaml(ref_dir, "brightness-volume-by-project.yaml")


def resolve_project_entry(
    table: dict[str, Any],
    project: str | None,
) -> tuple[str | None, dict[str, Any] | None]:
    """按项目名或 aliases 匹配表项，返回 (canonical_id, entry)。"""
    projects = table.get("projects") or {}
    if not isinstance(projects, dict) or not projects:
        return None, None
    key = (project or "").strip()
    if not key:
        return None, None
    if key in projects and isinstance(projects[key], dict):
        return key, dict(projects[key])
    key_l = key.lower()
    for pid, entry in projects.items():
        if not isinstance(entry, dict):
            continue
        if str(pid).lower() == key_l:
            return str(pid), dict(entry)
        aliases = entry.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [aliases]
        for alias in aliases:
            if str(alias).strip().lower() == key_l:
                return str(pid), dict(entry)
    return None, None


def _to_int(raw: Any) -> int | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            return None


def _to_float(raw: Any) -> float | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def lookup_setting(
    ref_dir: Path,
    *,
    project: str | None,
    test_case: str | None = None,
) -> dict[str, Any]:
    """查表得到目标设定。

    basic：brightness_level（等级比对）+ volume_index
    nps（最大亮度）：优先 level(0-255) → 曲线(0-4095) → brightness_nits；
    表内可配 brightness_level / brightness_nits + volume_index
    """
    table = load_brightness_volume_table(ref_dir)
    default_case = str(table.get("default_test_case") or "basic")
    case = normalize_test_case(test_case, default=default_case)
    phys = table.get("physical_standard") or {}
    pid, entry = resolve_project_entry(table, project)

    case_block: dict[str, Any] = {}
    if entry:
        raw = entry.get(case)
        if isinstance(raw, dict):
            case_block = dict(raw)

    brightness_level = _to_int(case_block.get("brightness_level"))
    brightness_nits = _to_float(case_block.get("brightness_nits"))
    volume_index = _to_int(case_block.get("volume_index"))

    # 未配置或无效占位
    if brightness_level is not None and brightness_level <= 0:
        brightness_level = None
    if brightness_nits is not None and brightness_nits <= 0:
        brightness_nits = None
    if volume_index is not None and volume_index < 0:
        volume_index = None

    compare_mode = "nits" if case == "nps" else "level"
    if case == "basic":
        test_case_label = "基础场景"
        column_hint = "350nit / 72dB"
    elif case == "nps":
        test_case_label = "NPS场景"
        column_hint = "最大亮度 / 最大音量"
    else:
        test_case_label = case
        column_hint = case

    return {
        "source_url": table.get("source_url") or "",
        "physical_standard": {
            "brightness_nits": phys.get("brightness_nits", 350),
            "volume_db": phys.get("volume_db", 72),
        },
        "project": pid,
        "project_requested": (project or "").strip() or None,
        "project_matched": pid is not None,
        "test_case": case,
        "test_case_label": test_case_label,
        "column_hint": column_hint,
        "compare_mode": compare_mode,
        "brightness_level": brightness_level,
        "brightness_nits": brightness_nits,
        "volume_index": volume_index,
        "known_projects": sorted(str(k) for k in (table.get("projects") or {}).keys()),
    }


def compare_level(measured: int | None, expected: int | None, tolerance: int = 0) -> str:
    if expected is None or measured is None:
        return "unknown"
    if abs(int(measured) - int(expected)) <= max(0, int(tolerance)):
        return "ok"
    return "bad"


def compare_nits(measured: float | None, expected: float | None, tolerance: float = 20.0) -> str:
    if expected is None or measured is None:
        return "unknown"
    if abs(float(measured) - float(expected)) <= max(0.0, float(tolerance)):
        return "ok"
    return "bad"
