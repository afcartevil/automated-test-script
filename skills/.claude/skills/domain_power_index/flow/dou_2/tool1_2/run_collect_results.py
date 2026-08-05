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
    parser = argparse.ArgumentParser(description="组装 topn-results.json（CPU JSON + AI JSON -> results_json）")
    parser.add_argument("top_scenes_json", help="由 run_topn_select.py 输出的 top_scenes_json")
    parser.add_argument("--cpu-dir", required=True, help="CPU JSON 所在目录（默认文件名 cpu_analysis_<suffix>.json）")
    parser.add_argument("--ai-dir", required=True, help="AI JSON 所在目录（默认文件名 ai_analysis_<suffix>.json）")
    parser.add_argument("--cpu-pattern", default="cpu_analysis_{suffix}.json", help="CPU 文件名模式")
    parser.add_argument("--ai-pattern", default="ai_analysis_{suffix}.json", help="AI 文件名模式")
    parser.add_argument("--output", default="", help="输出 results_json 路径（默认 cpu-dir/results_json.json）")
    args = parser.parse_args()

    top_scenes_path = Path(str(args.top_scenes_json).strip()).resolve()
    if not top_scenes_path.exists():
        print(f"top_scenes_json 不存在：{top_scenes_path}", file=sys.stderr)
        return 1

    cpu_dir = Path(str(args.cpu_dir).strip()).resolve()
    ai_dir = Path(str(args.ai_dir).strip()).resolve()
    if not cpu_dir.exists():
        print(f"cpu-dir 不存在：{cpu_dir}", file=sys.stderr)
        return 1
    if not ai_dir.exists():
        print(f"ai-dir 不存在：{ai_dir}", file=sys.stderr)
        return 1

    cpu_pattern = str(args.cpu_pattern)
    ai_pattern = str(args.ai_pattern)

    this_dir = Path(__file__).resolve().parent
    scripts_dir = (this_dir / ".." / "scripts").resolve()
    sys.path.insert(0, str(scripts_dir))
    from utils import parse_top_scenes_json  # noqa: E402

    payload = json.loads(top_scenes_path.read_text(encoding="utf-8"))
    top_scenes, ignored_scenes, _ = parse_top_scenes_json(payload)
    if not top_scenes:
        print("top_scenes_json 格式错误：无 top_scenes", file=sys.stderr)
        return 1
    if ignored_scenes:
        print(f"提示：{len(ignored_scenes)} 个可忽略场景未纳入 results_json（见 ignored_scenes）")

    results: dict[str, dict] = {}
    for sc in top_scenes:
        suf = str(sc.get("suffix", "")).strip()
        if not suf:
            continue
        cpu_path = cpu_dir / cpu_pattern.format(suffix=suf)
        ai_path = ai_dir / ai_pattern.format(suffix=suf)
        if not cpu_path.exists():
            print(f"缺少 CPU JSON：{cpu_path}", file=sys.stderr)
            return 1
        if not ai_path.exists():
            print(f"缺少 AI JSON：{ai_path}", file=sys.stderr)
            return 1

        cpu_payload = json.loads(cpu_path.read_text(encoding="utf-8"))
        ai_payload = json.loads(ai_path.read_text(encoding="utf-8"))
        cpu_data = cpu_payload.get("cpu_data")
        ai_result = ai_payload.get("ai_result")
        if cpu_data is None or ai_result is None:
            print(f"JSON 内容缺失：suffix={suf}", file=sys.stderr)
            return 1

        power_mah = sc.get("power_mah", ai_payload.get("power_difference_mAh", 0.0))
        try:
            power_mah = float(power_mah)
        except Exception:
            power_mah = 0.0

        results[suf] = {
            "cpu_data": cpu_data,
            "ai_result": ai_result,
            "power_difference_mAh": power_mah,
        }

        standby_path = ai_dir / f"standby_analysis_{suf}.json"
        if standby_path.exists():
            standby_payload = json.loads(standby_path.read_text(encoding="utf-8"))
            standby_result = standby_payload.get("standby_result")
            if isinstance(standby_result, dict):
                results[suf]["standby_result"] = standby_result
                results[suf]["is_long_standby"] = bool(
                    standby_payload.get("is_long_standby", True)
                )
                if standby_payload.get("standby_type"):
                    results[suf]["standby_type"] = standby_payload.get("standby_type")

    out_path = (
        Path(args.output).resolve()
        if str(args.output).strip()
        else cpu_dir / "results_json.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

