import time

from powertrde.utils.trde import adb
from tpy_aw.aw_helpers.aw_helper_transsion.aw_helper_transsion_tos16 import AwHelperTranssionTos16


class AwHelperTranssionXospadTos16(AwHelperTranssionTos16):
    variant_key = 'xospad_tos16'

    def clear_recent_apps_by_ui(self, post_clear_remaining_cards_by_swipe=False):
        time.sleep(2)
        self.press_app_switch_key()
        time.sleep(1)
        adb.tap_on_screen_by_percent(self.device_id, 0.5, 0.92)
        time.sleep(2)
        if post_clear_remaining_cards_by_swipe:
            self.clear_recent_cards_by_swipes()