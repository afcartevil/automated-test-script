import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_apps.aw_app_aigallery.aw_app_aigallery import AwAppAiGallery


class AwAppAiGalleryVivo(AwAppAiGallery):
    aw_nickname = "VivoGallery"
    variant_key = 'Vivo'
    default_app_package = 'com.vivo.gallery'

    def check_at_homepage(self):
        """
        检查是否在首页
        """
        try:
            self.u2d_helper.click_wait('//*[@content-desc="Photos"]', timeout=4)
            t_log.debug('已在Gallery主页')
            time.sleep(2)
        except Exception:
            raise XPathElementNotFoundError('未在Gallery主页')

    def click_any_photo(self, index=None):
        """
        进入相册后可以选择点击任何一张照片
        """
        con = self.u2d.xpath('//*[contains(@content-desc, "Image")]')
        if index:
            con = con.all()[index]

        self.u2d_helper.click_wait(con, timeout=3)

    def switch_to_albums_page(self):
        """
        切换到相册的页面
        """
        try:
            self.u2d_helper.click_wait('//*[@content-desc="Albums"]')
            time.sleep(2)
        except Exception:
            t_log.error('未找到albums')
            raise Exception('未找到albums')