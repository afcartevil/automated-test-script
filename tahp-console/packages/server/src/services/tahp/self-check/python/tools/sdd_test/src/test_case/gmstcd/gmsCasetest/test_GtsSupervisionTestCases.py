# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    adb_shell,
    get_feature,
    is_package_exist,
    get_device_android_version_sdk_full,
)


@pytest.mark.require_android_version_min(16)
def test_SupervisionAppVersion(device_serial):
    """
    # GMS-7.1-010.004
    # DESCRIPTION: [GTS]GtsSupervisionTestCases-com.google.android.supervision.gts.SupervisionTest#testSupervisionAppVersion
    测试家长控制应用版本，在Android 16 QPR2之后系统必须预装家长控制应用com.google.android.gms.supervision，并且不能预装stub版
    """
    SYSTEM_SUPERVISION_PACKAGE = "com.google.android.gms.supervision"
    
    logging.info("开始测试: test_SupervisionAppVersion")
    
    # 1. 检查 Android SDK 版本是否大于 36（Android 16 QPR2）
    logging.info("步骤 1: 检查 Android SDK 版本")
    android_version_sdk_full = get_device_android_version_sdk_full(device_serial)
    
    if not android_version_sdk_full:
        pytest.fail("无法获取设备 Android SDK 版本")
    
    try:
        sdk_version = float(android_version_sdk_full)
    except (ValueError, TypeError):
        pytest.fail(f"Android SDK 版本格式错误: {android_version_sdk_full}")
    
    if sdk_version <= 36:
        pytest.skip(f"测试设备 API 小于等于 36 (当前: {sdk_version})，跳过测试")
    
    logging.info(f"当前设备 SDK 版本 {sdk_version} > 36，继续测试")
    
    # 2. 检查是否安装了家长控制应用
    logging.info("步骤 2: 检查是否安装了家长控制应用")
    if not is_package_exist(device_serial, SYSTEM_SUPERVISION_PACKAGE):
        pytest.fail(f"Android 16 QPR2+ 设备必须预装家长控制应用 {SYSTEM_SUPERVISION_PACKAGE}")
    
    logging.info(f"已安装家长控制应用 {SYSTEM_SUPERVISION_PACKAGE}")
    
    # 3. 检查是否具有 WELLBEING 特性
    logging.info("步骤 3: 检查是否具有 WELLBEING 特性")
    wellbeing_feature = get_feature(device_serial, "com.google.android.feature.WELLBEING")
    
    if not wellbeing_feature:
        logging.info("当前设备未定义 WELLBEING 特性，跳过测试")
        pytest.skip("未定义 com.google.android.feature.WELLBEING，跳过测试")
    
    logging.info("当前设备具有feature： com.google.android.feature.WELLBEING")
    
    # 4. 获取家长控制应用版本信息
    logging.info("步骤 4: 获取家长控制应用版本信息")
    version_result = adb_shell(
        device_serial,
        f"dumpsys package {SYSTEM_SUPERVISION_PACKAGE} | grep versionName"
    )
    
    if not version_result["success"]:
        pytest.fail(f"无法获取家长控制应用版本信息: {version_result.get('error')}")
    
    output_str = version_result.get("output", "").strip()
    
    if not output_str:
        pytest.fail("家长控制应用版本信息为空")
    
    # 5. 检查是否为 stub 版本
    logging.info("步骤 5: 检查是否为 stub 版本")
    
    if "stub" in output_str.lower():
        pytest.fail(f"家长控制应用不能是 stub 版本，当前版本: {output_str}")
    
    # 6. 提取并显示版本号
    clean_version = output_str.replace("versionName=", "").strip()
    logging.info(f"测试通过 (PASS): 家长控制应用版本为 {clean_version}")



@pytest.mark.require_android_version_min(10)
def test_IsDefaultSupervisionComponent(device_serial):
    """
    # GMS-7.1-010.003
    # DESCRIPTION: [GTS]GtsSupervisionTestCases-com.google.android.supervision.gts.SupervisionTest#testIsDefaultSupervisionComponent
    检查config_defaultSupervisionProfileOwnerComponent是否默认为com.google.android.gms/.kids.account.receiver.ProfileOwnerReceiver
    """
    EXPECTED_COMPONENT = "com.google.android.gms/.kids.account.receiver.ProfileOwnerReceiver"

    logging.info("开始测试: test_IsDefaultSupervisionComponent")

    # 1. 获取配置的资源值
    logging.info("步骤 1: 获取 config_defaultSupervisionProfileOwnerComponent 配置")
    result = adb_shell(
        device_serial,
        "cmd overlay lookup android android:string/config_defaultSupervisionProfileOwnerComponent"
    )

    if not result["success"]:
        pytest.fail(f"获取配置项失败: {result.get('error')}")

    actual_component = result.get("output", "").strip()

    if not actual_component:
        pytest.fail("未找到 config_defaultSupervisionProfileOwnerComponent 配置项，请检查设备config_defaultSupervisionProfileOwnerComponent配置")

    # 2. 断言比对
    logging.info("步骤 2: 验证配置值是否正确")

    if actual_component == EXPECTED_COMPONENT:
        logging.info(f"测试通过 (PASS): 家长控制组件配置正确: {actual_component}")
    else:
        logging.error(f"测试失败 (FAIL): 家长控制组件配置不正确")
        logging.error(f"  期望值: {EXPECTED_COMPONENT}")
        logging.error(f"  实际值: {actual_component}")
        pytest.fail(f"家长控制组件配置错误，期望 {EXPECTED_COMPONENT}，实际 {actual_component}")






