from __future__ import annotations

from typing import Any

from .columns import (
    col_letter,
    find_target_columns,
    group_consecutive,
    should_skip_sheet,
)
from .decision import decide_row_update, merge_extra_codes
from .feishu import (
    cells_set,
    last_col_letter,
    parse_region_end_row,
    probe_current_region,
    read_sheet_grid,
    workbook_info,
)
from .parse import (
    INVALID_FORMAT_REMARK,
    code_cell_status,
    extract_feature_codes,
    normalize_tos_version,
    parse_document_title,
)
from .progress import EventCallback, emit
from .scmp import ScmpClient, find_tones_cli


WRITE_BATCH = 40


def sync_checklist(
    url: str,
    *,
    dry_run: bool = False,
    project: str | None = None,
    tos_version: str | None = None,
    include_hidden: bool = False,
    sheet_names: list[str] | None = None,
    tones_cli: str | None = None,
    on_event: EventCallback | None = None,
) -> dict[str, Any]:
    emit(on_event, "start", url=url, dry_run=dry_run, message="开始读取飞书表格")
    info = workbook_info(url)
    title = str(info.get("title") or "")
    emit(on_event, "workbook", title=title, message=f"已读取文档：{title}")
    parsed = parse_document_title(title)
    project_code = (project or parsed.project).upper()
    tos = normalize_tos_version(tos_version) if tos_version else parsed.tos_version
    emit(
        on_event,
        "parsed",
        project=project_code,
        tos_version=tos,
        message=f"解析标题：项目 {project_code}，tOS {tos}",
    )

    client = ScmpClient(find_tones_cli(tones_cli))
    emit(on_event, "scmp_login", message="正在登录 SCMP")
    client.login()
    emit(on_event, "scmp_resolve", message=f"正在匹配 SCMP 项目 {project_code} / {tos}")
    spec = client.resolve_spec(project_code, tos)
    emit(
        on_event,
        "scmp_resolved",
        spd_project=spec.spd_project,
        spec_bid=spec.spec_bid,
        tos_version=spec.tos_version,
        message=f"已定位规格：{spec.spd_project} ({spec.tos_version})",
    )
    emit(on_event, "scmp_loading", message="正在拉取各市场支持清单")
    support_map = client.market_support(spec.spec_bid)
    emit(
        on_event,
        "scmp_loaded",
        feature_cache_size=len(support_map),
        message=f"已加载 {len(support_map)} 条 SCMP 特性",
    )

    wanted = {name.strip() for name in (sheet_names or []) if name.strip()}
    planned = []
    for sheet in info.get("sheets") or []:
        name = str(sheet.get("sheet_name") or "")
        hidden = bool(sheet.get("is_hidden"))
        if wanted and name not in wanted:
            continue
        if should_skip_sheet(name, hidden=hidden, include_hidden=include_hidden):
            continue
        planned.append(sheet)

    emit(
        on_event,
        "plan",
        sheet_count=len(planned),
        sheet_names=[str(item.get("sheet_name") or "") for item in planned],
        message=f"将处理 {len(planned)} 张业务表",
    )

    sheet_reports: list[dict[str, Any]] = []
    for index, sheet in enumerate(planned, start=1):
        name = str(sheet.get("sheet_name") or "")
        emit(
            on_event,
            "sheet_start",
            index=index,
            total=len(planned),
            sheet_name=name,
            sheet_id=str(sheet.get("sheet_id") or ""),
            message=f"正在处理 {name} ({index}/{len(planned)})",
        )
        report = _sync_sheet(
            url=url,
            sheet=sheet,
            support_map=support_map,
            dry_run=dry_run,
            on_event=on_event,
        )
        sheet_reports.append(report)
        if report.get("error"):
            emit(
                on_event,
                "sheet_error",
                index=index,
                total=len(planned),
                sheet_name=name,
                error=report.get("error"),
                message=f"{name} 处理失败：{report.get('error')}",
            )
        else:
            emit(
                on_event,
                "sheet_done",
                index=index,
                total=len(planned),
                sheet_name=name,
                updated=report.get("updated"),
                supported=report.get("supported"),
                unsupported=report.get("unsupported"),
                partial=report.get("partial"),
                missing=report.get("missing"),
                invalid=report.get("invalid"),
                skipped_no_code=report.get("skipped_no_code"),
                written=report.get("written"),
                message=(
                    f"{name} 完成：{report.get('updated')} 条编码，"
                    f"支持 {report.get('supported')}，"
                    f"不支持 {report.get('unsupported')}，"
                    f"部分 {report.get('partial')}，"
                    f"不存在 {report.get('missing')}，"
                    f"格式异常 {report.get('invalid')}，"
                    f"跳过 {report.get('skipped_no_code')}"
                ),
            )

    failed = [item for item in sheet_reports if item.get("error")]
    summary = {
        "sheet_count": len(sheet_reports),
        "feature_count": sum(int(item.get("updated") or 0) for item in sheet_reports),
        "supported": sum(int(item.get("supported") or 0) for item in sheet_reports),
        "unsupported": sum(int(item.get("unsupported") or 0) for item in sheet_reports),
        "partial": sum(int(item.get("partial") or 0) for item in sheet_reports),
        "missing": sum(int(item.get("missing") or 0) for item in sheet_reports),
        "invalid": sum(int(item.get("invalid") or 0) for item in sheet_reports),
        "skipped_no_code": sum(int(item.get("skipped_no_code") or 0) for item in sheet_reports),
        "failed_sheets": [item.get("sheet_name") for item in failed],
    }
    result = {
        "ok": not failed,
        "data": {
            "title": title,
            "project": project_code,
            "tos_version": tos,
            "title_tos": parsed.raw_tos,
            "spd_project": spec.spd_project,
            "project_bid": spec.project_bid,
            "spec_bid": spec.spec_bid,
            "market_list": spec.market_list,
            "dry_run": dry_run,
            "feature_cache_size": len(support_map),
            "summary": summary,
            "sheets": sheet_reports,
        },
    }
    emit(
        on_event,
        "done",
        ok=result["ok"],
        summary=summary,
        message="全部处理完成" if result["ok"] else "处理完成，部分 sheet 失败",
    )
    return result


