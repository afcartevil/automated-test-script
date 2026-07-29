import time

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase

class AwAppVishaVideoPlayer(AwAppBase):
    aw_name = 'VishaVideoPlayer'
    default_app_package = 'com.transsion.magicshow'

    def first_direction(self):
        """
        第一次使用可能会有新手引导
        """
        self.u2d.xpath('//*[@text="Agree"]').click_exists(timeout=3)
        self.u2d.xpath('//*[@text="Skip"]').click_exists(timeout=5)

    def change_single_cycle(self):
        """
        单曲循环
        """

        if not self.u2d.xpath('//*[@resource-id="com.transsion.magicshow:id/iv_video_play_setting"]').exists:
            self.u2d.click(0.5, 0.5)
            time.sleep(1)
        self.u2d.xpath('//*[@resource-id="com.transsion.magicshow:id/iv_video_play_setting"]').click()
        # 默认是第三个单曲循环
        self.u2d_helper.click_wait('(//*[@resource-id="com.transsion.magicshow:id/fl_bg"])[3]', timeout=3, post_wait=1.5)