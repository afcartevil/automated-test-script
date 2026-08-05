"""DOU 长待机场景 → flow_power_standby_long_dou 桥接（pt5 + kernel + AI → standby_analysis_*.json）。"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd

_POWER_BASE = Path(__file__).resolve().parents[3] / "base"
_PT5_SCRIPT = _POWER_BASE / "standby_pt5" / "scripts" / "base_pt5.py"
_KERNEL_SCRIPT = _POWER_BASE / "kernel_standby" / "scripts" / "wakeup_source.py"

DEFAULT_STANDBY_TYPE = "WIFI"
DEFAULT_THRESHOLD_MA = 25
DATA_THRESHOLD_MA = 30
LONG_STANDBY_MIN_DURATION_SEC = 30 * 60


def _import_dou_utils():
    scripts = Path(__file__).resolve().parent
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from pt5_reader import find_pt5_for_suffix
    from utils import extract_suffix, find_test_report, is_screen_off_scene

    return find_pt5_for_suffix, find_test_report, extract_suffix, is_screen_off_scene


def is_long_standby_scene(
    desc: str = "",
    name: str = "",
    *,
    duration_sec: float | None = None,
) -> bool:
    """判定 DOU 长待机场景（灭屏 + 待机语义 / 足够时长）。"""
    _, _, _, is_screen_off_scene = _import_dou_utils()
    if not is_screen_off_scene(desc, name):
        return False
    text = f"{desc}\n{name}"
    low = text.lower()
    keywords = (
        "长待机",
        "待机",
        "standby",
        "overnight",
        "灭屏待机",
        "sleep",
        "screen off standby",
    )
    has_kw = any(k in text or k in low for k in keywords)
    try:
        dur = float(duration_sec) if duration_sec is not None else None
    except (TypeError, ValueError):
        dur = None
    if dur is not None and dur >= 3600:
        return True
    if has_kw and dur is not None and dur >= LONG_STANDBY_MIN_DURATION_SEC:
        return True
    if has_kw and dur is None:
        return True
    return False


def load_scene_row(high_dir: str, suffix: str) -> dict[str, Any] | None:
    find_pt5_for_suffix, find_test_report, extract_suffix, _ = _import_dou_utils()
    report = find_test_report(high_dir)
    if not report:
        return None
    df = pd.read_excel(
        report,
        sheet_name="report",
        usecols=["name", "desc", "starttime", "endtime", "duration_sec"],
    )
    suf = str(suffix).strip().lstrip("_")
    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if extract_suffix(name) == suf or name.endswith(f"_{suf}"):
            st = pd.to_datetime(row.get("starttime"))
            en = pd.to_datetime(row.get("endtime"))
            dur = row.get("duration_sec")
            if pd.isna(dur) or not dur:
                dur = (en - st).total_seconds()
            return {
                "name": name,
                "desc": str(row.get("desc", "") or ""),
                "starttime": st.strftime("%Y-%m-%d %H:%M:%S"),
                "endtime": en.strftime("%Y-%m-%d %H:%M:%S"),
                "duration_sec": float(dur),
            }
    return None


def resolve_platform(high_dir: str) -> str:
    for name in ("scene_compare_result.json", "dou_prepare_result.json"):
        path = os.path.join(high_dir, name)
        if not os.path.isfile(path):
            continue
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            plat = str(payload.get("platform") or payload.get("scene1_platform") or "").strip()
            if plat:
                up = plat.upper()
                if "QCOM" in up or "高通" in plat:
                    return "QCOM"
                return "MTK"
        except Exception:
            pass
    return "MTK"


def find_aplog_dir(high_dir: str) -> str | None:
    phone_logs = os.path.join(high_dir, "phone_logs")
    if not os.path.isdir(phone_logs):
        return None
    best: str | None = None
    for root, _dirs, files in os.walk(phone_logs):
        base = os.path.basename(root)
        if base in ("APLog", "aplog", "APLOG"):
            return root
        if any("linli_666" in f or f.endswith("_666.txt") for f in files):
            best = root
    return best


def resolve_standby_type(desc: str = "", explicit: str = "") -> tuple[str, float]:
    exp = str(explicit or "").strip().upper()
    if exp == "DATA":
        return "DATA", float(DATA_THRESHOLD_MA)
    text = f"{desc}".lower()
    if "mobile data" in text and "wifi off" in text:
        return "DATA", float(DATA_THRESHOLD_MA)
    return DEFAULT_STANDBY_TYPE, float(DEFAULT_THRESHOLD_MA)


def _run_json_script(script: Path, args: list[str], *, timeout: int = 600) -> dict[str, Any]:
    if not script.is_file():
        return {"success": False, "error": f"缺少脚本：{script}"}
    cmd = [sys.executable, str(script), *args]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"超时：{script.name}"}
    out = (proc.stdout or "").strip()
    if not out:
        return {"success": False, "error": (proc.stderr or "无输出").strip()}
    try:
        payload = json.loads(out)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass
    if proc.returncode != 0:
        return {"success": False, "error": out or proc.stderr or f"exit {proc.returncode}"}
    return {"success": True, "raw": out}


def analyze_pt5_standby(pt5_path: str) -> dict[str, Any]:
    return _run_json_script(
        _PT5_SCRIPT,
        [pt5_path, "--tool", "standby", "--format", "json"],
        timeout=300,
    )


def analyze_kernel_window(log_dir: str, t0: str, t1: str) -> dict[str, Any]:
    return _run_json_script(
        _KERNEL_SCRIPT,
        ["-d", log_dir, "-t", t0, t1, "--format", "json"],
        timeout=300,
    )


def build_standby_context(
    *,
    scene_row: dict[str, Any],
    suffix: str,
    high_dir: str,
    pt5_path: str,
    pt5_result: dict[str, Any],
    kernel_full: dict[str, Any] | None,
    kernel_max: dict[str, Any] | None,
    kernel_min: dict[str, Any] | None,
    standby_type: str,
    threshold_ma: float,
    platform: str,
) -> dict[str, Any]:
    pt5_ok = bool(pt5_result.get("success"))
    ctx: dict[str, Any] = {
        "flow": "flow_power_standby_long_dou",
        "suffix": suffix,
        "scene_desc": scene_row.get("desc") or "",
        "scene_name": scene_row.get("name") or "",
        "sleep_time_start": scene_row.get("starttime"),
        "sleep_time_end": scene_row.get("endtime"),
        "duration_sec": scene_row.get("duration_sec"),
        "pt5_path": pt5_path,
        "standby_type": standby_type,
        "threshold_ma": threshold_ma,
        "platform": platform,
        "pt5_ok": pt5_ok,
        "power_window_source": "pt5" if pt5_ok else "full_window",
        "pt5": pt5_result if pt5_ok else {"success": False, "error": pt5_result.get("error")},
        "kernel_full_window": kernel_full or {},
        "kernel_max_window": kernel_max or {},
        "kernel_min_window": kernel_min or {},
    }
    if pt5_ok:
        ctx["stdby_curr_ma"] = pt5_result.get("stdby_curr_ma")
        ctx["min_power_window"] = {
            "start": pt5_result.get("min_power_time_start"),
            "end": pt5_result.get("min_power_time_end"),
            "value_ma": pt5_result.get("min_power_value"),
        }
        ctx["max_power_window"] = {
            "start": pt5_result.get("max_power_time_start"),
            "end": pt5_result.get("max_power_time_end"),
            "value_ma": pt5_result.get("max_power_value"),
        }
    else:
        ctx["stdby_curr_ma"] = None
        ctx["attribution_hint"] = "单窗降级（pt5 失败，整段用户时间窗）"
    return ctx


def run_standby_analysis_for_scene(
    high_dir: str,
    suffix: str,
    *,
    results_dir: str = "",
    standby_type: str = "",
    force: bool = False,
    with_ai: bool = True,
    base_url: str = "",
    api_key: str = "",
    model: str = "",
) -> dict[str, Any]:
    """对单场景执行 standby_long_dou 并落盘 standby_analysis_<suffix>.json。"""
    suf = str(suffix).strip().lstrip("_")
    out_dir = os.path.abspath(results_dir or high_dir)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"standby_analysis_{suf}.json")
    if os.path.isfile(out_path) and not force:
        try:
            cached = json.loads(Path(out_path).read_text(encoding="utf-8"))
            if cached.get("standby_result", {}).get("ai_reply"):
                return cached
        except Exception:
            pass

    scene_row = load_scene_row(high_dir, suf)
    if not scene_row:
        return {"success": False, "suffix": suf, "error": f"testReport 无场景 {suf}"}

    if not is_long_standby_scene(
        scene_row.get("desc", ""),
        scene_row.get("name", ""),
        duration_sec=scene_row.get("duration_sec"),
    ):
        return {
            "success": False,
            "suffix": suf,
            "skipped": True,
            "error": "非长待机场景（需灭屏 + 待机语义或时长≥30min）",
        }

    find_pt5_for_suffix, _, _, _ = _import_dou_utils()
    meta = os.path.join(high_dir, "meta_report")
    pt5_path = find_pt5_for_suffix(meta, suf) if os.path.isdir(meta) else None
    if not pt5_path:
        return {"success": False, "suffix": suf, "error": f"meta_report 未找到场景 {suf} 的 pt5"}

    stype, threshold = resolve_standby_type(scene_row.get("desc", ""), standby_type)
    platform = resolve_platform(high_dir)
    t0 = scene_row["starttime"]
    t1 = scene_row["endtime"]

    pt5_result = analyze_pt5_standby(pt5_path)
    aplog = find_aplog_dir(high_dir)
    kernel_full = kernel_max = kernel_min = None
    if aplog:
        kernel_full = analyze_kernel_window(aplog, t0, t1)
        if pt5_result.get("success"):
            max_s = pt5_result.get("max_power_time_start")
            max_e = pt5_result.get("max_power_time_end")
            min_s = pt5_result.get("min_power_time_start")
            min_e = pt5_result.get("min_power_time_end")
            if max_s and max_e and re.match(r"\d{4}-\d{2}-\d{2}", str(max_s)):
                kernel_max = analyze_kernel_window(aplog, str(max_s), str(max_e))
            if min_s and min_e and re.match(r"\d{4}-\d{2}-\d{2}", str(min_s)):
                kernel_min = analyze_kernel_window(aplog, str(min_s), str(min_e))

    ctx = build_standby_context(
        scene_row=scene_row,
        suffix=suf,
        high_dir=high_dir,
        pt5_path=pt5_path,
        pt5_result=pt5_result,
        kernel_full=kernel_full,
        kernel_max=kernel_max,
        kernel_min=kernel_min,
        standby_type=stype,
        threshold_ma=threshold,
        platform=platform,
    )

    standby_result: dict[str, Any] = {"success": False, "ai_reply": ""}
    if with_ai:
        from ai_client import analyze_standby_dou_json, load_ai_config

        cfg = load_ai_config()
        kw = {
            "base_url": base_url or cfg.get("base_url") or "",
            "api_key": api_key or cfg.get("api_key") or "",
            "model": model or cfg.get("model") or "",
        }
        try:
            reply = analyze_standby_dou_json(ctx, **kw)
            standby_result = {"success": True, "ai_reply": reply}
        except Exception as exc:
            standby_result = {"success": False, "ai_reply": f"长待机 AI 分析失败：{exc}"}
    else:
        standby_result = {
            "success": bool(pt5_result.get("success")),
            "ai_reply": json.dumps(ctx, ensure_ascii=False, indent=2),
        }

    payload = {
        "success": standby_result.get("success", False),
        "suffix": suf,
        "is_long_standby": True,
        "standby_type": stype,
        "threshold_ma": threshold,
        "ai_mode": "standby_long_dou",
        "scene_desc": scene_row.get("desc") or "",
        "sleep_time_start": t0,
        "sleep_time_end": t1,
        "pt5_path": pt5_path,
        "pt5_ok": bool(pt5_result.get("success")),
        "power_window_source": ctx.get("power_window_source"),
        "context": ctx,
        "standby_result": standby_result,
    }
    Path(out_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    payload["path"] = out_path
    return payload


def scan_long_standby_from_topn(top_scenes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sc in top_scenes or []:
        if not isinstance(sc, dict):
            continue
        suf = str(sc.get("suffix") or "").strip().lstrip("_")
        if not suf:
            continue
        if is_long_standby_scene(sc.get("desc", ""), sc.get("name", "")):
            out.append(sc)
    return out