def _sync_sheet(
    *,
    url: str,
    sheet: dict[str, Any],
    support_map: dict[str, dict[str, str]],
    dry_run: bool,
    on_event: EventCallback | None = None,
) -> dict[str, Any]:
    sheet_id = str(sheet.get("sheet_id") or "")
    name = str(sheet.get("sheet_name") or "")
    report: dict[str, Any] = {
        "sheet_id": sheet_id,
        "sheet_name": name,
        "items": [],
        "updated": 0,
        "missing": 0,
        "partial": 0,
        "supported": 0,
        "unsupported": 0,
        "skipped_no_code": 0,
        "invalid": 0,
    }
    try:
        last_col = last_col_letter(int(sheet.get("column_count") or 1))
        region = probe_current_region(url, sheet_id, last_col)
        end_row = parse_region_end_row(region, int(sheet.get("row_count") or 50))
        grid = read_sheet_grid(url, sheet_id, last_col, end_row)
        header_rows = [cells for row_num, cells in grid if row_num <= 5]
        columns = find_target_columns(header_rows)
        report["columns"] = {
            "code": col_letter(columns.code_index + 1),
            "support": col_letter(columns.support_index + 1),
            "remark": col_letter(columns.remark_index + 1),
        }
        report["current_region"] = region

        support_writes: dict[int, str] = {}
        remark_writes: dict[int, str] = {}
        for row_num, cells in grid:
            code_cell = _cell(cells, columns.code_index)
            status = code_cell_status(code_cell)
            if status != "ok":
                _handle_unparsed_row(
                    report=report,
                    remark_writes=remark_writes,
                    on_event=on_event,
                    sheet_name=name,
                    row_num=row_num,
                    cells=cells,
                    code_cell=code_cell,
                    status=status,
                )
                continue
            primary, extras = extract_feature_codes(code_cell)
            if primary is None:
                continue
            markets = _lookup_markets(support_map, primary)
            decision = decide_row_update(markets)
            remark = merge_extra_codes(decision.remark, extras)
            if decision.write_support and decision.support is not None:
                support_writes[row_num] = decision.support
            remark_writes[row_num] = remark
            item = {
                "row": row_num,
                "code": primary,
                "extra_codes": extras,
                "support": decision.support,
                "remark": remark,
                "markets": markets,
            }
            report["items"].append(item)
            if decision.remark == "特性编码不存在":
                report["missing"] += 1
                status_text = "特性编码不存在"
            elif decision.remark.startswith("部分市场支持"):
                report["partial"] += 1
                status_text = decision.remark
            elif decision.support == "支持":
                report["supported"] += 1
                status_text = "支持"
            elif decision.support == "不支持":
                report["unsupported"] += 1
                status_text = "不支持"
            else:
                status_text = decision.remark or "已处理"
            emit(
                on_event,
                "row",
                sheet_name=name,
                row=row_num,
                code=primary,
                support=decision.support,
                remark=remark,
                message=f"{name} 第{row_num}行 {primary} → {status_text}",
            )

        report["updated"] = len(report["items"])
        if not dry_run:
            emit(on_event, "sheet_write", sheet_name=name, message=f"正在回写 {name}")
            _write_column(url, sheet_id, col_letter(columns.support_index + 1), support_writes)
            _write_column(url, sheet_id, col_letter(columns.remark_index + 1), remark_writes)
            report["written"] = True
        else:
            report["written"] = False
        return report
    except Exception as exc:  # noqa: BLE001
        report["error"] = str(exc)
        return report


