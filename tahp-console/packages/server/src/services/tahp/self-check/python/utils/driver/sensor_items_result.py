"""case22 sensor 逐项测试结果读写与复用（独立模块，避免 ui_tranfacmode 热加载缓存问题）。"""

import json
from pathlib import Path
from typing import Any, Callable

from utils.driver.tranfacmode_group_result import FAIL_TEXTS, PASS_TEXTS

SENSOR_ITEMS_JSON = "tranfacmode_sensor_items.json"
SOURCE_SENSOR_ITEMS_CASE_INDEX = 22


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _item_name_matches(name: str, keywords: tuple[str, ...]) -> bool:
    text = (name or "").strip()
    if not text:
        return False
    lower = text.lower()
    collapsed = lower.replace(" ", "")
    for keyword in keywords:
        kw = (keyword or "").strip().lower()
        if not kw:
            continue
        if kw in lower or kw.replace(" ", "") in collapsed:
            return True
    return False


def _item_name_excluded(name: str, exclude_keywords: tuple[str, ...]) -> bool:
    if not exclude_keywords:
        return False
    return _item_name_matches(name, exclude_keywords)


def load_sensor_items_result(result_dir: str | Path | None) -> dict[str, Any] | None:
    if not result_dir:
        return None
    path = Path(result_dir).resolve() / SENSOR_ITEMS_JSON
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_sensor_items_result(
    result_dir: str | Path | None,
    items: list[dict[str, str]],
    *,
    cali_items: list[dict[str, str]] | None = None,
) -> None:
    if not result_dir:
        return
    payload_items = [
        {"name": item.get("name", ""), "state": item.get("state", "")}
        for item in items
        if isinstance(item, dict) and item.get("name")
    ]
    payload_cali_items = [
        {"name": item.get("name", ""), "state": item.get("state", "")}
        for item in (cali_items or [])
        if isinstance(item, dict) and item.get("name")
    ]
    states = {(item.get("state") or "").strip() for item in payload_items}
    data = {
        "group": "sensor",
        "items": payload_items,
        "cali_items": payload_cali_items,
        "all_pass": bool(payload_items) and states.issubset(PASS_TEXTS),
        "has_fail": any(state in FAIL_TEXTS for state in states),
    }
    try:
        _save_json(Path(result_dir) / SENSOR_ITEMS_JSON, data)
    except OSError:
        pass


def evaluate_reused_sensor_item(
    data: dict[str, Any],
    keywords: tuple[str, ...],
    item_label: str,
    *,
    source_case_index: int = SOURCE_SENSOR_ITEMS_CASE_INDEX,
    item_source: str = "items",
    exclude_keywords: tuple[str, ...] = (),
) -> tuple[str, str]:
    kind_label = "校准" if item_source == "cali_items" else "测试"
    result_source_label = f"case{source_case_index} sensor工模{kind_label}"
    items = data.get(item_source) or []
    matched = [
        item
        for item in items
        if isinstance(item, dict)
        and _item_name_matches(item.get("name", ""), keywords)
        and not _item_name_excluded(item.get("name", ""), exclude_keywords)
    ]
    if not matched:
        all_names = "、".join(item.get("name", "") for item in items if isinstance(item, dict))
        suffix = f"（已有: {all_names}）" if all_names else ""
        return "fail", f"未在{result_source_label}结果中找到{item_label}子项{suffix}"

    failed = [
        item
        for item in matched
        if (item.get("state") or "").strip() in FAIL_TEXTS
    ]
    if failed:
        detail = "; ".join(
            f"{item.get('name', '?')}({item.get('state', '')})" for item in failed
        )
        return "fail", f"复用{result_source_label}结果: {detail}"

    pending = [
        item
        for item in matched
        if (item.get("state") or "").strip() not in PASS_TEXTS
    ]
    if pending:
        detail = "; ".join(
            f"{item.get('name', '?')}({item.get('state', '')})" for item in pending
        )
        return "fail", f"复用{result_source_label}结果: {item_label}未完成({detail})"

    names = "、".join(item.get("name", "") for item in matched if item.get("name"))
    return "pass", f"复用{result_source_label}结果: {names} 通过"


