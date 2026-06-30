# -*- coding: utf-8 -*-
import logging
import time
from pathlib import Path

import pytest

from src.utils.adb.adb_utils import (
    adb_shell,
    execute_command,
    is_package_exist,
)
from src.utils.adb.adb_utils_private import execute_command as execute_command_private


APK_PATH = Path(__file__).resolve().parent / "XtsSmokeTest.apk"
PACKAGE_NAME = "com.tran.xts.smoketest"
ACTIVITY_NAME = f"{PACKAGE_NAME}/.XtsMainActivity"
TAG_FILTER = "TAG_XtsMainActivity"


def _install_apk(device_serial):
    """安装 XtsSmokeTest.apk"""
    result = execute_command_private(
        ["adb", "-s", device_serial, "install", "-r", str(APK_PATH)],
        timeout=120,
        no_retry=True,
    )
    if not result.get("success"):
        logging.error(f"XtsSmokeTest install failed: {result}")
        return False
    return is_package_exist(device_serial, PACKAGE_NAME)


def _start_activity(device_serial):
    """启动 XtsSmokeTest 应用"""
    result = adb_shell(device_serial, f"am start -W -n {ACTIVITY_NAME}", timeout=30)
    logging.info(f"XtsSmokeTest start result: {result}")
    if not result.get("success"):
        pytest.fail(f"XtsSmokeTest start failed: {result}")


def _clear_logcat(device_serial):
    """清空 logcat 缓冲区"""
    execute_command_private(
        ["adb", "-s", device_serial, "logcat", "-c"],
        timeout=10,
        no_retry=True,
    )


def _dump_logcat(device_serial):
    """获取最近的 logcat 日志"""
    result = execute_command_private(
        ["adb", "-s", device_serial, "logcat", "-d", "-t", "3000"],
        timeout=30,
        no_retry=True,
    )
    if not result.get("success"):
        logging.error(f"logcat dump failed: {result}")
        pytest.fail(f"logcat dump failed: {result}")
    return result.get("output") or ""


def _check_smoke_fail(log_text):
    """在 logcat 日志中查找 'Smoking test FAIL' 字串"""
    fail_lines = [
        line for line in log_text.splitlines()
        if "Smoking test FAIL" in line
    ]
    return fail_lines


def _uninstall_apk(device_serial):
    """卸载 XtsSmokeTest.apk"""
    result = execute_command_private(
        ["adb", "-s", device_serial, "uninstall", PACKAGE_NAME],
        timeout=30,
        no_retry=True,
    )
    if not result.get("success"):
        logging.warning(f"XtsSmokeTest uninstall failed: {result}")


@pytest.mark.require_android_version_min(15)
def test_NoDebuggable(device_serial):
    """
    安装 XtsSmokeTest.apk，启动后读取 logcat 日志，
    若包含 "Smoking test FAIL" 则测试失败。
    """
    if not APK_PATH.exists():
        pytest.skip(f"XtsSmokeTest.apk not found: {APK_PATH}")

    if not _install_apk(device_serial):
        pytest.fail("XtsSmokeTest.apk install failed")

    try:
        _clear_logcat(device_serial)
        _start_activity(device_serial)
        time.sleep(5)

        log_text = _dump_logcat(device_serial)
        fail_lines = _check_smoke_fail(log_text)

        if fail_lines:
            detail = "\n".join(fail_lines)
            logging.error(f"Found 'Smoking test FAIL' in logcat:\n{detail}")
            pytest.fail(f"Found 'Smoking test FAIL' in logcat:\n{detail}")

        logging.info("XtsSmokeTest passed: no 'Smoking test FAIL' found in logcat")

    finally:
        _uninstall_apk(device_serial)
