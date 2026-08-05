"""单场景综合 AI（兼容入口）。

新流程：须先有 current_cpu_spike_<suffix>.json，再一次调用综合分析，
同时落盘 ai_analysis_* 与 current_cpu_spike_ai_*。

推荐直接用：run_current_cpu_spike.py --with-ai
或补跑：run_current_cpu_spike_ai.py
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
import sys
from pathlib import Path


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "scripts"


def _load_power_map(top_scenes_path: Path | None) -> dict[str, float]:
    if not top_scenes_path or not top_scenes_path.is_file():
        return {}
    sys.path.insert(0, str(_scripts_dir()))
    from utils import parse_top_scenes_json  # noqa: E402

    payload = json.loads(top_scenes_path.read_text(encoding="utf-8-sig"))
    top_scenes, _, _ = parse_top_scenes_json(payload)
    out: dict[str, float] = {}
    for sc in top_scenes:
        suf = str(sc.get("suffix", "")).strip()
        if not suf:
            continue
        try:
            out[suf] = float(sc.get("power_mah", 0.0))
        except (TypeError, ValueError):
            out[suf] = 0.0
    return out


def _analyze_combined(
    *,
    cpu_path: Path,
    spike_path: Path,
    results_dir: Path,
    power_mah: float | None,
    base_url: str,
    api_key: str,
    model: str,
    force: bool,
) -> int:
    if not spike_path.is_file():
        print(
            f"缺少 current_cpu_spike：{spike_path}\n"
            "请先运行 run_current_cpu_spike.py，再执行本脚本；"
            "或直接：run_current_cpu_spike.py ... --with-ai",
            file=sys.stderr,
        )
        return 1
    if not cpu_path.is_file():
        print(f"缺少 CPU JSON：{cpu_path}", file=sys.stderr)
        return 1

    spike_payload = json.loads(spike_path.read_text(encoding="utf-8-sig"))
    suffix = str(
        spike_payload.get("suffix") or spike_path.stem.replace("current_cpu_spike_", "")
    ).strip()
    ai_out = results_dir / f"ai_analysis_{suffix}.json"
    spike_ai_out = results_dir / f"current_cpu_spike_ai_{suffix}.json"
    if (ai_out.is_file() or spike_ai_out.is_file()) and not force:
        print(f"已存在，跳过：{ai_out if ai_out.is_file() else spike_ai_out}")
        return 0

    cpu_payload = json.loads(cpu_path.read_text(encoding="utf-8-sig"))
    sys.path.insert(0, str(_scripts_dir()))
    from ai_client import analyze_scene_combined_json, write_combined_ai_artifacts  # noqa: E402

    try:
        ai_reply = analyze_scene_combined_json(
            cpu_payload,
            spike_payload,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
        ai_result = {"success": True, "ai_reply": ai_reply}
        success = True
    except Exception as exc:
        ai_result = {"success": False, "ai_reply": f"AI 分析失败：{exc}"}
        success = False

    if power_mah is None:
        power_mah = 0.0

    a_path, s_path = write_combined_ai_artifacts(
        results_dir=results_dir,
        suffix=suffix,
        ai_result=ai_result,
        cpu_json=str(cpu_path.resolve()),
        spike_json=str(spike_path.resolve()),
        power_mah=power_mah,
    )
    print(f"已输出（综合×1）：{a_path}")
    print(f"                 {s_path}")
    return 0 if success else 1


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="DOU 单场景综合 AI（须已有 current_cpu_spike；一次 API 落盘双文件）"
    )
    parser.add_argument("cpu_json", nargs="?", default="", help="cpu_analysis_<suffix>.json 路径")
    parser.add_argument("--cpu-dir", default="", help="CPU JSON 目录（与 --suffix 或 --top-scenes 联用）")
    parser.add_argument("--spike-dir", default="", help="current_cpu_spike 目录（默认与 --cpu-dir 相同）")
    parser.add_argument("--suffix", default="", help="场景后缀；与 --cpu-dir 联用")
    parser.add_argument("--top-scenes", default="", help="topn_scenes JSON，批量分析全部 top_scenes")
    parser.add_argument("--output", default="", help="（兼容保留，忽略；固定写 ai_analysis_<suffix>.json）")
    parser.add_argument("--power-mah", type=float, default=None, help="功耗差异 mAh（可选）")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 AI 文件")
    parser.add_argument("--base-url", default="", help="API Base URL（默认读 ai_config.json / 环境变量）")
    parser.add_argument("--api-key", default="", help="API Key（默认 DOU_AI_API_KEY 环境变量）")
    parser.add_argument("--model", default="", help="模型名（默认 deepseek-v4-flash）")
    args = parser.parse_args()

    base_url = str(args.base_url).strip()
    api_key = str(args.api_key).strip()
    model = str(args.model).strip()

    cpu_json = str(args.cpu_json).strip()
    cpu_dir = Path(str(args.cpu_dir).strip()).resolve() if str(args.cpu_dir).strip() else None
    spike_dir = (
        Path(str(args.spike_dir).strip()).resolve()
        if str(args.spike_dir).strip()
        else cpu_dir
    )
    top_scenes = Path(str(args.top_scenes).strip()).resolve() if str(args.top_scenes).strip() else None
    suffix = str(args.suffix).strip().lstrip("_")

    power_map = _load_power_map(top_scenes)

    if top_scenes and cpu_dir:
        if not top_scenes.is_file():
            print(f"top-scenes 不存在：{top_scenes}", file=sys.stderr)
            return 1
        sys.path.insert(0, str(_scripts_dir()))
        from utils import parse_top_scenes_json  # noqa: E402

        payload = json.loads(top_scenes.read_text(encoding="utf-8-sig"))
        top_scenes_list, _, _ = parse_top_scenes_json(payload)
        sd = spike_dir or cpu_dir
        rc = 0
        for sc in top_scenes_list:
            suf = str(sc.get("suffix", "")).strip()
            if not suf:
                continue
            cpu_path = cpu_dir / f"cpu_analysis_{suf}.json"
            spike_path = sd / f"current_cpu_spike_{suf}.json"
            pm = power_map.get(suf)
            if pm is None:
                try:
                    pm = float(sc.get("power_mah", 0.0))
                except (TypeError, ValueError):
                    pm = 0.0
            code = _analyze_combined(
                cpu_path=cpu_path,
                spike_path=spike_path,
                results_dir=cpu_dir,
                power_mah=pm,
                base_url=base_url,
                api_key=api_key,
                model=model,
                force=args.force,
            )
            rc = max(rc, code)
        return rc

    if cpu_dir and suffix:
        sd = spike_dir or cpu_dir
        pm = args.power_mah if args.power_mah is not None else power_map.get(suffix)
        return _analyze_combined(
            cpu_path=cpu_dir / f"cpu_analysis_{suffix}.json",
            spike_path=sd / f"current_cpu_spike_{suffix}.json",
            results_dir=cpu_dir,
            power_mah=pm,
            base_url=base_url,
            api_key=api_key,
            model=model,
            force=args.force,
        )

    if cpu_json:
        cpu_path = Path(cpu_json).resolve()
        suf = str(cpu_path.stem.replace("cpu_analysis_", "")).strip()
        results_dir = cpu_path.parent
        sd = spike_dir or results_dir
        return _analyze_combined(
            cpu_path=cpu_path,
            spike_path=sd / f"current_cpu_spike_{suf}.json",
            results_dir=results_dir,
            power_mah=args.power_mah,
            base_url=base_url,
            api_key=api_key,
            model=model,
            force=args.force,
        )

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
