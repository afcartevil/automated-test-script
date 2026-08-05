# -*- coding: utf-8
"""Generate DOU full report: template layout + project data + AI synthesis."""
from __future__ import annotations
def _setup_utf8_stdio() -> None:
    import sys
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

HIGH = Path(
    r"\\10.205.4.20\sw_temp\底软通信开发部\lzx\DOU高功耗文件夹"
    r"\20260625-143325_X6877_16.3.0.043_SN169932561X101127_PowerMonitor - 2"
)
PROJECT_TITLE = "20260625-143325_X6877_16.3.0.043_SN169932561X101127_PowerMonitor - 2项目"
SUPPLIER_HIGH = "CN6一供"
SUPPLIER_LOW = "CN6二供"
SCREEN_ON = HIGH / "screen_on"


def find_test_report(folder: Path) -> Path | None:
    p = folder / "meta_report" / "testReport.xlsx"
    return p if p.is_file() else next((x for x in folder.rglob("testReport.xlsx")), None)


def _norm_col(name: object) -> str:
    s = str(name).replace("\r\n", " ").replace("\n", " ").strip().lower()
    return re.sub(r"\s+", " ", s)


def parse_total_pro(report_path: Path) -> dict:
    df = pd.read_excel(report_path, sheet_name="total pro", header=0)
    row = df.iloc[0]
    colmap = {_norm_col(c): c for c in df.columns}

    def pick(*candidates: str):
        for cand in candidates:
            key = _norm_col(cand)
            for nk, orig in colmap.items():
                if key in nk or nk in key:
                    val = row.get(orig)
                    if pd.notna(val):
                        return val
        return None

    battery = pick("battery", "电池容量")
    try:
        battery_f = float(battery)
    except Exception:
        battery_f = None

    return {
        "battery_85_mAh": round(battery_f * 0.85, 0) if battery_f else None,
        "dou_h": pick("dou - normalized", "归一化续航时长"),
        "screen_on_dou_h": pick("scrren-on dou", "亮屏续航时长"),
        "screen_on_current_mA": pick("screen-on current 4v", "亮屏平均电流"),
        "screen_off_current_mA": pick("screen-off current 4v", "灭屏平均电流"),
        "rom_version": pick("rom_version", "版本号"),
    }


def load_ai_reply(path: Path) -> str:
    if not path.is_file():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("ai_reply"):
        return str(data["ai_reply"]).strip()
    for nested in ("ai_result", "summary"):
        sub = data.get(nested)
        if isinstance(sub, dict) and sub.get("ai_reply"):
            return str(sub["ai_reply"]).strip()
    return ""


def strip_md(text: str) -> str:
    return re.sub(r"\*\*([^*]+)\*\*", r"\1", text)


def extract_synthesis(ai_text: str) -> str:
    """Pick the best single concluding paragraph from AI output."""
    if not ai_text:
        return ""
    markers = (
        "综合所有证据",
        "根因推断",
        "综合来看",
        "综合以上",
        "综上所述",
        "因此，优化",
        "综合结论",
    )
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", ai_text) if p.strip()]

    def score(p: str) -> int:
        s = 0
        for i, m in enumerate(markers):
            if m in p:
                s += 100 - i
        return s

    if not paragraphs:
        return strip_md(re.sub(r"\s+", " ", ai_text[:400]).strip())
    best = max(paragraphs, key=score)
    if score(best) > 0:
        return strip_md(re.sub(r"\s+", " ", best).strip())
    return strip_md(re.sub(r"\s+", " ", paragraphs[-1]).strip())


