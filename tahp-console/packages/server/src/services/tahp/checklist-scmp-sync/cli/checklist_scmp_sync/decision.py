from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RowUpdate:
    support: str | None
    remark: str
    write_support: bool


def decide_row_update(markets: dict[str, str] | None) -> RowUpdate:
    if not markets:
        return RowUpdate(support=None, remark="特性编码不存在", write_support=False)

    supported = sorted(name for name, value in markets.items() if str(value) == "1")
    unsupported = [name for name, value in markets.items() if str(value) != "1"]
    if supported and not unsupported:
        return RowUpdate(support="支持", remark="", write_support=True)
    if unsupported and not supported:
        return RowUpdate(support="不支持", remark="", write_support=True)
    return RowUpdate(
        support="支持",
        remark="部分市场支持：" + ", ".join(supported),
        write_support=True,
    )


def merge_extra_codes(remark: str, extras: list[str]) -> str:
    if not extras:
        return remark
    note = "另有编码未处理：" + ", ".join(extras)
    return f"{remark}；{note}" if remark else note
