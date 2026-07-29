# -*- coding: utf-8 -*-
from deprecated import deprecated

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase

import time
class YoutubeLocator(U2SelectorLocator):
    search_btn = U2Selector().xpath('//*[@resource-id="com.google.android.youtube:id/menu_item_1"]').bind()
    home_btn = U2Selector().xpath('//*[@content-desc="Home"]').bind()

class AwAppYoutube(YoutubeLocator, AwAppBase):
    aw_name = 'Youtube'
    default_app_package = 'com.google.android.youtube'

    def check_at_homepage(self):
        self.u2d.xpath('//*[@content-desc="Dismiss"]').click_exists()
        self.u2d.swipe(0.5, 0.3, 0.5, 0.7)
        time.sleep(1)
        result, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.google.android.youtube:id/pivot_bar"]/android.widget.LinearLayout[1]/android.widget.Button[1]', click=True)
        if result:
            t_log.debug('已在Youtube主页')
        else:
            raise Exception('未在Youtube主页')
        time.sleep(2)

    def check_yt_at_homepage2(self):
        exist,_ = self.u2d_helper.assert_icon_exist('xpath',
                                                  '//*[@resource-id="com.google.android.youtube:id/youtube_logo"]',
                                                  click=False)
        if exist:
            t_log.info('已在Youtube主页')
            return True
        else:
            return False

    def auto_login(self):
        ...
        # 切换登录账号 google登陆会吞字，暂时未解决
        # self.u2d.xpath('//*[@content-desc="Settings"]').click()
        # self.u2d_helper.click_wait('//*[@text="Switch account"]', timeout=5, post_wait=1)
        # time.sleep(3)
        # if self.u2d.xpath(f'//*[@text="{self.youtube_email}"]').exists:
        #     self.u2d.xpath('//*[@text="Manage accounts"]').click()
        #     self.u2d.swipe(0.5, 0.8, 0.5, 0.2)
        #     self.u2d.xpath(f'//*[@text="{self.youtube_email}"]').click()
        #     self.u2d_helper.click_wait('//*[@text="Remove account"]', pre_wait=1, timeout=10, post_wait=1)
        #     self.u2d_helper.click_wait('//*[@text="Remove account"]', pre_wait=1, timeout=10, post_wait=1)
        #     time.sleep(1)
        #     self.und_u2.click_back(1)
        #     self.u2d.xpath('//*[@text="Switch account"]').click_exists(timeout=5)
        # self.u2d_helper.click_wait('//*[@content-desc="Add account"]', timeout=15, post_wait=1)
        # self.u2d_helper.click_wait('//android.widget.EditText', pre_wait=2, timeout=60, post_wait=3)
        # time.sleep(2)
        # for ii in self.youtube_email:
        #     time.sleep(0.2)
        #     self.u2d.send_keys(ii)
        # self.u2d_helper.restore_keyboard_ime()
        # time.sleep(2)
        # self.u2d.xpath('//*[@text="Next"]').click()
        # self.u2d_helper.click_wait('//android.widget.EditText', pre_wait=2, timeout=60, post_wait=3)
        # time.sleep(2)
        # for ii in self.youtube_password:
        #     time.sleep(0.2)
        #     self.u2d.send_keys(ii)
        # self.u2d_helper.restore_keyboard_ime()
        # time.sleep(2)
        # self.u2d.xpath('//*[@text="Next"]').click()
        # time.sleep(10)
        # self.u2d.xpath('//*[@text="I agree"]').click_exists()
        # # 重新检查
        # time.sleep(15)
        # self.u2d_helper.restart_app(app_info.package)
        # self.u2d_helper.click_wait('//*[@text="You"]', timeout=60, post_wait=2)
        # time.sleep(2)
        # self.u2d.swipe(0.20, 0.75, 0.20, 0.25, 0.2)
        # time.sleep(1)

    def back_homepage(self, press_back_time=0):
        """
        通过按back键返回主页，最多返回2次仍不在主页则重启App
        """
        if not self.check_yt_at_homepage2():
           if press_back_time > 2:
               t_log.info("点击back键超过2次，重启Youtube")
               self.restart_app()
               return
           t_log.info('不在主页,点击back键')
           self.u2d_helper.press_back_key(times=1)
           press_back_time += 1
           t_log.info('back次数{}'.format(press_back_time))
           self.back_homepage(press_back_time)
        else:
           t_log.info('在Youtube主页')

    def change_to_shorts(self):
        """
        切换到短视频界面
        """
        self.u2d_helper.click_wait('//*[@text="Shorts"]', timeout=5)

    def check_youtube_member(self):
        """
        检查是不是Youtube会员
        """
        time.sleep(8)
        self.u2d_helper.click_wait('//*[@text="You"]')
        time.sleep(5)
        self.u2d_helper.wait_ui_obj('//*[@text="Your videos"]', timeout=7)
        self.u2d.swipe(0.20, 0.75, 0.20, 0.25, 0.2)
        time.sleep(3)
        try:
            is_member = self.u2d_helper.wait_ui_obj('//*[@text="Your Premium benefits" or @text="Premium benefits"]', timeout=6, raise_on_not_exist=True)
            if is_member:
                self.u2d(description = "Settings").click_exists(timeout=3)
                time.sleep(3)
                self.u2d(resourceId = 'com.google.android.youtube:id/recycler_view').scroll.to(text = "Background & downloads")
                time.sleep(3)
                self.u2d(text = "Background & downloads").click_exists(timeout=3)
                time.sleep(3)
                self.u2d(text = "Playback").click_exists(timeout=3)
                time.sleep(2)
                element = self.u2d(text = "Off")
                if not element.info.get('checked'):
                    element.click_exists(timeout=3)
                time.sleep(3)
                self.u2d(text = "CANCEL").click_exists(timeout=3)
        except Exception:
            t_log.info('Not Youtube member(不是Youtube会员)')
            raise Exception('Not Youtube member(不是Youtube会员)')

    def brush_yt_video(self):
        #先刷新视频再滑动播放
        self.u2d.swipe(0.2, 0.5, 0.2, 0.8,0.2)
        time.sleep(2)
        self.u2d.swipe(0.2,0.8,0.2,0.1,0.2)
        time.sleep(1)
        self.u2d.swipe(0.2,0.8,0.2,0.1,0.2)
        time.sleep(5)
        if self.is_ad():
            t_log.info('发现广告，继续滑动')
            self.u2d.swipe(0.2, 0.8, 0.2, 0.1, 0.2)
            time.sleep(1)
            self.u2d.swipe(0.2, 0.8, 0.2, 0.1, 0.2)
        time.sleep(2)
        if self.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/subtitle"]').wait(timeout=5):
            t_log.info('横屏播放视频')
            self.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/subtitle"]').click()
        elif self.u2d(descriptionContains='More actions').exists:
            t_log.info('播放短视频')
            self.u2d.xpath("//*[contains(@content-desc,'More actions')]/../..").click()
        elif self.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/floaty_bar_controls_view"]').exists:
            t_log.info('播放视频中播放其他视频15s')
            self.u2d_helper.click_wait('//*[@resource-id="com.google.android.youtube:id/results"]',pre_wait=3)
        elif self.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/results"]').exists:
            t_log.info('播放视频')
            self.u2d_helper.click_wait('//*[@resource-id="com.google.android.youtube:id/results"]', pre_wait=3)
        else:
            raise Exception("没有找到可播放的视频")

    def play_yt_vedio(self):
        time.sleep(5)
        if self.u2d(resourceId="com.google.android.youtube:id/elements_button_bar_container").exists:
            t_log.info('播放视频15s')
            time.sleep(15)
            return True
        elif self.u2d(descriptionContains='Download').exists:
            t_log.info('播放视频15s')
            time.sleep(15)
            return True
        elif self.u2d(descriptionContains='Share').exists:
            t_log.info('播放视频15s')
            time.sleep(15)
            return True
        else:
            t_log.info('没有找到可以播放的视频，返回主页')
            self.back_homepage()
            return False

    def close_small_window(self):
        """
        关闭小窗
        """
        small_window = self.u2d.xpath('//*[@resource-id="com.google.android.youtube:id'
                                               '/modern_miniplayer_close" or '
                                               '@resource-id="com.google.android.youtube:id/floaty_close_button"]')
        if small_window.exists:
            small_window.click()
            time.sleep(1)
            time.sleep(1)

    def clear_history(self):
        """
        清除youtube视频历史
        """
        self.u2d.xpath('//android.widget.TextView[@text="You"]').click()
        time.sleep(3)
        if self.u2d.xpath('//*[@content-desc="History"]/child::*[1]').wait(timeout=2):
            self.u2d.xpath('//*[@content-desc="History"]/child::*[1]').click()
            time.sleep(2)
            self.u2d.xpath('//*[@content-desc="More options"]').click()
            time.sleep(0.5)
            self.u2d.xpath('//*[@text="Clear all watch history"]').click()
            time.sleep(1.5)
            self.u2d.xpath('//*[@text="Clear watch history"]').click()
            time.sleep(8)

    def search_video(self, video_name, no_watch=False):
        """
        搜索Youtube视频
        @param no_watch: 可以选择不进入视频，选择自己的方式
        """
        t_log.info('关闭小窗')
        self.close_small_window()

        t_log.info('点击搜索')
        self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.google.android.youtube:id/menu_item_1"]',
                                          click=True)
        time.sleep(2)
        search = self.u2d.xpath('//android.widget.EditText')
        if not search.wait(timeout=5):
            raise Exception("搜索框未找到")

        search.click(timeout=5)
        time.sleep(2)
        u2utils.input_text(self.u2d, video_name)
        time.sleep(2)

        adb.exec_cmd(self.device_id, 'input keyevent 66')

        time.sleep(2)
        if not no_watch:
            for attempt in range(4):
                video = self.u2d.xpath(
                    "//*[contains(@content-desc, 'play video') and not(contains(@content-desc, 'Sponsored'))]")
                if video.exists:
                    t_log.info('播放视频')
                    video.click()
                    time.sleep(5)
                    return

                self.u2d.swipe(0.5, 0.8, 0.5, 0.2)
                time.sleep(1)  # 等待页面加载

            raise Exception("没有找到播放视频的控件")

    @deprecated
    def search_yt_video(self):
        t_log.info('点击搜索')
        search_exist,element = self.u2d_helper.assert_icon_exist('xpath',
                                                  '//*[@resource-id="com.google.android.youtube:id/modern_miniplayer_close"]')
        if search_exist:
            element.click()
            time.sleep(2)
        self.u2d_helper.assert_icon_exist('xpath','//*[@resource-id="com.google.android.youtube:id/menu_item_1"]',click=True)
        time.sleep(2)
        t_log.info('点击编辑框')
        search = self.u2d.xpath('//android.widget.EditText')
        if search.wait(timeout=5):
            search.click(timeout=5)
            time.sleep(2)
            u2utils.input_text(self.u2d, 'Oppenheimer')
        self.u2d.sleep(2)
        t_log.info('点击搜索')
        self.u2d_helper.assert_icon_exist('xpath','//*[@resource-id="com.google.android.youtube:id/search_type_icon"]',click=True)
        time.sleep(2)
        self.u2d.swipe(0.2, 0.8, 0.2, 0.5, 0.1)
        time.sleep(2)
        self.u2d.swipe(0.2, 0.8, 0.2, 0.5, 0.1)
        if self.is_ad():
            t_log.info('发现广告，继续滑动')
            self.u2d.swipe(0.2, 0.8, 0.2, 0.1, 0.2)
            time.sleep(1)
            self.u2d.swipe(0.2, 0.8, 0.2, 0.1, 0.2)
        time.sleep(2)
        if self.u2d(resourceId='com.google.android.youtube:id/subtitle').wait(timeout=5):
            t_log.info('播放视频1')
            self.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/subtitle"]').click()
            time.sleep(5)
        elif self.u2d(resourceId='com.google.android.youtube:id/results').wait(timeout=5):
            t_log.info('播放视频2')
            self.u2d_helper.click_wait('//*[@resource-id="com.google.android.youtube:id/results"]')
            time.sleep(5)
        else:
            raise Exception("没有找到播放视频的控件")

    def view_yt_comments(self):
        if self.u2d(resourceId="com.google.android.youtube:id/elements_button_bar_container").exists:
            t_log.info('播放竖屏视频，点击评论按钮')
            self.u2d.xpath('//*[@resource-id="com.google.android.youtube:id/elements_button_bar_container"]').click()
            time.sleep(2)
            comment_area_exist,_ = self.u2d_helper.assert_icon_exist('xpath',
                                                      '//*[@resource-id="com.google.android.youtube:id/app_engagement_panel"]',
                                                      click=False)
            if comment_area_exist:
                t_log.info('滑动评论区域')
                self.u2d.swipe(0.5, 0.8, 0.5, 0.5, 0.1)
                time.sleep(2)
            else:
                raise Exception('未能找到评论区域')
        else:
            try:
                self.u2d_helper.und_u2.click_match_text('Comments', match_times=3, limit_area=(0, 0.2, 0.5, 0.8))
                time.sleep(3)
                comment_area_exist2,_ = self.u2d_helper.assert_icon_exist('xpath',
                                                          '//*[@resource-id="com.google.android.youtube:id/engagement_panel"]',
                                                          click=False)
                if comment_area_exist2:
                    t_log.info('滑动评论区域')
                    self.u2d.swipe(0.5, 0.8, 0.5, 0.5, 0.1)
                    time.sleep(2)
                else:
                    t_log.error('没有找到评论区域')
            except Exception:
                t_log.error('点击Comments失败,点击back')
                self.u2d_helper.press_back_key(times=1)

    def is_ad(self):
        if self.u2d(descriptionContains="Learn more").exists:
            return True
        elif self.u2d(descriptionContains="Visit site").exists:
            return True
        elif self.u2d(descriptionContains="Open app").exists:
            return True
        elif self.u2d(descriptionContains="Install").exists:
            return True
        elif self.u2d(descriptionContains="Start now").exists:
            return True
        elif self.u2d(descriptionContains="Sign up").exists:
            return True
        elif self.u2d(descriptionContains="Watch").exists:
            return True
        elif self.u2d(descriptionContains="Shop now").exists:
            return True
        else:
            return False

    def click_a_video(self, swipe_times=5):
        """
        点击视频
        """
        for _ in range(swipe_times):
            video_title = self.u2d.xpath('//*[contains(@content-desc, "watching") or (contains(@content-desc, "ago")) or (contains(@text, "ago")) or (contains(@text, "watching"))]').wait(timeout=2)
            if video_title:
                self.u2d.xpath('//*[(contains(@content-desc, "watching") or (contains(@content-desc, "ago")) or (contains(@text, "ago")) or (contains(@text, "watching"))) and not (contains(@text, "Live"))]').click()
                time.sleep(2)
                break
            else:
                self.und_u2.swipe_direction('up', speed=200)
                time.sleep(2)

    def start_any_video_at_homepage(self):
        """
        主页查看任意一个视频
        """
        self.check_at_homepage()

        for i in range(5):
            if self.is_ad():
                t_log.info('发现广告，继续滑动')
                self.u2d.swipe(0.2, 0.8, 0.2, 0.1, 0.2)
                time.sleep(2)
            else:
                break
        self.u2d.click(0.5, 0.5)

    def fullscreen_video(self):
        """
        观看全屏视频，前提是已经到视频小窗界面
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.google.android.youtube:id/player_view"]/android.view.ViewGroup[1]')
        self.u2d_helper.click_wait('//*[@resource-id="com.google.android.youtube:id/fullscreen_button"]')
        time.sleep(1)

    def set_video_quaility(self, quality_selection, specific=None):
        """
        设置视频播放的画质，前提是已经到视频界面, 且为竖屏模式
        @param quality_selection: 'Auto', 'Higher picture quaility', 'Data saver', 'Advanced'
        @param specific: Advanced需要填  '1080p', '720p', '480p', '360p', '240p', '144p'
        """
        assert quality_selection in ('Auto', 'Higher picture quaility', 'Data saver', 'Advanced')
        self.u2d.click(0.50, 0.20)
        self.u2d_helper.click_wait('//*[@resource-id="com.google.android.youtube:id/player_overflow_button"]')
        self.und_u2.click_match_text('Quaility', limit_area=(0, 0.6, 0.5, 1), match_times=6)
        time.sleep(1)

        self.und_u2.click_match_text(quality_selection, limit_area=(0, 0.6, 0.5, 1), match_times=6)
        time.sleep(1)
        if quality_selection == 'Advanced':
            assert specific in ('1080p', '720p', '480p', '360p', '240p', '144p')
            try:
                self.und_u2.click_match_text(specific, limit_area=(0, 0.5, 0.5, 1), target_score=0.70, match_times=6)
            except:
                self.und_u2.click_match_text(specific, target_score=0.70, match_times=6)
        time.sleep(1)

    def close_video_ad(self):
        """
        关闭视频广告，后续改进
        """
        # 广告可能要看几秒才可以skip
        time.sleep(10)
        if self.u2d.xpath('//*[@content-desc="Close ad panel" or @text="Skip"]').exists:
            self.u2d.xpath('//*[@content-desc="Close ad panel" or @text="Skip"]').click()
            self.u2d.xpath('//*[@content-desc="Close ad panel" or @text="Skip"]').click_exists()
