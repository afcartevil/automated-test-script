# -*- coding: utf-8 -*-
import pytest
import logging

from data.res_list import CARRIAR_MARKETS
from src.utils.adb.adb_utils import (
    adb_shell,
    is_package_exist,
    get_feature,
)

def test_androidAutoHasNotificationAccess(device_serial):
    """
    # Case: androidAutoHasNotificationAccess
    # ID: KJ8SH339-342
    # DESCRIPTION: [GTS]GtsAndroidAutoDeviceTestCases-com.google.android.androidauto.gts.AndroidAutoTest#androidAutoHasNotificationAccess
    """
    # 定义 Android Auto 的包名
    gearhead_package = "com.google.android.projection.gearhead"
    
    logging.info("开始测试: androidAutoHasNotificationAccess")
    
    # 1. 检查是否安装了 Android Auto
    if not is_package_exist(device_serial, gearhead_package):
        pytest.fail("Android Auto 未安装，测试失败")
    
    logging.info(f"Android Auto 已安装: {gearhead_package}")
    
    # 2. 检查是否为国行版本（通过系统特性 cn.google.services 判断）
    cn_google_feature = get_feature(device_serial, "cn.google.services")
    
    if cn_google_feature:
        pytest.skip("当前设备为国行版本 (CN Build)，跳过测试")
    else:
        logging.info(f"当前设备为非国行版本 (Non-CN Build)，继续测试")
    
    # 3. 获取已启用的通知监听器列表
    result = adb_shell(device_serial, "settings get secure enabled_notification_listeners")
    
    if not result["success"] or not result["output"] or result["output"] == "null":
        enabled_packages = set()
        logging.warning("未获取到已启用的通知监听器列表")
    else:
        # 输出格式通常是 pkg1/cls1:pkg2/cls2...
        listeners = result["output"].split(":")
        enabled_packages = set()
        for listener in listeners:
            if "/" in listener:
                # 提取包名部分（斜杠前面的部分）
                pkg_name = listener.split("/")[0]
                enabled_packages.add(pkg_name)
    
    logging.info(f"当前拥有通知使用权的包名: {enabled_packages}")
    
    # 4. 断言验证
    if gearhead_package in enabled_packages:
        logging.info("测试通过 (PASS): Android Auto 已获得通知使用权！")
    else:
        pytest.fail("Android Auto 未获得通知使用权！")

