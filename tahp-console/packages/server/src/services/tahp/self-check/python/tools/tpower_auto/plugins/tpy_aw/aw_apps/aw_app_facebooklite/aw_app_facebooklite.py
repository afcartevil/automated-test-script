# -*- coding: utf-8 -*-
# @Time     : 2025/5/13 15:52
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_facebooklite.py
from powertrde.utils.trde import adb
from tpy_aw.aw_app_base import AwAppBase
import time
from deprecated import deprecated


class AwAppFacebookLite(AwAppBase):
    aw_name = 'FacebookLite'
    default_app_package = 'com.facebook.lite'

    @deprecated('不在首页不会报错，修改为更通用的check')
    def check_lite_at_homepage(self):
        # 检查是否在facebooklite主页
        facebook_logo = self.u2d.xpath('//*[@resource-id="com.facebook.lite:id/main_layout"]/android.widget.FrameLayout[1]/android.view.ViewGroup[3]/android.view.ViewGroup[1]').wait(timeout=2)
        if facebook_logo:
            self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.facebook.lite:id/main_layout"]/android.widget.FrameLayout[1]/android.view.ViewGroup[3]/android.view.ViewGroup[5]', click=True)
        else:
            self.u2d_helper.assert_icon_exist('xpath', '//*[@content-desc="feed"]', click=True)
        time.sleep(2)

    def search_friend(self, friend_name):
        """
        搜索好友，前提已经在Facebook主页
        """
        self.und_u2.click_match_template(self.tt('btn_search'), match_times=5, match_interval=2)
        time.sleep(1)
        self.u2d_helper.input_text(friend_name)
        time.sleep(2)
        adb.exec_cmd(self.device_id, 'input keyevent 66')

    def step_into_friends_reels(self):
        """
        点进好友列表的Reels, 前提是已经在好友列表
        """
        self.und_u2.click_match_text('Reels', match_times=5, limit_area=(0.65, 0.4, 1, 0.6))

    def step_into_messages(self):
        """
        点进lite中的messages
        """
        self.und_u2.click_match_template(self.tt('chat_page_icon'), limit_area=(0, 0, 1, 0.2), target_score=0.90)

    def send_a_photo_to_friend(self):
        """
        给message里的好友发送非视频的第一张照片，前提是已经在好友会话界
        """
        self.u2d_helper.click_wait('//*[@content-desc="Open photo gallery." or @content-desc="Open camera roll"]', timeout=8)
        time.sleep(1)

        gallery_items = self.u2d.xpath('//*[@resource-id="com.facebook.lite:id/header_recycler_view"]/android.widget.FrameLayout').all()

        for i in range(min(5, len(gallery_items))):
            frame_xpath = f'//*[@resource-id="com.facebook.lite:id/header_recycler_view"]/android.widget.FrameLayout[{i + 1}]'

            image_node = self.u2d.xpath(f'{frame_xpath}//*[@resource-id="com.facebook.lite:id/gallery_item_image"]')
            if not image_node.exists:
                continue

            # 判断当前 FrameLayout 内是否包含视频时长节点（即当前项是视频）
            video_duration_node = self.u2d.xpath(f'{frame_xpath}//*[@resource-id="com.facebook.lite:id/video_duration"]')
            if video_duration_node.exists:
                continue

            self.u2d.xpath(frame_xpath).click()
            time.sleep(1)

            if self.u2d.xpath('//*[@text="Send"]').exists:
                time.sleep(1)
                self.u2d_helper.click_wait('//*[@text="Send"]', timeout=4)
                break

    def send_message_to_friend(self, text):
        """
        给好友发送信息，前提是已经在好友会话界面
        """
        self.u2d_helper.click_wait('//*[@text="Message"]', timeout=4)
        time.sleep(1)
        self.u2d_helper.input_text(text)
        self.u2d_helper.click_wait('//*[@content-desc="Send message"]/android.widget.ImageView[1]', pre_wait=1, timeout=4)