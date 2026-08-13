"""电流图(pt5)与已有 CPU 分析结合：找出高低版本底电差异大的时段。

工作区根解析见 analysis/base/lib/repo_paths.py。
"""
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


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts"


def _resolve_low(high: str, low: str) -> str:
    low = str(low or "").strip()
    if low and os.path.isdir(low):
        return os.path.abspath(low)
    prep = os.path.join(high, "dou_prepare_result.json")
    if os.path.isfile(prep):
        data = json.load(open(prep, encoding="utf-8"))
        p = str(data.get("low") or "").strip()
        if p and os.path.isdir(p):
            return os.path.abspath(p)
    scene = os.path.join(high, "scene_compare_result.json")
    if os.path.isfile(scene):
        data = json.load(open(scene, encoding="utf-8"))
        p = str(data.get("low") or "").strip()
        if p and os.path.isdir(p):
            return os.path.abspath(p)
    raise RuntimeError("未指定低功耗目录，且 high 下无 dou_prepare/scene_compare 中的 low 路径")


def _resolve_results_dir(high: str, results_dir: str, screen: str) -> str:
    if results_dir:
        return os.path.abspath(results_dir)
    screen = str(screen or "").strip().lower()
    if screen in ("亮屏", "on", "screen_on"):
        return os.path.join(high, "screen_on")
    if screen in ("灭屏", "off", "screen_off"):
        return os.path.join(high, "screen_off")
    return high


