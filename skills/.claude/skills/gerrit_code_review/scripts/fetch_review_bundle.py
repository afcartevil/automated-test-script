#!/usr/bin/env python3
"""CLI entry: fetch Gerrit review bundle JSON for agent code review."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from gerrit_client import (
    build_review_bundle,
    load_auth,
    report_file_url,
    report_path_for_change,
    report_path_for_topic,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Gerrit review bundle for code review.")
    parser.add_argument("input", help="Gerrit change URL/number or topic URL/topic:xxx")
    parser.add_argument(
        "--output",
        "-o",
        default="review-bundle.json",
        help="Output JSON path (default: review-bundle.json)",
    )
    parser.add_argument(
        "--cred-file",
        type=Path,
        default=None,
        help="Credential JSON path (default: skill cred.json)",
    )
    parser.add_argument(
        "--expand-files",
        action="store_true",
        help="Fetch full content for each modified file",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        auth = load_auth(args.cred_file)
        bundle = build_review_bundle(
            args.input,
            auth=auth,
            cred_file=args.cred_file,
            expand_files=args.expand_files,
        )
    except Exception as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1

    output_path = Path(args.output)
    text = json.dumps(bundle, ensure_ascii=False, indent=2 if args.pretty else None)
    output_path.write_text(text, encoding="utf-8")

    kind = bundle.get("kind", "change")
    count = len(bundle.get("changes", []))
    modules_display = bundle.get("modules_display", "")
    if kind == "topic":
        topic = bundle.get("topic", "")
        print(f"OK topic={topic!r} changes={count} output={output_path}")
        if modules_display:
            print(f"modules={modules_display}")
        if topic:
            report_path = report_path_for_topic(topic)
            print(f"report_path={report_path}")
            print(f"report_url={report_file_url(report_path)}")
    else:
        number = bundle["changes"][0]["number"] if bundle.get("changes") else "unknown"
        print(f"OK change={number} output={output_path}")
        if modules_display:
            print(f"modules={modules_display}")
        report_path = report_path_for_change(number)
        print(f"report_path={report_path}")
        print(f"report_url={report_file_url(report_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
