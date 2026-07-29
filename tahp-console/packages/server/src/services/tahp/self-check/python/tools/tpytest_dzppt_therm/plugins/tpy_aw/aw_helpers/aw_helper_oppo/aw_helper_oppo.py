import subprocess
import time

from uiautomator2 import XPathElementNotFoundError
from powertrde.framework.logs_protocol import logs_p
from powertrde.utils.trde import adb
from tpy_aw.aw_apps.aw_app_desimu.aw_app_desimu import AwAppDesimu
from tpy_aw.aw_helpers.aw_helper_oppo.helper_constants_oppo import HelperConstantsOppo
from tpy_aw.u2d_test_helper import U2DTestHelper


class AwHelperOppo(HelperConstantsOppo, U2DTestHelper):
    aw_name = 'oppo'

    def clear_recent_apps_by_ui(self, post_clear_remaining_cards_by_swipe=False):
        time.sleep(2)
        self.press_app_switch_key()
        time.sleep(1)
        self.click_exists('//android.widget.Button')
        time.sleep(2)
        if post_clear_remaining_cards_by_swipe:
            self.clear_recent_cards_by_swipes()

    def clear_recent_cards_by_swipes(self, call_recent_ui_first=True):
        if call_recent_ui_first:
            self.press_app_switch_key()
            time.sleep(1)
        
        # 获取屏幕尺寸
        info = self.u2d.info
        width = info.get('displayWidth', 1080)
        height = info.get('displayHeight', 2400)
        
        for _ in range(255):
            # 检查当前界面是否还有FrameLayout元素（代表还有卡片）
            has_cards = False
            try:
                if self.u2d.xpath('//android.widget.ImageButton').exists:
                    has_cards = True
            except Exception:
                pass
            
            # 如果没有FrameLayout元素了，说明清理完成
            if not has_cards:
                self.press_back_key()
                break
            
            # 使用坐标滑动：从屏幕中下部向上滑
            start_x = width // 2
            start_y = int(height * 0.65)
            end_x = width // 2
            end_y = int(height * 0.25)
            self.u2d.swipe(start_x, start_y, end_x, end_y, duration=0.1)
            time.sleep(0.6)
        
        time.sleep(1)

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
                self.u2d(resourceId = 'android:id/button3').click_exists()
                return
            else:
                self.u2d(resourceId='com.android.settings:id/add_language').click()
                self.u2d.sleep(1)
                self.u2d(textContains='English').click()
                self.u2d.sleep(1)
                self.u2d(resourceId = 'android:id/button3').click_exists()
            self.u2d.sleep(1)
            if adb.exec_cmd(self.device_id, 'getprop persist.sys.locale')[0].strip() != 'en-US':
                raise Exception("set system language to English！")
            else:
                logs_p().log('set system language to English successfully！')

    def insert_sms(self, count=1):
        aw_desimu:AwAppDesimu = self.get_casted_app_aw(AwAppDesimu)
        self.grant_manage_external_storage(aw_desimu.app_package)
        aw_desimu.enter_app()
        aw_desimu.set_user_data(message_count=count)

    def set_brightness_and_close_auto_bright(self, level: int):
        adb.settings_set_screen_auto_brightness(self.device_id, False)
        adb.settings_set_screen_brightness(self.device_id, round((level / 255) * 18431))
        time.sleep(1)

    def open_close_airplane_mode(self, is_open: bool):
        if self.is_airplane_mode_on == is_open:
            return
        self.screen_on_and_unlock()
        # 设置飞行模式状态为关闭(0)
        cmd1 = f'adb -s {self.device_id} shell settings put global airplane_mode_on 0'
        subprocess.run(cmd1, shell=True)
        time.sleep(1)

    def set_ring_volume_level(self, level: int):
        # 不支持设置铃声音量
        pass

    def set_screen_fps_auto(self):
        # 暂时不支持该方法，因为没有人会动该选项
        pass

    def assert_hotspot_closed(self,is_open=bool):
        # 暂时不支持该方法，因为没有人会动该选项
        pass

    def close_sidebar(self):
        """
        关闭 oppo 手机的侧边栏功能（Smart Sidebar）
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
        # 暂时不支持该方法，因为没有人会动该选项
        pass

    def set_navi_mode_gesture(self):
        """
        在oppo设备上设置手势导航模式
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
