import subprocess
import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.utils.trde import adb
from powertrde.framework.logs_protocol import logs_p
from tpy_aw.aw_helpers.aw_helper_oppo.aw_helper_oppo import AwHelperOppo


class AwHelperOppoRealmeui(AwHelperOppo):
    variant_key = 'realmeui'

    def set_brightness_and_close_auto_bright(self, level: int):
        adb.settings_set_screen_auto_brightness(self.device_id, False)
        adb.settings_set_screen_brightness(self.device_id, round((level / 255) * 18431))
        time.sleep(1)

    def set_media_volume_level(self, level: int):
        level = round(level / 15 * 160)
        super().set_media_volume_level(level)

    def set_call_volume_level(self, level: int):
        level = round(level / 15 * 9)
        super().set_call_volume_level(level)

    def set_ring_volume_level(self, level: int):
        # realmeui 不支持设置铃声音量
        pass

    def set_screen_fps_auto(self):
        # 暂时不在realme里支持该方法，因为没有人会动该选项
        pass

    def open_close_airplane_mode(self, is_open: bool):
        if self.is_airplane_mode_on == is_open:
            return
        self.screen_on_and_unlock()
        # 设置飞行模式状态为关闭(0)
        cmd1 = f'adb -s {self.device_id} shell settings put global airplane_mode_on 0'
        subprocess.run(cmd1, shell=True)
        time.sleep(1)

    def assert_hotspot_closed(self,is_open=bool):
        # 暂时不在realme里支持该方法，因为没有人会动该选项
        pass

    def close_sidebar(self):
        """
        关闭 realme 手机的侧边栏功能（Smart Sidebar）
        """
        possible_packages = ['com.coloros.smartsidebar']
        for pkg in possible_packages:
            try:
                # 检查包是否存在
                cmd = f'pm list packages {pkg}'
                result = adb._exe_adb_cmd(self.device_id, cmd)
                if result and pkg in result[0]:
                    # 尝试禁用包
                    cmd = f'pm disable-user --user 0 {pkg}'
                    adb._exe_adb_cmd(self.device_id, cmd)
                    logs_p().log(f"已尝试禁用包: {pkg}", device_id=self.device_id)
            except Exception as e:
                logs_p().log_warning(f"尝试禁用包 {pkg} 失败: {e}", device_id=self.device_id)

    def set_aod_enabled(self, enabled):
        # 暂时不在realme里支持该方法，因为没有人会动该选项
        pass

    def set_navi_mode_gesture(self):
        """
        在realme设备上设置手势导航模式
        """
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
        u2d.xpath('//android.widget.TextView[@text="System & update"]').click(timeout=2)
        u2d.sleep(1)
        try:
            u2d.xpath('//android.widget.TextView[@text="System navigation"]').click(timeout=2)
        except XPathElementNotFoundError:
            u2d.xpath('//android.widget.TextView[@text="System Navigation"]').click(timeout=2)
        # 使用指定的XPath点击手势导航选项
        u2d.xpath('//*[@resource-id="com.android.settings:id/rb_gesture_navigation"]').click(timeout=2)
        u2d.sleep(2)
        try:
            u2d.xpath('//android.widget.Button[@text="Cancel"]').click(timeout=2)
            u2d.sleep(2)
        except XPathElementNotFoundError:
            pass
        u2d.sleep(1)
        u2d.app_stop('com.android.settings')
        assert adb.get_settings_value(self.device_id, "secure",
                                      'navigation_mode') != '0', 'Failed to enable navigation bottom 3 buttons mode'

