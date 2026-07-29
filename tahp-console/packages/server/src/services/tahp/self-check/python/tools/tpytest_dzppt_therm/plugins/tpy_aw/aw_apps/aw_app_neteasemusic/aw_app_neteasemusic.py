import time
import random

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from tpy_aw.aw_app_base import AwAppBase


class AwAppNeteasemusic(AwAppBase):
    aw_name = 'NetEaseMusic'
    default_app_package = 'com.netease.cloudmusic'

    def check_at_homepage(self):
        if self.und_u2.match_text('推荐', limit_area=(0, 0.85, 0.3, 1), target_score=0.85):
            t_log.info('已在NetEaseMusic主页')
            return True
        else:
            t_log.warning('不在NetEaseMusic主页')
            return False

    def back_homepage(self, press_back_time=0):
        if not self.check_at_homepage():
            if press_back_time > 2:
                t_log.info("点击back键超过2次，重启NetEaseMusic")
                self.restart_app()
                return
            t_log.info('不在主页,点击back键')
            self.u2d_helper.press_back_key(times=1)
            time.sleep(2)
            press_back_time += 1
            t_log.info('back次数{}'.format(press_back_time))
            self.back_homepage(press_back_time)
        else:
            t_log.info('在NetEaseMusic主页')

    def play_music_at_homepage(self):
        ...

