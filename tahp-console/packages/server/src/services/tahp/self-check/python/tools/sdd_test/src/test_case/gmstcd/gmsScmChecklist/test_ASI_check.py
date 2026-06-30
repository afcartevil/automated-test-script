# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    get_dumpsys_package,
    get_cmd_overlay_lookup,
    get_feature,
)


@pytest.mark.require_android_version_min(16)
@pytest.mark.require_non_go_device()
def test_ASI_check(device_serial):

    # ASI 检查
    mASI_pkg_name = "com.google.android.as"
    mASI_versionName = get_dumpsys_package(device_serial, mASI_pkg_name,"versionName")
    logging.info(f"mASI_versionName: {mASI_versionName}")

    if mASI_versionName is None:
        pytest.fail("ASI not install.")


    mDefaultAppPredictionService = get_cmd_overlay_lookup(device_serial, "string", "config_defaultAppPredictionService")
    logging.info(f"mDefaultAppPredictionService: {mDefaultAppPredictionService}")

    mASIPlus_feature = get_feature(device_serial, "com.google.android.feature.ASI")
    logging.info(f"mASIPlus_feature: {mASIPlus_feature}")
    mASI_feature = get_feature(device_serial, "com.google.android.feature.ASI_MINIMAL")
    logging.info(f"mASI_feature: {mASI_feature}")

    mSystemCaptionsServiceCallsEnabled = get_cmd_overlay_lookup(device_serial, "bool", "config_systemCaptionsServiceCallsEnabled")
    logging.info(f"mSystemCaptionsServiceCallsEnabled: {mSystemCaptionsServiceCallsEnabled}")

    # GMS_ASI_APK_PRELOAD_TYPE 为 Features，即 ASIPlus
    if "oemfull" in mASI_versionName :
        if mSystemCaptionsServiceCallsEnabled != "true" \
                or mDefaultAppPredictionService =="" \
                or mASIPlus_feature is None :
            pytest.fail("ASIPlus check fail.")
    else:
        if "oemminimal" not in mASI_versionName \
                or mSystemCaptionsServiceCallsEnabled == "true" \
                or mDefaultAppPredictionService !="" \
                or mASI_feature is None :
            pytest.fail("ASI check fail.")


@pytest.mark.require_android_version_min(16)
@pytest.mark.require_spd_feature_support("SF-202507-001187")
@pytest.mark.require_non_go_device()
def test_ASI_plus_check(device_serial):
    # ASI plus 检查
    mASI_plus_pkg_name = "com.google.android.as"
    mASI_plus_versionName = get_dumpsys_package(device_serial, mASI_plus_pkg_name,"versionName")
    logging.info(f"mASI_plus_versionName: {mASI_plus_versionName}")

    if "oemfull" not in mASI_plus_versionName :
        pytest.fail("ASI plus not install.")
        