# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    is_package_exist,
)


@pytest.mark.require_android_version_min(10)
def test_Required3ButtonNavMode(device_serial):
    """
    # GMS-8.4-001
    # DESCRIPTION: [GTS]GtsSystemNavigationTestCases-com.google.android.systemui.gts.SystemNavigationModeTest#testRequired3ButtonNavMode
    测试系统三键导航模式，测试手机底部三键导航应用是否被违规删除
    """
    THREE_BUTTON_NAV_PACKAGE = "com.android.internal.systemui.navbar.threebutton"

    logging.info("开始测试: testRequired3ButtonNavMode")

    # 1. 检查是否安装了系统导航模式
    if not is_package_exist(device_serial, THREE_BUTTON_NAV_PACKAGE):
        pytest.fail(f"系统三键导航应用{THREE_BUTTON_NAV_PACKAGE}未安装，测试失败")
    
    logging.info(f"系统三键导航应用已安装: {THREE_BUTTON_NAV_PACKAGE}")
    
    



@pytest.mark.require_android_version_min(10)
def test_RequiredGesturalNavMode(device_serial):
    """
    # GMS-8.4-003
    # DESCRIPTION: [GTS]GtsSystemNavigationTestCases-com.google.android.systemui.gts.SystemNavigationModeTest#testRequiredGesturalNavMode
    测试系统手势导航模式，测试手机底部手势导航应用是否被违规删除
    """
    GESTURAL_NAV_PACKAGE = "com.android.internal.systemui.navbar.gestural"

    logging.info("开始测试: testRequiredGesturalNavMode")

    # 1. 检查是否安装了系统导航模式
    if not is_package_exist(device_serial, GESTURAL_NAV_PACKAGE):
        pytest.fail(f"系统手势导航应用{GESTURAL_NAV_PACKAGE}未安装，测试失败")
    
    logging.info(f"系统手势导航应用已安装: {GESTURAL_NAV_PACKAGE}")





