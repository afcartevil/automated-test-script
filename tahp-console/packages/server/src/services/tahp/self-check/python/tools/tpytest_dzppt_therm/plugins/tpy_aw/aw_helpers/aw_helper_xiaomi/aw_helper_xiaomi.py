import time
from threading import Thread

from powertrde.utils.trde import adb
from tpy_aw.aw_apps.aw_app_desimu.aw_app_desimu import AwAppDesimu
from tpy_aw.aw_helpers.aw_helper_xiaomi.helper_constants_xiaomi import HelperConstantsXiaomi
from tpy_aw.u2d_test_helper import U2DTestHelper


class AwHelperXiaomi(HelperConstantsXiaomi, U2DTestHelper):
    aw_name = 'xiaomi'

    def install_app(self, apk_or_xapk_filepath: str, flags=('-g', '-r', '-t')):
        install_result = False

        _install_apk_method = super().install_app

        def _inner_install():
            nonlocal install_result
            install_result = _install_apk_method(apk_or_xapk_filepath, flags=flags)

        t = Thread(target=_inner_install)
        t.start()
        # xpath_obj = self.u2d.xpath("//android.widget.Button[@text='Install']")
        xpath_obj = self.u2d(text = "Install")
        for _ in range(240):
            ret = self.click_wait(xpath_obj, pre_wait=1, timeout=0, post_wait=1, no_raise=True)
            if ret or not t.is_alive():
                break
        t.join()
        return install_result

    def insert_sms(self, count=1):
        aw_desimu: AwAppDesimu = self.get_casted_app_aw(AwAppDesimu)
        aw_desimu.enter_app()
        aw_desimu.set_user_data(message_count=count)
        aw_desimu.stop_app()

    # def set_all_volume_level(self, level: int):
    #     """先读取各自音量再考虑是否设置"""
    #     self.set_call_volume_level(level)
    #     self.set_ring_volume_level(level)
    #     self.set_media_volume_level(level)
    #     self.u2d.sleep(3)
    #     # XIAOMI需要重启才能恢复
    #     self.reboot_and_wait_complete()
    #     self.u2d.sleep(3)
    #     self.screen_on_and_unlock()
    #
    # def set_call_volume_level(self, level: int):
    #     adb.exec_cmd(self.device_id, f'settings put system volume_voice_earpiece {level + 2}')
    #
    # def set_ring_volume_level(self, level: int):
    #     adb.exec_cmd(self.device_id, f'settings put system volume_ring_speaker {level + 2}')
    #
    # def set_media_volume_level(self, level: int):
    #     adb.exec_cmd(self.device_id, f'settings put system volume_music_speaker {level + 2}')

    def swipe_recent_card_and_check_reach_edge(self, swipe_up=True, find_icon_name=None) -> int:
        def _find_icon_name(tv_texts):
            if not find_icon_name:
                return False
            for elem in tv_texts:
                if find_icon_name == elem:
                    return True
                # if find_icon_name.startswith(elem.rstrip('.')):
                #     return True
            return False

        direction = 'down' if swipe_up else 'up'
        before = self.get_recent_card_texts()
        if _find_icon_name(before):
            return 2
        self.und_u2.swipe_direction(direction, 0.7, speed=70)
        time.sleep(0.2)
        after = self.get_recent_card_texts()
        if _find_icon_name(after):
            return 2
        return 1 if before == after else 0

    def find_recent_app(self, full_icon_name: str, from_up_to_down=True):
        width, height = self.u2d.window_size()
        self.press_app_switch_key()
        time.sleep(1)

        _conti_swipe_direction = ('up' if from_up_to_down else 'down')

        def _conti_swipe(count: int):
            for _ in range(count):
                self.und_u2.swipe_direction(_conti_swipe_direction, 0.5, speed=400)
                time.sleep(0.1)
            time.sleep(0.4)

        _conti_swipe(7)
        for _ in range(10):
            if self.swipe_recent_card_and_check_reach_edge(not from_up_to_down):
                break
            _conti_swipe(2)
        else:
            raise Exception('Can not swipe recent cards to edge!')

        _find_result = 0
        for _ in range(100):
            _find_result = self.swipe_recent_card_and_check_reach_edge(from_up_to_down, full_icon_name)
            if _find_result:
                self.u2d.xpath(f'//*[@text="{full_icon_name}"]').click()
                time.sleep(1)
                break
        if _find_result != 2:
            raise Exception(f'Can not find recent card named "{full_icon_name}"!')