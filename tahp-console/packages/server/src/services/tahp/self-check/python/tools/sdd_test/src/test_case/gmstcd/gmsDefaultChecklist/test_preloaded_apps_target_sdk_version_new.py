# -*- coding: utf-8 -*-
import logging
import re
import time
from pathlib import Path

import pytest

from src.utils.adb.adb_utils_private import (
    execute_command,
    get_apkpath_by_package,
    getprop,
)


APK_PATH = (
    Path(__file__).resolve().parents[4] / "data" / "file" / "TargetSdkCheck.apk"
)

PACKAGE_NAME = "com.transsion.preloadappstargetsdkcheck"
ACTIVITY_NAME = f"{PACKAGE_NAME}/.MainActivity"
TAG_FILTER = "SdkTargetChecker"

PYTHON_WHITELIST = {
    "com.qualcomm.qti.qms.service.trustzoneaccess",
    "com.qualcomm.qti.qms.service.connectionsecurity",
    "com.autotest.factory_reset_stress",
    "com.android.fanstrace",
    "com.jiiov.fingerprint_factorytest",
}


def _install_checker_apk(device_serial):
    result = execute_command(
        ["adb", "-s", device_serial, "install", "-r", str(APK_PATH)],
        timeout=120,
        no_retry=True,
    )

    if not result.get("success"):
        logging.error(f"TargetSdkCheck install failed: {result}")
        return False

    return bool(get_apkpath_by_package(device_serial, PACKAGE_NAME))


def _start_checker(device_serial):
    result = execute_command(
        ["adb", "-s", device_serial, "shell", "am", "start", "-W", "-n", ACTIVITY_NAME],
        timeout=30,
        no_retry=True,
    )

    logging.info(f"TargetSdkCheck start result: {result}")

    if not result.get("success"):
        pytest.fail(f"TargetSdkCheck start failed: {result}")


def _clear_logcat(device_serial):
    result = execute_command(
        ["adb", "-s", device_serial, "logcat", "-c"],
        timeout=10,
        no_retry=True,
    )

    if not result.get("success"):
        logging.warning(f"TargetSdkCheck clear logcat failed: {result}")


def _dump_recent_logcat(device_serial):
    result = execute_command(
        ["adb", "-s", device_serial, "logcat", "-d", "-t", "3000"],
        timeout=30,
        no_retry=True,
    )

    if not result.get("success"):
        logging.error(f"TargetSdkCheck logcat dump failed: {result}")
        pytest.fail(f"TargetSdkCheck logcat dump failed: {result}")

    return result.get("output") or ""


def _parse_apps_below_requirement(log_text):
    if not log_text:
        return []

    lines = [
        line
        for line in log_text.splitlines()
        if TAG_FILTER in line or "must target" in line
    ]

    if not lines:
        logging.info("TargetSdkCheck no targetSdk warning log found")
        return []

    logging.info("TargetSdkCheck matched log lines:\n" + "\n".join(lines))

    pattern = r"([a-zA-Z0-9_.]+)\s*\(must target (\d+) or higher, but targets (\d+)\)"

    apps = []

    for package_name, required_sdk, current_sdk in re.findall(
        pattern, "\n".join(lines)
    ):
        apps.append(
            {
                "package": package_name.strip(),
                "required_sdk": int(required_sdk),
                "current_sdk": int(current_sdk),
            }
        )

    return apps


def _uninstall_checker_apk(device_serial):
    result = execute_command(
        ["adb", "-s", device_serial, "uninstall", PACKAGE_NAME],
        timeout=30,
        no_retry=True,
    )

    if not result.get("success"):
        logging.warning(f"TargetSdkCheck uninstall failed or package not installed: {result}")


@pytest.mark.require_android_version_min(16)
def testPreloadedAppsTargetSdkVersionNew(device_serial):
    if not APK_PATH.exists():
        pytest.skip(f"TargetSdkCheck.apk not found: {APK_PATH}")

    sdk = int(getprop("ro.build.version.sdk", device_serial) or 0)

    if sdk <= 37:
        pytest.skip(f"device sdk={sdk}, skip targetSdk check")

    build_type = (getprop("ro.build.type", device_serial) or "").strip()

    if build_type == "userdebug":
        pytest.skip(f"build type is {build_type}, skip targetSdk check")

    if not _install_checker_apk(device_serial):
        pytest.fail("TargetSdkCheck.apk install failed")

    try:
        _clear_logcat(device_serial)

        _start_checker(device_serial)

        time.sleep(3)

        log_text = _dump_recent_logcat(device_serial)

        apps = _parse_apps_below_requirement(log_text)

        logging.info(f"TargetSdkCheck parsed dissatisfied apps: {apps}")

        if PYTHON_WHITELIST:
            original_count = len(apps)

            apps = [
                app
                for app in apps
                if app["package"] not in PYTHON_WHITELIST
            ]

            filtered_count = original_count - len(apps)

            if filtered_count:
                logging.info(
                    f"TargetSdkCheck Python whitelist filtered {filtered_count} app(s)"
                )

        if apps:
            details = "\n".join(
                f"{app['package']}: target {app['current_sdk']} "
                f"(required {app['required_sdk']} or higher)"
                for app in apps
            )

            logging.error(
                f"Found {len(apps)} system apps with dissatisfied targetSDK:\n{details}"
            )

            pytest.fail(
                f"Found {len(apps)} system apps with dissatisfied targetSDK:\n{details}"
            )

        logging.info("TargetSdkCheck passed: all system apps meet targetSdk requirement")

    finally:
        _uninstall_checker_apk(device_serial)