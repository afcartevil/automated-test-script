from __future__ import annotations

import re
from dataclasses import dataclass


CHANGELOG_NAMES = {"变更记录"}


@dataclass(frozen=True)
class TargetColumns:
    code_index: int
    support_index: int
    remark_index: int


def col_letter(index_1based: int) -> str:
    if index_1based <= 0:
        raise ValueError("column index must be >= 1")
    result = []
    n = index_1based
    while n:
        n, rem = divmod(n - 1, 26)
        result.append(chr(65 + rem))
    return "".join(reversed(result))


def _norm_header(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).strip()


def find_target_columns(header_rows: list[list[object]]) -> TargetColumns:
    code_index = None
    support_index = None
    remark_candidates: list[int] = []
    for row in header_rows:
        for index, cell in enumerate(row):
            text = _norm_header(cell)
            if text == "特性编码":
                code_index = index
            elif text == "此特性是否支持":
                support_index = index
            elif text == "备注":
                remark_candidates.append(index)
    if code_index is None:
        raise ValueError("未找到「特性编码」列")
    if support_index is None:
        raise ValueError("未找到「此特性是否支持」列")
    remark_index = None
    after_support = [idx for idx in remark_candidates if idx > support_index]
    if after_support:
        remark_index = min(after_support)
    elif remark_candidates:
        remark_index = remark_candidates[-1]
    if remark_index is None:
        raise ValueError("未找到「备注」列")
    return TargetColumns(
        code_index=code_index,
        support_index=support_index,
        remark_index=remark_index,
    )


def should_skip_sheet(name: str, hidden: bool, include_hidden: bool = False) -> bool:
    title = (name or "").strip()
    if title in CHANGELOG_NAMES:
        return True
    if include_hidden:
        return False
    if hidden:
        return True
    return "废弃" in title


def group_consecutive(values: list[int]) -> list[tuple[int, int]]:
    if not values:
        return []
    ordered = sorted(values)
    groups: list[tuple[int, int]] = []
    start = prev = ordered[0]
    for value in ordered[1:]:
        if value == prev + 1:
            prev = value
            continue
        groups.append((start, prev))
        start = prev = value
    groups.append((start, prev))
    return groups
