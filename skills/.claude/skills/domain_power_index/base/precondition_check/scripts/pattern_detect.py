"""YAML 驱动的前置条件探测（无 PyYAML 依赖）。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any


def _strip_inline_comment(line: str) -> str:
    if "#" not in line:
        return line.rstrip()
    in_quote = False
    for i, ch in enumerate(line):
        if ch in "\"'":
            in_quote = not in_quote
        elif ch == "#" and not in_quote:
            return line[:i].rstrip()
    return line.rstrip()


def _parse_scalar(raw: str) -> Any:
    val = raw.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1]
    if val.startswith("[") and val.endswith("]"):
        inner = val[1:-1].strip()
        if not inner:
            return []
        return [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
    if re.fullmatch(r"-?\d+", val):
        return int(val)
    if re.fullmatch(r"-?\d+\.\d+", val):
        return float(val)
    if val.lower() in ("true", "false"):
        return val.lower() == "true"
    return val


def load_detection_patterns(ref_dir: Path) -> dict[str, Any]:
    path = ref_dir / "detection-patterns.yaml"
    if not path.is_file():
        return {}
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    root: dict[str, Any] = {}
    stack: list[tuple[int, Any, dict[str, Any] | None]] = [(-1, root, None)]

    for raw_line in lines:
        line = _strip_inline_comment(raw_line)
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        parent, current_item = stack[-1][1], stack[-1][2]
        content = line.strip()

        if content.startswith("- "):
            item: dict[str, Any] = {}
            rest = content[2:].strip()
            if ":" in rest:
                key, val = rest.split(":", 1)
                item[key.strip()] = _parse_scalar(val)
            if not isinstance(parent, list):
                raise ValueError(f"YAML list item without list parent at: {line}")
            parent.append(item)
            stack.append((indent, item, item))
            continue

        if ":" not in content:
            continue
        key, rest = content.split(":", 1)
        key = key.strip()
        rest = rest.strip()
        target = current_item if current_item is not None and indent > stack[-1][0] else parent
        if rest == "":
            child: Any = [] if key in ("patterns",) else {}
            if isinstance(target, dict):
                target[key] = child
            stack.append((indent, child, None))
            continue
        if isinstance(target, dict):
            target[key] = _parse_scalar(rest)

    return dict(root.get("items") or {})


def _regex_flags(flags: str) -> int:
    f = 0
    if "ignorecase" in (flags or "").lower():
        f |= re.IGNORECASE
    return f


def _lines_for_pattern(pat: dict[str, Any], main_content: str, kernel_content: str) -> list[str]:
    log_names = pat.get("logs") or ["main_log"]
    chunks: list[str] = []
    if any(x in log_names for x in ("main_log", "main", "sys_log", "sys")):
        chunks.append(main_content)
    if any(x in log_names for x in ("kernel_log", "kernel")):
        chunks.append(kernel_content)
    out: list[str] = []
    for chunk in chunks:
        out.extend(chunk.splitlines())
    return out


def _detect_timeline_last(
    item_cfg: dict[str, Any],
    main_content: str,
    kernel_content: str,
) -> dict[str, Any]:
    not_detected = "未检测到"
    patterns = item_cfg.get("patterns") or []
    controller_marker = str(item_cfg.get("controller_marker") or "com.android.server.display.AutomaticBrightnessController")
    on_value = str(item_cfg.get("on_value", "开启"))
    off_value = str(item_cfg.get("off_value", "关闭"))
    merged: list[tuple[str, str]] = []
    for line in main_content.splitlines():
        merged.append(("main", line))
    for line in kernel_content.splitlines():
        merged.append(("kernel", line))

    timeline: list[dict[str, Any]] = []
    evidence: list[str] = []

    for source, line in merged:
        for pat in patterns:
            log_names = pat.get("logs") or ["main_log"]
            if source == "main" and not any(x in log_names for x in ("main_log", "main", "sys_log", "sys")):
                continue
            if source == "kernel" and not any(x in log_names for x in ("kernel_log", "kernel")):
                continue
            keywords = [str(k) for k in (pat.get("keywords") or [])]
            if keywords and not all(kw in line for kw in keywords):
                continue
            strategy = pat.get("strategy", "last_group")
            if strategy == "event" and controller_marker not in line:
                continue
            regex = str(pat.get("regex") or "")
            if not regex:
                continue
            if not re.search(regex, line, _regex_flags(str(pat.get("flags") or ""))):
                continue
            pat_id = str(pat.get("id") or "")
            if strategy == "event":
                value = str(pat.get("event_value") or on_value)
                if pat_id.endswith("_disable"):
                    value = off_value
                elif pat_id.endswith("_enable"):
                    value = on_value
            else:
                value = on_value
            timeline.append({"value": value, "pattern_id": pat_id, "line": line.rstrip()})
            if len(evidence) < 20:
                evidence.append(line.rstrip())

    if not timeline:
        return {
            "value": not_detected,
            "matched_pattern": None,
            "presence_hits": [],
            "raw_evidence": evidence,
        }
    last = timeline[-1]
    return {
        "value": last["value"],
        "matched_pattern": last.get("pattern_id"),
        "presence_hits": [t for t in timeline if str(t.get("pattern_id", "")).startswith("kernel_")],
        "raw_evidence": evidence,
        "timeline": timeline,
    }


def detect_item(
    item_id: str,
    item_cfg: dict[str, Any],
    main_content: str,
    kernel_content: str = "",
) -> dict[str, Any]:
    if item_cfg.get("resolve") == "timeline_last":
        return _detect_timeline_last(item_cfg, main_content, kernel_content)

    not_detected = "未检测到"
    patterns = item_cfg.get("patterns") or []
    presence_hits: list[dict[str, Any]] = []
    groups: list[str] = []
    events: list[str] = []
    evidence: list[str] = []

    for pat in patterns:
        regex = str(pat.get("regex") or "")
        if not regex:
            continue
        compiled = re.compile(regex, _regex_flags(str(pat.get("flags") or "")))
        keywords = [str(k) for k in (pat.get("keywords") or [])]
        pat_id = str(pat.get("id") or "")

        for line in _lines_for_pattern(pat, main_content, kernel_content):
            if keywords and not all(kw in line for kw in keywords):
                continue
            m = compiled.search(line)
            if not m:
                continue
            if len(evidence) < 20:
                evidence.append(line.rstrip())
            strategy = pat.get("strategy", "last_group")
            if strategy == "presence":
                presence_hits.append(
                    {
                        "pattern_id": pat_id,
                        "line": line.rstrip(),
                    }
                )
            elif strategy == "event":
                token = str(pat.get("event_value", ""))
                if token:
                    events.append(token)
            elif strategy == "last_group":
                gi = int(pat.get("group", 1))
                if m.lastindex and gi <= m.lastindex:
                    groups.append(m.group(gi))

    value = not_detected
    matched_pattern = None

    if item_cfg.get("resolve") == "any_presence" and presence_hits:
        value = str(item_cfg.get("on_value", "开启"))
        matched_pattern = presence_hits[0].get("pattern_id")
    elif groups:
        value = groups[-1]
    elif events:
        value = events[-1]

    return {
        "value": value,
        "matched_pattern": matched_pattern,
        "presence_hits": presence_hits,
        "raw_evidence": evidence,
    }


def references_dir(script_file: str) -> Path:
    return Path(script_file).resolve().parent.parent / "references"
