import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase

class ChromeLocator(U2SelectorLocator):
    chrome_home = U2Selector().xpath('//*[@content-desc="Open the home page"]').bind()
    btn_home_page = U2Selector().xpath('//*[@resource-id="com.android.chrome:id/home_button"]').bind()  # 主页左上角的home按钮
    search_box = U2Selector().xpath('//*[@resource-id="com.android.chrome:id/search_box"]').bind()  # 搜索框
    new_tab_btn_on_home_page = U2Selector().xpath('//*[@resource-id="com.android.chrome:id/optional_toolbar_button"]').bind()  # 新建标签页按键
    menu_btn = U2Selector().xpath('//*[@resource-id="com.android.chrome:id/menu_button_wrapper"]').bind()  # 右上角三个点按钮
    new_tab_btn_on_menu = U2Selector().xpath('//android.widget.TextView[@text="New tab"]').bind()  # 右上角三个点按钮里的新建标签按键
    share_btn_on_menu = U2Selector().xpath('//android.widget.TextView[@text="Share…"]').bind()  # 右上角三个点按钮里的分享
    tab_switcher_button = U2Selector().xpath('//*[@resource-id="com.android.chrome:id/tab_switcher_button"]').bind() # 右上角带数字的按钮


class AwAppChrome(ChromeLocator, AwAppBase):
    aw_name = 'Chrome'
    default_app_package = 'com.android.chrome'

    def check_at_homepage(self, click=True):
        """
        检测是否在chrome首页
        """
        self.u2d.xpath('//*[@text="Use without an account"]').click_exists(timeout=1)
        self.u2d.xpath('//*[@text="Continue"]').click_exists(timeout=1)
        result, _ = self.u2d_helper.assert_icon_exist('resourceId', 'com.android.chrome:id/home_button', click=click)
        if result:
            t_log.debug('已在Chrome主页')
        else:
            raise XPathElementNotFoundError('未在Chrome主页')
        time.sleep(2)

    def enter_homepage(self):
        """
        进入：enter_homepage
        """
        self.btn_home_page.click_wait()
        time.sleep(1)

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

        if self.u2d.xpath('//*[@text="Choose your search engine"]').exists:
            self.u2d.xpath('//*[@text="Google"]').click()
            time.sleep(2)
            self.u2d.xpath('//*[@text="Set as default"]').click()
            time.sleep(2)
            self.u2d.xpath('//android.widget.Button[@text="No thanks"]').click_exists(timeout=2)
            time.sleep(3)


    def search_web(self, website):
        """
        搜索指定网址全称
        """
        # chrome主页有两种形式
        screen_one, _ = self.u2d_helper.assert_icon_exist('resourceId', 'com.android.chrome:id/optional_toolbar_button_container', click=False)
        if not screen_one:
            self.u2d_helper.click_exists('//*[@resource-id="com.android.chrome:id/search_box"]/android.widget.RelativeLayout[1]', timeout=2)
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

    def check_xpath(self, path):
        """
        判断某个xpath路径是否存在，chrome里的控件可能加载不出来，所以要多尝试一下
        """
        for i in range(8):
            if self.u2d.xpath(path).exists:
                return True
            self.u2d.xpath('//*[@resource-id="com.android.chrome:id/tab_switcher_button"]').click()
            time.sleep(1)
            self.u2d_helper.press_back_key()
            time.sleep(2)
        else:
            return False

    def change_default_home_page(self, sleep_time=2):
        """
        设置默认的home界面为谷歌自带的界面，不是其他的一些网页的界面
        """
        t_log.debug('检测Chrome主页')
        self.u2d_helper.xpath_click('//*[@resource-id="com.android.chrome:id/home_button"]', sleep_time=sleep_time)
        if not self.u2d_helper.xpath_get('//*[@resource-id="com.android.chrome:id/search_box"]'):
            self.u2d_helper.xpath_click('//*[@resource-id="com.android.chrome:id/menu_button_wrapper"]')
            self.u2d_helper.xpath_click('//*[@text="Settings"]')
            u2utils.scroll_find_by_xpath(self.u2d, f'//*[@text="Homepage"]')
            self.u2d_helper.xpath_click('//*[@text="Homepage"]')
            self.u2d_helper.xpath_click('//*[@text="Chrome’s homepage"]')
            self.u2d_helper.press_back_key(2, interval=1.5)
            self.u2d_helper.xpath_click('//*[@resource-id="com.android.chrome:id/home_button"]', sleep_time=2)
            assert self.u2d_helper.xpath_get('//*[@resource-id="com.android.chrome:id/search_box"]'), "未成功切换到默认的浏览器页面"

    def is_default_home_page_now(self):
        return self.u2d_helper.xpath_get('//*[@resource-id="com.android.chrome:id/search_box"]')