def _load_suffixes(top_scenes_path: str) -> list[str]:
    data = json.load(open(top_scenes_path, encoding="utf-8"))
    if isinstance(data, list):
        scenes = data
    elif isinstance(data, dict):
        scenes = data.get("top_scenes") or []
    else:
        scenes = []
    out: list[str] = []
    for sc in scenes:
        suf = str(sc.get("suffix") or "").strip().lstrip("_")
        if suf:
            out.append(suf)
    return out


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="电流图(pt5)与已有 CPU JSON 结合分析（不重新跑 CPU）"
    )
    parser.add_argument("high", help="高功耗目录")
    parser.add_argument("low", nargs="?", default="", help="低功耗目录（可省略，从 scene_compare 读取）")
    parser.add_argument("--suffix", default="", help="单场景后缀")
    parser.add_argument("--top-scenes", default="", help="TopN JSON，批量分析")
    parser.add_argument("--cpu-dir", default="", help="cpu_analysis_*.json 所在目录")
    parser.add_argument("--screen", default="", help="亮屏/灭屏，自动解析 cpu-dir")
    parser.add_argument("--output", default="", help="单场景输出路径")
    parser.add_argument("--summary-output", default="", help="批量汇总 JSON 路径")
    parser.add_argument("--window-sec", type=float, default=10.0, help="差异窗口长度(秒)")
    parser.add_argument("--step-sec", type=float, default=2.0, help="滑动步长(秒)")
    parser.add_argument("--top-windows", type=int, default=3, help="保留差异最大的窗口数")
    parser.add_argument(
        "--with-ai",
        action="store_true",
        help="分析完成后单次调用综合 AI，同时落盘 ai_analysis_*.json 与 current_cpu_spike_ai_*.json",
    )
    parser.add_argument("--force-ai", action="store_true", help="覆盖已存在的综合 AI 文件")
    parser.add_argument("--base-url", default="", help="AI API Base URL")
    parser.add_argument("--api-key", default="", help="AI API Key")
    parser.add_argument("--model", default="", help="AI 模型名")
    args = parser.parse_args()

    high = os.path.abspath(str(args.high).strip())
    if not os.path.isdir(high):
        print(f"高功耗目录无效：{high}", file=sys.stderr)
        return 1

    try:
        low = _resolve_low(high, args.low)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    scripts = _scripts_dir()
    sys.path.insert(0, str(scripts))
    from current_cpu_spike import analyze_scene_current_cpu  # noqa: E402

    run_combined_ai = None
    if args.with_ai:
        from ai_client import (  # noqa: E402
            analyze_scene_combined_json,
            write_combined_ai_artifacts,
        )

        def run_combined_ai(spike_payload: dict, cpu_payload: dict | None, cpu_path: str, spike_out: str):
            try:
                ai_reply = analyze_scene_combined_json(
                    cpu_payload,
                    spike_payload,
                    base_url=str(args.base_url).strip(),
                    api_key=str(args.api_key).strip(),
                    model=str(args.model).strip(),
                )
                return {"success": True, "ai_reply": ai_reply}
            except Exception as exc:
                return {"success": False, "ai_reply": f"AI 分析失败：{exc}"}

    results_dir = _resolve_results_dir(high, args.cpu_dir, args.screen)
    suffixes: list[str] = []
    if args.suffix:
        suffixes = [str(args.suffix).strip().lstrip("_")]
    elif args.top_scenes:
        suffixes = _load_suffixes(os.path.abspath(args.top_scenes))
    else:
        print("请指定 --suffix 或 --top-scenes", file=sys.stderr)
        return 1

    power_map: dict[str, float] = {}
    if args.top_scenes and os.path.isfile(os.path.abspath(args.top_scenes)):
        try:
            from utils import parse_top_scenes_json  # noqa: E402

            ts_payload = json.load(open(os.path.abspath(args.top_scenes), encoding="utf-8"))
            top_scenes_list, _, _ = parse_top_scenes_json(ts_payload)
            for sc in top_scenes_list:
                suf0 = str(sc.get("suffix") or "").strip()
                if not suf0:
                    continue
                try:
                    power_map[suf0] = float(sc.get("power_mah", 0.0))
                except (TypeError, ValueError):
                    power_map[suf0] = 0.0
        except Exception:
            pass

    summary: dict = {"success": True, "high": high, "low": low, "scenes": {}}
    ok = 0
    for suf in suffixes:
        cpu_path = os.path.join(results_dir, f"cpu_analysis_{suf}.json")
        if not os.path.isfile(cpu_path):
            cpu_path = os.path.join(high, f"cpu_analysis_{suf}.json")
        cpu_payload = None
        if os.path.isfile(cpu_path):
            try:
                cpu_payload = json.load(open(cpu_path, encoding="utf-8"))
            except Exception:
                cpu_payload = None
        try:
            result = analyze_scene_current_cpu(
                high,
                low,
                suf,
                cpu_json_path=cpu_path if os.path.isfile(cpu_path) else None,
                window_sec=args.window_sec,
                step_sec=args.step_sec,
                top_windows=args.top_windows,
            )
        except Exception as exc:
            result = {"success": False, "suffix": suf, "error": str(exc)}
        if args.output and len(suffixes) == 1:
            out = os.path.abspath(args.output)
        else:
            out = os.path.join(results_dir, f"current_cpu_spike_{suf}.json")
        if args.with_ai and result.get("success") and run_combined_ai:
            ai_out = os.path.join(results_dir, f"ai_analysis_{suf}.json")
            spike_ai_out = os.path.join(results_dir, f"current_cpu_spike_ai_{suf}.json")
            if (not os.path.isfile(ai_out) and not os.path.isfile(spike_ai_out)) or args.force_ai:
                ai_result = run_combined_ai(result, cpu_payload, cpu_path, out)
                result["ai_result"] = ai_result
                a_path, s_path = write_combined_ai_artifacts(
                    results_dir=results_dir,
                    suffix=suf,
                    ai_result=ai_result,
                    cpu_json=cpu_path if os.path.isfile(cpu_path) else "",
                    spike_json=out,
                    power_mah=power_map.get(suf, 0.0),
                )
                try:
                    from ai_client import merge_record_flat_into_combined_artifacts

                    m_ai, _ = merge_record_flat_into_combined_artifacts(results_dir, suf)
                    if m_ai:
                        print(f"  已合并平缓段专项 AI -> {m_ai}")
                except Exception as exc:
                    print(f"  平缓段专项 AI 合并跳过：{exc}")
                print(f"  AI(综合×1) -> {a_path}")
                print(f"             -> {s_path}")
            else:
                try:
                    prefer = ai_out if os.path.isfile(ai_out) else spike_ai_out
                    ai_payload = json.load(open(prefer, encoding="utf-8"))
                    ai = ai_payload.get("ai_result")
                    if isinstance(ai, dict):
                        result["ai_result"] = ai
                    print(f"  AI 已存在，跳过：{prefer}")
                except Exception:
                    pass
            try:
                from ai_client import merge_record_flat_into_combined_artifacts

                m_ai, _ = merge_record_flat_into_combined_artifacts(results_dir, suf)
                if m_ai:
                    print(f"  已合并平缓段专项 AI -> {m_ai}")
            except Exception:
                pass
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"[{'OK' if result.get('success') else 'FAIL'}] {suf} -> {out}")
        if result.get("success"):
            ok += 1
            s = result.get("current_summary") or {}
            top = (result.get("spike_windows") or [{}])[0]
            print(
                f"  底电(最低) 高 {s.get('high_floor_ma')} / 低 {s.get('low_floor_ma')} mA | "
                f"底电差 {s.get('floor_diff_ma')} mA"
            )
            print(
                f"  平均底电({s.get('avg_baseline_window_sec', 10)}s窗) "
                f"高 {s.get('high_avg_baseline_ma')} / 低 {s.get('low_avg_baseline_ma')} mA | "
                f"平均底电差 {s.get('avg_baseline_diff_ma')} mA"
            )
            print(
                f"  对齐均差 {s.get('aligned_avg_diff_ma')} mA | "
                f"差值范围 [{s.get('min_diff_ma')}, {s.get('max_diff_ma')}] mA | "
                f"最大窗口 {top.get('relative_time')} 均差 {top.get('mean_diff_ma')} mA"
            )
        else:
            print(f"  {result.get('error')}")
        summary["scenes"][suf] = {"path": out, **{k: result.get(k) for k in ("success", "error", "current_summary", "spike_windows")}}

    summary_path = args.summary_output or os.path.join(results_dir, "current_cpu_spike_result.json")
    summary["success"] = ok > 0
    summary["analyzed_count"] = ok
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"汇总 -> {summary_path} ({ok}/{len(suffixes)} 成功)")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
