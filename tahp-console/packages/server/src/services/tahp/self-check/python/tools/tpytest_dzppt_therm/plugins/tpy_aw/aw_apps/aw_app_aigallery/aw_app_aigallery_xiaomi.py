# -*- coding: utf-8 -*-
# @Time     : 2025/5/14 15:12
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_chrome.py
import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_apps.aw_app_aigallery.aw_app_aigallery import AwAppAiGallery


class AwAppAiGalleryXiaomi(AwAppAiGallery):
    aw_nickname = "XiaomiGallery"
    variant_key = 'Xiaomi'
    default_app_package = 'com.miui.gallery'

    def check_at_homepage(self):
        """
        检查是否在首页
        """
        try:
            self.u2d_helper.click_wait('//*[@resource-id="com.miui.gallery:id/home_page"]', timeout=4)
            t_log.debug('已在Gallery主页')
            time.sleep(2)
        except Exception:
            raise XPathElementNotFoundError('未在Gallery主页')

    def return_home_page(self):
        """
        回到主页
        """
        for i in range(6):
            time.sleep(2)
            if not self.u2d.xpath('//*[@resource-id="com.miui.gallery:id/home_page"]').exists:
                self.u2d_helper.press_back_key()
            else:
                self.u2d_helper.click_wait('//*[@resource-id="com.miui.gallery:id/home_page"]')
                break
        else:
            raise Exception('点击5次都没回到首页')

    def switch_to_albums_page(self):
        """
        切换到相册的页面
        """
        try:
            self.u2d.xpath('//*[@resource-id="com.miui.gallery:id/album_page"]').click(timeout=4)
            time.sleep(2)
        except Exception:
            t_log.error('未找到albums')
            raise Exception('未找到albums')

    def switch_to_home_page(self):
        """
        进入相册的主页
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.miui.gallery:id/home_page"]', timeout=5, post_wait=1)

    def enter_all_photos(self):
        """
        进入默认相册 All Photos
        """
        try:
            self.u2d_helper.click_wait('//*[@text="All Photos"]', timeout=4)
            time.sleep(2)
        except Exception:
            t_log.error('未找到albums')
            raise Exception('未找到albums')

    def enter_special_album(self, album_name):
        """
        进入特定的相册
        """
        self.u2d_helper.click_wait('//*[@text="Albums"]', pre_wait=1, timeout=5, post_wait=1)
        for i in range(3):
            special_album = self.u2d.xpath(f'//*[@text="{album_name}"]')
            # 避免在偏下的位置影响相册
            if special_album.exists:
                b = special_album.get().info['bounds']
                h = self.u2d.window_size()[1]
                if ((b['top'] + b['bottom']) / 2) / h <= 0.8:
                    special_album.click()
                    return
            self.und_u2.swipe_direction('up')
            time.sleep(1)

        t_log.error(f'未找到{album_name}')
        raise Exception(f'未找到{album_name}')

    def click_search_tab(self):
        """
        点击搜索tab
        """
        ...

    def click_any_photo(self, index=None):
        """
        进入相册后可以选择点击任何一张照片
        """
        con = self.u2d.xpath('//*[contains(@content-desc, "Photo,")]')
        if index:
            con = con.all()[index]

        self.u2d_helper.click_wait(con, timeout=3)