import time
from uiautomator2 import Device

from tests.dzppt.aw.dzppt_u2d_helper import DzpptU2DTestHelper
from tpytest.scheme.scheme_test_env import get_scheme_env, SchemeTestEnv

scheme_env: SchemeTestEnv = get_scheme_env().get_instance()
u2d_helper: DzpptU2DTestHelper = scheme_env.u2d_helper
u2d: Device = scheme_env.u2d
logger = scheme_env.logger


####################################   wifi   #########################################

def wifi_aging(stop_event=None):
    """
    WIFI老化测试
    """
    bluetooth_config = scheme_env.user_config.configured_config_dict["hardware_aging"]["wifi"]
    wifi_switch_seconds = bluetooth_config["switch_duration_seconds"]
    test_time_seconds = bluetooth_config["test_time_seconds"]
    is_open_operation = True  # 记录下一次的操作
    start_time = time.time()
    logger.info(f'[WIFI老化测试 开始]', ext_event=True)
    while time.time() - start_time < test_time_seconds:
        is_open_operation = not is_open_operation
        logger.info(f'[WIFI老化测试 {"打开" if is_open_operation else "关闭"}]', ext_event=True)
        u2d_helper.open_close_wifi(is_open_operation)
        if stop_event:
            if stop_event.wait(wifi_switch_seconds):
                break
        else:
            time.sleep(wifi_switch_seconds)
    logger.info(f'[WIFI老化测试 结束]', ext_event=True)


####################################   bluetooth   #########################################
def bluetooth_aging(stop_event=None):
    """
    蓝牙老化测试
    """
    bluetooth_config = scheme_env.user_config.configured_config_dict["hardware_aging"]["bluetooth"]
    bluetooth_switch_seconds = bluetooth_config["switch_duration_seconds"]
    test_time_seconds = bluetooth_config["test_time_seconds"]
    is_open_operation = True  # 记录下一次的操作
    start_time = time.time()
    logger.info(f'[蓝牙老化测试 开始]', ext_event=True)
    while time.time() - start_time < test_time_seconds:
        is_open_operation = not is_open_operation
        logger.info(f'[蓝牙老化测试 {"打开" if is_open_operation else "关闭"}]', ext_event=True)
        u2d_helper.open_close_bluetooth(is_open_operation)
        if stop_event:
            if stop_event.wait(bluetooth_switch_seconds):
                break
        else:
            time.sleep(bluetooth_switch_seconds)
    logger.info(f'[蓝牙老化测试 结束]', ext_event=True)


####################################   gps   #########################################
def gps_aging(stop_event=None):
    """GPS老化测试"""
    logger.info(f'[运行GPS老化前，关闭所有的后台应用]', ext_event=True)
    u2d_helper.stop_visible_recent_tasks(False)
    gps_config = scheme_env.user_config.configured_config_dict["hardware_aging"]["gps"]
    location_switch_seconds = gps_config["switch_duration_seconds"]
    test_time_seconds = gps_config["test_time_seconds"]
    is_open_operation = True  # 记录下一次的操作
    start_time = time.time()
    logger.info(f'[GPS老化测试 开始]', ext_event=True)
    while time.time() - start_time < test_time_seconds:
        is_open_operation = not is_open_operation
        logger.info(f'[GPS老化测试 {"打开" if is_open_operation else "关闭"}]', ext_event=True)
        u2d_helper.open_close_location_service(is_open_operation)
        if stop_event:
            if stop_event.wait(location_switch_seconds):
                break
        else:
            time.sleep(location_switch_seconds)
    logger.info(f'[GPS老化测试 结束]', ext_event=True)


####################################   nfc   #########################################
def nfc_aging(stop_event=None):
    """GPS老化测试"""
    logger.info(f'[运行nfc老化前，关闭所有的后台应用]', ext_event=True)
    u2d_helper.stop_visible_recent_tasks(False)
    nfc_config = scheme_env.user_config.configured_config_dict["hardware_aging"]["nfc"]
    location_switch_seconds = nfc_config["switch_duration_seconds"]
    test_time_seconds = nfc_config["test_time_seconds"]
    is_open_operation = True  # 记录下一次的操作
    start_time = time.time()
    logger.info(f'[nfc老化测试 开始]', ext_event=True)
    while time.time() - start_time < test_time_seconds:
        is_open_operation = not is_open_operation
        logger.info(f'[nfc老化测试 {"打开" if is_open_operation else "关闭"}]', ext_event=True)
        u2d_helper.open_close_nfc(is_open_operation)
        if stop_event:
            if stop_event.wait(location_switch_seconds):
                break
        else:
            time.sleep(location_switch_seconds)
    logger.info(f'[nfc老化测试 结束]', ext_event=True)


####################################   flashlight   #########################################
def _get_flashlight_xpath_item(device: Device, max_retries=3):
    """
    获取闪光灯开关按钮
    :param device:
    :param max_retries: 最大重试次数
    :return:
    """
    for retry in range(max_retries):
        try:
            device.open_quick_settings()
            time.sleep(2)
            flashlight_element = device(description="Flashlight")

            try:
                if flashlight_element.exists:
                    return flashlight_element
            except Exception:
                continue

            if retry < max_retries - 1:  # 如果没找到，稍等一下再试
                time.sleep(2)
                device.press("back")  # 关闭通知面板
                time.sleep(1)

        except Exception as e:
            if retry < max_retries - 1:
                time.sleep(2)
            else:
                logger.error("获取闪光灯开关按钮出错")

    return None  # 如果所有重试都失败，返回None而不是无限递归


def _get_flashlight_status(device: Device):
    """
    获取闪光灯状态
    :param device:
    :return:
    """
    item = _get_flashlight_xpath_item(device)
    if item:
        return item, item.info["checked"]

    return None, None


def _open_flashlight(device: Device):
    '''
    打开闪光灯
    '''
    item, checked = _get_flashlight_status(device)
    if item and not checked:
        item.click()
        return True


def _close_flashlight(device: Device):
    '''
    关闭闪光灯
    '''
    item, checked = _get_flashlight_status(device)
    if item and checked:
        item.click()
        return True

def _toggle_flashlight(device: Device):
    """
    切换闪光灯状态（不关心当前状态，直接点一次按钮）
    """
    item = _get_flashlight_xpath_item(device)
    if item:
        logger.info("切换闪光灯状态（点击按钮）")
        item.click()
        time.sleep(0.5)
        device.press("back")
        return True
    else:
        logger.error("未找到闪光灯按钮")
        return False


def flashlight_aging(stop_event=None):
    """flashlight老化测试"""
    logger.info(f'[运行flashlight老化前，关闭所有的后台应用]', ext_event=True)
    u2d_helper.stop_visible_recent_tasks(False)
    flashlight_config = scheme_env.user_config.configured_config_dict["hardware_aging"]["flashlight"]
    location_switch_seconds = flashlight_config["switch_duration_seconds"]
    test_time_seconds = flashlight_config["test_time_seconds"]
    # is_open_operation = True  # 记录下一次的操作
    start_time = time.time()
    logger.info(f'[flashlight老化测试 开始]', ext_event=True)
    while time.time() - start_time < test_time_seconds:
        # is_open_operation = not is_open_operation
        logger.info(f'[flashlight老化测试 打开或关闭]', ext_event=True)
        _toggle_flashlight(u2d)
        if stop_event:
            if stop_event.wait(location_switch_seconds):
                break
        else:
            time.sleep(location_switch_seconds)
    logger.info(f'[flashlight老化测试 结束]', ext_event=True)


