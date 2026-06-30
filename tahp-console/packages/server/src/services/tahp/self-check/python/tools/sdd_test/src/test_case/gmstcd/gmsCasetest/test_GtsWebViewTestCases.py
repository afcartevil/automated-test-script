# -*- coding: utf-8 -*-
import re
import pytest
import logging

from src.utils.adb.adb_utils import (
    adb_shell,
    get_feature,
    is_package_exist,
)

WEBVIEW_PACKAGE_NAME = "com.google.android.webview"
PLAYSTORE_PACKAGE_NAME = "com.android.vending"
CHROME_PACKAGE_NAME = "com.android.chrome"
TRICHROME_LIBRARY_PACKAGE_NAME = "com.google.android.trichromelibrary"
TR_3P_WEBVIEW_FEATURE = "com.google.android.feature.TR_3P_WEBVIEW"


def _skip_if_google_webview_not_required(device_serial):
    """
    对应 Java WebViewTest.skipIfGoogleWebViewNotRequired。
    Play Store 未预装或启用第三方 WebView 特性时跳过测试。
    """
    if not is_package_exist(device_serial, PLAYSTORE_PACKAGE_NAME):
        pytest.skip("Play store does not exist on device, skipping test.")

    if get_feature(device_serial, TR_3P_WEBVIEW_FEATURE):
        pytest.skip("3P WebView feature flag set, skipping test.")


def _lookup_webview_package_count(device_serial):
    """对应 Java lookupWebViewPackageCount，统计已安装的 Google WebView 包数量。"""
    res = adb_shell(device_serial, f"pm list packages {WEBVIEW_PACKAGE_NAME}")
    if not res["success"] or not res["output"]:
        return 0

    count = 0
    for line in res["output"].splitlines():
        line = line.strip()
        if not line.startswith("package:"):
            continue
        package_name = line[len("package:") :].strip()
        if package_name == WEBVIEW_PACKAGE_NAME:
            count += 1
    return count


def _assert_single_webview_installed(device_serial):
    """对应 Java 中多处 Assert 仅允许安装一个 WebView 包。"""
    webview_count = _lookup_webview_package_count(device_serial)
    if webview_count != 1:
        pytest.fail(
            f"A single WebViewGoogle APK must be installed, found {webview_count}"
        )
    return webview_count


def _is_webview_system_app(device_serial):
    """
    对应 Java ApplicationInfo.flags & FLAG_SYSTEM。
    使用 pm list packages -s 判定 WebView 是否为系统应用。
    """
    res = adb_shell(device_serial, f"pm list packages -s {WEBVIEW_PACKAGE_NAME}")
    if not res["success"]:
        return False

    for line in res["output"].splitlines():
        if line.strip() == f"package:{WEBVIEW_PACKAGE_NAME}":
            return True
    return False


def _get_package_long_version_code(device_serial, package_name):
    """对应 Java PackageInfo.getLongVersionCode()。"""
    res = adb_shell(
        device_serial,
        f"dumpsys package {package_name} | grep -E 'versionCode|longVersionCode'",
    )
    if not res["success"] or not res["output"]:
        return None

    for line in res["output"].splitlines():
        match = re.search(r"(?:longVersionCode|versionCode)=(\d+)", line)
        if match:
            return int(match.group(1))
    return None


def _does_package_depend_on_trichrome(device_serial, package_name):
    """
    对应 Java doesPackageDependOnTrichrome：
    检查 ApplicationInfo.sharedLibraryFiles 是否引用 Trichrome 库 APK。
    """
    if not is_package_exist(device_serial, package_name):
        return False

    res = adb_shell(device_serial, f"dumpsys package {package_name}")
    if not res["success"] or not res["output"]:
        return False

    for line in res["output"].splitlines():
        if "sharedLibraryFiles" not in line:
            continue
        if ".apk" not in line:
            continue
        if TRICHROME_LIBRARY_PACKAGE_NAME in line or "trichromelibrary" in line.lower():
            return True
    return False


def _find_trichrome_library_count_and_version(device_serial):
    """
    对应 Java 在 getSharedLibraries 中查找 TrichromeLibrary。
    返回 (已安装数量, versionCode 或 None)。
    """
    res = adb_shell(
        device_serial, f"pm list packages {TRICHROME_LIBRARY_PACKAGE_NAME}"
    )
    if not res["success"] or not res["output"]:
        return 0, None

    count = 0
    for line in res["output"].splitlines():
        package_name = line.replace("package:", "").strip()
        if package_name == TRICHROME_LIBRARY_PACKAGE_NAME:
            count += 1

    if count == 0:
        return 0, None

    version = _get_package_long_version_code(
        device_serial, TRICHROME_LIBRARY_PACKAGE_NAME
    )
    return count, version


