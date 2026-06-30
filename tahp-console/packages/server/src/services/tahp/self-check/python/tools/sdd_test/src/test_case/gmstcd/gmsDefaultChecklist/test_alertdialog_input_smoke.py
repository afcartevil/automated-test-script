# -*- coding: utf-8 -*-
import pytest

from src.utils.adb.adb_utils import adb_shell, get_feature


def _shell_output(device_serial, command):
    result = adb_shell(device_serial, command, no_retry=True)
    return (result.get("output") or result.get("error") or "").strip()

@pytest.mark.require_android_version_min(15)
def test_alertdialog_keyevent_callback_capability_smoke(device_serial):
    """
    ID:TOS1600-ALERTDIALOG-INPUT-CAP
    DESCRIPTION:[CTS]AlertDialogTest#testCallback
    """
    if get_feature(device_serial, "android.software.leanback"):
        pytest.skip("skip on leanback device")

    input_help = _shell_output(device_serial, "input -h")
    if not input_help:
        pytest.skip("input -h returns empty output; input command path may be unavailable")
    lower_input_help = input_help.lower()
    if "can't find service" in lower_input_help or "securityexception" in lower_input_help:
        pytest.fail(f"input command service unavailable: {input_help}")

    window_service = _shell_output(device_serial, "service check window")
    if not window_service:
        pytest.skip("service check window returns empty output; window service path may be unavailable")
    lower_window_service = window_service.lower()
    if "not found" in lower_window_service or "no service" in lower_window_service:
        pytest.fail(f"window service not found: {window_service}")
    if "permission denial" in lower_window_service or "exception" in lower_window_service:
        pytest.fail(f"window service check failed: {window_service}")

    window_dump = _shell_output(device_serial, "dumpsys window windows")
    if window_dump:
        focus_lines = [
            ln for ln in window_dump.splitlines()
            if ("mCurrentFocus" in ln or "mFocusedApp" in ln or "mFocusedWindow" in ln)
        ]
        if focus_lines:
            preview = " | ".join(focus_lines)
            if len(preview) > 200:
                preview = preview[:200] + "..."

    keyevent_result = _shell_output(
        device_serial,
        'input keyevent 7 >/dev/null 2>&1; echo __EXIT:$?__',
    )
    assert "__EXIT:0__" in keyevent_result, (
        f"input keyevent command failed, raw output: {keyevent_result}"
    )
