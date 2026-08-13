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


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="DOU 场景对比（仅生成 DOU3.0 对比 Excel）")
    parser.add_argument("high", help="高功耗目录")
    parser.add_argument("low", help="低功耗目录")
    parser.add_argument("platform", nargs="?", default="MTK", help="平台：MTK/高通/展锐")
    parser.add_argument("--output", default="", help="输出 JSON 路径")
    args = parser.parse_args()

    high = os.path.abspath(str(args.high).strip())
    low = os.path.abspath(str(args.low).strip())
    platform = str(args.platform).strip() or "MTK"

    if not os.path.isdir(high):
        print(f"高功耗目录不存在：{high}", file=sys.stderr)
        return 1
    if not os.path.isdir(low):
        print(f"低功耗目录不存在：{low}", file=sys.stderr)
        return 1

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
        print(result.get("message", "场景对比失败"), file=sys.stderr)
        return 1

    scene_excel_path = getattr(app_state, "scene_excel_path", "") or ""
    out = {
        "success": True,
        "high": high,
        "low": low,
        "platform": platform,
        "scene_excel_path": scene_excel_path,
        "scene1_excel_path": getattr(app_state, "scene1_excel_path", ""),
        "scene2_excel_path": getattr(app_state, "scene2_excel_path", ""),
    }

    out_path = Path(args.output).resolve() if args.output else Path(high) / "scene_compare_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出：{out_path}")

    from utils import apply_auto_error_ignorable_rules  # noqa: E402

    auto_info = apply_auto_error_ignorable_rules(high, low)
    error_scenes = auto_info.get("error_scenes") or []
    if error_scenes:
        names = ", ".join(str(sc.get("name") or "") for sc in error_scenes[:8])
        suffix = " ..." if len(error_scenes) > 8 else ""
        print(
            f"已从 testReport error 场景临时写入 ignorable_scenes.json："
            f"{auto_info.get('added', 0)} 条（{names}{suffix}；run_final_html 结束后自动清除）"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
