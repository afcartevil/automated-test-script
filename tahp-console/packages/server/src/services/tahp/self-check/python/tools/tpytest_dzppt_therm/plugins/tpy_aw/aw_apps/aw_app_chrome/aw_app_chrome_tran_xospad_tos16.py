import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase
from tpy_aw.aw_apps.aw_app_chrome.aw_app_chrome import AwAppChrome


class AwAppChromeTranssionXospadTos16(AwAppChrome):
    aw_name = 'Chrome'
    default_app_package = 'com.android.chrome'

    def search_web(self, website):
        """
        搜索指定网址全称
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.android.chrome:id/search_box" or @resource-id="com.android.chrome:id/url_bar"]', timeout=3)
        time.sleep(1)
        self.u2d_helper.input_text(website)
        time.sleep(2)
        adb.exec_cmd(self.device_id, 'input keyevent 66')
        time.sleep(10)


