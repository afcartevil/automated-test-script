# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    get_dumpsys_package,
    getprop,
    get_dumpsys_role_adb,
    is_device_connect_wifi,
)


@pytest.mark.require_android_version_min(16)
def test_google_dlc_check(device_serial):

    ro_mainline_version_value = getprop('ro.mainline.version' , device_serial)
    logging.info(f"ro_mainline_version_value : {ro_mainline_version_value} ")

    if ro_mainline_version_value is None:
        pytest.skip("non APEX install")

    mSystem_device_controller_role_value = get_dumpsys_role_adb(device_serial, "android.app.role.SYSTEM_FINANCED_DEVICE_CONTROLLER")
    logging.info(f"mSystem_device_controller_role_value : {mSystem_device_controller_role_value} ")

    DLC_pkg_name = "com.google.android.devicelock"
    mDLC_version_value = get_dumpsys_package(device_serial, DLC_pkg_name, "Version")
    logging.info(f"mDLC_version_value : {mDLC_version_value} ")
    dlc_ver = mDLC_version_value or ""

    if "343201000" not in dlc_ver:
        pytest.fail("Google DLC 2.0 Apex version check FAIL!")

    if "com.google.android.devicelockcontroller" not in mSystem_device_controller_role_value:
        if is_device_connect_wifi(device_serial):
            pytest.skip("SYSTEM_FINANCED_DEVICE_CONTROLLER role is empty while device connect wifi; skip DLC role check")
        pytest.fail("Google DLC 2.0 Apex check FAIL!")


