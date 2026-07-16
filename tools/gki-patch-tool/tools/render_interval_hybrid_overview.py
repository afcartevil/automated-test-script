#!/usr/bin/env python3
"""
从 patch_analyzer 区间 JSON 生成「脚本汇总 + 大模型综合研判」概览 HTML。

典型用法（在 render_report_indexed 生成索引之后）：

  python tools/render_interval_hybrid_overview.py \\
    --input outputs/patch-analysis.json \\
    --indexed-dir outputs/my-indexed-folder \\
    --output outputs/my-indexed-folder/interval-hybrid-overview.html

大模型段落可来自：
  --narrative-file path/to.txt   （UTF-8，支持与 HTML 换行）
若不提供：根据 summary 与各档位数生成一段默认说明性综述（可随时用手写文件替换）。

索引页文件名：<input basename>-indexed.html，若 --indexed-html 省略则在 indexed-dir 下自动探测 *-indexed.html。
"""
from __future__ import annotations

import argparse
import html as html_std
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple


def esc(s: object) -> str:
    return html_std.escape(str(s), quote=True)


def lowest_highest_scores(
    patches: List[Dict[str, Any]], n_low: int = 15, n_high: int = 5
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    pts = [(float(p.get("score", 0)), p) for p in patches]
    pts.sort(key=lambda x: x[0])
    low = [p for _, p in pts[: max(1, min(n_low, len(pts)))]]
    high = []
    if pts:
        pts_rev = pts[::-1]
        high = [p for _, p in pts_rev[: max(1, min(n_high, len(pts_rev)))]]
    return low, high


def default_narrative(data: Dict[str, Any]) -> str:
    s = data.get("summary") or {}
    repo = data.get("repo", "")
    ft = data.get("from_tag", "")
    tt = data.get("to_tag", "")
    total = int(data.get("total") or data.get("analyzed") or 0)
    avg = s.get("avg_score", 0)
    blocked = s.get("blocked_count", 0)
    counts = s.get("recommendation_counts") or {}
    paragraphs: List[str] = [
        f"区间为 {ft} → {tt}，仓库 {repo}。",
        f"脚本侧：共分析 {total} 笔 patch；区间平均分 {avg} / 10；硬阻断笔数 {blocked}。合入档位分布见「一、脚本口径」表格，全部来自 patch_analyzer 与 scoring-config，本页未另行计分。",
    ]
    bullets = [
        "本配置下「测试证据」信号对大量 patch 为负向贡献时，「有条件合入」往往成为统计上的主档位；这不等于可以不做回归，而是提示：应结合业务相关子系统做抽样深度审阅。",
        "优先复核：不建议合入、需大幅修改与硬阻断条目；对其余「有条件合入」按发布影响面与目录（如 mm、drivers、security）排优先级。",
        "单笔语义仍以「索引表 → 明细页」中的结构化字段为准；区间综述仅便于发布决策与分工。",
    ]
    paragraphs.append("\n".join("- " + b for b in bullets))
    if counts:
        ctext = "；".join(f"{k}: {v}" for k, v in counts.items())
        paragraphs.append(f"档位笔数汇总：{ctext}。")
    return "\n\n".join(paragraphs)


def mdish_to_paragraphs(text: str) -> str:
    """简单把段落拆成 <p>/<ul>。"""
    text = text.strip()
    parts: List[str] = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("- "):
            items = []
            for ln in block.splitlines():
                if ln.startswith("- "):
                    items.append(f"<li>{esc(ln[2:].strip())}</li>")
            if items:
                parts.append("<ul>" + "".join(items) + "</ul>")
            else:
                parts.append("<p>" + esc(block) + "</p>")
        else:
            parts.append("<p>" + esc(block).replace("\n", "<br/>") + "</p>")
    return "\n".join(parts) if parts else "<p>（暂无综合研判文本）</p>"


OVERVIEW_CSS = """<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; color: #1f2937; max-width: 1100px; }
h1, h2 { margin: 0 0 12px 0; }
.muted { color: #6b7280; font-size: 14px; }
.grid { display: grid; grid-template-columns: repeat(4, minmax(120px, 1fr)); gap: 12px; margin: 16px 0; }
.card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; background: #fff; }
.v { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
.k { font-size: 12px; color: #6b7280; }
.panel { border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin: 16px 0; background: #fafafa; }
.panel h2 { font-size: 16px; }
table { border-collapse: collapse; width: 100%; font-size: 13px; margin-top: 8px; }
th, td { border: 1px solid #e5e7eb; padding: 6px 8px; text-align: left; vertical-align: top; }
th { background: #f3f4f6; }
a { color: #2563eb; text-decoration: none; }
a:hover { text-decoration: underline; }
code { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: 12px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 6px; background: #eef2ff; color: #3730a3; font-size: 12px; }
</style>"""


def find_indexed_html(indexed_dir: Path) -> Path | None:
    matches = list(indexed_dir.glob("*-indexed.html"))
    if len(matches) == 1:
        return matches[0]
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="区间混合概览 HTML（脚本汇总 + 大模型综合研判）")
    ap.add_argument("--input", required=True, help="patch_analyzer 区间 JSON")
    ap.add_argument("--indexed-dir", help="render_report_indexed 输出目录（用于相对链接）")
    ap.add_argument("--indexed-html", help="索引页文件名或相对 indexed-dir 的路径，默认自动探测 *-indexed.html")
    ap.add_argument("--narrative-file", help="UTF-8 大模型综述文本（可选）")
    ap.add_argument("--output", required=True, help="输出 hybrid overview HTML 路径")
    args = ap.parse_args()

    inp = Path(args.input)
    data = json.loads(inp.read_text(encoding="utf-8"))
    patches: List[Dict[str, Any]] = data.get("patches") or []
    summary = data.get("summary") or {}

    indexed_dir = Path(args.indexed_dir) if args.indexed_dir else None
    indexed_href = "#"
    indexed_name = "（未配置索引页）"
    out_path = Path(args.output).resolve()
    if indexed_dir and indexed_dir.is_dir():
        idx: Path | None = None
        if args.indexed_html:
            cand = Path(args.indexed_html)
            idx = cand if cand.is_file() else indexed_dir / args.indexed_html
        else:
            idx = find_indexed_html(indexed_dir)
        if idx and idx.is_file():
            try:
                indexed_href = Path(
                    os.path.relpath(idx.resolve(), out_path.parent)
                ).as_posix()
            except ValueError:
                indexed_href = idx.name
            indexed_name = idx.name

    low, high = lowest_highest_scores(patches)
    if args.narrative_file:
        narrative_body = Path(args.narrative_file).read_text(encoding="utf-8")
        narrative_html = mdish_to_paragraphs(narrative_body)
    else:
        narrative_html = mdish_to_paragraphs(default_narrative(data))

    rows_low = []
    for p in low:
        sha = esc(p.get("commit", ""))
        rel = f"details-html/{sha}.html"
        rows_low.append(
            f"<tr><td><code>{sha[:12]}…</code></td><td>{esc(p.get('title', '')[:100])}</td>"
            f"<td>{float(p.get('score', 0)):.1f}</td><td>{esc(p.get('recommendation', ''))}</td>"
            f"<td><a href='{esc(rel)}' target='_blank'>明细</a></td></tr>"
        )

    rows_high = []
    for p in high:
        sha = esc(p.get("commit", ""))
        rel = f"details-html/{sha}.html"
        rows_high.append(
            f"<tr><td><code>{sha[:12]}…</code></td><td>{esc(p.get('title', '')[:100])}</td>"
            f"<td>{float(p.get('score', 0)):.1f}</td><td>{esc(p.get('recommendation', ''))}</td>"
            f"<td><a href='{esc(rel)}' target='_blank'>明细</a></td></tr>"
        )

    ft, tt = data.get("from_tag", ""), data.get("to_tag", "")
    total = int(data.get("total") or len(patches))
    avg = summary.get("avg_score", 0)
    blocked = summary.get("blocked_count", 0)

    html_out = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>区间混合报告（脚本 + 综合研判）</title>
  {OVERVIEW_CSS}
