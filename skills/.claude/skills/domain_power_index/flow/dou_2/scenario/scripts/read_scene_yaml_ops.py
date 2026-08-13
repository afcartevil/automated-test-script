#!/usr/bin/env python3
"""读取 DOU meta_report 场景 YAML 的操作步骤，映射为相对时间轴（对齐 pt5 / diff_segments）。

用法:
  python read_scene_yaml_ops.py <meta_report目录> <suffix>
  python read_scene_yaml_ops.py <yaml文件路径>

输出 JSON（stdout）：steps 含 t0/t1、is_setup、op_kind、expected_current_shape。
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
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

SETUP_EXACT = {
    "确保退到桌面",
    "识别黑屏解锁",
    "左右滑桌面",
    "退到桌面",
    "退回桌面",
    "单用例结束机械手回轴",
    "回到桌面",
}

# (keyword_in_step_or_sub, op_kind, expected_current_shape)
OP_KIND_RULES: list[tuple[str, str, str]] = [
    ("小窗", "video_pip", "高平台持续（解码+PIP）；尖峰少于纯滑动段"),
    ("长视频播放", "video_watch", "高平台持续（硬解）；波动相对平滑"),
    ("长视频", "video_watch", "高平台持续（硬解）；波动相对平滑"),
    ("滑动浏览", "video_or_feed_scroll", "中高平台 + 周期性尖峰（划动节奏）"),
    ("短距划", "feed_scroll", "中高平台 + 密集周期尖峰（如每数秒一次）"),
    ("短距离滑动", "feed_scroll", "中高平台 + 密集周期尖峰（如每数秒一次）"),
    ("循环滑动", "feed_scroll", "中高平台 + 与 sub_step 周期对齐的尖峰"),
    ("循环上滑", "feed_scroll", "中高平台 + 周期尖峰"),
    ("主界面观看", "feed_scroll", "中高平台 + 周期尖峰（观看中间歇滑动）"),
    ("上下滑动", "feed_scroll", "中高平台 + 周期尖峰"),
    ("浏览滑动", "feed_scroll", "中高平台 + 周期尖峰"),
    ("滑动查看", "document_browse", "中平台 + 翻页/滚动尖峰"),
    ("换滤镜", "media_filter_edit", "中高平台 + 每次滤镜操作脉冲尖峰"),
    ("滤镜", "media_filter_edit", "中高平台 + 编辑脉冲"),
    ("拍照", "camera_shot", "快门/后处理尖峰簇"),
    ("录制", "content_record", "录制段抬升平台；结束有编码尖峰可能"),
    ("Share", "content_upload", "上传段中高平台 + 网络尖峰"),
    ("发布", "content_publish", "预览/编码/上传分段抬升"),
    ("下载", "store_download", "下载段持续中高平台；安装另有尖峰"),
    ("安装", "store_install", "短时尖峰或台阶"),
    ("导航", "maps_nav", "高平台持续（定位+渲染），少见纯尖峰形态"),
    ("剪辑", "media_edit", "高平台（GPU/多路解码）；导出段更高"),
    ("待机", "app_idle", "底电平台抬高、尖峰稀疏；密尖峰→心跳/定位"),
    ("打开网页", "web_browse", "打开尖峰 + 后续滚动/脚本平台"),
    ("循环滑动", "web_browse", "滚动尖峰密"),
    ("搜索打开", "app_launch", "启动尖峰后回落；分析业务段时应降权"),
]


def _load_yaml(path: Path) -> dict:
    if yaml is None:
        raise SystemExit("需要 PyYAML：pip install pyyaml")
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise SystemExit(f"YAML 根节点非 dict: {path}")
    return data


def find_scene_yaml(meta_report: Path, suffix: str) -> Path | None:
    suf = str(suffix).strip().lstrip("_")
    if not suf or not meta_report.is_dir():
        return None
    patterns = (
        re.compile(rf"_(pass|error)_dou3_{re.escape(suf)}\.ya?ml$", re.I),
        re.compile(rf"dou3_{re.escape(suf)}\.ya?ml$", re.I),
    )
    cands: list[Path] = []
    for p in meta_report.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in {".yaml", ".yml"}:
            continue
        if any(rx.search(p.name) for rx in patterns):
            cands.append(p)
    if not cands:
        return None
    # prefer pass over error, then newest mtime
    def key(p: Path) -> tuple:
        pass_first = 0 if "_pass_" in p.name.lower() else 1
        return (pass_first, -p.stat().st_mtime)

    return sorted(cands, key=key)[0]


def _is_setup(step_name: str) -> bool:
    name = (step_name or "").strip()
    if name in SETUP_EXACT:
        return True
    if name.startswith("搜索打开"):
        return True
    return False


def _classify(step_name: str, sub_step_name: str) -> tuple[str, str]:
    blob = f"{step_name or ''} {sub_step_name or ''}"
    for kw, kind, shape in OP_KIND_RULES:
        if kw in blob:
            return kind, shape
    if _is_setup(step_name):
        return "setup", "启动/收尾；电流尖峰常见但非业务主因"
    return "unknown", "对照 diff_segments 经验判定"


def parse_scene_yaml(path: Path) -> dict:
    raw = _load_yaml(path)
    steps_raw = (raw.get("data") or {}).get("step_time_datas") or []
    steps: list[dict] = []
    t = 0.0
    for i, s in enumerate(steps_raw):
        if not isinstance(s, dict):
            continue
        name = str(s.get("step_name") or "")
        sub = str(s.get("sub_step_name") or "")
        actual = float(s.get("actual_time") or 0.0)
        expect = float(s.get("expect_time") or 0.0)
        t0, t1 = t, t + actual
        kind, shape = _classify(name, sub)
        setup = _is_setup(name)
        steps.append(
            {
                "index": i,
                "step_name": name,
                "sub_step_name": sub,
                "expect_time": round(expect, 3),
                "actual_time": round(actual, 3),
                "t0_sec": round(t0, 3),
                "t1_sec": round(t1, 3),
                "is_setup": setup,
                "op_kind": kind,
                "expected_current_shape": shape,
            }
        )
        t = t1

    business = [x for x in steps if not x["is_setup"]]
    # routing hint text = join business step names
    route_text = " ".join(
        f"{x['step_name']} {x['sub_step_name']}".strip() for x in business
    )
    case_desc = str(raw.get("case_desc") or "")

    return {
        "ok": True,
        "yaml_path": str(path),
        "suffix": _suffix_from_name(path.name),
        "case_name": raw.get("case_name"),
        "case_desc": case_desc,
        "test_result": raw.get("test_result"),
        "start_time": raw.get("start_time"),
        "end_time": raw.get("end_time"),
        "avg_cur": (raw.get("data") or {}).get("avg_cur"),
        "total_actual_sec": round(t, 3),
        "steps": steps,
        "business_steps": business,
        "route_text": route_text,
        "case_desc_vs_ops_warning": _desc_ops_warning(case_desc, business),
        "note": (
            "t0/t1 为相对场景起点秒，与 pt5 相对轴 / current_cpu_spike.diff_segments 对齐；"
            "分析电流波动时优先看 business_steps，setup 段降权。"
        ),
    }


def _suffix_from_name(name: str) -> str | None:
    m = re.search(r"dou3_(\d+)", name, re.I)
    return m.group(1) if m else None


def _desc_ops_warning(case_desc: str, business: list[dict]) -> str | None:
    """case_desc 与真实操作不一致时告警（如 Gallery 拍照 vs 换滤镜）。"""
    if not business:
        return "无业务步骤"
    names = " ".join(x["step_name"] for x in business)
    if "拍照" in case_desc and "滤镜" in names and "拍照" not in names:
        return "case_desc 含「拍照」但 YAML 业务步为滤镜编辑，路由/归因以 YAML 操作为准"
    if "小窗" in case_desc and "小窗" not in names and "长视频" in names:
        return "case_desc 含小窗但步骤名未出现小窗关键字，请人工核对步骤"
    return None


def main() -> int:
    _setup_utf8_stdio()
    ap = argparse.ArgumentParser(description="读取 DOU 场景 YAML 操作时间轴")
    ap.add_argument("path", help="meta_report 目录，或单个 .yaml 文件")
    ap.add_argument("suffix", nargs="?", help="场景号（目录模式必填），如 00572")
    ap.add_argument("-o", "--output", help="写入 JSON 文件（默认 stdout）")
    args = ap.parse_args()

    p = Path(args.path)
    if p.is_file():
        yaml_path = p
    elif p.is_dir():
        if not args.suffix:
            print("目录模式必须提供 suffix", file=sys.stderr)
            return 2
        yaml_path = find_scene_yaml(p, args.suffix)
        if not yaml_path:
            out = {"ok": False, "error": f"未找到 dou3_{args.suffix} yaml", "meta_report": str(p)}
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 1
    else:
        print(f"路径不存在: {p}", file=sys.stderr)
        return 2

    result = parse_scene_yaml(yaml_path)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        out = Path.cwd() / f"scene_yaml_{yaml_path.stem}.json"
        out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