def run_reuse_sensor_items_item(
    context: dict[str, Any],
    keywords: tuple[str, ...],
    *,
    item_label: str,
    step_update: Callable[[str], None] | None = None,
    source_case_index: int = SOURCE_SENSOR_ITEMS_CASE_INDEX,
    item_source: str = "items",
    exclude_keywords: tuple[str, ...] = (),
) -> dict[str, str]:
    sub_steps = ""
    kind_label = "校准" if item_source == "cali_items" else "测试"

    def update(steps: str) -> None:
        if callable(step_update):
            step_update(steps)

    sub_steps += (
        f"\n复用 case{source_case_index} sensor工模{kind_label}结果({item_label})"
    )
    update(sub_steps)

    data = load_sensor_items_result(context.get("result_dir"))
    if not data:
        sub_steps += f"-失败(未找到 case{source_case_index} 结果文件)"
        update(sub_steps)
        return {
            "status": "fail",
            "message": (
                f"未找到 case{source_case_index} 工模结果文件，"
                f"请在同一次测试中先勾选并执行 case{source_case_index}（加速度功能正常），"
                f"再执行本用例"
            ),
        }

    status, message = evaluate_reused_sensor_item(
        data,
        keywords,
        item_label,
        source_case_index=source_case_index,
        item_source=item_source,
        exclude_keywords=exclude_keywords,
    )
    sub_steps += "-成功" if status == "pass" else "-失败"
    update(sub_steps)
    return {"status": status, "message": message}


def _is_sensor_item_not_found(message: str) -> bool:
    text = (message or "").strip()
    return "未在" in text and "结果中找到" in text and "子项" in text


def run_reuse_sensor_item_with_support_check(
    context: dict[str, Any],
    keywords: tuple[str, ...],
    *,
    item_label: str,
    feature_name: str,
    step_update: Callable[[str], None] | None = None,
    source_case_index: int = SOURCE_SENSOR_ITEMS_CASE_INDEX,
    item_source: str = "items",
    exclude_keywords: tuple[str, ...] = (),
) -> dict[str, str]:
    """复用 sensor 工模结果；未找到子项时人工确认是否支持该功能。"""
    sub_steps = ""
    operator_notify = context.get("operator_notify")
    manual_confirm = context.get("manual_confirm")

    def update(steps: str) -> None:
        nonlocal sub_steps
        sub_steps = steps
        if callable(step_update):
            step_update(sub_steps)

    result = run_reuse_sensor_items_item(
        context,
        keywords,
        item_label=item_label,
        step_update=update,
        source_case_index=source_case_index,
        item_source=item_source,
        exclude_keywords=exclude_keywords,
    )
    if result["status"] == "pass":
        return result

    message = result.get("message") or ""
    if not _is_sensor_item_not_found(message):
        return result

    notice = (
        f"Sensor 工模结果中未找到{item_label}，请确认本机是否支持{feature_name}。"
    )
    sub_steps += f"\n需人工确认：{notice}"
    update(sub_steps)
    if callable(operator_notify):
        operator_notify(notice)

    if not callable(manual_confirm):
        return {"status": "pending", "message": f"需确认设备是否支持{feature_name}"}

    status = manual_confirm(
        f"Sensor 工模未找到{item_label}，请确认本机是否支持{feature_name}。",
        pass_label="支持",
        fail_label="不支持",
    )
    if status != "pass":
        return {
            "status": "skip",
            "message": f"设备不支持{feature_name}，已跳过（{item_label}未找到）",
        }
    return {
        "status": "fail",
        "message": f"{message}（人工确认支持{feature_name}）",
    }
