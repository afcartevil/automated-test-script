#!/usr/bin/env python3
"""Extract patches from JSON analysis into a compact markdown template for LLM analysis."""
import argparse
import json
import sys
from pathlib import Path


def esc(v: object) -> str:
    return str(v or "")


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract patches for LLM analysis")
    parser.add_argument("--input", required=True, help="input JSON from patch_analyzer")
    parser.add_argument("--output", required=True, help="output markdown template path")
    parser.add_argument("--start", type=int, default=0, help="starting patch index (0-based)")
    parser.add_argument("--count", type=int, default=5, help="number of patches to extract")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    patches = data.get("patches", [])
    total = len(patches)
    end = min(args.start + args.count, total)

    lines = [
        f"# LLM Patch 分析任务\n",
        f"来源: {data.get('repo', '-')}",
        f"区间: {data.get('from_tag', '-')} -> {data.get('to_tag', '-')}",
        f"总patch数: {total}",
        f"本批索引: {args.start} - {end - 1} (共 {end - args.start} 笔)",
        "",
    ]

    for idx in range(args.start, end):
        p = patches[idx]
        sha = p.get("commit", "")[:12]
        title = esc(p.get("title", ""))
        msg = esc(p.get("commit_message_full", ""))
        diff = esc(p.get("diff_preview", {}).get("text", ""))
        score = p.get("score", 0)
        rec = p.get("recommendation", "")

        lines.append(f"---")
        lines.append(f"## Patch {idx}: `{sha}`")
        lines.append(f"**标题**: {title}")
        lines.append(f"**脚本评分**: {score}/10 | **建议**: {rec}")
        lines.append("")
        lines.append("### Commit Message")
        lines.append("```")
        lines.append(msg)
        lines.append("```")
        lines.append("")
        lines.append("### Diff 预览")
        lines.append("```diff")
        lines.append(diff)
        lines.append("```")
        lines.append("")

    # Write output
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Extracted {end - args.start} patches to {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
