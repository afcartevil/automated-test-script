# -*- coding: utf-8 -*-
# @Time     : 2025/5/13 15:52
# @Author   : kaiyuan.xie
# @Email    : kaiyuan.xie@transsion.com
# @File     : aw_app_facebooklite.py
from powertrde.framework.tran_logger import t_log
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

    def search_friend(self, search_name, enter_people=False):
        """
        搜索用户，前提已经在Facebook主页, 但没有进入好友界面
        lite没有可获取控件，可自行选择图片识别或文字视频进入好友界面
        """
        self.und_u2.click_match_template(self.tt('btn_search'), match_times=5, match_interval=2)
        time.sleep(1)
        self.u2d_helper.input_text(search_name)
        time.sleep(2)
        adb.exec_cmd(self.device_id, 'input keyevent 66')
        time.sleep(2)
        # 点击people页面，有的用户反而搜不到
        # if enter_people:
        #     try:
        #         self.und_u2.click_match_text("People", target_score=0.5, match_times=5, match_interval=2)
        #     except:
        #         raise Exception('界面需要设置成英文')
        btn_mln = self.und_u2.match_text("People", target_score=0.5, match_times=5,
                                         match_interval=2)
        if btn_mln:
            # rn.record_pos("btn_ycg", btn_ycg.center)
            self.und_u2.click_tuple(btn_mln.center)
            time.sleep(3)

    def step_into_friends_reels(self):
        """
        点进好友列表的Reels看第一个视频, 前提是已经在好友列表
        """
        self.und_u2.click_match_text('Reels', match_times=5, limit_area=(0.65, 0.4, 1, 0.6))
        time.sleep(2)
        self.u2d.click(0.15, 0.7)
        time.sleep(2)
        # assert_reels = self.und_u2.match_text('Reels', match_times=5, limit_area=(0, 0, 0.5, 0.15))
        # assert_morevideos = self.und_u2.match_text('More videos', match_times=5, limit_area=(0, 0, 1, 0.15))
        # if not (assert_reels or assert_morevideos):
        #     raise Exception("疑似没有正确进入到视频Reels界面，检查是否更新或网络问题。")


    def step_into_messages(self):
        """
        点进lite中的messages界面
        """
        self.und_u2.click_match_template(self.tt('chat_page_icon'), limit_area=(0, 0, 1, 0.2), target_score=0.90)
        time.sleep(2)
        self.u2d_helper.wait_ui_obj('//*[@text="Messages"]', timeout=8, raise_on_not_exist=True)

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

    def enter_friends_message(self):
        """
        进入好友的对话界面，前提是已经在好友界面了
        """
        try:
            self.und_u2.click_match_text('Message', limit_area=(0.3, 0.3, 1, 0.6), match_times=7, scale_factor=1)
            time.sleep(2)
            assert not self.und_u2.match_text('Message', limit_area=(0.3, 0.3, 1, 0.6), match_times=7, scale_factor=1)
        except Exception as e:
            self.und_u2.click_match_text('Message', match_times=7, scale_factor=1)
            t_log.info("进入friends会话界面断言还是失败")
        self.first_message_pop()


    def send_message_to_friend(self, text):
        """
        给好友发送信息，前提是已经在好友会话界面
        """
        self.u2d_helper.click_wait('//*[@text="Message"]', timeout=4)
        time.sleep(1)
        self.u2d_helper.input_text(text)
        self.u2d_helper.click_wait('//*[@content-desc="Send message"]/android.widget.ImageView[1]', pre_wait=1, timeout=4)

    def first_message_pop(self):
        """
        第一次进入会话可能有弹窗，后面捕捉到可以加到监控里。暂时点击其他地方以免后续失败
        """
        self.u2d.click(0.3, 0.3)
        time.sleep(1)