def _cell(cells: list[str], index: int) -> str:
    if index < 0 or index >= len(cells):
        return ""
    return cells[index]


def _is_data_row(cells: list[str], row_num: int) -> bool:
    if row_num <= 1:
        return False
    nonempty = [item for item in cells if str(item or "").strip()]
    return len(nonempty) >= 2


def _handle_unparsed_row(
    *,
    report: dict[str, Any],
    remark_writes: dict[int, str],
    on_event: EventCallback | None,
    sheet_name: str,
    row_num: int,
    cells: list[str],
    code_cell: str,
    status: str,
) -> None:
    stripped = (code_cell or "").strip()
    if stripped == "特性编码" or row_num == 1:
        return
    if status == "invalid_format":
        compact = "".join(stripped.split())
        remark_writes[row_num] = INVALID_FORMAT_REMARK
        report["invalid"] += 1
        report["items"].append(
            {
                "row": row_num,
                "code": compact or stripped,
                "extra_codes": [],
                "support": None,
                "remark": INVALID_FORMAT_REMARK,
                "markets": None,
            }
        )
        emit(
            on_event,
            "row",
            sheet_name=sheet_name,
            row=row_num,
            code=compact or stripped,
            support=None,
            remark=INVALID_FORMAT_REMARK,
            reason="invalid_format",
            message=f"{sheet_name} 第{row_num}行 {compact or stripped} → {INVALID_FORMAT_REMARK}",
        )
        return
    if not _is_data_row(cells, row_num):
        return
    report["skipped_no_code"] += 1
    reason_text = {
        "empty": "无特性编码",
        "placeholder": "特性编码为占位符",
        "other": "特性编码无法识别",
    }.get(status, "跳过")
    emit(
        on_event,
        "row_skip",
        sheet_name=sheet_name,
        row=row_num,
        reason=status,
        code_raw=stripped,
        message=f"{sheet_name} 第{row_num}行 {reason_text}，跳过",
    )


def _lookup_markets(
    support_map: dict[str, dict[str, str]],
    code: str,
) -> dict[str, str] | None:
    if code in support_map:
        return support_map[code]
    upper = code.upper()
    if upper in support_map:
        return support_map[upper]
    for key, value in support_map.items():
        if key.upper() == upper:
            return value
    return None


def _write_column(
    url: str,
    sheet_id: str,
    column: str,
    values: dict[int, str],
) -> None:
    if not values:
        return
    for start, end in group_consecutive(list(values)):
        cursor = start
        while cursor <= end:
            batch_end = min(cursor + WRITE_BATCH - 1, end)
            cells = [[{"value": values[row]}] for row in range(cursor, batch_end + 1)]
            cells_set(url, sheet_id, f"{column}{cursor}:{column}{batch_end}", cells)
            cursor = batch_end + 1
