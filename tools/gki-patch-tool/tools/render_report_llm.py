#!/usr/bin/env python3
"""Comprehensive LLM-enhanced HTML report with full patch analysis display."""
import argparse
import html
import json
from pathlib import Path
from typing import List


HTML_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Patch 分析报告 - LLM 增强综合版</title>
  <style>
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2937; background: #f8fafc; }}
    h1, h2, h3 {{ margin: 0 0 8px 0; }}
    .muted {{ color: #6b7280; font-size: 13px; }}
    .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin: 16px 0 20px 0; }}
    .card {{ border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; background: #fff; }}
    .card-v {{ font-size: 24px; font-weight: 700; margin-bottom: 4px; }}
    .card-k {{ font-size: 12px; color: #6b7280; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 12px; background: #fff; }}
    th, td {{ border: 1px solid #e5e7eb; padding: 8px; text-align: left; font-size: 13px; }}
    th {{ background: #f1f5f9; position: sticky; top: 0; z-index: 2; }}
    .pill {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; border: 1px solid #d1d5db; }}
    .tag {{ display: inline-block; padding: 2px 7px; border-radius: 999px; font-size: 11px; background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe; margin: 1px 2px; }}
    .llm-badge {{ background: #dcfce7; color: #166534; border-color: #86efac; font-weight: 600; }}
    .script-badge {{ background: #f3f4f6; color: #4b5563; border-color: #d1d5db; }}
    .ok {{ color: #0f766e; }} .warn {{ color: #a16207; }} .bad {{ color: #b91c1c; }}
    .toolbar {{ display: flex; gap: 8px; margin: 8px 0 12px 0; flex-wrap: wrap; }}
    input, select {{ padding: 6px 8px; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; }}
    .detail-row {{ background: #fcfdfd; }}
    .detail-panel {{ border: 1px solid #e5e7eb; border-radius: 8px; margin: 8px 0; overflow: hidden; background: #fff; }}
    .detail-header {{ background: #f8fafc; padding: 10px 14px; cursor: pointer; font-weight: 600; font-size: 14px; border-bottom: 1px solid #e5e7eb; user-select: none; }}
    .detail-header:hover {{ background: #f1f5f9; }}
    .detail-body {{ padding: 14px; }}
    .section {{ margin-bottom: 16px; }}
    .section:last-child {{ margin-bottom: 0; }}
    .section-title {{ font-size: 13px; font-weight: 700; color: #374151; margin-bottom: 6px; padding-bottom: 4px; border-bottom: 2px solid #e5e7eb; }}
    .section-title.llm {{ border-color: #86efac; }}
    .section-title.script {{ border-color: #93c5fd; }}
    .section-body {{ font-size: 13px; line-height: 1.7; color: #4b5563; padding: 0 4px; }}
    .section-body p {{ margin: 4px 0; }}
    .diff-box {{ background: #1e293b; color: #e2e8f0; padding: 12px; border-radius: 6px; overflow-x: auto; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; line-height: 1.5; white-space: pre; max-height: 300px; overflow-y: auto; }}
    .diff-add {{ color: #4ade80; }} .diff-del {{ color: #f87171; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .grid-2-1 {{ display: grid; grid-template-columns: 2fr 1fr; gap: 12px; }}
    .info-box {{ background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 10px; }}
    .info-box.blue {{ background: #eff6ff; border-color: #bfdbfe; }}
    .link-icon {{ color: #2563eb; text-decoration: none; font-size: 13px; }}
    .link-icon:hover {{ text-decoration: underline; }}
    .score-mini {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
    .legend {{ display: flex; gap: 16px; margin: 8px 0; font-size: 12px; }}
    .legend-item {{ display: flex; align-items: center; gap: 4px; }}
    .score-detail-grid, .score-grid, .score-summary-grid {{ display: flex; flex-direction: column; gap: 6px; }}
    .score-summary-item {{ border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px 10px; background: #fafbfc; font-size: 13px; line-height: 1.6; color: #4b5563; }}
    .score-summary-item + .score-summary-item {{ margin-top: 4px; }}
    .ss-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 4px; }}
    .score-summary-label {{ font-weight: 700; color: #374151; }}
    .score-summary-value {{ font-weight: 700; color: #059669; font-size: 15px; }}
    .ss-metrics-row {{ display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }}
    .ss-metric-block {{ display: inline-block; }}
    .ss-metric {{ font-size: 11px; color: #6b7280; background: #f3f4f6; border-radius: 4px; padding: 1px 6px; }}
    .ss-metric strong {{ color: #374151; }}
    .ss-rule {{ font-size: 11px; color: #6b7280; padding: 0 2px; }}
    .ss-rule::before {{ content: "▸ "; color: #9ca3af; }}
    .score-summary-reason {{ color: #4b5563; margin-top: 4px; }}
    details {{ cursor: pointer; }}
    details > summary {{ font-weight: 600; font-size: 13px; padding: 4px 0; }}
    .compact-header {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
    .section-grid {{ display: grid; grid-template-columns: 1fr; gap: 14px; }}
    .section-card {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; margin-bottom: 14px; }}
    .section-card.llm {{ border-left: 3px solid #86efac; }}
    .section-card.script {{ border-left: 3px solid #93c5fd; }}
    .section-card.generic {{ border-left: 3px solid #cbd5e1; }}
    .section-card-header {{ padding: 8px 12px; background: #f8fafc; border-bottom: 1px solid #e5e7eb; font-size: 13px; font-weight: 700; color: #374151; }}
    .section-card-body {{ padding: 12px; font-size: 13px; line-height: 1.7; color: #4b5563; }}
    .section-card-body p {{ margin: 4px 0; }}
    .sub-label {{ font-size: 12px; font-weight: 700; color: #6b7280; letter-spacing: 0.3px; }}
    .link-row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
    .link-row a {{ color: #2563eb; text-decoration: none; font-size: 13px; }}
    .link-row a:hover {{ text-decoration: underline; }}
    .commit-msg-box {{ background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; margin-top: 6px; font-family: monospace; font-size: 12px; line-height: 1.6; white-space: pre-wrap; max-height: 240px; overflow-y: auto; }}
    .crash-warning-banner {{ background: #fef2f2; border: 1px solid #fca5a5; border-left: 4px solid #ef4444; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; }}
    .crash-warning-banner .warning-title {{ font-weight: 700; color: #b91c1c; font-size: 14px; margin-bottom: 4px; }}
    .crash-warning-banner .warning-desc {{ color: #7f1d1d; font-size: 13px; line-height: 1.6; }}
    .pattern-warning-banner {{ background: #fffbeb; border: 1px solid #fcd34d; border-left: 4px solid #f59e0b; border-radius: 6px; padding: 10px 14px; margin-bottom: 14px; }}
    .pattern-tag {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; margin: 2px; }}
    .pattern-tag.high {{ background: #fee2e2; color: #991b1b; border: 1px solid #fca5a5; }}
    .pattern-tag.medium {{ background: #fef3c7; color: #92400e; border: 1px solid #fcd34d; }}
    .crash-risk-card {{ border-left: 3px solid #ef4444; }}
    .future-fix-card {{ border-left: 3px solid #8b5cf6; }}
  </style>
</head>
<body>
  <h1>Patch 分析报告（LLM 增强综合版）</h1>
  <p class="muted">仓库: {repo}<br/>区间: {from_tag} → {to_tag}</p>

  <div class="legend">
    <span class="legend-item"><span class="pill llm-badge">LLM 深度分析</span>：由大模型逐笔解读</span>
    <span class="legend-item"><span class="pill script-badge">脚本分析</span>：由规则引擎生成</span>
  </div>

  <div class="summary-grid">
    <div class="card"><div class="card-v">{total}</div><div class="card-k">区间总提交数</div></div>
    <div class="card"><div class="card-v">{analyzed}</div><div class="card-k">已分析</div></div>
    <div class="card"><div class="card-v">{avg_score}</div><div class="card-k">平均分</div></div>
    <div class="card"><div class="card-v">{llm_count}</div><div class="card-k">LLM 深度分析</div></div>
  </div>

  {test_summary_html}

  <div class="toolbar">
    <select id="llmFilter"><option value="">全部方式</option><option value="llm">仅 LLM 分析</option><option value="script">仅脚本分析</option></select>
    <input id="kw" placeholder="搜索 commit / 标题 / 风险" />
  </div>

  <div id="patches-container">{patches_html}</div>

  <script>
    const llmFilter = document.getElementById('llmFilter');
    const kw = document.getElementById('kw');
    const panels = Array.from(document.querySelectorAll('.detail-panel'));
    function applyFilter() {{
      const llm = llmFilter.value.trim();
      const q = kw.value.trim().toLowerCase();
      panels.forEach(p => {{
        const rLlm = p.dataset.llm || '';
        const txt = (p.innerText || '').toLowerCase();
        p.style.display = (!llm || rLlm === llm) && (!q || txt.includes(q)) ? '' : 'none';
      }});
    }}
    llmFilter.addEventListener('change', applyFilter);
    kw.addEventListener('input', applyFilter);
  </script>
</body>
</html>
"""


def esc(v):
    return html.escape(str(v or ""), quote=True)


def esc_br(v):
    return esc(v).replace("\n", "<br/>")


def render_diff(diff_text):
    if not diff_text:
        return ""
    return f"<div class='diff-box'>{esc(diff_text)}</div>"


def render_tags(display_tags):
    labels = []
    for tag in display_tags:
        label = str(tag.get("label", "")).strip()
        if label:
            labels.append(label)
    if not labels:
        labels.append("通用内核")
    return " ".join(f'<span class="tag">{esc(l)}</span>' for l in labels[:6])


def render_test_summary(patches):
    """Aggregate test suggestions across all patches into a summary block."""
    from collections import Counter
    TEST_FIELDS = ["unit_test", "integration_test", "regression_test", "manual_validation", "release_safeguard"]
    FIELD_LABELS = {
        "unit_test": "单元测试",
        "integration_test": "集成测试",
        "regression_test": "回归测试",
        "manual_validation": "手工验证",
        "release_safeguard": "上线保障",
    }
    all_items: Dict[str, List[str]] = {f: [] for f in TEST_FIELDS}
    for p in patches:
        ts = p.get("test_suggestions", {}) or {}
        if isinstance(ts, dict):
            for field in TEST_FIELDS:
                val = ts.get(field, "")
                if val:
                    parts = [item.strip() for item in val.split("；") if item.strip()]
                    all_items[field].extend(parts)

    sections = []
    for field in TEST_FIELDS:
        items = all_items.get(field, [])
        if not items:
            continue
        counter = Counter(items)
        top = counter.most_common(5)
        total_count = sum(c for _, c in top)
        parts_html = "".join(
            f'<span class="tag">{esc(text)} <strong>{cnt}</strong></span>'
            for text, cnt in top
        )
        sections.append(
            f"<div style='margin-bottom:8px'><strong>{FIELD_LABELS[field]}</strong>"
            f" <span class='muted' style='font-size:11px'>({total_count}笔涉及)</span><br/>"
            f"<div style='margin-top:4px'>{parts_html}</div></div>"
        )

    if not sections:
        return ""
    return (
        '<div class="card" style="margin-top:14px">'
        '<div style="font-size:14px;font-weight:700;margin-bottom:8px">🧪 综合测试建议</div>'
        + "".join(sections)
        + "</div>"
    )


def render_score_details(score_details):
    if not score_details:
        return "<p class='muted'>无评分明细</p>"
    items = []
    _TRUSTED_MERGE_POLICY_NOTE = "集成合并策略已覆盖"
    for dim_key, dim_label in [
        ("correctness_completeness", "正确性与完整性"),
        ("risk_safety", "风险与安全性"),
        ("diff_maintainability", "Diff 可维护性"),
        ("commit_metadata_quality", "Commit/元信息质量"),
    ]:
        d = score_details.get(dim_key, {})
        if not d:
            continue
        score = d.get("score", "-")
        weight = d.get("weight")
        weighted_score = d.get("weighted_score")
        reason = esc(d.get("reason", ""))
        breakdown = d.get("breakdown") or {}
        base_score = breakdown.get("base_score") if isinstance(breakdown, dict) else None
        rules = d.get("applied_rules", []) or []

        # ── metrics line ──
        parts = []
        if base_score is not None:
            parts.append(f'<span class="ss-metric">基础分: <strong>{esc(base_score)}</strong></span>')
        if weight is not None:
            pct = int(weight * 100)
            parts.append(f'<span class="ss-metric">比重: <strong>{pct}%</strong></span>')
        if weighted_score is not None:
            parts.append(f'<span class="ss-metric">加权: <strong>{esc(weighted_score)}</strong></span>')
        metrics = "".join(f'<div class="ss-metric-block">{p}</div>' for p in parts)

        # ── applied rules (exclude trusted merge note) ──
        rule_lines = []
        for r in rules:
            r_str = str(r)
            if _TRUSTED_MERGE_POLICY_NOTE not in r_str:
                rule_lines.append(f'<div class="ss-rule">{esc(r_str)}</div>')
        rules_html = "".join(rule_lines)

        items.append(
            f'<div class="score-summary-item">'
            f'<div class="ss-header">'
            f'<span class="score-summary-label">{dim_label}</span>'
            f'<span class="score-summary-value">{score}</span>'
            f'</div>'
            f'<div class="ss-metrics-row">{metrics}</div>'
            f'{rules_html}'
            f'<div class="score-summary-reason">{reason}</div>'
            f'</div>'
        )
    return f'<div class="score-summary-grid">{"".join(items)}</div>'


def _introducer_combined(introducer, introduced_risk):
    """Combine introducer analysis and introduced risk into one card body."""
    parts = []
    if introducer:
        parts.append(f'<div class="sub-label">\U0001f50d 引入提交</div><div>{introducer}</div>')
    if introduced_risk:
        parts.append(f'<div class="sub-label" style="margin-top:8px">\u26a0\ufe0f 引入风险</div><div>{introduced_risk}</div>')
    if not parts:
        return '<p class="muted">暂无分析</p>'
    return "\n".join(parts)


def _patch_score_color(score) -> str:
    value = float(score or 0)
    if value >= 7:
        return "#0f766e"
    if value >= 4:
        return "#a16207"
    return "#b91c1c"


def _render_patch_status_badges(p) -> str:
    badges: List[str] = []
    rec = str(p.get("recommendation") or p.get("merge_advice") or "").strip()
    if rec:
        badges.append(f'<span class="patch-status-badge rec">{esc(rec)}</span>')

    key_risk = str(p.get("key_risk") or "").strip()
    if key_risk and key_risk.lower() not in ("无", "none", "n/a", "-", "—"):
        badges.append(f'<span class="patch-status-badge risk">{esc(key_risk)}</span>')

    if p.get("blocked"):
        badges.append('<span class="patch-status-badge blocked">阻断</span>')

    fixes = p.get("fix_in_future") or []
    if fixes:
        fix_tags: List[str] = []
        for fix in fixes:
            tag = str(fix.get("fix_tag") or "").strip()
            if tag and tag not in fix_tags:
                fix_tags.append(tag)
        tag_hint = ""
        if fix_tags:
            tag_hint = f' · 修复于 {esc("、".join(fix_tags[:2]))}'
        badges.append(
            f'<span class="patch-status-badge defect">'
            f'⚠ 已知缺陷 · {len(fixes)} 笔后续修复{tag_hint}</span>'
        )

    crash = str(p.get("crash_risk") or "").strip()
    if crash in ("高", "中"):
        badges.append(f'<span class="patch-status-badge crash">死机风险 {esc(crash)}</span>')

    if not badges:
        return ""
    return f'<div class="patch-status-badges">{"".join(badges)}</div>'


def _render_defect_summary_banner(fix_in_future, introducer: str = "") -> str:
    if not fix_in_future:
        return ""
    intro_text = str(introducer or "").strip()
    intro_html = (
        f'<div class="patch-defect-intro">{intro_text}</div>'
        if intro_text
        else ""
    )
    return (
        f'<div class="patch-defect-banner">'
        f'<div class="patch-defect-title">🔗 本 patch 在后续 tag 中有 {len(fix_in_future)} 笔 Fixes 修复</div>'
        f'<div class="patch-defect-desc">合入前请确认风险是否已被后续修复覆盖，或评估是否可接受已知缺陷。</div>'
        f'{intro_html}'
        f'</div>'
    )


def _render_warning_banners(crash_risk, crash_risk_reason, crash_patterns) -> str:
    warning_banners: List[str] = []
    if crash_risk == "高":
        warning_banners.append(
            f'<div class="crash-warning-banner">'
            f'<div class="warning-title">\U0001f6a8 死机风险: 高</div>'
            f'<div class="warning-desc">{crash_risk_reason or "LLM 评估该 patch 有较高的死机风险"}</div>'
            f'</div>'
        )
    elif crash_risk == "中" and crash_risk_reason:
        warning_banners.append(
            f'<div class="pattern-warning-banner">'
            f'<div class="warning-title">\u26a0\ufe0f 死机风险: 中</div>'
            f'<div class="warning-desc">{crash_risk_reason}</div>'
            f'</div>'
        )
    if crash_patterns:
        pattern_tags = "".join(
            f'<span class="pattern-tag {"high" if pt.get("severity")=="高" else "medium"}">'
            f'{esc(pt.get("label",""))}</span>'
            for pt in crash_patterns
        )
        warning_banners.append(
            f'<div class="pattern-warning-banner">'
            f'<div class="warning-title">\U0001f50d 死机模式匹配 ({len(crash_patterns)} 项)</div>'
            f'<div class="pattern-tag-row">{pattern_tags}</div>'
            f'</div>'
        )
    return "\n".join(warning_banners)


def _render_crash_risk_html(crash_risk, crash_risk_reason, crash_patterns) -> str:
    crash_risk_parts: List[str] = []
    if crash_risk and crash_risk != "无":
        risk_color = "#b91c1c" if crash_risk == "高" else "#a16207" if crash_risk == "中" else "#0f766e"
        crash_risk_parts.append(
            f'<div class="info-box crash-risk-box">'
            f'<strong>死机风险等级:</strong> '
            f'<span style="color:{risk_color};font-weight:700">{esc(crash_risk)}</span>'
            f'</div>'
        )
        if crash_risk_reason:
            crash_risk_parts.append(f'<p>{crash_risk_reason}</p>')
    if crash_patterns:
        pattern_items = []
        for pt in crash_patterns:
            lines_html = "".join(
                f'<li><code>{esc(line)}</code></li>'
                for line in pt.get("matched_lines", [])[:3]
            )
            pattern_items.append(
                f'<div class="crash-pattern-item"><strong>{esc(pt.get("label",""))}</strong>'
                f' <span class="pattern-tag {"high" if pt.get("severity")=="高" else "medium"}">'
                f'{esc(pt.get("severity",""))}</span>'
                f'<div class="muted crash-pattern-desc">{esc(pt.get("description",""))}</div>'
                f'<ul class="crash-pattern-lines">{lines_html}</ul></div>'
            )
        crash_risk_parts.append("".join(pattern_items))
    return "\n".join(crash_risk_parts) if crash_risk_parts else '<p class="muted">无死机风险</p>'


def _render_future_fix_html(fix_in_future, repo_base: str = "") -> str:
    if not fix_in_future:
        return ""
    fix_items: List[str] = []
    for fix in fix_in_future:
        fix_sha = esc(fix.get("sha", ""))
        fix_subject = esc(fix.get("subject", ""))
        matched_via = fix.get("matched_via", "direct")
        upstream_ref = fix.get("upstream_sha", "")
        fix_tag = fix.get("fix_tag", "")
        fix_tags = fix.get("fix_tags", [])
        cp_count = fix.get("cherry_pick_count", 0)
        cp_shas = fix.get("cherry_pick_shas", [])

        if repo_base and fix_sha:
            sha_link = (
                f'<a href="{repo_base}{fix_sha}" target="_blank" class="future-fix-sha" '
                f'data-patch-jump="{fix_sha}">'
                f'{fix_sha}</a>'
            )
        else:
            sha_link = f'<code class="future-fix-sha" data-patch-jump="{fix_sha}">{fix_sha}</code>'

        display_title = fix_subject if fix_subject else esc(fix.get("title", ""))
        title_line = f'<div class="future-fix-title">{display_title}</div>'

        tags_to_show = fix_tags if fix_tags else ([fix_tag] if fix_tag else [])
        tag_badges_html = ""
        if tags_to_show:
            badges = []
            for index, raw_tag in enumerate(tags_to_show):
                is_beyond = str(raw_tag).startswith(">")
                display = str(raw_tag)[1:] if is_beyond else str(raw_tag)
                prefix_label = "在 " if is_beyond else ""
                suffix_label = " 之后" if is_beyond else ""
                badge_class = "future-fix-tag primary" if index == 0 else "future-fix-tag"
                badges.append(
                    f'<span class="{badge_class}">{prefix_label}{esc(display)}{suffix_label}</span>'
                )
            tag_badges_html = f'<div class="future-fix-tags">{"".join(badges)}</div>'
        else:
            tag_badges_html = (
                '<div class="future-fix-tags">'
                '<span class="future-fix-tag warn">⚠ 同版本同内核未合入</span></div>'
            )

        cp_html = ""
        if cp_count > 1:
            cp_links = []
            for cp_sha in cp_shas[:6]:
                if repo_base:
                    cp_links.append(
                        f'<a href="{repo_base}{esc(cp_sha)}" target="_blank" class="future-fix-cp" '
                        f'data-patch-jump="{esc(cp_sha)}">'
                        f'{esc(cp_sha)[:12]}</a>'
                    )
                else:
                    cp_links.append(
                        f'<code class="future-fix-cp" data-patch-jump="{esc(cp_sha)}">'
                        f'{esc(cp_sha)[:12]}</code>'
                    )
            cp_html = (
                f'<div class="future-fix-cp-box">'
                f'<strong>{cp_count} 个 cherry-pick:</strong> {", ".join(cp_links)}</div>'
            )

        via_html = ""
        if matched_via != "direct" and upstream_ref:
            if repo_base:
                upstream_link = (
                    f'<a href="{repo_base}{esc(upstream_ref)}" target="_blank" class="future-fix-via">'
                    f'{esc(upstream_ref)}</a>'
                )
            else:
                upstream_link = esc(upstream_ref)
            label = "上游 SHA" if matched_via == "upstream" else "兄弟 SHA"
            via_html = f'<div class="future-fix-via-box">{label}: {upstream_link}</div>'

        merged_subjects = fix.get("merged_subjects", [])
        merged_html = ""
        if merged_subjects and len(merged_subjects) > 1:
            ms_items = "<br>".join(f"&bull; {esc(subject)}" for subject in merged_subjects[:3])
            merged_html = (
                f'<div class="future-fix-merged"><div class="muted">合并的提交:</div>{ms_items}</div>'
            )

        fix_items.append(
            f'<div class="future-fix-item">'
            f'{sha_link}{title_line}{tag_badges_html}{cp_html}{via_html}{merged_html}'
            f'</div>'
        )
    return "".join(fix_items)


def render_patch(idx, p):
    is_llm = bool(p.get("llm_analyzed", False))
    section_type = "llm" if is_llm else "script"

    sha = str(p.get("commit") or p.get("sha") or "")
    title = esc(str(p.get("title", "")))

    # LLM sections
    mod_interp = esc_br((p.get("commit_interpretation_rich") or {}).get("summary", ""))
    logic_changes = (p.get("code_change_analysis_rich") or {}).get("logic_changes", [])
    problem_solved = esc_br((p.get("problem_closure_rich") or {}).get("conclusion", ""))
    introducer = esc_br((p.get("problem_introducer_rich") or {}).get("summary", ""))
    introduced_risk = esc_br(p.get("introduced_risk", ""))

    # Crash risk & defect scan data
    crash_risk = p.get("crash_risk", "")
    crash_risk_reason = esc_br(p.get("crash_risk_reason", ""))
    crash_patterns = p.get("crash_patterns", [])
    fix_in_future = p.get("fix_in_future", [])
    upstream_sha = p.get("upstream_sha", "")

    # Original data
    diff_text = (p.get("diff_preview") or {}).get("text", "")
    score_details = p.get("score_details", {})
    test_suggestions_script = p.get("test_suggestions", {})
    llm_test = esc_br(p.get("llm_test_suggestions", ""))
    commit_url = esc(p.get("commit_url", ""))
    diff_url = esc(p.get("diff_url", ""))
    commit_msg = esc_br(p.get("commit_message_full", ""))

    # Extract base URL for constructing commit links (e.g. https://android.googlesource.com/kernel/common/+/{sha})
    _repo_base = ""
    _raw_commit_url = p.get("commit_url", "")
    if _raw_commit_url and "/+/" in _raw_commit_url:
        _repo_base = _raw_commit_url.rsplit("/+/", 1)[0] + "/+/"

    # Card helper
    def card(title, body, typ=None):
        t = typ or section_type
        return f'''<div class="section-card {t}">
  <div class="section-card-header">{title}</div>
  <div class="section-card-body">{body}</div>
</div>'''

    # Code changes HTML
    code_html_parts = []
    if is_llm and logic_changes:
        for lc in logic_changes:
            loc = esc(lc.get("location", ""))
            expl = esc_br(lc.get("explanation", ""))
            code_html_parts.append(f"<p><strong>位置:</strong> {loc}</p><p>{expl}</p>")
    if diff_text:
        code_html_parts.append(render_diff(diff_text))
    code_html = "".join(code_html_parts) or "<p class='muted'>无代码变化信息</p>"

    # Score details
    score_html = render_score_details(score_details)

    # Test suggestions
    test_parts = []
    if llm_test:
        test_parts.append(f'<div class="info-box"><strong>LLM 定制建议:</strong><br/>{llm_test}</div>')
    ts = test_suggestions_script
    if isinstance(ts, dict):
        script_items = []
        for k, v in [("单元测试", ts.get("unit_test", "")), ("集成测试", ts.get("integration_test", "")),
                      ("回归测试", ts.get("regression_test", "")), ("手工验证", ts.get("manual_validation", "")),
                      ("上线保障", ts.get("release_safeguard", ""))]:
            if v:
                script_items.append(f"<li><strong>{k}:</strong> {esc(v)}</li>")
        if script_items:
            test_parts.append(f'<div class="info-box blue"><strong>脚本建议:</strong><ul style="margin:4px 0;padding-left:18px">{"".join(script_items)}</ul></div>')
    test_html = "".join(test_parts) or "<p class='muted'>无测试建议</p>"

    links_parts = []
    if commit_url:
        links_parts.append(f'<a href="{commit_url}" target="_blank">🔗 原始提交页面</a>')
    if diff_url:
        links_parts.append(f'<a href="{diff_url}" target="_blank">🔗 原始 Diff</a>')
    links_html = f'<div class="link-row">{"".join(links_parts)}</div>' if links_parts else ""

    banners_html = _render_warning_banners(crash_risk, crash_risk_reason, crash_patterns)
    defect_banner_html = _render_defect_summary_banner(fix_in_future, introducer)
    crash_risk_html = _render_crash_risk_html(crash_risk, crash_risk_reason, crash_patterns)
    future_fix_html = _render_future_fix_html(fix_in_future, _repo_base)
    status_badges_html = _render_patch_status_badges(p)
    score_color = _patch_score_color(p.get("score", 0))

    commit_details_html = ""
    if commit_msg:
        commit_details_html = (
            f'<details class="patch-commit-details">'
            f'<summary>📜 Commit 原文</summary>'
            f'<div class="patch-commit-msg">{commit_msg}</div>'
            f'</details>'
        )

    return f'''
<div class="detail-panel" data-llm="{'llm' if is_llm else 'script'}">
  <div class="patch-info-header">
    <div class="patch-info-title">
      <span class="patch-sha">{esc(sha[:12])}</span>
      <span class="patch-title-text">{title}</span>
    </div>
    <div class="patch-info-meta">
      <span class="patch-score" style="color:{score_color}">得分 {(p.get('score',0) or 0):.1f}</span>
      {f'<span class="patch-module">{esc(p.get("dev_module",""))}</span>' if p.get('dev_module') else ''}
      {f'<span class="patch-author">{esc(p.get("author",""))}</span>' if p.get('author') else ''}
      {f'<span class="patch-date">{esc(p.get("date",""))}</span>' if p.get('date') else ''}
      {f'<span class="patch-files">{len(p.get("files",[]) or [])} 个文件</span>' if p.get('files') else ''}
      {f'<span class="patch-upstream" title="上游社区 SHA">upstream {esc(upstream_sha[:12])}</span>' if upstream_sha else ''}
      <span class="patch-type-tag {'llm' if is_llm else 'script'}">{'LLM 分析' if is_llm else '脚本分析'}</span>
    </div>
    {status_badges_html}
    {commit_details_html}
  </div>
  <div class="detail-body">
    {defect_banner_html}
    {banners_html}
    <div class="section-grid">
      <div>
        {card("📝 修改解读", mod_interp or '<p class="muted">暂无 LLM 解读</p>')}
        {card("🔧 代码变化", code_html)}
        {card("🎯 问题闭环", problem_solved or '<p class="muted">暂无 LLM 分析</p>')}
        {card("🔍 引入分析", _introducer_combined(introducer, introduced_risk))}
        {card("🔮 死机风险评估", crash_risk_html)}
        {card("🔗 后续修复", future_fix_html) if future_fix_html else ''}
      </div>
      <div>
        {card("📊 评分明细", score_html)}
        {card("🧪 测试建议", test_html)}
      </div>
    </div>

    <div class="section-card generic patch-links-card">
      <div class="section-card-header">🔗 原始链接</div>
      <div class="section-card-body">{links_html or '<p class="muted">无链接信息</p>'}</div>
    </div>

    <details class="patch-diff-details">
      <summary>📄 展开 Diff</summary>
      <div class="diff-box">{esc_br(diff_text) if diff_text else '<p class="muted">无 diff 信息</p>'}</div>
    </details>
  </div>
</div>
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Render comprehensive LLM-enhanced HTML report")
    parser.add_argument("--input", required=True, help="enriched JSON file")
    parser.add_argument("--output", default="patch-analysis-llm-comprehensive.html", help="output HTML path")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    patches = data.get("patches", [])
    llm_count = sum(1 for p in patches if p.get("llm_analyzed"))
    summary = data.get("summary", {})

    patches_html = "".join(render_patch(i, p) for i, p in enumerate(patches))

    test_summary_html = render_test_summary(patches)

    html = HTML_TEMPLATE.format(
        repo=esc(data.get("repo", "-")),
        from_tag=esc(data.get("from_tag", "-")),
        to_tag=esc(data.get("to_tag", "-")),
        total=data.get("total", 0),
        analyzed=len(patches),
        avg_score=summary.get("avg_score", 0),
        llm_count=llm_count,
        test_summary_html=test_summary_html,
        patches_html=patches_html,
    )
    Path(args.output).write_text(html, encoding="utf-8")
    print(f"Comprehensive LLM report generated: {args.output}")
    print(f"  Total patches: {len(patches)}, LLM analyzed: {llm_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
