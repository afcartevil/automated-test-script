# -*- coding: utf-8 -*-
import pytest
import logging

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    get_feature,
    get_dumpsys_package,
)


@pytest.mark.require_android_version_min(15)
def test_gemini_check(device_serial):

    mGemini_supprot = get_feature(device_serial, 'com.google.android.feature.GEMINI_EXPERIENCE')

    if mGemini_supprot is None:
        pytest.skip("Gemini not support,跳过测试")

    # Gemini packageName com.google.android.apps.bard/.shellapp.BardEntryPointActivity
    get_Gemini_versionName = get_dumpsys_package(device_serial, "com.google.android.apps.bard", "versionName")
    logging.info("get_Gemini_versionName=" + get_Gemini_versionName)

    if get_Gemini_versionName is None:
        reason = "Gemini not install"
        pytest.fail(reason)

    get_GoogleAssistant_versionName = get_feature(device_serial, "com.google.android.apps.googleassistant", "versionName")
    logging.info("get_GoogleAssistant_versionName=" + get_GoogleAssistant_versionName)

    if get_GoogleAssistant_versionName is not None:
        reason = "GoogleAssistant install for Gemini device"
        pytest.fail(reason)


@pytest.mark.require_android_version_min(16)
@pytest.mark.require_spd_feature_support("SF-202507-001368")
def test_gemini_A16_check(device_serial):

    mGemini_supprot = get_feature(device_serial, 'com.google.android.feature.GEMINI_EXPERIENCE')

    if mGemini_supprot is None:
        pytest.fail("项目支持Gemini ,测试fail。")

    # Gemini packageName com.google.android.apps.bard/.shellapp.BardEntryPointActivity
    get_Gemini_versionName = get_dumpsys_package(device_serial, "com.google.android.apps.bard", "versionName")
    logging.info("get_Gemini_versionName=" + get_Gemini_versionName)

    if get_Gemini_versionName is None:
        reason = "Gemini not install"
        pytest.fail(reason)

    get_GoogleAssistant_versionName = get_feature(device_serial, "com.google.android.apps.googleassistant", "versionName")
    logging.info("get_GoogleAssistant_versionName=" + get_GoogleAssistant_versionName)

    if get_GoogleAssistant_versionName is not None:
        reason = "GoogleAssistant install for Gemini device"
        pytest.fail(reason)

