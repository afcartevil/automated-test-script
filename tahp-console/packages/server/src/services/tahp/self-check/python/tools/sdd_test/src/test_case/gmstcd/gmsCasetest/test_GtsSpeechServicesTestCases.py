# -*- coding: utf-8 -*-
import re
import pytest
import logging

from src.utils.adb.adb_utils import (
    adb_shell,
    get_feature,
    is_GO_device,
    is_package_exist,
    get_dumpsys_package,
)


def _check_cn_build_and_skip(device_serial):
    """
    检查是否为国行版本，如果是则跳过测试
    Args:
        device_serial: 设备序列号
    Returns:
        bool: True 表示是国行版本（已跳过），False 表示非国行版本（继续测试）
    """
    cn_google_feature = get_feature(device_serial, "cn.google.services")

    if cn_google_feature:
        pytest.skip("当前设备为国行版本 (CN Build)，跳过测试")
    else:
        logging.info("当前设备为非国行版本 (Non-CN Build)，继续测试")
        return False


def _get_device_user_ids(device_serial):
    """
    获取设备上的所有用户 ID 列表
    Args:
        device_serial: 设备序列号
    Returns:
        list: 用户 ID 列表
    """
    users_result = adb_shell(device_serial, "pm list users")

    if not users_result["success"]:
        pytest.fail("无法获取用户列表，请检查设备连接状态")

    # 解析输出，例如 "UserInfo{0:Owner:13}" 提取出数字 0
    user_ids = re.findall(r'UserInfo\{(\d+):', users_result["output"])

    if not user_ids:
        pytest.fail("无法解析用户列表，设备可能异常")

    logging.info(f"发现 {len(user_ids)} 个用户配置: {', '.join(user_ids)}")
    return user_ids


@pytest.mark.require_android_version_min(12)
def test_DeviceHasCorrectSpeechApkByDeviceLevel(device_serial):
    """
    # GMSX-6.2-004
    # DESCRIPTION: [GTS]GtsSpeechServicesTestCases-com.google.android.speech.gts.SpeechServicesTestCases#testDeviceHasCorrectSpeechApkByDeviceLevel
    测试设备是否有正确的语音服务APK
    """
    package_name = "com.google.android.tts"
    service_name = "com.google.android.apps.speech.tts.googletts.service.GoogleTTSRecognitionService"

    logging.info("开始测试: test_DeviceHasCorrectSpeechApkByDeviceLevel")

    # 0. 检查是否为国行版本
    _check_cn_build_and_skip(device_serial)

    # 1. 检查是否安装了该包
    logging.info(f"步骤 1: 检查设备是否安装了 {package_name}")
    if not is_package_exist(device_serial, package_name):
        pytest.fail(f"设备未安装包 {package_name} (核心服务缺失，请检查预装情况)")
    logging.info(f"{package_name} 已安装")

    # 2. 检查包内是否注册了目标服务
    logging.info(f"步骤 2: 检查 {package_name} 是否注册了服务: {service_name}")
    service_dump = get_dumpsys_package(device_serial, package_name, service_name)

    # 3. 断言比对
    if service_dump and service_name in service_dump:
        logging.info(f"测试通过 (PASS): 找到了 {service_name}")
    else:
        logging.error(f"测试失败 (FAIL): 未找到目标服务 {service_name}")
        pytest.fail(f"未在 {package_name} 中找到目标服务 {service_name}，请检查 APK 预装是否正确")




