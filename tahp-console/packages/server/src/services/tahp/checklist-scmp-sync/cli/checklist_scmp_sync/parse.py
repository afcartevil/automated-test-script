from __future__ import annotations

import re
from dataclasses import dataclass


PROJECT_RE = re.compile(r"(?<![A-Za-z0-9])(X\d{3,})", re.IGNORECASE)
TOS_RE = re.compile(r"tOS\s*(\d+(?:\.\d+){0,2})", re.IGNORECASE)
# 去空白后只需 SF/SR- 后跟数字，不卡死 6 位。单元格内换行会把编码拆开。
FEATURE_RE = re.compile(r"(?:SF|SR)-\d[\d-]*", re.IGNORECASE)
LOOSE_FEATURE_RE = re.compile(r"(?:SF|SR)\s*-\s*\d[\d\s-]*", re.IGNORECASE)
EMPTY_TOKENS = {"", "/", "\\", "-", "—", "NA", "N/A"}
PLACEHOLDER_TOKENS = {"待补充", "TBD", "TODO"}
INVALID_FORMAT_REMARK = "特性编码格式不正确"
CODE_FRAGMENT_RE = re.compile(r"(?:SF|SR)\s*-", re.IGNORECASE)


@dataclass(frozen=True)
class ParsedTitle:
    project: str
    tos_version: str
    raw_tos: str


def normalize_tos_version(raw: str) -> str:
    text = (raw or "").strip().lstrip("vV")
    if not text:
        raise ValueError("tOS 版本为空")
    parts = text.split(".")
    if len(parts) > 3:
        raise ValueError(f"无法识别的 tOS 版本: {raw}")
    normalized = []
    for part in parts:
        if not part.isdigit():
            raise ValueError(f"无法识别的 tOS 版本: {raw}")
        normalized.append(str(int(part)))
    while len(normalized) < 3:
        normalized.append("0")
    return ".".join(normalized)


def parse_document_title(title: str) -> ParsedTitle:
    text = (title or "").strip()
    if not text:
        raise ValueError("文档标题为空，无法解析项目和 tOS 版本")
    project_match = PROJECT_RE.search(text)
    tos_match = TOS_RE.search(text)
    if project_match is None:
        raise ValueError(f"无法从标题解析项目编码: {title}")
    if tos_match is None:
        raise ValueError(f"无法从标题解析 tOS 版本: {title}")
    raw_tos = tos_match.group(1)
    return ParsedTitle(
        project=project_match.group(1).upper(),
        tos_version=normalize_tos_version(raw_tos),
        raw_tos=raw_tos,
    )


def extract_feature_codes(text: str) -> tuple[str | None, list[str]]:
    stripped = (text or "").strip()
    if stripped.upper() in EMPTY_TOKENS:
        return None, []
    codes: list[str] = []
    seen: set[str] = set()
    for match in LOOSE_FEATURE_RE.finditer(stripped):
        code = re.sub(r"\s+", "", match.group(0)).upper().rstrip("-")
        if FEATURE_RE.fullmatch(code) is None or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    if not codes:
        return None, []
    return codes[0], codes[1:]


def code_cell_status(text: str) -> str:
    primary, _extras = extract_feature_codes(text)
    if primary:
        return "ok"
    stripped = (text or "").strip()
    if not stripped or stripped.upper() in {token.upper() for token in EMPTY_TOKENS}:
        return "empty"
    if stripped in PLACEHOLDER_TOKENS or stripped.upper() in PLACEHOLDER_TOKENS:
        return "placeholder"
    if CODE_FRAGMENT_RE.search(stripped):
        return "invalid_format"
    return "other"
