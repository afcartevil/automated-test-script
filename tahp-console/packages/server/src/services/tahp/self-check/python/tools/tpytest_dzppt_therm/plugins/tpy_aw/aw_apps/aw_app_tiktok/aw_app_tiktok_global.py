from tpy_aw.aw_apps.aw_app_tiktok.aw_app_tiktok import AwAppTiktok
import time

from powertrde.utils.u2_extends import u2utils


class AwAppTiktokGlobal(AwAppTiktok):
    variant_key = 'GO'
    default_app_package = 'com.zhiliaoapp.musically'

    def search_user(self, search_name, user_name=None):
        """
        搜索好友名, 搜索的名字（只能英文/拼音，大小写不敏感）和用户的名字（可以中文）可能不一样。
        """
        self.return_home_page()
        time.sleep(1)
        self.u2d.click(0.93, 0.08)
        time.sleep(1)
        if not self.u2d.xpath('//*[@text="Search"]').exists:
            self.u2d.click(0.93, 0.08)
            time.sleep(1)
        u2utils.input_text(self.u2d, user_name)
        self.u2d_helper.click_wait('//*[@text="Search"]', pre_wait=1, timeout=5, post_wait=1)
        time.sleep(5)
        self.u2d_helper.click_wait('//*[@text="Users"]', pre_wait=1, timeout=5, post_wait=1)
        # 大小写不敏感
        if user_name:
            self.u2d_helper.click_wait(f'//*[@text="{user_name}"]', timeout=5)
        else:
            self.u2d_helper.click_wait(f'//*[translate(@text, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz") = "{user_name.lower()}"]', timeout=5)
        time.sleep(1)


    def enter_live_page(self):
        """
        进入live界面
        """
        self.return_home_page()
        self.u2d_helper.click_wait('//*[@resource-id="com.zhiliaoapp.musically:id/f61"]', pre_wait=1, timeout=5,
                                   post_wait=1)
        time.sleep(1)
        u2utils.input_text(self.u2d, 'live')
        self.u2d_helper.click_wait('//*[@text="Search"]', pre_wait=1, timeout=5, post_wait=1)
        time.sleep(5)
        self.u2d_helper.click_wait('//*[@text="LIVE"]', timeout=4)
        time.sleep(1)
        self.u2d_helper.wait_ui_obj('//*[@text="LIVE"]')
        last_live = self.u2d.xpath('//*[@text="LIVE"]').all()[2]
        last_live.click()
        time.sleep(1)

    def enter_user_first_video(self):
        """
        进入用户第一个视频
        """
        self.u2d.click(0.17, 0.49)

        # 进入视频后的断言
        self.u2d_helper.wait_ui_obj('//*[@text="Add comment..." or @content-desc="Like"]', timeout=8, raise_on_not_exist=True)