@pytest.mark.require_android_version_min(12)
def test_DeviceHasSpeechServicesAsDefaultRecognizer(device_serial):
    """
    # GMS-7.X-001
    # DESCRIPTION: [GTS]GtsSpeechServicesTestCases-com.google.android.speech.gts.SpeechServicesTestCases#testDeviceHasSpeechServicesAsDefaultRecognizer
    测试设备预装的语音apk是否有语音服务作为默认识别器
    """
    expected_service = "com.google.android.tts/com.google.android.apps.speech.tts.googletts.service.GoogleTTSRecognitionService"

    logging.info("开始测试: test_DeviceHasSpeechServicesAsDefaultRecognizer")

    # 0. 检查是否为国行版本
    _check_cn_build_and_skip(device_serial)

    # 1. 获取设备上的所有用户 ID
    logging.info("步骤 1: 获取设备多用户列表")
    user_ids = _get_device_user_ids(device_serial)

    # 2. 遍历每个用户，检查其默认语音识别引擎设置
    logging.info("步骤 2: 检查每个用户的默认语音识别服务配置")
    all_passed = True

    for uid in user_ids:
        logging.info(f"检查用户 [User {uid}] 的语音识别设置...")

        # 使用 settings 命令读取对应用户的 voice_recognition_service
        cmd = f"settings --user {uid} get secure voice_recognition_service"
        current_service_result = adb_shell(device_serial, cmd)

        if not current_service_result["success"]:
            logging.error(f"用户 [User {uid}] 获取设置失败")
            all_passed = False
            continue

        current_service = current_service_result["output"]

        if current_service == expected_service:
            logging.info(f"用户 [User {uid}] 验证通过 (PASS)")
        else:
            logging.error(f"用户 [User {uid}] 验证失败 (FAIL)")
            logging.error(f"  期望服务: {expected_service}")
            actual_service = current_service if current_service != 'null' else '未设置(null)'
            logging.error(f"  实际服务: {actual_service}")
            all_passed = False

    # 3. 输出最终结论
    if all_passed:
        logging.info("测试通过 (PASS): 所有用户已正确配置 Google 语音服务为默认识别器")
    else:
        logging.error("测试失败 (FAIL): 存在未正确配置 Google 语音服务的用户")
        pytest.fail("存在未正确配置 Google 语音服务的用户")


@pytest.mark.require_android_version_min(12)
def test_ProvidedIMEEnabledByDefault(device_serial):
    """
    # GMS-X.X-XXX
    # DESCRIPTION: [GTS]GtsSpeechServicesTestCases-com.google.android.speech.gts.SpeechServicesTestCases#testProvidedIMEEnabledByDefault
    测试设备是否默认启用了谷歌语音输入法
    """
    expected_ime = "com.google.android.tts"

    logging.info("开始测试: test_ProvidedIMEEnabledByDefault")

    # 0. 检查是否为国行版本
    _check_cn_build_and_skip(device_serial)

    # 1. 获取设备已启用的输入法列表
    logging.info("步骤 1: 获取设备已启用的输入法列表")
    enabled_imes = adb_shell(device_serial, "settings get secure enabled_input_methods")

    if not enabled_imes["success"]:
        pytest.fail("无法获取已启用的输入法列表，请检查设备连接状态")

    # 2. 断言比对
    if expected_ime in enabled_imes["output"]:
        logging.info(f"测试通过 (PASS): 设备已默认启用 Google 语音输入法 {expected_ime}")
    else:
        logging.error(f"测试失败 (FAIL): 设备未默认启用 Google 语音输入法 {expected_ime}")
        pytest.fail("设备未默认启用 Google 语音输入法")



