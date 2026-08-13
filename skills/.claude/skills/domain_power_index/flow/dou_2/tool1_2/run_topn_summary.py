from __future__ import annotations
def _setup_utf8_stdio() -> None:
    import sys
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


import argparse
import json
import sys
from pathlib import Path


def _infer_screen_label(path: Path, explicit: str = "") -> str:
    exp = (explicit or "").strip()
    if exp in ("亮屏", "灭屏"):
        return exp
    low = exp.lower()
    if low in ("on", "screen_on", "screen-on"):
        return "亮屏"
    if low in ("off", "screen_off", "screen-off"):
        return "灭屏"
    parts = [p.lower() for p in path.resolve().parts]
    if "screen_on" in parts:
        return "亮屏"
    if "screen_off" in parts:
        return "灭屏"
    return ""


def _find_topn_json(results_dir: Path) -> Path | None:
    cands = sorted(results_dir.glob("topn_scenes_top*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if cands else None


def _run_one(
    *,
    top_path: Path,
    results_path: Path,
    out_path: Path,
    screen_label: str,
    base_url: str,
    api_key: str,
    model: str,
) -> int:
    if not top_path.is_file():
        print(f"top_scenes_json 不存在：{top_path}", file=sys.stderr)
        return 1
    if not results_path.is_file():
        print(f"results_json 不存在：{results_path}", file=sys.stderr)
        return 1

    top_payload = json.loads(top_path.read_text(encoding="utf-8-sig"))
    results_payload = json.loads(results_path.read_text(encoding="utf-8-sig"))
    label = screen_label or _infer_screen_label(results_path)

    this_dir = Path(__file__).resolve().parent
    scripts_dir = (this_dir / ".." / "scripts").resolve()
    sys.path.insert(0, str(scripts_dir))
    from ai_client import summarize_topn  # noqa: E402

    try:
        ai_reply = summarize_topn(
            top_payload,
            results_payload,
            screen_label=label,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
        summary = {"success": True, "ai_reply": ai_reply}
        success = True
    except Exception as exc:
        summary = {"success": False, "ai_reply": f"TopN 总结失败：{exc}"}
        success = False

    out = {
        "success": success,
        "screen_label": label or "",
        "summary": summary,
        "top_scenes_json": str(top_path),
        "results_json": str(results_path),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出【{label or '未标注'}】总结论：{out_path}")
    return 0 if success else 1


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="DOU 分卷 TopN 总结论（亮屏/灭屏各自一份 topn_summary.json）"
    )
    parser.add_argument("top_scenes_json", nargs="?", default="", help="top_scenes JSON（单分卷模式）")
    parser.add_argument("results_json", nargs="?", default="", help="results_json（单分卷模式）")
    parser.add_argument("--high", default="", help="高功耗根目录；与 --both 联用，对 screen_on/off 各跑一份")
    parser.add_argument(
        "--both",
        action="store_true",
        help="对 <high>/screen_on 与 <high>/screen_off 分别生成总结论（推荐）",
    )
    parser.add_argument("--screen", default="", help="亮屏/灭屏（可从路径推断）")
    parser.add_argument("--output", default="", help="输出 topn_summary.json 路径（单分卷）")
    parser.add_argument("--base-url", default="", help="API Base URL")
    parser.add_argument("--api-key", default="", help="API Key")
    parser.add_argument("--model", default="", help="模型名")
    args = parser.parse_args()

    base_url = str(args.base_url).strip()
    api_key = str(args.api_key).strip()
    model = str(args.model).strip()

    if args.both or str(args.high).strip():
        high = Path(str(args.high).strip()).resolve()
        if not high.is_dir():
            print(f"高功耗目录无效：{high}", file=sys.stderr)
            return 1
        rc = 0
        ran = 0
        for sub, label in (("screen_on", "亮屏"), ("screen_off", "灭屏")):
            d = high / sub
            results_path = d / "results_json.json"
            top_path = _find_topn_json(d)
            if not results_path.is_file() or top_path is None:
                print(f"跳过【{label}】：缺少 {results_path.name} 或 topn_scenes_top*.json（{d}）")
                continue
            code = _run_one(
                top_path=top_path,
                results_path=results_path,
                out_path=d / "topn_summary.json",
                screen_label=label,
                base_url=base_url,
                api_key=api_key,
                model=model,
            )
            ran += 1
            rc = max(rc, code)
        if ran == 0:
            print("未找到可总结的分卷（screen_on / screen_off）", file=sys.stderr)
            return 1
        if ran == 1:
            print(
                "警告：仅生成了 1 个分卷的总结论；亮屏与灭屏应各自有一份 topn_summary.json。",
                file=sys.stderr,
            )
        return rc

    top_arg = str(args.top_scenes_json).strip()
    results_arg = str(args.results_json).strip()
    if not top_arg or not results_arg:
        parser.print_help()
        return 1

    top_path = Path(top_arg).resolve()
    results_path = Path(results_arg).resolve()
    out_path = (
        Path(args.output).resolve()
        if args.output
        else results_path.parent / "topn_summary.json"
    )
    return _run_one(
        top_path=top_path,
        results_path=results_path,
        out_path=out_path,
        screen_label=_infer_screen_label(results_path, args.screen),
        base_url=base_url,
        api_key=api_key,
        model=model,
    )


if __name__ == "__main__":
    raise SystemExit(main())
