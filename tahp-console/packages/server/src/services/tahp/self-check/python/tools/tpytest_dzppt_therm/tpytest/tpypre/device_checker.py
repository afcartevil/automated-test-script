import datetime
import os
import subprocess
import time
from typing import Optional

import uiautomator2

from powertrde.env import ASSETS_DIR, ADB_EXE
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends.u2utils import U2DeviceProtocol
from tpytest.tpypre.checker import Checker


class DeviceChecker(Checker):
    def __init__(self, sn):
        self.sn = sn
        self.last_connected_u2_device: Optional[uiautomator2.Device, U2DeviceProtocol] = None

    def check_battery(self, need_battery: int):
        batt = adb.read_battery(self.sn)
        if batt < need_battery:
            raise Exception(f"Phone battery did not reach {need_battery}%")

    def check_time(self):
        """检查PC和Android手机的时间差"""
        pc_time = datetime.datetime.now()
        android_time = self.get_android_local_time()

        if android_time is None:
            raise Exception("Unable to get the time of Android phone")

        time_difference = abs((pc_time - android_time).total_seconds())

        threshold_seconds = 60

        if time_difference > threshold_seconds:
            raise Exception(f"Time difference between phone and PC is too large: {time_difference} seconds")

    def get_android_local_time(self):
        # 使用adb命令获取Android手机的时间
        result = adb.exec_cmd(self.sn, "date +'%Y-%m-%d %H:%M:%S'")[0]
        # 解析时间字符串
        phone_time = datetime.datetime.strptime(result, '%Y-%m-%d %H:%M:%S')
        return phone_time

    def set_screen_sleep_delay(self, sleep_timeout: int):
        if adb.get_screen_off_timeout(self.sn) < sleep_timeout:
            adb.set_screen_off_timeout(self.sn, sleep_timeout)
            time.sleep(1)
            adb.poweroff_phone_screen(self.sn)
            time.sleep(1)
            adb.poweron_screen_and_unlock(self.sn)
        adb.poweron_screen_and_unlock(self.sn)

    def check_os_language(self, language: str):
        if adb.exec_cmd(self.sn, 'getprop persist.sys.locale')[0].strip() != language:
            raise Exception(f"You must set the system language of your phone to '{language}'!")

    def uninstall_u2d(self):
        adb.uninstall_apk(self.sn, "com.github.uiautomator")
        adb.uninstall_apk(self.sn, "com.github.uiautomator.test")

    def connect_u2_device(self, force_refresh: bool):
        if not force_refresh and self.last_connected_u2_device and self.last_connected_u2_device.serial == self.sn:
            return self.last_connected_u2_device
        adb.stop_app(self.sn, "com.github.uiautomator")
        try:
            any_installed = False
            if not adb.package_is_installed(self.sn, "com.github.uiautomator"):
                adb.install_apk(self.sn, os.path.join(ASSETS_DIR, 'uia2', "app-uiautomator.apk"))
                any_installed = True
            if not adb.package_is_installed(self.sn, "com.github.uiautomator.test"):
                adb.install_apk(self.sn, os.path.join(ASSETS_DIR, 'uia2', "app-uiautomator-test.apk"))
                any_installed = True
            if any_installed:
                time.sleep(0.2)
            last_connected_u2_device = uiautomator2.connect(self.sn)
            time.sleep(0.3)
            return last_connected_u2_device
        except Exception as e:
            raise Exception(f"Cannot connect to the phone via UI automator2!\nDetails: {e}")

    def set_heads_up_notify_enabled(self, enabled):
        adb.exec_cmd(self.sn, f"settings put global heads_up_notifications_enabled {1 if enabled else 0}")

    def check_network_connection(self):
        if adb.is_airplane_mode_on(self.sn):
            adb.exit_airplane_mode(self.sn)
            time.sleep(3)
        if not adb.is_wifi_open(self.sn):
            adb.open_close_wifi(self.sn, True)
            time.sleep(3)
        is_pass = False
        for i in range(3):
            try:
                result = subprocess.run(
                    [ADB_EXE, "-s", self.sn, "shell", "ping", "-c", "1", "google.com"],
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
            raise Exception('Unable to connect to Google. Please confirm if its network is functioning properly.')

    def check_app_install(self):
        pass
