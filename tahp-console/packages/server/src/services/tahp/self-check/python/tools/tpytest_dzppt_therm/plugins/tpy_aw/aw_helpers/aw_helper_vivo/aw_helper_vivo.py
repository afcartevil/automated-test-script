import os
import re
import time

from powertrde.env import GET_RES_SCHEME_DIR
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_helpers.aw_helper_vivo.helper_constants_vivo import HelperConstantsVivo
from tpy_aw.u2d_test_helper import U2DTestHelper


class AwHelperVivo(HelperConstantsVivo, U2DTestHelper):
    aw_name = 'vivo'


    def check_app_position(self, app_name, position):
        try:
            assert position in (1, 2, 3, 4), f"不支持判定位置 {position}"

            adb.press_home_key(self.device_id)
            time.sleep(0.3)
            adb.press_home_key(self.device_id)
            time.sleep(1)

            u2d = self.u2d
            elements = u2d.xpath(f'//*[@text="{app_name}"]').all()
            if not elements:
                return False

            b = elements[0].info['bounds']
            [top_left_x, top_left_y], [_, _] = self.get_homeapp_x_y_for_index(position)

            return abs(b['left'] - top_left_x) < 45 and abs(b['top'] - top_left_y) < 180

        except Exception as e:
            # logging.info('位置不符合')
            return False
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
        u2d.long_click(pos_x, pos_y, 1)
        u2d.sleep(1)
        if u2d.xpath('//*[@text="Remove"]').exists:
            u2d.xpath('//*[@text="Remove"]').click(timeout=5)
            u2d.sleep(2)
        u2d.press('home')
        u2d.sleep(1)
        app_name = app_name.replace('_', ' ')
        width, height = u2d.window_size()
        u2d.swipe(width / 2, height * 3 / 4, width / 2, height / 4, 0.1)
        u2d.sleep(1)
        u2d.xpath('//*[@text="Apps"]').click()
        u2d.sleep(1)
        search_box = u2d.xpath('//android.widget.EditText')
        if search_box.exists:
            search_box.click(timeout=5)
            u2d.sleep(1)
            u2utils.input_text(u2d, app_name)
            u2d.sleep(1)
        else:
            assert False, 'search box not found!'
        # s_app = u2d(text=app_package)[1]
        b = u2d.xpath(f'//*[@text="{app_name}"]').all()[1].info['bounds']
        start_position = [(b['left'] + b['right']) / 2, (b['top'] + b['bottom']) / 2]
        middle_position = ((top_left_x + bottom_right_x) / 2, (top_left_y + bottom_right_y) / 2)
        time.sleep(0.5)
        u2d.drag(start_position[0], start_position[1], middle_position[0], middle_position[1]+100, 1)

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
            u2d.send_keys('Home Settings')
            u2d.sleep(1)
            u2d.xpath('//*[@resource-id="android:id/icon"]').click_exists(timeout=5)
            u2d.sleep(1)
            auto_arrange_button = u2d.xpath("(//android.widget.Switch)[4]")

        if auto_arrange_button.info['checked']:
            auto_arrange_button.click(timeout=5)
        if not auto_arrange_button.exists:
            assert False, 'auto arrange button not found'

    def get_homeapp_x_y_for_index(self, index):
        """
        根据index，获取第一个图标或者第二个图标的位置， 添加到3/ 4

        如果传入,若果传入1，表示home面，如果全部摆放成app图标，没有空余位置，那放在第1位的图标的左上角和右下角坐标
        此时，如果index==1，android.view.ViewGroup的左上角坐标与第一个app左上角重合，再偏移一些高度和宽度即可
        index = 2同理
        """
        element_group = self.u2d.xpath('(//android.view.ViewGroup)[3]').all()[
            0]  # 外面框
        element_app = self.u2d.xpath('(//android.widget.TextView)[4]').all()[
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

    def check_to_install_unplug_sim_apk(self):
        # 竞品不需要下载
        pass

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

        if use_sim_index == 1:
            first_index = 0
            second_index = 1
        else:
            first_index = 1
            second_index = 0


        sim_title_group_xpath = '//*[@resource-id="com.android.settings:id/image"]'
        self.assert_wait_ui_obj(sim_title_group_xpath, timeout=10, post_wait=1)
        self.u2d.xpath(sim_title_group_xpath).all()[first_index].click()

        u2d.sleep(3)
        btn_enable = u2d.xpath('//*[@resource-id="com.android.settings:id/switch_btn"]')
        if not btn_enable.info['checked']:
            btn_enable.click()
            u2d.sleep(1)
        u2d.press('back')
        u2d.sleep(2)

        self.assert_wait_ui_obj(sim_title_group_xpath, timeout=5, post_wait=1)
        self.u2d.xpath(sim_title_group_xpath).all()[second_index].click()

        u2d.sleep(3)
        btn_enable = u2d.xpath('//*[@resource-id="com.android.settings:id/switch_btn"]')
        if not btn_enable.info['checked']:
            btn_enable.click()
        elif use_sim_index != 0:
            btn_enable.click()
            u2d.sleep(3)
            btn_enable.click()
        u2d.sleep(1)
        self.stop_app('com.android.settings')

    def set_settings_sim_enabled(self, sim_index: int = 1, enable: bool = True):
        self.screen_on_and_unlock()
        u2d = self.u2d
        self.restart_app('com.android.settings')
        u2d.sleep(2)
        u2d.xpath('//*[contains(@text, "SIM")]').click()
        u2d.sleep(5)
        if sim_index == 1:
            self.click_wait(u2d.xpath(
                '//*[@resource-id="com.android.settings:id/image"]').all()[
                                0], pre_wait=1,
                            timeout=5, post_wait=1)
        else:
            self.click_wait(u2d.xpath(
                '//*[@resource-id="com.android.settings:id/image"]').all()[
                                1], pre_wait=1,
                            timeout=5, post_wait=1)
        u2d.sleep(1)
        btn_enable = u2d.xpath('//android.widget.Switch[2]')
        if btn_enable.info['checked'] != enable:
            btn_enable.click()
            u2d.sleep(1)
        if u2d.xpath('//android.widget.Switch[2]').info['checked'] != enable:
            u2d.app_stop('com.android.settings')
            raise Exception(f"A SIM card indexed as {sim_index} failed to set! ")
        u2d.app_stop('com.android.settings')

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
        phone_number = re.sub(r"[^\d]", "", phone_number)[2:]


        cn_card.click(timeout=2)
        text_from_control = u2d(textContains="SIM").get_text(timeout=2)
        match = re.search(r'\d+', text_from_control)
        cn_sim_index = match.group(0) if match else 1
        return cn_sim_index, phone_number

    def close_data_warn(self):
        """关闭流量提醒"""
        self.restart_settings_activity()
        self.click_wait(self.u2d(textMatches=".*Search.*"), pre_wait=1, timeout=10, post_wait=1)
        time.sleep(1)
        u2utils.input_text(self.u2d, 'data limit')
        self.click_wait('(//*[@resource-id="android:id/title"])[2]', pre_wait=1, timeout=15, post_wait=2)
        time.sleep(4 if self.is_sprd else 3)
        data_warn = self.u2d.xpath('//*[@text="Data warning"]')
        if data_warn.info["enabled"] == "true":
            self.u2d.xpath('//*[@resource-id="com.android.settings:id/switchWidget"]').all()[0].click()
        data_limit = self.u2d.xpath('//*[@text="Data limit"]')
        if data_limit.info["enabled"] == "true":
            self.u2d.xpath('//*[@resource-id="com.android.settings:id/switchWidget"]').all()[1].click()

        self.press_home_key()
        self.stop_settings()

    def set_dialer_default(self):
        # 设置默认Phone应用
        adb.exec_cmd(self.device_id, 'cmd role add-role-holder android.app.role.DIALER com.android.dialer')

    def grant_debug_logger_permissions(self):
        eng_package = 'com.mediatek.gnssdebugreport'
        self.grant_all_useful_permissions(eng_package)
        adb.grant_android_permissions(self.device_id, eng_package, ['BLUETOOTH_SCAN'])

    def dex2oat_transform_package_to_speed_profile(self, app_name):
        pass
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
        self.click_wait('//*[@text="Search settings"]', timeout=8, post_wait=1)
        u2utils.input_text(self.u2d, 'Automatically')
        self.u2d.press("back")
        time.sleep(1)
        for i in range(5):
            self.und_u2.swipe_direction("up")
            if self.u2d.xpath('//*[@text="Auto-sync app data"]').exists:
                self.u2d.xpath('//*[@text="Auto-sync app data"]').click()
                break
        self.u2d.xpath('//android.widget.Switch[@checked="true"]').click_exists(timeout=2)
        self.u2d.xpath('//*[@text="OK"]').click_exists(timeout=2)
        self.u2d.app_stop('com.android.settings')

        # 关闭Automatic system update
        adb.set_settings_value(self.device_id, 'global', 'ota_disable_automatic_update', 1)

        # Auto-update apps
        self.restart_app('com.android.vending')
        self.wait_ui_obj('//*[@text="Apps"]', timeout=10, post_wait=1)
        self.u2d.xpath('(//*[@resource-id="com.android.vending:id/0_resource_name_obfuscated"])[6]').click()
        self.click_wait('//*[@text="Settings"]', timeout=8, post_wait=1)
        time.sleep(2)
        self.u2d.xpath('//*[@text="Got it"]').click_exists(timeout=2)
        if not self.u2d.xpath('//*[@text="Network preferences"]').exists:
            self.u2d.xpath('//*[@text="General"]').click()
        self.click_wait('//*[@text="Network preferences"]', timeout=8, post_wait=1)
        self.click_wait('//*[@text="Auto-update apps"]', timeout=8, post_wait=1)
        self.click_wait('//*[@text="Don\'t auto-update apps"]', timeout=8, post_wait=1)
        self.u2d.app_stop('com.android.vending')


    def open_close_airplane_mode(self, is_open: bool):
        if self.is_airplane_mode_on == is_open:
            return
        self.screen_on_and_unlock()
        u2d = self.u2d
        u2d.app_stop("com.android.settings")
        u2d.sleep(2)
        u2d.app_start("com.android.settings")
        u2d.sleep(2)
        self.u2d(textContains="More connections").click()
        u2d.sleep(2)
        self.u2d(textContains='Airplane mode').click(timeout=5)
        u2d.sleep(3)
        u2d.app_stop("com.android.settings")
        u2d.sleep(1)


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
        u2utils.input_text(u2d, 'Home Settings')
        u2d.sleep(5)
        u2d.xpath('//*[@resource-id="android:id/icon"]').click_exists(timeout=5)
        u2d.sleep(1)
        auto_arrange_button = u2d.xpath("(//android.widget.Switch)[3]")

        if auto_arrange_button.info['checked']:
            auto_arrange_button.click(timeout=5)
        if not auto_arrange_button.exists:
            assert False, 'auto arrange button not found'

    def get_launcher_icon(self,package_name:str):
        if self.u2d.xpath('//*[@text="All apps"]').exists:
            icon_view_list = self.u2d.xpath('//*[@text="All apps"]/../../*').all()[1:]
        else:
            icon_view_list = self.u2d.xpath('//androidx.recyclerview.widget.RecyclerView//android.widget.TextView').all()
        if icon_view_list:
            return icon_view_list
        else:
            raise Exception('应用图标不存在')

    def get_launcher_icon(self,package_name:str):
        if self.u2d.xpath('//*[@text="All apps"]').exists:
            icon_view_list = self.u2d.xpath('//*[@text="All apps"]/../../*').all()[1:]
        else:
            icon_view_list = self.u2d.xpath('//androidx.recyclerview.widget.RecyclerView//android.widget.TextView').all()
        if icon_view_list:
            return icon_view_list
        else:
            raise Exception('应用图标不存在')

    def enter_small_window(self,package):
        """
        进入小窗
        """
        self.u2d.press("home")

    def clear_recent_apps_by_ui(self, post_clear_remaining_cards_by_swipe=False):
        time.sleep(2)
        self.press_app_switch_key()
        time.sleep(1)
        self.u2d.xpath('//*[contains(@content-desc, "Clean") or contains(@resource-id, "clean")]').click()
        time.sleep(2)
        if post_clear_remaining_cards_by_swipe:
            self.clear_recent_cards_by_swipes()