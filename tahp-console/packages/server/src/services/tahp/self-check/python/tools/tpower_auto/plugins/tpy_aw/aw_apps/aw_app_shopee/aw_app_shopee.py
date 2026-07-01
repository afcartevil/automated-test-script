import time

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase


class AwAppShopee(AwAppBase):
    aw_name = 'Shopee'
    default_app_package = 'com.shopee.sg'

    def check_at_home_page(self):
        assert self.u2d.xpath('//*[@content-desc="tab_bar_button_home"]').exists

    def click_commodity(self):
        # 因为点前三个很有可能点到顶部的搜索框
        self.u2d.xpath('(//*[@resource-id="com.shopee.sg:id/TANGRAM_VIEW_CONTAINER_ID"])[4]').click()