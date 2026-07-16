"""Unified diff 工具：按文件路径提取 hunk。"""
from __future__ import annotations


def _normalize_path(path: str) -> str:
    return (path or "").strip().lstrip("./").replace("\\", "/")


def _paths_match(diff_path: str, target: str) -> bool:
    diff_path = _normalize_path(diff_path)
    target = _normalize_path(target)
    if not diff_path or not target:
        return False
    if diff_path == target:
        return True
    return diff_path.endswith("/" + target) or target.endswith("/" + diff_path)


def extract_file_diff(diff_text: str, file_path: str) -> str:
    """从 unified diff 文本中提取单个文件的 diff 片段。"""
    if not diff_text or not file_path:
        return ""
    target = _normalize_path(file_path)
    lines = diff_text.splitlines()
    chunks: list[list[str]] = []
    current: list[str] = []
    matched = False

    for line in lines:
        if line.startswith("diff --git "):
            if matched and current:
                chunks.append(current)
            current = [line]
            matched = False
            parts = line.split()
            if len(parts) >= 3:
                a_path = parts[2][2:] if parts[2].startswith("a/") else parts[2]
                b_path = parts[3][2:] if len(parts) >= 4 and parts[3].startswith("b/") else a_path
                matched = _paths_match(a_path, target) or _paths_match(b_path, target)
            continue
        if current:
            current.append(line)

    if matched and current:
        chunks.append(current)

    if not chunks:
        return ""
    return "\n".join("\n".join(c) for c in chunks).strip()
