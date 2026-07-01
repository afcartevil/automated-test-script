import time

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase


class AwAppDANA(AwAppBase):
    aw_name = 'DANA'
    default_app_package = 'id.dana'

    def check_at_homepage(self):
        assert self.u2d.xpath('//*[@resource-id="id.dana:id/btn_home_tab_pay"]').exists

    def click_pay(self):
        self.u2d_helper.click_wait('//*[@resource-id="id.dana:id/btn_home_tab_pay"]', timeout=10, post_wait=1)