@pytest.mark.require_android_version_min(12)
def test_GoDeviceHasCorrectApplicationsInstalled(device_serial):
    """
    # GMS-10.2-001 / GMSX-6.2-004 
    # DESCRIPTION: [GTS]GtsSpeechServicesTestCases-com.google.android.speech.gts.SpeechServicesTestCases#testGoDeviceHasCorrectApplicationsInstalled
    测试 GO 设备是否安装了正确的 TTS 应用
    """
    logging.info("开始测试: test_GoDeviceHasCorrectApplicationsInstalled")

    # 0. 检查是否为 GO 设备
    logging.info("步骤 0: 检查设备类型")
    if is_GO_device(device_serial):
        logging.info("当前设备为 GO device，继续测试")
    else:
        pytest.skip("当前设备为 non-GO device，跳过测试")

    # 1. 检查是否安装了 com.google.android.apps.speechservices（不应安装）
    logging.info("步骤 1: 检查是否错误安装了 com.google.android.apps.speechservices")
    if is_package_exist(device_serial, "com.google.android.apps.speechservices"):
        pytest.fail("GO 设备不应安装 com.google.android.apps.speechservices")
    logging.info("未安装 com.google.android.apps.speechservices (符合预期)")

    # 2. 检查是否安装了 com.google.android.tts（必须安装）
    logging.info("步骤 2: 检查是否安装了 com.google.android.tts")
    if not is_package_exist(device_serial, "com.google.android.tts"):
        pytest.fail("GO 设备必须安装 com.google.android.tts")
    logging.info("已安装 com.google.android.tts")


@pytest.mark.require_android_version_min(12)
def test_EEADevicesHaveCorrectPackages(device_serial):
    """
    # GMS-X.X-XXX
    # DESCRIPTION: [GTS]GtsSpeechServicesTestCases-com.google.android.speech.gts.SpeechServicesTestCases#testEEADevicesHaveCorrectPackages
    测试 EEA（欧洲经济区）版本的 Android 设备是否按照 Google 的区域政策预装了正确的应用包组合
    """
    logging.info("开始测试: test_EEADevicesHaveCorrectPackages")

    # 0. 检查是否为 GO 设备（GO 设备跳过）
    logging.info("步骤 0: 检查设备类型")
    if is_GO_device(device_serial):
        pytest.skip("当前设备为 GO device，跳过测试")
    logging.info("当前设备为 non-GO device，继续测试")

    # 1. 检查是否为国行版本（国行设备跳过）
    _check_cn_build_and_skip(device_serial)

    # 2. 检查是否为 EEA 设备
    logging.info("步骤 1: 检查是否为 EEA_DEVICE")
    eea_feature = get_feature(device_serial, "com.google.android.feature.EEA_DEVICE")
    if not eea_feature:
        pytest.skip("非 EEA_DEVICE，跳过测试")
    logging.info("当前设备是 EEA_DEVICE")

    # 3. 检查包安装逻辑
    has_agsa = is_package_exist(device_serial, "com.google.android.googlequicksearchbox")

    logging.info("步骤 2: 检查 AGSA 和 ActionsService 的安装情况")
    if has_agsa:
        # 预装了 AGSA
        logging.info("已预装 AGSA (com.google.android.googlequicksearchbox)")

        # 检查不应安装的包
        if is_package_exist(device_serial, "com.google.android.apps.actionsservice"):
            pytest.fail("预装 AGSA 的设备不应安装 com.google.android.apps.actionsservice")
        logging.info("未安装 com.google.android.apps.actionsservice (符合预期)")

        if is_package_exist(device_serial, "com.google.android.apps.speechservices"):
            pytest.fail("预装 AGSA 的设备不应安装 com.google.android.apps.speechservices")
        logging.info("未安装 com.google.android.apps.speechservices (符合预期)")
    else:
        # 未预装 AGSA，必须安装 ActionsService
        logging.info("未预装 AGSA，检查是否安装了 ActionsService")
        if not is_package_exist(device_serial, "com.google.android.apps.actionsservice"):
            pytest.fail("未预装 AGSA 的设备必须安装 com.google.android.apps.actionsservice")
        logging.info("已安装 com.google.android.apps.actionsservice (符合预期)")

    # 4. 检查 TTS 是否安装（必须安装）
    logging.info("步骤 3: 检查是否安装了 com.google.android.tts")
    if not is_package_exist(device_serial, "com.google.android.tts"):
        pytest.fail("EEA 设备必须安装 com.google.android.tts")
    logging.info("已安装 com.google.android.tts")

    logging.info("测试通过 (PASS): EEA 设备包安装检查全部通过")

