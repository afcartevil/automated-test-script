import time

from powertrde.utils.trde import adb
from tpy_aw.aw_apps.aw_app_launcher.aw_app_launcher import AwAppLauncher


class AwAppLauncherTranssionXospadTos16(AwAppLauncher):
    variant_key = 'tran_xospad_tos16'
    default_app_package = 'com.transsion.launcher3'

    def open_notification_center(self):
        w, h = self.u2d.window_size()
        # 从屏幕顶部中间往下滑
        self.u2d.swipe(int(w * 0.3), int(h * 0.01), int(w * 0.3), int(h * 0.3), 0.2)
        time.sleep(2)

    def open_quicksettings_center(self):
        w, h = self.u2d.window_size()
        # 从屏幕顶部靠右往下滑
        self.u2d.swipe(int(w * 0.85), int(h * 0.01), int(w * 0.85), int(h * 0.3), 0.2)
        time.sleep(2)

    def click_recent_app(self, app_name: str = None):
        """
        点击最近使用的应用
        特别注意：不滑动
        """
        icon_pos = self.u2d.xpath(f'//*[@text="{app_name}"]')
        x = (icon_pos.info['bounds']['left'] + icon_pos.info['bounds']['right']) / 2
        y = (icon_pos.info['bounds']['top'] + icon_pos.info['bounds']['bottom']) / 2
        adb.exec_cmd(self.device_id, f"input swipe {x} {y + 50} {x} {y + 50} 100")
