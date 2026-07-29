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


class GoogleMapsLocator(U2SelectorLocator):
    btn_search = U2Selector().xpath('//*[@resource-id="com.google.android.apps.maps:id/search_omnibox_text_box"]').bind()
    btn_close = U2Selector().xpath('//*[@content-desc="Close navigation"]').bind()

class AwAppGoogleMaps(AwAppBase, GoogleMapsLocator):
    aw_name = 'GoogleMaps'
    default_app_package = 'com.google.android.apps.maps'

    def check_at_homepage(self):
        """
        检测是否在主页
        """
        result, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.google.android.apps.maps:id/explore_tab_strip_button"]', click=True)
        if result:
            t_log.info('已在GoogleMaps主页')
        else:
            raise XPathElementNotFoundError('未在GoogleMaps主页')
        time.sleep(2)

    def search_location(self, location):
        """
        只搜索地点，不点击
        """
        self.u2d_helper.click_wait('//*[@text="Search here" or @resource-id="com.google.android.apps.maps:id/search_omnibox_text_box"]', timeout=4)
        time.sleep(2)
        # self.u2d.send_keys(location)
        u2utils.input_text(self.u2d, location)
        time.sleep(1)
        adb.exec_cmd(self.device_id, 'input keyevent 66')
        time.sleep(1)

    def click_directions(self):
        """
        点击导航, 前提是已经到一个具体的地点
        """
        self.u2d_helper.click_wait('//*[@text="Directions" or contains(@content-desc, "Directions")]', timeout=10, post_wait=1)
        time.sleep(2)
        if self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.google.android.gms:id/messages"]')[0]:
            t_log.info('点击权限弹框')
            self.u2d_helper.assert_icon_exist('xpath', '//*[@text="Turn on"]', click=True)
        if self.u2d_helper.assert_icon_exist('xpath', '//*[@text="Choose start location"]',click=True)[0]:
            t_log.info('点击选择起点')
            time.sleep(2)
            self.u2d_helper.assert_icon_exist('xpath', '//*[@text="Your location"]', click=True)
        time.sleep(5)
        t_log.info('点击开始导航')
        start_icon = self.u2d(text="Start")
        if start_icon.wait(timeout=15):
            start_icon.click()
        else:
            raise Exception('未找到开始导航Start按钮！')
        time.sleep(5)
        if self.u2d_helper.assert_icon_exist('xpath', '//*[@text="Got it"]',click=True)[0]:
            t_log.info('点击got it弹窗')
        if self.u2d_helper.assert_icon_exist('xpath', '//*[@text="Dismiss"]',click=True)[0]:
            t_log.info('点击diss弹窗')

    def exit_navigation(self):
        """
        退出导航
        """
        self.btn_close.click_wait(timeout=8, wait_after_click=1)

    def pull_grippy(self):
        """
        把探索栏拉出来
        """
        bar_result, bar = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.google.android.apps.maps:id/grippy"]', click=False)
        if bar_result:
            x = (bar.info['bounds']['left'] + bar.info['bounds']['right']) / 2
            y = (bar.info['bounds']['top'] + bar.info['bounds']['bottom']) / 2
            self.u2d.swipe(x, y, x, 200)
            time.sleep(1)
        else:
            t_log.error('未找到探索栏')
            raise Exception('未找到探索栏')

    def click_contribute_tab(self):
        """
        点击贡献tab
        """
        self.u2d.xpath('//*[@text="Contribute"]').click()
        time.sleep(2)

    def click_explore_tab(self):
        """
        点击探索tab
        """
        self.u2d.xpath('//*[@text="Explore"]').click()
        time.sleep(2)

    def check_if_in_navigation(self):
        t_log.info('点击开始导航')
        start_icon = self.u2d(text="Start")
        head_east_icon = self.u2d(descriptionContains="Head east")
        if start_icon.wait(timeout=15):
            start_icon.click()
            return True
        elif head_east_icon.wait(timeout=5):
            return True
        else:
            return False

    def click_explore(self):
        """
        maps首页第一个explore
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.google.android.apps.maps:id/navigation_bar_item_large_label_view"]', timeout=10)

    def swipe_the_window(self):
        """
        将maps半屏显示的往上拉
        """
        self.u2d.swipe(0.5, 0.85, 0.5, 0.3)

    def set_work(self, work_place_name):
        """
        设置工作地， 有两种设置的情况。支持模糊匹配，大小写不敏感
        """
        work_place_name = work_place_name.lower()
        if not self.u2d.xpath('//*[@content-desc="Explore"]').exists:
            self.u2d_helper.press_back_key()
        save_page = self.u2d.xpath('//android.widget.TextView[@text="You"]')
        if not save_page.exists:
            save_page = self.u2d.xpath('//android.widget.TextView[@text="Saved"]')
        save_page.click()
        time.sleep(2)

        set_work = self.u2d.xpath('//android.widget.TextView[@text="Set work"]')
        if set_work.exists:
            set_work.click()
            time.sleep(1)
            u2utils.input_text(self.u2d, work_place_name)
            time.sleep(2)
            adb.exec_cmd(self.device_id, 'input keyevent 66')
            time.sleep(2)
            # 模糊匹配
            self.u2d_helper.click_wait(self.u2d.xpath(f'//*[contains(translate(@text, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "{work_place_name}")]').all()[1], timeout=8, post_wait=1)
        # 情况1结束

        self.u2d.xpath('//*[@text="No thanks"]').click_exists()
        self.u2d_helper.click_wait('//android.widget.TextView[@text="Explore"]', timeout=10, post_wait=1)
        time.sleep(2)

        self.btn_search.click_wait()
        time.sleep(1)

        # 设置工作地情况2
        set_location = self.u2d.xpath('//android.widget.TextView[@text="Set location"]')
        if set_location.exists:
            if len(set_location.all()) > 1:
                set_location.all()[1].click()
                time.sleep(2)
                u2utils.input_text(self.u2d, work_place_name)
                time.sleep(2)
                adb.exec_cmd(self.device_id, 'input keyevent 66')
                time.sleep(2)
                self.u2d_helper.click_wait(self.u2d.xpath(
                    f'//*[contains(translate(@text, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"), "{work_place_name}")]').all()[
                                               1], timeout=8, post_wait=1)
        # 情况2结束
