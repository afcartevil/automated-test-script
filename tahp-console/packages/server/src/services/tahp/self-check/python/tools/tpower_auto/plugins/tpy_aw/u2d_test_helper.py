import os
import re
import subprocess
import threading
import time
from datetime import datetime
from typing import Union, List, Optional, cast, Type, TypeVar
from functools import cached_property

import uiautomator2
from uiautomator2 import XPathElementNotFoundError
import random

from powertrde import env
from powertrde.env import ADB_EXE, TOOLS_DIR
from powertrde.framework.logs_protocol import logs_p
from powertrde.framework.tran_logger import t_log
from powertrde.framework.uni_device import UniDevice
from powertrde.utils import misc_utils
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from powertrde.utils.u2_extends.base_u2d_test_helper import BaseU2DTestHelper
from tpy_aw import aw_registry
from tpy_aw.u2d_helper_constants import U2DHelperConstants
from tpytest.aw_framework.aw_base import AwBase
from typing import Tuple

T = TypeVar('T')


class U2DTestHelper(BaseU2DTestHelper, U2DHelperConstants, AwBase):
    aw_category = 'u2_helper'
    aw_name = ''

    def __init__(self, u2d_or_device_id: Union[uiautomator2.Device, str]):
        super().__init__(u2d_or_device_id)
        self.known_country_codes = {"86", "254", "92", "63", "62", "234"}
        self._watcher_register = None
        self._bound_und = None

    @cached_property
    def phone_os_info(self):
        _cached_os_info = env.get_user_env_arg('device_os_info')
        if _cached_os_info and env.get_user_env_arg('device_sn') == self.device_real_sn:
            return _cached_os_info
        assert self.device_id, 'Device ID must not be empty!'
        return aw_registry.detect_os_info(self.device_id)

    @property
    def und_u2(self):
        from tpy_aw.uni_device_u2d import UniDeviceU2D
        if self.is_wifi_adb_mode:
            if not self._wifi_und_u2:
                self._wifi_und_u2 = UniDeviceU2D(self.u2d)
            return self._wifi_und_u2
        else:
            if not self._und_u2:
                self._und_u2 = UniDeviceU2D(self.u2d)
            return self._und_u2

    @property
    def und(self):
        if self._bound_und is None:
            return self.und_u2
        return self._bound_und

    def bind_und(self, und: Optional[UniDevice]):
        self._bound_und = und

    def get_bound_und(self):
        return self._bound_und

    def get_aw_app_variant_key(self, name: str, default_value=''):
        _app_static_info_class = env.load_member('tpytest_extends.scheme.apps_static_info.AppsStaticInfo')
        if not _app_static_info_class:
            return ''
        get_app_info_method = _app_static_info_class.get_app_info_no_raise
        if get_app_info_method:
            app_info = get_app_info_method(name, self.device_real_sn)
            if not app_info:
                return ''
            key = app_info.get_closest_variant_key()
            return key
        return ''

    @property
    def is_sprd(self):
        return adb.is_sprd(self.device_id)

    @property
    def is_mtk(self):
        return adb.is_mtk(self.device_id)

    @property
    def is_qcom(self):
        return adb.is_qcom(self.device_id)

    @property
    def tran_cpu_platform(self):
        _tran_cpu_platform = 'other'
        if adb.is_mtk(self.device_id):
            _tran_cpu_platform = 'mtk'
        elif adb.is_sprd(self.device_id):
            _tran_cpu_platform = 'sprd'
        elif adb.is_qcom(self.device_id):
            _tran_cpu_platform = 'qcom'
        return _tran_cpu_platform

    def get_app_aw(self, app_name: str, variant: Optional[str] = None, no_raise: bool = False):
        try:
            from tpy_aw.aw_registry import get_aw_app
            return get_aw_app(self, app_name, variant)
        except Exception:
            if not no_raise:
                raise
        return None

    def get_casted_app_aw(self, cast_type: Type[T], app_name: Optional[str] = None, variant: Optional[str] = None,
                          no_raise: bool = False) -> Optional[T]:
        return cast(cast_type, self.get_app_aw(app_name or cast_type.aw_name, variant, no_raise))

    def get_feature_aw(self, ft_name: str, variant: Optional[str] = None, no_raise: bool = False):
        try:
            from tpy_aw.aw_registry import get_aw_feature
            return get_aw_feature(self, ft_name, variant)
        except Exception:
            if not no_raise:
                raise
        return None

    def get_casted_feature_aw(self, cast_type: Type[T], ft_name: Optional[str] = None, variant: Optional[str] = None,
                              no_raise: bool = False) -> Optional[T]:
        return cast(cast_type, self.get_feature_aw(ft_name or cast_type.aw_name, variant, no_raise))

    def input_text_after_wait(self, text):
        if adb.is_sprd(self.device_id):
            time.sleep(1)

        u2utils.input_text(self.u2d, text)

    def adjust_phone_volume(self, choose):
        """
        adb调整手机音量
        :param choose: up：增加, down: 减小, mute: 静音
        """
        if choose.lower() == "up":
            num = "24"
        elif choose.lower() == "down":
            num = "25"
        elif choose.lower() == "mute":
            num = "164"
        else:
            raise Exception('Volume error key')

        adb.exec_cmd(self.device_id, f'input keyevent {num}')

    def assert_device_connected(self):
        assert self.device_id, 'Phone device id must not be empty!'
        assert self.is_device_connected, f"Phone device '{self.device_id}' is not connected!"

    @property
    def is_phone_monitor_app_installed(self):
        self.assert_device_connected()
        return adb.package_is_installed(self.device_id, self.PHONE_MONITOR_APP_PACKAGE)

    def try_launch_phone_monitor_app(self):
        try:
            assert self.is_phone_monitor_app_installed, 'Phone monitor apk is not installed!'
            self.start_activity(self.PHONE_MONITOR_APP_MAIN_ACTIVITY)
        except Exception as e:
            t_log.warning(f'Start phone monitor activity failed, details: {e}')

    def clear_recent_apps_by_ui(self, retain_phone_monitor_app: bool = False):
        from tpy_aw.aw_apps.aw_app_camera.aw_app_camera import AwAppCamera
        aw_camera = self.get_casted_app_aw(AwAppCamera)
        need_retain_phone_monitor = (retain_phone_monitor_app and adb.package_is_installed(self.device_id,
                                                                                           self.PHONE_MONITOR_APP_PACKAGE))
        if need_retain_phone_monitor:
            self.press_home_key(2)
            time.sleep(0.5)
            self.start_activity(self.PHONE_MONITOR_APP_MAIN_ACTIVITY)
            time.sleep(1)
        self.start_launcher_activity(aw_camera.default_app_package)
        time.sleep(2)
        self.press_app_switch_key()
        time.sleep(1)
        adb.tap_on_screen_by_percent(self.device_id, 0.5, 0.87)
        time.sleep(2)
        if need_retain_phone_monitor:
            time.sleep(0.5)
            self.press_app_switch_key()
            time.sleep(1)
            self.und_u2.swipe_direction('up', speed=350)
            self.press_back_key()
            time.sleep(1)

    def end_system_phone_call(self):
        if adb.is_phone_calling(self.device_id):
            adb.press_end_call_key(self.device_id)

    def press_key(self, keycode):
        adb.press_key(self.device_id, keycode)

    def set_fake_battery_level(self, level):
        adb.exec_cmd(self.device_id, f'dumpsys battery set level {level}')
        adb.exec_cmd(self.device_id, f'dumpsys battery unplug')

    def reset_fake_battery_level(self):
        adb.reset_battery_status(self.device_id)

    def set_fake_usb_connection(self, connect: bool):
        adb.exec_cmd(self.device_id, f'dumpsys battery set usb {1 if connect else 0}')

    def get_battery_level(self):
        result = adb.exec_cmd(self.device_id, 'dumpsys battery | grep level')

        if result:
            level = result[0].strip()
            level = level.split('level')[-1].replace('：', ':').split(':')[-1].strip()

            return int(level)
        raise Exception('Can not get battery level.')

    def assert_app_installed(self, app_package: str, app_hint_name: str = ''):
        if not adb.package_is_installed(self.device_id, app_package):
            raise Exception(f"{app_hint_name if app_hint_name else app_package} is not installed!")

    def is_app_installed(self, app_package: str):
        return adb.package_is_installed(self.device_id, app_package)

    def get_foreground_package(self):
        """获取正在前台活跃的包名"""
        return adb.get_foreground_package(self.device_id)

    def get_foreground_activity(self):
        """获取正在前台活跃的Activity"""
        return adb.get_foreground_activity(self.device_id)

    @property
    def is_now_in_desktop(self):
        """获取当前是否正处于桌面"""
        now_package = self.get_foreground_package()
        try:
            return 'launcher' in now_package.split('.')[-1].lower()
        except Exception:
            return False

    @property
    def is_screen_on_and_unlocked(self):
        """设备是否亮屏并且已解锁"""
        return adb.is_screen_on_desktop(self.device_id)

    def open_app(self, app_package: str, raise_exception_on_fail=True):
        adb.start_launcher_activity(self.device_id, app_package, raise_exception_on_fail)

    def open_app_by_monkey(self, app_package: str, raise_exception_on_fail=True):
        adb.launch_app(self.device_id, app_package, raise_exception=raise_exception_on_fail)

    def search_app_from_desktop_via_ui(self, app_icon_name: str):
        """
        在桌面找到相应app图标名称的桌面页面并停留
        returns: 是否找到app所在页面
        """
        if self.is_now_in_desktop:
            if self.u2d.xpath(f'//*[@text="{app_icon_name}" or @text="● {app_icon_name}"]').exists:
                return True
            self.press_home_key(times=1)
        else:
            self.press_home_key(times=3)

        time.sleep(0.5)
        for i in range(10):
            app_icon = self.u2d.xpath(f'//*[@text="{app_icon_name}" or @text="● {app_icon_name}"]').wait(timeout=1)
            if app_icon:
                return True
            else:
                self.und_u2.swipe_direction('left', speed=350)
                time.sleep(1)
        return False

    def start_app_from_desktop_via_ui(self, app_icon_name: str):
        """
        在桌面找到相应app图标并进行点击打开
        找不到抛出异常
        """
        if not self.search_app_from_desktop_via_ui(app_icon_name):
            raise Exception(f'Not found APP "{app_icon_name}" in desktop!')
        self.u2d.xpath(f'//*[@text="{app_icon_name}" or @text="● {app_icon_name}"]').click(timeout=1)

    def change_app_from_recent(self, app_icon_name, include_press_recent=True):
        if include_press_recent:
            self.press_recent_key()
            time.sleep(2)
        self.u2d.swipe(0.8, 0.5, 0.2, 0.5)
        click_bool = False
        for i in range(5):
            time.sleep(2)
            app = self.u2d.xpath(f'//*[@text="{app_icon_name}" or @text="● {app_icon_name}"]')
            if app.exists:
                self.u2d.click(0.5, 0.5)
                click_bool = True
                break
            self.u2d.swipe(0.2, 0.5, 0.8, 0.5)
        if not click_bool:
            raise Exception(f'Did not find {app_icon_name} in the recent')

    def search_index_of_app(self, app_name, is_package=False):
        """
        只支持前4个
        """
        self.press_home_key(times=2)
        self.u2d.swipe(0.5, 0.8, 0.5, 0.2)
        time.sleep(1)
        self.u2d.xpath('//android.widget.EditText').click()
        time.sleep(1)
        u2utils.input_text(self.u2d, app_name)
        x = ((self.u2d.xpath(f'//*[@text="{app_name}"]').all()[1].center()[0] / self.u2d.window_size()[0]) / 0.25)
        # y = (self.u2d.xpath(f'//*[@text="{app_name}"]').center[1]/self.u2d.window_size()[1])
        return int(x) + 1

    def start_activity(self, full_activity_name: str, wait=True, flag=''):
        adb.start_activity(self.device_id, full_activity_name, wait, flag)

    def start_app_activity(self, app_package: str, relative_activity_name: str, wait=True, flag=''):
        adb.start_apk_activity(self.device_id, app_package, relative_activity_name, wait, flag)

    def start_launcher_activity(self, package: str, wait=True, flag=''):
        adb.start_launcher_activity(self.device_id, package, wait, flag)

    def grant_all_runtime_permissions(self, app_package_name: str):
        adb.grant_all_runtime_permissions(self.device_id, app_package_name)

    def dex2oat_transform_package_to_speed_profile(self, app_package_name: str):
        adb.dex2oat_transform_package_to_speed_profile(self.device_id, app_package_name)

    def get_launcher_activity(self, app_package_name: str):
        return adb.get_launcher_activity(self.device_id, app_package_name)

    def stop_app(self, app_package: str):
        adb.stop_app(self.device_id, app_package)

    def start_app(self, app_package: str, raise_exception_on_fail=True):
        self.open_app(app_package, raise_exception_on_fail)

    def restart_app(self, app_package: str):
        self.stop_app(app_package)
        time.sleep(0.5)
        self.open_app(app_package)

    def restart_app_by_monkey(self, app_package: str):
        self.stop_app(app_package)
        time.sleep(0.5)
        self.open_app_by_monkey(app_package)

    def restart_settings_activity(self):
        adb.start_settings_activity(self.device_id, is_restart=True)

    def stop_settings(self):
        self.stop_app(adb.ANDROID_SETTINGS_PACKAGE)

    def soft_stop_app(self, app_package: str):
        adb.soft_stop_app(self.device_id, app_package)

    def uninstall_app(self, app_package: str):
        adb.uninstall_apk(self.device_id, app_package)

    def reboot_and_wait_complete(self):
        adb.reboot_phone(self.device_id)
        time.sleep(10)
        try:
            adb.DISABLE_ADB_ERROR_OUTPUT = True
            for i in range(120):
                time.sleep(1)
                if adb.is_boot_completed(self.device_id):
                    time.sleep(5)
                    break
            else:
                raise Exception('Failed to complete the reboot within 120 seconds!')
        finally:
            adb.DISABLE_ADB_ERROR_OUTPUT = False

    def get_skin_or_battery_temperature(self):
        try:
            return adb.get_skin_temperature(self.device_id)
        except Exception:
            return adb.get_battery_temperature(self.device_id)

    def set_heads_up_notify_enabled(self, enabled):
        # 关闭所有弹窗
        enabled = (bool(enabled) and enabled != '0')
        adb.set_heads_up_notify_enabled(self.device_id, enabled)

    def set_aod_enabled(self, enabled):
        adb.set_aod_enabled(self.device_id, enabled)

    @property
    def is_aod_enabled(self):
        return adb.is_aod_enabled(self.device_id)

    def restore_keyboard_ime(self):
        adb.DISABLE_ADB_ERROR_OUTPUT = True
        adb.exec_cmd(self.device_id,
                     'ime set com.facemoji.lite.transsion/com.baidu.simeji.SimejiIME')
        adb.DISABLE_ADB_ERROR_OUTPUT = False
        adb.exec_cmd(self.device_id,
                     'ime set com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME')

    def check_to_install_unplug_sim_apk(self):
        # 检查UI版本拔卡APK是否已安装，如未安装，进行安装，如安装时发现文件不存在，抛出异常
        self.press_home_key(times=2)
        time.sleep(0.5)
        sim = self.check_app_position('SimUnplugTool', 2)
        if not sim:
            sim_tool_dir = os.path.join(TOOLS_DIR, 'sim')
            if adb.package_is_installed(self.device_id, 'com.transsion.mft'):
                adb.uninstall_apk(self.device_id, 'com.transsion.mft')
            if self.android_version >= 16:
                # Android 16 单独签名的拔卡工具
                adb.install_apk(self.device_id, os.path.join(sim_tool_dir, f"ui_sim_tool_os16.apk"))
            else:
                d_b = adb.device_brand(self.device_id)
                install_k_v = {'infinix': "ui_sim_tool_infinix", 'tecno': "ui_sim_tool_tecno",
                               'itel': "ui_sim_tool_itel"}
                adb.install_apk(self.device_id, os.path.join(sim_tool_dir, f"{install_k_v.get(d_b)}.apk"))
            assert adb.package_is_installed(self.device_id, 'com.transsion.mft'), "install mft fail"

    def unplug_sim(self, sim_index: int, use_mode: int = 1):
        """
        使用apk或者ui模式来拔除指定sim卡
        Args:
            sim_index: 需要拔除的sim卡序号，一般为1或2
            use_mode: 0 表示apk模式，1 表示ui模式
        """
        # if use_mode != 0:
        #     self.unplug_sim_via_ui(sim_index)
        # else:
        #     self.unplug_sim_via_apk(sim_index)
        self.unplug_sim_via_ui(sim_index)

    def unplug_sim_via_ui(self, sim_index: int):
        self.set_settings_sim_enabled(sim_index, False)

    def plug_sim_via_ui(self, sim_index: int):
        self.set_settings_sim_enabled(sim_index, True)

    def unplug_sim_via_apk(self, sim_index: int):
        # 通过UI版本拔卡APK拔除一张指定index的sim卡，U2D实现
        assert sim_index == 1 or sim_index == 2, "unplug arg error"
        if adb.is_mtk(self.device_id):
            self.check_to_install_unplug_sim_apk()
            self.u2d.app_start('com.transsion.mft', 'com.transsion.mft.MainActivity')
            time.sleep(2)
            UNPLUG_list = ['//*[@text="UNPLUG NO.1"]', '//*[@text="UNPLUG NO.2"]']
            self.u2d.xpath(UNPLUG_list[sim_index - 1]).click()
            for i in range(5):
                if not adb.get_sim_is_plugged(self.device_id, sim_index):
                    break
                time.sleep(3)
            self.u2d.app_stop('com.transsion.mft')
            assert not adb.get_sim_is_plugged(self.device_id, sim_index)
        else:  # 展锐pass
            pass

    def restore_sim(self, use_sim_index: int, use_mode: int = 1):
        """
        使用apk或者ui模式来恢复所有卡，并将打电话和流量的卡同时切换到use_sim_index的卡位
        Args:
            use_sim_index: 需要默认电话和流量使用的卡位，一般为1或2
            use_mode: 0 表示apk模式，1 表示ui模式
        """
        # if use_mode != 0:
        #     self.restore_sim_via_ui(use_sim_index)
        # else:
        #     self.restore_sim_via_apk(use_sim_index)
        # 永远使用UI方式
        self.restore_sim_via_ui(use_sim_index)

    def restore_sim_via_ui(self, use_sim_index: int):
        # 通过UI模拟操作的方式恢复所有sim卡，并将电话和流量卡均置为规定的index卡，如果index为0，则忽略通话+流量卡设定
        sim_count = self.get_sim_count()
        if sim_count < 2 or sim_count == self.get_enabled_sim_count():
            return
        self.screen_on_and_unlock()
        u2d = self.u2d
        self.restart_app('com.android.settings')
        self.wait_ui_obj('//*[contains(@text, "SIM")]', timeout=5, pre_wait=1)
        u2d.xpath('//*[contains(@text, "SIM")]').click()
        u2d.sleep(2)

        is_sprd = self.is_sprd

        if use_sim_index == 1:
            first_index = 0
            second_index = 1
        else:
            first_index = 1
            second_index = 0

        if self.android_version >= 16:
            sim_title_group_xpath = '//*[@resource-id="com.android.settings:id/title"]'
        else:
            sim_title_group_xpath = '//*[@resource-id="com.transsion.tele.settings:id/title"]'
        self.assert_wait_ui_obj(sim_title_group_xpath, timeout=10, post_wait=1)
        self.u2d.xpath(sim_title_group_xpath).all()[first_index].click()

        u2d.sleep(3)
        btn_enable = u2d.xpath('//*[@resource-id="android:id/switch_widget"]')
        if not btn_enable.info['checked']:
            btn_enable.click()
            if is_sprd:
                u2d.sleep(7)
                u2d.press('back')
            u2d.sleep(1)
        u2d.press('back')
        u2d.sleep(2)

        self.assert_wait_ui_obj(sim_title_group_xpath, timeout=5, post_wait=1)
        self.u2d.xpath(sim_title_group_xpath).all()[second_index].click()

        u2d.sleep(3)
        btn_enable = u2d.xpath('//*[@resource-id="android:id/switch_widget"]')
        if not btn_enable.info['checked']:
            btn_enable.click()
            if is_sprd:
                u2d.sleep(7)
                u2d.press('back')
        elif use_sim_index != 0:
            btn_enable.click()
            u2d.sleep(3)
            btn_enable.click()
            if is_sprd:
                u2d.sleep(7)
                u2d.press('back')
        u2d.sleep(1)
        self.stop_app('com.android.settings')

    @property
    def android_version(self) -> int:
        return int(adb.device_android_version(self.device_id))

    def restore_sim_via_apk(self, use_sim_index: int):
        # 通过拔卡APK恢复所有sim卡，并将电话和流量卡均置为规定的index卡，如果index为0，则忽略通话+流量卡设定
        if adb.is_mtk(self.device_id):
            self.check_to_install_unplug_sim_apk()
            self.u2d.app_start('com.transsion.mft', 'com.transsion.mft.MainActivity')
            time.sleep(2)
            self.u2d.xpath('//*[@text="  PLUG ALL  "]').click()
            time.sleep(2)

            if use_sim_index > 0:
                UNPLUG_list = ['//*[@text="UNPLUG NO.1"]', '//*[@text="UNPLUG NO.2"]']
                if use_sim_index == 1:
                    self.u2d.xpath(UNPLUG_list[1]).click()
                else:
                    self.u2d.xpath(UNPLUG_list[0]).click()
                time.sleep(1)
                self.u2d.xpath('//*[@text="  PLUG ALL  "]').click()
                time.sleep(2)

            time.sleep(3)
            self.u2d.app_stop('com.transsion.mft')
            # for i in range(5):
            #     if adb.get_sim_is_plugged(self.device_id, 1) or adb.get_sim_is_plugged(self.device_id, 2):
            #         break
            #     time.sleep(3)

            # 暂时不需要做assert，因为不知道有几张卡，有时候1张卡也在恢复
            # assert adb.get_sim_is_plugged(self.device_id, 1)
            # assert adb.get_sim_is_plugged(self.device_id, 2)
        else:  # 展锐pass
            pass

    def open_close_banana_vpn(self, is_open: bool, no_return_home: bool = False, node: str = '新加坡'):
        self.u2d.app_start('com.bananago.speed')
        time.sleep(2)
        for i in range(4):
            if not self.u2d.xpath('//*[@text="OK"]').exists:
                break
            self.u2d.xpath('//*[@text="OK"]').click()
            self.u2d.app_start('com.bananago.speed')
            time.sleep(1)
        if is_open:
            time.sleep(3)  # node需要时间加载
            if not self.u2d.xpath(f"//*[contains(@text, '{node}')]").exists:
                self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/BLTextView"]').click()
                for i in range(5):
                    self.u2d.swipe(0.5, 0.8, 0.5, 0.2)
                    time.sleep(1)
                    if self.u2d.xpath(f"//*[contains(@text, '{node}')]").exists:
                        self.u2d.xpath(f"//*[contains(@text, '{node}')]").click()
                        time.sleep(1)
                        break
            if not self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/ivStartAfterBg"]').exists:
                self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/svStart"]').click()
                if self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/tvCancel"]').exists:
                    self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/tvCancel"]').click()
                    time.sleep(3)
                    self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/svStart"]').click()
        else:
            if self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/ivStartAfterBg"]').exists:
                self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/svStart"]').click()

        if not no_return_home:
            self.u2d.click(0.5, 0.979)

    def open_close_linsoc_vpn(self, is_open: bool, no_return_home: bool = False, node: str = '曼谷1'):
        self.u2d.app_start('com.linsoc.android')
        time.sleep(2)
        self.u2d.xpath('//*[@text="应用程序" and @checked="false"]').click_exists(timeout=2)
        if is_open:
            for i in range(5):
                self.u2d.swipe(0.5, 0.8, 0.5, 0.2)
                time.sleep(1)
                if self.u2d.xpath(f"//*[contains(@text, '{node}')]").exists:
                    self.u2d.xpath(f"//*[contains(@text, '{node}')]").click()
                    time.sleep(1)
                    self.u2d.xpath('//*[@text="OK"]').click_exists(timeout=2)
                    for i in range(3):
                        if self.u2d.xpath('//*[@text="DISCONNECT"]').exists:
                            break
                        time.sleep(2)
                    break
        else:
            self.u2d.xpath('//*[@text="DISCONNECT"]').click()

        if not no_return_home:
            self.u2d.click(0.5, 0.979)

    def wait_skin_temperature_cooling(self, check_temp, target_temp):
        """
        等待降温并返回是否有发生降温
        """
        t = float(check_temp)
        tt = float(target_temp)
        ct = self.get_skin_or_battery_temperature()
        logs_p().log(f'Current skin temperature is {ct}℃')
        if ct < t:
            return False

        logs_p().log(
            f'Temperature is too high, exceeding {t}℃, waiting for it to cool down to {tt}℃')
        self.screen_off()
        for i in range(30):
            time.sleep(30)
            ct = self.get_skin_or_battery_temperature()
            logs_p().log(f'Current skin temperature is {ct}')
            if ct < tt:
                logs_p().log(f'Temperature of {tt}℃ is reached, exiting cooling process')
                return True
        else:
            raise Exception(f'Failed to cool down to {t}℃ within 15 minutes')

    def get_package_pid(self, app_package: str):
        return adb.get_running_package_pid(self.device_id, app_package)

    def get_current_package_name(self):
        # 使用 adb shell dumpsys 获取当前包名
        cmd = f"dumpsys window | grep mCurrentFocus"
        result = adb.exec_cmd(self.device_id, cmd)
        # 提取包名
        try:
            package_name = result[0].split()[2].split('/')[0]
        except:
            package_name = 'unknown'
        return package_name

    def get_visible_recent_packages(self, only_alive=True):
        packages = set()

        # 获取最近任务的输出信息
        output = subprocess.check_output(
            [ADB_EXE, "-s", self.device_id, "shell", "dumpsys", "activity", "recents"]).decode('utf-8')

        # 使用正则表达式来解析可见的最近任务
        visible_tasks = re.findall(r'\* RecentTaskInfo #[0-9]+:\s+id=(\d+).*?cmp=([^ ]+)', output, re.DOTALL)

        # 遍历每个可见的最近任务并关闭
        for task_id, component in visible_tasks:
            # 在这里可以添加逻辑，决定是否关闭某个特定的任务。例如，排除掉Launcher（一般不会出现，所以这里先注释）
            # if "launcher" not in component.lower():
            package = component.split('/')[0]
            if not only_alive or self.get_package_pid(package):
                packages.add(package)
        return packages

    def stop_visible_recent_tasks(self, soft_stop=True):
        try:
            for package in self.get_visible_recent_packages():
                subprocess.run(
                    [ADB_EXE, "-s", self.device_id, "shell", "am", "stop-app" if soft_stop else 'force-stop', package],
                    check=True)
        except subprocess.CalledProcessError as e:
            logs_p().log_error(f"Error executing ADB command: {e}")
        except FileNotFoundError:
            logs_p().log_error(
                "ADB command not found, please ensure ADB is properly installed and added to the system path.")

    def set_oobe_country(self, country_code):
        if country_code == adb.getprop(self.device_id, 'persist.sys.oobe_country'):
            return
        logs_p().log(f"Set OOBE country to {country_code}")
        adb.setprop(self.device_id, 'persist.sys.oobe_country', country_code)
        # time.sleep(1)
        # self.reboot_and_wait_complete()

    def get_uptime_in_seconds(self):
        # 使用adb shell命令获取手机的开机时间，单位是秒
        adb_command = f"{ADB_EXE} -s {self.device_id} shell cat /proc/uptime"
        result = subprocess.run(adb_command.split(), capture_output=True, text=True, encoding='utf-8')

        # 检查命令是否成功执行
        if result.returncode != 0:
            raise Exception("ADB command execution failed, please check ADB connection and device status.")

        # 解析输出，获取开机时间的秒数
        uptime_seconds = float(result.stdout.split()[0])

        return uptime_seconds

    def clear_app_data(self, package_name):
        adb.clear_app_data(self.device_id, package_name)

    def revoke_location_permissions(self, package_name):
        pms = ['ACCESS_COARSE_LOCATION', 'ACCESS_FINE_LOCATION']
        adb.revoke_android_permissions(self.device_id, package_name, pms)

    def grant_location_permissions(self, package_name):
        pms = ['ACCESS_COARSE_LOCATION', 'ACCESS_FINE_LOCATION']
        adb.grant_android_permissions(self.device_id, package_name, pms)

    def grant_common_permissions(self, package_name):
        pms = ['POST_NOTIFICATIONS', 'READ_CONTACTS', 'RECORD_AUDIO',
               'READ_PHONE_STATE', 'CAMERA', 'READ_EXTERNAL_STORAGE', 'WRITE_EXTERNAL_STORAGE',
               'READ_MEDIA_AUDIO', 'READ_MEDIA_IMAGES', 'READ_MEDIA_VIDEO']
        adb.grant_android_permissions(self.device_id, package_name, pms)

    def grant_debug_logger_permissions(self):
        eng_package = 'com.mediatek.engineermode'
        if self.is_sprd:
            eng_package = 'com.sprd.engineermode'
        self.grant_all_useful_permissions(eng_package)
        adb.grant_android_permissions(self.device_id, eng_package, ['BLUETOOTH_SCAN'])

    def grant_file_management_permissions(self, package_name):
        adb.granting_high_level_permission(self.device_id, package_name, 'MANAGE_EXTERNAL_STORAGE')

    def grant_all_useful_permissions(self, package_name):
        # self.grant_common_permissions(package_name)
        # self.grant_location_permissions(package_name)
        self.grant_all_runtime_permissions(package_name)
        self.grant_file_management_permissions(package_name)

    def deny_pip_permission(self, package_name):
        adb.deny_high_level_permission(self.device_id, package_name, 'PICTURE_IN_PICTURE')

    def granting_pip_permission(self, package_name):
        adb.granting_high_level_permission(self.device_id, package_name, 'PICTURE_IN_PICTURE')

    def open_close_wifi(self, is_open: bool):
        adb.open_close_wifi(self.device_id, is_open)

    def open_close_mobile_data(self, is_open: bool):
        adb.open_close_mobile_data(self.device_id, is_open)

    def open_close_bluetooth(self, is_open: bool):
        adb.open_close_bluetooth(self.device_id, is_open)

    def open_close_location_service(self, is_open: bool):
        adb.open_close_location_service(self.device_id, is_open)

    def open_close_nfc(self, is_open: bool):
        adb.open_close_nfc(self.device_id, is_open)

    def open_close_auto_brightness(self, is_open: bool):
        adb.settings_set_screen_auto_brightness(self.device_id, is_open)

    def open_close_auto_rotate(self, enabled: bool):
        adb.open_close_auto_rotate(self.device_id, enabled)

    def set_screen_fps_auto(self):
        adb.set_settings_screen_fps_auto(self.device_id)

    def get_time(self):
        """获取Android手机的当前时间"""
        result = adb.exec_cmd(self.device_id, "date +'%Y-%m-%d %H:%M:%S'")[0]
        phone_time = datetime.strptime(result, '%Y-%m-%d %H:%M:%S')
        return phone_time

    @property
    def is_hotspot_open(self):
        return adb.is_hotspot_open(self.device_id)

    def assert_hotspot_closed(self):
        if (adb.is_hotspot_open(self.device_id)):
            adb.stop_settings_activity(self.device_id)
            self.u2d.sleep(1)
            adb.open_settings_activity(self.device_id)
            self.u2d.sleep(3)
            if self.u2d(textMatches=".*Search.*").exists:
                self.u2d.sleep(1)
                self.u2d(textMatches=".*Search.*").click()
            else:
                assert False, 'search box not found'
            self.u2d.sleep(1)
            self.u2d.send_keys('Hotspot Set')
            self.u2d.sleep(1)
            menu = self.u2d(resourceId="com.android.settings.intelligence:id/breadcrumb", textContains="Personal Hotspot")
            if menu.exists(timeout=3):
                menu.click()
            else:
                assert False, (f"Personal Hotspot menu not found")
            self.u2d.sleep(1)
            self.u2d.xpath('//*[@resource-id="com.transsion.settings.wifi:id/recycler_view"]/android.view.ViewGroup[1]/android.widget.LinearLayout[1]').click(timeout=3)
            self.u2d.sleep(1)
        assert not adb.is_hotspot_open(self.device_id), 'Hotspot is still open'

    @property
    def is_airplane_mode_on(self):
        return adb.is_airplane_mode_on(self.device_id)

    def open_close_airplane_mode(self, is_open: bool):
        if self.is_airplane_mode_on == is_open:
            return
        self.screen_on_and_unlock()
        u2d = self.u2d
        u2d.app_stop("com.android.settings")
        u2d.sleep(2)
        u2d.app_start("com.android.settings")
        u2d.sleep(2)
        if u2d(textContains='Hotspot & Connections').exists():
            self.u2d(textContains='Hotspot & Connections').click()
            u2d.sleep(2)
        self.u2d(textContains='Airplane').click(timeout=5)
        u2d.sleep(3)
        
        u2d.app_stop("com.android.settings")
        u2d.sleep(1)

    def screen_off(self):
        adb.off_screen(self.device_id)

    def press_home_key(self, times=1, interval=0.5):
        for i in range(times):
            if i > 0:
                time.sleep(interval)
            adb.press_home_key(self.device_id)

    def press_back_key(self, times=1, interval=0.5):
        for i in range(times):
            if i > 0:
                time.sleep(interval)
            adb.press_back_key(self.device_id)

    def press_app_switch_key(self):
        adb.press_app_switch_key(self.device_id)

    def press_recent_key(self):
        adb.press_recent_key(self.device_id)

    def call_the_lasted_app_small_window(self):
        """
        点出recent中最新的一个应用的小窗模式
        """
        self.u2d.swipe(0.8, 0.5, 0.2, 0.5)
        time.sleep(2)
        small_window_button = self.u2d.xpath('//*[@resource-id="com.transsion.launcher3:id/smallWindowButton"]').all()
        if len(small_window_button) == 2:
            small_window_button[1].click()
        else:
            small_window_button[0].click()
        time.sleep(2)

    def get_bounds_corner(self, resource_id_or_xpath, position):
        """
        获取控件的中心/四角的绝对位置。
        """
        bounds = self.u2d.xpath(resource_id_or_xpath).info['bounds']
        if position == 'center':
            return ((bounds['left'] + bounds['right']) / 2,
                    (bounds['top'] + bounds['bottom']) / 2)
        elif position == 'left_top':
            return (bounds['left'], bounds['top'])
        elif position == 'right_top':
            return (bounds['right'], bounds['top'])
        elif position == 'left_bottom':
            return (bounds['left'], bounds['bottom'])
        elif position == 'right_bottom':
            return (bounds['right'], bounds['bottom'])

    def adjust_the_size_of_small_window(self, expect_postion: tuple = None, resource_id_or_xpath=None):
        """
        调整桌面小窗的大小，目前固定拉大相对多位置(100,100), 后期需要自定义位置可拓展。默认位置需要保留
        """
        if not resource_id_or_xpath:
            resource_id_or_xpath = '(//*[@resource-id="android:id/content"])[2]'
        left, bottom = self.get_bounds_corner(resource_id_or_xpath, 'left_bottom')
        # 需要把焦点放在桌面，否则滑动是在应用内完成的
        self.press_home_key()
        # 调整窗口大小（从左下角往外面拉）
        self.u2d.drag(left, bottom,
                      left - 100, bottom + 100)

    def adjust_the_position_of_small_window(self, expect_postion: tuple = None, resource_id_or_xpath=None):
        """
        调整桌面小窗的未知
        @param expect_postion: tuple(0-1, 0-1) 相对坐标
        """
        width, height = self.u2d.window_size()[0], self.u2d.window_size()[1]
        if not expect_postion:
            expect_postion = (0.1, 0.1)
        if not resource_id_or_xpath:
            resource_id_or_xpath = '(//*[@resource-id="android:id/content"])[2]'
        # 需要把焦点放在桌面，否则滑动是在应用内完成的
        self.press_home_key()
        # 拖动窗口位置
        x, y = self.get_bounds_corner(resource_id_or_xpath, 'center')
        self.u2d.swipe(x, y, width * expect_postion[0], height * expect_postion[1])

    def clean_small_window(self):
        window_bounds = f'(//*[@resource-id="android:id/content"])[2]'
        window_x, window_y = self.get_bounds_corner(window_bounds, 'center')
        self.u2d.swipe(window_x, window_y, 0.5 * self.u2d.info['displayWidth'], self.u2d.info['displayHeight'])

    def screen_on_and_unlock(self):
        need_wait = False
        if not adb.is_screen_on(self.device_id):
            need_wait = True
        adb.poweron_screen_and_unlock(self.device_id)
        if need_wait:
            time.sleep(1)

    def screen_on_and_unlock_numeric(self, password):
        adb.poweron_phone_screen(self.device_id)
        time.sleep(1)

        cmd = 'wm dismiss-keyguard'
        adb.exec_cmd(self.device_id, cmd)
        time.sleep(2)

        adb.exec_cmd(self.device_id, 'input text ' + password)

    def assert_language_en(self):
        """
        Check whether the test phone and copilot phone system language is English
        """
        if adb.exec_cmd(self.device_id, 'getprop persist.sys.locale')[0].strip() != 'en-US':
            raise Exception('The test phone system language is not set to English.')

    def check_switch_language_en(self):
        """
        Set the system language to English
        """
        if adb.exec_cmd(self.device_id, 'getprop persist.sys.locale')[0].strip() != 'en-US':
            logs_p().log('The phone system language is not set to English, try setting it to English.')
            adb.exec_cmd(self.u2d.serial, 'am start -a android.settings.LOCALE_SETTINGS')
            eng = self.u2d(textContains='English').wait(timeout=2)
            if eng:
                self.u2d(textContains='English').click()
                self.u2d.sleep(1)
                self.u2d(resourceId='com.android.settings:id/btn_positive').click()
            else:
                self.u2d(resourceId='com.android.settings:id/add_language').click()
                self.u2d.sleep(1)
                for i in range(3):
                    if(self.u2d(textContains='English').exists()):
                        break
                    self.u2d.swipe(0.5, 0.7, 0.5, 0.3)
                    self.u2d.sleep(1)
                self.u2d(textContains='English').click()
                self.u2d.sleep(1)
                self.u2d(resourceId='com.android.settings:id/btn_positive').click()
            self.u2d.sleep(1)
            if adb.exec_cmd(self.device_id, 'getprop persist.sys.locale')[0].strip() != 'en-US':
                raise Exception("set system language to English！")
            else:
                logs_p().log('set system language to English successfully！')

    def set_default_browser(self, app_package):
        adb.exec_cmd(self.device_id, f'cmd role add-role-holder android.app.role.BROWSER {app_package}')

    def set_as_default_sms(self, app_package):
        adb.exec_cmd(self.device_id, f'cmd role add-role-holder android.app.role.SMS {app_package}')

    def switch_keyboard_default(self):
        """
        Set the system language to English(QWERTY)
        """
        self.restore_keyboard_ime()
        # self.screen_on_and_unlock()
        # self.u2d.press('home')
        # self.u2d.sleep(1)
        # self.u2d.app_stop("com.android.settings")
        # self.u2d.app_start("com.android.settings")
        # for i in range(5):
        #     self.u2d.swipe(0.5, 0.7, 0.5, 0.3)
        #     self.u2d.sleep(1)
        # self.u2d(textContains='System').click()
        # self.u2d.sleep(1)
        # self.u2d(textContains='Input').click()
        # self.u2d.sleep(1)
        # self.u2d(textContains='On-screen keyboard').click()
        # self.u2d.sleep(1)
        # keyboards = self.u2d(resourceId='android:id/title')
        # for keyboard in keyboards:
        #     if keyboard.get_text() == 'Emoji Keyboard':
        #         keyboard.click()
        #         activate = self.u2d(textContains='Switch to Emoji Keyboard').wait(timeout=2)
        #         if activate:
        #             self.u2d(textContains='Switch to Emoji Keyboard').click()
        #             self.u2d.sleep(1)
        #             self.u2d(textContains='Emoji Keyboard').click()
        #             self.u2d.sleep(1)
        #         self.u2d(resourceId='com.facemoji.lite.transsion:id/tabbar_settting_iv').click()
        #         self.u2d.sleep(1)
        #         self.u2d(text='Languages').click()
        #         self.u2d.sleep(1)
        #         eng = self.u2d(textContains='English')
        #         if eng:
        #             self.u2d(textContains='English').click()
        #             self.u2d.sleep(2)
        #             self.u2d(textContains='English').click()
        #             break
        #         else:
        #             raise Exception("Set the keyboard language to English！")
        #     if keyboard.get_text() == 'Yandex Keyboard':
        #         keyboard.click()
        #         activate = self.u2d(text='OK').wait(timeout=2)
        #         if activate:
        #             self.u2d.sleep(1)
        #             self.u2d(description='Select').click()
        #             self.u2d.sleep(1)
        #             self.u2d(textContains='Yandex Keyboard').click()
        #             self.u2d.sleep(1)
        #             self.u2d(textContains='Go to settings').click()
        #             self.u2d.sleep(1)
        #         eng_parent = self.u2d(text='Language')
        #         eng = eng_parent.sibling(index=1)
        #         if eng.get_text() != "English":
        #             raise Exception("Set the keyboard language to English！")
        #         else:
        #             eng.click()
        #             layout = self.u2d(text='QWERTY').wait(timeout=2)
        #             if layout is False:
        #                 raise Exception("Set the keyboard layout to QWERTY！")
        #     if keyboard.get_text() == 'Gboard':
        #         keyboard.click()
        #         self.u2d.sleep(1)
        #         language = self.u2d(text='Languages')
        #         text = language.sibling(index=1).get_text()
        #         if "English" not in text:
        #             raise Exception("Set the keyboard language to English！")
        #         if "QWERTY" not in text:
        #             raise Exception("Set the keyboard layout to QWERTY！")
        #         break
        # self.u2d.app_stop("com.android.settings")

    def assert_battery_level(self, level: int):
        now_level = adb.read_battery(self.device_id)
        assert now_level >= level, f'The battery level is {now_level} less than {level}！'

    def get_sim_count(self):
        return adb.get_sim_count(self.device_id)

    def get_enabled_sim_count(self):
        return adb.get_enabled_sim_count(self.device_id)

    def check_the_slot_loaded(self, index):
        """
        必须要两张卡及以上, 只检查是否加载
        """
        if self.is_sprd or self.is_qcom:
            # 两种方法都可以
            sim_states = adb.getprop(self.device_id, 'gsm.sim.state')
            sim_state_list = sim_states.split(',')
            return sum(1 for item in sim_state_list) > 1 and sim_state_list[index] == 'LOADED'
            # sim_states = adb.getprop(self.device_id, 'gsm.sim.operator.alpha')
            # sim_state_list = sim_states.split(',')
            # return sum(1 for item in sim_state_list) > 1 and sim_state_list[index] != ''
        else:
            operators = adb.getprop(self.device_id, 'gsm.operator.alpha')
            operator_list = operators.split(',')  # 按逗号分割成列表
            return sum(1 for item in operator_list) > 1 and operator_list[index] != ''

    def get_cn_sim_index(self):
        return adb.get_cn_sim_index(self.device_id)

    def is_sim_plugged_and_loaded(self, sim_index: int):
        return adb.get_sim_is_plugged(self.device_id, sim_index)

    def get_overseas_sim_index(self):
        return adb.get_overseas_sim_index(self.device_id)

    def set_settings_sim_enabled(self, sim_index: int = 1, enable: bool = True):
        self.screen_on_and_unlock()
        u2d = self.u2d
        self.restart_app('com.android.settings')
        u2d.sleep(2)
        u2d.xpath('//*[contains(@text, "SIM")]').click()
        u2d.sleep(5)
        if sim_index == 1:
            # 更稳定
            self.u2d.click(0.5, 0.175)
            # self.click_wait(u2d.xpath(
            #     '//*[@resource-id="com.transsion.tele.settings:id/title"] | //*[@resource-id="com.android.settings:id/icon"]').all()[
            #                     0], pre_wait=1,
            #                 timeout=5, post_wait=1)
        else:
            self.u2d.click(0.5, 0.27)
            # self.click_wait(u2d.xpath(
            #     '//*[@resource-id="com.transsion.tele.settings:id/title"] | //*[@resource-id="com.android.settings:id/icon"]').all()[
            #                     1], pre_wait=1,
            #                 timeout=5, post_wait=1)
        self.wait_ui_obj('//*[@resource-id="android:id/switch_widget"]', pre_wait=1, timeout=5)
        btn_enable = u2d.xpath('//*[@resource-id="android:id/switch_widget"]')
        if btn_enable.info['checked'] != enable:
            btn_enable.click()
            u2d.sleep(1)
        if u2d.xpath('//*[@resource-id="android:id/switch_widget"]').info['checked'] != enable:
            u2d.app_stop('com.android.settings')
            raise Exception(f"A SIM card indexed as {sim_index} failed to set! ")
        u2d.app_stop('com.android.settings')

    def _prepare_or_restore_sim_status_for_special_overseas_app(self, is_prepare: bool):
        sim_count = self.get_sim_count()
        if sim_count < 2:
            t_log.warning(f'There is only {sim_count} sim card, will skip set sim status for special overseas app...')
            return

        enabled_sim_count = self.get_enabled_sim_count()

        cn_index = self.get_cn_sim_index()
        if cn_index == 0 and enabled_sim_count >= 2:
            return

        if cn_index == 0:
            os_index = self.get_overseas_sim_index()
            if os_index == 0:
                raise Exception('Not found overseas sim card index!')
            cn_index = (2 if os_index == 1 else 1)
        else:
            os_index = (2 if cn_index == 1 else 1)

        if enabled_sim_count == 2:
            if self.is_sprd:
                self.unplug_sim_via_ui(cn_index if is_prepare else os_index)
                self.click_wait('//android.widget.Button[@text="OK"]', timeout=5, no_raise=True)
            else:
                self.unplug_sim_via_ui(cn_index if is_prepare else os_index)
        elif enabled_sim_count == 1:
            if self.is_sim_plugged_and_loaded(cn_index if is_prepare else os_index):
                if self.is_sprd:
                    self.plug_sim_via_ui(os_index if is_prepare else cn_index)
                    self.click_wait('//android.widget.Button[@text="OK"]', timeout=5, no_raise=True)
                    self.unplug_sim_via_ui(cn_index if is_prepare else os_index)
                    self.click_wait('//android.widget.Button[@text="OK"]', timeout=5, no_raise=True)
                else:
                    self.plug_sim_via_ui(os_index if is_prepare else cn_index)
                    self.unplug_sim_via_ui(cn_index if is_prepare else os_index)

    def set_sim_overseas_enabled_cn_disabled(self):
        """确保只有一张海外卡被Enable"""
        self._prepare_or_restore_sim_status_for_special_overseas_app(True)

    def set_sim_overseas_disabled_cn_enabled(self):
        """确保只有一张海外卡被Enable"""
        self._prepare_or_restore_sim_status_for_special_overseas_app(False)

    def assert_sim_count(self, need_sim_count: int):
        sim_count = adb.get_sim_count(self.device_id)
        assert sim_count == need_sim_count, f'The sim card count is {sim_count} not equals {need_sim_count}！'

    def assert_sim_count_greater_than(self, need_sim_count: int):
        sim_count = adb.get_sim_count(self.device_id)
        assert sim_count >= need_sim_count, f'The sim card count is {sim_count} less than {need_sim_count}！'

    def get_cn_sim_index_and_number(self):
        self.screen_on_and_unlock()
        u2d = self.u2d
        u2d.app_stop("com.android.settings")
        u2d.sleep(2)
        u2d.app_start("com.android.settings")
        u2d.sleep(2)
        try:
            u2d(textContains="SIM").click(timeout=2)
        except:
            u2d.app_stop("com.android.settings")
            u2d.sleep(2)
            u2d.app_start("com.android.settings")
            u2d.sleep(2)
            u2d(textContains="SIM").click(timeout=2)
        u2d.sleep(2)
        cn_card = u2d(textContains="+86")
        phone_domestic = cn_card.wait(timeout=2)
        if not phone_domestic:
            raise Exception("No CN SIM card found！")
        phone_number = cn_card.get_text(timeout=2)
        country = phone_number.split(" ")[0]
        phone_number = phone_number.replace(country, "").replace(" ", "")
        phone_number = re.sub(r'\D+', '', phone_number)

        cn_card.click(timeout=2)
        text_from_control = u2d(textContains="SIM").get_text(timeout=2)
        match = re.search(r'\d+', text_from_control)
        cn_sim_index = match.group(0) if match else 1
        u2d.app_stop("com.android.settings")
        return cn_sim_index, phone_number

    def correct_sim_mode_for_cn_card_and_overseas_card(self):
        """
        Check if the SIM card is set to default to the domestic card for data and calls.
        """
        if adb.get_sim_count(self.device_id) != 2:
            return
        self.screen_on_and_unlock()
        u2d = self.u2d
        u2d.app_stop("com.android.settings")
        u2d.sleep(2)
        u2d.app_start("com.android.settings")
        u2d.sleep(2)
        u2d(textContains="SIM").click(timeout=4)
        u2d.sleep(2)
        cn_card_1 = u2d.xpath("(//*[contains(@text, '+')]/../../../../*)[1]//*[contains(@text, '+')]")
        cn_card_2 = u2d.xpath("(//*[contains(@text, '+')]/../../../../*)[2]//*[contains(@text, '+')]")
        cn_card = None
        overseas_card = None
        if cn_card_1.exists:
            cn_card = cn_card_1
            overseas_card = u2d.xpath("(//*[contains(@text, '+')]/../../../../*)[2]")
        elif cn_card_2.exists:
            cn_card = cn_card_2
            overseas_card = u2d.xpath("(//*[contains(@text, '+')]/../../../../*)[1]")
        if not cn_card:
            raise Exception('No cn sim card found!')
        cn_card.click(timeout=1)
        u2d.sleep(2)
        switch = u2d.xpath('//*[@resource-id="android:id/switch_widget"]').get(timeout=2)
        if not switch.info['checked']:
            switch.click()
            u2d.sleep(2)
        u2d.press('back')
        u2d.sleep(2)
        overseas_card.click(timeout=1)
        u2d.sleep(2)
        switch = u2d.xpath('//*[@resource-id="android:id/switch_widget"]').get(timeout=2)
        if switch.info['checked']:
            switch.click()
            u2d.sleep(3)
        u2d.xpath('//*[@resource-id="android:id/switch_widget"]').click()
        u2d.sleep(3)
        u2d.press('home')

    def close_sleep_mode(self):
        adb.set_settings_value(self.device_id, 'global', 'battery_lab_ai_reminder', '0')

    def disable_ai_net_control_enable(self):
        adb.set_settings_value(self.device_id, 'global', 'ai_net_control_enable', '0')

    def get_ai_net_control_enable(self):
        v = adb.get_settings_value(self.device_id, 'global', 'ai_net_control_enable')
        return v == '0'

    def close_google_protect(self):
        adb.set_settings_value(self.device_id, 'global', 'package_verifier_user_consent', '-1')
        # self.screen_on_and_unlock()
        # u2d = self.u2d
        # u2d.app_stop("com.android.vending")
        # u2d.sleep(2)
        # u2d.app_start("com.android.vending")
        # u2d.sleep(5)
        # if u2d.xpath('//androidx.compose.ui.platform.ComposeView/android.view.View[1]/android.view.View[3]').exists:
        #     u2d.xpath('//androidx.compose.ui.platform.ComposeView/android.view.View[1]/android.view.View[3]').click()
        # else:
        #     self.u2d.xpath('//*[@resource-id="com.android.vending:id/0_resource_name_obfuscated"]').all()[5].click()
        # self.click_wait('//*[@text="Play Protect"]', timeout=8, post_wait=1)
        # self.click_wait('//*[@content-desc="Settings"]', timeout=8, post_wait=1)
        # self.wait_ui_obj('//android.support.v7.widget.RecyclerView/android.widget.LinearLayout[1]/'
        #                  'android.widget.LinearLayout[1]/android.widget.Switch[1]', timeout=8, post_wait=1)
        # btn1 = u2d.xpath('//android.support.v7.widget.RecyclerView/android.widget.LinearLayout[1]/'
        #                  'android.widget.LinearLayout[1]/android.widget.Switch[1]')
        # if btn1.info['checked']:
        #     btn1.click()
        #     u2d.sleep(1)
        #     u2d.xpath('//*[@text="Turn off"]').click(timeout=2)

    def set_long_screen_sleep_time(self):
        self.set_screen_sleep_time(True, True)

    def assert_swipe_unlock_mode(self):
        lock_result = adb.exec_cmd(self.device_id, 'locksettings get-disabled')[0]
        if lock_result == 'true':
            adb.exec_cmd(self.device_id, 'locksettings set-disabled false')
        elif lock_result != 'false':
            raise Exception("Phone swipe unlock mode is not correct！")

    def set_all_volume_level(self, level: int):
        self.set_media_volume_level(level)
        self.set_call_volume_level(level)
        self.set_ring_volume_level(level)

    def set_media_volume_level(self, level: int):
        if float(adb.device_android_version(self.device_id)) < 16:
            adb.exec_cmd(self.device_id, f'service call audio 12 i32 3 i32 {level} i32 1')
        else:
            adb.exec_cmd(self.device_id, f'service call audio 14 i32 3 i32 {level} i32 1')
        time.sleep(0.5)

    def set_call_volume_level(self, level: int):
        if float(adb.device_android_version(self.device_id)) < 16:
            adb.exec_cmd(self.device_id, f'service call audio 12 i32 3 i32 {level} i32 1')
        else:
            adb.exec_cmd(self.device_id, f'service call audio 14 i32 3 i32 {level} i32 1')
        time.sleep(0.5)

    def set_ring_volume_level(self, level: int):
        if float(adb.device_android_version(self.device_id)) < 16:
            adb.exec_cmd(self.device_id, f'service call audio 12 i32 3 i32 {level} i32 1')
        else:
            adb.exec_cmd(self.device_id, f'service call audio 14 i32 3 i32 {level} i32 1')
        time.sleep(0.5)

    def set_brightness_and_close_auto_bright(self, level: int):
        adb.settings_set_screen_auto_brightness(self.device_id, False)
        adb.settings_set_screen_brightness(self.device_id, level)
        time.sleep(1)

    def assert_navi_mode_3_buttons(self):
        assert adb.get_settings_value(self.device_id, "secure",
                                      'navigation_mode') == '0', 'Phone navigation is not 3-buttons'

    def assert_navi_mode_gesture(self):
        assert adb.get_settings_value(self.device_id, "secure",
                                      'navigation_mode') != '0', 'Phone navigation is not gesture'

    def set_navi_mode_3_buttons(self):
        if adb.get_settings_value(self.device_id, "secure", 'navigation_mode') == '0':
            return
        self.screen_on_and_unlock()
        u2d = self.u2d
        u2d.app_stop('com.android.settings')
        u2d.sleep(2)
        u2d.app_start('com.android.settings')
        u2d.sleep(1)
        for i in range(3):
            u2d.swipe(0.5, 0.8, 0.5, 0.2)
            u2d.sleep(1)
        u2d.xpath('//android.widget.TextView[@text="System"]').click(timeout=2)
        u2d.sleep(1)
        u2d.swipe(0.5, 0.2, 0.5, 0.8)
        u2d.sleep(1)
        try:
            u2d.xpath('//android.widget.TextView[@text="System Navigation"]').click(timeout=2)
        except XPathElementNotFoundError:
            u2d.xpath('//android.widget.TextView[@text="System navigation"]').click(timeout=2)
        try:
            u2d.xpath('//*[@text="Three-button navigation"]').click(timeout=2)
            u2d.sleep(1)
            try:
                u2d.sleep(1)
                u2d.xpath('//*[@resource-id="com.transsion.microintelligence:id/key_nav_img_button"]').click(timeout=2)
                u2d.sleep(3)
                u2d.xpath(
                    '//*[@resource-id="com.transsion.microintelligence:id/position_first_key_radiobutton"]').click(
                    timeout=2)
            except XPathElementNotFoundError:
                pass
        except XPathElementNotFoundError:
            u2d.sleep(1)
            u2d.xpath('//*[@resource-id="com.transsion.microintelligence:id/key_nav_img_button"]').click(timeout=2)
            u2d.sleep(3)
            u2d.xpath('//*[@resource-id="com.transsion.microintelligence:id/position_first_key_radiobutton"]').click(
                timeout=2)
        u2d.sleep(1)
        u2d.app_stop('com.android.settings')
        assert adb.get_settings_value(self.device_id, "secure",
                                      'navigation_mode') == '0', 'Failed to enable navigation bottom 3 buttons mode'
        u2d.press('home')

    def check_network_connections(self, check_overseas: bool):
        website = "google.com" if check_overseas else "www.baidu.com"
        is_pass = False
        for i in range(3):
            try:
                result = subprocess.run(
                    [ADB_EXE, "-s", self.device_id, "shell", "ping", "-c", "1", website],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    encoding='utf-8'
                )
                is_pass = result.returncode == 0
            except:
                pass
            if is_pass:
                break
            else:
                time.sleep(0.5)
        if not is_pass:
            raise Exception('Can not connect to the network!')

    def assert_non_disturb_mode_close(self):
        if (adb.get_settings_value(self.device_id, 'global', 'zen_mode') == '1'):
            adb.stop_settings_activity(self.device_id)
            self.u2d.sleep(1)
            adb.open_settings_activity(self.device_id)
            self.u2d.sleep(3)
            if self.u2d(textMatches=".*Search.*").exists:
                self.u2d.sleep(1)
                self.u2d(textMatches=".*Search.*").click()
            else:
                assert False, 'search box not found'
            self.u2d.sleep(1)
            self.u2d.send_keys('Do Not Distur')
            self.u2d.sleep(1)
            menu = self.u2d(resourceId="com.android.settings.intelligence:id/breadcrumb", textContains="Do Not Disturb")
            if menu.exists(timeout=3):
                menu.click()
            else:
                assert False, (f"Do Not Disturb menu not found")
            self.u2d.sleep(1)
            self.u2d.xpath('//*[@resource-id="com.android.settings:id/recycler_view"]/android.view.ViewGroup[1]/android.widget.LinearLayout[1]').click()
            self.u2d.sleep(1)

    def close_desktop_auto_align(self):
        self.screen_on_and_unlock()
        u2d = self.u2d
        tos = adb.exec_cmd(self.device_id, 'getprop ro.build.version.release')[0]
        adb.open_settings_activity(self.device_id)
        u2d.sleep(1)
        if u2d(textMatches=".*Search.*").exists:
            search_box = u2d(textMatches=".*Search.*")
        else:
            assert False, 'search box not found'
        search_box.click(timeout=5)
        u2d.sleep(1)
        if tos == '14':
            u2d.send_keys('Desktop Setting')
            u2d.sleep(2)
            u2d.xpath('//*[@resource-id="android:id/icon"]').click_exists(timeout=5)
            u2d.sleep(1)
            u2d.xpath('//*[@text="Desktop Setting"]').click(timeout=5)
            u2d.sleep(1)
            u2d.xpath('//*[@text="Others"]').click(timeout=5)
            u2d.sleep(1)
            auto_arrange_button = u2d.xpath("(//android.widget.Switch)[2]")
        else:
            self.input_text('Home Screen Settings')
            u2d.sleep(1)
            self.click_wait('//*[@resource-id="android:id/icon"]', timeout=20, post_wait=1)
            u2d.sleep(1)
            auto_arrange_button = u2d.xpath("(//android.widget.Switch)[3]")

        if auto_arrange_button.info['checked']:
            auto_arrange_button.click(timeout=5)
        if not auto_arrange_button.exists:
            assert False, 'auto arrange button not found'

    def get_phone_number_ke(self):
        u2d = self.u2d
        phone_number = ''
        self.screen_on_and_unlock()

        def _try_get_number():
            u2d.app_stop('com.sh.smart.caller')
            adb.press_home_key(self.device_id)
            u2d.sleep(2)
            u2d.app_start('com.sh.smart.caller')
            u2d.sleep(2)
            u2d.xpath('//android.widget.TextView[@text="Recents"]').click(timeout=10)
            u2d.sleep(1)
            u2d(text='*').click(timeout=2)
            u2d(text='1').click(timeout=2)
            u2d(text='0').click(timeout=2)
            u2d(text='0').click(timeout=2)
            u2d(text='#').click(timeout=2)
            u2d.sleep(1)
            u2d.xpath('//*[@text="Check mobile phone number"]').click(timeout=2)
            u2d.sleep(6)
            window = u2d.xpath('//*[contains(@text, "4:My Account")]').wait(timeout=6)
            if window is False:
                raise Exception("can't open Safaricom service window")
            u2utils.input_text(u2d, '4')
            u2d.sleep(2)
            self.u2d(text='Send').click(timeout=4)
            u2d.sleep(5)
            u2utils.input_text(u2d, '1')
            u2d.sleep(2)
            self.u2d(text='Send').click(timeout=4)
            u2d.sleep(5)
            u2utils.input_text(u2d, '1')
            u2d.sleep(2)
            self.u2d(text='Send').click(timeout=4)
            u2d.sleep(5)
            banner = self.u2d(textContains='Your number is').wait(timeout=4)
            if banner:
                _phone_number = self.u2d(textContains='Your number is').get_text(timeout=2)
                _phone_number = _phone_number.replace("Your number is ", "").replace(".", "")
                _phone_number = re.sub(r'\D+', '', _phone_number)
                # 不添加区号，可能打不通电话
                _phone_number = "+254" + _phone_number
                try:
                    self.u2d(text='OK').click(timeout=2)
                except:
                    pass
                u2d.app_stop('com.sh.smart.caller')
                return _phone_number
            else:
                try:
                    self.u2d(text='OK').click(timeout=2)
                except:
                    pass
                raise Exception("can't get phone number")

        for _ in range(2):
            try:
                phone_number = _try_get_number()
                break
            except Exception as e:
                logs_p().log(e)
                time.sleep(1)

        if not phone_number:
            raise Exception('Can not get phone number!')

        return phone_number

    def get_phone_number_manual_window(self, title='Record phone number for process', tips='Enter phone number:',
                                       default_number='', timeout=10):
        """
            弹出一个Tkinter窗口，要求用户输入电话号码。
            输入框限制只能输入数字和'+'符号。

            Returns:
                str: 用户输入的电话号码。
        """
        import tkinter as tk
        """
            弹出一个Tkinter窗口，要求用户输入电话号码。
            输入框限制只能输入数字和'+'符号，并允许传入一个默认电话号码。
            如果传入了默认电话号码且在 `timeout` 秒内未发生任何输入，则自动点击OK按钮。

            Args:
                default_number (str): 输入框中的默认电话号码。
                timeout (int): 超时时间（秒），在无人操作时自动点击OK。

            Returns:
                str: 用户输入的电话号码。
            """
        # 创建主窗口
        root = tk.Tk()
        root.title(title)
        root.geometry("300x150")  # 设置窗口大小

        phone_number = tk.StringVar(value=default_number)  # 用于存储用户输入的电话号码，并设置默认值
        has_interacted = [False if default_number else True]  # 用于检测用户是否与输入框交互

        def validate_input(*args):
            """
            限制输入框中只能输入数字和'+'符号。
            如果输入合法，启用OK按钮；否则禁用OK按钮。
            """
            valid_chars = "0123456789+"
            current_text = phone_number.get()

            # 检查是否所有字符都合法
            if len(current_text) > 3 and all(char in valid_chars for char in current_text):
                ok_button.config(state="normal")
            else:
                ok_button.config(state="disabled")

            # 如果检测到用户手动修改输入框内容，则取消自动超时关闭
            has_interacted[0] = True

        def on_ok():
            """
            点击OK按钮时退出主窗口。
            """
            root.destroy()

        def auto_close():
            """
            如果达到超时时间且用户未进行任何操作，则自动点击OK按钮。
            """
            if not has_interacted[0]:  # 检测是否有用户交互
                on_ok()

        # 提示文字
        label = tk.Label(root, text=tips, font=("Arial", 12))
        label.pack(pady=10)

        # 输入框
        entry = tk.Entry(root, textvariable=phone_number, font=("Arial", 12))
        entry.pack(pady=5)

        # 绑定输入框的变化事件
        phone_number.trace_add("write", validate_input)

        # OK按钮
        ok_button = tk.Button(root, text="OK", font=("Arial", 12), command=on_ok, state="normal")
        ok_button.pack(pady=10)

        # 启动超时机制
        if default_number:
            root.after(timeout * 1000, auto_close)

        # 进入主事件循环，显示窗口
        root.mainloop()

        # 返回电话号码
        return phone_number.get()

    def get_phone_number_and_countrycode(self, phone_number):
        """
        前提是已经获取到了手机号

        return countrycode, phone_number
        """
        context = re.sub(r'[^\d+]', '', phone_number)
        match = re.match(r'\+?(\d{2})(\d+)', context)
        if match:
            country_code = match.group(1)
            phone_number = match.group(2)
            # 确保 country_code 在已知国家代码列表中，否则调整
            if country_code not in self.known_country_codes:
                match = re.match(r'\+?(\d{3})(\d+)', context)
                country_code = match.group(1)
                phone_number = match.group(2)

            return country_code, phone_number

    def set_dialer_default(self, app_package: str = 'com.sh.smart.caller'):
        # 设置默认Phone应用
        adb.exec_cmd(self.device_id, f'cmd role add-role-holder android.app.role.DIALER {app_package}')

    def touch_down_and_up_with_sleep(self, sx, sy, ex, ey, before_time=0.0, after_time=0.0):
        self.u2d.touch.down(sx, sy)
        time.sleep(before_time)
        self.u2d.touch.move(ex, ey)
        time.sleep(after_time)
        self.u2d.touch.up(ex, ey)

    def set_time_12_24(self, t: bool):
        adb.set_settings_value(self.device_id, 'system', 'time_12_24', 24 if t else 12)

    @property
    def is_double_tap_screen_wake_open(self):
        return adb.is_double_click_wake_enabled(self.device_id)

    @property
    def is_dynamic_island_open(self):
        value = adb.get_settings_value(self.device_id, 'global', 'os_island_switch')
        return value != '0'

    def set_dynamic_island_open_close(self, is_open):
        if is_open != self.is_dynamic_island_open:
            adb.set_settings_value(self.device_id, 'global', 'os_island_switch', '1' if is_open else '0')

    def set_inadvertently_mode_open_close(self, is_open):
        adb.set_settings_value(self.device_id, 'system', 'show_inadvertent', '1' if is_open else '0')

    def set_screen_sleep_time(self, long_or_short: bool, set_screen_on: bool):
        self.set_screen_sleep_time_for_target_sn(long_or_short, set_screen_on)

    def close_low_battery_remainder(self):
        # Battery Saver
        adb.set_settings_value(self.device_id, 'system', 'tran_settings_long_battery_mode', '0')
        # Battery Saver Notification
        adb.set_settings_value(self.device_id, 'system', 'power_boost_reminder_enabled', '0')
        # Auto-enable Battery Saver Mode
        adb.set_settings_value(self.device_id, 'global', 'low_power_trigger_level', '0')
        adb.set_settings_value(self.device_id, 'system', 'power_boost_auto_open_enabled', '0')

    def set_screen_sleep_time_for_target_sn(self, long_or_short: bool, set_screen_on: bool):
        target_sn = self.device_id
        target_time = 600000 if long_or_short else 30000
        if adb.get_screen_off_timeout(target_sn) != target_time:
            adb.set_screen_off_timeout(target_sn, target_time)
            if adb.is_screen_on(target_sn):
                adb.poweroff_phone_screen(target_sn)
                time.sleep(2)
                adb.poweron_screen_and_unlock(target_sn)
                time.sleep(1)
            elif set_screen_on:
                adb.poweron_screen_and_unlock(target_sn)
                time.sleep(1)
        elif set_screen_on:
            if not adb.is_screen_on(target_sn):
                adb.poweron_screen_and_unlock(target_sn)
                time.sleep(1)

    def get_homeapp_x_y_for_index(self, index):
        """
        根据index，获取第一个图标或者第二个图标的位置， 添加到3/ 4

        如果传入,若果传入1，表示home面，如果全部摆放成app图标，没有空余位置，那放在第1位的图标的左上角和右下角坐标
        此时，如果index==1，android.view.ViewGroup的左上角坐标与第一个app左上角重合，再偏移一些高度和宽度即可
        index = 2同理
        """
        element_group = self.u2d.xpath('//*[contains(@resource-id, "workspace")]//android.view.ViewGroup').all()[
            0]  # 外面框
        element_app = self.u2d.xpath(
            '//*[contains(@resource-id, "workspace")]//android.view.ViewGroup/android.widget.TextView').all()[
            0]  # app的小方块
        # 获取元素的位置和尺寸

        # 获取元素的bounds
        bounds = element_group.info['bounds']

        # group左上角坐标
        group_top_left_x = bounds['left']
        group_top_left_y = bounds['top']

        # 计算宽度和高度
        app_bounds = element_app.info['bounds']
        app_width = app_bounds['right'] - app_bounds['left']
        app_height = app_bounds['bottom'] - app_bounds['top']

        if index in [1, 2, 3, 4]:
            offset_x = (index - 1) * app_width
            top_left_x = group_top_left_x + offset_x
            top_left_y = group_top_left_y
            bottom_right_x = top_left_x + app_width
            bottom_right_y = top_left_y + app_height
            return [top_left_x, top_left_y], [bottom_right_x, bottom_right_y]

    def search_and_move_app_to_home(self, app_name, to_index):
        """
        to_index:1 为1时表示放在第一位，为2时表示放在第二位, 支持1-4
        """
        assert to_index == 1 or to_index == 2 or to_index == 3 or to_index == 4, f"不支持移动index {to_index}"

        adb.press_home_key(self.device_id)
        time.sleep(0.3)
        adb.press_home_key(self.device_id)
        time.sleep(1)
        adb.press_home_key(self.device_id)
        time.sleep(1)

        [top_left_x, top_left_y], [bottom_right_x, bottom_right_y] = self.get_homeapp_x_y_for_index(to_index)

        pos_x = (top_left_x + bottom_right_x) / 2
        pos_y = (top_left_y + bottom_right_y) / 2

        u2d = self.u2d
        # u2d.long_click(0.13, 0.13, 0.5)
        u2d.long_click(pos_x, pos_y, 0.5)
        u2d.sleep(1)
        if u2d.xpath('//*[@text="Disband"]').exists:
            u2d.xpath('//*[@text="Disband"]').click(timeout=5)
            u2d.sleep(6)
            u2d.press('home')
            u2d.sleep(1)
            # u2d.long_click(0.13, 0.13, 0.5)
            u2d.long_click(pos_x, pos_y, 0.5)
        u2d.sleep(1)
        remove_button = u2d.xpath('//*[@text="Remove"]')
        if remove_button.exists:
            remove_button.click(timeout=5)
        else:
            # u2d.click(0.13, 0.13)
            # u2d.click(pos_x, pos_y)
            adb.press_back_key(self.device_id)
        u2d.sleep(1)
        app_name = app_name.replace('_', ' ')
        width, height = u2d.window_size()
        u2d.swipe(width / 2, height * 3 / 4, width / 2, height / 4, 0.1)
        u2d.sleep(1)
        search_box = u2d(textMatches=".*Search.*")
        if u2d(textMatches=".*Search.*").exists:
            search_box.click(timeout=5)
            u2d.sleep(1)
            u2utils.input_text(u2d, app_name)
            u2d.sleep(1)
        else:
            assert False, 'search box not found!'
        # s_app = u2d(text=app_package)[1]
        b = u2d.xpath(f'//*[@text="{app_name}"]').all()[1].info['bounds']
        start_position = [(b['left'] + b['right']) / 2, (b['top'] + b['bottom']) / 2]
        width = b['right'] - b['left']
        offset_x = (to_index - 1) * width
        middle_position = (start_position[0] + offset_x, start_position[1] + 100)
        time.sleep(0.5)
        u2d.drag(start_position[0], start_position[1], middle_position[0], middle_position[1], 0.5)

    def close_auto_arrange(self):
        u2d = self.u2d
        tos = adb.exec_cmd(self.device_id, 'getprop ro.build.version.release')[0]
        adb.open_settings_activity(self.device_id)
        u2d.sleep(1)
        if u2d(textMatches=".*Search.*").exists:
            search_box = u2d(textMatches=".*Search.*")
        else:
            assert False, 'search box not found'
        search_box.click(timeout=5)
        u2d.sleep(1)
        u2utils.input_text(u2d, 'Home Screen Settings')
        u2d.sleep(5)
        u2d.xpath('//*[@resource-id="android:id/icon"]').click_exists(timeout=5)
        u2d.sleep(1)
        auto_arrange_button = u2d.xpath("(//android.widget.Switch)[3]")

        if auto_arrange_button.info['checked']:
            auto_arrange_button.click(timeout=5)
        if not auto_arrange_button.exists:
            assert False, 'auto arrange button not found'

    def check_app_position(self, app_name, position):
        try:
            assert position in (1, 2, 3, 4), f"不支持判定位置 {position}"

            adb.press_home_key(self.device_id)
            time.sleep(0.3)
            adb.press_home_key(self.device_id)
            time.sleep(1)

            u2d = self.u2d
            elements = u2d.xpath(
                f'//*[contains(@resource-id, "workspace")]//android.view.ViewGroup//*[@text="{app_name}"]'
            ).all()
            if not elements:
                return False

            b = elements[0].info['bounds']
            [top_left_x, top_left_y], [_, _] = self.get_homeapp_x_y_for_index(position)

            return abs(b['left'] - top_left_x) < 5 and abs(b['top'] - top_left_y) < 5

        except Exception as e:
            # logging.info('位置不符合')
            return False

    def check_path_type(self, device_path):
        return adb.check_path_type(self.device_id, device_path)

    def make_phone_dir(self, path):
        return adb.make_dirs(self.device_id, path)

    def delete_file_or_dir(self, path):
        return adb.delete_file_or_dir(self.device_id, path)

    def push_file(self, src_path: Union[str, os.PathLike], target_path: Union[str, os.PathLike], overwrite=True):
        """
        将文件或文件夹推送到Android设备的指定路径。

        :param src_path: 源文件或文件夹路径
        :param target_path: 目标路径
        :param overwrite: 如果为True，允许覆盖已存在的文件；否则跳过
        """
        adb.push_file_ext(self.device_id, src_path, target_path, overwrite)

    def delete_except(self, target_dir, patterns: List[str]):
        """
        删除Android设备上指定目录下除匹配特定正则表达式的文件和文件夹。

        :param target_dir: 目标文件夹路径
        :param patterns: 要保留的文件名的正则表达式列表
        """
        device_id = self.device_id

        # 检查设备是否连接
        # result = subprocess.run(['adb', 'devices'], capture_output=True, text=True)
        # if device_id not in result.stdout:
        #     raise ValueError(f"Device {device_id} not connected.")

        # 获取目录下所有文件和文件夹
        cmd_list = [ADB_EXE, '-s', device_id, 'shell', f'ls "{target_dir}"']
        result = subprocess.run(cmd_list, capture_output=True, text=True, encoding='utf-8')

        if result.returncode != 0:
            # logs_p().log_error("Error listing directory:" + str(result.stderr))
            return

        # 分析结果，逐个文件进行正则匹配
        files_and_dirs = result.stdout.splitlines()
        for item in files_and_dirs:
            item_str = str(item)
            # 构建完整路径
            item_path = f"{target_dir}/{item_str}"

            # 检查是否匹配任意一个正则表达式
            if not any(re.match(pattern, item_str) for pattern in patterns):
                # 删除不匹配的文件或文件夹
                cmd_rm = [ADB_EXE, '-s', device_id, 'shell', f'rm -rf "{item_path}"']
                rm_result = subprocess.run(cmd_rm, capture_output=True, text=True, encoding='utf-8')

                if rm_result.returncode != 0:
                    logs_p().log_error(f"Error deleting {item_path}:", rm_result.stderr)
                # else:
                #     print(f"Deleted {item_path}")

    def check_file_exists(self, path):
        device_id = self.device_id
        try:
            # 使用ls命令检查文件或文件夹是否存在
            result = subprocess.run(
                [ADB_EXE, "-s", device_id, "shell", f"ls '{path}'"],
                capture_output=True,
                text=True,
                encoding='utf-8'
            )

            # 根据返回码判断文件或目录是否存在
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            # 如果adb命令执行异常，则抛出错误
            raise RuntimeError(f"ADB command failed with error: {e}")

    def list_dir(self, dir_path) -> List[Tuple[str, bool]]:
        """返回目录下的所有文件，返回元组列表，元组元素为文件名、是否是文件夹"""
        return adb.list_dir(self.device_id, dir_path)

    def input_text(self, text: str):
        """
        安全使用U2D打字，不会自动切换输入法到U2D输入法
        """
        u2utils.input_text(self.u2d, text)

    def press_enter_key(self):
        """
        安全使用U2D打字，发送回车符
        """
        u2utils.press_enter(self.u2d)

    @property
    def is_host_local_china(self):
        return misc_utils.is_host_local_china()

    def assert_wait_ui_obj(self,
                           u2o: Union[
                               uiautomator2.UiObject, uiautomator2.xpath.XPathSelector, uiautomator2.xpath.XMLElement, str],
                           pre_wait: float = 0.0, timeout: float = 5.0, post_wait: float = 0.5) -> Union[
        uiautomator2.UiObject, uiautomator2.xpath.XMLElement]:
        """
        等待指定的UI对象加载，如果其在指定时间没有加载成功，抛出异常。

        :param u2o: 目标UI对象，可以是UiObject、XPathSelector、XMLElement或字符串类型的XPath。
        :param pre_wait: 在查找UI对象之前等待的时间（秒），默认为0.0。
        :param timeout: 查找UI对象的超时时间（秒），默认为5.0。
        :param post_wait: 在找到UI对象后等待的时间（秒），默认为0.5。
        :return: 找到的UI对象（UiObject或XMLElement），如果未找到则抛出异常。
        """
        return u2utils.wait_ui_obj(self.u2d, u2o, pre_wait, timeout, post_wait, True)

    def click_desktop_icon(self, icon_name: str, timeout=1):
        self.u2d.xpath(f"//*[@text='{icon_name}' or @text='● {icon_name}']").click(timeout=timeout)

    def exist_desktop_icon(self, icon_name: str, timeout=-1.0):
        return self.u2d.xpath(f"//*[@text='{icon_name}' or @text='● {icon_name}']").wait(timeout=timeout)

    def wait_ui_obj(self,
                    u2o: Union[
                        uiautomator2.UiObject, uiautomator2.xpath.XPathSelector, uiautomator2.xpath.XMLElement, str],
                    pre_wait: float = 0.0, timeout: float = 5.0, post_wait: float = 0.5,
                    raise_on_not_exist: bool = False) -> Union[
        uiautomator2.UiObject, uiautomator2.xpath.XMLElement, None]:
        """
        等待指定的UI对象加载，但不执行点击操作。

        :param u2o: 目标UI对象，可以是UiObject、XPathSelector、XMLElement或字符串类型的XPath。
        :param pre_wait: 在查找UI对象之前等待的时间（秒），默认为0.0。
        :param timeout: 查找UI对象的超时时间（秒），默认为5.0。
        :param post_wait: 在找到UI对象后等待的时间（秒），默认为0.5。
        :param raise_on_not_exist: 如果为True，未找到UI对象时抛出异常，默认为False。
        :return: 找到的UI对象（UiObject或XMLElement），如果未找到则返回None（仅在raise_on_not_exist为False时）。
        """
        return u2utils.wait_ui_obj(self.u2d, u2o, pre_wait, timeout, post_wait, raise_on_not_exist)

    def click_wait(self, u2o: Union[
        uiautomator2.UiObject, uiautomator2.xpath.XPathSelector, uiautomator2.xpath.XMLElement, str],
                   pre_wait: float = 0.0, timeout: float = 5.0, post_wait: float = 0.5, no_raise: bool = False,
                   wait_after_click: float = 0.0, offset=(0.5, 0.5)) -> \
            Union[uiautomator2.UiObject, uiautomator2.xpath.XMLElement, None]:
        """
        等待指定的UI对象加载，并执行点击操作。

        :param u2o: 目标UI对象，可以是UiObject、XPathSelector、XMLElement或字符串类型的XPath。
        :param pre_wait: 在查找UI对象之前等待的时间（秒），默认为0.0。
        :param timeout: 查找UI对象的超时时间（秒），默认为5.0。
        :param post_wait: 在找到UI对象后等待的时间（秒），默认为0.5。
        :param no_raise: 如果为True，在找不到UI对象时不抛出异常，默认为False。
        :param wait_after_click: 如果大于0且perform_click为True，则在点击之后执行等待相应时间（秒）。
        :param offset: 点击的相对位置（中心就是0.5, 0.5）。
        :return: 找到的UI对象（UiObject或XMLElement），如果未找到则返回None（仅在no_raise为True时）。
        """
        return u2utils.click_wait(self.u2d, u2o, pre_wait, timeout, post_wait, no_raise, wait_after_click, offset)

    def click_and_sleep(self, u2o: Union[
        uiautomator2.UiObject, uiautomator2.xpath.XPathSelector, uiautomator2.xpath.XMLElement, str],
                        pre_wait: float = 0.0, timeout: float = 5.0, post_wait: float = 0.2, no_raise: bool = False,
                        wait_after_click: float = 1.0) -> \
            Union[uiautomator2.UiObject, uiautomator2.xpath.XMLElement, None]:
        """
        等待指定的UI对象加载，并执行点击操作（默认在点击后等待1秒，且查找到控件后再等待的时间缩短为0.2秒）。

        :param u2o: 目标UI对象，可以是UiObject、XPathSelector、XMLElement或字符串类型的XPath。
        :param pre_wait: 在查找UI对象之前等待的时间（秒），默认为0.0。
        :param timeout: 查找UI对象的超时时间（秒），默认为5.0。
        :param post_wait: 在找到UI对象后等待的时间（秒），默认为0.2。
        :param no_raise: 如果为True，在找不到UI对象时不抛出异常，默认为False。
        :param wait_after_click: 如果大于0且perform_click为True，则在点击之后执行等待相应时间（秒）。
        :return: 找到的UI对象（UiObject或XMLElement），如果未找到则返回None（仅在no_raise为True时）。
        """
        return u2utils.click_wait(self.u2d, u2o, pre_wait, timeout, post_wait, no_raise, wait_after_click)

    def get_appBehavior_logcat(self, tag_check=None):
        tags = ['APP_START_OCCURRED', 'APP_ANIMATION_OCCURRED', 'UI_ACTION_LATENCY', 'APP_TRANSITION_OCCURRED']
        tags_result = {}
        result = subprocess.run(['adb', '-s', self.device_id, 'logcat', '-d'], capture_output=True, text=True,
                                encoding='utf-8').stdout
        if tag_check is None:
            for tag in tags:
                if tag in result:
                    tags_result[tag] = "OK"
                else:
                    tags_result[tag] = "FAIL"
        else:
            if tag_check in result:
                tags_result[tag_check] = "OK"
            else:
                tags_result[tag_check] = "FAIL"
        return tags_result

    def assert_icon_exist(self, search_type='xpath', icon_path='', double_ckeck=False, click=False):
        def _check_icon(get_icon_func):
            icon_exist = get_icon_func().wait(timeout=2)
            if icon_exist:
                icon_search = get_icon_func()
                if click:
                    icon_search.click()
                return True, icon_search
            else:
                if double_ckeck:
                    self.press_back_key(1)
                    time.sleep(1)
                    icon_search_2 = get_icon_func().wait(timeout=2)
                    if icon_search_2:
                        icon_search = get_icon_func()
                        if click:
                            icon_search.click()
                        return True, icon_search
                    else:
                        return False, ''
                else:
                    return False, ''

        if search_type == 'xpath':
            return _check_icon(lambda: self.u2d.xpath(icon_path))
        elif search_type == 'descriptionContains':
            return _check_icon(lambda: self.u2d(descriptionContains=icon_path))
        elif search_type == 'description':
            return _check_icon(lambda: self.u2d(description=icon_path))
        elif search_type == 'text':
            return _check_icon(lambda: self.u2d(text=icon_path))
        elif search_type == 'textContains':
            return _check_icon(lambda: self.u2d(textContains=icon_path))
        elif search_type == 'resourceId':
            return _check_icon(lambda: self.u2d(resourceId=icon_path))
        elif search_type == 'className':
            return _check_icon(lambda: self.u2d(className=icon_path))

    def open_playstore_page(self, package_name: str):
        return adb.open_playstore_page(self.device_id, package_name)

    def kill_monkey_process(self):
        """
        在 Android 设备上查找并终止所有 com.android.commands.monkey 进程。
        """
        try:
            # 获取进程列表，过滤出 Monkey 进程
            # 注意：部分 Android 版本 ps 命令输出格式可能不同，如需要可改为 ps -A 或 ps -ef
            ps_cmd = [ADB_EXE, '-s', self.device_id, "shell",
                      "ps |grep -v grep |grep -F com.android.commands.monkey | awk " + "'{print $2}'"]
            ps_output = subprocess.check_output(ps_cmd, text=True)
            killed = False

            for line in ps_output.splitlines():
                # 不同 Android 版本中 PID 列可能在索引 1 或 2，尝试通用取法
                # pid = parts[1] if parts[1].isdigit() else parts[2]
                subprocess.run([ADB_EXE, '-s', self.device_id, "shell", "kill", "-9", line])
                #t_log.debug(f"[KILL-MONKEY] Killed Monkey process with PID {line}")
                killed = True

            if not killed:
                pass
                #t_log.debug("[KILL-MONKEY] No Monkey process found to kill.")
        except subprocess.CalledProcessError as e:
            t_log.debug(f"[KILL-MONKEY] Failed to list processes: {e}")
        except Exception as e:
            t_log.debug(f"[KILL-MONKEY] Unexpected error in kill_monkey_process: {e}")

    def run_monkey_test(self, package_name: str,
                        duration_seconds: int,
                        seed: Optional[int] = None,
                        throttle: int = 200,
                        log_path: Optional[str] = None):
        """
        对指定包运行 Monkey 测试一定时间，并在到期时自动终止 Monkey 进程。
        """

        # 自动生成随机种子（如果未指定）
        if seed is None:
            seed = random.randint(1, 10_000_000)
            t_log.debug(f"[MONKEY] Auto-generated seed: {seed}")

        monkey_cmd = [
            ADB_EXE, '-s', self.device_id, "shell", "monkey",
            "-p", package_name,
            "--throttle", str(throttle),
            "--ignore-crashes",
            "--ignore-timeouts",
            "--monitor-native-crashes",
            "--kill-process-after-error",
            "-s", str(seed),
            "-v", "-v", "-v",
            str(100_000_000)  # 大量事件，最终由时间控制终止
        ]

        t_log.debug(f"[MONKEY] Starting Monkey on package: {package_name}")
        t_log.debug(f"[MONKEY] Duration: {duration_seconds} sec | Throttle: {throttle} ms | Seed: {seed}")

        # 启动 Monkey
        log_file = None
        if log_path:
            log_file = open(log_path, "w")
            output = log_file
            t_log.debug(f"[MONKEY] Monkey log will be saved to: {log_path}")
        else:
            output = None

        process = subprocess.Popen(monkey_cmd, stdout=output, stderr=subprocess.STDOUT)

        def stop_monkey_after_timeout():
            time.sleep(duration_seconds)
            t_log.debug("[MONKEY] Duration reached. Killing Monkey process on device...")
            self.kill_monkey_process()

        timer_thread = threading.Thread(target=stop_monkey_after_timeout)
        timer_thread.start()

        process.wait()
        timer_thread.join()

        if log_file:
            log_file.close()

    def close_data_warn(self):
        """关闭流量提醒"""
        self.restart_settings_activity()
        self.click_wait(self.u2d(textMatches=".*Search.*"), pre_wait=1, timeout=10, post_wait=1)
        time.sleep(1)
        u2utils.input_text(self.u2d, 'data usage')
        self.click_wait('//android.widget.TextView[@text="Data Usage "]', pre_wait=1, timeout=15, post_wait=2)
        time.sleep(4 if self.is_sprd else 3)
        self.click_wait('//android.widget.TextView[@text="Data Usage"]', pre_wait=1, timeout=15, post_wait=2)
        time.sleep(1)
        self.u2d.xpath('//*[@text="Agree"]').click_exists(timeout=2)
        if self.u2d.xpath('//*[@text="Your package period is?"]').exists:
            self.und_u2.click_back()
        for i in range(2):
            self.u2d.swipe(0.5, 0.8, 0.5, 0.2)
            time.sleep(1)
        self.u2d.xpath('//*[@text="Settings"]').click()
        time.sleep(1)
        if self.u2d.xpath('//*[@text="Allow"]').exists:
            self.u2d.xpath('//*[@text="Allow"]').click()
            # 重新进
            for i in range(3):
                self.u2d.swipe(0.5, 0.8, 0.5, 0.2)
            self.u2d.xpath('//*[@text="Settings"]').click()
        self.click_wait('//*[@text="When data plan is used up"]', timeout=10, post_wait=1)
        self.click_wait('//*[@text="Don\'t Remind Me"]', timeout=10, post_wait=1)
        self.press_home_key()
        self.stop_settings()

    def close_sidebar(self):
        """关闭侧边栏"""
        adb.exec_cmd(self.device_id, 'settings put global smart_panel_status 69904')

    def assert_time_with_pc(self, threshold_seconds=10):
        """检查Android手机和PC主机的时间差"""
        time_difference = adb.measure_device_time_offset_ms(self.device_id) / 1000.0

        if abs(time_difference) > threshold_seconds:
            raise Exception(
                f'The time difference between the phone and the computer is {time_difference}, exceeding the threshold {threshold_seconds}.')
        else:
            t_log.debug(f'The time difference between the phone and the computer is {time_difference}')

    def check_wifi_network_connection(self, check_overseas_net: bool = True):
        if not adb.is_wifi_open(self.device_id):
            self.open_close_wifi(True)
            time.sleep(5)
        try:
            self.check_network_connections(check_overseas_net)
        except Exception:
            raise Exception(f"Wifi network connection check failed (overseas net: {check_overseas_net})")

    def close_wifi_auto_switch(self):
        adb.exec_cmd(self.device_id, 'settings put global key_wifi_cell_switch 0')
        adb.exec_cmd(self.device_id, 'settings put global key_wifi_smart_assistant_switch 0')

    def measure_device_time_offset_ms(
            self,
            samples: int = 5,
            calib_samples: int = 5,
            sleep_interval: float = 0.05
    ) -> Optional[float]:
        """
        高精度测量并返回指定 ADB 设备与主机时间的偏差（毫秒），

        :param samples: 正式测量采样次数（>=3 推荐）
        :param calib_samples: 校准空跑采样次数
        :param sleep_interval: 采样间隔（秒）
        """
        return adb.measure_device_time_offset_ms(self.device_id, samples, calib_samples, sleep_interval)

    def wait_for_idle(self):
        """
        等待当前应用进入idle状态
        """
        time.sleep(2)

    def close_auto_update(self):
        """
        关闭Google GMS套件自动更新
        有3处触发更新的:
        1.setting里面account,有个Automatically sync app data
        2.setting里面developer options,有个Automatic system update
        3.playstore里面setting,有个Auto-update apps
        """
        # Automatically sync app data 没有系统参数
        self.restart_app('com.android.settings')
        if self.u2d(textMatches=".*Search.*").exists:
            self.u2d(textMatches=".*Search.*").click(timeout=5)
        else:
            self.click_wait('//android.widget.TextView[@text="Search"]', timeout=8, post_wait=1)
        u2utils.input_text(self.u2d, 'Automatically')
        self.click_wait('//android.widget.TextView[@text="Automatically Sync App Data "]', timeout=15, post_wait=1)
        time.sleep(1)
        self.u2d.xpath('//android.widget.Switch[@checked="true"]').click_exists(timeout=2)
        self.u2d.xpath('//*[@text="OK"]').click_exists(timeout=2)
        self.u2d.app_stop('com.android.settings')

        # 关闭Automatic system update
        adb.set_settings_value(self.device_id, 'global', 'ota_disable_automatic_update', 1)

        # Auto-update apps
        self.restart_app('com.android.vending')
        self.wait_ui_obj('//*[@text="Apps"]', timeout=10, post_wait=1)
        self.u2d(resourceId="com.android.vending:id/0_resource_name_obfuscated").click_exists(timeout=2)
        self.u2d(description="Options").click_exists(timeout=2)
        time.sleep(2)
        self.u2d.swipe(0.5, 0.8, 0.5, 0.2)
        self.click_wait('//*[@text="Settings"]', timeout=8, post_wait=1)
        time.sleep(2)
        self.u2d.xpath('//*[@text="Got it"]').click_exists(timeout=2)
        if not self.u2d.xpath('//*[@text="Network preferences"]').exists:
            self.u2d.xpath('//*[@text="General"]').click()
        self.click_wait('//*[@text="Network preferences"]', timeout=8, post_wait=1)
        self.click_wait('//*[@text="Auto-update apps"]', timeout=8, post_wait=1)
        self.click_wait('//*[@text="Don\'t auto-update apps"]', timeout=8, post_wait=1)
        self.u2d.app_stop('com.android.vending')

    def swipe_recent_card_and_check_reach_edge(self, swipe_left=True, find_icon_name=None) -> int:
        def _find_icon_name(tv_texts):
            if not find_icon_name:
                return False
            for elem in tv_texts:
                if find_icon_name.startswith(elem.rstrip('.')):
                    return True
            return False

        direction = 'left' if swipe_left else 'right'
        xpath = '//android.widget.TextView'
        region = (0.2, 0.1, 0.8, 0.5)
        before = [tv.text for tv in u2utils.xpath_within_region(self.u2d, xpath, region=region)]
        if _find_icon_name(before):
            return 2
        self.und_u2.swipe_direction(direction, 0.2, speed=100)
        time.sleep(0.2)
        after = [tv.text for tv in u2utils.xpath_within_region(self.u2d, xpath, region=region)]
        if _find_icon_name(after):
            return 2
        return 1 if before == after else 0

    def find_recent_app(self, full_icon_name: str, from_right_to_left=True):
        self.press_app_switch_key()
        time.sleep(1)

        _conti_swipe_direction = ('right' if from_right_to_left else 'left')

        def _conti_swipe(count: int):
            for _ in range(count):
                self.und_u2.swipe_direction(_conti_swipe_direction, 0.7, speed=400)
                time.sleep(0.1)
            time.sleep(0.4)

        _conti_swipe(5)
        for _ in range(10):
            if self.swipe_recent_card_and_check_reach_edge(not from_right_to_left):
                break
            _conti_swipe(2)
        else:
            raise Exception('Can not swipe recent cards to edge!')

        _find_result = 0
        for _ in range(100):
            _find_result = self.swipe_recent_card_and_check_reach_edge(from_right_to_left, full_icon_name)
            if _find_result:
                break
        if _find_result != 2:
            raise Exception(f'Can not find recent card named "{full_icon_name}"!')

    def _generate_phone_number(self, prefix: str = "199") -> str:
        """生成11位以 prefix 开头的随机手机号"""
        suffix = ''.join(random.choices('0123456789', k=8))
        return prefix + suffix

    def inster_contacts(self,pre_name:str="test",pre_phone:str="199",count:int=2)->None:
        """
        添加联系人
        """
        for i in range(count):
            # 添加一列
            self.u2d.shell(self.RAW_CONTACTS_SHELL)
            #查询数据库中所有联系人id
            rows:str = self.u2d.shell(self.QUERY_CONTACTS_SHELL).output
            ids:list[str] = re.findall(r'_id=(\d+)', rows)
            if not ids:
                t_log.error("No raw_contacts found")
                return
                # 找最大_id
            max_id:int = max(map(int, ids))
            t_log.info(f"Max _id:{max_id}")
            self.u2d.shell(self.INSERT_NAME_SHELL.format(raw_contact_id=max_id, contact_name=f"{pre_name}_{i}"))
            phone_number:str = self._generate_phone_number(pre_phone)
            self.u2d.shell(self.INSERT_PHONE_SHELL.format(raw_contact_id=max_id, phone_number=phone_number))
    def delete_all_contacts(self)->None:
        """
        删除所有联系人（通过 content provider 删除 raw_contacts）
        """
        self.u2d.shell(self.DELETE_ALL_CONTACTS_SHELL)
    def delete_contact_by_name(self, name):
        """
        通过联系人姓名删除联系人
        """
        # 查询联系人ID
        query_result:str = self.u2d.shell(self.QUERY_CONTACTS_BY_NAME_SHELL.format(name=name)).output
        match = re.search(r'_id=(\d+)', query_result)
        if not match:
            t_log.error(f"未找到联系人: {name}")
            return
        contact_id:str = match.group(1)

        self.u2d.shell(self.DELETE_CONTACTS_BY_ID_SHELL.format(contact_id=contact_id))

    def insert_call_logs(self, count=5, pre_phone="199"):
        """
        向 call_log 中插入通话记录
        """
        for i in range(count):
            phone_number = self._generate_phone_number(pre_phone)
            call_type = random.choice([1, 2, 3])  # 1: INCOMING, 2: OUTGOING, 3: MISSED
            duration = random.randint(5, 360) if call_type in [1, 2] else 0
            timestamp = int(time.time() * 1000)  # 毫秒时间戳
            self.u2d.shell(self.INSERT_ALL_CALL_SHELL.format(phone_number=phone_number,call_type=2,timestamp=timestamp,duration=duration,index=1))

    def delete_call_logs(self):
        """
        删除设备上的所有通话记录。
        """
        result = self.u2d.shell(self.DELETE_ALL_CALL_SHELL)
        if result.exit_code == 0:
            t_log.info("✅ 通话记录删除成功")
        else:
            t_log.error(f"❌ 删除失败: {result.output}")

    def insert_sms(self, address=None, body=None, count=1):
        for _ in range(count):
            number = address or self._generate_phone_number()
            content = body or f"PDM TEST{random.randint(1000, 9999)}"
            self.u2d.shell(self.INSERT_MESSAGE_SHELL.format(number=number,content=content))

    def delete_all_sms(self):
        """
        删除所有短信记录
        """
        self.u2d.shell(self.DELETE_MESSAGE_SHELL)
    def enter_small_window(self,package):
        """
        进入小窗
        """
        command = f"appops set {package} SYSTEM_ALERT_WINDOW allow"
        t_log.info(f"执行命令: {command}")
        self.u2d.shell(command)

    def get_launcher_icon(self,package_name:str):
        icon_view = self.u2d.xpath(f'//*[@resource-id="{package_name}:id/icon"]')
        if icon_view.wait(timeout=5):
            all_app_icon = icon_view.all()
            return all_app_icon
        else:
            raise Exception('应用图标不存在')

    def xpath_click(self, xpath, instance=0, timeout=3, sleep_time=1):
        """
        通过xpath点击
        """
        d1 = self.u2d.xpath(xpath)
        if d1.wait(timeout=timeout):
            d1.click()
            time.sleep(sleep_time)

    def xpath_click_must(self, xpath, instance=0, timeout=3, sleep_time=1):
        """
        通过xpath点击
        """
        self.u2d.xpath(xpath).wait(timeout=timeout)
        self.u2d.xpath(xpath).click()
        time.sleep(sleep_time)

    def xpath_get(self, xpath, instance=0, timeout=3, sleep_time=1):
        """
        通过xpath点击
        """
        d1 = self.u2d.xpath(xpath)
        if d1.wait(timeout=timeout):
            return d1

    def check_is_swip_success(self, xpath):
        # 获取滚动控件的第一个子元素的结尾位置在哪里，以后判断是否改变
        child1 = self.xpath_get(f"{xpath}/child::*[1]")
        assert child1 is not None
        (lx, ly, rx, ry) = child1.get().bounds
        return ry

    def data_load(self, screen_width, sscreen_height, xpath, scroll_time=4):
        """
        数据加载,要做到往下滑动的时候必须是有效滑动，可能有时候网络不好就是无效的滑动
        要做到，向上滑动的时候不能滑动到顶部造成页面刷新，所以先进行5次有效向下滑动，然后2次再大幅的向上滑动，再小步的一直向上滑动
        """
        # 按照屏幕比例，从屏幕中心滑动，y轴上，从屏幕的1/4到3/4滑动，先向下滚动5次，再向上滚动5次
        # scroll_time = 4

        temp_scroll_time = scroll_time
        child1_down_y = self.check_is_swip_success(xpath)

        x = str(int(screen_width / 2))
        y_up = str(int(sscreen_height / 4))
        y_down = str(int(sscreen_height*3 / 4))

        for i in range(25):
            self.u2d.shell(["input", "swipe", x, y_down, x, y_up, "100"])
            time.sleep(2)
            child1_down_y_temp = self.check_is_swip_success(xpath)
            if child1_down_y != child1_down_y_temp:
                child1_down_y = child1_down_y_temp
                scroll_time = scroll_time - 1

            if scroll_time <= 0:
                break

        assert scroll_time <= 0, "没有达到4次有效滑动"

        for i in range(max(2, temp_scroll_time-2)):
            self.u2d.shell(["input", "swipe", x, y_up, x, y_down, "100"])
            time.sleep(1)
        time.sleep(2)


    def lock_screnn_status(self):
        result = self.u2d.shell("dumpsys window | grep mDreamingLockscreen").output
        return bool(result.split("=")[1])

