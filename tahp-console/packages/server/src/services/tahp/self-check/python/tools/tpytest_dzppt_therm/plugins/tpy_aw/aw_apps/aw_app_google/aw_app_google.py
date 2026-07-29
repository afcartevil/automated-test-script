import time
from deprecated import deprecated

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase
from tpytest_extends.scheme.cases_scheme import CasesScheme


class AwAppGoogle(AwAppBase):
    aw_name = 'Google'
    default_app_package = 'com.google.android.googlequicksearchbox'

    def check_at_homepage(self, raise_exception=True):
        result, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.google.android.googlequicksearchbox:id/googleapp_navigation_bar_discover"]', click=True)
        if result:
            t_log.debug('已在Google主页')
            return True
        elif raise_exception:
            raise Exception('不在Google首页')

        return False

    def view_news(self, swipe_times=0):
        time.sleep(2)
        t_log.info("滑动主页")
        self.u2d.swipe(0.5, 0.8, 0.5, 0.2, 0.2)
        time.sleep(2)
        like_btn_result = self.u2d.xpath('//*[@content-desc="Like"]').wait(timeout=2)
        if like_btn_result:
            t_log.info('找到Like按钮')
            like_btn = self.u2d.xpath('//*[@content-desc="Like"]')
            x = (like_btn.info['bounds']['left'] + like_btn.info['bounds']['right']) / 2
            y = (like_btn.info['bounds']['top'] + like_btn.info['bounds']['bottom']) / 2
            self.u2d.click(x, y-200)
        elif swipe_times < 5:
            t_log.info('没有找到Like按钮,滑动主页')
            swipe_times += 1
            self.view_news(swipe_times)
        else:
            raise XPathElementNotFoundError('没有找到评论按钮')

    def search_web(self, website):
        """
        搜索网页
        """
        self.u2d.xpath('//*[@resource-id="googleapp_facade_search_box" or @resource-id="com.google.android.googlequicksearchbox:id/googleapp_srp_search_box"]').click()
        time.sleep(2)
        u2utils.input_text(self.u2d, website)
        self.u2d_helper.press_key(66)  # KEYCODE_ENTER
        time.sleep(5)

