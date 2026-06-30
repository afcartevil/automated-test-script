# -*- coding: utf-8 -*-
import logging
import re

import pytest

from src.conftests.device import get_device_market
from src.utils.adb.adb_utils import (
    get_apkpath_by_package,
    get_product_name_without_market,
    getprop,
    is_package_exist,
)

GOOGLE_ONE_PACKAGE = "com.google.android.apps.subscriptions.red"
# COCL 市场不可卸载，安装在非 operator 路径
GOOGLE_ONE_NON_REMOVABLE_PATHS = {
    "/tr_region/app/GoogleOne/GoogleOne.apk",
    "/tr_carrier/app/GoogleOne/GoogleOne.apk",
}
# 其他市场可卸载，安装在 operator 路径
GOOGLE_ONE_REMOVABLE_PATHS = {
    "/tr_region/operator/app/GoogleOne/GoogleOne.apk",
    "/tr_carrier/operator/app/GoogleOne/GoogleOne.apk",
}

A16_REQUIRED_PROJECTS = {
    "X6887",
    "X6878",
    "X6879",
    "X6891",
    "X6890",
    "X6896",
    "X6895",
    "X6895B",
    "X6842B",
    "X6842",
    "X6840B",
    "X6840",
    "CN5",
    "CN5C",
    "CN7C",
    "CN6C",
    "CN6",
    "LK7K",
    "LK7",
    "KN4",
    "KN4N",
    "KN8",
    "KO5",
    "KO3",
    "X1103",
    "X1103B",
}
A15_REQUIRED_PROJECTS = {"KN3"}


def _get_android_major_version(device_serial):
    android_version = (getprop("ro.build.version.release", device_serial) or "").strip()
    match = re.search(r"\d+", android_version)
    return int(match.group()) if match else 0


def _is_google_one_required(android_major_version, project_name, market):
    normalized_project = (project_name or "").strip().upper()
    normalized_market = (market or "").strip().upper()

    if android_major_version == 16 and normalized_project in A16_REQUIRED_PROJECTS:
        return normalized_market != "RU"
    if android_major_version == 15 and normalized_project in A15_REQUIRED_PROJECTS:
        return normalized_market != "RU"
    return False



@pytest.mark.require_android_version_min(15)
def test_google_one_preload_check(device_serial):
    android_major_version = _get_android_major_version(device_serial)
    project_name = get_product_name_without_market(device_serial)
    market = get_device_market(device_serial)

    logging.info(
        "Google One check context - android_major_version: %s, project_name: %s, market: %s",
        android_major_version,
        project_name,
        market,
    )

    normalized_market = (market or "").strip().upper()
    is_required = _is_google_one_required(android_major_version, project_name, market)

    if normalized_market == "TOCC":
        pytest.skip(f"TOCC 市场暂不校验 Google One 预装: Android {android_major_version}, Project {project_name}")

    is_installed = is_package_exist(device_serial, GOOGLE_ONE_PACKAGE)
    apk_path = get_apkpath_by_package(device_serial, GOOGLE_ONE_PACKAGE) if is_installed else ""

    logging.info(
        "Google One status - required: %s, installed: %s, apk_path: %s",
        is_required,
        is_installed,
        apk_path,
    )

    if normalized_market == "RU":
        if is_installed:
            pytest.fail("RU 市场不应预装 Google One")
        return

    if not is_required:
        pytest.skip(
            f"当前项目不在 Google One 预装范围: Android {android_major_version}, "
            f"Project {project_name}, Market {market}"
        )

    if not is_installed:
        pytest.fail("Google One 应预装但未安装")

    if normalized_market == "COCL":
        if apk_path not in GOOGLE_ONE_NON_REMOVABLE_PATHS:
            pytest.fail(
                f"COCL 市场 Google One 预装路径不符合预期。实际: {apk_path}, "
                f"期望: {sorted(GOOGLE_ONE_NON_REMOVABLE_PATHS)}"
            )
    else:
        if apk_path not in GOOGLE_ONE_REMOVABLE_PATHS:
            pytest.fail(
                f"可卸载市场 Google One 预装路径不符合预期。实际: {apk_path}, "
                f"期望: {sorted(GOOGLE_ONE_REMOVABLE_PATHS)}"
            )
