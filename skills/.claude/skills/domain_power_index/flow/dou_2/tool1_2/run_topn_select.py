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


def _norm_screen_filter(v: str) -> str:
    s = (v or "").strip()
    if not s:
        return ""
    s_low = s.lower()
    if s in ("灭屏", "熄屏") or s_low in ("off", "screen_off", "screen-off"):
        return "off"
    if s in ("亮屏",) or s_low in ("on", "screen_on", "screen-on"):
        return "on"
    return "__invalid__"


def _match_screen(desc: str, name: str, screen: str) -> bool:
    if not screen:
        return True
    from utils import is_screen_off_scene  # noqa: E402

    off_hit = is_screen_off_scene(desc, name)
    if screen == "off":
        return off_hit
    if screen == "on":
        return not off_hit
    return True


def _read_excel_rows(scene_excel_path: Path):
    import pandas as pd  # noqa: E402
    from utils import _safe_float_cell, extract_suffix, scene_screen_label  # noqa: E402

    base_cols = ["name", "desc", "功耗差异mAh"]
    optional_cols = ["对亮屏电流影响(mA)", "对灭屏电流影响(mA)", "场景亮灭屏"]
    try:
        df = pd.read_excel(scene_excel_path)
    except Exception as exc:
        raise RuntimeError(f"读取 Excel 失败：{exc}") from exc

    for col in base_cols:
        if col not in df.columns:
            raise RuntimeError(f"Excel 缺少列：{col}")

    rows: list[dict] = []
    for _, row in df.iterrows():
        name = str(row.get("name", "")).strip()
        if not name:
            continue
        desc = row.get("desc", "无描述")
        try:
            diff = float(row.get("功耗差异mAh", 0))
        except Exception:
            continue
        if diff <= 0:
            continue

        suf = extract_suffix(name)
        if not suf:
            continue

        on_ma = _safe_float_cell(row.get("对亮屏电流影响(mA)")) if "对亮屏电流影响(mA)" in df.columns else None
        off_ma = _safe_float_cell(row.get("对灭屏电流影响(mA)")) if "对灭屏电流影响(mA)" in df.columns else None
        avg_4v_diff = (
            _safe_float_cell(row.get("avg_cur_4v_diff"))
            if "avg_cur_4v_diff" in df.columns
            else None
        )
        screen_label = str(row.get("场景亮灭屏", "") or "").strip() if "场景亮灭屏" in df.columns else ""
        if not screen_label:
            screen_label = scene_screen_label(desc, name)

        rows.append(
            {
                "suffix": suf,
                "name": name,
                "desc": desc,
                "power_mah": round(diff, 4),
                "screen_label": screen_label,
                "impact_on_ma": on_ma,
                "impact_off_ma": off_ma,
                "avg_cur_4v_diff": avg_4v_diff,
            }
        )
    return rows


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="DOU TopN 选择器（从 DOU3.0 Excel 生成 top_scenes_json）")
    parser.add_argument("scene_excel_path", help="DOU3.0版本数据对比.xlsx 路径")
    parser.add_argument("--topn", type=int, default=3, help="TopN，默认 3")
    parser.add_argument("--screen", default="", help="可选：灭屏/亮屏（或 off/on）")
    parser.add_argument("--output", default="", help="输出 top_scenes_json 路径（默认同目录）")
    parser.add_argument(
        "--ignorable-config",
        default="",
        help="可忽略场景配置 JSON（默认技能目录 ignorable_scenes.json）",
    )
    args = parser.parse_args()

    scene_excel_path = Path(str(args.scene_excel_path).strip()).resolve()
    if not scene_excel_path.exists():
        print(f"Excel 不存在：{scene_excel_path}", file=sys.stderr)
        return 1

    topn = max(1, min(25, int(args.topn)))
    screen_filter_raw = str(args.screen or "").strip()
    screen_filter = _norm_screen_filter(screen_filter_raw) if screen_filter_raw else ""
    if screen_filter == "__invalid__":
        print(f"不支持的 screen 参数：{screen_filter_raw}（仅支持 灭屏/亮屏/off/on）", file=sys.stderr)
        return 1

    this_dir = Path(__file__).resolve().parent
    scripts_dir = (this_dir / ".." / "scripts").resolve()
    sys.path.insert(0, str(scripts_dir))

    from utils import (  # noqa: E402
        apply_auto_error_ignorable_rules,
        is_ignorable_scene,
        ignorable_scene_reason,
        load_ignorable_scenes_config,
        resolve_high_dir_from_artifact,
        resolve_low_dir_from_high,
    )

    ignorable_path = str(args.ignorable_config).strip() or None
    high_dir = resolve_high_dir_from_artifact(scene_excel_path)
    low_dir = resolve_low_dir_from_high(high_dir)
    auto_info = apply_auto_error_ignorable_rules(high_dir, low_dir, ignorable_path)
    error_scenes = auto_info.get("error_scenes") or []
    if error_scenes:
        names = ", ".join(str(sc.get("name") or "") for sc in error_scenes[:8])
        suffix = " ..." if len(error_scenes) > 8 else ""
        print(
            f"已从 testReport error 场景临时写入 ignorable_scenes.json："
            f"{auto_info.get('added', 0)} 条（{names}{suffix}）"
        )

    ignorable_config = load_ignorable_scenes_config(ignorable_path)

    try:
        all_rows = _read_excel_rows(scene_excel_path)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    candidate_rows: list[dict] = []
    ignored_rows: list[dict] = []

    for rr in all_rows:
        if screen_filter and not _match_screen(str(rr.get("desc", "")), str(rr.get("name", "")), screen_filter):
            continue

        if is_ignorable_scene(rr["name"], rr["desc"], rr["suffix"], ignorable_config):
            ignored_rows.append(
                {
                    **rr,
                    "skip_reason": "脚本问题",
                    "ignore_reason": ignorable_scene_reason(
                        rr["name"], rr["desc"], rr["suffix"], ignorable_config
                    ),
                }
            )
            continue

        candidate_rows.append(
            {
                "suffix": rr["suffix"],
                "name": rr["name"],
                "desc": rr["desc"],
                "power_mah": rr["power_mah"],
                "screen_label": rr.get("screen_label"),
                "impact_on_ma": rr.get("impact_on_ma"),
                "impact_off_ma": rr.get("impact_off_ma"),
                "avg_cur_4v_diff": rr.get("avg_cur_4v_diff"),
            }
        )

    candidate_rows.sort(key=lambda x: -x["power_mah"])
    ignored_rows.sort(key=lambda x: -x["power_mah"])

    seen: set[str] = set()
    top_scenes: list[dict] = []
    for rr in candidate_rows:
        if rr["suffix"] in seen:
            continue
        seen.add(rr["suffix"])
        top_scenes.append(rr)
        if len(top_scenes) >= topn:
            break

    if not top_scenes:
        if screen_filter:
            sf_label = "灭屏" if screen_filter == "off" else "亮屏"
            print(f"没有符合条件的 TopN 场景：功耗差异 mAh > 0 且筛选={sf_label}", file=sys.stderr)
        else:
            print("没有符合条件的 TopN 场景：功耗差异 mAh > 0", file=sys.stderr)
        return 1

    if str(args.output).strip():
        out_path = Path(args.output).resolve()
    elif screen_filter:
        from utils import screen_results_dir  # noqa: E402

        bucket_dir = Path(
            screen_results_dir(str(scene_excel_path.parent), screen_filter_raw or screen_filter)
        )
        out_path = bucket_dir / f"topn_scenes_top{topn}.json"
    else:
        out_path = scene_excel_path.parent / f"topn_scenes_top{topn}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = {
        "top_scenes": top_scenes,
        "ignored_scenes": ignored_rows,
        "ignorable_config": ignorable_config.get("path"),
        "topn": topn,
        "screen_bucket": screen_filter or None,
        "screen_label": ("灭屏" if screen_filter == "off" else "亮屏") if screen_filter else "",
        "results_dir": str(out_path.parent),
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出：{out_path}")
    if ignored_rows:
        print(f"可忽略场景（脚本问题，未纳入 TopN）：{len(ignored_rows)} 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
