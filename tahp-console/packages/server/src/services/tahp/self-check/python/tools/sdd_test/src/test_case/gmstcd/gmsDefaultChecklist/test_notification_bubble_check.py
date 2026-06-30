# -*- coding: utf-8 -*-
import pytest

from src.utils.adb.adb_utils import (
    adb_shell,
    adb_shell_settings_get_secure,
    get_feature,
    getprop,
)


def _shell_output(device_serial, command):
    result = adb_shell(device_serial, command, no_retry=True)
    return (result.get("output") or result.get("error") or "").strip()

@pytest.mark.require_android_version_min(15)
def test_notification_bubble_launch_activity_options_security_smoke(device_serial):
    """
    ID:TOS1600-NOTIF-BUBBLE-SEC
    DESCRIPTION:[CTS]NotificationManagerBubbleTest#testNotificationManagerBubble_launchBubble_activityOptions_fails
    """
    if getprop("ro.config.low_ram", device_serial) == "true":
        pytest.skip("low_ram device")
    if get_feature(device_serial, "android.hardware.type.watch"):
        pytest.skip("watch device")
    if get_feature(device_serial, "android.hardware.type.automotive"):
        pytest.skip("automotive device")
    if get_feature(device_serial, "android.software.leanback"):
        pytest.skip("leanback device")

    cmd_help = _shell_output(device_serial, "cmd notification -h")
    if not cmd_help:
        pytest.skip("cmd notification -h returns empty output")
    if "Can't find service: notification" in cmd_help:
        pytest.fail("cmd notification service path unavailable")

    bubble_setting = adb_shell_settings_get_secure(device_serial, "notification_bubbles")
    if not bubble_setting:
        pytest.skip(
            "settings secure notification_bubbles is empty; bubbles may be unsupported on this device"
        )
    if bubble_setting == "null":
        pytest.skip("notification_bubbles is null")
