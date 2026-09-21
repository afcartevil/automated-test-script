#!/usr/bin/env python3
"""Shared TOS version detection for SPD memory/CPU feature checks.

Resolution order:
1) env SPD_TOS_VERSION
2) dedicated TOS props in getprop map
3) parse major.minor from ``getprop | grep version`` output
"""

from __future__ import annotations

import os
import re
from typing import Dict, Optional, Tuple

TosMm = Tuple[int, int]

TOS_PROP_KEYS_DEFAULT = (
    "ro.transsion.tos.version",
    "ro.vendor.transsion.tos.version",
    "ro.build.tranos.version",
    "ro.tranos.version",
    "ro.tr_os.version",
)

_MM_RE = re.compile(r"(?P<maj>\d{1,2})\.(?P<min>\d{1,2})")
# Prefer TOS-looking versions in the 1x.x range first when scanning free text.
_TOS_HINT_RE = re.compile(
    r"(?:tos|tranos|tr_os|tran\.os)[^\d]{0,12}(?P<maj>1[0-9])\.(?P<min>\d{1,2})",
    re.IGNORECASE,
)


def parse_mm_from_text(text: str) -> Optional[TosMm]:
    raw = (text or "").strip()
    if not raw:
        return None
    hint = _TOS_HINT_RE.search(raw)
    if hint:
        return int(hint.group("maj")), int(hint.group("min"))
    # Prefer 16.x / 17.x style first
    candidates: list[TosMm] = []
    for m in _MM_RE.finditer(raw):
        maj, minor = int(m.group("maj")), int(m.group("min"))
        if 10 <= maj <= 30:
            candidates.append((maj, minor))
    if candidates:
        # Prefer higher major then minor (e.g. 16.3 over 15.0)
        return max(candidates)
    m = _MM_RE.search(raw)
    if not m:
        return None
    return int(m.group("maj")), int(m.group("min"))


def detect_tos_mm_from_env() -> Optional[TosMm]:
    env = (os.environ.get("SPD_TOS_VERSION") or "").strip()
    if not env:
        return None
    return parse_mm_from_text(env)


def detect_tos_mm_from_props(
    props: Dict[str, str],
    keys: Tuple[str, ...] = TOS_PROP_KEYS_DEFAULT,
) -> Optional[TosMm]:
    for key in keys:
        val = (props.get(key) or "").strip()
        if not val:
            continue
        mm = parse_mm_from_text(val)
        if mm is not None:
            return mm
    return None


def detect_tos_mm_from_grep(grep_out: str) -> Optional[TosMm]:
    return parse_mm_from_text(grep_out or "")


def detect_tos_mm_combined(
    props: Dict[str, str],
    grep_out: str = "",
) -> Tuple[Optional[TosMm], str]:
    """Return ((major, minor) or None, source_label)."""
    env_mm = detect_tos_mm_from_env()
    if env_mm is not None:
        return env_mm, "SPD_TOS_VERSION"

    prop_mm = detect_tos_mm_from_props(props)
    if prop_mm is not None:
        return prop_mm, "tos_prop"

    grep_mm = detect_tos_mm_from_grep(grep_out)
    if grep_mm is not None:
        return grep_mm, "getprop_grep_version"

    return None, ""
