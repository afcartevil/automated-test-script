import time

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase


class AwAppGrab(AwAppBase):
    aw_name = 'Grab'
    default_app_package = 'com.grabtaxi.passenger'

    def check_at_home_page(self):
        assert self.u2d.xpath('//*[@resource-id="com.grabtaxi.passenger:id/bar_item_discover"]').exists

    def change_to_food_page(self):
        self.u2d_helper.click_wait('//*[@text="Food" or @content-desc="Food, double tap to select"]', timeout=10, post_wait=1)