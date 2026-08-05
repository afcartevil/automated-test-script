"""DOU 长待机分析：调用 flow_power_standby_long_dou 桥接，落盘 standby_analysis_*.json。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts"


def _load_top_scenes(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return list(data.get("top_scenes") or [])
    return []


def main() -> int:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="DOU 长待机分析（standby_long_dou）")
    ap.add_argument("high", help="高功耗项目目录")
    ap.add_argument("--suffix", default="", help="单场景 suffix")
    ap.add_argument("--top-scenes", default="", help="topn_scenes JSON，批量扫描长待机")
    ap.add_argument(
        "--results-dir",
        default="",
        help="落盘目录（默认 high；灭屏 TopN 建议 <high>/screen_off）",
    )
    ap.add_argument("--screen", default="", help="亮屏/灭屏，自动解析 results-dir")
    ap.add_argument("--standby-type", default="", choices=("", "WIFI", "DATA"))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-ai", action="store_true", help="仅收集 pt5/kernel 上下文，不调 AI")
    ap.add_argument("--base-url", default="")
    ap.add_argument("--api-key", default="")
    ap.add_argument("--model", default="")
    args = ap.parse_args()

    high = Path(str(args.high).strip()).resolve()
    if not high.is_dir():
        print(f"目录不存在：{high}", file=sys.stderr)
        return 1

    sys.path.insert(0, str(_scripts_dir()))
    from dou_standby_long import (  # noqa: E402
        is_long_standby_scene,
        load_scene_row,
        run_standby_analysis_for_scene,
        scan_long_standby_from_topn,
    )
    from utils import norm_screen_bucket, screen_results_dir  # noqa: E402

    results_dir = str(args.results_dir).strip()
    if not results_dir and args.screen:
        bucket = norm_screen_bucket(args.screen)
        if bucket:
            results_dir = screen_results_dir(str(high), args.screen)
    if not results_dir:
        results_dir = str(high)
    results_dir = str(Path(results_dir).resolve())

    kw = {
        "results_dir": results_dir,
        "standby_type": args.standby_type,
        "force": args.force,
        "with_ai": not args.no_ai,
        "base_url": args.base_url,
        "api_key": args.api_key,
        "model": args.model,
    }

    suffixes: list[str] = []
    if args.suffix:
        suffixes = [str(args.suffix).strip().lstrip("_")]
    elif args.top_scenes:
        top_path = Path(str(args.top_scenes).strip()).resolve()
        if not top_path.is_file():
            print(f"top-scenes 不存在：{top_path}", file=sys.stderr)
            return 1
        scenes = scan_long_standby_from_topn(_load_top_scenes(top_path))
        if not scenes:
            for sc in _load_top_scenes(top_path):
                suf = str(sc.get("suffix") or "").strip().lstrip("_")
                if not suf:
                    continue
                row = load_scene_row(str(high), suf)
                if row and is_long_standby_scene(
                    row.get("desc", ""),
                    row.get("name", ""),
                    duration_sec=row.get("duration_sec"),
                ):
                    scenes.append(sc)
        suffixes = [str(s.get("suffix")).strip().lstrip("_") for s in scenes if s.get("suffix")]
        print(f"长待机候选场景：{len(suffixes)}")
    else:
        ap.print_help()
        return 1

    rc = 0
    for suf in suffixes:
        if not suf:
            continue
        result = run_standby_analysis_for_scene(str(high), suf, **kw)
        if result.get("skipped"):
            print(f"[SKIP] {suf}: {result.get('error')}")
            continue
        if not result.get("success") and not (result.get("standby_result") or {}).get("success"):
            print(f"[FAIL] {suf}: {result.get('error')}", file=sys.stderr)
            rc = 1
            continue
        print(f"[OK] {suf} -> {result.get('path', '')}")
        ai = (result.get("standby_result") or {}).get("ai_reply") or ""
        if ai:
            print(ai[:500] + ("…" if len(ai) > 500 else ""))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
