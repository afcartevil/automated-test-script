"""Task-level HTML report aligned with the Patch Analysis page UI."""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from web_app.app_paths import data_dir, setup_sys_path, tools_dir

setup_sys_path()

from render_report_llm import render_patch


def esc(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _score_color(score: Any) -> str:
    try:
        value = float(score or 0)
    except (TypeError, ValueError):
        value = 0.0
    if value >= 7:
        return "#0f766e"
    if value >= 4:
        return "#a16207"
    return "#b91c1c"


def _format_score(score: Any) -> str:
    try:
        value = float(score or 0)
    except (TypeError, ValueError):
        return "-"
    return f"{value:.1f}"


def _simple_markdown(text: str) -> str:
    """Lightweight markdown → HTML close to the analysis page summary renderer."""
    raw = str(text or "").strip()
    if not raw:
        return ""
    rendered = esc(raw)
    rendered = rendered.replace("\n\n", "</p><p>")
    rendered = rendered.replace("\n", "<br>")
    rendered = re.sub(r"####\s+(.+?)(?=<br>|</p>|$)", r'<h4 class="md-h4">\1</h4>', rendered)
    rendered = re.sub(r"###\s+(.+?)(?=<br>|</p>|$)", r'<strong class="md-h3">\1</strong>', rendered)
    rendered = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", rendered)
    rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
    rendered = re.sub(r"(?:^|<br>|</p>)[\*\-]\s+(.+?)(?=<br>|</p>|$)", r"<li>\1</li>", rendered)
    rendered = re.sub(r"(?:<li>.*?</li>)+", lambda m: f"<ul>{m.group(0)}</ul>", rendered)
    if not rendered.startswith("<"):
        rendered = f"<p>{rendered}</p>"
    return rendered


def _patch_data(row: Dict[str, Any]) -> Dict[str, Any]:
    data = row.get("data")
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            data = {}
    if not isinstance(data, dict):
        data = {}
    merged = dict(data)
    for key in ("sha", "title", "score", "recommendation", "key_risk", "dev_module"):
        if row.get(key) and not merged.get(key):
            merged[key] = row[key]
    if not merged.get("sha") and row.get("sha"):
        merged["sha"] = row["sha"]
    if not merged.get("commit") and merged.get("sha"):
        merged["commit"] = merged["sha"]
    return merged


def _render_stat_cards(summary: Dict[str, Any], total: int, analyzed: int, avg_score: float) -> str:
    cards = [
        (summary.get("total") or total, "总 Patch 数"),
        (summary.get("llm_analyzed") or 0, "LLM 分析"),
        (summary.get("script_analyzed") or max(0, analyzed - int(summary.get("llm_analyzed") or 0)), "脚本分析"),
        (summary.get("blocked") or 0, "阻断"),
        (summary.get("avg_score") if summary.get("avg_score") is not None else avg_score, "平均分"),
    ]
    parts = []
    for value, label in cards:
        parts.append(
            f'<div class="stat-card"><div class="stat-value">{esc(value)}</div>'
            f'<div class="stat-label">{esc(label)}</div></div>'
        )
    return f'<div class="summary-grid">{"".join(parts)}</div>'


def _render_tag_pills(tag_counts: Dict[str, Any]) -> str:
    if not tag_counts:
        return ""
    items = sorted(tag_counts.items(), key=lambda item: -int(item[1] or 0))
    pills = "".join(
        f'<span class="tag-pill">{esc(label)} <strong>{esc(count)}</strong></span>'
        for label, count in items[:16]
    )
    return (
        '<div class="summary-block">'
        '<div class="section-title">🏷️ 标签分布</div>'
        f'<div class="tag-row">{pills}</div>'
        "</div>"
    )


def _render_markdown_section(title: str, text: str, *, section_id: str = "", bare: bool = False) -> str:
    body = _simple_markdown(text)
    if not body:
        return ""
    if bare:
        return (
            f'<div class="summary-block">'
            f'<div class="section-title">{esc(title)}</div>'
            f'<div class="prose">{body}</div>'
            f"</div>"
        )
    sid = f' id="{esc(section_id)}"' if section_id else ""
    return (
        f'<section class="report-section analysis-anchor"{sid}>'
        f'<div class="section-title">{esc(title)}</div>'
        f'<div class="prose">{body}</div>'
        f"</section>"
    )


def _render_test_suggestions(summary: Dict[str, Any]) -> str:
    llm_text = str(summary.get("test_summary_llm") or "").strip()
    if llm_text:
        return _render_markdown_section(
            "🧪 综合测试建议（LLM）",
            llm_text,
            section_id="report-section-tests",
        )

    suggestions = summary.get("test_suggestions") or {}
    if not isinstance(suggestions, dict):
        return ""
    field_labels = {
        "unit_test": "单元测试",
        "integration_test": "集成测试",
        "regression_test": "回归测试",
        "manual_validation": "手工验证",
        "release_safeguard": "上线保障",
    }
    blocks = []
    for key, label in field_labels.items():
        items = suggestions.get(key) or []
        if not items:
            continue
        pills = "".join(
            f'<span class="tag-pill" title="{esc(item.get("text"))}">'
            f'{esc(str(item.get("text") or "")[:60])} <strong>{esc(item.get("count") or 0)}</strong></span>'
            for item in items
            if isinstance(item, dict)
        )
        total = sum(int(item.get("count") or 0) for item in items if isinstance(item, dict))
        blocks.append(
            f'<div class="test-group"><strong>{esc(label)}</strong>'
            f'<span class="muted">（{total} 笔涉及）</span>'
            f'<div class="tag-row">{pills}</div></div>'
        )
    if not blocks:
        return ""
    return (
        '<section class="report-section analysis-anchor" id="report-section-tests">'
        '<div class="section-title">🧪 综合测试建议</div>'
        f'{"".join(blocks)}'
        "</section>"
    )


def _crash_badge_class(level: str) -> str:
    if level == "高":
        return "crash-high"
    if level == "中":
        return "crash-mid"
    return "crash-low"


def _encode_patches_attr(patches: List[Any]) -> str:
    briefs = []
    for brief in patches[:8]:
        if not isinstance(brief, dict):
            continue
        briefs.append(
            {
                "sha": str(brief.get("sha") or "")[:12],
                "full_sha": str(brief.get("full_sha") or brief.get("sha") or "")[:40],
                "title": str(brief.get("title") or "")[:120],
                "score": brief.get("score"),
                "key_risk": str(brief.get("key_risk") or ""),
                "crash_risk": str(brief.get("crash_risk") or ""),
                "llm_analyzed": bool(brief.get("llm_analyzed")),
                "summary": str(brief.get("summary") or "")[:500],
                "insertions": int(brief.get("insertions") or 0),
                "deletions": int(brief.get("deletions") or 0),
            }
        )
    if not briefs:
        return ""
    return esc(json.dumps(briefs, ensure_ascii=False))


def _render_code_tree_node(node: Any, depth: int = 0) -> str:
    if not isinstance(node, dict):
        return ""
    name = str(node.get("name") or "")
    node_type = str(node.get("type") or "dir")
    children = node.get("children") or []
    patch_count = int(node.get("patch_count") or 0)
    pad = max(0, depth) * 14

    if node_type == "file":
        patches = node.get("patches") or []
        if not isinstance(patches, list):
            patches = []
        patches_attr = _encode_patches_attr(patches)
        patch_rows = []
        for brief in patches[:8]:
            if not isinstance(brief, dict):
                continue
            sha = str(brief.get("sha") or brief.get("full_sha") or "")[:12]
            if not sha:
                continue
            title = esc(str(brief.get("title") or "")[:80])
            try:
                score_text = f"{float(brief.get('score')):.1f}"
            except (TypeError, ValueError):
                score_text = "-"
            badge = "llm-badge" if brief.get("llm_analyzed") else "script-badge"
            badge_text = "LLM" if brief.get("llm_analyzed") else "脚本"
            crash = esc(str(brief.get("crash_risk") or "").strip())
            crash_html = f'<span class="patch-head-crash">死机 {crash}</span>' if crash else ""
            key_risk = str(brief.get("key_risk") or "").strip()
            risk_html = ""
            if key_risk:
                none_risk = key_risk.lower() in {"无", "none", "n/a", "-", "—"}
                risk_cls = "patch-head-risk-none" if none_risk else "patch-head-risk-warn"
                risk_label = "核心风险：无明显" if none_risk else f"核心风险：{key_risk}"
                risk_html = f'<div class="patch-head-risk {risk_cls}">{esc(risk_label)}</div>'
            one_attr = _encode_patches_attr([brief])
            patch_rows.append(
                f'<div class="code-tree-patch-block" data-patches="{one_attr}">'
                f'<div class="code-tree-patch-head">'
                f'<span class="pill {badge}">{badge_text}</span>'
                f'<a class="sha-link" href="#patch-{esc(sha)}" data-jump-patch="{esc(sha)}">{esc(sha)}</a>'
                f'<span class="patch-head-title">{title}</span>'
                f'<span class="patch-head-score">{esc(score_text)}</span>'
                f"{crash_html}</div>{risk_html}</div>"
            )
        detail_body = "".join(patch_rows) or '<div class="code-tree-empty">无关联 patch</div>'
        detail = f'<div class="code-tree-file-detail">{detail_body}</div>'
        return (
            f'<details class="code-tree-node code-tree-file-node">'
            f'<summary class="code-tree-row code-tree-file-row" style="padding-left:{pad}px" '
            f'data-patches="{patches_attr}">'
            f'<span class="code-tree-toggle">▶</span>'
            f'<span class="code-tree-file">📄 {esc(name)}</span>'
            f'<span class="code-tree-count">({patch_count})</span>'
            f"</summary>{detail}</details>"
        )

    if name == "/":
        return "".join(_render_code_tree_node(child, 0) for child in children)

    # Match analysis page: only depth-0 dirs start expanded.
    open_attr = "open" if depth < 1 else ""
    child_html = "".join(_render_code_tree_node(child, depth + 1) for child in children)
    return (
        f'<details class="code-tree-node code-tree-dir-node" {open_attr}>'
        f'<summary class="code-tree-row" style="padding-left:{pad}px">'
        f'<span class="code-tree-toggle">▶</span>'
        f'<span class="code-tree-dir">📁 {esc(name)}</span>'
        f'<span class="code-tree-count">({patch_count})</span>'
        f"</summary>"
        f'<div class="code-tree-children">{child_html}</div>'
        f"</details>"
    )


def _render_module_card(name: str, mod: Dict[str, Any]) -> str:
    stats = mod.get("stats") or {}
    analysis = mod.get("analysis") or {}
    coverage = mod.get("coverage") or {}
    chunk_summaries = mod.get("chunk_summaries") or []
    code_tree = mod.get("code_tree")

    crash = str(analysis.get("crash_risk") or "低").strip() or "低"
    meta_parts = [
        f'{int(stats.get("patch_count") or 0)} 笔',
        f'{int(stats.get("files_changed") or 0)} 文件',
        f'+{int(stats.get("insertions") or 0)}/-{int(stats.get("deletions") or 0)}',
        f'均分 {esc(stats.get("avg_score") or 0)}',
    ]
    if coverage.get("total_patch_count"):
        meta_parts.append(
            f'覆盖 {int(coverage.get("covered_patch_count") or 0)}/'
            f'{int(coverage.get("total_patch_count") or 0)}'
        )
    if int(coverage.get("chunk_count") or 0) > 1:
        meta_parts.append(f'{int(coverage.get("chunk_count") or 0)} chunks')

    badges = [f'<span class="crash-badge {_crash_badge_class(crash)}">死机 {esc(crash)}</span>']
    truncated = int(coverage.get("truncated_chunk_count") or 0) + int(
        coverage.get("split_exhausted_count") or 0
    )
    if truncated:
        badges.insert(
            0,
            f'<span class="coverage-badge coverage-warn">Diff 截断 {truncated}</span>',
        )
    elif coverage.get("auto_split"):
        badges.insert(0, '<span class="coverage-badge coverage-ok">已自动拆分</span>')

    body_parts: List[str] = []
    if truncated:
        body_parts.append(
            '<p class="coverage-hint muted">仅 diff 未全量入模；patch 摘要与高风险片段已覆盖，结论仍可用。</p>'
        )

    if chunk_summaries:
        chunk_html = []
        for chunk in chunk_summaries:
            if not isinstance(chunk, dict):
                continue
            head = (
                f'<div class="chunk-head"><strong>{esc(chunk.get("chunk_id"))}</strong>'
                f'<span class="muted">{int(chunk.get("patch_count") or 0)} 笔</span>'
            )
            if chunk.get("truncated_input"):
                head += '<span class="coverage-badge coverage-warn">Diff 截断</span>'
            head += "</div>"
            main = esc(chunk.get("main_changes") or "").replace("\n", "<br>")
            shas = chunk.get("covered_shas") or []
            sha_line = ""
            if shas:
                shown = ", ".join(esc(str(s)[:12]) for s in shas[:8])
                more = f" …(+{len(shas) - 8})" if len(shas) > 8 else ""
                sha_line = f'<div class="muted">覆盖: {shown}{more}</div>'
            chunk_html.append(
                f'<div class="chunk-item">{head}'
                f'{f"<div class=prose>{main}</div>" if main else ""}'
                f"{sha_line}</div>"
            )
        body_parts.append(
            f'<div class="module-card-section"><h4>🧩 Chunk 摘要 ({len(chunk_html)})</h4>'
            f'{"".join(chunk_html)}</div>'
        )

    def add_md(title: str, text: Any) -> None:
        rendered = _simple_markdown(str(text or ""))
        if rendered:
            body_parts.append(
                f'<div class="module-card-section"><h4>{esc(title)}</h4>'
                f'<div class="prose">{rendered}</div></div>'
            )

    add_md("📖 修改解读", analysis.get("modification_interpretation"))
    add_md("🎯 影响范围", analysis.get("impact_scope"))
    add_md("✅ 问题闭环", analysis.get("problem_closure_summary"))

    code_changes = analysis.get("code_changes") or []
    if isinstance(code_changes, list) and code_changes:
        items = []
        for change in code_changes:
            if not isinstance(change, dict):
                continue
            loc = esc(change.get("location") or "")
            risk = esc(change.get("risk_level") or "")
            expl = esc(change.get("explanation") or "")
            risk_html = f' <span class="muted">[{risk}]</span>' if risk else ""
            items.append(f"<li><code>{loc}</code>{risk_html} — {expl}</li>")
        if items:
            body_parts.append(
                '<div class="module-card-section"><h4>🔧 代码变化</h4>'
                f'<ul>{"".join(items)}</ul></div>'
            )

    tree_html = _render_code_tree_node(code_tree) if code_tree else ""
    body_parts.append(
        '<div class="module-card-section"><h4>🌳 代码树</h4>'
        '<div class="code-tree-hint">📁 点击目录展开/折叠 · 📄 点击文件查看关联 patch · 悬停查看分析摘要</div>'
        f'<div class="code-tree">{tree_html or "<div class=code-tree-empty>(无文件变更)</div>"}</div></div>'
    )

    add_md("🧪 测试建议", analysis.get("test_suggestions"))

    checklist = analysis.get("verification_checklist") or []
    if isinstance(checklist, list) and checklist:
        items = "".join(f"<li>{esc(item)}</li>" for item in checklist if item)
        if items:
            body_parts.append(
                '<div class="module-card-section"><h4>☑️ 验证清单</h4>'
                f"<ul>{items}</ul></div>"
            )

    crash_reason = esc(analysis.get("crash_risk_reason") or "")
    body_parts.append(
        '<div class="module-card-section"><h4>⚠️ 死机风险评估</h4>'
        f'<div><strong>{esc(crash)}</strong>'
        f'{f" — {crash_reason}" if crash_reason else ""}</div></div>'
    )

    high_risk = analysis.get("high_risk_patches") or []
    if isinstance(high_risk, list) and high_risk:
        rows = []
        for item in high_risk:
            if not isinstance(item, dict):
                continue
            sha = esc(str(item.get("sha") or "")[:12])
            title = esc(item.get("title") or "-")
            reason = esc(item.get("risk") or item.get("reason") or "")
            rows.append(
                f'<a class="risk-item" href="#patch-{sha}" data-jump-patch="{sha}">'
                f"<code>{sha}</code><span>{title}</span>"
                f'{f"<span class=reason-line>原因：{reason}</span>" if reason else ""}</a>'
            )
        if rows:
            body_parts.append(
                '<div class="module-card-section"><h4>🔴 高风险 Patch</h4>'
                f'<div class="risk-list">{"".join(rows)}</div></div>'
            )

    add_md("🔗 跨模块影响", analysis.get("cross_module_notes"))

    return f"""
<details class="module-card">
  <summary class="module-card-header">
    <div>
      <div class="module-card-title">{esc(name or "未分类")}</div>
      <div class="module-card-meta">{esc(" · ".join(meta_parts))}</div>
    </div>
    <div class="module-card-badges">{"".join(badges)}</div>
  </summary>
  <div class="module-card-body">{"".join(body_parts)}</div>
</details>"""


def _render_module_analysis(summary: Dict[str, Any]) -> str:
    ms = summary.get("module_summaries") or {}
    modules = ms.get("modules") if isinstance(ms, dict) else None
    if not isinstance(modules, dict) or not modules:
        return ""

    entries = sorted(
        modules.items(),
        key=lambda item: -int(((item[1] or {}).get("stats") or {}).get("patch_count") or 0),
    )
    cards = "".join(
        _render_module_card(name, mod if isinstance(mod, dict) else {})
        for name, mod in entries
    )
    coverage = summary.get("analysis_coverage") or {}
    coverage_line = ""
    if coverage.get("total_patches") or ms.get("total_patches"):
        complete = coverage.get("coverage_complete", ms.get("coverage_complete", True))
        badge = (
            '<span class="coverage-badge coverage-ok">全量覆盖</span>'
            if complete
            else '<span class="coverage-badge coverage-warn">部分 Diff 未完整取证</span>'
        )
        coverage_line = (
            f'<div class="module-coverage muted">已分析 '
            f'{esc(coverage.get("total_patches") or ms.get("total_patches") or 0)} 笔 patch · '
            f'{esc(coverage.get("module_count") or len(entries))} 个模块 · '
            f'{esc(coverage.get("total_chunks") or ms.get("total_chunks") or 0)} 个 chunk '
            f"{badge}</div>"
        )

    return (
        '<section class="report-section analysis-anchor" id="report-section-modules">'
        f'<div class="section-title">🗂 分模块分析'
        f'<span class="muted">（{len(entries)} 个模块）</span></div>'
        f"{coverage_line}"
        f'<div class="module-analysis-grid">{cards}</div>'
        "</section>"
    )


def _render_risk_list(title: str, items: List[Dict[str, Any]], *, kind: str = "risk", section_id: str = "") -> str:
    if not items:
        return ""
    rows = []
    for item in items:
        sha = esc(str(item.get("sha") or "")[:12])
        title_text = esc(item.get("title") or "-")
        extra = ""
        if kind == "future":
            fix_count = item.get("fix_count") or len(item.get("fixes") or [])
            tags = item.get("fix_tags") or []
            badge = f'<span class="future-badge">{esc(fix_count)} 笔后续修复</span>'
            tag_line = (
                f'<span class="muted">修复 tag：{esc("、".join(str(t) for t in tags[:4]))}</span>'
                if tags
                else ""
            )
            intro = esc(str(item.get("introducer_summary") or "")[:220])
            subjects = item.get("fix_subjects") or []
            subject_line = (
                f'<span class="reason-line">修复：{esc("；".join(str(s) for s in subjects[:3]))}</span>'
                if subjects
                else ""
            )
            intro_line = f'<span class="reason-line">引入：{intro}</span>' if intro else ""
            extra = f"{badge}{tag_line}{intro_line}{subject_line}"
        else:
            reason = esc(item.get("risk") or item.get("reason") or "")
            extra = f'<span class="reason-line">原因：{reason}</span>' if reason else ""
        rows.append(
            f'<a class="risk-item" href="#patch-{sha}" data-jump-patch="{sha}">'
            f'<code>{sha}</code><span>{title_text}</span>{extra}</a>'
        )
    sid = f' id="{esc(section_id)}"' if section_id else ""
    section_cls = "future-section" if kind == "future" else "risk-section"
    return (
        f'<section class="report-section analysis-anchor {section_cls}"{sid}>'
        f'<div class="section-title">{esc(title)}'
        f'<span class="muted">（{len(items)} 笔）</span></div>'
        f'<div class="risk-list">{"".join(rows)}</div>'
        "</section>"
    )


def render_monthly_analysis_html(task_id: str) -> str:
    """Render sub-tag analysis section for downloadable HTML report."""
    from web_app.analyzer_service import (
        build_monthly_tag_recommendation,
        get_progress,
        is_same_month_subtag_range,
    )
    from web_app.database import get_task

    task = get_task(task_id) or {}
    if is_same_month_subtag_range(
        str(task.get("from_tag") or ""),
        str(task.get("to_tag") or ""),
    ):
        return ""

    prog = get_progress(task_id)
    monthly = prog.get("monthly_recommendation") if prog else None
    raw = task.get("monthly_subtag_results") or ""
    if raw and not monthly:
        try:
            doc = json.loads(raw) if isinstance(raw, str) else dict(raw)
            if doc.get("embedded"):
                from web_app.monthly_subtag_service import (
                    build_monthly_tag_recommendation_from_results,
                )
                monthly = build_monthly_tag_recommendation_from_results(
                    doc.get("intervals") or [],
                )
        except Exception:
            monthly = None

    extend_ids = (prog or {}).get("extend_task_ids") or []
    if not monthly and extend_ids:
        try:
            monthly = build_monthly_tag_recommendation([task_id] + [e for e in extend_ids if e])
        except Exception:
            monthly = None

    if not monthly or not (monthly.get("has_recommendation") or monthly.get("range_stats")):
        return ""

    recommended = esc(str(monthly.get("recommended_tag") or "暂无结论"))
    reason = esc(str(monthly.get("reason") or ""))
    rows = []
    for item in monthly.get("range_stats") or []:
        risk = item.get("risk_distribution") or {}
        rows.append(
            "<tr>"
            f"<td class=\"mono\">{esc(item.get('from_tag'))} → {esc(item.get('to_tag'))}</td>"
            f"<td class=\"mono\">{esc(item.get('to_tag'))}</td>"
            f"<td>{int(item.get('total_patches') or 0)}</td>"
            f"<td>{esc(item.get('avg_score', 0))}</td>"
            f"<td>{esc(item.get('min_score', 0))}</td>"
            f"<td>高 {int(risk.get('high') or 0)} / 中 {int(risk.get('medium') or 0)} / "
            f"低 {int(risk.get('low') or 0)}</td>"
            f"<td>{int(item.get('has_future_fix_count') or 0)}</td>"
            "</tr>"
        )
    if not rows:
        return ""

    return f"""
<section class="report-section analysis-anchor" id="report-section-subtag">
  <div class="section-title">📅 目标月份子 tag 分析</div>
  <p class="muted section-hint">表格按相邻增量展示 diff（r1→r2、r2→r3…）；优选与合入结论按从月初 r1 累计到该 tag 评估</p>
  <p><strong>优选子 tag：</strong><span class="pill preferred">{recommended}</span></p>
  <p class="prose-inline">{reason}</p>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>子区间</th><th>目标子 tag</th><th>Patch</th>
          <th>平均分</th><th>最低分</th><th>风险分布</th><th>未来修复</th>
        </tr>
      </thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
  </div>
</section>"""


def _render_patch_item(index: int, patch: Dict[str, Any]) -> str:
    data = _patch_data(patch)
    sha = str(data.get("sha") or data.get("commit") or patch.get("sha") or "")
    sha12 = sha[:12]
    title = esc(data.get("title") or patch.get("title") or "-")
    score = data.get("score", patch.get("score"))
    score_text = _format_score(score)
    score_color = _score_color(score)
    is_llm = bool(data.get("llm_analyzed"))
    badge_cls = "llm-badge" if is_llm else "script-badge"
    badge_text = "LLM" if is_llm else "脚本"
    rec = esc(data.get("recommendation") or data.get("merge_advice") or "GKI 合入")
    module = esc(data.get("dev_module") or "")
    key_risk = esc(str(data.get("key_risk") or "").strip())
    crash = str(data.get("crash_risk") or "").strip()
    fixes = data.get("fix_in_future") or []
    meta_bits = []
    if module:
        meta_bits.append(f'<span class="tag-pill dev-module">{module}</span>')
    if fixes:
        meta_bits.append(
            f'<span class="pill defect-pill">⚠ 已知缺陷 · {len(fixes)} 笔修复</span>'
        )
    if crash == "高":
        meta_bits.append('<span class="pill crash-pill">🚨 死机风险</span>')
    if data.get("blocked"):
        meta_bits.append('<span class="pill blocked-pill">⛔ 阻断</span>')
    if key_risk and key_risk.lower() not in {"无", "none", "n/a", "-", "—"}:
        meta_bits.append(f'<span class="risk-text">核心风险：{key_risk}</span>')

    detail = render_patch(index, data)
    return f"""
<details class="patch-item" id="patch-{esc(sha12)}" data-llm="{'llm' if is_llm else 'script'}">
  <summary class="patch-header">
    <div class="patch-row">
      <span class="pill {badge_cls}">{badge_text}</span>
      <span class="sha mono">{esc(sha12)}</span>
      <span class="title">{title}</span>
      <span class="score" style="color:{score_color}">{score_text}</span>
      <span class="rec-pill">{rec}</span>
    </div>
    <div class="patch-meta">{''.join(meta_bits)}</div>
  </summary>
  <div class="patch-detail patch-detail-html">{detail}</div>
</details>"""


REPORT_CSS = """
:root {
  --bg: #f1f5f9;
  --card: #ffffff;
  --text: #0f172a;
  --muted: #64748b;
  --border: #e2e8f0;
  --primary: #2563eb;
  --expand-accent: #3b82f6;
  --expand-accent-soft: #eff6ff;
  --expand-accent-border: #bfdbfe;
  --expand-accent-strong: #1d4ed8;
  --expand-accent-bg: #f8fbff;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  color: var(--text);
  background: linear-gradient(180deg, #eef4ff 0%, var(--bg) 220px);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  line-height: 1.5;
}
.page {
  max-width: 1180px;
  margin: 0 auto;
  padding: 28px 20px 64px;
}
.hero {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 16px;
  padding: 22px 24px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.05);
  margin-bottom: 18px;
}
.hero h1 { margin: 0 0 8px; font-size: 28px; letter-spacing: -0.02em; }
.hero .muted { color: var(--muted); font-size: 13px; margin: 0; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 12px;
  margin-top: 16px;
}
.stat-card {
  background: #f8fafc;
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 12px;
}
.stat-value { font-size: 26px; font-weight: 800; margin-bottom: 4px; }
.stat-label { font-size: 12px; color: var(--muted); }
.report-section {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 16px 18px;
  margin: 14px 0;
}
.section-title {
  font-size: 16px;
  font-weight: 800;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
}
.module-analysis-grid { display: grid; gap: 10px; margin-top: 10px; }
.module-coverage { margin-bottom: 10px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.module-card {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}
.module-card[open] {
  border-color: var(--expand-accent-border);
  box-shadow: 0 0 0 1px rgba(59,130,246,.12), 0 8px 20px rgba(15,23,42,.06);
}
.module-card-header {
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  cursor: pointer;
  background: #f8fafc;
}
.module-card-header::-webkit-details-marker { display: none; }
.module-card[open] .module-card-header {
  background: var(--expand-accent-soft);
  border-bottom: 1px solid var(--expand-accent-border);
  box-shadow: inset 3px 0 0 var(--expand-accent);
}
.module-card-title { font-size: 15px; font-weight: 800; color: #0f172a; }
.module-card-meta { margin-top: 4px; font-size: 12px; color: var(--muted); }
.module-card-badges { display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
.module-card-body { padding: 12px 14px 14px; background: #fff; }
.module-card-section { margin-top: 12px; }
.module-card-section:first-child { margin-top: 0; }
.module-card-section h4 { margin: 0 0 6px; font-size: 13px; }
.module-card-section ul { margin: 4px 0 0 18px; padding: 0; }
.coverage-badge, .crash-badge {
  display: inline-flex; align-items: center; padding: 2px 8px;
  border-radius: 999px; font-size: 11px; font-weight: 700; border: 1px solid transparent;
}
.coverage-badge.coverage-ok { color: #166534; background: #dcfce7; border-color: #86efac; }
.coverage-badge.coverage-warn { color: #92400e; background: #fef3c7; border-color: #fcd34d; }
.crash-badge.crash-high { color: #b91c1c; background: #fef2f2; border-color: #fca5a5; }
.crash-badge.crash-mid { color: #c2410c; background: #fff7ed; border-color: #fdba74; }
.crash-badge.crash-low { color: #0f766e; background: #ecfdf5; border-color: #a7f3d0; }
.coverage-hint { margin: 0 0 8px; font-size: 12px; }
.chunk-item {
  padding: 8px 10px; margin-bottom: 8px; border: 1px solid var(--border);
  border-radius: 8px; background: #f8fafc;
}
.chunk-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 4px; }
.code-tree-hint { margin: 0 0 8px; font-size: 12px; color: var(--muted); }
.code-tree {
  padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px;
  background: #0f172a; font-size: 12px; line-height: 1.55; color: #e2e8f0;
}
.code-tree-node { margin: 0; }
.code-tree-row {
  display: flex; align-items: center; gap: 6px; padding: 3px 6px;
  border-radius: 6px; cursor: pointer; list-style: none; user-select: none;
}
.code-tree-row::-webkit-details-marker { display: none; }
.code-tree-row:hover { background: rgba(255,255,255,0.06); }
.code-tree-toggle {
  width: 12px; color: #94a3b8; font-size: 9px; flex-shrink: 0;
}
.code-tree-dir-node > summary .code-tree-toggle::before { content: "▶"; }
.code-tree-dir-node[open] > summary .code-tree-toggle::before { content: "▼"; }
.code-tree-file-node > summary .code-tree-toggle::before { content: "▶"; }
.code-tree-file-node[open] > summary .code-tree-toggle::before { content: "▼"; }
.code-tree-toggle { font-size: 0; }
.code-tree-toggle::before { font-size: 9px; color: #94a3b8; }
.code-tree-dir { color: #93c5fd; font-weight: 700; }
.code-tree-file { color: #86efac; }
.code-tree-count { color: #94a3b8; font-size: 10px; }
.code-tree-children { margin: 0; }
.code-tree-file-detail {
  margin: 4px 0 8px 22px; padding: 8px 10px;
  border: 1px solid #334155; border-radius: 8px; background: #111827;
}
.code-tree-patch-block { margin-bottom: 10px; }
.code-tree-patch-block:last-child { margin-bottom: 0; }
.code-tree-patch-head {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 4px;
}
.code-tree-patch-head .sha-link {
  color: #93c5fd; font-family: ui-monospace, monospace; font-weight: 700;
  text-decoration: none; background: none; border: 0; padding: 0; cursor: pointer;
}
.code-tree-patch-head .sha-link:hover { text-decoration: underline; }
.patch-head-title { color: #e2e8f0; flex: 1; min-width: 120px; }
.patch-head-score { color: #86efac; font-weight: 700; }
.patch-head-crash { color: #fdba74; font-size: 11px; }
.patch-head-risk { font-size: 11px; margin-top: 2px; }
.patch-head-risk-warn { color: #fbbf24; }
.patch-head-risk-none { color: #94a3b8; }
.code-tree-empty { color: #94a3b8; font-style: italic; font-size: 11px; }
.patch-popover {
  position: fixed; z-index: 9999; display: none;
  min-width: 312px; max-width: min(468px, calc(100vw - 24px));
  max-height: min(70vh, calc(100vh - 24px));
  padding: 13px 16px; background: #fff; color: #334155;
  border: 1px solid #cbd5e1; border-radius: 10px;
  box-shadow: 0 10px 40px rgba(15, 23, 42, 0.18);
  overflow-y: auto; font-size: 12px; line-height: 1.55;
}
.patch-popover.visible { display: block; }
.patch-popover-title { margin-bottom: 5px; color: #0f172a; font-weight: 600; word-break: break-word; }
.patch-popover-meta { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; color: #64748b; font-size: 11px; }
.patch-popover-summary { color: #475569; line-height: 1.6; white-space: pre-wrap; word-break: break-word; }
.patch-popover-risk { margin-top: 8px; font-size: 11px; }
.patch-popover-risk-warn { color: #b45309; }
.patch-popover-risk-none { color: #64748b; }
.patch-popover-item { padding-bottom: 10px; margin-bottom: 10px; border-bottom: 1px solid #e2e8f0; }
.patch-popover-item:last-child { padding-bottom: 0; margin-bottom: 0; border-bottom: 0; }
.muted { color: var(--muted); font-size: 13px; }
.tag-row { display: flex; flex-wrap: wrap; gap: 8px; }
.tag-pill, .pill, .rec-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  border: 1px solid var(--border);
  background: #f8fafc;
  color: #334155;
}
.tag-pill.dev-module, .patch-module {
  background: #fef3c7; color: #92400e; border-color: #fcd34d; font-weight: 700;
}
.pill.preferred { background: #eff6ff; color: #1d4ed8; border-color: #93c5fd; font-weight: 700; }
.llm-badge { background: #dcfce7; color: #166534; border-color: #86efac; font-weight: 700; }
.script-badge { background: #f1f5f9; color: #475569; border-color: #cbd5e1; font-weight: 700; }
.defect-pill { color: #c2410c; background: #fff7ed; border-color: #fdba74; font-weight: 700; }
.crash-pill { color: #c2410c; background: #fff7ed; border-color: #fdba74; font-weight: 700; }
.blocked-pill { color: #b91c1c; background: #fef2f2; border-color: #fca5a5; font-weight: 700; }
.prose, .prose-inline { font-size: 13px; line-height: 1.7; color: #334155; }
.prose p { margin: 8px 0; }
.prose ul { margin: 6px 0 6px 18px; padding: 0; }
.prose code, .md-h4, .md-h3 {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.prose code {
  background: #f1f5f9;
  border-radius: 4px;
  padding: 1px 4px;
  font-size: 12px;
}
.test-group { margin-bottom: 12px; }
.risk-section { border-color: #fecaca; background: #fffbfb; }
.future-section { border-color: #fdba74; background: #fffbf5; }
.risk-list { display: grid; gap: 8px; }
.risk-item {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  padding: 10px 12px;
  border: 1px solid #fecaca;
  border-radius: 10px;
  background: #fff;
  text-decoration: none;
  color: inherit;
}
.future-section .risk-item { border-color: #fdba74; }
.risk-item:hover { border-color: #fb923c; box-shadow: 0 1px 4px rgba(251,146,60,.15); }
.risk-item code { color: #0369a1; font-weight: 700; }
.reason-line { width: 100%; color: #64748b; font-size: 12px; }
.future-badge {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #c2410c;
  background: #ffedd5;
  border: 1px solid #fdba74;
}
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; background: #fff; }
th, td { padding: 8px 10px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
th { background: #f8fafc; color: #475569; font-weight: 700; }
.toolbar {
  display: flex; gap: 8px; flex-wrap: wrap; margin: 10px 0 14px;
}
.toolbar input, .toolbar select {
  padding: 8px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  font-size: 13px;
  background: #fff;
}
.toolbar input { min-width: 220px; flex: 1; }
.legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 12px; color: var(--muted); margin-bottom: 8px; }
.patch-list { display: grid; gap: 8px; }
.patch-item {
  border: 1px solid var(--border);
  border-radius: 12px;
  background: #fff;
  overflow: hidden;
}
.patch-item[open] {
  border-color: var(--expand-accent-border);
  box-shadow: 0 0 0 1px rgba(59,130,246,.12), 0 8px 20px rgba(15,23,42,.06);
}
.patch-header {
  list-style: none;
  cursor: pointer;
  padding: 12px 14px;
  background: #fff;
}
.patch-header::-webkit-details-marker { display: none; }
.patch-header:hover { background: #f8fbff; }
.patch-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.patch-row .sha { color: #1d4ed8; font-weight: 700; font-size: 12px; }
.patch-row .title { flex: 1; min-width: 180px; font-weight: 600; color: #0f172a; }
.patch-row .score { font-weight: 800; font-size: 14px; }
.rec-pill { background: #eff6ff; color: #1e40af; border-color: #93c5fd; font-weight: 700; }
.patch-meta { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.risk-text { font-size: 12px; color: #9a3412; }
.patch-detail {
  padding: 14px;
  background: var(--expand-accent-bg);
  border-top: 1px solid var(--expand-accent-border);
  box-shadow: inset 3px 0 0 var(--expand-accent);
}
.patch-detail-html .detail-panel { border: none; background: transparent; margin: 0; }
.patch-detail-html .patch-info-header {
  padding: 14px; margin-bottom: 14px; background: #fff;
  border: 1px solid var(--border); border-radius: 10px;
}
.patch-detail-html .patch-info-title {
  display: flex; align-items: flex-start; gap: 10px; margin-bottom: 10px;
}
.patch-detail-html .patch-sha {
  flex-shrink: 0; padding: 4px 8px; border-radius: 6px;
  background: #eff6ff; color: #1d4ed8; font-family: ui-monospace, monospace;
  font-size: 12px; font-weight: 700;
}
.patch-detail-html .patch-title-text {
  font-size: 15px; font-weight: 700; line-height: 1.45; color: #0f172a; word-break: break-word;
}
.patch-detail-html .patch-info-meta {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 12px; color: #64748b;
}
.patch-detail-html .patch-score { font-size: 14px; font-weight: 800; }
.patch-detail-html .patch-module,
.patch-detail-html .patch-author,
.patch-detail-html .patch-date,
.patch-detail-html .patch-files,
.patch-detail-html .patch-upstream {
  padding: 2px 8px; border-radius: 999px; background: #f8fafc; border: 1px solid #e2e8f0;
}
.patch-detail-html .patch-type-tag {
  padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; border: 1px solid transparent;
}
.patch-detail-html .patch-type-tag.llm { color: #166534; background: #dcfce7; border-color: #86efac; }
.patch-detail-html .patch-type-tag.script { color: #475569; background: #f1f5f9; border-color: #cbd5e1; }
.patch-detail-html .patch-status-badges { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.patch-detail-html .patch-status-badge {
  display: inline-flex; align-items: center; padding: 4px 10px; border-radius: 999px;
  font-size: 11px; font-weight: 700; border: 1px solid transparent;
}
.patch-detail-html .patch-status-badge.rec { color: #1e40af; background: #eff6ff; border-color: #93c5fd; }
.patch-detail-html .patch-status-badge.risk { color: #9a3412; background: #fff7ed; border-color: #fdba74; }
.patch-detail-html .patch-status-badge.blocked { color: #b91c1c; background: #fef2f2; border-color: #fca5a5; }
.patch-detail-html .patch-status-badge.defect { color: #c2410c; background: #fff7ed; border-color: #fdba74; }
.patch-detail-html .patch-status-badge.crash { color: #b91c1c; background: #fef2f2; border-color: #fca5a5; }
.patch-detail-html .patch-commit-details,
.patch-detail-html .patch-diff-details {
  margin-top: 10px; border: 1px solid var(--border); border-radius: 10px; background: #fff; overflow: hidden;
}
.patch-detail-html .patch-commit-details > summary,
.patch-detail-html .patch-diff-details > summary {
  cursor: pointer; padding: 10px 12px; font-weight: 700; font-size: 13px; list-style: none;
}
.patch-detail-html .patch-commit-details > summary::-webkit-details-marker,
.patch-detail-html .patch-diff-details > summary::-webkit-details-marker { display: none; }
.patch-detail-html .patch-commit-details[open] > summary,
.patch-detail-html .patch-diff-details[open] > summary {
  background: var(--expand-accent-soft);
  border-bottom: 1px solid var(--expand-accent-border);
  box-shadow: inset 3px 0 0 var(--expand-accent);
  color: var(--expand-accent-strong);
}
.patch-detail-html .patch-commit-msg {
  margin: 10px 12px 12px; padding: 10px 12px; border: 1px solid #e2e8f0; border-radius: 8px;
  background: #f8fafc; font-family: ui-monospace, monospace; font-size: 12px; line-height: 1.6;
  white-space: pre-wrap; max-height: 240px; overflow: auto;
}
.patch-detail-html .patch-defect-banner {
  margin-bottom: 14px; padding: 12px 14px; border: 1px solid #fcd34d;
  border-left: 4px solid #f59e0b; border-radius: 8px; background: #fffbeb;
}
.patch-detail-html .patch-defect-title { font-size: 14px; font-weight: 700; color: #92400e; }
.patch-detail-html .patch-defect-desc,
.patch-detail-html .patch-defect-intro { margin-top: 6px; font-size: 13px; line-height: 1.55; color: #78350f; }
.patch-detail-html .section-grid { display: grid; grid-template-columns: 1fr; gap: 14px; }
@media (min-width: 960px) {
  .patch-detail-html .section-grid { grid-template-columns: 2fr 1fr; align-items: start; }
}
.patch-detail-html .crash-warning-banner,
.patch-detail-html .pattern-warning-banner {
  margin-bottom: 14px; padding: 12px 14px; border-radius: 8px;
}
.patch-detail-html .crash-warning-banner {
  background: #fef2f2; border: 1px solid #fca5a5; border-left: 4px solid #ef4444;
}
.patch-detail-html .pattern-warning-banner {
  background: #fffbeb; border: 1px solid #fcd34d; border-left: 4px solid #f59e0b;
}
.patch-detail-html .warning-title { font-weight: 700; margin-bottom: 4px; }
.patch-detail-html .pattern-tag-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.patch-detail-html .pattern-tag {
  display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px;
}
.patch-detail-html .pattern-tag.high { background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }
.patch-detail-html .pattern-tag.medium { background: #fef3c7; color: #92400e; border: 1px solid #fcd34d; }
.patch-detail-html .future-fix-item {
  padding: 10px 12px; margin-bottom: 8px; background: #f8fafc;
  border: 1px solid #e2e8f0; border-radius: 8px;
}
.patch-detail-html .future-fix-sha,
.patch-detail-html .future-fix-cp {
  color: var(--primary); font-family: ui-monospace, monospace;
  font-size: 13px; font-weight: 700; text-decoration: none;
}
.patch-detail-html .future-fix-title { margin: 4px 0 6px; font-size: 13px; line-height: 1.45; color: #1f2937; }
.patch-detail-html .future-fix-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 4px; }
.patch-detail-html .future-fix-tag {
  display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px;
  background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1;
}
.patch-detail-html .future-fix-tag.primary { background: #ede9fe; color: #5b21b6; border-color: #c4b5fd; }
.patch-detail-html .future-fix-tag.warn { background: #fff7ed; color: #c2410c; border-color: #fdba74; }
.patch-detail-html .detail-body { padding: 0; }
.patch-detail-html .section-card {
  background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; margin-bottom: 14px;
}
.patch-detail-html .section-card.llm { border-left: 3px solid #86efac; }
.patch-detail-html .section-card.script { border-left: 3px solid #93c5fd; }
.patch-detail-html .section-card.generic { border-left: 3px solid #cbd5e1; }
.patch-detail-html .section-card-header {
  padding: 8px 12px; background: #f8fafc; border-bottom: 1px solid #e5e7eb;
  font-size: 13px; font-weight: 700; color: #374151;
}
.patch-detail-html .section-card-body {
  padding: 12px; font-size: 13px; line-height: 1.7; color: #4b5563;
}
.patch-detail-html .section-card-body p { margin: 4px 0; }
.patch-detail-html .diff-box {
  background: #1e293b; color: #e2e8f0; padding: 12px; border-radius: 6px; overflow: auto;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px;
  line-height: 1.5; white-space: pre; max-height: 360px;
}
.patch-detail-html .info-box {
  background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 10px;
}
.patch-detail-html .info-box.blue { background: #eff6ff; border-color: #bfdbfe; }
.patch-detail-html .link-row { display: flex; gap: 12px; flex-wrap: wrap; }
.patch-detail-html .link-row a { color: #2563eb; text-decoration: none; font-size: 13px; }
.patch-detail-html .link-row a:hover { text-decoration: underline; }
.patch-detail-html .score-summary-item {
  border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px 10px;
  background: #fafbfc; font-size: 13px; line-height: 1.6; color: #4b5563; margin-bottom: 6px;
}
.patch-detail-html .ss-header { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }
.patch-detail-html .score-summary-label { font-weight: 700; color: #374151; }
.patch-detail-html .score-summary-value { font-weight: 700; color: #059669; font-size: 15px; }
.patch-detail-html .ss-metrics-row { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
.patch-detail-html .ss-metric {
  font-size: 11px; color: #6b7280; background: #f3f4f6; border-radius: 4px; padding: 1px 6px;
}
.patch-detail-html .ss-rule { font-size: 11px; color: #6b7280; padding: 0 2px; }
.patch-detail-html .ss-rule::before { content: "▸ "; color: #9ca3af; }
.analysis-section-nav {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 14px;
  padding: 10px 12px;
  background: rgba(255, 255, 255, 0.96);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
  backdrop-filter: blur(8px);
}
.analysis-section-nav-btn {
  padding: 6px 12px;
  border: 1px solid #dbeafe;
  border-radius: 999px;
  background: #f8fafc;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease, color 0.15s ease;
}
.analysis-section-nav-btn:hover {
  background: #eff6ff;
  border-color: #93c5fd;
  color: #1d4ed8;
}
.analysis-section-nav-btn.active {
  background: #2563eb;
  border-color: #2563eb;
  color: #fff;
}
.analysis-anchor { scroll-margin-top: 72px; }
.scroll-to-top-overlay {
  position: fixed;
  right: 20px;
  bottom: 24px;
  z-index: 40;
  pointer-events: none;
}
.scroll-to-top-btn {
  pointer-events: auto;
  display: none;
  align-items: center;
  justify-content: center;
  width: 48px;
  height: 48px;
  padding: 0;
  border: 1px solid rgba(148, 163, 184, 0.45);
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.82);
  backdrop-filter: blur(8px);
  color: #1d4ed8;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.12);
  cursor: pointer;
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
  transition: transform 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}
.scroll-to-top-btn.visible { display: inline-flex; }
.scroll-to-top-btn:hover {
  background: rgba(239, 246, 255, 0.92);
  border-color: rgba(147, 197, 253, 0.65);
  transform: translateY(-2px);
}
@media print {
  body { background: #fff; }
  .toolbar, .analysis-section-nav, .scroll-to-top-overlay { display: none !important; }
  .patch-item { break-inside: avoid; }
  .patch-item:not([open]) { border-color: #cbd5e1; }
}
"""


def _enrich_patch_future_fixes(
    patches: List[Dict[str, Any]],
    summary: Dict[str, Any],
) -> None:
    """Attach task-level future-fix snapshot onto raw patch rows when missing."""
    stored = summary.get("future_fix_patches") or []
    if not isinstance(stored, list) or not stored:
        return
    by_sha12: Dict[str, Dict[str, Any]] = {}
    for item in stored:
        if not isinstance(item, dict):
            continue
        sha12 = str(item.get("sha") or "")[:12]
        if sha12:
            by_sha12[sha12] = item
    if not by_sha12:
        return
    for row in patches:
        data = _patch_data(row)
        sha12 = str(data.get("sha") or data.get("commit") or row.get("sha") or "")[:12]
        item = by_sha12.get(sha12)
        if not item:
            continue
        fixes = item.get("fixes") or []
        if not fixes:
            continue
        if isinstance(row.get("data"), dict):
            if not row["data"].get("fix_in_future"):
                row["data"]["fix_in_future"] = fixes
        elif isinstance(row.get("data"), str):
            try:
                parsed = json.loads(row["data"])
            except (json.JSONDecodeError, TypeError):
                continue
            if not parsed.get("fix_in_future"):
                parsed["fix_in_future"] = fixes
                row["data"] = parsed
        elif not row.get("fix_in_future"):
            row["fix_in_future"] = fixes


def build_task_report_html(
    task: Dict[str, Any],
    patches: List[Dict[str, Any]],
    *,
    summary: Optional[Dict[str, Any]] = None,
    monthly_html: str = "",
) -> str:
    summary = summary or {}
    patches = list(patches or [])
    _enrich_patch_future_fixes(patches, summary)
    repo = task.get("repo", "")
    from_tag = task.get("from_tag", "") or "(单笔)"
    to_tag = task.get("to_tag", "") or "(单笔)"
    total = int(task.get("total") or len(patches) or 0)
    analyzed = int(task.get("analyzed") or len(patches) or 0)

    scores: List[float] = []
    for row in patches:
        data = _patch_data(row)
        try:
            scores.append(float(data.get("score") or 0))
        except (TypeError, ValueError):
            pass
    avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

    stats_html = _render_stat_cards(summary, total, analyzed, avg_score)
    tags_html = _render_tag_pills(summary.get("tag_counts") or {})
    summary_text_html = _render_markdown_section(
        "📝 详细综述",
        str(summary.get("text") or ""),
        bare=True,
    )
    tests_html = _render_test_suggestions(summary)
    future_html = _render_risk_list(
        "🔗 后续 Fixes 修复",
        list(summary.get("future_fix_patches") or [])[:30],
        kind="future",
        section_id="report-section-future-fix",
    )
    high_risk_html = _render_risk_list(
        "⚠️ 高风险 Patch",
        list(summary.get("high_risk") or [])[:15],
        kind="risk",
        section_id="report-section-high-risk",
    )

    patch_items = "".join(_render_patch_item(i, row) for i, row in enumerate(patches))
    llm_count = sum(1 for row in patches if _patch_data(row).get("llm_analyzed"))

    summary_body_parts = []
    if stats_html:
        summary_body_parts.append(stats_html)
    if tags_html:
        summary_body_parts.append(tags_html)
    if summary_text_html:
        summary_body_parts.append(summary_text_html)
    summary_section_html = ""
    if summary_body_parts:
        summary_section_html = (
            '<section class="report-section analysis-anchor" id="report-section-summary">'
            '<div class="section-title">📊 分析总结</div>'
            f'{"".join(summary_body_parts)}'
            "</section>"
        )

    modules_html = _render_module_analysis(summary)

    nav_sections: List[tuple[str, str]] = []
    if monthly_html:
        nav_sections.append(("report-section-subtag", "子 tag 分析"))
    if summary_section_html:
        nav_sections.append(("report-section-summary", "分析总结"))
    if modules_html:
        nav_sections.append(("report-section-modules", "模块分析"))
    if tests_html:
        nav_sections.append(("report-section-tests", "测试建议"))
    if future_html:
        nav_sections.append(("report-section-future-fix", "后续修复"))
    if high_risk_html:
        nav_sections.append(("report-section-high-risk", "高风险"))
    if patches:
        nav_sections.append(("report-section-patches", "Patch 列表"))

    nav_html = ""
    if nav_sections:
        buttons = "".join(
            f'<button type="button" class="analysis-section-nav-btn" data-nav-id="{esc(sid)}">{esc(label)}</button>'
            for sid, label in nav_sections
        )
        nav_html = f'<nav class="analysis-section-nav" aria-label="报告导航">{buttons}</nav>'

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Patch 分析报告</title>
  <style>{REPORT_CSS}</style>
</head>
<body>
  <div class="page">
    <header class="hero">
      <h1>Patch 分析报告</h1>
      <p class="muted">仓库: {esc(repo)}<br/>区间: <span class="mono">{esc(from_tag)}</span> → <span class="mono">{esc(to_tag)}</span></p>
    </header>

    {nav_html}
    {monthly_html}
    {summary_section_html}
    {modules_html}
    {tests_html}
    {future_html}
    {high_risk_html}

    <section class="report-section analysis-anchor" id="report-section-patches">
      <div class="section-title">📦 Patch 列表
        <span class="muted">（{len(patches)} 笔 · LLM {llm_count} 笔）</span>
      </div>
      <div class="legend">
        <span><span class="pill llm-badge">LLM</span> 深度分析</span>
        <span><span class="pill script-badge">脚本</span> 规则分析</span>
      </div>
      <div class="toolbar">
        <select id="llmFilter">
          <option value="">全部方式</option>
          <option value="llm">仅 LLM</option>
          <option value="script">仅脚本</option>
        </select>
        <input id="kw" placeholder="搜索 SHA / 标题 / 风险…" />
      </div>
      <div class="patch-list" id="patches-container">{patch_items or '<p class="muted">暂无 patch 结果</p>'}</div>
    </section>
  </div>

  <div class="scroll-to-top-overlay">
    <button type="button" id="scrollNavBtn" class="scroll-to-top-btn" title="回到顶部" aria-label="回到顶部">↑</button>
  </div>
  <div id="patchPopover" class="patch-popover" aria-hidden="true"></div>

  <script>
    const llmFilter = document.getElementById('llmFilter');
    const kw = document.getElementById('kw');
    const items = Array.from(document.querySelectorAll('.patch-item'));
    const navBtns = Array.from(document.querySelectorAll('.analysis-section-nav-btn'));
    const scrollBtn = document.getElementById('scrollNavBtn');
    let returnY = null;
    let spyPausedUntil = 0;

    function applyFilter() {{
      const llm = (llmFilter.value || '').trim();
      const q = (kw.value || '').trim().toLowerCase();
      items.forEach((el) => {{
        const mode = el.dataset.llm || '';
        const text = (el.innerText || '').toLowerCase();
        el.style.display = (!llm || mode === llm) && (!q || text.includes(q)) ? '' : 'none';
      }});
    }}
    llmFilter.addEventListener('change', applyFilter);
    kw.addEventListener('input', applyFilter);

    function saveReturnPoint() {{
      returnY = window.scrollY || document.documentElement.scrollTop || 0;
      updateScrollBtn();
    }}

    function updateScrollBtn() {{
      const y = window.scrollY || document.documentElement.scrollTop || 0;
      const canReturn = returnY != null;
      const show = y > 120 || canReturn;
      scrollBtn.classList.toggle('visible', show);
      if (canReturn) {{
        scrollBtn.textContent = '↩';
        scrollBtn.title = '回到刚才的位置';
        scrollBtn.setAttribute('aria-label', '回到刚才的位置');
      }} else {{
        scrollBtn.textContent = '↑';
        scrollBtn.title = '回到顶部';
        scrollBtn.setAttribute('aria-label', '回到顶部');
      }}
    }}

    function scrollToSavedOrTop() {{
      if (returnY != null) {{
        const y = returnY;
        returnY = null;
        updateScrollBtn();
        window.scrollTo({{ top: y, behavior: 'smooth' }});
        return;
      }}
      window.scrollTo({{ top: 0, behavior: 'smooth' }});
    }}

    function jumpToSection(sectionId) {{
      const target = document.getElementById(sectionId);
      if (!target) return;
      saveReturnPoint();
      spyPausedUntil = Date.now() + 800;
      navBtns.forEach((btn) => btn.classList.toggle('active', btn.dataset.navId === sectionId));
      target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
    }}

    function jumpToPatch(sha) {{
      if (!sha) return false;
      const target = document.getElementById('patch-' + sha)
        || document.querySelector('[id^="patch-' + sha.slice(0, 8) + '"]');
      if (!target) return false;
      saveReturnPoint();
      spyPausedUntil = Date.now() + 800;
      if (target.tagName === 'DETAILS') target.open = true;
      target.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
      return true;
    }}

    navBtns.forEach((btn) => {{
      btn.addEventListener('click', () => jumpToSection(btn.dataset.navId || ''));
    }});

    document.querySelectorAll('[data-jump-patch]').forEach((el) => {{
      el.addEventListener('click', (event) => {{
        event.preventDefault();
        event.stopPropagation();
        jumpToPatch(el.getAttribute('data-jump-patch') || '');
      }});
    }});

    const popover = document.getElementById('patchPopover');
    let hideTimer = null;
    function cancelHidePopover() {{
      if (hideTimer) {{ clearTimeout(hideTimer); hideTimer = null; }}
    }}
    function scheduleHidePopover() {{
      cancelHidePopover();
      hideTimer = setTimeout(() => {{
        popover.classList.remove('visible');
        popover.setAttribute('aria-hidden', 'true');
      }}, 180);
    }}
    function formatScore(v) {{
      const n = Number(v);
      return Number.isFinite(n) ? n.toFixed(1) : '-';
    }}
    function renderPopover(patches, x, y) {{
      if (!patches || !patches.length) return;
      popover.innerHTML = patches.map((p) => {{
        const sha = String(p.sha || p.full_sha || '').slice(0, 12);
        const title = String(p.title || '-');
        const summary = String(p.summary || '(暂无解读)');
        const risk = String(p.key_risk || '').trim();
        const noneRisk = ['无','none','n/a','na','-','—'].includes(risk.toLowerCase());
        const riskHtml = risk
          ? `<div class="patch-popover-risk ${{noneRisk ? 'patch-popover-risk-none' : 'patch-popover-risk-warn'}}">${{noneRisk ? '✓ 核心风险：无明显' : ('⚠ 核心风险：' + risk)}}</div>`
          : '';
        const crash = p.crash_risk ? `<span>死机风险 ${{p.crash_risk}}</span>` : '';
        return `<div class="patch-popover-item">
          <div class="patch-popover-title">${{sha}} · ${{title}}</div>
          <div class="patch-popover-meta">
            <span>${{p.llm_analyzed ? 'LLM' : '脚本'}}</span>
            <span>评分 ${{formatScore(p.score)}}</span>
            <span>+${{p.insertions || 0}}/-${{p.deletions || 0}}</span>
            ${{crash}}
          </div>
          <div class="patch-popover-summary">${{summary}}</div>
          ${{riskHtml}}
        </div>`;
      }}).join('');
      const left = Math.min(x + 14, window.innerWidth - 340);
      const top = Math.min(y + 14, window.innerHeight - 120);
      popover.style.left = Math.max(12, left) + 'px';
      popover.style.top = Math.max(12, top) + 'px';
      popover.classList.add('visible');
      popover.setAttribute('aria-hidden', 'false');
    }}
    function parsePatches(raw) {{
      if (!raw) return [];
      try {{ return JSON.parse(raw); }} catch (e) {{ return []; }}
    }}
    document.querySelectorAll('[data-patches]').forEach((el) => {{
      el.addEventListener('mouseenter', (event) => {{
        cancelHidePopover();
        const patches = parsePatches(el.getAttribute('data-patches') || '');
        renderPopover(patches, event.clientX, event.clientY);
      }});
      el.addEventListener('mousemove', (event) => {{
        if (!popover.classList.contains('visible')) return;
        const left = Math.min(event.clientX + 14, window.innerWidth - 340);
        const top = Math.min(event.clientY + 14, window.innerHeight - 120);
        popover.style.left = Math.max(12, left) + 'px';
        popover.style.top = Math.max(12, top) + 'px';
      }});
      el.addEventListener('mouseleave', scheduleHidePopover);
    }});
    popover.addEventListener('mouseenter', cancelHidePopover);
    popover.addEventListener('mouseleave', scheduleHidePopover);

    scrollBtn.addEventListener('click', scrollToSavedOrTop);
    window.addEventListener('scroll', updateScrollBtn, {{ passive: true }});
    updateScrollBtn();

    function syncActiveNav() {{
      if (Date.now() < spyPausedUntil) return;
      const ids = navBtns.map((btn) => btn.dataset.navId).filter(Boolean);
      if (!ids.length) return;
      const anchorLine = 80;
      let current = ids[0];
      if ((window.innerHeight + window.scrollY) >= (document.body.scrollHeight - 24)) {{
        current = ids[ids.length - 1];
      }} else {{
        ids.forEach((id) => {{
          const el = document.getElementById(id);
          if (!el) return;
          if (el.getBoundingClientRect().top <= anchorLine) current = id;
        }});
      }}
      navBtns.forEach((btn) => btn.classList.toggle('active', btn.dataset.navId === current));
    }}
    window.addEventListener('scroll', () => {{
      window.requestAnimationFrame(syncActiveNav);
    }}, {{ passive: true }});
    syncActiveNav();
  </script>
</body>
</html>"""
