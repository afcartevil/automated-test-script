import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_apps.aw_app_aigallery.aw_app_aigallery import AwAppAiGallery


class AwAppAiGalleryVivo(AwAppAiGallery):
    aw_nickname = "OppoGallery"
    variant_key = 'Oppo'
    default_app_package = 'com.coloros.gallery3d'

    def check_at_homepage(self):
        """
        检查是否在首页
        """
        try:
            self.u2d_helper.click_wait('//*[@text="Photos"]', timeout=4)
            t_log.debug('已在Photos主页')
            time.sleep(2)
        except Exception:
            raise XPathElementNotFoundError('未在Photos主页')

    def click_any_photo(self, index=None):
        """
        进入相册后可以选择点击任何一张照片
        """
        con = self.u2d.xpath('(//com.oplus.gallery.business_lib.timeline.view.TimelineView)[2]')
        if index:
            con = con.all()[index]

        self.u2d_helper.click_wait(con, timeout=3)

    def switch_to_albums_page(self):
        """
        切换到相册的页面
        """
        try:
            logo = '//*[@text="Albums"]'
            if self.u2d.xpath(logo).exists:
                self.u2d_helper.click_wait(logo)
            time.sleep(2)
        except Exception:
            t_log.error('未找到albums')
            raise Exception('未找到albums')

