import time
import re

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_app_base import AwAppBase


class AwAppIMO(AwAppBase):
    aw_name = 'IMO'
    default_app_package = 'com.imo.android.imoim'

    def check_at_homepage(self):
        """
        检测是否在首页
        """
        self.u2d.xpath('//*[@text="Not Now"]').click_exists(timeout=4)
        result, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.imo.android.imoim:id/sliding_tabs"]/android.widget.LinearLayout[1]/android.view.ViewGroup[1]', click=True)
        if result:
            t_log.debug('已在IMO主页')
        else:
            raise XPathElementNotFoundError('未在IMO主页')
        time.sleep(2)

    def send_text(self, text):
        """
        发送消息
        """
        result_chat_bar, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.imo.android.imoim:id/chat_input_container"]', double_ckeck=True, click=True)
        if result_chat_bar is False:
            t_log.error('找不到聊天输入框')
            raise XPathElementNotFoundError('找不到聊天输入框')
        time.sleep(1)
        # self.u2d.send_keys('hello')
        u2utils.input_text(self.u2d, text)
        time.sleep(1)
        self.u2d_helper.press_back_key(1)
        time.sleep(1)
        self.u2d_helper.click_wait('//*[@resource-id="com.imo.android.imoim:id/chat_send"]', timeout=4)
        time.sleep(7)

    def send_image(self):
        """
        发送图片
        """
        self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.imo.android.imoim:id/chat_gallery"]', double_ckeck=True, click=True)
        time.sleep(1)
        # 规避发送视频以及规避存在长视频无法发送导致出错问题
        i = 2
        for i in range(2, 10):
            is_video = self.u2d.xpath(
                f'//*[@resource-id="com.imo.android.imoim:id/media_grid"]/android.widget.FrameLayout[{i}]/*[@resource-id="com.imo.android.imoim:id/video_duration_view"]').exists
            time.sleep(0.5)
            if not is_video:
                break
        self.u2d_helper.click_wait(f'//*[@resource-id="com.imo.android.imoim:id/media_grid"]/android.widget.FrameLayout[{i}]', timeout=5, post_wait=1)
        time.sleep(1)
        self.u2d_helper.click_wait('//*[@resource-id="com.imo.android.imoim:id/action_button"]', timeout=5, post_wait=1)
        time.sleep(1)
        self.u2d_helper.click_wait( '//*[@resource-id="com.imo.android.imoim:id/send"]', timeout=5, post_wait=1)
        time.sleep(3)

    def video_call(self, try_back = False):
        """
        try_back: 第一次没找到会点击back再找一下
        video call， 结束后可能有无法关闭的全屏广告
        """
        if not self.u2d.xpath('//*[@content-desc="Video call"]').exists and try_back:
            self.u2d_helper.press_back_key()
            time.sleep(1)
        self.u2d_helper.click_wait('//*[@content-desc="Video call"]', timeout=5)

    def change_to_contacts(self):
        """
        进入联系人界面
        """
        try:
            self.u2d_helper.click_wait('(//*[@resource-id="com.imo.android.imoim:id/tv_tab_text"])[3]', timeout=8, post_wait=1)
        except:
            raise Exception('没能成功进入联系人界面')

    def click_a_contact(self, contact_name):
        """
        进入某个好友的会话界面
        """
        try:
            self.u2d_helper.click_wait(f'//*[@text="{contact_name}"]', timeout=8, post_wait=1)
        except:
            raise Exception(f'没找到好友{contact_name}')

    def answer_call(self):
        """
        从弹窗接听电话
        """
        try:
            self.u2d_helper.click_wait('//*[@resource-id="com.imo.android.imoim:id/btn_video_accept_c_bg" or @resource-id="com.imo.android.imoim:id/audio_answer_button"]', timeout=8, post_wait=1)
        except:
            raise Exception('没成功接听电话')


    def end_call(self):
        """
        结束通话， 包括未接通的电话
        """
        if not adb.is_screen_on(self.u2d_helper.device_id):
            self.u2d_helper.screen_on_and_unlock()
            time.sleep(1)

        try:
            for i in range(3):
                if len(self.u2d.xpath('//*[@resource-id="com.imo.android.imoim:id/v_icon"]').all()) > 2:
                    self.u2d.xpath('//*[@resource-id="com.imo.android.imoim:id/v_icon"]').all()[3].click()
                    break

                self.u2d.click(0.5, 0.5)
                time.sleep(1)
        except:
            raise Exception('Failed to end call(没成功挂断电话)')

    def add_friends(self, imo_id, nick_name, c_u2d):
        """
        通过imo_id添加好友, 前提是已经在contacts界面
        """
        try:
            self.u2d.xpath('//android.widget.TextView[@text="New Contacts"]').click()
            time.sleep(2)
            self.u2d.xpath('//*[@resource-id="com.imo.android.imoim:id/tab_tv_imo_id"]').click()
            time.sleep(2)
            self.u2d.xpath('//android.widget.EditText').click()
            u2utils.input_text(self.u2d, imo_id)
            time.sleep(2)
            self.u2d.xpath('//*[@resource-id="com.imo.android.imoim:id/btn_search"]').click()
            time.sleep(3)
            self.u2d.xpath('//android.widget.TextView[@text="Accept"]').click_exists(timeout=2)
            new_friend = self.u2d.xpath('//*[@resource-id="com.imo.android.imoim:id/btn_add"]')
            if new_friend.exists:
                new_friend.click()
                time.sleep(3)
                c_u2d.swipe(0.50, 0.10, 0.50, 0.02, 0.1)
                time.sleep(3)
                c_u2d.xpath('//*[@resource-id="com.imo.android.imoim:id/b_start_btn"]').click()
                time.sleep(1)
                c_u2d.xpath('//*[@resource-id="com.imo.android.imoim:id/tv_tab_text"]').all()[2].click()
                time.sleep(1)
                c_u2d.xpath('//android.widget.TextView[@text="New Contacts"]').click()
                time.sleep(1)
                c_u2d.xpath('//android.widget.TextView[@text="Accept"]').click()
                time.sleep(3)
                self.u2d.xpath('//*[@resource-id="com.imo.android.imoim:id/et_message"]').click()
                for i in range(20):
                    adb.exec_cmd(self.device_id, 'input keyevent KEYCODE_DEL')
                time.sleep(1)
                u2utils.input_text(self.u2d, nick_name)
                time.sleep(1)
                self.u2d.xpath('//*[@resource-id="com.imo.android.imoim:id/btn_send" or @text="Save"]').click()
                time.sleep(1)

            # 已经添加但未修改nickname
            else:
                self.u2d.xpath('//*[@text="Accept"]').click_exists(timeout=4)
                self.u2d.xpath('//*[@resource-id="com.imo.android.imoim:id/barMoreBtn"]').click()
                self.u2d_helper.click_wait('//android.widget.TextView[@text="Remark"]', pre_wait=1, timeout=10,
                                           post_wait=1)
                for i in range(20):
                    adb.exec_cmd(self.device_id, 'input keyevent KEYCODE_DEL')
                time.sleep(1)
                u2utils.input_text(self.u2d, nick_name)
                time.sleep(1)
                self.u2d.xpath('//*[@resource-id="com.imo.android.imoim:id/b_end_btn"]').click()
                time.sleep(1)
        except:
            raise Exception(f'检测到没有配对的好友，但添加好友失败')

    def get_imo_id(self):
        """
        获取登录账号的imo_id
        """
        try:
            self.u2d.xpath('//*[@resource-id="com.imo.android.imoim:id/home_profile_pic"]').click()
            time.sleep(1)
            full_text = self.u2d(resourceId="com.imo.android.imoim:id/tv_imoid").get_text()
            time.sleep(1)
            imo_id = re.search(r'imo ID:(.*)', full_text).group(1).strip()
            return imo_id
        except:
            raise Exception('获取imo_id失败')

    def check_friend_exist(self, friend_name, c_aw):
        """
        ：imo_id为空，则只检查该名字的好友是否存在;不为空检查该好友和imo_id是否匹配
        检查该好友是否存在
        return: 0- 好友不存在 1-好友存在 2:好有存在但ID不匹配
        """
        try:
            friend = self.u2d.xpath(f'//*[@text="{friend_name}"]')
            time.sleep(2)
            if friend.exists:
                friend.click()
                time.sleep(1)
                self.video_call()
                time.sleep(2)
                try:
                    c_aw.end_call()
                    return 1
                except:
                    self.end_call()
                    self.u2d_helper.press_back_key(1)
                    return 2
            elif friend.exists:
                return 1

            return 0
        except:
            raise Exception('Failed to check whether the friend exist')

    def delete_friend(self, friend_name):
        """
        删除好友, 初始页面在好友会话界面。
        """
        try:
            self.u2d_helper.click_wait(f'//*[@text={friend_name}]', timeout=5, post_wait=1)
            self.u2d_helper.click_wait('//*[@resource-id="com.imo.android.imoim:id/barMoreBtn"]', timeout=5, post_wait=1)
            self.u2d_helper.click_wait('//*[@text="Delete Contact"]', timeout=5, post_wait=1)
            self.u2d_helper.click_wait('//*[@text="Yes"]', timeout=5, post_wait=1)
        except:
            raise Exception('Failed to delete friends')
