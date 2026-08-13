#!/usr/bin/env python3
"""
Merge pre-project audio_device.xml diff onto post-platform baseline.
SOP: workflows/01-projects-repo.md §1.6

Usage:
  python merge_audio_device_xml.py \\
    --pre-project  <old device/transsion/.../audio_device.xml> \\
    --pre-platform <old device/mediatek/.../audio_device.xml> \\
    --post-platform <new device/mediatek/.../audio_device.xml> \\
    --output <new vendor/transsion/projects/.../audio_device.xml>
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

PATH_BLOCK_RE = re.compile(
    r"(?P<block>(?P<prefix>(?:[ \t]*<!--.*?-->[ \t]*\n)*)"
    r"[ \t]*<path\s+name=\"(?P<name>[^\"]+)\"\s+value=\"(?P<value>[^\"]+)\"\s*>.*?</path>)",
    re.DOTALL,
)


def extract_ordered_paths(text: str) -> list[dict]:
    items = []
    for m in PATH_BLOCK_RE.finditer(text):
        items.append(
            {
                "key": (m.group("name"), m.group("value")),
                "block": m.group("block"),
                "start": m.start(),
                "end": m.end(),
            }
        )
    return items


def norm_body(block: str) -> str:
    m = re.search(r"<path[^>]*>(.*)</path>", block, re.DOTALL)
    body = m.group(1) if m else block
    return re.sub(r"\s+", " ", body.strip())


def authoritative_blocks(ordered: list[dict]) -> dict[tuple[str, str], str]:
    out: dict[tuple[str, str], str] = {}
    for item in ordered:
        out[item["key"]] = item["block"]
    return out


def parse_segments(text: str) -> list[tuple]:
    """Split into ('text', str) and ('path', key, block) segments preserving order."""
    segments: list[tuple] = []
    last = 0
    for m in PATH_BLOCK_RE.finditer(text):
        if m.start() > last:
            segments.append(("text", text[last : m.start()]))
        segments.append(("path", (m.group("name"), m.group("value")), m.group("block")))
        last = m.end()
    if last < len(text):
        segments.append(("text", text[last:]))
    return segments


def normalize_line_breaks(text: str) -> str:
    """Split glued tags onto separate lines; remove blank lines (match legacy MTK layout)."""
    text = re.sub(r"</path>[ \t]+(?=<!--)", "</path>\n        ", text)
    text = re.sub(r"</path>[ \t]+(?=<path)", "</path>\n        ", text)
    text = re.sub(r"-->[ \t]+(?=<path)", "-->\n        ", text)
    lines = text.split("\n")
    lines = [ln for ln in lines if ln.strip() != ""]
    trailing_nl = "\n" if text.endswith("\n") else ""
    return "\n".join(lines) + trailing_nl


def segments_to_text(segments: list[tuple]) -> str:
    parts: list[str] = []
    prev_was_path = False
    for seg in segments:
        if seg[0] == "text":
            chunk = seg[1]
            if prev_was_path:
                chunk = chunk.lstrip("\n")
                stripped = chunk.lstrip()
                if stripped and not stripped.startswith("\n"):
                    if stripped.startswith("<!--") or stripped.startswith("<path"):
                        chunk = "\n" + chunk.lstrip("\n")
            parts.append(chunk)
            prev_was_path = False
        else:
            parts.append(seg[2].rstrip() + "\n")
            prev_was_path = True
    return normalize_line_breaks("".join(parts))


def find_path_seg_index(segments: list[tuple], key: tuple[str, str]) -> int | None:
    matches = [i for i, seg in enumerate(segments) if seg[0] == "path" and seg[1] == key]
    return matches[-1] if matches else None


def count_path_keys(text: str) -> Counter:
    c: Counter = Counter()
    for m in re.finditer(r'<path\s+name="([^"]+)"\s+value="([^"]+)"', text):
        c[(m.group(1), m.group(2))] += 1
    return c


def merge(pre_project: str, pre_platform: str, post_platform: str) -> str:
    proj_order = extract_ordered_paths(pre_project)
    plat_order = extract_ordered_paths(pre_platform)
    proj_auth = authoritative_blocks(proj_order)
    plat_auth = authoritative_blocks(plat_order)

    diff_keys: list[tuple[str, str]] = []
    for key, block in proj_auth.items():
        if key not in plat_auth or norm_body(block) != norm_body(plat_auth[key]):
            diff_keys.append(key)

    # insertion plan: last occurrence in project file + anchor = previous path key
    # insertion plan from project file order
    plan: list[dict] = []
    seen: set[tuple[str, str]] = set()
    prev_key: tuple[str, str] | None = None
    for item in proj_order:
        key = item["key"]
        if key in diff_keys and key not in seen:
            seen.add(key)
            plan.append(
                {
                    "key": key,
                    "block": proj_auth[key],
                    "anchor": prev_key,
                    "proj_pos": item["start"],
                }
            )
        prev_key = key

    # 1) parse baseline; drop diff keys; dedupe non-diff keys (keep last occurrence per SOP)
    segments = parse_segments(post_platform)
    last_baseline_idx: dict[tuple[str, str], int] = {}
    for i, seg in enumerate(segments):
        if seg[0] == "path" and seg[1] not in diff_keys:
            last_baseline_idx[seg[1]] = i
    segments = [
        seg
        for i, seg in enumerate(segments)
        if seg[0] != "path"
        or (seg[1] not in diff_keys and i == last_baseline_idx[seg[1]])
    ]

    # 2) insert project blocks after anchor path segment (bottom-up)
    plan.sort(key=lambda x: x["proj_pos"], reverse=True)
    keys_in_order = [item["key"] for item in proj_order]
    for entry in plan:
        anchor = entry["anchor"]
        idx = None
        if anchor is not None:
            idx = find_path_seg_index(segments, anchor)
        if idx is None:
            key_idx = keys_in_order.index(entry["key"])
            for j in range(key_idx - 1, -1, -1):
                idx = find_path_seg_index(segments, keys_in_order[j])
                if idx is not None:
                    break
        if idx is None:
            # after versioncontrol text
            vc = "</versioncontrol>"
            for i, seg in enumerate(segments):
                if seg[0] == "text" and vc in seg[1]:
                    tail = seg[1].split(vc, 1)
                    segments[i] = ("text", tail[0] + vc + "\n" + entry["block"] + tail[1])
                    idx = -2  # handled
                    break
            if idx is None:
                raise RuntimeError(f"cannot anchor path key {entry['key']}")
        elif idx >= 0:
            segments.insert(idx + 1, ("path", entry["key"], entry["block"]))

    return segments_to_text(segments)


def validate(result: str, post_platform: str, pre_project: str) -> None:
    dup = [k for k, v in count_path_keys(result).items() if v > 1]
    if dup:
        raise SystemExit(f"duplicate path keys: {dup[:10]} (total {len(dup)})")

    if "</mixercontrol>" not in result or result.count("</mixercontrol>") != 1:
        raise SystemExit(
            f"expected exactly one </mixercontrol>, got {result.count('</mixercontrol>')}"
        )

    baseline_mixer_end = post_platform.find("</mixercontrol>")
    tail = post_platform[baseline_mixer_end:]
    if tail.strip() and tail.strip() not in result[result.find("</mixercontrol>") :]:
        raise SystemExit("missing content after </mixercontrol> (outputdevice etc.)")

    min_size = int(len(post_platform) * 0.85)
    if len(result) < min_size:
        raise SystemExit(
            f"result too small: {len(result)} bytes < 85% of baseline {len(post_platform)}"
        )

    proj_comments = pre_project.count("<!--")
    result_comments = result.count("<!--")
    if result_comments < proj_comments * 0.7:
        raise SystemExit(
            f"comment count dropped suspiciously: {result_comments} vs project {proj_comments}"
        )

    glued = len(re.findall(r"</path>[ \t]+(?:<!--|<path)", result))
    if glued:
        raise SystemExit(f"formatting: {glued} glued </path> lines (expected 0)")
    if re.search(r"\n\s*\n", result):
        raise SystemExit("formatting: blank lines found (expected none)")

    try:
        ET.fromstring(result)
    except ET.ParseError as e:
        raise SystemExit(f"XML parse error: {e}") from e


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge audio_device.xml per DRV_Audio_Adapt §1.6")
    ap.add_argument("--pre-project", required=True)
    ap.add_argument("--pre-platform", required=True)
    ap.add_argument("--post-platform", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()

    pre_project = Path(args.pre_project).read_text(encoding="utf-8", errors="replace")
    pre_platform = Path(args.pre_platform).read_text(encoding="utf-8", errors="replace")
    post_platform = Path(args.post_platform).read_text(encoding="utf-8", errors="replace")

    result = merge(pre_project, pre_platform, post_platform)
    validate(result, post_platform, pre_project)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(result, encoding="utf-8")

    diff_n = len(
        [
            k
            for k in authoritative_blocks(extract_ordered_paths(pre_project))
            if k not in authoritative_blocks(extract_ordered_paths(pre_platform))
            or norm_body(authoritative_blocks(extract_ordered_paths(pre_project))[k])
            != norm_body(authoritative_blocks(extract_ordered_paths(pre_platform))[k])
        ]
    )
    keys_total = len(count_path_keys(result))
    print(
        f"OK: wrote {out} ({len(result)} bytes), diff_keys={diff_n}, path_keys={keys_total}, dup=0"
    )


if __name__ == "__main__":
    main()
