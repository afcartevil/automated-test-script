import time

from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase


class LauncherLocator(U2SelectorLocator):
    ...


class AwAppLauncher(LauncherLocator, AwAppBase):
    aw_name = 'Launcher'
    default_app_package = ''

    def open_notification_center(self):
        w, h = self.u2d.window_size()
        # 从屏幕顶部中间往下滑
        self.u2d.swipe(int(w * 0.3), int(h * 0.05), int(w * 0.3), int(h * 0.3), 0.2)
        time.sleep(2)

    def open_quicksettings_center(self):
        w, h = self.u2d.window_size()
        # 从屏幕顶部靠右往下滑
        self.u2d.swipe(int(w * 0.85), int(h * 0.05), int(w * 0.85), int(h * 0.3), 0.2)
        time.sleep(2)

    def open_global_search(self):
        w, h = self.u2d.window_size()
        # 从屏幕中间偏下往下滑
        self.u2d.swipe(w // 2, int(h * 0.5), w // 2, int(h * 0.95), 0.1)
        time.sleep(2)

    def open_the_a_z_interface(self):
        w, h = self.u2d.window_size()
        # 从屏幕中间偏下往上滑
        self.u2d.swipe(w // 2, int(h * 0.95), w // 2, int(h * 0.5), 0.1)
        time.sleep(2)

    def click_recent_app(self, app_name: str = None):
        """
        点击最近使用的应用
        特别注意：不滑动
        """
        self.u2d.click(0.5, 0.5)
