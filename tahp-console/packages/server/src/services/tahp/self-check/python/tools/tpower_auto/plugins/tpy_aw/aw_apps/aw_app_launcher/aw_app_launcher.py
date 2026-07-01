import time

from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase


class LauncherLocator(U2SelectorLocator):
    ...


class AwAppLauncher(LauncherLocator, AwAppBase):
    aw_name = 'Launcher'
    default_app_package = ''

    def open_notification_center(self):
        self.u2d.swipe(300, 50, 300, 1000, 0.1)
        time.sleep(2)

    def open_quicksettings_center(self):
        self.u2d.swipe(700, 50, 700, 1000, 0.1)
        time.sleep(2)
