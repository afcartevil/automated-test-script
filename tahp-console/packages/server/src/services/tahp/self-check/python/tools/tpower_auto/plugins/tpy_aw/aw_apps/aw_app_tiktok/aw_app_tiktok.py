import time
from tpy_aw.aw_app_base import AwAppBase
from powertrde.utils.u2_extends import u2utils


class AwAppTiktok(AwAppBase):
    aw_name = 'TikTok'
    default_app_package = 'com.ss.android.ugc.trill'

    def return_home_page(self):
        for _ in range(10):
            home_page = self.u2d.xpath('//*[@text="Home"]')
            if not home_page.exists:
                self.u2d_helper.press_back_key()
                time.sleep(1)
            else:
                return
        raise Exception('return home page failed')

    def search_friend(self):
        self.return_home_page()
        time.sleep(1)
        self.u2d.click(0.93, 0.08)
        time.sleep(1)
        if not self.u2d.xpath('//*[@text="Search"]').exists:
            self.u2d.click(0.93, 0.08)
            time.sleep(1)
        u2utils.input_text(self.u2d, "chuanguiyuan")
        self.u2d_helper.click_wait('//*[@text="Search"]', pre_wait=1, timeout=5, post_wait=1)
        time.sleep(5)
        self.u2d_helper.click_wait('//*[@text="Users"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.assert_icon_exist('xpath', '//*[@text="Chuanguiyuan"]', click=True)
        time.sleep(1)

    def enter_live_page(self):
        self.return_home_page()
        time.sleep(1)
        self.u2d.click(0.93, 0.08)
        time.sleep(1)
        if not self.u2d.xpath('//*[@text="Search"]').exists:
            self.u2d.click(0.93, 0.08)
            time.sleep(1)
        u2utils.input_text(self.u2d, 'live')
        self.u2d_helper.click_wait('//*[@text="Search"]', pre_wait=1, timeout=5, post_wait=1)
        time.sleep(3)
        self.u2d_helper.click_wait('//*[@text="LIVE"]', pre_wait=1, timeout=5, post_wait=1)
        time.sleep(3)
        self.u2d_helper.wait_ui_obj('//*[@text="LIVE"]')
        last_live = self.u2d.xpath('//*[@text="LIVE"]').all()[2]
        last_live.click()
        time.sleep(1)
