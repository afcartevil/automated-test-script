import os
import re
import subprocess
import threading
import time
from datetime import datetime, timedelta
from typing import Union, List, Optional, cast, Type, TypeVar, Sequence
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
from powertrde.utils.u2_extends.u2utils import U2DeviceProtocol, U2ObjectProtocol, U2XMLElementProtocol, \
    connect_u2_device
from tpy_aw import aw_registry
from tpy_aw.aw_configs.supported_os_config import SupportedOS
from tpy_aw.u2d_helper_constants import U2DHelperConstants
from tpy_aw.u2d_helper_mobilelog import U2DHelperMobileLog
from tpytest.aw_framework.aw_base import AwBase
from typing import Tuple

T = TypeVar('T')


class U2DTestHelper(U2DHelperMobileLog, U2DHelperConstants, AwBase):
    aw_category = 'u2_helper'
    aw_name = ''

    def __init__(self, u2d_or_device_id: Union[uiautomator2.Device, U2DeviceProtocol, str]):
        super().__init__(u2d_or_device_id)
        self.known_country_codes = {"86", "254", "92", "63", "62", "234"}
        self._watcher_register = None
        self._bound_und = None

    @property
    def adb(self):
        return adb

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

    def get_app_aw(self, app_name: str, variant: Optional[str] = None, no_raise: bool = False,
                   app_nickname: Optional[str] = None, base_type: Optional[type] = None):
        try:
            from tpy_aw.aw_registry import get_aw_app
            return get_aw_app(self, app_name, variant, app_nickname, base_type)
        except Exception:
            if not no_raise:
                raise
        return None

    def get_casted_app_aw(self, cast_type: Type[T], app_name: Optional[str] = None, variant: Optional[str] = '',
                          no_raise: bool = False, app_nickname: Optional[str] = '') -> Optional[T]:
        return cast(cast_type,
                    self.get_app_aw(app_name or cast_type.aw_name,
                                    (cast_type.variant_key if variant is None else variant), no_raise,
                                    (cast_type.aw_nickname if app_nickname is None else app_nickname), cast_type))

    def get_feature_aw(self, ft_name: str, variant: Optional[str] = None, no_raise: bool = False,
                       ft_nickname: Optional[str] = None, base_type: Optional[type] = None):
        try:
            from tpy_aw.aw_registry import get_aw_feature
            return get_aw_feature(self, ft_name, variant, ft_nickname, base_type)
        except Exception:
            if not no_raise:
                raise
        return None

    def get_casted_feature_aw(self, cast_type: Type[T], ft_name: Optional[str] = None, variant: Optional[str] = '',
                              no_raise: bool = False, ft_nickname: Optional[str] = '') -> Optional[T]:
        return cast(cast_type, self.get_feature_aw(ft_name or cast_type.aw_name,
                                                   (cast_type.variant_key if variant is None else variant), no_raise,
                                                   (cast_type.aw_nickname if ft_nickname is None else ft_nickname),
                                                   cast_type))

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

    def get_phone_volume(self, volume_type, choose_info):
        """
           adb获取手机音量
           :param volume_type: STREAM_MUSIC: 媒体/音乐音量（最常用） STREAM_VOICE_CALL：通话音量,
           STREAM_SYSTEM: 系统音量（提示音）, STREAM_RING: 媒体/音乐音量（最常用）

           :param choose_info：Min MaxstreamVolume
        """
        return int(adb.exec_cmd(self.device_id,
                                f' dumpsys audio 2>/dev/null | sed -n \'/{volume_type}:/,/^$/p\' | sed -n \'s/.*{choose_info}://p\' | head -1')[0])

    def adjust_phone_music_volume_to_max(self):
        """
        针对媒体音量调节最大（抖音用例）
        """
        music_volume_max = self.get_phone_volume(volume_type='STREAM_MUSIC', choose_info='Max')
        for _ in range(20):
            if self.get_phone_volume(volume_type='STREAM_MUSIC', choose_info='streamVolume') >= music_volume_max:
                break
            self.adjust_phone_volume('up')
            time.sleep(0.1)

    def is_audio_playing(self):
        """
        判断手机是否有音乐在播放
        :return: True 表示有音频播放，False 表示没有
        """
        # 先获取完整的音频策略信息，避免引号嵌套问题
        result = adb.exec_cmd(self.device_id, 'dumpsys media.audio_policy')
        if not result:
            return False

        # 在Python中解析输出，查找是否包含AudioTrack active
        full_output = '\n'.join(result)
        return 'AudioTrack active' in full_output

    def get_audio_playing_app_uid(self):
        """
        如果后台有音乐播放，返回播放音乐应用的 UID
        :return: UID 字符串，如果返回为空则说明没有音乐在播放
        """
        # 分步执行，避免复杂的管道命令引号嵌套问题
        # 先获取完整的音频策略信息
        result = adb.exec_cmd(self.device_id, 'dumpsys media.audio_policy')
        if not result:
            return ''

        # 在Python中解析输出，查找AudioTrack active后的uid
        full_output = '\n'.join(result)
        lines = full_output.split('\n')

        for i, line in enumerate(lines):
            if 'AudioTrack active' in line:
                # 向后查找最多5行，找到包含uid的行
                for j in range(i, min(i + 6, len(lines))):
                    if 'uid' in lines[j]:
                        # 提取uid值，格式类似：uid 10292; ...
                        import re
                        match = re.search(r'uid\s+(\d+)', lines[j])
                        if match:
                            return match.group(1)
        return ''

    def get_package_name_by_uid(self, uid: str):
        """
        根据 UID 号返回应用的包名
        :param uid: 应用的 UID，例如 "10292"
        :return: 应用的包名，如果未找到则返回空字符串
        """
        # 先获取所有包的列表信息
        result = adb.exec_cmd(self.device_id, 'cmd package list packages -U')
        if not result:
            return ''

        # 在Python中查找匹配的uid
        # 格式：package:com.example.app uid:10292
        import re
        for line in result:
            if f'uid:{uid}' in line:
                match = re.search(r'package:([^\s]+)', line)
                if match:
                    return match.group(1)
        return ''

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

    def clear_recent_apps_by_ui(self, post_clear_remaining_cards_by_swipe=False):
        # need_retain_phone_monitor = (retain_phone_monitor_app and adb.package_is_installed(self.device_id,
        #                                                                                    self.PHONE_MONITOR_APP_PACKAGE))
        # if need_retain_phone_monitor:
        #     self.press_home_key(2)
        #     time.sleep(0.5)
        #     self.start_activity(self.PHONE_MONITOR_APP_MAIN_ACTIVITY)
        #     time.sleep(1)
        time.sleep(2)
        self.press_app_switch_key()
        time.sleep(1)
        adb.tap_on_screen_by_percent(self.device_id, 0.5, 0.87)
        time.sleep(2)
        # if need_retain_phone_monitor:
        #     time.sleep(0.5)
        #     self.press_app_switch_key()
        #     time.sleep(1)
        #     self.und_u2.swipe_direction('up', speed=350)
        #     self.press_back_key()
        #     time.sleep(1)
        if post_clear_remaining_cards_by_swipe:
            self.clear_recent_cards_by_swipes()

    def clear_recent_cards_by_swipes(self, call_recent_ui_first=True):
        if call_recent_ui_first:
            self.press_app_switch_key()
            time.sleep(1)
        v_id = None
        for _ in range(255):
            _c, _id = self._count_first_list_or_scroll_children_with_id(timeout=2)
            if not v_id:
                v_id = _id
            if not _c or not _id or _id != v_id:
                self.press_back_key()
                break
            self.und.swipe_direction('up', speed=300)
            time.sleep(0.6)
        time.sleep(1)

    def end_system_phone_call(self):
        if adb.is_phone_calling(self.device_id):
            adb.press_end_call_key(self.device_id)

    def press_key(self, keycode):
        adb.press_key(self.device_id, keycode)

    def set_fake_battery_level(self, level):
        adb.exec_cmd(self.device_id, f'dumpsys battery set level {level}')

    def reset_fake_battery_level(self):
        adb.reset_battery_status(self.device_id)

    def set_fake_battery_unplug(self):
        adb.exec_cmd(self.device_id, 'dumpsys battery unplug')

    def reset_fake_battery_unplug(self):
        adb.exec_cmd(self.device_id, 'dumpsys battery set usb 1')

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
            if self.u2d.xpath(self.get_icon_name_xpath(app_icon_name)).exists:
                return True
            self.press_home_key(times=1)
        else:
            self.press_home_key(times=3)

        time.sleep(0.5)
        for i in range(10):
            app_icon = self.u2d.xpath(self.get_icon_name_xpath(app_icon_name)).wait(timeout=1)
            if app_icon:
                return True
            else:
                self.und_u2.swipe_direction('left', speed=350)
                time.sleep(1)
        return False

    def get_icon_name_xpath(self, app_icon_name: str):
        # 核心修改：使用normalize-space处理@text，去除首尾任意数量空格后匹配
        xpath_expr = (
            f'//*['
            f'normalize-space(@text)="{app_icon_name}" '
            f'or normalize-space(@text)="● {app_icon_name}"'
            f']'
        )
        return xpath_expr

    def start_app_from_desktop_via_ui(self, app_icon_name: Union[str, Sequence[str]]):
        """
        启动桌面应用
        Args:
            app_icon_name: 可以是字符串（单个应用）或字符串序列（多个应用）
        """
        if isinstance(app_icon_name, str):
            # 单个应用的情况
            if not self.search_app_from_desktop_via_ui(app_icon_name):
                raise Exception(f'Not found APP "{app_icon_name}" in desktop!')
            self.u2d.xpath(self.get_icon_name_xpath(app_icon_name)).click(timeout=1)
        elif isinstance(app_icon_name, Sequence):
            # 多个应用的情况
            found_any = False
            for icon_name in app_icon_name:
                if self.search_app_from_desktop_via_ui(icon_name):
                    self.u2d.xpath(self.get_icon_name_xpath(icon_name)).click(timeout=1)
                    found_any = True
                    time.sleep(0.5)
                    break
            if not found_any:
                raise Exception(f'Not found any of the APPs "{app_icon_name}" in desktop!')
        else:
            raise TypeError(f"app_icon_name must be str or Sequence[str], got {type(app_icon_name)}")

    def find_desktop_icon_position(self, app_icon_name: str, index: int = 1):
        """
        在桌面上滑动查找app图标，返回该图标的坐标信息
        多个相同名字的图标要在同一个界面 ( 系统messages, google messages )
        :param app_icon_name: app图标名字
        :param index: 返回第几个图标的坐标，默认为1（第一个）
        :return: 元组 (top_left, bottom_right, center)
                 - top_left: 左上角坐标 (x, y)
                 - bottom_right: 右下角坐标 (x, y)
                 - center: 中心坐标 (x, y)
                 如果找不到，返回 None
        """
        try:
            logs_p().log(f'开始在桌面查找图标: {app_icon_name}，目标索引: {index}')

            # 确保索引至少为1
            if index < 1:
                logs_p().log(f'索引值 {index} 无效，使用默认值 1')
                index = 1

            # 先回到桌面
            if not self.is_now_in_desktop:
                self.press_home_key(times=3)
            else:
                self.press_home_key(times=1)
            time.sleep(0.5)

            # 最多滑动 10 页查找
            for page in range(10):
                logs_p().log(f'正在搜索第 {page + 1} 页')

                # 查找当前页面上的所有匹配图标
                icons = self.u2d.xpath(self.get_icon_name_xpath(app_icon_name)).all()

                if icons:
                    logs_p().log(f'在第 {page + 1} 页找到 {len(icons)} 个匹配的图标')

                    # 检查是否有足够的图标
                    if len(icons) >= index:
                        # 获取指定索引的图标（索引从1开始，数组从0开始）
                        target_icon = icons[index - 1]
                        bounds = target_icon.info['bounds']

                        # 计算坐标
                        top_left = (bounds['left'], bounds['top'])
                        bottom_right = (bounds['right'], bounds['bottom'])
                        center = (
                            (bounds['left'] + bounds['right']) / 2,
                            (bounds['top'] + bounds['bottom']) / 2
                        )

                        logs_p().log(f'找到第 {index} 个图标 "{app_icon_name}"')
                        logs_p().log(f'左上角: {top_left}, 右下角: {bottom_right}, 中心: {center}')

                        return top_left, bottom_right, center
                    else:
                        logs_p().log(f'当前页只有 {len(icons)} 个图标，但需要第 {index} 个，继续搜索')

                # 滑动到下一页
                if page < 9:  # 最后一页不需要再滑动
                    self.und_u2.swipe_direction('left', speed=350)
                    time.sleep(1)

            logs_p().log(f'未找到第 {index} 个图标 "{app_icon_name}"')
            return None

        except Exception as e:
            logs_p().log(f'查找桌面图标时出错: {e}')
            return None

    def change_app_from_recent(self, app_icon_name, include_press_recent=True):
        if include_press_recent:
            self.press_recent_key()
            time.sleep(2)
        self.u2d.swipe(0.8, 0.5, 0.2, 0.5)
        click_bool = False
        for i in range(5):
            time.sleep(2)
            app = self.u2d.xpath(self.get_icon_name_xpath(app_icon_name))
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
        return adb.grant_all_runtime_permissions(self.device_id, app_package_name)

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

    def reboot_and_wait_complete(self, execute_reboot=True):
        if execute_reboot:
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
        adb.exec_cmd(self.device_id,
                     'ime set com.google.android.inputmethod.latin/com.android.inputmethod.latin.LatinIME')
        adb.DISABLE_ADB_ERROR_OUTPUT = False
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
            sim_title_group_xpath = '//*[@resource-id="com.android.settings:id/title" or @resource-id="com.android.settings:id/tran_iv_next"]'
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
        time.sleep(10)
        self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/ivClose"]').click_exists(timeout=5)
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
                        self._handle_popup_dialogs()
                        time.sleep(1)
                        break
            if not self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/ivStartAfterBg"]').exists:
                self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/svStart"]').click()
                self._handle_popup_dialogs()
                if self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/tvCancel"]').exists:
                    self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/tvCancel"]').click()
                    self._handle_popup_dialogs()
                    time.sleep(3)
                    self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/svStart"]').click()
                    self._handle_popup_dialogs()
        else:
            if self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/ivStartAfterBg"]').exists:
                self.u2d.xpath('//*[@resource-id="com.bananago.speed:id/svStart"]').click()
                self._handle_popup_dialogs()

        if not no_return_home:
            self.u2d.click(0.5, 0.979)

    def _handle_popup_dialogs(self, timeout: int = 3):
        """
        处理VPN操作过程中可能出现的各种弹窗
        """
        # 常见的弹窗按钮文本
        popup_buttons = [
            "OK",
        ]

        for button_text in popup_buttons:
            if self.u2d.xpath(f'//*[@text="{button_text}"]').click_exists(timeout=timeout):
                time.sleep(0.5)
                break

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
        try:
            launchers = set()
            if self.phone_os_info.key != 'UNKNOWN':
                launchers.add(self.phone_os_info.launcher)
            else:
                raise Exception('The launcher must not be unknown!')
        except Exception:
            launchers = SupportedOS.get_all_launchers()

        packages = set()

        # 获取最近任务的输出信息
        output = subprocess.check_output(
            [ADB_EXE, "-s", self.device_id, "shell", "dumpsys", "activity", "recents"]).decode('utf-8')

        # 使用正则表达式来解析可见的最近任务
        visible_tasks = re.findall(r'\* RecentTaskInfo #[0-9]+:\s+id=(\d+).*?cmp=([^ ]+)', output, re.DOTALL)

        # 遍历每个可见的最近任务并关闭
        for task_id, component in visible_tasks:
            # 在这里可以添加逻辑，决定是否关闭某个特定的任务。例如，排除掉Launcher
            package = component.split('/')[0]
            if package not in launchers:
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

    def grant_common_high_level_permissions(self, package_name: str):
        adb.granting_common_high_level_permissions(self.device_id, package_name)

    def grant_high_level_permission(self, package_name: str, permission: str):
        adb.granting_high_level_permission(self.device_id, package_name, permission)

    def is_app_persistent(self, package_name):
        return adb.is_package_persistent(self.device_id, package_name)

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
        self.grant_common_high_level_permissions(package_name)

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

    # ---------------------- Low-end policy helpers ----------------------
    @property
    def is_low_end(self) -> bool:
        """是否低端机。

        判定规则：
        根据 CPU 类型与平台判断：
           - CPU 型号包含 "G100" 视为低端机；
           - 若平台为展锐且 CPU 型号包含 "T620" 或 "T615"，视为低端机
        """
        cpu_name = adb.detect_cpu_model_name(self.device_id).upper()
        if 'G100' in cpu_name:
            return True
        # 展锐平台 + T620/T615 判定
        is_sprd_platform = (self.tran_cpu_platform == 'sprd') or self.is_sprd
        if is_sprd_platform and (('T620' in cpu_name) or ('T615' in cpu_name)):
            return True

        return False

    def get_time(self):
        """获取Android手机的当前时间"""
        result = adb.exec_cmd(self.device_id, "date +'%Y-%m-%d %H:%M:%S'")[0]
        phone_time = datetime.strptime(result, '%Y-%m-%d %H:%M:%S')
        return phone_time

    @property
    def is_hotspot_open(self):
        return adb.is_hotspot_open(self.device_id)

    def assert_hotspot_closed(self):
        assert not adb.is_hotspot_open(self.device_id), 'Hotspot is still open'

    def open_close_hotspot_by_adbui(self, is_open):
        current_state = self.is_hotspot_open
        # 如果当前状态已经符合目标状态，则无需操作
        if current_state == is_open:
            return
        self.screen_on_and_unlock()
        self.press_home_key(times=3)
        adb.exec_cmd(self.device_id, 'am start -a android.settings.TETHER_SETTINGS')
        time.sleep(3)
        success = False
        # 尝试多种可能的开关定位方式
        switch_selectors = [
            '//android.widget.Switch',
            '//*[@resource-id="android:id/switch_widget"]',
            '(//*[@text="Personal Hotspot"])[2]',

        ]
        for selector in switch_selectors:
            switch_elm = self.u2d.xpath(selector)
            if switch_elm.exists:
                switch_elm.click(timeout=2)
                success = True
                time.sleep(2)
                break
        if not success:
            Exception('Failed to switch to hotpot')

        self.u2d.app_stop('com.android.settings')

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
        self.click_exists('//*[@text="Hotspot & Connections"]')
        u2d.sleep(2)
        self.u2d(textContains='Airplane').click(timeout=5)
        u2d.sleep(3)
        u2d.app_stop("com.android.settings")
        u2d.sleep(1)

    def open_close_airplane_mode_by_adbui(self, is_open):
        current_state = self.is_airplane_mode_on
        # 如果当前状态已经符合目标状态，则无需操作
        if current_state == is_open:
            return
        self.screen_on_and_unlock()
        self.press_home_key(times=3)
        adb.exec_cmd(self.device_id, 'am start -a android.settings.AIRPLANE_MODE_SETTINGS')
        time.sleep(3)
        success = False
        # 尝试多种可能的开关定位方式
        switch_selectors = [
            '//android.widget.Switch',
            '//*[@text="Airplane mode"]',
            '//*[contains(@text, "Airplane")]',

        ]
        for selector in switch_selectors:
            switch_elm = self.u2d.xpath(selector)
            if switch_elm.exists:
                switch_elm.click(timeout=2)
                success = True
                time.sleep(2)
                break
        if not success:
            Exception('Failed to switch to airplane mode!')

        self.u2d.app_stop('com.android.settings')

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

    def adb_open_video(self, video_path):
        """
        adb打开mp4视频
        """
        adb.exec_cmd(self.device_id, f'am start -a android.intent.action.VIEW -d "file://{video_path}" -t "video/mp4"')

        time.sleep(4)
        # 默认选择第一个推荐的app，有可能是visha,有可能是Aigallery
        self.u2d.xpath('//*[@resource-id="android:id/button_always"]').click_exists()


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

    def screen_on_and_unlock(self, retry_count=0):
        def _internal_func():
            need_wait = False
            if not adb.is_screen_on(self.device_id):
                need_wait = True
            adb.poweron_screen_and_unlock(self.device_id)
            if need_wait:
                time.sleep(1)

        def _is_at_desktop():
            try:
                return bool(adb.get_foreground_package(self.device_id))
            except Exception as e:
                return False

        _internal_func()

        if retry_count > 0:
            if not _is_at_desktop():
                for _ in range(retry_count):
                    # 执行进入桌面的操作
                    _internal_func()
                    time.sleep(3)
                    if _is_at_desktop():
                        break
                else:
                    raise Exception(f'尝试{retry_count}次无法进入桌面！')

    def screen_on_and_unlock_numeric(self, password):
        adb.poweron_phone_screen(self.device_id)
        time.sleep(1)

        cmd = 'wm dismiss-keyguard'
        adb.exec_cmd(self.device_id, cmd)
        enter_pwd = self.u2d.xpath('//*[@text="Enter Password"]').wait(timeout=5)
        if not enter_pwd:
            adb.poweron_phone_screen(self.device_id)
            time.sleep(1)
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
        if 'en' not in adb.exec_cmd(self.device_id, 'getprop persist.sys.locale')[0].strip():
            logs_p().log('The phone system language is not set to English, try setting it to English.')
            adb.exec_cmd(self.u2d.serial, 'am start -a android.settings.LOCALE_SETTINGS')
            eng = self.u2d(textContains='English').wait(timeout=2)
            if eng:
                self.u2d(textContains='English').click()
                self.u2d.sleep(1)
                self.u2d(resourceId='com.android.settings:id/btn_positive').click_exists()
            else:
                self.u2d.xpath(
                    '//*[@resource-id="android:id/icon" or @resource-id="com.android.settings:id/add_language" or @text="其他语言"]').click()
                self.u2d.sleep(1)
                for _ in range(5):
                    if self.u2d(textContains='English').exists:
                        break
                    self.u2d.swipe_ext("up")
                    self.u2d.sleep(2)
                self.u2d(textContains='English').click()
                self.u2d.sleep(1)
                self.u2d(resourceId='com.android.settings:id/btn_positive').click_exists()
            self.u2d.sleep(1)
            if 'en' not in adb.exec_cmd(self.device_id, 'getprop persist.sys.locale')[0].strip():
                raise Exception("set system language to English！")
            else:
                logs_p().log('set system language to English successfully！')

    def set_default_browser(self, app_package):
        adb.exec_cmd(self.device_id, f'cmd role add-role-holder android.app.role.BROWSER {app_package}')

    def set_as_default_sms(self, app_package):
        adb.exec_cmd(self.device_id, f'cmd role add-role-holder android.app.role.SMS {app_package}')

    def close_palmstore_file_folder_switch(self):
        """
        关闭PalmStore应用中的文件夹打开开关
        """
        try:
            logs_p().log('开始关闭PalmStore文件夹打开开关')

            # 确保应用已安装
            package_name = 'com.transsnet.store'
            if not self.is_app_installed(package_name):
                logs_p().log(f'{package_name} 未安装，跳过')
                return False

            # 启动设置页面
            activity = 'com.afmobi.palmplay.setting.IndividualCenterSetting2OutActivity'
            self.start_activity(f'{package_name}/{activity}')
            time.sleep(2)

            # 查找文件夹打开开关
            switch_xpath = '//*[@resource-id="com.transsnet.store:id/tv_file_folder_open_switch"]'
            switch_elem = self.wait_ui_obj(switch_xpath, timeout=5, raise_on_not_exist=False)

            if not switch_elem:
                logs_p().log('未找到文件夹打开开关控件')
                self.stop_app(package_name)
                return False

            # 检查开关状态并关闭
            # 注意：不同的开关控件可能使用不同的属性表示状态
            # 尝试获取checked属性或text属性
            try:
                switch_info = switch_elem.info
                is_on = switch_info.get('checked', False) or switch_info.get('text', '').lower() in ['on', '开启', 'enabled']

                if is_on:
                    logs_p().log('文件夹打开开关当前为开启状态，正在关闭...')
                    switch_elem.click()
                    time.sleep(1)
                    logs_p().log('已点击关闭文件夹打开开关')
                else:
                    logs_p().log('文件夹打开开关已经是关闭状态')
            except Exception as e:
                # 如果无法判断状态，直接点击
                logs_p().log(f'无法判断开关状态: {e}，尝试直接点击')
                switch_elem.click()
                time.sleep(1)

            # 关闭应用
            self.stop_app(package_name)
            logs_p().log('PalmStore文件夹打开开关处理完成')
            return True

        except Exception as e:
            logs_p().log(f'关闭PalmStore文件夹打开开关时出错: {e}')
            try:
                self.stop_app('com.transsnet.store')
            except Exception:
                pass
            return False

    def clear_launcher_data(self):
        """
        清除 Launcher 应用数据
        清除 Launcher 数据会重置桌面布局、壁纸、小组件等所有 Launcher 设置
        清除后桌面会恢复到初始状态
        建议在清除后等待一段时间让系统重新初始化 Launcher
        """
        try:
            logs_p().log('开始清除 Launcher 应用数据...')

            # 先返回桌面获取桌面包名
            self.press_home_key(times=3)
            time.sleep(1)

            # 获取当前桌面的包名
            launcher_package = self.get_foreground_package()

            if not launcher_package:
                logs_p().log('无法获取桌面包名，使用默认包名: com.transsion.launcher3')
                launcher_package = 'com.transsion.launcher3'
            else:
                logs_p().log(f'检测到的桌面包名: {launcher_package}')

            # 执行清除命令
            result = adb.exec_cmd(self.device_id, f'pm clear {launcher_package}')

            if result and 'Success' in str(result):
                logs_p().log(f'{launcher_package} 应用数据清除成功')
                time.sleep(2)  # 等待清除完成
                return True
            else:
                logs_p().log(f'{launcher_package} 应用数据清除结果: {result}')
                return True  # pm clear 即使成功也可能返回空

        except Exception as e:
            logs_p().log(f'清除 Launcher 应用数据时出错: {e}')
            return False

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
        if self.android_version >= 16:
            if sim_index == 1:
                self.click_wait(u2d.xpath(
                    '//*[@resource-id="com.transsion.tele.settings:id/title" or @resource-id="com.android.settings:id/tran_iv_next" or @resource-id="com.android.settings:id/icon"]').all()[0], pre_wait=1,
                                timeout=5, post_wait=1)
            else:
                self.click_wait(u2d.xpath(
                    '//*[@resource-id="com.transsion.tele.settings:id/title" or @resource-id="com.android.settings:id/tran_iv_next" or @resource-id="com.android.settings:id/icon"]').all()[1], pre_wait=1,
                                timeout=5, post_wait=1)
        else:
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
        current_state = btn_enable.info['checked']
        if current_state != enable:
            u2d.xpath('//*[@resource-id="android:id/switch_widget"]').click()
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
        """确保只有一张海外卡被Didable"""
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
            adb.exec_cmd(self.device_id, f'service call audio 12 i32 0 i32 {level} i32 1')
        else:
            adb.exec_cmd(self.device_id, f'service call audio 14 i32 0 i32 {level} i32 1')
        time.sleep(0.5)

    def set_ring_volume_level(self, level: int):
        if float(adb.device_android_version(self.device_id)) < 16:
            adb.exec_cmd(self.device_id, f'service call audio 12 i32 7 i32 {level} i32 1')
        else:
            adb.exec_cmd(self.device_id, f'service call audio 14 i32 7 i32 {level} i32 1')
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
    def set_navi_mode_gesture(self):
        if adb.get_settings_value(self.device_id, "secure", 'navigation_mode') != '0':
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
        try:
            u2d.xpath('//android.widget.TextView[@text="System Navigation"]').click(timeout=2)
        except XPathElementNotFoundError:
            u2d.xpath('//android.widget.TextView[@text="System navigation"]').click(timeout=2)
        try:
            u2d.xpath('//*[@text="Gesture navigation"]').click(timeout=2)
            u2d.sleep(1)
            try:
                u2d.sleep(1)
                u2d.xpath('//*[@resource-id="com.transsion.microintelligence:id/gesture_nav_img_button"]').click(timeout=2)
                u2d.sleep(3)
                u2d.xpath(
                    '//*[@resource-id="com.transsion.microintelligence:id/gesture_nav_img_button"]').click(
                    timeout=2)
            except XPathElementNotFoundError:
                pass
        except XPathElementNotFoundError:
            u2d.sleep(1)
            u2d.xpath('//*[@resource-id="com.transsion.microintelligence:id/gesture_nav_img_button"]').click(timeout=2)
            u2d.sleep(3)
            u2d.xpath('//*[@resource-id="com.transsion.microintelligence:id/gesture_nav_img_button"]').click(
                timeout=2)
        u2d.sleep(1)
        u2d.app_stop('com.android.settings')
        assert adb.get_settings_value(self.device_id, "secure",
                                      'navigation_mode') != '0', 'Failed to enable navigation bottom 3 buttons mode'

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
        try:
            u2d.xpath('//android.widget.TextView[@text="System Navigation"]').click(timeout=2)
        except XPathElementNotFoundError:
            u2d.xpath('//android.widget.TextView[@text="System navigation"]').click(timeout=2)
        try:
            u2d.xpath('//*[@text="Three-button navigation" or @resource-id="com.transsion.microintelligence:id/key_nav_img_button"]').click(timeout=2)
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

    def check_network_connections(self, check_overseas: bool):
        website = "google.com" if check_overseas else "www.baidu.com"
        is_pass = False
        for i in range(5): # 增加重试次数
            try:
                result = subprocess.run(
                    [ADB_EXE, "-s", self.device_id, "shell", "ping", "-c", "1", website],
                    capture_output=True,
                    text=True,
                    timeout=10,  # 增加超时时间到10秒
                    encoding='utf-8'
                )
                is_pass = result.returncode == 0
            except subprocess.TimeoutExpired:
                # 处理超时异常
                pass
            except Exception:
                pass
            if is_pass:
                break
            else:
                time.sleep(1)  # 增加重试间隔
        if not is_pass:
            raise Exception('Can not connect to the network!')

    def _check_network_connections(self, check_overseas: bool):
        website = "google.com" if check_overseas else "www.baidu.com"
        is_pass = False
        for i in range(5):  # 增加重试次数
            try:
                result = subprocess.run(
                    [ADB_EXE, "-s", self.device_id, "shell", "ping", "-c", "1", website],
                    capture_output=True,
                    text=True,
                    timeout=10,  # 增加超时时间到10秒
                    encoding='utf-8'
                )
                is_pass = result.returncode == 0
            except subprocess.TimeoutExpired:
                # 处理超时异常
                pass
            except Exception:
                pass
            if is_pass:
                break
            else:
                time.sleep(1)  # 增加重试间隔
        if not is_pass:
            raise Exception('Can not connect to the network!')

    def check_network_status(self):
        active_id = self.get_active_network_id()
        t_log.debug(f'[当前网络id] {active_id}')
        return self.is_network_validated(active_id)

    def get_active_network_id(self):
        """
        获取当前活跃网络 ID
        """
        try:
            result = subprocess.run(
                [ADB_EXE, "-s", self.device_id, "shell", "dumpsys", "connectivity"],
                capture_output=True,
                text=True,
                timeout=10,  # 增加超时时间到10秒
                encoding='utf-8'
            )
        except subprocess.TimeoutExpired:
            # 处理超时异常
            pass
        except Exception:
            pass

        output = result.stdout
        for line in output.splitlines():
            if "Active default network" in line:
                return line.strip().split()[-1]
        return None


    def is_network_validated(self, active_id):
        """
        判断活跃网络对应的 NetworkAgentInfo 中是否包含 VALIDATED
        """
        if not active_id:
            return False

        try:
            result = subprocess.run(
                [ADB_EXE, "-s", self.device_id, "shell", "dumpsys", "connectivity"],
                capture_output=True,
                text=True,
                timeout=10,  # 增加超时时间到10秒
                encoding='utf-8'
            )
        except subprocess.TimeoutExpired:
            # 处理超时异常
            pass
        except Exception:
            pass

        output = result.stdout
        inside_block = False
        block_lines = []
        for line in output.splitlines():
            if f"network{{{active_id}}}" in line:
                inside_block = True
            elif inside_block and line.strip() == "":
                # 读到空行说明 NetworkAgentInfo 块结束
                break

            if inside_block:
                block_lines.append(line)

        block_text = "\n".join(block_lines)
        return "VALIDATED" in block_text

    def assert_non_disturb_mode_close(self):
        assert adb.get_settings_value(self.device_id, 'global', 'zen_mode') != '1', 'Non-disturb mode is not closed'

    def open_close_non_disturb_mode_by_ui(self, is_open):
        """
        通过UI界面控制勿扰模式的开关
        - is_open (bool): True表示打开免打扰模式，False表示关闭免打扰模式
        """
        current_state = self.is_non_disturb_mode_open()
        # 如果当前状态已经符合目标状态，则无需操作
        if current_state == is_open:
            return
        self.screen_on_and_unlock()
        self.press_home_key(times=3)
        self.restart_app('com.android.settings')
        # adb.exec_cmd(self.device_id, 'am start -a android.settings.ZEN_MODE_SETTINGS')
        time.sleep(2)
        for i in range(5):
            if self.u2d.xpath('//*[@text="Sound & Vibration"]').exists:
                self.u2d.xpath('//*[@text="Sound & Vibration"]').click()
                break
            else:
                self.u2d.swipe_ext("up")
                time.sleep(1)
        else:
            raise Exception("未找到Sound & Vibration元素")
        time.sleep(2)
        for i in range(5):
            if self.u2d.xpath('// *[ @ text = "Do Not Disturb"]').exists:
                self.u2d.xpath('// *[ @ text = "Do Not Disturb"]').click()
                break
            else:
                self.u2d.swipe_ext("up")
                time.sleep(1)
        else:
            raise Exception("未找到Do Not Disturb元素")
        time.sleep(2)
        success = False
        # 尝试多种可能的开关定位方式
        switch_selectors = [
            '//android.widget.Switch',
            '//*[@resource-id="android:id/switch_widget"]',
            '(//*[@text="Do Not Disturb"])[2]',

        ]
        for selector in switch_selectors:
            switch_elm = self.u2d.xpath(selector)
            if switch_elm.exists:
                switch_elm.click(timeout=2)
                success = True
                time.sleep(2)
                break
        if not success:
            Exception('Failed to switch to non-disturb mode!')

        self.stop_app('com.android.settings')


    def is_non_disturb_mode_open(self):
        """
        检查免打扰模式是否开启

        返回值说明：
        - bool: True表示免打扰模式已开启，False表示已关闭

        功能说明：
        通过ADB命令获取系统的zen_mode参数值来判断免打扰模式状态
        zen_mode值为'1'表示开启，其他值表示关闭

        异常情况：
        - 如果无法获取设置值，返回False作为默认值
        """
        try:
            value = adb.get_settings_value(self.device_id, 'global', 'zen_mode')
            return value == '1'
        except Exception:
            return False

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

    def open_close_double_tap_screen_wake_open(self, is_open):
        if is_open != self.is_double_tap_screen_wake_open:
            adb.set_settings_value(self.device_id, 'system', 'os_action_tapping_wake', '1' if is_open else '0')

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
        根据index，获取图标位置，支持1-24（4列 x 6行布局）
        """
        assert 1 <= index <= 24, f"不支持的index {index}, 只支持1-24"

        element_group = self.u2d.xpath('//*[contains(@resource-id, "workspace")]//android.view.ViewGroup').all()[0]  # 外面框
        element_app = self.u2d.xpath('//*[contains(@resource-id, "workspace")]//android.view.ViewGroup/android.widget.TextView').all()[0]  # app的小方块

        # 获取元素的bounds
        bounds = element_group.info['bounds']
        group_top_left_x = bounds['left']
        group_top_left_y = bounds['top']

        # 计算app的宽度和高度
        app_bounds = element_app.info['bounds']
        app_width = app_bounds['right'] - app_bounds['left']
        app_height = app_bounds['bottom'] - app_bounds['top']

        # 计算列和行（0-based）
        col = (index - 1) % 4  # 0-3
        row = (index - 1) // 4  # 0-5

        top_left_x = group_top_left_x + col * app_width
        top_left_y = group_top_left_y + row * app_height
        bottom_right_x = top_left_x + app_width
        bottom_right_y = top_left_y + app_height

        return [top_left_x, top_left_y], [bottom_right_x, bottom_right_y]

    def _calc_grid_position(self, index):
        """
        根据格子的序号（1~24）计算格子中心的坐标 (x, y)，用于拖拽落点。
        """
        [top_left_x, top_left_y], [bottom_right_x, bottom_right_y] = self.get_homeapp_x_y_for_index(index)
        cell_w = bottom_right_x - top_left_x
        # 原来的x坐标
        origin_x = top_left_x + cell_w / 2
        height = self.u2d.window_size()[1]
        x_ratio = 0.20 + (((index - 1) % 4) * (0.8 - 0.2)/3.0)
        # 拖动的x坐标
        clean_x = x_ratio * self.u2d.window_size()[0]
        row_index = (index - 1) // 4
        # 拖动的y坐标
        y_ratio = 0.22 + (row_index * (0.71 - 0.22) / 5.0) + 0.03
        clean_y = height * y_ratio
        # 原来的y坐标
        origin_y = top_left_y + (bottom_right_y - top_left_y) / 2
        return clean_x, clean_y, origin_x, origin_y

    def _move_app(self, app_name, to_index, icon_name=None):
        """
        移动app的子函数，只接手1-24的范围。
        """
        assert to_index <= 24

        icon_name = icon_name if icon_name else app_name

        self.press_home_key(times=3, interval=0.3)

        u2d = self.u2d

        clean_x, clean_y, orgin_x, orgin_y = self._calc_grid_position(to_index)

        self._clear_slot(orgin_x, orgin_y)

        start_x, start_y = self._search_app_and_get_offset_position(app_name, icon_name)

        time.sleep(0.2)
        u2d.drag(start_x, start_y, clean_x, clean_y, 0.5)
        adb.press_home_key(self.device_id)
        time.sleep(1)
        return

    def _clear_slot(self, x, y):
        """
        清空某个格子的位置，解除文件夹、移除已有应用，让槽位空出来
        """
        u2d = self.u2d
        try:
            u2d.long_click(x, y, 0.5)
            u2d.sleep(1)
            if u2d.xpath('//*[@text="Disband"]').exists:
                u2d.xpath('//*[@text="Disband"]').click(timeout=5)
                u2d.sleep(6)
                u2d.press('home')
                u2d.sleep(1)
                u2d.long_click(x, y, 0.5)
            u2d.sleep(1)
            remove_button = u2d.xpath('//*[contains(@text, "Remove")]')
            if remove_button.exists:
                remove_button.click(timeout=5)
                time.sleep(1)
                remove_stack_button = u2d.xpath('//*[@text="Remove"]')
                if remove_stack_button.exists:
                    remove_stack_button.click(timeout=5)
            else:
                adb.press_back_key(self.device_id)
            u2d.sleep(1)
        except Exception:
            pass

    def _input_search_name(self, text):
        has_chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
        if has_chinese_pattern.search(text):
            search_bar = self.u2d.xpath("//*[contains(@text, 'Search for')]")
            search_bar.set_text(text)
            self.restore_keyboard_ime()
        else:
            u2utils.input_text(self.u2d, str(text).lower().replace('_', ' '))

    def _search_app_and_get_offset_position(self, search_text, target_text: Union[str, Sequence[str], None] = None):
        """
        搜索应用并返回其位置坐标

        Args:
            search_text: 搜索框输入的应用名称
            target_text: 可以是单个字符串、字符串列表/元组，或者None
                        如果提供了多个名称，会尝试找到任意一个匹配的
                        如果为None，则使用search_text.replace('_', ' ')
        """
        u2d = self.u2d
        width, height = u2d.window_size()

        # 滑动屏幕显示搜索框
        u2d.swipe(20, height * 3 / 4, 20, height / 4, 0.1)
        u2d.sleep(1)

        # 查找并点击搜索框
        search_box = u2d(textMatches=".*Search.*")
        if not search_box.exists:
            for _ in range(20):
                adb.exec_cmd(self.device_id, 'input keyevent KEYCODE_DEL')
            search_box = u2d(textMatches=".*Search.*")
        if search_box.exists:
            search_box.click(timeout=5)
            u2d.sleep(1)
            if isinstance(search_text, list):
                for text in search_text:
                    self._input_search_name(text)
                    if self.u2d.xpath("//*[contains(@resource-id, 'empty') or contains(@text, 'relevant') or contains(@text, 'Search for')]").exists:
                        for _ in range(20):
                            adb.exec_cmd(self.device_id, 'input keyevent KEYCODE_DEL')
                        continue
                    else:
                        break
            else:
                self._input_search_name(search_text)
            u2d.sleep(1)
            self.press_back_key()
        else:
            assert False, 'search box not found!'

        # 处理target_text参数
        if target_text is None:
            # 如果target_text为None，使用search_text
            target_list = [search_text.replace('_', ' ')]
        elif isinstance(target_text, str):
            # 如果target_text是单个字符串
            target_list = [target_text]
        else:
            # 如果target_text是列表/元组等序列
            target_list = list(target_text)

        # 遍历所有目标文本，尝试找到任意一个
        app_element = None
        found_text = None

        for target in target_list:
            results = u2d.xpath(self.get_icon_name_xpath(target)).all()
            if results:
                app_element = results[0]  # 取第一个匹配项
                found_text = target
                break

        # 如果都没有找到，则抛出错误
        if not app_element:
            target_str = ", ".join([f'"{t}"' for t in target_list])
            raise AssertionError(f"未在搜索结果中找到应用: 尝试了 {target_str}")

        # 计算点击位置
        b = app_element.info['bounds']
        start_x = b['left'] + (b['right'] - b['left']) * 0.2
        start_y = (b['top'] + b['bottom']) / 2

        print(f"成功找到应用: {found_text}，坐标: ({start_x:.1f}, {start_y:.1f})")
        return start_x, start_y

    def add_az_widgets(self,to_index):
        [top_left_x, top_left_y], [bottom_right_x, bottom_right_y] = self.get_homeapp_x_y_for_index(to_index)
        pos_x = (top_left_x + bottom_right_x) / 2
        pos_y = (top_left_y + bottom_right_y) / 2
        self.u2d.long_click(pos_x, pos_y, 0.5)
        self.u2d.sleep(5)
        self.u2d.xpath('//*[@text="Widgets"]').click()
        time.sleep(2)
        self.u2d.xpath('//*[@resource-id="com.transsion.launcher3:id/widget_search"]').click()
        time.sleep(2)
        u2utils.input_text(self.u2d,'A-Z')
        time.sleep(2)
        self.u2d(text = 'A-Z').sibling(resourceId = 'com.transsion.launcher3:id/widget_detail_preview_container').click()
        time.sleep(2)
        self.u2d.xpath('//*[@text="Add to Home Screen"]').click()

    def search_and_move_app_to_home(self, app_name, to_index, icon_name: Union[str, Sequence[str], None] = None):
        """
        to_index:1 为1时表示放在第一位，为2时表示放在第二位
        app_name默认为search_name,icon_name默认为桌面的名字
        如果需要自动创建新的页数，则只能创建到当前页数+1
        例如：当前只有1页，to_index则支持1-48位；有2页，则支持1-72位。一页默认有24个应用。如果是从1-n连续放置，则不存在这个问题。
        """

        if to_index <= 24:
            self._move_app(app_name, to_index, icon_name)
            return

        u2d = self.u2d

        target_page = (to_index - 1) // 24 + 1
        local_index = ((to_index - 1) % 24) + 1

        # 翻页
        current_page = adb.get_desktop_page_number(self.device_id)
        for i in range(target_page + 3):
            if current_page == target_page:
                break
            if current_page < target_page:
                self.und_u2.swipe_direction('left', speed=350)
            else:
                self.und_u2.swipe_direction('right', speed=350)
            time.sleep(1)
            new_page = adb.get_desktop_page_number(self.device_id)
            if new_page == current_page:
                break
            current_page = new_page

        current_page_after_clean = adb.get_desktop_page_number(self.device_id)
        if current_page_after_clean == target_page:
            self._move_app(app_name, to_index, icon_name)
            return
        elif current_page_after_clean + 1 < target_page:
            # 只能滑动一页
            raise Exception('要求滑动的页数大于2页')

        end_x, end_y, orginal_x, orginal_y = self._calc_grid_position(local_index)

        # 修改这里：传递 icon_name 参数
        start_x, start_y = self._search_app_and_get_offset_position(app_name, icon_name)

        width, height = u2d.window_size()
        u2d.touch.down(start_x, start_y)
        time.sleep(0.6)
        steps = 12
        for i in range(steps):
            x_pos = start_x + (width * 0.95 - start_x) * (i + 1) / steps
            u2d.touch.move(x_pos, start_y)
            time.sleep(0.05)

        time.sleep(1)

        steps_drop = 10
        for i in range(steps_drop):
            x_pos = (width * 0.95) + (end_x - width * 0.95) * (i + 1) / steps_drop
            y_pos = start_y + (end_y - start_y) * (i + 1) / steps_drop
            u2d.touch.move(x_pos, y_pos)
            time.sleep(0.05)

        # 在格子松手
        u2d.touch.up(end_x, end_y)
        time.sleep(1)
        assert adb.get_desktop_page_number(self.device_id) == target_page

    def close_auto_arrange(self):
        u2d = self.u2d
        tos = adb.exec_cmd(self.device_id, 'getprop ro.build.version.release')[0]
        adb.open_settings_activity(self.device_id)
        u2d.sleep(5)
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

    def clear_all_desktop_items(self, max_pages: int = 10, max_items_per_page: int = 50):
        """
        清空手机桌面所有元素，包括app图标、小组件（天气、建议等）
        
        :param max_pages: 最大遍历的桌面页数，默认10页
        :param max_items_per_page: 每页最大移除项目数，默认50个（避免死循环）
        """
        logs_p().log('开始清空桌面所有元素...')

        self.close_palmstore_file_folder_switch()

        # 回到桌面主页
        self.press_home_key(times=3)
        time.sleep(1)

        u2d = self.u2d
        removed_count = 0

        for page_index in range(max_pages):
            logs_p().log(f'处理第 {page_index + 1} 页桌面')

            # 每页尝试移除所有项目
            for item_index in range(max_items_per_page):
                time.sleep(0.5)

                # 查找桌面上的所有可移除项目（图标和组件）
                # 查找workspace（桌面主区域）和hotseat（底部快捷栏）中的TextView（app图标）
                workspace_items = u2d.xpath('//*[contains(@resource-id, "workspace")]//android.widget.TextView | //*[contains(@resource-id, "hotseat")]//android.widget.TextView').all()

                if not workspace_items:
                    # 如果没有TextView，尝试查找其他类型的组件（如小组件）
                    workspace_items = u2d.xpath('//*[contains(@resource-id, "workspace")]//*[@clickable="true"] | //*[contains(@resource-id, "hotseat")]//android.widget.TextView').all()

                if not workspace_items:
                    logs_p().log(f'第 {page_index + 1} 页没有找到可移除的项目')
                    break

                # 获取第一个项目的位置并长按
                try:
                    first_item = workspace_items[0]
                    bounds = first_item.info['bounds']
                    center_x = (bounds['left'] + bounds['right']) / 2
                    center_y = (bounds['top'] + bounds['bottom']) / 2

                    # 长按项目以进入编辑模式
                    u2d.long_click(center_x, center_y, 0.8)
                    time.sleep(1)

                    # 尝试点击"Remove"或"删除"按钮
                    remove_buttons = [
                        '//*[@text="Remove"]',
                        '//*[@text="删除"]',
                        '//*[@text="移除"]',
                        '//*[@content-desc="Remove"]',
                        '//*[@content-desc="删除"]',
                        '//*[contains(@text, "Remove")]',
                        '//*[contains(@text, "删除")]'
                    ]

                    confirm_remove_buttons = [
                        '//*[@text="Remove"]',
                        '//*[@text="Confirm"]',
                        '//*[@text="确定"]',
                        '//*[@text="确认"]',
                        '//*[@content-desc="Confirm"]',
                        '//*[contains(@text, "Remove")]'
                    ]

                    removed = False
                    for button_xpath in remove_buttons:
                        if u2d.xpath(button_xpath).exists:
                            u2d.xpath(button_xpath).click(timeout=2)
                            removed = True
                            removed_count += 1
                            logs_p().log(f'已移除第 {removed_count} 个项目')
                            time.sleep(0.5)
                            # 二次确认检查
                            for confirm_xpath in confirm_remove_buttons:
                                if u2d.xpath(confirm_xpath).exists:
                                    u2d.xpath(confirm_xpath).click(timeout=2)
                                    time.sleep(0.5)
                                    break

                    if not removed:
                        # 如果是文件夹，可能需要先解散
                        if u2d.xpath('//*[@text="Disband"]').exists:
                            u2d.xpath('//*[@text="Disband"]').click(timeout=2)
                            time.sleep(1)
                            logs_p().log('解散了一个文件夹')
                        else:
                            # 如果找不到移除按钮，尝试拖动到删除区域或点击返回
                            self.press_back_key()
                            time.sleep(0.5)
                            logs_p().log('无法移除该项目，跳过')
                            # 如果连续多次无法移除，可能该页已清理完成
                            if item_index > 5:
                                break

                except Exception as e:
                    logs_p().log(f'移除项目时出错: {e}')
                    self.press_back_key()
                    time.sleep(0.5)
                    continue

            # 检查是否还有下一页，尝试向左滑动
            time.sleep(0.5)
            width, height = u2d.window_size()

            # 先检查当前页是否还有项目（包括workspace和hotseat）
            remaining_items = len(u2d.xpath('//*[contains(@resource-id, "workspace")]//android.widget.TextView | //*[contains(@resource-id, "hotseat")]//android.widget.TextView').all())
            if remaining_items == 0:
                # 尝试滑动到下一页
                u2d.swipe(width * 0.8, height * 0.5, width * 0.2, height * 0.5, 0.2)
                time.sleep(1)

                # 检查滑动后是否有新内容
                new_items = len(u2d.xpath('//*[contains(@resource-id, "workspace")]//android.widget.TextView | //*[contains(@resource-id, "hotseat")]//android.widget.TextView').all())
                if new_items == 0:
                    logs_p().log('已遍历完所有桌面页')
                    break
            else:
                # 当前页还有项目，继续处理当前页
                continue

        # 回到主桌面
        self.press_home_key(times=2)
        time.sleep(1)

        logs_p().log(f'桌面清理完成，共移除 {removed_count} 个项目')
        return removed_count



    def check_app_position(self, app_names, position):
        global elements
        try:
            assert position >= 1, f"不支持判定位置 {position}"

            adb.press_home_key(self.device_id)
            time.sleep(0.3)
            adb.press_home_key(self.device_id)
            time.sleep(1)

            target_page = (position - 1) // 24 + 1
            local_index = ((position - 1) % 24) + 1

            current_page = adb.get_desktop_page_number(self.device_id)
            for i in range(target_page+3):
                if current_page == target_page:
                    break
                if current_page < target_page:
                    self.und_u2.swipe_direction('left', speed=350)
                else:
                    self.und_u2.swipe_direction('right', speed=350)
                time.sleep(1)
                new_page = adb.get_desktop_page_number(self.device_id)
                if new_page == current_page:
                    break
                current_page = new_page

            if current_page != target_page:
                t_log.info('3')
                return False

            u2d = self.u2d
            exist_flag = False
            if isinstance(app_names, str):
                app_names = [app_names]
            for app_name in app_names:
                icon_name_xpath = self.get_icon_name_xpath(app_name).replace("]", "")
                elements_xpath = f'//*[contains(@resource-id, "workspace")]//android.view.ViewGroup{icon_name_xpath} or @content-desc="{app_name}"]'
                elements = u2d.xpath(elements_xpath).all()
                if elements:
                    exist_flag = True
                    break
            if not exist_flag:
                return False


            # if not elements[0].info.get('longClickable', True) or not elements[0].info.get('focusable', True):
            #     return False

            b = elements[0].info['bounds']
            [top_left_x, top_left_y], [bottom_right_x, bottom_right_y] = self.get_homeapp_x_y_for_index(local_index)

            screen_width, screen_height = self.u2d.window_size()

            icon_cx = (b['left'] + b['right']) / 2
            icon_cy = (b['top'] + b['bottom']) / 2
            cell_cx = (top_left_x + bottom_right_x) / 2
            cell_cy = (top_left_y + bottom_right_y) / 2

            return abs(icon_cx - cell_cx) < screen_width * 0.1 and abs(icon_cy - cell_cy) < screen_height * 0.05

        except Exception as e:
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
                           u2o: Union[uiautomator2.UiObject, uiautomator2.xpath.XPathSelector, uiautomator2.xpath.XMLElement, str],
                           pre_wait: float = 0.0, timeout: float = 5.0, post_wait: float = 0.5) -> Union[U2ObjectProtocol, U2XMLElementProtocol, None]:
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
        for _ in range(30):
            icon_pos_check = self.u2d.xpath(self.get_icon_name_xpath(icon_name)).wait(timeout=2)
            if not icon_pos_check:
                time.sleep(2)
            else:
                icon_pos = self.u2d.xpath(self.get_icon_name_xpath(icon_name))
                x = (icon_pos.info['bounds']['left'] + icon_pos.info['bounds']['right']) / 2
                y = (icon_pos.info['bounds']['top'] + icon_pos.info['bounds']['bottom']) / 2
                self.u2d.click(x, y-50)
                break

    def click_desktop_any_icon(self, icon_names: Sequence[str], timeout=-1.0):
        # 任意一个名称的图标在当前桌面即点击
        head = "//*["
        is_first = True
        for icon_name in icon_names:
            if is_first:
                is_first = False
            else:
                head += " or "
            head += f"normalize-space(@text)='{icon_name}' or normalize-space(@text)='● {icon_name}'"
        head += "]"
        for _ in range(30):
            icon_pos_check = self.u2d.xpath(head).wait(timeout=2)
            if not icon_pos_check:
                time.sleep(2)
            else:
                icon_pos = self.u2d.xpath(head)
                x = (icon_pos.info['bounds']['left'] + icon_pos.info['bounds']['right']) / 2
                y = (icon_pos.info['bounds']['top'] + icon_pos.info['bounds']['bottom']) / 2
                adb.exec_cmd(self.device_id, f"input swipe {x} {y-50} {x} {y-50} 100")
                # self.u2d.click(x, y-50)
                break

    def exist_desktop_icon(self, icon_name: str, timeout=-1.0):
        return self.u2d.xpath(self.get_icon_name_xpath(icon_name)).wait(timeout=timeout)

    def exist_desktop_any_icon(self, icon_names: Sequence[str], timeout=-1.0):
        # 检查任意一个名称的图标在当前桌面即返回 True
        head = "//*["
        is_first = True
        for icon_name in icon_names:
            if is_first:
                is_first = False
            else:
                head += " or "
            head += f"normalize-space(@text)='{icon_name}' or normalize-space(@text)='● {icon_name}'"
        head += "]"
        return self.u2d.xpath(head).wait(timeout=timeout)

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

    def click_exists(self, u2o: Union[
        uiautomator2.UiObject, uiautomator2.xpath.XPathSelector, uiautomator2.xpath.XMLElement, str],
                     pre_wait: float = 0.0, timeout: float = 0.0, post_wait: float = 0.0,
                     wait_after_click: float = 0.0, offset=(0.5, 0.5)) -> \
            Union[uiautomator2.UiObject, uiautomator2.xpath.XMLElement, None]:
        """
        对象存在时才执行点击操作。

        :param u2o: 目标UI对象，可以是UiObject、XPathSelector、XMLElement或字符串类型的XPath。
        :param pre_wait: 在查找UI对象之前等待的时间（秒），默认为0.0。
        :param timeout: 查找UI对象的超时时间（秒），默认为0.0。
        :param post_wait: 在找到UI对象后等待的时间（秒），默认为0.0。
        :param wait_after_click: 如果大于0且perform_click为True，则在点击之后执行等待相应时间（秒）。
        :param offset: 点击的相对位置（中心就是0.5, 0.5）。
        :return: 找到的UI对象（UiObject或XMLElement），如果未找到则返回None（仅在no_raise为True时）。
        """
        return u2utils.click_wait(self.u2d, u2o, pre_wait, timeout, post_wait, True, wait_after_click, offset)

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
                t_log.debug(f"[KILL-MONKEY] Killed Monkey process with PID {line}")
                killed = True

            if not killed:
                t_log.debug("[KILL-MONKEY] No Monkey process found to kill.")
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
            "-s", str(seed),
            "--throttle", str(throttle),
            "--monitor-native-crashes",
            "--kill-process-after-error",
            "--randomize-throttle",
            "--ignore-crashes",
            "--ignore-timeouts",
            "--ignore-security-exceptions",
            "--ignore-native-crashes",
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
        time.sleep(4 if self.is_sprd else 3)
        self.u2d.xpath('//android.widget.TextView[@text="Data Usage " or @text="Data Usage"]').click()
        time.sleep(1)
        self.u2d.xpath('//android.widget.TextView[@text="Data Usage " or @text="Data Usage"]').click()
        time.sleep(1)
        self.u2d(resourceId="com.transsion.phonemaster:id/rv_mobile_daily_list").scroll.to(text="Settings")
        time.sleep(1)
        self.u2d.swipe(0.5, 0.8, 0.5, 0.2)
        time.sleep(3)
        self.u2d.xpath('//*[@text="Settings"]').click()
        self.u2d.xpath('//*[@text="Agree"]').click_exists(timeout=2)
        if self.u2d.xpath('//*[@text="Your package period is?"]').exists:
            self.und_u2.click_back()
        # os16
        if self.u2d.xpath('//*[@text="Mobile data usage"]').exists:
            self.u2d.xpath('//*[@text="Mobile data usage"]').click(timeout=3)
            time.sleep(5)
            self.u2d.xpath('//*[@resource-id="com.android.settings:id/filter_settings"]').click_exists(timeout=3)
            time.sleep(3)
            switch_element = self.u2d.xpath('(//*[@resource-id="android:id/widget_frame"])[2]')
            if switch_element.info.get('enabled'):
                switch_element.click_exists(timeout=3)
        else:
            self.click_wait('//*[@text="When data plan is used up"]', timeout=10, post_wait=1)
            self.click_wait('//*[@text="Don\'t Remind Me"]', timeout=10, post_wait=1)
        self.press_home_key()
        self.stop_settings()

    def close_sidebar(self):
        """关闭侧边栏"""
        adb.exec_cmd(self.device_id, 'settings put global smart_panel_status 69904')

    def assert_time_with_pc(self, threshold_seconds: float = 10, is_auto_correct=True) -> None:
        """检查Android手机和PC主机的时间差，如超过阈值则自动调整时间设置"""

        MAX_RETRY_ATTEMPTS = 2

        for attempt in range(MAX_RETRY_ATTEMPTS):
            time_difference = adb.measure_device_time_offset_ms(self.device_id) / 1000.0

            if abs(time_difference) <= threshold_seconds:
                t_log.debug(f'时间差在允许范围内: {time_difference:.2f}秒')
                return

            t_log.warning(f'设备时间差超出阈值: {time_difference:.2f}秒 > {threshold_seconds}秒')

            if attempt == MAX_RETRY_ATTEMPTS - 1:
                raise Exception(
                    f'时间同步失败，设备与PC时间差 {time_difference:.2f}秒，超出阈值 {threshold_seconds}秒'
                )
            if is_auto_correct:
                # 执行时间设置调整流程
                self.press_home_key(2)
                self.restart_settings_activity()
                time.sleep(3)

                # 执行两次上滑
                for _ in range(3):
                    self.und_u2.swipe_direction('up', speed=300)
                    time.sleep(0.3)

                # 点击系统选项
                u2d = connect_u2_device(self.device_id)
                u2d.xpath('//*[@text="System"]').click()
                time.sleep(2)
                u2d(textContains='Date').click()
                time.sleep(2)
                u2d(textContains='Auto').click()
                time.sleep(2)

        # 循环正常结束说明调整后时间仍然不符合要求
        final_difference = adb.measure_device_time_offset_ms(self.device_id) / 1000.0
        raise Exception(
            f'时间同步失败，最终时间差 {final_difference:.2f}秒，超出阈值 {threshold_seconds}秒'
        )

    def check_wifi_network_connection(self, check_overseas_net: bool = True):
        if not adb.is_wifi_open(self.device_id):
            self.open_close_wifi(True)
            time.sleep(5)

        try:
            if self.check_network_status():
                return
        except Exception:
            pass

        # 状态未VALIDATED时，作为补充走内部ping方法；如果失败，再以状态兜底一次
        try:
            self._check_network_connections(check_overseas_net)
            return
        except Exception:
            try:
                if self.check_network_status():
                    # 即便ping失败，只要状态VALIDATED，就认为网络正常
                    return
            except Exception:
                pass
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
        self.click_exists('//android.widget.TextView[@text="Search"]', timeout=8, post_wait=1,wait_after_click=1)
        self.u2d.xpath('//*[@text="Search"]').click_exists(timeout=3)
        u2utils.input_text(self.u2d, 'Automatically')
        time.sleep(3)
        if not self.u2d.xpath('//android.widget.TextView[@text="Automatically Sync App Data "]').exists:
            self.u2d(resourceId = 'com.android.settings.intelligence:id/text_search').clear_text(timeout=3)
            u2utils.input_text(self.u2d, 'auto-sync')
        time.sleep(3)
        self.u2d.xpath('//*[@text="Auto-sync Personal Data "]').click_exists(timeout=8)
        self.u2d.xpath('//android.widget.TextView[@text="Automatically Sync App Data "]').click_exists(timeout=8)
        time.sleep(3)
        self.u2d.xpath('//android.widget.Switch[@checked="true"]').click_exists(timeout=2)
        self.u2d.xpath('//*[@text="OK"]').click_exists(timeout=2)
        self.u2d.app_stop('com.android.settings')

        # 关闭Automatic system update
        adb.set_settings_value(self.device_id, 'global', 'ota_disable_automatic_update', 1)

        # Auto-update apps
        self.restart_app('com.android.vending')
        self.wait_ui_obj('//*[@text="Apps"]', timeout=10, post_wait=1)
        self.u2d.click(0.87, 0.072)
        time.sleep(3)
        self.u2d(resourceId = "com.android.vending:id/0_resource_name_obfuscated").scroll.to(text = "Settings")
        time.sleep(3)
        self.click_wait('//*[@text="Settings"]', timeout=8, post_wait=1)
        time.sleep(2)
        self.u2d.xpath('//*[@text="Got it"]').click_exists(timeout=2)
        if not self.u2d.xpath('//*[@text="Network preferences"]').exists:
            self.u2d.xpath('//*[@text="General"]').click()
        self.click_wait('//*[@text="Network preferences"]', timeout=8, post_wait=1)
        self.click_wait('//*[@text="Auto-update apps"]', timeout=8, post_wait=1)
        self.click_wait('//*[@text="Don\'t auto-update apps"]', timeout=8, post_wait=1)
        self.u2d.app_stop('com.android.vending')

    def get_recent_card_texts(self):
        xpath = '//android.widget.TextView'
        region = (0.2, 0.1, 0.8, 0.5)
        return [tv.text for tv in u2utils.xpath_within_region(self.u2d, xpath, region=region)]

    def _count_first_list_or_scroll_children_with_id(self, timeout: float = 3.0) -> Tuple[int, str]:
        """
        返回 (children_count, resource_id)
          - 如果同时存在 ListView 和 ScrollView -> 返回 (0, "")
          - 如果两者都不存在 -> 返回 (0, "")
          - 否则返回第一个出现的 ListView 或 ScrollView 的直接子节点数量和 resource-id（若无返回""）

        Args:
            timeout: dump_hierarchy 操作的超时时间（部分 uiautomator2 版本支持）

        Returns:
            (int, str): children_count, resource_id_or_empty
        """
        try:
            ui_xml = self.u2d.dump_hierarchy()  # uiautomator2 提供的 XML 字符串
        except Exception as e:
            # 无法导出 UI 层级，视为未找到
            # 可改为抛异常按需处理
            # print(f"dump_hierarchy failed: {e}")
            return 0, ""

        import xml.etree.ElementTree as ET
        try:
            root = ET.fromstring(ui_xml)
        except ET.ParseError:
            return 0, ""

        # 遍历所有节点，按文档顺序找出类名后缀匹配的节点
        list_nodes = []
        scroll_nodes = []

        for node in root.iter():
            cls = node.attrib.get('class') or node.attrib.get('className') or ""
            if not cls:
                continue
            # 以后缀判断，兼容自定义子类 (e.g. com.xxx.MyListView)
            if cls.endswith("ListView"):
                list_nodes.append(node)
            elif cls.endswith("ScrollView"):
                scroll_nodes.append(node)

        # 若两种类型同时存在 -> 不唯一
        if list_nodes and scroll_nodes:
            return 0, ""

        # 若都不存在
        if not list_nodes and not scroll_nodes:
            return 0, ""

        # 只有一种类型存在，取第一个出现的节点
        target_nodes = list_nodes if list_nodes else scroll_nodes
        first_node = target_nodes[0]

        # 直接子节点数量（只算第一层 children）
        children_count = len(list(first_node))

        # 获取 resource-id（在 uiautomator xml 中通常为 'resource-id'）
        resource_id = first_node.attrib.get('resource-id') or first_node.attrib.get('resourceId') or ""

        return children_count, resource_id

    def swipe_recent_card_and_check_reach_edge(self, swipe_left=True, find_icon_name=None) -> int:
        def _find_icon_name(tv_texts):
            if not find_icon_name:
                return False
            for elem in tv_texts:
                for find_icon in find_icon_name:
                    if find_icon in elem:
                        return True
                # if find_icon_name.startswith(elem.rstrip('.')):
                #     return True
            return False

        direction = 'left' if swipe_left else 'right'
        before = self.get_recent_card_texts()
        if _find_icon_name(before):
            return 2
        self.und_u2.swipe_direction(direction, 0.7, speed=70)
        time.sleep(0.2)
        after = self.get_recent_card_texts()
        if _find_icon_name(after):
            return 2
        return 1 if before == after else 0

    def find_recent_app(self, full_icon_name: str, from_right_to_left=True):
        width, height = self.u2d.window_size()
        self.press_app_switch_key()
        time.sleep(1)

        _conti_swipe_direction = ('right' if from_right_to_left else 'left')

        def _conti_swipe(count: int):
            for _ in range(count):
                self.und_u2.swipe_direction(_conti_swipe_direction, 0.7, speed=400)
                time.sleep(0.1)
            time.sleep(0.4)

        _conti_swipe(7)
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
                self.u2d.click(width / 2, height / 2)
                time.sleep(1)
                break
        if _find_result != 2:
            raise Exception(f'Can not find recent card named "{full_icon_name}"!')

    def find_any_recent_app(self, full_icon_names: Sequence[str], from_right_to_left=True):
        width, height = self.u2d.window_size()
        self.press_app_switch_key()
        time.sleep(1)

        _conti_swipe_direction = ('right' if from_right_to_left else 'left')

        def _conti_swipe(count: int):
            for _ in range(count):
                self.und_u2.swipe_direction(_conti_swipe_direction, 0.7, speed=400)
                time.sleep(0.1)
            time.sleep(0.4)

        _conti_swipe(7)
        for _ in range(10):
            if self.swipe_recent_card_and_check_reach_edge(not from_right_to_left):
                break
            _conti_swipe(2)
        else:
            raise Exception('Can not swipe recent cards to edge!')

        _find_result = 0
        for _ in range(100):
            _find_result = self.swipe_recent_card_and_check_reach_edge(from_right_to_left, full_icon_names)
            if _find_result:
                self.u2d.click(width / 2, height / 2)
                time.sleep(1)
                break
        if _find_result != 2:
            raise Exception(f'Can not find recent card named "{full_icon_names}"!')

    def _generate_phone_number(self, prefix: str = "199") -> str:
        """生成11位以 prefix 开头的随机手机号"""
        suffix = ''.join(random.choices('0123456789', k=8))
        return prefix + suffix

    def insert_contacts(self, pre_name: str = "test", pre_phone: str = "199", count: int = 2) -> None:
        """
        添加联系人
        """
        for i in range(count):
            # 添加一列
            self.u2d.shell(self.RAW_CONTACTS_SHELL)

            # 查询数据库中所有联系人id
            rows: str = self.u2d.shell(self.QUERY_CONTACTS_SHELL).output
            ids: List[str] = re.findall(r'_id=(\d+)', rows)
            if not ids:
                t_log.error("No raw_contacts found")
                return
                # 找最大_id

            max_id: int = max(map(int, ids))
            t_log.info(f"Max _id:{max_id}")
            self.u2d.shell(self.INSERT_NAME_SHELL.format(raw_contact_id=max_id, contact_name=f"{pre_name}_{i}"))
            phone_number: str = self._generate_phone_number(pre_phone)
            self.u2d.shell(self.INSERT_PHONE_SHELL.format(raw_contact_id=max_id, phone_number=phone_number))

    def delete_all_contacts(self) -> None:
        """
        删除所有联系人（通过 content provider 删除 raw_contacts）
        """
        self.u2d.shell(self.DELETE_ALL_CONTACTS_SHELL)

    def delete_contact_by_name(self, name):
        """
        通过联系人姓名删除联系人
        """
        # 查询联系人ID
        query_result: str = self.u2d.shell(self.QUERY_CONTACTS_BY_NAME_SHELL.format(name=name)).output
        match = re.search(r'_id=(\d+)', query_result)
        if not match:
            t_log.error(f"未找到联系人: {name}")
            return
        contact_id: str = match.group(1)

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
            self.u2d.shell(
                self.INSERT_ALL_CALL_SHELL.format(phone_number=phone_number, call_type=2, timestamp=timestamp,
                                                  duration=duration, index=1))

    def delete_call_logs(self):
        """
        删除设备上的所有通话记录。
        """
        result = self.u2d.shell(self.DELETE_ALL_CALL_SHELL)
        if result.exit_code == 0:
            t_log.info("✅ 通话记录删除成功")
        else:
            t_log.error(f"❌ 删除失败: {result.output}")

    def insert_sms(self, count=1):
        from apk_rpc.rpc_util import RPCUtil
        rpc = RPCUtil.get_instance()
        flag, res = rpc.insert_sms(self.device_id, count)
        t_log.info(f"请求结果：{flag},{res}")

    def insert_contacts_by_phonemonitor(self,count=1):
        from apk_rpc.rpc_util import RPCUtil
        rpc = RPCUtil.get_instance()
        flag, res = rpc.insert_contacts(self.device_id, count)
        t_log.info(f"请求结果：{flag},{res}")

    def delete_contacts_by_phonemonitor(self):
        from apk_rpc.rpc_util import RPCUtil
        rpc = RPCUtil.get_instance()
        flag, res = rpc.delete_contacts(self.device_id)
        t_log.info(f"请求结果：{flag},{res}")

    def insert_call_logs_by_phonemonitor(self, count=1):
        from apk_rpc.rpc_util import RPCUtil
        rpc = RPCUtil.get_instance()
        flag, res = rpc.insert_call_logs(self.device_id, count)
        t_log.info(f"请求结果：{flag},{res}")

    def delete_call_logs_by_phonemonitor(self):
        from apk_rpc.rpc_util import RPCUtil
        rpc = RPCUtil.get_instance()
        flag, res = rpc.delete_call_logs(self.device_id)
        t_log.info(f"请求结果：{flag},{res}")

    def delete_all_sms(self):
        """
        删除所有短信记录
        """
        self.u2d.shell(self.DELETE_MESSAGE_SHELL)

    def enter_small_window(self, package):
        """
        进入小窗
        """
        command = f"appops set {package} SYSTEM_ALERT_WINDOW allow"
        t_log.info(f"执行命令: {command}")
        self.u2d.shell(command)

    def get_launcher_icon(self, package_name: str):
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

    def xpath_get_last(self, xpath, instance=0, timeout=3, sleep_time=1):
        """
        通过xpath点击
        """
        d1 = self.u2d.xpath(xpath).all()
        if d1 is None or len(d1) == 0:
            return None
        else:
            return d1[-1]

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
        y_down = str(int(sscreen_height * 3 / 4))

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

        for i in range(max(2, temp_scroll_time - 2)):
            self.u2d.shell(["input", "swipe", x, y_up, x, y_down, "100"])
            time.sleep(1)
        time.sleep(2)

    def drag_with_pause(self, start, mid, end, pause_time=3, fast_steps=5, slow_steps=10, step_delay_fast=0.01,
                        step_delay_slow=0.05, hold_time=1.0):
        """
        比如systemui的功能图标，先长按，再从最下面拉到最上面，然后停留一会
        模拟拖动（长按 -> 快 -> 停顿 -> 慢），过程中不松手
        :param start: (x, y) 起点
        :param mid: (x, y) 中间点
        :param end: (x, y) 终点
        :param pause_time: 中间停顿时间
        :param fast_steps: 起点到中间分成多少步
        :param slow_steps: 中间到终点分成多少步
        :param step_delay_fast: 快速阶段每步延迟
        :param step_delay_slow: 慢速阶段每步延迟
        :param hold_time: 按下后初始长按时间（秒）
        """
        sx, sy = start
        mx, my = mid
        ex, ey = end

        try:
            # 按下起点
            self.u2d.touch.down(sx, sy)

            # 长按等待
            time.sleep(hold_time)

            # 快速移动到中间
            for i in range(1, fast_steps + 1):
                x = sx + (mx - sx) * i / fast_steps
                y = sy + (my - sy) * i / fast_steps
                self.u2d.touch.move(x, y)
                time.sleep(step_delay_fast)

            # 中间停顿
            time.sleep(pause_time)

            # 慢速移动到终点
            for i in range(1, slow_steps + 1):
                x = mx + (ex - mx) * i / slow_steps
                y = my + (ey - my) * i / slow_steps
                self.u2d.touch.move(x, y)
                time.sleep(step_delay_slow)

        except Exception as e:
            print(f"发生异常: {e}")
            raise
        finally:
            # 无论如何都松手
            try:
                self.u2d.touch.up(ex, ey)
            except Exception as e:
                print(f"松手时出错: {e}")

    def lock_screen_status(self):
        result = self.u2d.shell("dumpsys window | grep mDreamingLockscreen").output

        match = re.search(r"mDreamingLockscreen=(true|false)", result, re.IGNORECASE)
        if match:
            return match.group(1).lower() == "true"
        else:
            t_log.warning("未找到锁屏状态字段")
            return False

    def check_and_update_apps(self, required_apps, local_app_dir=None):
        """
        检查并更新测试所需的app
        @param: required_apps 需要的app
            格式
            required_apps = {
                'WhatsApp': 'com.whatsapp',
                .....
                }
        @param local_app_dir: 拉到本地的路径 默认在'dz_auto_env_configs\app_res‘
        注意：检查的格式默认是utp拉下来的zip，其他的不一定支持
        """

        from powertrde.utils.feishu.utp_api_helper import UTPApiHelper

        # 初始化UTP API Helper
        utp = UTPApiHelper('ru9k74pa', '8noZHKdTZAkPt0igiAFkJawHgGu4t5u4')
        package_list = list(required_apps.values())
        local_app_dir = env.get_framework_shared_cache_dir(True, 'app_res')

        t_log.info(f"开始检查 {len(required_apps)} 个应用的更新状态...")

        # 1. 获取远程版本信息，同时过滤掉缺失的包
        remote_versions = utp.get_package_versions(package_list)
        missing_packages = utp.find_missing_packages(package_list)

        if missing_packages:
            t_log.warning(f"远程仓库缺失: {missing_packages}")
            required_apps = {k: v for k, v in required_apps.items() if v not in missing_packages}

        self.download_new_apps(required_apps, remote_versions, local_app_dir)

    def download_new_apps(self, required_apps, remote_versions, local_app_dir):
        """
        更新的应用需要下载，本地的更新应用需要安装
        返回: (apps_to_download, apps_to_install)
        """
        from powertrde.utils.trde import adb
        import os

        def _compare_versions(v1, v2):
            """
            比较两个apk版本号
            返回值: -1 表示 version1 < version2, 0 表示相等, 1 表示 version1 > version2
            """
            if not v1 or not v2:
                return -1 if not v1 else 1

                # 简单的字符串比较（适用于大多数情况）
            return (v1 > v2) - (v1 < v2)

        to_download = []
        to_install = []

        from powertrde.utils.feishu.utp_api_helper import UTPApiHelper
        utp = UTPApiHelper('ru9k74pa', '8noZHKdTZAkPt0igiAFkJawHgGu4t5u4')

        # 批量检查状态
        for app_name, package_name in required_apps.items():
            if package_name not in remote_versions:
                continue

            remote_ver = remote_versions[package_name]['latestVersion']
            device_ver = adb.get_installed_package_version(self.device_id, package_name) if adb.package_is_installed(
                self.device_id, package_name) else None

            local_zip = os.path.join(local_app_dir, f"{package_name}.zip")
            local_ver = utp.get_zip_version(local_zip) if os.path.exists(local_zip) else None

            if not local_ver or _compare_versions(local_ver, remote_ver) < 0:
                to_download.append(package_name)
            if not device_ver or _compare_versions(device_ver, remote_ver) < 0:
                to_install.append(package_name)

        # 批量操作
        if to_download:
            t_log.info(f"下载: {to_download}")
            utp.multiple_download_apk(to_download, local_app_dir)

        if to_install:
            t_log.info(f"安装: {to_install}")
            utp.install_apps_from_zip(to_install, local_app_dir, self.device_id)

    def try_stop_exist_detached_perfetto(self):
        adb.try_stop_exist_detached_perfetto(self.device_id)

    def wait_device_connection(self, timeout: float, interval: float):
        start_time = time.time()
        time.sleep(0.05)

        while True:
            elapsed_time = time.time() - start_time
            result = self.is_device_connected
            if result:
                return elapsed_time

            remaining_time = timeout - elapsed_time

            if remaining_time <= 0:
                break
            else:
                # 如果剩余时间已经不足间隔时间，则直接等待剩余时间
                time.sleep(min(interval, remaining_time))

        return None

    def check_to_charge(self, charging_trigger_level: int, target_level: int, stop_all_recent_app_before_charge=False, max_charge_duration=28800):
        """
        检查电量不足时是否需要充电
        """
        interval_for_show = timedelta(minutes=3)
        start_time = datetime.now()
        next_check_time = start_time + interval_for_show
        single_check_duration = 20
        max_loop = int(max_charge_duration / single_check_duration)
        disconnected_once = False

        def _safe_get_battery():
            nonlocal disconnected_once
            try:
                return self.get_battery_level()
            except Exception:
                disconnected_once = True
                return None

        start_battery = _safe_get_battery()
        target_battery = target_level

        # 前置判断：只有能正常读取电量时，才做“无需充电”的快速返回
        if start_battery is not None:
            if start_battery > charging_trigger_level:
                t_log.info(f'Now the battery level {start_battery} is higher than charging trigger level {charging_trigger_level}, it will not charge.',ext_event=True)
                return False
            if start_battery >= target_battery:
                t_log.info(f'Now the battery level {start_battery} is reached target {target_battery}. Will go.',ext_event=True)
                return False

        if stop_all_recent_app_before_charge:
            self.screen_on_and_unlock()
            self.stop_visible_recent_tasks(soft_stop=False)
            self.press_home_key(3)
            time.sleep(0.5)

        self.screen_off()

        if start_battery is None:
            t_log.warning(f'Cannot read battery level (device may be disconnected). Enter tolerant charge waiting to target {target_battery}%.', ext_event=True)
        else:
            t_log.warning(f'Now the battery level {start_battery} is lower than {target_battery}, it will automatically charge to {target_battery}.', ext_event=True)

        # 记录首次成功读取到的电量，用于更准确的日志
        first_seen_battery = start_battery

        for _ in range(max_loop):
            time.sleep(single_check_duration)
            now_time = datetime.now()
            charge_duration = now_time - start_time

            now_battery = _safe_get_battery()
            if now_battery is None:
                # 设备未连接，周期性提示
                if now_time >= next_check_time:
                    next_check_time += interval_for_show
                    t_log.info(f'Charging in progress (device not connected to PC): charged for {charge_duration}, waiting to reach target {target_battery}% and reconnect...', ext_event=True)
                continue

            if first_seen_battery is None:
                first_seen_battery = now_battery

            if now_battery >= target_battery:
                t_log.info(f'Charging finished! Init battery level {first_seen_battery}, it has been charging for {charge_duration} now, the battery level is {now_battery}, has reach {target_battery}.', ext_event=True)
                self.screen_on_and_unlock()
                if disconnected_once:
                    t_log.info('Device seems reconnected. Continue by waking and unlocking the screen.', ext_event=True)
                time.sleep(1)
                break
            else:
                if now_time >= next_check_time:
                    next_check_time += interval_for_show
                    t_log.info(f'Init battery level {first_seen_battery}, it has been charging for {charge_duration} now, the battery level is {now_battery}, and the target is {target_battery}.', ext_event=True)
        else:
            now_battery = _safe_get_battery()
            now_time = datetime.now()
            charge_duration = now_time - start_time
            t_log.warning(
                f'After {charge_duration} of charging, the battery was charged from {first_seen_battery} to {now_battery}, but exceeded the time limit and was forced to exit charging.',
                ext_event=True)
            self.screen_on_and_unlock()
            time.sleep(1)
        return True

    def open_url(self, url):
        """
        一键打开网址

        Args:
            url: 要打开的网址，如 'https://www.example.com'
        """
        adb.browser_web(self.device_id, url)

    def disable_screen_lock(self):
        """
        关闭解锁功能（包括滑动解锁）

        通过adb命令禁用屏幕锁定，关闭所有解锁方式包括滑动解锁
        """
        adb.remove_swipe_lock(self.device_id)

    def make_call(self, phone_number: str):
        """通过ADB拨打电话"""
        return adb.make_call(self.device_id, phone_number)

    def is_high_level_permission_allowed(self, package_name: str, permission_name: str) -> bool:
        return adb.is_high_level_permission_allowed(self.device_id, package_name, permission_name)

    def is_manage_external_storage_permission_allowed(self, package_name: str):
        return self.is_high_level_permission_allowed(package_name, 'MANAGE_EXTERNAL_STORAGE')

    def grant_manage_external_storage(self, package_name: str):
        self.grant_high_level_permission(package_name, 'MANAGE_EXTERNAL_STORAGE')
        # try:
        #     self.u2d.shell(f'set --user 0 {package_name} MANAGE_EXTERNAL_STORAGE allow')
        # except Exception as e:
        #     pass
        # result_content = self.u2d.shell(f'appops get --user 0 {package_name} MANAGE_EXTERNAL_STORAGE').output
        # def _start_app():
        #     self.u2d.app_start(package_name, wait=False)
        # if "MANAGE_EXTERNAL_STORAGE: allow" not in result_content:
        #     self.stop_app(package_name)
        #     time.sleep(1)
        #     t = threading.Thread(target=_start_app)
        #     t.start()
        #     self.u2d.xpath('android:id/switch_widget').click_exists(timeout=5)
        #     self.u2d.xpath('//*[@resource-id="com.android.settings:id/switchWidget"]').click_exists(timeout=5)
        #     t.join()
        #     time.sleep(1)
        #     self.stop_app(package_name)
        #     self.press_back_key()
        #     self.press_home_key()
        # self.start_app(package_name)
        # result_content = self.u2d.shell(f'appops get --user 0 {package_name} MANAGE_EXTERNAL_STORAGE').output
        # assert "MANAGE_EXTERNAL_STORAGE: allow" in result_content,"grant permission MANAGE_EXTERNAL_STORAGE fail! "

    def check_app_position_line(self, app_name: str):
        """
        属于静态模型时延类的定制功能，需要保证应用图标，必须放在应用列表的最后一行，注意不是常驻dock栏，因为这样启动动效一定是从上面开始展开的
        """

        app_list = self.u2d.xpath(f'//*[@content-desc="{app_name}"]').all()
        app_y_pos = [app.bounds['bottom'] for app in app_list]
        app_center_pos = [app.center() for app in app_list]

        view_group_bottom = self.xpath_get('//android.widget.ScrollView//android.view.ViewGroup//android.view.ViewGroup').get().bounds['bottom']
        for icon_bottom, [x_center, y_center] in zip(app_y_pos, app_center_pos):
            if view_group_bottom - icon_bottom < 10: #几乎贴合的意思
                return True, [x_center, y_center]

        return False, [0, 0]


    def close_playstore_auto_update(self,):

        max_retries = 3
        for retry_count in range(max_retries):
            try:
                self.stop_app("com.android.vending")
                self.start_app("com.android.vending")
                self.click_wait('//*[contains(@content-desc, "Account and settings")]', pre_wait=3, timeout=3)
                xpath = '//*[@text="Settings"]'
                max_swipes = 3
                account_elem = None
                if self.u2d.xpath(xpath).exists:
                    account_elem = self.u2d.xpath(xpath)
                else:
                    for i in range(max_swipes):
                        self.u2d.swipe_ext("up", 0.7)
                        time.sleep(1.5)
                        if self.u2d.xpath(xpath).exists:
                            account_elem = self.u2d.xpath(xpath)
                            break
                if account_elem and account_elem.exists:
                    account_elem.click()
                self.click_wait('//*[@text="Settings"]', pre_wait=3, timeout=3)
                self.click_wait('//*[@text="Network preferences"]', pre_wait=3, timeout=3)
                self.click_wait('//*[@text="Auto-update apps"]', pre_wait=3, timeout=3)
                self.click_wait('//*[contains(@text, "t auto-update apps")]', pre_wait=3, timeout=3)
                time.sleep(2)
                self.stop_app("com.android.vending")
                break
            except Exception as e:
                if retry_count < max_retries - 1:
                    t_log.warning(f'pre_standby_mock_1 执行失败，进行第 {retry_count + 1} 次重试。错误信息: {e}',
                                        ext_event=True)
                    time.sleep(2)  # 等待 2 秒后重试
                else:
                    t_log.error(f'pre_standby_mock_1 执行失败，已重试 {max_retries} 次均失败。错误信息: {e}',
                                      ext_event=True)
                    raise