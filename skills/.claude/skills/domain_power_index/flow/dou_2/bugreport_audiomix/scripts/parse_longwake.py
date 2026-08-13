#!/usr/bin/env python3
"""Parse bugreport txt for ALL longwake (long wakelock) timeline events."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from parse_audiomix import (
    DURATION_BUCKETS,
    BUCKET_COLORS,
    build_uid_map,
    duration_bucket,
    find_bugreport_txt,
    format_duration_ms,
    infer_year,
    parse_timestamp,
    resolve_owner_label,
    short_app_name,
)

TS_RE = re.compile(r"(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})")
EVENT_RE = re.compile(r"(?P<sign>[+-])?(?P<kind>longwake)=(?P<rest>[^\s]+)")


def parse_longwake_rest(rest: str) -> Tuple[str, str]:
    if ":" in rest:
        owner, tag = rest.split(":", 1)
        return owner, tag.strip('"')
    return rest, rest


@dataclass
class LongwakeEvent:
    line_no: int
    timestamp: str
    dt: str
    action: str
    owner: str
    tag: str
    owner_label: str
    raw: str


@dataclass
class LongwakeInterval:
    owner: str
    tag: str
    owner_label: str
    start: str
    end: Optional[str]
    duration_ms: int
    duration_text: str
    bucket: str
    procstate: str = ""
    incomplete: bool = False


@dataclass
class LongwakeReport:
    bugreport_txt: str
    generated_at: str
    uid_map: Dict[str, str] = field(default_factory=dict)
    timeline_events: List[LongwakeEvent] = field(default_factory=list)
    intervals: List[LongwakeInterval] = field(default_factory=list)
    by_owner_totals: Dict[str, dict] = field(default_factory=dict)
    by_tag_totals: Dict[str, dict] = field(default_factory=dict)
    by_category_totals: Dict[str, dict] = field(default_factory=dict)
    by_bucket: Dict[str, List[dict]] = field(default_factory=dict)


def parse_timeline_events(text: str, uid_map: Dict[str, str], year: int) -> List[LongwakeEvent]:
    events: List[LongwakeEvent] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if "longwake" not in line:
            continue
        ts_m = TS_RE.search(line)
        if not ts_m:
            continue
        ts_str = ts_m.group(1)
        dt = parse_timestamp(ts_str, year).isoformat(sep=" ")
        raw = line.strip()
        for ev_m in EVENT_RE.finditer(line):
            sign = ev_m.group("sign") or ""
            owner, tag = parse_longwake_rest(ev_m.group("rest"))
            if sign == "-":
                action = "release"
            elif sign == "+":
                action = "acquire"
            else:
                action = "held_at_start"
            events.append(
                (
                    ev_m.start(),
                    LongwakeEvent(
                        line_no=line_no,
                        timestamp=ts_str,
                        dt=dt,
                        action=action,
                        owner=owner,
                        tag=tag,
                        owner_label=resolve_owner_label(owner, uid_map),
                        raw=raw,
                    ),
                )
            )
    events.sort(key=lambda item: (item[1].dt, item[1].line_no, item[0]))
    return [ev for _, ev in events]


def build_intervals(events: List[LongwakeEvent]) -> List[LongwakeInterval]:
    open_locks: Dict[Tuple[str, str], LongwakeEvent] = {}
    intervals: List[LongwakeInterval] = []

    for ev in events:
        key = (ev.owner, ev.tag)
        if ev.action in ("acquire", "held_at_start"):
            if key not in open_locks:
                open_locks[key] = ev
            continue
        if ev.action == "release":
            start_ev = open_locks.pop(key, None)
            if start_ev is None:
                continue
            start_dt = datetime.fromisoformat(start_ev.dt)
            end_dt = datetime.fromisoformat(ev.dt)
            dur_ms = max(0, int((end_dt - start_dt).total_seconds() * 1000))
            procstate = ""
            pm = re.search(r"procstate:\s*(.+?)\s*$", ev.raw)
            if pm:
                procstate = pm.group(1)
            sec = dur_ms / 1000.0
            intervals.append(
                LongwakeInterval(
                    owner=ev.owner,
                    tag=ev.tag,
                    owner_label=ev.owner_label,
                    start=start_ev.timestamp,
                    end=ev.timestamp,
                    duration_ms=dur_ms,
                    duration_text=format_duration_ms(dur_ms),
                    bucket=duration_bucket(sec),
                    procstate=procstate,
                    incomplete=False,
                )
            )

    for (owner, tag), start_ev in sorted(open_locks.items()):
        intervals.append(
            LongwakeInterval(
                owner=owner,
                tag=tag,
                owner_label=start_ev.owner_label,
                start=start_ev.timestamp,
                end=None,
                duration_ms=-1,
                duration_text="未释放(至 bugreport 结束)",
                bucket="未闭合",
                incomplete=True,
            )
        )

    intervals.sort(key=lambda x: (x.start, x.owner, x.tag))
    return intervals


def aggregate_by_owner(intervals: List[LongwakeInterval]) -> Dict[str, dict]:
    totals: Dict[str, dict] = {}
    for itv in intervals:
        if itv.incomplete:
            continue
        rec = totals.setdefault(
            itv.owner,
            {
                "owner": itv.owner,
                "owner_label": itv.owner_label,
                "interval_count": 0,
                "timeline_total_ms": 0,
                "max_single_ms": 0,
                "tags": set(),
            },
        )
        rec["interval_count"] += 1
        rec["timeline_total_ms"] += itv.duration_ms
        rec["max_single_ms"] = max(rec["max_single_ms"], itv.duration_ms)
        rec["tags"].add(itv.tag)

    for rec in totals.values():
        rec["tags"] = sorted(rec["tags"])
        rec["timeline_total_text"] = format_duration_ms(rec["timeline_total_ms"])
        rec["max_single_text"] = format_duration_ms(rec["max_single_ms"])
    return dict(sorted(totals.items(), key=lambda kv: kv[1]["timeline_total_ms"], reverse=True))


def aggregate_by_tag(intervals: List[LongwakeInterval]) -> Dict[str, dict]:
    totals: Dict[str, dict] = {}
    for itv in intervals:
        if itv.incomplete:
            continue
        rec = totals.setdefault(
            itv.tag,
            {
                "tag": itv.tag,
                "interval_count": 0,
                "timeline_total_ms": 0,
                "max_single_ms": 0,
                "owners": set(),
            },
        )
        rec["interval_count"] += 1
        rec["timeline_total_ms"] += itv.duration_ms
        rec["max_single_ms"] = max(rec["max_single_ms"], itv.duration_ms)
        rec["owners"].add(itv.owner_label)

    for rec in totals.values():
        rec["owners"] = sorted(rec["owners"])
        rec["timeline_total_text"] = format_duration_ms(rec["timeline_total_ms"])
        rec["max_single_text"] = format_duration_ms(rec["max_single_ms"])
    return dict(sorted(totals.items(), key=lambda kv: kv[1]["timeline_total_ms"], reverse=True))


def bucket_intervals(intervals: List[LongwakeInterval]) -> Dict[str, List[dict]]:
    buckets: Dict[str, List[dict]] = {label: [] for label, _, _ in DURATION_BUCKETS}
    buckets["未闭合"] = []
    for itv in intervals:
        key = itv.bucket if itv.bucket in buckets else "未闭合"
        buckets.setdefault(key, []).append(asdict(itv))
    return {k: v for k, v in buckets.items() if v}


def analyze_bugreport(path: Path) -> LongwakeReport:
    txt_path = find_bugreport_txt(path)
    text = txt_path.read_text(encoding="utf-8", errors="replace")
    year = infer_year(text.splitlines())
    uid_map = build_uid_map(text)
    events = parse_timeline_events(text, uid_map, year)
    intervals = build_intervals(events)
    return LongwakeReport(
        bugreport_txt=str(txt_path),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        uid_map=uid_map,
        timeline_events=events,
        intervals=intervals,
        by_owner_totals=aggregate_by_owner(intervals),
        by_tag_totals=aggregate_by_tag(intervals),
        by_category_totals=aggregate_by_category(intervals),
        by_bucket=bucket_intervals(intervals),
    )


def _report_year(report: LongwakeReport) -> int:
    if report.timeline_events:
        return int(report.timeline_events[0].dt[:4])
    return datetime.now().year


def _ts_to_dt(ts: str, year: int) -> datetime:
    return parse_timestamp(ts, year)


def _timeline_range(report: LongwakeReport) -> Tuple[Optional[datetime], Optional[datetime], int]:
    year = _report_year(report)
    dts: List[datetime] = []
    for ev in report.timeline_events:
        dts.append(_ts_to_dt(ev.timestamp, year))
    for itv in report.intervals:
        if itv.incomplete:
            continue
        dts.append(_ts_to_dt(itv.start, year))
        if itv.end:
            dts.append(_ts_to_dt(itv.end, year))
    if not dts:
        return None, None, year
    return min(dts), max(dts), year


def _short_tag(tag: str) -> str:
    if tag == "AudioMix":
        return "AudioMix"
    if tag.startswith("*job*"):
        return tag.split("/")[-1] if "/" in tag else tag[:40]
    if tag.startswith("*gms_scheduler*"):
        return tag.split("/")[-1] if "/" in tag else tag[:40]
    if len(tag) > 36:
        return tag[:33] + "..."
    return tag


# 泳道图大类（顺序即展示顺序）
CATEGORY_ORDER = [
    "AudioMix（音频播放）",
    "音频采集/通话",
    "后台 Job",
    "GMS 调度",
    "媒体播放器",
    "系统/其他",
]

CATEGORY_COLORS = {
    "AudioMix（音频播放）": "#2563eb",
    "音频采集/通话": "#7c3aed",
    "后台 Job": "#ea580c",
    "GMS 调度": "#0891b2",
    "媒体播放器": "#ca8a04",
    "系统/其他": "#64748b",
}


def tag_category(tag: str) -> str:
    if tag == "AudioMix":
        return "AudioMix（音频播放）"
    if tag == "AudioIn" or "VoiceService" in tag:
        return "音频采集/通话"
    if (
        tag.startswith("*job*")
        or "JobService" in tag
        or "JobInfoScheduler" in tag
        or "SystemJobService" in tag
    ):
        return "后台 Job"
    if tag.startswith("*gms_scheduler*") or (
        tag.startswith(".") and "Service" in tag
    ):
        return "GMS 调度"
    if "ExoPlayer" in tag or "WakeLockManager" in tag:
        return "媒体播放器"
    return "系统/其他"


def aggregate_by_category(intervals: List[LongwakeInterval]) -> Dict[str, dict]:
    totals: Dict[str, dict] = {}
    for itv in intervals:
        if itv.incomplete:
            continue
        cat = tag_category(itv.tag)
        rec = totals.setdefault(
            cat,
            {
                "category": cat,
                "interval_count": 0,
                "timeline_total_ms": 0,
                "max_single_ms": 0,
                "tags": set(),
                "owners": set(),
            },
        )
        rec["interval_count"] += 1
        rec["timeline_total_ms"] += itv.duration_ms
        rec["max_single_ms"] = max(rec["max_single_ms"], itv.duration_ms)
        rec["tags"].add(itv.tag)
        rec["owners"].add(itv.owner_label)

    for rec in totals.values():
        rec["tags"] = sorted(rec["tags"])
        rec["owners"] = sorted(rec["owners"])
        rec["timeline_total_text"] = format_duration_ms(rec["timeline_total_ms"])
        rec["max_single_text"] = format_duration_ms(rec["max_single_ms"])

    ordered: Dict[str, dict] = {}
    for cat in CATEGORY_ORDER:
        if cat in totals:
            ordered[cat] = totals[cat]
    for cat, rec in totals.items():
        if cat not in ordered:
            ordered[cat] = rec
    return ordered


def format_timeline_visual(report: LongwakeReport) -> str:
    lines: List[str] = []
    year = _report_year(report)
    t_min, t_max, _ = _timeline_range(report)
    if t_min and t_max:
        span = t_max - t_min
        lines.append(
            f"时间范围: {t_min.strftime('%m-%d %H:%M:%S')} ~ "
            f"{t_max.strftime('%m-%d %H:%M:%S')} "
            f"(跨度 {format_duration_ms(int(span.total_seconds() * 1000))})"
        )
    lines.append("")
    lines.append("图例: ▶持锁开始  ■持锁结束  ○日志起点已持锁  ──持锁区间条")
    lines.append("")

    release_map: Dict[str, LongwakeInterval] = {}
    for itv in report.intervals:
        if itv.end and not itv.incomplete:
            release_map[f"{itv.end}|{itv.owner}|{itv.tag}"] = itv

    open_holds: Dict[Tuple[str, str], LongwakeEvent] = {}
    action_sym = {"acquire": "▶", "release": "■", "held_at_start": "○"}
    action_cn = {"acquire": "持锁+", "release": "释锁-", "held_at_start": "已持锁"}

    for ev in report.timeline_events:
        sym = action_sym.get(ev.action, "·")
        app = short_app_name(ev.owner_label, report.uid_map)
        tag = _short_tag(ev.tag)
        head = f"{ev.timestamp}  {sym} [{action_cn.get(ev.action, ev.action):^4}] {tag:36} {app}"

        if ev.action in ("acquire", "held_at_start"):
            key = (ev.owner, ev.tag)
            if key not in open_holds:
                open_holds[key] = ev
            if len(open_holds) > 1:
                head += f"  (并行 {len(open_holds)} 路)"
            lines.append(head)
            continue

        if ev.action == "release":
            key = (ev.owner, ev.tag)
            open_holds.pop(key, None)
            itv = release_map.get(f"{ev.timestamp}|{ev.owner}|{ev.tag}")
            if itv:
                bar_len = min(40, max(4, itv.duration_ms // 15000))
                bar = "━" * bar_len
                ps = f" | {itv.procstate}" if itv.procstate else ""
                lines.append(
                    f"{head}  │ {bar} {itv.duration_text} │ [{itv.bucket}]{ps}"
                )
            else:
                lines.append(f"{head}  (无配对开始事件)")
            continue

        lines.append(head)

    lines.append("")
    lines.append("【持锁区间条带图】(按开始时间排序，宽度∝时长)")
    lines.append("")
    complete = [i for i in report.intervals if not i.incomplete]
    complete.sort(key=lambda x: x.start)
    if not complete:
        lines.append("  (无完整区间)")
        return "\n".join(lines)

    max_ms = max(i.duration_ms for i in complete) or 1
    for itv in complete:
        app = short_app_name(itv.owner_label, report.uid_map)
        tag = _short_tag(itv.tag)
        bar_len = max(2, int(itv.duration_ms / max_ms * 36))
        bar = "█" * bar_len
        end = itv.end or "?"
        lines.append(
            f"  {itv.start} ─{bar}─ {end}  "
            f"{itv.duration_text:>12}  {app} / {tag}  [{itv.bucket}]"
        )
    return "\n".join(lines)


def format_text_report(report: LongwakeReport) -> str:
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("Bugreport 全部 Long Wakelock 分析")
    lines.append("=" * 72)
    lines.append(f"源文件: {report.bugreport_txt}")
    lines.append(f"生成时间: {report.generated_at}")
    lines.append(f"事件数: {len(report.timeline_events)}")
    lines.append(
        f"完整区间: {sum(1 for i in report.intervals if not i.incomplete)} | "
        f"未闭合: {sum(1 for i in report.intervals if i.incomplete)}"
    )
    lines.append("")

    lines.append("=" * 72)
    lines.append("【主视图】全部 longwake 时间轴")
    lines.append("=" * 72)
    lines.append(format_timeline_visual(report))
    lines.append("")

    lines.append("【按 Tag 类型累计】")
    for rec in report.by_tag_totals.values():
        owners = ", ".join(short_app_name(o, report.uid_map) for o in rec["owners"][:5])
        if len(rec["owners"]) > 5:
            owners += f" +{len(rec['owners']) - 5}"
        lines.append(
            f"  - {_short_tag(rec['tag']):36} | "
            f"{rec['interval_count']:2} 段 | 合计 {rec['timeline_total_text']:>12} | "
            f"最长 {rec['max_single_text']:>12} | {owners}"
        )
    lines.append("")

    lines.append("【按持锁方累计】")
    for rec in report.by_owner_totals.values():
        tags = ", ".join(_short_tag(t) for t in rec["tags"][:4])
        if len(rec["tags"]) > 4:
            tags += f" +{len(rec['tags']) - 4}"
        lines.append(
            f"  - {rec['owner_label']:45} | "
            f"{rec['interval_count']:2} 段 | 合计 {rec['timeline_total_text']:>12} | "
            f"最长 {rec['max_single_text']:>12} | tags: {tags}"
        )
    lines.append("")

    lines.append("【按时长分桶明细】")
    for label, _, _ in DURATION_BUCKETS:
        items = report.by_bucket.get(label, [])
        lines.append(f"  {label}: {len(items)} 段")
        for itv in items:
            end = itv.get("end") or "未释放"
            tag = _short_tag(itv.get("tag", ""))
            ps = f" procstate={itv['procstate']}" if itv.get("procstate") else ""
            lines.append(
                f"    {itv['start']} ~ {end} | {itv['owner_label']} | "
                f"{tag} | {itv['duration_text']}{ps}"
            )
    if report.by_bucket.get("未闭合"):
        lines.append(f"  未闭合: {len(report.by_bucket['未闭合'])} 段")
        for itv in report.by_bucket["未闭合"]:
            lines.append(
                f"    {itv['start']} ~ 未释放 | {itv['owner_label']} | {_short_tag(itv.get('tag', ''))}"
            )
    lines.append("")
    return "\n".join(lines)


def _html_pct(ts: str, year: int, t_min: datetime, span_ms: int) -> float:
    dt = _ts_to_dt(ts, year)
    return max(0.0, min(100.0, (dt - t_min).total_seconds() * 1000 / span_ms * 100))


def _render_bars(
    items: List[LongwakeInterval],
    *,
    year: int,
    t_min: datetime,
    span_ms: int,
    t_max_s: str,
    uid_map: Dict[str, str],
    cat: str,
    cat_color: str,
    bar_height: str = "22px",
    bar_top: str = "3px",
) -> str:
    bars: List[str] = []
    for itv in sorted(items, key=lambda x: x.start):
        left = _html_pct(itv.start, year, t_min, span_ms)
        end_ts = itv.end or t_max_s
        width = max(0.3, _html_pct(end_ts, year, t_min, span_ms) - left)
        bar_color = BUCKET_COLORS.get(itv.bucket, cat_color)
        app = short_app_name(itv.owner_label, uid_map)
        title = (
            f"[{cat}]\\n{app} / {_short_tag(itv.tag)}\\n"
            f"{itv.start} ~ {itv.end or '未释放'}\\n"
            f"{itv.duration_text} [{itv.bucket}]"
        )
        bars.append(
            f'<div class="bar" style="left:{left:.2f}%;width:{width:.2f}%;top:{bar_top};height:{bar_height};'
            f'background:{bar_color};border-left:2px solid {cat_color}" '
            f'title="{title}"></div>'
        )
    return "".join(bars)


def _render_lane_row(
    label_html: str,
    bars_html: str,
    total_text: str,
    *,
    css_class: str = "lane",
    track_height: str = "28px",
) -> str:
    return (
        f'<div class="{css_class}"><div class="lane-label">{label_html}</div>'
        f'<div class="lane-track" style="height:{track_height}">{bars_html}</div>'
        f'<div class="lane-total-col">{total_text}</div></div>'
    )


def format_html_report(report: LongwakeReport) -> str:
    year = _report_year(report)
    t_min, t_max, _ = _timeline_range(report)
    if not t_min or not t_max:
        return "<html><body><p>无 longwake 时间轴数据</p></body></html>"

    span_ms = max(1, int((t_max - t_min).total_seconds() * 1000))
    t_min_s = t_min.strftime("%m-%d %H:%M:%S")
    t_max_s = t_max.strftime("%m-%d %H:%M:%S")

    # 按大类聚合
    by_cat: Dict[str, List[LongwakeInterval]] = {cat: [] for cat in CATEGORY_ORDER}
    incomplete: List[LongwakeInterval] = []
    for itv in report.intervals:
        if itv.incomplete:
            incomplete.append(itv)
            continue
        by_cat.setdefault(tag_category(itv.tag), []).append(itv)

    # ── 上图：大类总览 ──
    overview_html: List[str] = []
    for cat in CATEGORY_ORDER:
        items = by_cat.get(cat, [])
        if not items:
            continue
        cat_color = CATEGORY_COLORS.get(cat, "#64748b")
        total_text = format_duration_ms(sum(i.duration_ms for i in items))
        top_apps = [
            short_app_name(o, report.uid_map)
            for o in sorted(
                {i.owner_label for i in items},
                key=lambda lbl: sum(x.duration_ms for x in items if x.owner_label == lbl),
                reverse=True,
            )[:4]
        ]
        apps_hint = ", ".join(top_apps)
        extra = len({i.owner_label for i in items}) - len(top_apps)
        if extra > 0:
            apps_hint += f" +{extra}"
        label = (
            f'<span class="cat-dot" style="background:{cat_color}"></span>{cat}'
            f'<span class="lane-sub">{len(items)}段 · {apps_hint}</span>'
            f'<span class="lane-total">Σ {total_text}</span>'
        )
        bars = _render_bars(
            items,
            year=year,
            t_min=t_min,
            span_ms=span_ms,
            t_max_s=t_max_s,
            uid_map=report.uid_map,
            cat=cat,
            cat_color=cat_color,
        )
        overview_html.append(_render_lane_row(label, bars, total_text))

    if incomplete:
        bars = []
        for itv in incomplete:
            left = _html_pct(itv.start, year, t_min, span_ms)
            width = max(0.3, 100.0 - left)
            title = f"未闭合\\n{itv.owner_label}\\n{_short_tag(itv.tag)}\\n自 {itv.start}"
            bars.append(
                f'<div class="bar incomplete" style="left:{left:.2f}%;width:{width:.2f}%;'
                f'background:#9333ea" title="{title}"></div>'
            )
        label = (
            '<span class="cat-dot" style="background:#9333ea"></span>未闭合'
            f'<span class="lane-sub">{len(incomplete)}段</span>'
        )
        overview_html.append(_render_lane_row(label, "".join(bars), "—"))

    # ── 下图：各大类内按应用细分 ──
    detail_html: List[str] = []
    for cat in CATEGORY_ORDER:
        items = by_cat.get(cat, [])
        if not items:
            continue
        cat_color = CATEGORY_COLORS.get(cat, "#64748b")
        cat_total = format_duration_ms(sum(i.duration_ms for i in items))

        # 大类标题行
        detail_html.append(
            f'<div class="cat-header">'
            f'<span class="cat-dot" style="background:{cat_color}"></span>'
            f'{cat}<span class="cat-header-meta">{len(items)}段 · Σ {cat_total}</span>'
            f'</div>'
        )

        # 类内按 owner 分组
        by_owner: Dict[str, List[LongwakeInterval]] = {}
        for itv in items:
            by_owner.setdefault(itv.owner_label, []).append(itv)

        for owner_label, owner_items in sorted(
            by_owner.items(),
            key=lambda kv: sum(x.duration_ms for x in kv[1]),
            reverse=True,
        ):
            app = short_app_name(owner_label, report.uid_map)
            tags = sorted({ _short_tag(i.tag) for i in owner_items })
            tag_hint = tags[0] if len(tags) == 1 else f"{tags[0]} +{len(tags)-1}"
            owner_total = format_duration_ms(sum(i.duration_ms for i in owner_items))
            label = (
                f'<span class="detail-indent"></span>'
                f'<span class="detail-app">{app}</span>'
                f'<span class="lane-sub">{len(owner_items)}段 · {tag_hint}</span>'
            )
            bars = _render_bars(
                owner_items,
                year=year,
                t_min=t_min,
                span_ms=span_ms,
                t_max_s=t_max_s,
                uid_map=report.uid_map,
                cat=cat,
                cat_color=cat_color,
                bar_height="18px",
                bar_top="2px",
            )
            detail_html.append(
                _render_lane_row(
                    label, bars, owner_total,
                    css_class="lane lane-detail",
                    track_height="22px",
                )
            )

    if incomplete:
        detail_html.append(
            '<div class="cat-header">'
            '<span class="cat-dot" style="background:#9333ea"></span>'
            f'未闭合<span class="cat-header-meta">{len(incomplete)}段</span></div>'
        )
        for itv in incomplete:
            app = short_app_name(itv.owner_label, report.uid_map)
            left = _html_pct(itv.start, year, t_min, span_ms)
            width = max(0.3, 100.0 - left)
            title = f"未闭合\\n{itv.owner_label}\\n{_short_tag(itv.tag)}\\n自 {itv.start}"
            bars = (
                f'<div class="bar incomplete" style="left:{left:.2f}%;width:{width:.2f}%;'
                f'background:#9333ea" title="{title}"></div>'
            )
            label = (
                f'<span class="detail-indent"></span>'
                f'<span class="detail-app">{app}</span>'
                f'<span class="lane-sub">{_short_tag(itv.tag)}</span>'
            )
            detail_html.append(
                _render_lane_row(label, bars, "—", css_class="lane lane-detail", track_height="22px")
            )

    cat_rows = ""
    for rec in report.by_category_totals.values():
        apps = ", ".join(
            short_app_name(o, report.uid_map) for o in rec["owners"][:5]
        )
        if len(rec["owners"]) > 5:
            apps += f" +{len(rec['owners']) - 5}"
        cat_rows += (
            f"<tr><td>{rec['category']}</td>"
            f"<td>{rec['interval_count']}</td>"
            f"<td>{rec['timeline_total_text']}</td>"
            f"<td>{rec['max_single_text']}</td>"
            f"<td>{apps}</td></tr>"
        )

    owner_rows = ""
    for rec in report.by_owner_totals.values():
        cats = sorted({ tag_category(t) for t in rec["tags"] })
        owner_rows += (
            f"<tr><td>{short_app_name(rec['owner_label'], report.uid_map)}</td>"
            f"<td>{rec['owner_label']}</td>"
            f"<td>{', '.join(cats)}</td>"
            f"<td>{rec['interval_count']}</td>"
            f"<td>{rec['timeline_total_text']}</td>"
            f"<td>{rec['max_single_text']}</td></tr>"
        )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>全部 Long Wakelock 时间轴</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 16px; background: #f8fafc; color: #0f172a; }}
h1 {{ font-size: 1.25rem; }}
h2 {{ font-size: 1rem; margin-top: 28px; }}
.meta {{ color: #64748b; font-size: 0.875rem; margin-bottom: 16px; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 12px 0 16px; font-size: 0.75rem; }}
.legend-item {{ display: flex; align-items: center; gap: 4px; }}
.cat-dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 4px; vertical-align: middle; }}
.lane {{ display: grid; grid-template-columns: 220px 1fr 90px; gap: 8px; margin: 8px 0; align-items: center; }}
.lane-detail {{ margin: 4px 0; }}
.lane-label {{ font-size: 0.8rem; font-weight: 600; }}
.lane-sub {{ display: block; font-size: 0.65rem; font-weight: 400; color: #64748b; margin-top: 2px; }}
.lane-total {{ color: #64748b; font-size: 0.7rem; margin-left: 4px; }}
.lane-track {{ position: relative; height: 28px; background: #e2e8f0; border-radius: 4px; }}
.bar {{ position: absolute; top: 3px; height: 22px; border-radius: 3px; opacity: 0.88; cursor: default; }}
.bar.incomplete {{ opacity: 0.5; background: repeating-linear-gradient(45deg,#9333ea,#9333ea 4px,#a855f7 4px,#a855f7 8px)!important; }}
.lane-total-col {{ font-size: 0.75rem; text-align: right; font-weight: 600; }}
.cat-header {{ font-size: 0.85rem; font-weight: 700; margin: 18px 0 6px; padding: 6px 10px; background: #e2e8f0; border-radius: 4px; border-left: 4px solid #64748b; }}
.cat-header-meta {{ font-size: 0.7rem; font-weight: 400; color: #64748b; margin-left: 8px; }}
.detail-indent {{ display: inline-block; width: 12px; }}
.detail-app {{ font-weight: 500; }}
.section-hint {{ font-size: 0.75rem; color: #64748b; margin: 4px 0 12px; }}
.detail-block {{ border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px 12px 12px; background: #fff; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 16px; font-size: 0.875rem; }}
th, td {{ border: 1px solid #cbd5e1; padding: 6px 8px; text-align: left; }}
th {{ background: #e2e8f0; }}
</style>
</head>
<body>
<h1>Bugreport 全部 Long Wakelock 时间轴</h1>
<div class="meta">
源: {report.bugreport_txt}<br/>
时间: {t_min_s} ~ {t_max_s} | 事件 {len(report.timeline_events)} | 区间 {sum(1 for i in report.intervals if not i.incomplete)}
</div>
<div class="legend">
{"".join(f'<span class="legend-item"><span class="cat-dot" style="background:{CATEGORY_COLORS[c]}"></span>{c}</span>' for c in CATEGORY_ORDER if c in report.by_category_totals)}
</div>

<h2>总览泳道（按大类）</h2>
<p class="section-hint">条带颜色 = 持锁时长分桶；悬停查看应用与 tag 详情</p>
{"".join(overview_html)}

<h2>细分泳道（大类 → 应用）</h2>
<p class="section-hint">各大类下按持锁应用展开，同一应用的多段 tag 合并到一行</p>
<div class="detail-block">
{"".join(detail_html)}
</div>

<h2>按大类汇总</h2>
<table><thead><tr><th>大类</th><th>段数</th><th>合计</th><th>最长单段</th><th>主要应用</th></tr></thead>
<tbody>{cat_rows}</tbody></table>

<h2>按应用汇总</h2>
<table><thead><tr><th>应用</th><th>UID/包名</th><th>涉及大类</th><th>段数</th><th>合计</th><th>最长单段</th></tr></thead>
<tbody>{owner_rows}</tbody></table>
</body>
</html>"""


def report_to_json(report: LongwakeReport) -> dict:
    return {
        "bugreport_txt": report.bugreport_txt,
        "generated_at": report.generated_at,
        "event_count": len(report.timeline_events),
        "interval_count": sum(1 for i in report.intervals if not i.incomplete),
        "incomplete_count": sum(1 for i in report.intervals if i.incomplete),
        "uid_map": report.uid_map,
        "by_owner_totals": report.by_owner_totals,
        "by_tag_totals": report.by_tag_totals,
        "by_category_totals": report.by_category_totals,
        "by_bucket": report.by_bucket,
        "intervals": [asdict(i) for i in report.intervals],
        "timeline_events": [asdict(e) for e in report.timeline_events],
    }
