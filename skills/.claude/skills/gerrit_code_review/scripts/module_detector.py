#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Infer affected hardware/software modules from Gerrit change metadata."""

from __future__ import annotations

import re
from typing import Iterable

# Display order for peripheral modules (通信 appended when matched).
PERIPHERAL_MODULE_ORDER = (
    "LCM",
    "TP",
    "Sensor",
    "Audio",
    "Video",
    "Key",
    "马达",
    "Charger",
    "USB",
)

COMM_MODULE = "通信"

# (module_name, compiled regex) — match file path, subject, or patch text (case-insensitive).
_MODULE_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "LCM",
        re.compile(
            r"(?:\blcm\b|lcd|display|panel|mipi[_-]?dsi|drm[_/]|framebuffer|\bfb\b|"
            r"mediatek[_/]drm|panel[_-]?driver|disp[_/]|ddp[_/]|dpc[_/])",
            re.IGNORECASE,
        ),
    ),
    (
        "TP",
        re.compile(
            r"(?:\btp\b|touch(?:screen)?|touchpanel|gsl\d|ft5\d|goodix|"
            r"himax|synaptics|focaltech|nt36\d|gt9\d)",
            re.IGNORECASE,
        ),
    ),
    (
        "Sensor",
        re.compile(
            r"(?:sensor|accelerometer|gyro(?:scope)?|als|ps[_/]|proximity|"
            r"magnetometer|\bhall\b|barometer|light[_-]?sensor|stk\d|"
            r"mpu\d|lsm\d|icm\d|akm\d)",
            re.IGNORECASE,
        ),
    ),
    (
        "Audio",
        re.compile(
            r"(?:\baudio\b|sound|codec|speaker|spk|microphone|\bmic\b|afe|"
            r"mtk[_-]?afe|aw87|tas\d|rt5\d|mt63\d|snd[_/]|asoc)",
            re.IGNORECASE,
        ),
    ),
    (
        "Video",
        re.compile(
            r"(?:\bvideo\b|camera|imgsensor|camsys|csi[_-]?|isp[_/]|v4l2)",
            re.IGNORECASE,
        ),
    ),
    (
        "Key",
        re.compile(
            r"(?:gpio[_-]?keys?|\bkeypad\b|power[_-]?key|volume[_-]?key|"
            r"home[_-]?key|key[_-]?driver|\bkeys\b)",
            re.IGNORECASE,
        ),
    ),
    (
        "马达",
        re.compile(
            r"(?:vibrator|vib[_/]|haptic|\bmotor\b|linear[_-]?motor|"
            r"aw86\d|drv26\d)",
            re.IGNORECASE,
        ),
    ),
    (
        "Charger",
        re.compile(
            r"(?:charger|charging|mtk[_-]?chg|battery|fuel[_-]?gauge|"
            r"gauge|bq\d|sc\d|pd[_-]?chg|qc\d|chg[_/])",
            re.IGNORECASE,
        ),
    ),
    (
        "USB",
        re.compile(
            r"(?:\busb\b|type[_-]?c|typec|xhci|gadget|usb[_-]?phy|"
            r"usb[_-]?switch|usb[_-]?role|drd)",
            re.IGNORECASE,
        ),
    ),
    (
        COMM_MODULE,
        re.compile(
            r"(?:telephony|telecom|\bphone\b|\bril\b|modem|radio|"
            r"\bsim\b|simcard|usim|data[_-]?network|cellular|connectivity|"
            r"volte|vonr|ims[_/]|\bnr\b|\blte\b|\bgsm\b|\bcdma\b|"
            r"network[_-]?stack|netd|telephony|carrier|apn|"
            r"subscription|mipc|ccci|md\d)",
            re.IGNORECASE,
        ),
    ),
]


def _collect_text(change: dict) -> str:
    parts: list[str] = [
        str(change.get("subject", "")),
        str(change.get("project", "")),
    ]
    for item in change.get("files", []) or []:
        if isinstance(item, dict):
            parts.append(str(item.get("path", "")))
    patch = change.get("patch_text", "")
    if isinstance(patch, str) and patch:
        # Limit patch scan size for performance on large diffs.
        parts.append(patch[:200_000])
    return "\n".join(parts)


def detect_modules_for_change(change: dict) -> list[str]:
    """Return ordered, deduplicated module names for a single change."""
    text = _collect_text(change)
    matched: set[str] = set()
    for name, pattern in _MODULE_RULES:
        if pattern.search(text):
            matched.add(name)

    ordered: list[str] = []
    for name in PERIPHERAL_MODULE_ORDER:
        if name in matched:
            ordered.append(name)
    if COMM_MODULE in matched:
        ordered.append(COMM_MODULE)
    return ordered


def detect_modules(changes: Iterable[dict]) -> list[str]:
    """Aggregate modules across one or more changes (topic-safe)."""
    merged: set[str] = set()
    for change in changes:
        merged.update(detect_modules_for_change(change))

    ordered: list[str] = []
    for name in PERIPHERAL_MODULE_ORDER:
        if name in merged:
            ordered.append(name)
    if COMM_MODULE in merged:
        ordered.append(COMM_MODULE)
    return ordered


def format_modules(modules: list[str]) -> str:
    """Format module list for display (e.g. LCM/TP/Sensor)."""
    return "/".join(modules) if modules else "未识别"