def trim_text(text: str, limit: int = 360) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    if "。" in cut[limit // 2 :]:
        cut = cut[: cut.rfind("。") + 1]
    else:
        cut += "…"
    return cut


def top_processes(cpu_ai: str, limit: int = 3) -> list[str]:
    if not cpu_ai:
        return []
    seen: list[str] = []
    for name in re.findall(r"\*\*([^*]+)\*\*", cpu_ai):
        name = name.strip()
        if name and name not in seen:
            seen.append(name)
        if len(seen) >= limit:
            break
    return seen


def build_scene_synthesis(suffix: str, cpu_dir: Path) -> str:
    # 新流程：综合 AI 同文写入两文件；任取其一。旧产物仍兼容双读合并。
    cpu_ai = load_ai_reply(cpu_dir / f"ai_analysis_{suffix}.json")
    spike_ai = load_ai_reply(cpu_dir / f"current_cpu_spike_ai_{suffix}.json")
    combined = spike_ai or cpu_ai
    if spike_ai and cpu_ai and spike_ai.strip() != cpu_ai.strip():
        # 旧双次 AI 产物：优先电流时段结论
        primary = extract_synthesis(spike_ai) or extract_synthesis(cpu_ai)
        if not primary:
            primary = spike_ai
    else:
        primary = extract_synthesis(combined) or combined

    if not primary:
        return "（该场景暂无 AI 分析结论）"

    return trim_text(clean_synthesis(primary), 300)


def parse_topn_section(topn_text: str, start_heading: str, end_heading: str | None) -> str:
    pattern = rf"{re.escape(start_heading)}([\s\S]*?)"
    if end_heading:
        pattern += rf"(?={re.escape(end_heading)}|$)"
    else:
        pattern += r"$"
    m = re.search(pattern, topn_text)
    return m.group(1).strip() if m else ""


def parse_cross_items(section: str) -> list[str]:
    items: list[str] = []
    for m in re.finditer(
        r"\*\*(\d+)\.\s*([^*]+?)\*\*([\s\S]*?)(?=\*\*\d+\.|$)",
        section,
    ):
        rank, title, body = m.groups()
        title = title.strip().rstrip("。")
        body = re.sub(r"\s+", " ", strip_md(body)).strip()
        if len(body) > 140:
            body = body[:138] + "…"
        items.append(f"{rank}. {title}：{body}" if body else f"{rank}. {title}")
    return items


def clean_synthesis(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(综合[^。]{0,20}[，。]\s*)+", "", text)
    return text.strip()


def parse_priority_items(section: str) -> list[str]:
    items: list[str] = []
    for m in re.finditer(
        r"\*\*(\d+)\.\s*(?:\[([^\]]+)\]|【([^】]+)】)\s*([\s\S]*?)\*\*([\s\S]*?)(?=\*\*\d+\.|$)",
        section,
    ):
        rank = m.group(1)
        level = (m.group(2) or m.group(3) or "").strip()
        title = m.group(4).strip().rstrip("。")
        body = re.sub(r"\s+", " ", strip_md(m.group(5))).strip()
        if len(body) > 100:
            body = body[:98] + "…"
        line = f"{rank}. [{level}] {title}" if level else f"{rank}. {title}"
        if body:
            line += f"：{body}"
        items.append(line)
    return items


def fmt_num(v, digits=2) -> str:
    try:
        return f"{float(v):.{digits}f}"
    except Exception:
        return str(v) if v is not None else "-"


def build_report() -> str:
    sc = json.loads((HIGH / "scene_compare_result.json").read_text(encoding="utf-8"))
    v1 = parse_total_pro(find_test_report(Path(sc["high"])))
    v2 = parse_total_pro(find_test_report(Path(sc["low"])))

    df = pd.read_excel(HIGH / "DOU3.0版本数据对比.xlsx", sheet_name="Sheet1")
    total_mah = float(df["功耗差异mAh"].sum())
    on_mah = float(df[df["场景亮灭屏"] == "亮屏"]["功耗差异mAh"].sum())
    off_mah = float(df[df["场景亮灭屏"] == "灭屏"]["功耗差异mAh"].sum())

    pa = json.loads((HIGH / "power_analysis_result.json").read_text(encoding="utf-8"))
    comp = (pa.get("result", {}).get("data") or {}).get("comparison", {}).get("combined", {})
    on_diff = comp.get("on_power", {}).get("difference")
    off_diff = comp.get("off_power", {}).get("difference")

    topn_text = load_ai_reply(SCREEN_ON / "topn_summary.json")
    top15 = json.loads((SCREEN_ON / "topn_scenes_top15.json").read_text(encoding="utf-8"))

    on_cur1 = float(v1.get("screen_on_current_mA") or 0)
    on_cur2 = float(v2.get("screen_on_current_mA") or 0)
    off_cur1 = float(v1.get("screen_off_current_mA") or 0)
    off_cur2 = float(v2.get("screen_off_current_mA") or 0)
    on_cur_gap = on_cur1 - on_cur2
    off_cur_gap = off_cur1 - off_cur2

    lines: list[str] = []
    lines.append(f"# {PROJECT_TITLE}")
    lines.append("")
    lines.append(f"生成时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
    lines.append("")

    lines.append("## 版本数据")
    lines.append("")
    lines.append(f"| | {SUPPLIER_HIGH} | {SUPPLIER_LOW} |")
    lines.append("|---|---:|---:|")
    b85 = v1.get("battery_85_mAh")
    lines.append(f"| 电池容量*85% | {int(b85) if b85 else '-'} | {int(b85) if b85 else '-'} |")
    lines.append(f"| 续航时长(h) | {fmt_num(v1.get('dou_h'))} | {fmt_num(v2.get('dou_h'))} |")
    lines.append(f"| 亮屏可用时长(h) | {fmt_num(v1.get('screen_on_dou_h'))} | {fmt_num(v2.get('screen_on_dou_h'))} |")
    lines.append(f"| 亮屏电流(mA) | {fmt_num(v1.get('screen_on_current_mA'))} | {fmt_num(v2.get('screen_on_current_mA'))} |")
    lines.append(f"| 灭屏电流(mA) | {fmt_num(v1.get('screen_off_current_mA'))} | {fmt_num(v2.get('screen_off_current_mA'))} |")
    lines.append(f"| 测试版本 | {v1.get('rom_version', '-')} | {v2.get('rom_version', '-')} |")
    lines.append("")

    lines.append("## 整体功耗影响")
    lines.append("")
    lines.append(f"- 全场景累计差异：**{total_mah:.2f} mAh**（一供相对二供）")
    lines.append(f"- 亮屏场景累计：**{on_mah:.2f} mAh**；灭屏场景累计：**{off_mah:.2f} mAh**")
    if on_diff is not None and off_diff is not None:
        lines.append(
            f"- 射频加权亮屏电流差：**{float(on_diff):+.2f} mA**；灭屏：**{float(off_diff):+.2f} mA**"
        )
    try:
        dou_diff = float(v1["dou_h"]) - float(v2["dou_h"])
        lines.append(f"- DOU 归一化续航差：**{dou_diff:+.2f} h**")
    except Exception:
        pass
    lines.append("")

    # --- AI auto summary ---
    lines.append("## 问题分析总结")
    lines.append("")
    lines.append("**问题分析总结：**")
    lines.append("")
    higher_on = SUPPLIER_HIGH if on_cur_gap >= 0 else SUPPLIER_LOW
    lower_on = SUPPLIER_LOW if on_cur_gap >= 0 else SUPPLIER_HIGH
    lines.append(
        f"从 testReport 归一化数据看，{higher_on}较{lower_on}亮屏平均电流高 **{abs(on_cur_gap):.2f} mA**"
        f"（{on_cur1:.2f} vs {on_cur2:.2f} mA），灭屏差 **{off_cur_gap:+.2f} mA**"
        f"（{off_cur1:.2f} vs {off_cur2:.2f} mA）。"
        f"场景对比累计一供多耗电 **{total_mah:.2f} mAh**，灭屏场景贡献 **{off_mah:.2f} mAh** 为主。"
    )
    lines.append("")

    cross_section = parse_topn_section(
        topn_text, "### 跨场景共性分析", "### 最值得优先验证/优化的关键点"
    )
    priority_section = parse_topn_section(
        topn_text, "### 最值得优先验证/优化的关键点", None
    )
    cross_items = parse_cross_items(cross_section)
    priority_items = parse_priority_items(priority_section)

    lines.append("**当前项目 DOU 问题分析汇总：**")
    lines.append("")
    if cross_items:
        for item in cross_items:
            lines.append(item)
    else:
        lines.append("（TopN AI 综合总结暂无，请先运行 run_topn_summary.py）")
    lines.append("")

    lines.append("**重点问题跟进:**")
    lines.append("")
    if priority_items:
        for item in priority_items:
            lines.append(item)
    else:
        lines.append("（暂无 AI 生成的跟进项）")
    lines.append("")

    lines.append("## 亮屏 Top15 深度分析（单场景）")
    lines.append("")
    for rank, scene in enumerate(top15.get("top_scenes", []), 1):
        suffix = scene["suffix"]
        desc = scene.get("desc", "")
        power_mah = scene.get("power_mah", "?")
        synthesis = build_scene_synthesis(suffix, SCREEN_ON)
        lines.append(f"### {rank}. 场景 {suffix} — {desc}（差异 {power_mah} mAh）")
        lines.append("")
        lines.append(f"**综合来看：**{synthesis}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    _setup_utf8_stdio()
    report = build_report()
    out = HIGH / "DOU完整分析报告.md"
    out.write_text(report, encoding="utf-8")
    print(f"written: {out}")
    print(f"lines: {len(report.splitlines())}")


if __name__ == "__main__":
    main()
