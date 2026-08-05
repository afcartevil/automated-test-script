from __future__ import annotations
def _setup_utf8_stdio() -> None:
    import sys
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


import argparse
import json
import os
import sys
from pathlib import Path


def _ensure_scene_excel(high: str, low: str, platform: str, scene_excel: str) -> str:
    if scene_excel and os.path.exists(scene_excel):
        return os.path.abspath(scene_excel)

    this_dir = Path(__file__).resolve().parent
    scripts_dir = (this_dir / ".." / "scripts").resolve()
    sys.path.insert(0, str(scripts_dir))
    from folder_select import FolderSelector  # noqa: E402

    class _AppState:
        pass

    app_state = _AppState()
    app_state.scene1_folder = high
    app_state.scene2_folder = low
    app_state.scene1_platform = platform
    app_state.scene2_platform = platform
    app_state.root_folder = high
    app_state.scene_excel_path = ""
    app_state.scene1_excel_path = ""
    app_state.scene2_excel_path = ""
    app_state.scene1_log_files = []
    app_state.scene2_log_files = []

    fs = FolderSelector(app_state)
    result = fs.execute_scene_comparison()
    if not result.get("success"):
        raise RuntimeError(result.get("message", "场景对比失败"))
    return str(getattr(app_state, "scene_excel_path", "") or "")


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="DOU CPU 独立分析")
    parser.add_argument("high", help="高功耗目录")
    parser.add_argument("low", help="低功耗目录")
    parser.add_argument("platform", nargs="?", default="MTK", help="平台：MTK/高通/展锐")
    parser.add_argument("suffix", help="场景后缀（如 3796）")
    parser.add_argument("--scene-excel", default="", help="DOU3.0 对比 Excel 路径，不填则自动先做场景对比")
    parser.add_argument("--output", default="", help="输出 JSON 路径")
    parser.add_argument(
        "--results-dir",
        default="",
        help="亮/灭屏产物目录（如 <high>/screen_on）；也可用 --screen 亮屏/灭屏 自动解析",
    )
    parser.add_argument("--screen", default="", help="亮屏/灭屏（或 on/off），与 --results-dir 二选一")
    args = parser.parse_args()

    high = os.path.abspath(str(args.high).strip())
    low = os.path.abspath(str(args.low).strip())
    platform = str(args.platform).strip() or "MTK"
    suffix = str(args.suffix).strip().lstrip("_")

    if not os.path.isdir(high):
        print(f"高功耗目录不存在：{high}", file=sys.stderr)
        return 1
    if not os.path.isdir(low):
        print(f"低功耗目录不存在：{low}", file=sys.stderr)
        return 1
    if not suffix:
        print("suffix 不能为空", file=sys.stderr)
        return 1

    this_dir = Path(__file__).resolve().parent
    scripts_dir = (this_dir / ".." / "scripts").resolve()
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from cpu_analyzer import CPULogAnalyzer  # noqa: E402
    from utils import norm_screen_bucket, screen_results_dir  # noqa: E402

    results_dir = str(args.results_dir).strip()
    screen_raw = str(args.screen).strip()
    if not results_dir and screen_raw:
        bucket = norm_screen_bucket(screen_raw)
        if not bucket:
            print(f"不支持的 screen 参数：{screen_raw}", file=sys.stderr)
            return 1
        results_dir = screen_results_dir(high, screen_raw)
    elif results_dir:
        results_dir = os.path.abspath(results_dir)
        os.makedirs(results_dir, exist_ok=True)
    else:
        results_dir = high

    scene_excel_path = _ensure_scene_excel(high, low, platform, str(args.scene_excel).strip())
    if not scene_excel_path or not os.path.exists(scene_excel_path):
        print("无法获得有效 scene_excel_path", file=sys.stderr)
        return 1

    analyzer = CPULogAnalyzer(
        scene1_folder=high,
        scene2_folder=low,
        scene1_platform=platform,
        scene2_platform=platform,
        scene_excel_path=scene_excel_path,
    )
    result = analyzer.analyze(suffix)

    out = {
        "success": True,
        "high": high,
        "low": low,
        "platform": platform,
        "suffix": suffix,
        "scene_excel_path": scene_excel_path,
        "cpu_data": result,
    }

    out_path = (
        Path(args.output).resolve()
        if args.output
        else Path(results_dir) / f"cpu_analysis_{suffix}.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
