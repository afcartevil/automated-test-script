"""case.json 与用例目录的公共解析（test_type / module / category 复合键）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CASE_ROOT = Path(__file__).resolve().parent  # self-check/python/
CASES_DIR = CASE_ROOT / "cases"
CASE_JSON_PATH = CASE_ROOT / "case.json"

# xlsx sheet 名 -> (test_type, module)
SHEET_TO_MODULE: dict[str, tuple[str, str]] = {
    "str4_tdd": ("str4", "tdd"),
    "str4_driver_component": ("str4", "driver_component"),
    "str4_driver_hardware": ("str4", "driver_hardware"),
    "week_tdd": ("week", "tdd"),
    "week_driver": ("week", "driver"),
    "monkey_monkey": ("monkey", "monkey"),
    "smoke_usd": ("smoke", "usd"),
    "gms_cts": ("gms", "cts"),
    "gms_gts": ("gms", "gts"),
    "gms_vts": ("gms", "vts"),
}

MODULE_TO_SHEET: dict[tuple[str, str], str] = {
    value: key for key, value in SHEET_TO_MODULE.items()
}

TEST_TYPE_LABELS = {
    "str4": "str4转测摸底测试",
    "week": "周版本测试",
    "monkey": "monkey测试",
    "smoke": "冒烟测试",
    "gms": "GMS测试",
}

MODULE_LABELS = {
    "driver": "驱动",
    "driver_component": "驱动-器件",
    "driver_hardware": "驱动-硬测",
    "tdd": "通信框架",
    "monkey": "monkey测试",
    "usd": "USD冒烟测试",
    "cts": "CTS",
    "gts": "GTS",
    "vts": "VTS",
}

TEST_TYPE_ORDER = ("str4", "week", "monkey", "smoke", "gms")
MODULE_ORDER = ("driver_component", "driver_hardware", "driver", "monkey", "usd", "cts", "gts", "vts", "tdd")


def make_category_key(test_type: str, module: str) -> str:
    return f"{test_type}/{module}"


CATEGORY_ORDER = tuple(
    make_category_key(test_type, module)
    for test_type in TEST_TYPE_ORDER
    for module in MODULE_ORDER
)

DEFAULT_CATEGORY = make_category_key("str4", "tdd")


def parse_category_key(category: str) -> tuple[str, str]:
    text = (category or "").strip()
    if "/" not in text:
        raise ValueError(f"无效的用例分类键: {category!r}")
    test_type, module = text.split("/", 1)
    return test_type.strip(), module.strip()


def resolve_result_category(
    category: str = "",
    *,
    context: dict[str, Any] | None = None,
    test_type: str = "",
    module: str = "",
    default: str = DEFAULT_CATEGORY,
) -> str:
    """解析 result.json / 复用查询使用的复合键（如 str4/tdd）。"""
    resolved_category = (category or "").strip()
    resolved_test_type = (test_type or "").strip()
    resolved_module = (module or "").strip()
    if context:
        if not resolved_category:
            resolved_category = (context.get("category") or "").strip()
        if not resolved_test_type:
            resolved_test_type = (context.get("test_type") or "").strip()
        if not resolved_module:
            resolved_module = (context.get("module") or "").strip()
    if resolved_test_type and resolved_module:
        return make_category_key(resolved_test_type, resolved_module)
    if resolved_category:
        try:
            tt, md = parse_category_key(resolved_category)
            return make_category_key(tt, md)
        except ValueError:
            return resolved_category
    return default


def sort_category_keys(categories) -> list[str]:
    order = {name: index for index, name in enumerate(CATEGORY_ORDER)}
    return sorted(categories, key=lambda name: order.get(name, 999))


def category_to_sheet_name(category: str) -> str:
    """result.json 复合键 -> Excel sheet 名（与用例 xlsx 的 str4_tdd 等对齐）。"""
    try:
        test_type, module = parse_category_key(category)
        return MODULE_TO_SHEET.get((test_type, module), category.replace("/", "_"))
    except ValueError:
        return (category or "未分类").replace("/", "_")


def load_case_json() -> dict[str, Any]:
    try:
        with open(CASE_JSON_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def get_module_case_names(
    case_data: dict[str, Any] | None,
    test_type: str,
    module: str,
) -> list[str]:
    data = case_data if case_data is not None else load_case_json()
    type_node = data.get(test_type, {})
    if not isinstance(type_node, dict):
        return []
    names = type_node.get(module, [])
    if not isinstance(names, list):
        return []
    return [str(name) for name in names]


def get_case_name(
    case_data: dict[str, Any] | None,
    test_type: str,
    module: str,
    case_index: int,
) -> str:
    names = get_module_case_names(case_data, test_type, module)
    if 1 <= case_index <= len(names):
        return (names[case_index - 1] or "").strip()
    return ""


def get_case_index_by_name(
    case_data: dict[str, Any] | None,
    test_type: str,
    module: str,
    case_name: str,
) -> int:
    target = (case_name or "").strip()
    if not target:
        return 0
    for index, name in enumerate(get_module_case_names(case_data, test_type, module), start=1):
        if (name or "").strip() == target:
            return index
    return 0


def module_dir(test_type: str, module: str) -> Path:
    return CASES_DIR / test_type / module


def load_case_manual_info(test_type: str, module: str, case_index: int) -> dict[str, Any]:
    """按 case_index 读取模块 case_info.json 中对应条目。"""
    info_path = module_dir(test_type, module) / "case_info.json"
    if not info_path.is_file():
        return {}
    try:
        with open(info_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, list):
            return {}
        try:
            target_index = int(case_index)
        except (TypeError, ValueError):
            return {}
        if target_index <= 0 or target_index > len(data):
            return {}
        row = data[target_index - 1]
        return dict(row) if isinstance(row, dict) else {}
    except Exception:
        return {}


def resolve_case_item(
    item: dict[str, Any],
    case_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """将选中项或进度项规范为 category / test_type / module / case_index / case_name。"""
    data = case_data if case_data is not None else load_case_json()
    test_type = (item.get("test_type") or "").strip()
    module = (item.get("module") or "").strip()
    category = (item.get("category") or "").strip()

    if test_type and module:
        category = category or make_category_key(test_type, module)
    elif category:
        test_type, module = parse_category_key(category)
    else:
        raise ValueError("用例项缺少 test_type/module 或 category")

    case_index = int(item.get("case_index") or 0)
    case_name = (item.get("case_name") or "").strip()
    if case_index <= 0 and case_name:
        case_index = get_case_index_by_name(data, test_type, module, case_name)
    if not case_name and case_index > 0:
        case_name = get_case_name(data, test_type, module, case_index)

    return {
        "category": category,
        "test_type": test_type,
        "module": module,
        "case_index": case_index,
        "case_name": case_name,
    }
