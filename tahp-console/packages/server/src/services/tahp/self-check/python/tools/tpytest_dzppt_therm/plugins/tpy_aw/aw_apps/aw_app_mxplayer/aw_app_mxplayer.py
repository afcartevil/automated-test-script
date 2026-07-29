import time
import random

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from tpy_aw.aw_app_base import AwAppBase


class AwAppMXPlayer(AwAppBase):
    aw_name = 'MXPlayer'
    default_app_package = 'com.mxtech.videoplayer.ad'

    def check_mxplayer_at_homepage(self):
        if self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.mxtech.videoplayer.ad:id/local_tab"]', click=True):
            t_log.info('已在mxplayer主页')
            return True
        else:
            t_log.warning('已在mxplayer主页')
            return False

    def music_play(self):
        icon_exist,ele = self.u2d_helper.assert_icon_exist('xpath',
                                                       '//*[@resource-id="com.mxtech.videoplayer.ad:id/storage_permission_accept"]')
        if icon_exist:
            t_log.info('点击ALLOW ACCESS')
            ele.click()
            time.sleep(2)
            self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.android.settings:id/switchWidget"]',
                                              click=True)
            self.u2d_helper.press_back_key()
        exist,ele = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.mxtech.videoplayer.ad:id/music_tab"]')
        if exist:
            ele.click()
            self.u2d_helper.assert_icon_exist('xpath','//*[@resource-id="com.mxtech.videoplayer.ad:id/cover_image"]',click=True)

    def enter_video_folder(self, video_foder_name):
        """
        查找视频文件夹
        """
        video_folder = self.u2d.xpath(f'//*[@text="{video_foder_name}"]').wait(timeout=2)
        if video_folder:
            self.u2d.xpath(f'//*[@text="{video_foder_name}"]').click()
        else:
            raise XPathElementNotFoundError(f'未找到视频文件夹{video_foder_name}')

    def play_video(self):
        """
        播放视频（已进入视频文件夹）
        """
        self.u2d.xpath('//*[@resource-id="com.mxtech.videoplayer.ad:id/duration"]').click()