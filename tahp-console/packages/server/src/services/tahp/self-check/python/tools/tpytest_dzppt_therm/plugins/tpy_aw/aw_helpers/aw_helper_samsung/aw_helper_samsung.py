import time

from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_helpers.aw_helper_samsung.helper_constants_samsung import HelperConstantsSamsung
from tpy_aw.u2d_test_helper import U2DTestHelper


class AwHelperSamsung(HelperConstantsSamsung, U2DTestHelper):
    aw_name = 'samsung'

    def install_app(self, apk_or_xapk_filepath: str, flags=('-g', '-r', '-t')):
        if apk_or_xapk_filepath.lower().endswith('.apk'):
            return self._install_apk_file(apk_or_xapk_filepath, flags=flags)
        else:
            return self._install_xapk_file(apk_or_xapk_filepath, flags=flags)

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
        time.sleep(3)
        adb.tap_on_screen_by_percent(self.device_id, 0.5, 0.783)
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

    def get_recent_card_texts(self):
        xpath = '//android.view.View'
        region = (0.2, 0, 0.8, 0.5)
        els = u2utils.xpath_within_region(self.u2d, xpath, region=region)
        des = []
        for e in els:
            t = e.info.get('contentDescription', '')
            if t:
                des.append(t)
        return des

    def swipe_recent_card_and_check_reach_edge(self, swipe_left=True, find_icon_name=None) -> int:
        def _find_icon_name(tv_texts):
            if not find_icon_name:
                return False
            for elem in tv_texts:
                if find_icon_name in elem:
                    return True
                # if find_icon_name.startswith(elem.rstrip('.')):
                #     return True
            return False

        direction = 'left' if swipe_left else 'right'
        before = self.get_recent_card_texts()
        if _find_icon_name(before):
            return 2
        self.und_u2.swipe_direction(direction, 0.4, speed=70)
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
                self.und_u2.swipe_direction(_conti_swipe_direction, 0.3, speed=100)
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
                self.u2d.xpath(f'//*[contains(@content-desc, "{full_icon_name}")]').click()
                time.sleep(1)
                break
        if _find_result != 2:
            raise Exception(f'Can not find recent card named "{full_icon_name}"!')
