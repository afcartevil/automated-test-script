import time
from typing import Optional

from powertrde.utils.simple_event_center import SimpleEventCenter
from tpy_aw.aw_device_base import AwDeviceBase


class AwAppBase(AwDeviceBase):
    aw_category = 'app'
    default_app_package = ''
    app_shared_signals: SimpleEventCenter = SimpleEventCenter()

    def __init__(self):
        super().__init__()
        from tpy_aw.u2d_test_helper import U2DTestHelper
        self.u2d_helper: Optional[U2DTestHelper] = None
        self._app_info = None

    @property
    def app_package(self):
        try:
            return self.app_info.package
        except Exception:
            return self.default_app_package

    @property
    def app_name(self):
        return self.aw_name

    @property
    def app_info(self):
        if self._app_info is None:
            from tpytest_extends.scheme.apps_static_info import AppsStaticInfo
            self._app_info = AppsStaticInfo.get_app_info(app_name=self.aw_name, variant_device_sn=self.device_real_sn)
        return self._app_info

    def clear_app_data(self):
        self.u2d_helper.clear_app_data(self.app_package)

    def open_app(self):
        self.u2d_helper.open_app(self.app_package)

    def restart_app(self):
        self.u2d_helper.restart_app(self.app_package)

    def open_app_by_monkey(self):
        self.u2d_helper.open_app_by_monkey(self.app_package)

    def restart_app_by_monkey(self):
        self.u2d_helper.restart_app_by_monkey(self.app_package)

    def soft_stop_app(self):
        self.u2d_helper.soft_stop_app(self.app_package)

    def stop_app(self):
        self.u2d_helper.stop_app(self.app_package)

    def grant_all_runtime_permissions(self):
        self.u2d_helper.grant_all_runtime_permissions(self.app_package)

    def start_activity(self, relative_activity_name: str, wait=True, flag=''):
        self.u2d_helper.start_app_activity(self.app_package, relative_activity_name, wait, flag)

    def start_launcher_activity(self, wait=True, flag=''):
        self.u2d_helper.start_launcher_activity(self.app_package, wait, flag)

    def restart_launcher_activity(self, wait=True, flag=''):
        self.u2d_helper.stop_app(self.app_package)
        self.u2d_helper.start_launcher_activity(self.app_package, wait, flag)

    def get_launcher_activity(self):
        return self.u2d_helper.get_launcher_activity(self.app_package)

    def search_app_from_desktop_via_ui(self):
        self.u2d_helper.press_home_key(times=3)
        for i in range(10):
            app_icon = self.u2d.xpath(
                f'//*[@text="{self.app_info.icon_name}"] or @text="● {self.app_info.icon_name}"]').wait(timeout=1)
            if app_icon:
                return True
            else:
                self.u2d.swipe(0.7, 0.5, 0.3, 0.5)
                time.sleep(1)
        return False

    def open_playstore_page(self):
        return self.u2d_helper.open_playstore_page(self.app_package)

    def u2_stop_watchers(self):
        self.u2_watcher_manager.stop_watchers(self.u2d)

    def search_app_via_ui(self, stop_app_first=True):
        if stop_app_first:
            self.u2d_helper.stop_app(self.app_info.package)
        return self.u2d_helper.search_app_from_desktop_via_ui(self.app_info.icon_name)

    def start_app_via_ui(self, stop_app_first=True):
        if stop_app_first:
            self.stop_app()
        return self.u2d_helper.start_app_from_desktop_via_ui(self.app_info.icon_name)

    def grant_common_permissions(self):
        self.u2d_helper.grant_common_permissions(self.app_package)
