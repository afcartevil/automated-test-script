# -*- coding: utf-8 -*-
import logging
import os

import pytest

from src.utils.adb.adb_utils import (
    getprop,
    is_file_exist,
    pull_file,
)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_PERMISSION_GROUPS = 3  # owner / group / all users
_READ_PERMISSION = 4
_WRITE_PERMISSION = 2
_EXECUTE_PERMISSION = 1

_VENDOR_OR_ODM_NAMESPACES = [
    "ctl.odm.",
    "ctl.vendor.",
    "ctl.start$odm.",
    "ctl.start$vendor.",
    "ctl.stop$odm.",
    "ctl.stop$vendor.",
    "init.svc.odm.",
    "init.svc.vendor.",
    "ro.boot.",
    "ro.hardware.",
    "ro.odm.",
    "ro.vendor.",
    "odm.",
    "persist.odm.",
    "persist.vendor.",
    "vendor.",
]

# API level <= 30 时额外允许的命名空间
_VENDOR_OR_ODM_NAMESPACES_WHITELIST = [
    "persist.camera.",
    "persist.dumpstate.verbose_logging.enabled",
]

_PRODUCT_PROPERTY_CONTEXTS_PATH = (
    "/product/etc/selinux/product_property_contexts"
)

# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------

def _has_permission(permission_bits: str, group_index: int, permission: int) -> bool:
    """判断权限位字符串中某个组是否拥有指定权限。

    Args:
        permission_bits: 八进制权限字符串，如 "741"
        group_index: 组索引（0=owner, 1=group, 2=others），-1 表示检查所有组
        permission: 权限值（READ=4, WRITE=2, EXECUTE=1）

    Returns:
        True 表示指定组（或所有组）均拥有该权限

    Raises:
        ValueError: group_index 或 permission_bits 非法
    """
    if group_index >= _PERMISSION_GROUPS:
        raise ValueError(f"Invalid group: {group_index}")
    if len(permission_bits) != _PERMISSION_GROUPS:
        raise ValueError(f"Invalid permission bits: {permission_bits}")

    start = group_index if group_index >= 0 else 0
    end = group_index + 1 if group_index >= 0 else _PERMISSION_GROUPS

    for i in range(start, end):
        perm = int(permission_bits[i])  # 非数字时抛出 ValueError
        if perm > 7:
            raise ValueError(f"Invalid permission bit: {perm}")
        if perm & permission == 0:
            return False
    return True

def _is_readable(permission_bits: str) -> bool:
    """判断权限位字符串中是否有任意组拥有读权限。"""
    return any(
        _has_permission(permission_bits, i, _READ_PERMISSION)
        for i in range(_PERMISSION_GROUPS)
    )

def _parse_property_dict(property_contexts_file, exact_only: bool = False) -> dict:
    """解析 property_contexts 文件，返回 {property_name: tokens} 字典。

    Args:
        property_contexts_file: 已打开的文件对象
        exact_only: 为 True 时仅解析带 exact 匹配标记的属性
    """
    property_dict = {}
    for line in property_contexts_file.readlines():
        tokens = line.strip().rstrip("\n").split()
        if not tokens or tokens[0].startswith("#"):
            continue
        if not exact_only:
            property_dict[tokens[0]] = tokens
        elif len(tokens) >= 4 and tokens[2] == "exact":
            property_dict[tokens[0]] = tokens
    return property_dict

def _check_vendor_or_odm_property_names(
    device_serial: str, partition: str, contexts_path: str
) -> list[str]:
    """检查指定分区的 property_contexts 文件中是否存在命名空间违规。

    Returns:
        违规属性名列表；列表为空表示检查通过；返回 None 表示文件不存在（跳过）
    """
    if not is_file_exist(device_serial, contexts_path):
        logging.info(f"{contexts_path} 不存在，跳过 {partition} 属性检查")
        return None

    local_path = f"{partition}_property_contexts"

    try:
        ok = pull_file(device_serial, contexts_path, local_path)
        if not ok:
            logging.warning(f"pull {contexts_path} 失败，跳过 {partition} 属性检查")
            return None

        with open(local_path, "r") as f:
            property_dict = _parse_property_dict(f)

        logging.info(f"在 {partition} property contexts 中找到 {len(property_dict)} 个属性")

        allowed = _VENDOR_OR_ODM_NAMESPACES.copy()
        launch_api_level = int(getprop("ro.product.first_api_level", sn=device_serial) or 0)
        if launch_api_level <= 30:
            allowed += _VENDOR_OR_ODM_NAMESPACES_WHITELIST

        violations = [
            name
            for name in property_dict
            if not any(name.startswith(prefix) for prefix in allowed)
        ]
        return violations

    finally:
        if os.path.exists(local_path):
            os.remove(local_path)


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

@pytest.mark.require_non_cuttlefish
def test_vendor_property_names(device_serial):
    """vendor property_contexts 中的属性必须使用合法的 vendor/ODM 命名空间。"""
    violations = _check_vendor_or_odm_property_names(
        device_serial,
        partition="vendor",
        contexts_path="/vendor/etc/selinux/vendor_property_contexts",
    )

    if violations is None:
        pytest.skip("vendor_property_contexts 文件不存在，跳过检查")

    if violations:
        pytest.fail(
            f"vendor properties 命名空间违规: {sorted(violations)}"
        )

@pytest.mark.require_non_cuttlefish
def test_odm_property_names(device_serial):
    """odm property_contexts 中的属性必须使用合法的 vendor/ODM 命名空间。"""
    violations = _check_vendor_or_odm_property_names(
        device_serial,
        partition="odm",
        contexts_path="/odm/etc/selinux/odm_property_contexts",
    )

    if violations is None:
        pytest.skip("odm_property_contexts 文件不存在，跳过检查")

    if violations:
        pytest.fail(
            f"odm properties 命名空间违规: {sorted(violations)}"
        )

@pytest.mark.require_non_cuttlefish
def test_product_property_names(device_serial):
    """product properties 不得使用 vendor/ODM 命名空间（Android Q 及以上）。"""
    launch_api_level = int(
        getprop("ro.product.first_api_level", sn=device_serial) or 0
    )
    if launch_api_level <= 28:
        pytest.skip("首发 API level <= 28（Android P 及以下），跳过检查")

    if not is_file_exist(device_serial, _PRODUCT_PROPERTY_CONTEXTS_PATH):
        pytest.skip(f"{_PRODUCT_PROPERTY_CONTEXTS_PATH} 不存在，跳过检查")

    local_path = "product_property_contexts"

    try:
        ok = pull_file(device_serial, _PRODUCT_PROPERTY_CONTEXTS_PATH, local_path)
        if not ok:
            pytest.skip(f"pull {_PRODUCT_PROPERTY_CONTEXTS_PATH} 失败，跳过检查")

        logging.info(f"adb pull {_PRODUCT_PROPERTY_CONTEXTS_PATH} → {local_path}")

        with open(local_path, "r") as f:
            property_dict = _parse_property_dict(f, exact_only=True)

        logging.info(f"在 product property contexts 中找到 {len(property_dict)} 个属性")

        violations = [
            name
            for name in property_dict
            if any(name.startswith(prefix) for prefix in _VENDOR_OR_ODM_NAMESPACES)
        ]

        if violations:
            pytest.fail(
                f"product properties 命名空间违规: {sorted(violations)}"
            )

    finally:
        if os.path.exists(local_path):
            os.remove(local_path)

