# -*- coding: utf-8 -*-
import pytest
import logging

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    get_feature,
    get_apkpath_by_package,
    getprop,
    execute_command,
    get_cmd_overlay_lookup,
)


@pytest.mark.require_android_version_min(15)
@pytest.mark.require_gmse_plus
def test_gmse_plus_fmd(device_serial):
    google_findmydevice_path = get_apkpath_by_package(
        device_serial, "com.google.android.apps.adm"
    )

    logging.info(f"google_findmydevice_path path: {google_findmydevice_path}")


    if not bool(google_findmydevice_path):
        pytest.fail("Google FindMyDevice 未安装")

@pytest.mark.require_gmse_plus
def test_gmse_plus_calendar(device_serial):
    google_calendar_path = get_apkpath_by_package(
        device_serial, "com.google.android.calendar"
    )

    logging.info(f"google_calendar_path path: {google_calendar_path}")

    google_calendar_syncadapters_path = get_apkpath_by_package(
        device_serial, "com.google.android.syncadapters.calendar"
    )
    logging.info(f"google_calendar_syncadapters_path path: {google_calendar_syncadapters_path}")

    if not bool(google_calendar_path):
        pytest.fail("Google Calendar 未安装")

    if bool(google_calendar_syncadapters_path):
        pytest.fail("GoogleCalendarSyncAdapter 安装")


@pytest.mark.require_gmse_plus
def test_gmse_plus_mms(device_serial):
    google_messages_path = get_apkpath_by_package(
        device_serial, "com.google.android.apps.messaging"
    )

    logging.info(f"google_messages_path path: {google_messages_path}")

    if not bool(google_messages_path):
        pytest.fail("Google Messages 未安装")


@pytest.mark.require_android_version_min(17)
@pytest.mark.require_gmse_plus
def test_gmse_plus_defaultSms(device_serial):
    cmd_overlay_defaultSms = get_cmd_overlay_lookup(device_serial,"string","config_defaultSms")

    logging.info(f"cmd_overlay_defaultSms : {cmd_overlay_defaultSms}")

    if cmd_overlay_defaultSms != "com.google.android.apps.messaging":
        pytest.fail("GMSE+ 项目，默认短信不是 Google Messages")

@pytest.mark.require_gmse_plus
def test_gmse_plus_GoogleAssistant(device_serial):

    google_Assistant_path = get_apkpath_by_package(
        device_serial, "com.google.android.apps.googleassistant"
    )

    logging.info(f"google_Assistant_path path: {google_Assistant_path}")

    if not bool(google_Assistant_path):
        pytest.fail("GMSE+ 项目，Google Assistant 未安装")

@pytest.mark.require_gmse_plus
def test_gmse_plus_defaultAssistant(device_serial):

    cmd_overlay_defaultAssistant = get_cmd_overlay_lookup(device_serial,"string","config_defaultAssistant")

    logging.info(f"config_defaultAssistant : {cmd_overlay_defaultAssistant}")

    if cmd_overlay_defaultAssistant != "com.google.android.googlequicksearchbox":
        pytest.fail("GMSE+ 项目，默认助手不是 Google Assistant")

@pytest.mark.require_gmse_plus
def test_gmse_plus_defaultGallery(device_serial):

    cmd_overlay_defaultGallery = get_cmd_overlay_lookup(device_serial,"string","default_galler")

    logging.info(f"cmd_overlay_defaultGallery : {cmd_overlay_defaultGallery}")

    if cmd_overlay_defaultGallery != "com.google.android.apps.photos":
        pytest.fail("GMSE+ 项目，默认图库不是 Google Photos")



@pytest.mark.require_android_version_min(15)
@pytest.mark.require_gmse_plus
def test_gmse_plus_defaultBrowser_check(device_serial):
    
    cmd_overlay_defaultBrowser = get_cmd_overlay_lookup(device_serial,"string","default_browser")

    if cmd_overlay_defaultBrowser != "com.android.chrome":
        pytest.fail("GMSE+ 项目，默认浏览器不是 Google Chrome")


@pytest.mark.require_android_version_min(16)
@pytest.mark.require_gmse_plus
def test_Corner_swipe_Check(device_serial):

    cmd_overlay_longPressOnPowerBehavior = get_cmd_overlay_lookup(device_serial,"integer","config_longPressOnPowerBehavior")

    if cmd_overlay_longPressOnPowerBehavior == "5":
        pytest.fail("GME+ 项目支持 Corner_swipe,默认不能打开 LPP,测试fail")

@pytest.mark.require_gmse_plus
def test_gmse_intent_check(device_serial):
    """GME+ 项目特殊 intent 唤起 Google Assistant 检查"""

    is_low_ram = getprop("ro.config.low_ram", sn=device_serial) == "true"
    logging.info(f"is_low_ram: {is_low_ram}")

    check_intents = [
        "android.intent.action.ASSIST",
        "android.intent.action.VOICE_COMMAND",
        "android.speech.action.WEB_SEARCH",
    ]

    for intent in check_intents:
        cmd = f"adb -s {device_serial} shell am start -W -a {intent}"
        res = execute_command(cmd)
        logging.info(f"am start intent={intent}, output={res['output']}")

        activity_line = ""
        for line in res["output"].split("\n"):
            if "Activity:" in line:
                activity_line = line
                logging.info(activity_line)
                break

        # GO 项目需要指定 intent 拉起 com.google.android.apps.searchlite
        if is_low_ram:
            if "com.google.android.apps.searchlite" not in activity_line:
                pytest.fail(
                    f"check intent {intent} fail, should launch com.google.android.apps.searchlite"
                )
        # 非 GO 项目需要指定 intent 拉起 com.google.android.googlequicksearchbox
        else:
            if "com.google.android.googlequicksearchbox" not in activity_line:
                pytest.fail(
                    f"check intent {intent} fail, should launch com.google.android.googlequicksearchbox"
                )

    # 特殊 intent：android.speech.action.VOICE_SEARCH_HANDS_FREE 仅检查非 GO 项目
    if not is_low_ram:
        hands_free_intent = "android.speech.action.VOICE_SEARCH_HANDS_FREE"
        cmd = f"adb -s {device_serial} shell am start -W -a {hands_free_intent}"
        res = execute_command(cmd)
        logging.info(f"am start intent={hands_free_intent}, output={res['output']}")

        activity_line = ""
        for line in res["output"].split("\n"):
            if "Activity:" in line:
                activity_line = line
                logging.info(activity_line)
                break

        if "com.google.android.googlequicksearchbox" not in activity_line:
            pytest.fail(
                "check intent android.speech.action.VOICE_SEARCH_HANDS_FREE fail, "
                "should launch com.google.android.googlequicksearchbox"
            )

