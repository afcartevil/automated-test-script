"""flow/game 共用 YAML 子集解析（无 PyYAML 依赖）。"""

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


def load_yaml_config(path: Path) -> dict[str, Any]:
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
            child: Any = (
                []
                if key
                in (
                    "patterns",
                    "rules",
                    "conditions",
                    "checks",
                    "hardware_rows",
                    "games",
                )
                else {}
            )
            if isinstance(target, dict):
                target[key] = child
            stack.append((indent, child, None))
            continue
        if isinstance(target, dict):
            target[key] = _parse_scalar(rest)

    return root
