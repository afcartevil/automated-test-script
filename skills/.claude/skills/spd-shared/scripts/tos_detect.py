"""
Shared TOS major.minor detection for SPD scripts.

Priority:
1) env SPD_TOS_VERSION (e.g. 16.3.1)
2) Dedicated TOS props on device (see TOS_PROP_KEYS_DEFAULT)
3) Fallback: parse `adb shell sh -c 'getprop | grep version'` output and extract
   the first N.M pattern from each line's value (or raw line), then pick the best
   candidate (prefer keys containing tos/tranos, then major>=16).
"""

from __future__ import annotations

import os
import re
from typing import Optional, Tuple

TOS_PROP_KEYS_DEFAULT = (
    "ro.transsion.tos.version",
    "ro.vendor.transsion.tos.version",
    "ro.build.tranos.version",
    "ro.tranos.version",
)

PROP_LINE_RE = re.compile(r"^\[(?P<key>.+?)\]:\s*\[(?P<value>.*)\]\s*$")


def parse_tos_mm(text: str) -> Optional[Tuple[int, int]]:
    if not text or text.strip() == "unknown":
        return None
    m = re.search(r"(?P<maj>\d+)\.(?P<min>\d+)", text.strip())
    if not m:
        return None
    return int(m.group("maj")), int(m.group("min"))


def _collect_mm_from_grep_version_block(block: str) -> list[Tuple[int, int, str]]:
    """Return list of (maj, min, debug_source)."""
    out: list[Tuple[int, int, str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line:
            continue
        m = PROP_LINE_RE.match(line)
        key = ""
        chunks: list[str] = []
        if m:
            key = m.group("key")
            chunks.append(m.group("value"))
            chunks.append(line)
        else:
            chunks.append(line)
        for ch in chunks:
            mm = parse_tos_mm(ch)
            if mm:
                out.append((mm[0], mm[1], f"{key or '(raw)'}: {ch[:120]}"))
                break
    return out


def _pick_best_mm_from_grep_candidates(
    candidates: list[Tuple[int, int, str]],
) -> Optional[Tuple[int, int]]:
    if not candidates:
        return None

    def priority(item: Tuple[int, int, str]) -> int:
        maj, _mino, src = item
        lk = src.lower()
        if "tos" in lk or "tranos" in lk:
            return 3
        if maj >= 16:
            return 2
        return 1

    best_pri = -1
    best_mm: Optional[Tuple[int, int]] = None
    for c in candidates:
        pr = priority(c)
        mm = (c[0], c[1])
        if pr > best_pri:
            best_pri = pr
            best_mm = mm
        elif pr == best_pri and best_mm is not None:
            if mm > best_mm:
                best_mm = mm
        elif pr == best_pri and best_mm is None:
            best_mm = mm
    return best_mm


def tos_mm_from_getprop_grep_version(grep_version_text: str) -> Optional[Tuple[int, int]]:
    cands = _collect_mm_from_grep_version_block(grep_version_text)
    return _pick_best_mm_from_grep_candidates(cands)


def detect_tos_mm_combined(
    props: dict[str, str],
    grep_version_text: str,
    *,
    tos_prop_keys: Tuple[str, ...] = TOS_PROP_KEYS_DEFAULT,
) -> Tuple[Optional[Tuple[int, int]], str]:
    """
    Returns ( (major, minor) or None, source_label ).
    source_label examples: SPD_TOS_VERSION, ro.transsion.tos.version, getprop|grep version
    """
    env = os.environ.get("SPD_TOS_VERSION", "").strip()
    if env:
        mm = parse_tos_mm(env)
        if mm:
            return mm, "SPD_TOS_VERSION"
        print(f"WARN: SPD_TOS_VERSION={env!r} not parseable as major.minor", flush=True)

    for key in tos_prop_keys:
        val = props.get(key, "").strip()
        if val:
            mm = parse_tos_mm(val)
            if mm:
                return mm, key

    mm = tos_mm_from_getprop_grep_version(grep_version_text or "")
    if mm:
        return mm, "getprop|grep version"

    return None, ""