</head>
<body>
  <p class="muted"><span class="badge">patch-analysis-score · 区间</span></p>
  <h1>Tag 区间混合报告</h1>
  <p class="muted">仓库: {esc(data.get("repo", ""))}<br/>
  区间: {esc(ft)} → {esc(tt)}<br/>
  脚本 JSON: {esc(inp.name)}</p>

  <div class="grid">
    <div class="card"><div class="v">{esc(total)}</div><div class="k">分析笔数</div></div>
    <div class="card"><div class="v">{esc(avg)}</div><div class="k">平均分</div></div>
    <div class="card"><div class="v">{esc(blocked)}</div><div class="k">硬阻断笔数</div></div>
    <div class="card"><div class="v"><a href="{esc(indexed_href)}" target="_blank">打开索引表</a></div><div class="k">{esc(indexed_name)}</div></div>
  </div>

  <div class="panel">
    <h2>一、脚本口径（JSON 真源）</h2>
    <p>合入档位分布与每笔分数、明细均来自 <code>patch_analyzer.py</code>；本页仅做区间汇总与导航，不重算分数。</p>
    <table>
      <thead><tr><th>档位</th><th>笔数</th></tr></thead>
      <tbody>
"""
    for k, v in (summary.get("recommendation_counts") or {}).items():
        html_out += f"<tr><td>{esc(k)}</td><td>{esc(v)}</td></tr>\n"
    html_out += """      </tbody>
    </table>
  </div>

  <div class="panel">
    <h2>二、大模型综合研判（区间）</h2>
"""
    html_out += narrative_html
    html_out += """
    <p class="muted">说明：区间级表述为在阅读脚本统计后的综述，不修改各笔 JSON；若与明细冲突以 commit 明细与代码为准。</p>
  </div>

  <div class="panel">
    <h2>三、低分样例（脚本分数升序 · 抽检用）</h2>
    <table>
      <thead><tr><th>Commit</th><th>标题</th><th>分数</th><th>建议</th><th>明细</th></tr></thead>
      <tbody>
""" + "\n".join(
        rows_low
    )
    html_out += """
      </tbody>
    </table>
  </div>

  <div class="panel">
    <h2>四、高分样例（脚本分数降序 · 对照用）</h2>
    <table>
      <thead><tr><th>Commit</th><th>标题</th><th>分数</th><th>建议</th><th>明细</th></tr></thead>
      <tbody>
""" + "\n".join(rows_high)
    html_out += """
      </tbody>
    </table>
  </div>
</body>
</html>
"""

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html_out, encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
