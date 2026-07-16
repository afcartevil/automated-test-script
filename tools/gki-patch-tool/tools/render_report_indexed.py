#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from render_report import (
    HTML_TEMPLATE,
    build_closure_rich_html,
    build_commit_rich_html,
    build_code_rich_html,
    build_introducer_html,
    build_score_details_html,
    build_source_html,
    build_tags_inline_html,
    build_test_suggestions_html,
    get_display_tags,
    get_patch_tags,
    tone_class,
)


def esc(value: object) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


def build_summary(patches: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not patches:
        return {
            "avg_score": 0,
            "blocked_count": 0,
            "recommendation_counts": {"建议合入": 0, "有条件合入": 0, "需大幅修改": 0, "不建议合入": 0},
            "intent_tag_counts": {"fix bug": 0, "新需求": 0},
        }
    avg = round(sum(float(p.get("score", 0)) for p in patches) / len(patches), 1)
    blocked = sum(1 for p in patches if p.get("blocked"))
    counts: Dict[str, int] = {"建议合入": 0, "有条件合入": 0, "需大幅修改": 0, "不建议合入": 0}
    for patch in patches:
        rec = str(patch.get("recommendation", "有条件合入"))
        counts[rec] = counts.get(rec, 0) + 1
    fix_bug_n = sum(
        1
        for p in patches
        for t in (p.get("patch_tags") or [])
        if str((t or {}).get("label", "")).strip() == "fix bug"
    )
    feat_n = sum(
        1
        for p in patches
        for t in (p.get("patch_tags") or [])
        if str((t or {}).get("label", "")).strip() == "新需求"
    )
    return {
        "avg_score": avg,
        "blocked_count": blocked,
        "recommendation_counts": counts,
        "intent_tag_counts": {"fix bug": fix_bug_n, "新需求": feat_n},
    }


def build_dataset(base_data: Dict[str, Any], patches: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {
        "repo": base_data.get("repo", ""),
        "from_tag": base_data.get("from_tag", ""),
        "to_tag": base_data.get("to_tag", ""),
        "total": len(patches),
        "analyzed": len(patches),
        "failed": 0,
        "failed_items": [],
        "summary": build_summary(patches),
        "patches": patches,
    }


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def file_stem(name: str) -> str:
    stem = []
    for ch in name:
        if ch.isalnum() or ch in ("-", "_", "."):
            stem.append(ch)
        else:
            stem.append("-")
    return "".join(stem).strip("-") or "report"


INDEX_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Patch 分析索引报告</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2937; }
    h1, h2 { margin: 0 0 12px 0; }
    .muted { color: #6b7280; }
    .grid { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; margin: 16px 0 20px 0; }
    .card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; background: #fff; }
    .v { font-size: 24px; font-weight: 700; margin-bottom: 6px; }
    .k { font-size: 12px; color: #6b7280; }
    table { border-collapse: collapse; width: 100%; margin-top: 12px; }
    th, td { border: 1px solid #e5e7eb; padding: 8px; text-align: left; font-size: 13px; vertical-align: top; }
    th { background: #f9fafb; position: sticky; top: 0; }
    .ok { color: #0f766e; }
    .warn { color: #a16207; }
    .bad { color: #b91c1c; }
    .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 12px; border: 1px solid #d1d5db; }
    .tag { display: inline-block; padding: 2px 7px; border-radius: 999px; font-size: 12px; background: #eef2ff; color: #3730a3; border: 1px solid #c7d2fe; margin: 1px 3px 1px 0; }
    .toolbar { display: flex; gap: 8px; margin: 8px 0 12px 0; }
    input, select { padding: 6px 8px; border: 1px solid #d1d5db; border-radius: 6px; }
    a { color: #2563eb; text-decoration: none; }
    a:hover { text-decoration: underline; }
    code { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; }
  </style>
</head>
<body>
  <h1>Patch 分析索引报告</h1>
  <p class="muted">仓库: __REPO__<br/>区间: __FROM_TAG__ -> __TO_TAG__</p>
  <div class="grid">
    <div class="card"><div class="v">__TOTAL__</div><div class="k">区间总数</div></div>
    <div class="card"><div class="v">__AVG_SCORE__</div><div class="k">平均分</div></div>
    <div class="card"><div class="v">__BLOCKED_COUNT__</div><div class="k">阻断数</div></div>
    <div class="card"><div class="v">__DETAIL_COUNT__</div><div class="k">详情页数</div></div>
  </div>
  <p class="muted">意图类标签（部分提交）：「fix bug」 __TAG_FIX__ 笔 | 「新需求」 __TAG_NEW__ 笔</p>
  <div class="toolbar">
    <select id="recFilter">
      <option value="">全部建议</option>
      <option>建议合入</option>
      <option>有条件合入</option>
      <option>需大幅修改</option>
      <option>不建议合入</option>
    </select>
    <input id="kw" placeholder="按 commit/标题/标签/风险过滤" />
  </div>
  <table id="t">
    <thead>
      <tr>
        <th>Commit</th>
        <th>标题</th>
        <th>分数</th>
        <th>建议</th>
        <th>阻断</th>
        <th>标签</th>
        <th>关键风险</th>
        <th>详情</th>
      </tr>
    </thead>
    <tbody>
__ROWS__
    </tbody>
  </table>
  <script>
    const recFilter = document.getElementById('recFilter');
    const kw = document.getElementById('kw');
    const rows = Array.from(document.querySelectorAll('#t tbody tr'));
    function applyFilter() {
      const rec = recFilter.value.trim();
      const q = kw.value.trim().toLowerCase();
      rows.forEach((r) => {
        const rRec = r.dataset.rec || '';
        const txt = (r.innerText || '').toLowerCase();
        const okRec = !rec || rRec === rec;
        const okKw = !q || txt.includes(q);
        r.style.display = (okRec && okKw) ? '' : 'none';
      });
    }
    recFilter.addEventListener('change', applyFilter);
    kw.addEventListener('input', applyFilter);
  </script>
</body>
</html>
"""
def build_row(patch: Dict[str, Any], href: str) -> str:
    rec = str(patch.get("recommendation", ""))
    blocked = bool(patch.get("blocked", False))
    css = tone_class(rec, blocked)
    display_tags = get_display_tags(patch)
    return (
        "<tr data-rec='{rec}'>"
        "<td><code>{sha}</code></td>"
        "<td>{title}</td>"
        "<td>{score:.1f}</td>"
        "<td><span class='pill {css}'>{rec}</span></td>"
        "<td>{blocked}</td>"
        "<td>{tags}</td>"
        "<td>{risk}</td>"
        "<td><a href='{href}' target='_blank'>打开详情</a></td>"
        "</tr>"
    ).format(
        rec=esc(rec),
        sha=esc(patch.get("commit", "")),
        title=esc(patch.get("title", "")),
        score=float(patch.get("score", 0)),
        css=css,
        blocked="是" if blocked else "否",
        tags=build_tags_inline_html(display_tags),
        risk=esc(patch.get("key_risk", "")),
        href=esc(href),
    )


def render_index(data: Dict[str, Any], rows_html: str, detail_count: int) -> str:
    summary = data.get("summary", {})
    html = INDEX_TEMPLATE
    itc = summary.get("intent_tag_counts") or {}
    replacements = {
        "__REPO__": esc(data.get("repo", "-")),
        "__FROM_TAG__": esc(data.get("from_tag", "-")),
        "__TO_TAG__": esc(data.get("to_tag", "-")),
        "__TOTAL__": esc(data.get("total", 0)),
        "__AVG_SCORE__": esc(summary.get("avg_score", 0)),
        "__BLOCKED_COUNT__": esc(summary.get("blocked_count", 0)),
        "__DETAIL_COUNT__": esc(detail_count),
        "__ROWS__": rows_html,
        "__TAG_FIX__": esc(itc.get("fix bug", 0)),
        "__TAG_NEW__": esc(itc.get("新需求", 0)),
    }
    for key, value in replacements.items():
        html = html.replace(key, value)
    return html


def render_single_patch_html(base_data: Dict[str, Any], patch: Dict[str, Any]) -> str:
    summary = build_dataset(base_data, [patch]).get("summary", {})
    rec_counts = summary.get("recommendation_counts", {})
    rec = str(patch.get("recommendation", ""))
    blocked = bool(patch.get("blocked", False))
    css = tone_class(rec, blocked)
    score_details = patch.get("score_details", {})
    why_scored = patch.get("why_scored", [])
    test_suggestions = patch.get("test_suggestions", {})
    change_summary = patch.get("change_summary", "")
    problem_solved = patch.get("problem_solved", "")
    commit_interpretation_rich = patch.get("commit_interpretation_rich", {})
    code_change_analysis_rich = patch.get("code_change_analysis_rich", {})
    problem_closure_rich = patch.get("problem_closure_rich", {})
    problem_introducer_rich = patch.get("problem_introducer_rich", {})
    commit_url = patch.get("commit_url", "")
    diff_url = patch.get("diff_url", "")
    commit_message_full = patch.get("commit_message_full", "")
    diff_preview = patch.get("diff_preview", {})
    display_tags = get_display_tags(patch)
    detail_html = (
        "<tr class='detail-row' data-rec='{rec}'>"
        "<td colspan='7' class='detail-cell'>"
        "<details open>"
        "<summary>查看评分明细 / 建议测试项</summary>"
        "<div class='detail-grid'>"
        "<div class='detail-card'><div class='detail-title'>意图（Commit 信息）</div><div class='detail-body'>{commit_rich}</div></div>"
        "<div class='detail-card'><div class='detail-title'>代码变化（Code Diff）</div><div class='detail-body'>{code_rich}</div></div>"
        "<div class='detail-card' style='grid-column: span 2;'><div class='detail-title'>问题闭环（解决了什么）</div><div class='detail-body'>{closure_rich}</div></div>"
        "<div class='detail-card' style='grid-column: span 2;'><div class='detail-title'>问题引入（由哪笔引入）</div><div class='detail-body'>{introducer_rich}</div></div>"
        "<div class='detail-card' style='grid-column: span 2;'><div class='detail-title'>原始提交与 Diff</div><div class='detail-body'>{source}</div></div>"
        "<div class='detail-card'><div class='detail-title'>评分明细</div><div class='detail-body'>{score_details}</div></div>"
        "<div class='detail-card'><div class='detail-title'>建议测试项</div><div class='detail-body'>{test_suggestions}</div></div>"
        "</div>"
        "</details>"
        "</td>"
        "</tr>"
    ).format(
        rec=esc(rec),
        commit_rich=build_commit_rich_html(commit_interpretation_rich, commit_message_full=commit_message_full),
        code_rich=build_code_rich_html(code_change_analysis_rich),
        closure_rich=build_closure_rich_html(problem_closure_rich, problem_solved, change_summary),
        introducer_rich=build_introducer_html(problem_introducer_rich),
        source=build_source_html(commit_url, diff_url, commit_message_full, diff_preview),
        score_details=build_score_details_html(score_details, why_scored),
        test_suggestions=build_test_suggestions_html(test_suggestions),
    )
    rows = (
        "<tr class='main-row' data-rec='{rec}'>"
        "<td><code>{sha}</code></td>"
        "<td>{title}</td>"
        "<td>{score:.1f}</td>"
        "<td><span class='pill {css}'>{rec}</span></td>"
        "<td>{blocked}</td>"
        "<td>{tags}</td>"
        "<td>{risk}</td>"
        "</tr>{detail}".format(
            rec=rec,
            sha=esc(str(patch.get("commit", ""))),
            title=esc(str(patch.get("title", ""))),
            score=float(patch.get("score", 0)),
            css=css,
            blocked="是" if blocked else "否",
            tags=build_tags_inline_html(display_tags),
            risk=esc(str(patch.get("key_risk", ""))),
            detail=detail_html,
        )
    )
    itc = summary.get("intent_tag_counts") or {}
    return HTML_TEMPLATE.format(
        repo=base_data.get("repo", "-"),
        from_tag=base_data.get("from_tag", "-"),
        to_tag=base_data.get("to_tag", "-"),
        total=1,
        analyzed=1,
        avg_score=summary.get("avg_score", 0),
        blocked_count=summary.get("blocked_count", 0),
        rec_ok=rec_counts.get("建议合入", 0),
        rec_cond=rec_counts.get("有条件合入", 0),
        rec_rework=rec_counts.get("需大幅修改", 0),
        rec_no=rec_counts.get("不建议合入", 0),
        tag_fix_bug=itc.get("fix bug", 0),
        tag_new_req=itc.get("新需求", 0),
        rows=rows,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Render index + per-patch HTML reports from patch analyzer JSON")
    parser.add_argument("--input", required=True, help="input JSON file")
    parser.add_argument("--output-dir", required=True, help="output directory for index/detail reports")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    patches: List[Dict[str, Any]] = data.get("patches", []) or []

    details_json_dir = output_dir / "details-json"
    details_html_dir = output_dir / "details-html"
    details_json_dir.mkdir(parents=True, exist_ok=True)
    details_html_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for patch in patches:
        commit = str(patch.get("commit", "unknown"))
        detail_json = details_json_dir / f"{commit}.json"
        detail_html = details_html_dir / f"{commit}.html"
        write_json(detail_json, build_dataset(data, [patch]))
        detail_html.write_text(render_single_patch_html(data, patch), encoding="utf-8")
        rows.append(build_row(patch, f"details-html/{detail_html.name}"))

    index_path = output_dir / f"{file_stem(input_path.stem)}-indexed.html"
    index_path.write_text(render_index(data, "\n".join(rows), len(patches)), encoding="utf-8")
    print(f"Indexed report generated: {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
