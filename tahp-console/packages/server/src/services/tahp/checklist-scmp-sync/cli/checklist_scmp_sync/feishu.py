from __future__ import annotations

import json
from typing import Any

from .columns import col_letter
from .proc import parse_annotated_csv, resolve_executable, run_json_command


def _lark() -> str:
    return resolve_executable("lark-cli")


def workbook_info(url: str) -> dict[str, Any]:
    payload = run_json_command(
        [_lark(), "sheets", "+workbook-info", "--url", url, "--format", "json"]
    )
    if payload.get("ok") is False:
        raise RuntimeError(payload.get("error") or payload)
    return payload.get("data") or {}


def csv_get(url: str, sheet_id: str, range_a1: str) -> dict[str, Any]:
    payload = run_json_command(
        [
            _lark(),
            "sheets",
            "+csv-get",
            "--url",
            url,
            "--sheet-id",
            sheet_id,
            "--range",
            range_a1,
            "--format",
            "json",
        ]
    )
    if payload.get("ok") is False:
        raise RuntimeError(payload.get("error") or payload)
    return payload.get("data") or {}


def cells_set(
    url: str,
    sheet_id: str,
    range_a1: str,
    cells: list[list[dict[str, str]]],
) -> dict[str, Any]:
    payload = run_json_command(
        [
            _lark(),
            "sheets",
            "+cells-set",
            "--url",
            url,
            "--sheet-id",
            sheet_id,
            "--range",
            range_a1,
            "--cells",
            "-",
        ],
        input_text=json.dumps(cells, ensure_ascii=False),
    )
    if payload.get("ok") is False:
        raise RuntimeError(payload.get("error") or payload)
    return payload.get("data") or {}


def read_sheet_grid(url: str, sheet_id: str, last_col: str, last_row: int) -> list[tuple[int, list[str]]]:
    data = csv_get(url, sheet_id, f"A1:{last_col}{last_row}")
    return parse_annotated_csv(data.get("annotated_csv") or "")


def probe_current_region(url: str, sheet_id: str, last_col: str) -> str:
    data = csv_get(url, sheet_id, f"A1:{last_col}5")
    return str(data.get("current_region") or "")


def parse_region_end_row(current_region: str, fallback: int) -> int:
    if not current_region or ":" not in current_region:
        return fallback
    end = current_region.split(":")[-1]
    digits = "".join(ch for ch in end if ch.isdigit())
    return int(digits) if digits else fallback


def last_col_letter(column_count: int) -> str:
    return col_letter(max(int(column_count or 1), 1))
