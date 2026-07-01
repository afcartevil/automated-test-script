from tpy_aw.aw_apps.aw_app_tiktok.aw_app_tiktok import AwAppTiktok
import time

from powertrde.utils.u2_extends import u2utils


class AwAppTiktokGlobal(AwAppTiktok):
    variant_key = 'GO'
    default_app_package = 'com.zhiliaoapp.musically'

    def search_friend(self):
        self.return_home_page()
        self.u2d_helper.click_wait('//*[@resource-id="com.zhiliaoapp.musically:id/f61"]', pre_wait=1, timeout=5,
                                   post_wait=1)  # com.zhiliaoapp.musically搜索控件
        time.sleep(1)
        u2utils.input_text(self.u2d, 'chuanguiyuan')
        self.u2d_helper.click_wait('//*[@text="Search"]', pre_wait=1, timeout=5, post_wait=1)
        time.sleep(5)
        self.u2d_helper.click_wait('//*[@text="Users"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.assert_icon_exist('xpath', '//*[@text="Chuanguiyuan"]', click=True)
        time.sleep(1)

    def enter_live_page(self):
        self.return_home_page()
        self.u2d_helper.click_wait('//*[@resource-id="com.zhiliaoapp.musically:id/f61"]', pre_wait=1, timeout=5,
                                   post_wait=1)
        time.sleep(1)
        u2utils.input_text(self.u2d, 'live')
        self.u2d_helper.click_wait('//*[@text="Search"]', pre_wait=1, timeout=5, post_wait=1)
        time.sleep(5)
        self.u2d_helper.assert_icon_exist('xpath', '//*[@text="LIVE"]', click=True)
        time.sleep(1)
        self.u2d_helper.wait_ui_obj('//*[@text="LIVE"]')
        last_live = self.u2d.xpath('//*[@text="LIVE"]').all()[2]
        last_live.click()
        time.sleep(1)
