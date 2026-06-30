# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    get_dumpsys_package,
    get_dumpsys_role_adb,
)


@pytest.mark.require_android_version_min(16)
def test_emergency_role_has_holder(device_serial):

    # OS162-35591:
    # 检查 PersonalSafetyCommonTest#testEmergencyRoleHasHolder
    # 验证设备上是否有应用持有 android.app.role.EMERGENCY 角色

    mPersonalSafetyPkgName = "com.google.android.apps.safetyhub"
    get_PersonalSafety_versionName = get_dumpsys_package(device_serial, mPersonalSafetyPkgName, "versionName")

    # logging.info(f"get_PersonalSafety_versionName : {get_PersonalSafety_versionName} ")

    if get_PersonalSafety_versionName is None:
        pytest.fail("项目需求: Google PersonalSafety 未安装")

    # 检查 android.app.role.EMERGENCY 角色是否有 holder
    emergency_role_holder = get_dumpsys_role_adb(device_serial, "android.app.role.EMERGENCY")

    logging.info(f"android.app.role.EMERGENCY holder={emergency_role_holder}")

    if emergency_role_holder is None or emergency_role_holder.strip() == "":
        reason = ("No app holds the android.app.role.EMERGENCY role.")
        pytest.fail(reason)

    # 验证 holder 是否为 safetyhub
    if "com.google.android.apps.safetyhub" not in emergency_role_holder:
        reason = ("android.app.role.EMERGENCY holder is: " + emergency_role_holder +
                  ", not com.google.android.apps.safetyhub. Please verify the EMERGENCY role configuration.")
        pytest.fail(reason)

    logging.info("test_emergency_role_has_holder: PASS")


