import time
from tpy_aw.aw_app_base import AwAppBase
from powertrde.utils.u2_extends import u2utils


class AwAppMoj(AwAppBase):
    aw_name = 'Moj'
    default_app_package = 'in.mohalla.video'

    def return_home_page(self):
        for _ in range(10):
            home_page = self.u2d.xpath('//*[@resource-id="in.mohalla.video:id/action_home"]')
            if not home_page.exists:
                self.u2d_helper.press_back_key()
                time.sleep(1)
            else:
                return
        raise Exception('return home page failed')

    def search_user(self, search_name, user_name=None):
        """
        搜索好友名, 搜索的名字（大小写敏感）和用户的名字（可以中文）可能不一样。
        """
        self.return_home_page()
        time.sleep(1)
        self.u2d.xpath('//*[@resource-id="in.mohalla.video:id/action_explore"]')
        time.sleep(1)
        self.u2d.xpath('//*[@text="Search"]').click_exists()
        time.sleep(1)
        u2utils.input_text(self.u2d, search_name)
        self.u2d_helper.click_wait('//*[@text="Search"]', pre_wait=1, timeout=5, post_wait=1)
        time.sleep(5)
        self.u2d_helper.click_wait('//*[@text="Users"]', pre_wait=1, timeout=5, post_wait=1)
        # 大小写敏感
        if user_name:
            self.und_u2.click_match_text(f"{user_name}", limit_area=(0.1, 0.15, 1, 0.8), match_times=5)
        else:
            self.und_u2.click_match_text(f"{search_name}", limit_area=(0.1, 0.15, 1, 0.8), match_times=5)
        time.sleep(1)

    def enter_live_page(self):
        """
        点击任意一个live界面
        """
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

    def enter_user_first_video(self):
        """
        进入用户第一个视频
        """
        self.u2d.click(0.17, 0.49)

        # 进入视频后的断言
        self.u2d_helper.wait_ui_obj('//*[@text="Add comment..." or @content-desc="Like"]', timeout=8, raise_on_not_exist=True)