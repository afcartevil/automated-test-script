# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    get_dumpsys_package,
    get_feature,
    get_cmd_overlay_lookup,
)


@pytest.mark.require_android_version_min(16)
@pytest.mark.require_spd_feature_support("SF-202507-002346")
def test_GPPS_integrate_check(device_serial):
    mOdad_pkg_name = "com.google.android.odad"
    mOdad_version_value = get_dumpsys_package(device_serial, mOdad_pkg_name, "versionName")

    logging.info(f"mOdad_version_value : {mOdad_version_value} ")

    mGPPS_features_SUPPORT = get_feature(
        feature_name="com.google.android.feature.GPP_SERVICE_COMPATIBLE", device_serial=device_serial
    )

    mConfig_defaultListenerAccessPackages = get_cmd_overlay_lookup(device_serial, "string", "config_defaultListenerAccessPackages")
    mConfig_systemAppProtectionService = get_cmd_overlay_lookup(device_serial, "string", "config_systemAppProtectionService")
    mConfig_defaultContentProtectionService = get_cmd_overlay_lookup(device_serial, "string", "config_defaultContentProtectionService")


    if mOdad_version_value is None \
            or mGPPS_features_SUPPORT is None \
            or "com.google.android.odad" not in mConfig_defaultListenerAccessPackages \
            or mConfig_systemAppProtectionService == "" \
            or mConfig_defaultContentProtectionService == "":
        pytest.fail("项目需求: Google Odad 未安装")