@pytest.mark.require_android_version_min(10)
def test_WebViewIsPreinstalled(device_serial):
    """
    # GMS
    # DESCRIPTION: [GTS]GtsWebViewTestCases-com.google.android.webview.gts.WebViewTest#testWebViewIsPreinstalled
    测试 WebView 是否预装
    """
    logging.info("开始测试: test_WebViewIsPreinstalled")

    _skip_if_google_webview_not_required(device_serial)
    _assert_single_webview_installed(device_serial)

    logging.info(f"测试通过: 设备预装了唯一的 {WEBVIEW_PACKAGE_NAME}")


@pytest.mark.require_android_version_min(10)
def test_WebViewIsSystem(device_serial):
    """
    # DESCRIPTION: [GTS]GtsWebViewTestCases-com.google.android.webview.gts.WebViewTest#testWebViewIsSystem
    测试 WebView 是否为系统应用 (FLAG_SYSTEM)
    """
    logging.info("开始测试: test_WebViewIsSystem")

    _skip_if_google_webview_not_required(device_serial)
    _assert_single_webview_installed(device_serial)

    if not _is_webview_system_app(device_serial):
        pytest.fail("WebViewGoogle APK must be FLAG_SYSTEM")

    logging.info(f"测试通过: {WEBVIEW_PACKAGE_NAME} 为系统应用")


@pytest.mark.require_android_version_min(10)
def test_TrichromeLibraryVersionsMatch(device_serial):
    """
    # GMS-7.7-002
    # DESCRIPTION: [GTS]GtsWebViewTestCases-com.google.android.webview.gts.WebViewTest#testTrichromeLibraryVersionsMatch
    测试 Trichrome 共享库与 WebView/Chrome 的版本是否一致
    """
    logging.info("开始测试: test_TrichromeLibraryVersionsMatch")

    _skip_if_google_webview_not_required(device_serial)

    if not is_package_exist(device_serial, WEBVIEW_PACKAGE_NAME):
        pytest.fail("WebView 必须预装")

    is_trichrome_webview = _does_package_depend_on_trichrome(
        device_serial, WEBVIEW_PACKAGE_NAME
    )
    is_trichrome_chrome = False
    if is_package_exist(device_serial, CHROME_PACKAGE_NAME):
        is_trichrome_chrome = _does_package_depend_on_trichrome(
            device_serial, CHROME_PACKAGE_NAME
        )

    trichrome_count, trichrome_version = _find_trichrome_library_count_and_version(
        device_serial
    )
    if trichrome_count > 1:
        pytest.fail("TrichromeLibrary 只能预装一个版本")

    webview_version = _get_package_long_version_code(
        device_serial, WEBVIEW_PACKAGE_NAME
    )
    logging.info(
        "Trichrome 依赖状态: webview=%s, chrome=%s, trichrome_count=%s",
        is_trichrome_webview,
        is_trichrome_chrome,
        trichrome_count,
    )

    if is_trichrome_webview:
        if trichrome_count == 0 or trichrome_version is None:
            pytest.fail("WebView 依赖 TrichromeLibrary，必须预装 TrichromeLibrary")
        if webview_version != trichrome_version:
            pytest.fail(
                f"WebView 与 TrichromeLibrary 的 versionCode 必须一致: "
                f"{webview_version} vs {trichrome_version}"
            )

    if is_trichrome_chrome:
        chrome_version = _get_package_long_version_code(
            device_serial, CHROME_PACKAGE_NAME
        )
        if trichrome_count == 0 or trichrome_version is None:
            pytest.fail("Chrome 依赖 TrichromeLibrary，必须预装 TrichromeLibrary")
        if chrome_version != trichrome_version:
            pytest.fail(
                f"Chrome 与 TrichromeLibrary 的 versionCode 必须一致: "
                f"{chrome_version} vs {trichrome_version}"
            )

    if not is_trichrome_webview and not is_trichrome_chrome:
        if trichrome_count > 0:
            pytest.fail(
                "WebView 与 Chrome 均不依赖 TrichromeLibrary 时，不得预装 TrichromeLibrary"
            )

    logging.info("测试通过: Trichrome 库版本与依赖关系符合要求")
