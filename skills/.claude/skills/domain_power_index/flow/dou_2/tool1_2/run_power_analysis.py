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
    parser = argparse.ArgumentParser(description="DOU 功耗分析（Modem/Wi-Fi）")
    parser.add_argument("high", help="高功耗目录")
    parser.add_argument("low", nargs="?", default="", help="低功耗目录（不填则单目录模式）")
    parser.add_argument("--output", default="", help="输出 JSON 路径")
    args = parser.parse_args()

    high = os.path.abspath(str(args.high).strip())
    low = os.path.abspath(str(args.low).strip()) if str(args.low).strip() else high

    if not os.path.isdir(high):
        print(f"目录不存在：{high}", file=sys.stderr)
        return 1
    if not os.path.isdir(low):
        print(f"目录不存在：{low}", file=sys.stderr)
        return 1

    this_dir = Path(__file__).resolve().parent
    scripts_dir = (this_dir / ".." / "scripts").resolve()
    sys.path.insert(0, str(scripts_dir))
    from power_analysis import HighPowerAnalyzer  # noqa: E402

    hpa = HighPowerAnalyzer()
    hpa.set_folders(high, low)
    result = hpa.analyze_high_power_scenario()

    out = {
        "success": bool(result.get("success")),
        "high": high,
        "low": low,
        "single_folder_mode": high == low,
        "result": result,
    }

    out_path = Path(args.output).resolve() if args.output else Path(high) / "power_analysis_result.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出：{out_path}")
    return 0 if out["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
