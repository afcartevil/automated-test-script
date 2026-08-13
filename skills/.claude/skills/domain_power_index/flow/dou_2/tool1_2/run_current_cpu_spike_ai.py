"""单场景综合 AI：读取 current_cpu_spike + cpu_analysis，一次 API 调用落盘。

同时写入 ai_analysis_<suffix>.json 与 current_cpu_spike_ai_<suffix>.json（同一结论）。
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


def _load_suffixes(top_scenes_path: Path) -> list[str]:
    data = json.loads(top_scenes_path.read_text(encoding="utf-8-sig"))
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


def _analyze_one(
    spike_path: Path,
    *,
    cpu_path: Path | None,
    results_dir: Path,
    power_mah: float,
    base_url: str,
    api_key: str,
    model: str,
    force: bool,
    embed_in_spike: bool,
) -> int:
    ai_out = results_dir / f"ai_analysis_{spike_path.stem.replace('current_cpu_spike_', '')}.json"
    # resolve suffix first from file
    if not spike_path.is_file():
        print(f"缺少电流+CPU JSON：{spike_path}", file=sys.stderr)
        return 1

    spike_payload = json.loads(spike_path.read_text(encoding="utf-8-sig"))
    if not spike_payload.get("success"):
        print(f"电流+CPU 分析未成功：{spike_path}", file=sys.stderr)
        return 1

    suffix = str(
        spike_payload.get("suffix") or spike_path.stem.replace("current_cpu_spike_", "")
    ).strip()
    if not suffix:
        print(f"无法解析 suffix：{spike_path}", file=sys.stderr)
        return 1

    ai_out = results_dir / f"ai_analysis_{suffix}.json"
    spike_ai_out = results_dir / f"current_cpu_spike_ai_{suffix}.json"
    if (ai_out.is_file() or spike_ai_out.is_file()) and not force:
        print(f"已存在，跳过：{ai_out if ai_out.is_file() else spike_ai_out}")
        return 0

    cpu_payload = None
    cpu_json_str = ""
    if cpu_path and cpu_path.is_file():
        cpu_payload = json.loads(cpu_path.read_text(encoding="utf-8-sig"))
        cpu_json_str = str(cpu_path.resolve())
    elif (results_dir / f"cpu_analysis_{suffix}.json").is_file():
        cpu_path = results_dir / f"cpu_analysis_{suffix}.json"
        cpu_payload = json.loads(cpu_path.read_text(encoding="utf-8-sig"))
        cpu_json_str = str(cpu_path.resolve())

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

    a_path, s_path = write_combined_ai_artifacts(
        results_dir=results_dir,
        suffix=suffix,
        ai_result=ai_result,
        cpu_json=cpu_json_str,
        spike_json=str(spike_path.resolve()),
        power_mah=power_mah,
    )
    try:
        from ai_client import merge_record_flat_into_combined_artifacts

        m_ai, m_spike = merge_record_flat_into_combined_artifacts(results_dir, suffix)
        if m_ai or m_spike:
            print(f"已合并平缓段专项 AI -> {m_ai or m_spike}")
    except Exception as exc:
        print(f"平缓段专项 AI 合并跳过：{exc}", file=sys.stderr)
    print(f"已输出（综合×1）：{a_path}")
    print(f"                 {s_path}")

    if embed_in_spike:
        spike_payload["ai_result"] = ai_result
        spike_path.write_text(
            json.dumps(spike_payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"已回写 ai_result -> {spike_path}")

    return 0 if success else 1


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="DOU 单场景综合 AI（CPU+电流一次调用；落盘 ai_analysis_* 与 current_cpu_spike_ai_*）"
    )
    parser.add_argument("spike_json", nargs="?", default="", help="current_cpu_spike_<suffix>.json 路径")
    parser.add_argument("--spike-dir", default="", help="current_cpu_spike_*.json 所在目录")
    parser.add_argument("--cpu-dir", default="", help="cpu_analysis_*.json 所在目录（默认与 spike-dir 相同）")
    parser.add_argument("--suffix", default="", help="场景后缀；与 --spike-dir 联用")
    parser.add_argument("--top-scenes", default="", help="topn_scenes JSON，批量分析")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的 AI 文件")
    parser.add_argument("--embed", action="store_true", help="将 ai_result 回写进 current_cpu_spike JSON")
    parser.add_argument("--base-url", default="", help="API Base URL")
    parser.add_argument("--api-key", default="", help="API Key")
    parser.add_argument("--model", default="", help="模型名")
    args = parser.parse_args()

    base_url = str(args.base_url).strip()
    api_key = str(args.api_key).strip()
    model = str(args.model).strip()
    embed = bool(args.embed)

    spike_dir = Path(str(args.spike_dir).strip()).resolve() if str(args.spike_dir).strip() else None
    cpu_dir = Path(str(args.cpu_dir).strip()).resolve() if str(args.cpu_dir).strip() else spike_dir
    top_scenes = Path(str(args.top_scenes).strip()).resolve() if str(args.top_scenes).strip() else None
    suffix = str(args.suffix).strip().lstrip("_")
    spike_json = str(args.spike_json).strip()
    power_map = _load_power_map(top_scenes)

    if top_scenes and spike_dir:
        if not top_scenes.is_file():
            print(f"top-scenes 不存在：{top_scenes}", file=sys.stderr)
            return 1
        rc = 0
        for suf in _load_suffixes(top_scenes):
            spike_path = spike_dir / f"current_cpu_spike_{suf}.json"
            cpu_path = (cpu_dir or spike_dir) / f"cpu_analysis_{suf}.json"
            code = _analyze_one(
                spike_path,
                cpu_path=cpu_path if cpu_path.is_file() else None,
                results_dir=spike_dir,
                power_mah=power_map.get(suf, 0.0),
                base_url=base_url,
                api_key=api_key,
                model=model,
                force=args.force,
                embed_in_spike=embed,
            )
            rc = max(rc, code)
        return rc

    if spike_dir and suffix:
        spike_path = spike_dir / f"current_cpu_spike_{suffix}.json"
        cpu_path = (cpu_dir or spike_dir) / f"cpu_analysis_{suffix}.json"
        return _analyze_one(
            spike_path,
            cpu_path=cpu_path if cpu_path.is_file() else None,
            results_dir=spike_dir,
            power_mah=power_map.get(suffix, 0.0),
            base_url=base_url,
            api_key=api_key,
            model=model,
            force=args.force,
            embed_in_spike=embed,
        )

    if spike_json:
        spike_path = Path(spike_json).resolve()
        results_dir = spike_path.parent
        suf = str(spike_path.stem.replace("current_cpu_spike_", "")).strip()
        cpu_path = (cpu_dir or results_dir) / f"cpu_analysis_{suf}.json"
        return _analyze_one(
            spike_path,
            cpu_path=cpu_path if cpu_path.is_file() else None,
            results_dir=results_dir,
            power_mah=power_map.get(suf, 0.0),
            base_url=base_url,
            api_key=api_key,
            model=model,
            force=args.force,
            embed_in_spike=embed,
        )

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
