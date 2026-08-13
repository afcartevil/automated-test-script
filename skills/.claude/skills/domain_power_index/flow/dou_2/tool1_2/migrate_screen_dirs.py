"""将根目录 TopN/CPU/AI 产物按亮灭屏迁入 screen_on、screen_off。"""
from __future__ import annotations
def _setup_utf8_stdio() -> None:
    import sys
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


import argparse
import json
import shutil
import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = (THIS_DIR / ".." / "scripts").resolve()
sys.path.insert(0, str(SCRIPTS_DIR))

from utils import SCREEN_OFF_SUBDIR, SCREEN_ON_SUBDIR, scene_screen_label  # noqa: E402


def _bucket(desc: str, name: str) -> str:
    return SCREEN_OFF_SUBDIR if scene_screen_label(desc, name) == "灭屏" else SCREEN_ON_SUBDIR


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="迁移 DOU 产物到亮/灭屏子目录")
    parser.add_argument("high", help="高功耗目录")
    parser.add_argument("--dry-run", action="store_true", help="仅打印，不移动")
    args = parser.parse_args()

    high = Path(args.high).resolve()
    if not high.is_dir():
        print(f"目录不存在：{high}", file=sys.stderr)
        return 1

    suffix_map: dict[str, str] = {}
    topn_files = sorted(high.glob("topn_scenes_top*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if topn_files:
        data = json.loads(topn_files[0].read_text(encoding="utf-8"))
        rows = data.get("top_scenes") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            rows = []
        for sc in rows:
            suf = str(sc.get("suffix", "")).strip()
            if suf:
                suffix_map[suf] = _bucket(str(sc.get("desc", "")), str(sc.get("name", "")))

    for p in high.glob("cpu_analysis_*.json"):
        suf = p.stem.replace("cpu_analysis_", "", 1)
        if not suf or suf in suffix_map:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            cd = d.get("cpu_data") or {}
            suffix_map[suf] = _bucket(str(cd.get("scene_desc", "")), "")
        except Exception:
            suffix_map[suf] = SCREEN_ON_SUBDIR

    if not suffix_map:
        print("未找到可分类的 cpu_analysis_*.json 或 topn_scenes_top*.json", file=sys.stderr)
        return 1

    for suf, sub in suffix_map.items():
        dest = high / sub
        if not args.dry_run:
            dest.mkdir(parents=True, exist_ok=True)
        for pat in (f"cpu_analysis_{suf}.json", f"ai_analysis_{suf}.json"):
            src = high / pat
            if src.is_file():
                tgt = dest / pat
                print(f"{'[dry] ' if args.dry_run else ''}move {src.name} -> {sub}/")
                if not args.dry_run:
                    shutil.move(str(src), str(tgt))

    if topn_files:
        data = json.loads(topn_files[0].read_text(encoding="utf-8"))
        for sub, bucket, label in (
            (SCREEN_ON_SUBDIR, "on", "亮屏"),
            (SCREEN_OFF_SUBDIR, "off", "灭屏"),
        ):
            dest = high / sub
            if not args.dry_run:
                dest.mkdir(parents=True, exist_ok=True)
            sufs = {s for s, b in suffix_map.items() if b == sub}
            top = [
                sc
                for sc in (data.get("top_scenes") or [])
                if str(sc.get("suffix", "")).strip() in sufs
            ]
            out = dest / topn_files[0].name
            payload = {
                **data,
                "top_scenes": top,
                "screen_bucket": bucket,
                "screen_label": label,
                "results_dir": str(dest),
            }
            print(f"{'[dry] ' if args.dry_run else ''}write {out.relative_to(high)} ({len(top)} scenes)")
            if not args.dry_run:
                out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        "note: results_json.json / topn_summary.json 需在各分卷目录分别 run_collect_results 与 TopN 总结"
    )
    print(f"done: {len(suffix_map)} suffixes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
