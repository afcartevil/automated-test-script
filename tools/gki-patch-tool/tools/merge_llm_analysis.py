#!/usr/bin/env python3
"""Merge LLM analysis results back into the original patch analyzer JSON (v2 - richer format)."""
import argparse
import json
import sys
from pathlib import Path

import yaml


def parse_llm_analysis(yaml_path: Path) -> dict:
    raw = yaml_path.read_text(encoding="utf-8")
    records = yaml.safe_load(raw)
    if not isinstance(records, list):
        print(f"Error: expected a YAML list, got {type(records).__name__}", file=sys.stderr)
        sys.exit(1)
    indexed = {}
    for rec in records:
        sha = rec.get("sha", "").strip()
        if sha:
            indexed[sha] = rec
    return indexed


def _match_sha(patch_sha: str, analysis_shas: dict) -> tuple:
    if patch_sha in analysis_shas:
        return True, analysis_shas[patch_sha]
    prefix = patch_sha[:12]
    if prefix in analysis_shas:
        return True, analysis_shas[prefix]
    return False, None


def build_commit_interpretation_rich(a: dict) -> dict:
    return {
        "title": a.get("title", ""),
        "problem_context": "",
        "constraint_context": "",
        "summary": a.get("modification_interpretation", ""),
        "signals": [],
        "references": [],
        "fixes_closes": [],
        "llm_generated": True,
    }


def build_code_change_analysis_rich(a: dict) -> dict:
    raw_changes = a.get("code_changes", [])
    if not raw_changes:
        raw_changes = [{"location": "综合", "explanation": a.get("code_analysis", "")}]
    return {
        "summary": "",
        "touched_directories": [],
        "files_stat": [],
        "logic_changes": [
            {"location": c.get("location", ""), "explanation": c.get("explanation", ""), "before": "", "after": ""}
            for c in raw_changes
        ],
        "llm_generated": True,
    }


def build_problem_closure_rich(a: dict) -> dict:
    return {
        "status": "已分析",
        "confidence": "高",
        "evidence": [],
        "conclusion": a.get("problem_solved", ""),
        "why_fixed": a.get("problem_solved", ""),
        "missing_evidence": "",
        "acceptance": "",
        "llm_generated": True,
    }


def build_problem_introducer_rich(a: dict) -> dict:
    text = a.get("introducer_analysis", "")
    detected = bool(text) and "未识别" not in text and "不适用" not in text
    return {
        "detected": detected,
        "confidence": "高" if detected else "低",
        "detection_method": "LLM分析（commit + 代码比对）",
        "summary": text,
        "introducer_commit": "",
        "introducer_title": "",
        "introducer_commit_url": "",
        "introducer_diff_url": "",
        "introduced_change_summary": "",
        "why_introduced": "",
        "evidence": [],
        "llm_generated": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge LLM analysis into patch JSON (v2)")
    parser.add_argument("--input", required=True, help="original JSON from patch_analyzer")
    parser.add_argument("--analysis", required=True, help="YAML file with LLM analysis")
    parser.add_argument("--output", required=True, help="output enriched JSON path")
    args = parser.parse_args()

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    patches = data.get("patches", [])
    analysis_map = parse_llm_analysis(Path(args.analysis))

    updated = 0
    for p in patches:
        sha = p.get("commit", "")
        matched, a = _match_sha(sha, analysis_map)
        if matched:
            p["commit_interpretation_rich"] = build_commit_interpretation_rich(a)
            p["code_change_analysis_rich"] = build_code_change_analysis_rich(a)
            p["problem_closure_rich"] = build_problem_closure_rich(a)
            p["problem_introducer_rich"] = build_problem_introducer_rich(a)
            # Store LLM test suggestions in a separate field
            ts = a.get("test_suggestions", "")
            if ts:
                p["llm_test_suggestions"] = ts
            p["llm_analyzed"] = True
            updated += 1

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Merged LLM analysis: {updated} patches updated -> {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
