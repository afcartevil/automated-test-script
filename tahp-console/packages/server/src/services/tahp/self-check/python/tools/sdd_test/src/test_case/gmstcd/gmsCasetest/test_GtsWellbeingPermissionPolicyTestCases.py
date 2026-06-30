# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    get_dumpsys_role_adb,
)

KNOWN_WELLBEING_PACKAGES = {
    "com.google.android.apps.tv.launcherx",
    "com.google.android.apps.wellbeing",
    "com.samsung.android.forest",
    "com.samsung.android.wellbeing",
}

ROLE_SYSTEM_WELLBEING = "android.app.role.SYSTEM_WELLBEING"


@pytest.mark.require_android_version_min(10)
def test_IsWellbeingAppKnown(device_serial):
    """
    # GMS-3.5-011
    # DESCRIPTION: [GTS]GtsWellbeingPermissionPolicyTestCases-com.google.android.wellbeing.permissionpolicy.gts.WellbeingPermissionPolicyTest#testIsWellbeingAppKnown
    验证设备上的 wellbeing 应用包名是否为已知包名
    """
    logging.info("开始测试: test_IsWellbeingAppKnown")

    logging.info("步骤 1: 获取 wellbeing 应用包名")
    role_holders = get_dumpsys_role_adb(device_serial, ROLE_SYSTEM_WELLBEING)
    logging.info(f"android.app.role.SYSTEM_WELLBEING holder={role_holders}")

    wellbeing_app_package_name = ""
    if role_holders and role_holders.strip():
        wellbeing_app_package_name = role_holders.strip().split("\n")[0].strip()

    if not wellbeing_app_package_name:
        logging.info("wellbeing 包名为空，测试通过 (PASS)")
        return

    logging.info("步骤 2: 验证 wellbeing 包名是否为已知包名")
    if wellbeing_app_package_name not in KNOWN_WELLBEING_PACKAGES:
        pytest.fail(f"Unknown wellbeing package: {wellbeing_app_package_name}")

    logging.info(f"测试通过 (PASS): wellbeing 包名 {wellbeing_app_package_name} 为已知包名")

