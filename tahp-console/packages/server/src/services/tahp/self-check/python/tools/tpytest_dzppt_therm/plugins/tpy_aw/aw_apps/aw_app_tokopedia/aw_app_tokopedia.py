import time

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase


class AwAppTokopedia(AwAppBase):
    aw_name = 'Tokopedia'
    default_app_package = 'com.tokopedia.tkpd'

    def check_at_homepage(self):
        assert self.u2d.xpath('//*[@resource-id="com.tokopedia.tkpd:id/iv_icon"]').exists

    def click_commodity(self):
        self.u2d.xpath('//*[@resource-id="com.tokopedia.tkpd:id/productCardCardUnifyContainer"]').click()