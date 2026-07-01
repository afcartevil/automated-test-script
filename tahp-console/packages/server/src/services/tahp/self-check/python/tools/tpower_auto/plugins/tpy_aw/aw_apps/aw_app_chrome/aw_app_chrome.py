import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase

class ChromeLocator(U2SelectorLocator):
    chrome_home = U2Selector().xpath('//*[@content-desc="Open the home page"]').bind()

class AwAppChrome(ChromeLocator, AwAppBase):
    aw_name = 'Chrome'
    default_app_package = 'com.android.chrome'

    def check_at_homepage(self):
        """
        检测是否在chrome首页
        """
        result, _ = self.u2d_helper.assert_icon_exist('resourceId', 'com.android.chrome:id/home_button', click=True)
        if result:
            t_log.debug('已在Chrome主页')
        else:
            raise XPathElementNotFoundError('未在Chrome主页')
        time.sleep(2)

    def set_default_browser(self):
        """
        设置为默认浏览器
        """
        self.u2d_helper.set_default_browser(self.app_package)

    def stay_at_homepage(self):
        """
        进入chrome首页
        """
        self.chrome_home.click_wait()

    def pop_not_log_in(self):
        """
        初次进入chrome的弹窗，选择不要登录账号
        """
        if self.u2d.xpath('//android.widget.Button[@text="Use without an account"]').exists:
            self.u2d.xpath('//android.widget.Button[@text="Use without an account"]').click()
            time.sleep(3)
            self.u2d.xpath('//android.widget.Button[@text="Got it"]').click_exists(timeout=2)
            time.sleep(3)
            self.u2d.xpath('//android.widget.Button[@text="Keep Google"]').click_exists(timeout=2)
            time.sleep(3)
            self.u2d.xpath('//android.widget.Button[@text="No thanks"]').click_exists(timeout=2)
            time.sleep(3)


    def search_web(self, website):
        """
        搜索指定网址全称
        """
        # chrome主页有两种形式
        screen_one, _ = self.u2d_helper.assert_icon_exist('resourceId', 'com.android.chrome:id/optional_toolbar_button_container', click=False)
        if not screen_one:
            self.u2d_helper.click_wait('//*[@resource-id="com.android.chrome:id/search_box"]/android.widget.RelativeLayout[1]', timeout=2)
            time.sleep(3)
        self.u2d_helper.click_wait('//*[@resource-id="com.android.chrome:id/search_box" or @resource-id="com.android.chrome:id/url_bar"]', timeout=3)
        time.sleep(1)
        self.u2d_helper.input_text(website)
        time.sleep(2)
        adb.exec_cmd(self.device_id, 'input keyevent 66')
        time.sleep(10)

    def open_news(self):
        """
        从chrome主页打开新闻页面
        """
        width, height = self.u2d.window_size()
        close_sync = self.u2d.xpath('//*[@resource-id="com.android.chrome:id/sync_promo_close_button"]').wait(timeout=1)
        if close_sync:
            self.u2d.xpath('//*[@resource-id="com.android.chrome:id/sync_promo_close_button"]').click()
            time.sleep(1)
        result_discover = self.u2d.xpath('//*[@text="Discover"]').wait(timeout=1)
        if result_discover:
            discover = self.u2d.xpath('//*[@text="Discover"]')
            x = (discover.info['bounds']['left'] + discover.info['bounds']['right']) / 2
            y = (discover.info['bounds']['top'] + discover.info['bounds']['bottom']) / 2 + 200
        else:
            x, y = width / 2, height / 2 + 200
        self.u2d.click(x, y)
        time.sleep(8)

    def swipe_quick_web_list(self):
        """
        左右滑动应用快捷方式区域栏
        """
        width, height = self.u2d.window_size()
        result_navigate = self.u2d(textContains='百度').wait(timeout=1)
        result_navigate2 = self.u2d_helper.und_u2.match_text('YouTube', limit_area=(0, 0, 1, 0.5))
        if result_navigate:
            navigate = self.u2d(textContains='百度')
            y = navigate.info['bounds']['top']
            self.u2d.swipe(width-200, y, 200, y)
            time.sleep(2)
            self.u2d.swipe(200, y, width-200, y)
            time.sleep(2)
        elif result_navigate2:
            y = (result_navigate2.center[1]-0.05) * height
            self.u2d.swipe(width-200, y, 200, y)
            time.sleep(2)
            self.u2d.swipe(200, y, width-200, y)
            time.sleep(2)
        else:
            # 找不到，在大概区域滑动
            self.u2d.swipe(width-200, 0.2 * height, 200, 0.2 * height)
            time.sleep(2)
            self.u2d.swipe(200, 0.2 * height, width-200, 0.2 * height)
            time.sleep(2)
            self.u2d.swipe(width-200, 0.4*height, 200, 0.4*height)
            time.sleep(2)
            self.u2d.swipe(200, 0.4*height, width-200, 0.4*height)
            time.sleep(2)

    def login_in(self):
        """
        检查登录弹窗
        """
        self.restart_launcher_activity()
        self.u2d(textContains="Continue as ").click_exists(timeout=10)
        self.u2d(text="Yes, I’m in").click_exists(timeout=15)
        self.u2d(text = "Yes, I’m in").click_exists(timeout=15)
        self.u2d(text = "Continue").click_exists(timeout=15)

    def check_is_login_success(self,username):
        """
        检查是否登录成功
        """
        self.u2d(resourceId="com.android.chrome:id/menu_button_wrapper").click_exists(timeout=10)
        self.u2d(text = "Settings").click_exists(timeout=5)
        if not self.u2d(text = username).exists:
            raise Exception("login fail!")

