import time
from typing import Optional

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.i18n import I18n
from powertrde.framework.tran_logger import t_log
from powertrde.utils.simple_event_center import SimpleEventCenter
from tpy_aw.aw_device_base import AwDeviceBase


class AwAppBase(AwDeviceBase):
    aw_category = 'app'
    app_info_from_nickname = False
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
            app_name = self.aw_nickname if self.app_info_from_nickname else self.aw_name
            self._app_info = AppsStaticInfo.get_app_info(app_name=app_name, variant_device_sn=self.device_real_sn)
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
        return self.u2d_helper.grant_all_runtime_permissions(self.app_package)

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
                self.u2d_helper.get_icon_name_xpath(self.app_info.icon_name)).wait(timeout=1)
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
            self.u2d_helper.soft_stop_app(self.app_info.package)
        return self.u2d_helper.search_app_from_desktop_via_ui(self.app_info.icon_name)

    def start_app_via_ui(self, stop_app_first=True, wait_after_stop=2):
        if stop_app_first:
            self.soft_stop_app()
            time.sleep(wait_after_stop)
        return self.u2d_helper.start_app_from_desktop_via_ui(self.app_info.icon_names)

    def grant_common_permissions(self):
        self.u2d_helper.grant_common_permissions(self.app_package)

    def is_app_persistent(self):
        return self.u2d_helper.is_app_persistent(self.app_package)

    def close_app_in_the_recent(self):
        """
        先点开app，从卡片里划出app
        """
        self.start_app_via_ui()
        time.sleep(1)
        self.u2d_helper.press_home_key(1)
        time.sleep(1)
        self.u2d_helper.press_recent_key()
        time.sleep(1)
        self.u2d.swipe(0.5, 0.7, 0.5, 0.1)
        time.sleep(1)
        self.u2d_helper.press_home_key()
        time.sleep(1)

    def auto_stop_persistent_app(self):
        """
        检查是不是常驻app，自动选择stop方法
        """
        if self.is_app_persistent():
            self.close_app_in_the_recent()
        else:
            self.stop_app()

    def click_xpath_with_retry(self, xpath_str, click=True, timeout=30, retry_interval=1.0):
        """
        带重试机制的控件等待和点击

        Args:
            xpath_str: 控件xpath
            click: 是否点击
            timeout: 总超时时间
            retry_interval: 重试间隔

        Returns:
            bool: 是否成功
        """
        start_time = time.time()
        end_time = start_time + timeout
        find_flag = False

        while time.time() < end_time:
            element = self.u2d.xpath(xpath_str).wait(timeout=0.5)
            if element:
                if click:
                    self.u2d.xpath(xpath_str).click()
                find_flag = True
                break

        time.sleep(retry_interval)
        # 超时后的处理
        if time.time() > start_time + retry_interval + 1:
            error_msg_en = f'Element wait timeout: {xpath_str}, timeout: {round(time.time()-start_time, 2)} seconds'
            error_msg_zh = f'控件等待超时: {xpath_str}, 超时时间: {round(time.time()-start_time, 2)}秒'
            error_msg = I18n.gen_str(error_msg_en, error_msg_zh)
            t_log.error(error_msg)
            if not find_flag:
                raise XPathElementNotFoundError(error_msg)
