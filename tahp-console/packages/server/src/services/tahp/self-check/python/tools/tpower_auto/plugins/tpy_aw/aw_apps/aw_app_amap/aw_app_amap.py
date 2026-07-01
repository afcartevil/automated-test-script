import time
import random
from deprecated import deprecated
from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_app_base import AwAppBase


class AwAppAMAP(AwAppBase):
    aw_name = 'AMAP'
    default_app_package = 'com.autonavi.minimap'

    def check_at_amap(self):
        """
        检查是否在首页
        """
        assert self.u2d.xpath('//*[@resource-id="com.autonavi.minimap:id/route_line_icon"]').exists
        t_log.debug('已在高德地图主页')

    def navigation(self):
        t_log.debug('点击路线')
        self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.autonavi.minimap:id/route_line_icon"]',click=True)
        time.sleep(5)
        route_edit=self.u2d.xpath('//*[@resource-id="com.autonavi.minimap:id/route_edit_end_text"]')
        if route_edit:
            route_edit.click()
            time.sleep(1)
            t_log.debug("输入搜索内容")
            u2utils.input_text(self.u2d, 'shenzhen')
            time.sleep(5)
            t_log.debug("点击目的地搜索")
            self.u2d_helper.click_wait('//*[@text="深圳市"]', wait_after_click=2)
            t_log.debug("点击开始导航")
            self.u2d_helper.click_wait('//android.view.View[@text="开始导航"]',timeout=15,wait_after_click=5)
        else:
            t_log.debug('点击路线失败')

    def click_home_tab(self):
        """
        点击首页tab
        """
        self.u2d.xpath('//*[@text="首页"]').click()
        time.sleep(2)

    def click_message_tab(self):
        """
        点击消息tab
        """
        self.u2d.xpath('//*[@text="消息"]').click(timeout=1)
        time.sleep(2)

    def click_me_tab(self):
        """
        点击我的tab
        """
        self.u2d.xpath('//*[@text="我的"]').click()
        time.sleep(2)
