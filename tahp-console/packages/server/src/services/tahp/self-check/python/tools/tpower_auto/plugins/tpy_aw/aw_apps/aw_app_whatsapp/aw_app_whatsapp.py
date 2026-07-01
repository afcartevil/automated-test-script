import time
from deprecated import deprecated

from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends import u2utils
from tpy_aw.aw_app_base import AwAppBase
import time

from tpy_aw.aw_apps.aw_app_phone.aw_app_phone import AwAppPhone


class AwAppWhatsapp(AwAppBase):
    aw_name = 'WhatsApp'
    default_app_package = 'com.whatsapp'
    press_back_key_times = 0

    @deprecated('是否可以使用check_at_homepage')
    def check_and_return_at_homepage(self):
        icon_exist, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.whatsapp:id/bottom_nav"]')
        if icon_exist:
            t_log.info('已在whatsapp主页')
            return True
        else:
            return False

    def back_homepage(self, press_back_time=0):
        if not self.check_and_return_at_homepage():
            if press_back_time > 2:
                t_log.info("点击back键超过2次，重启whatsapp")
                self.restart_app()
                return
            t_log.info('不在主页,点击back键')
            self.u2d_helper.press_back_key(times=1)
            time.sleep(2)
            press_back_time += 1
            t_log.info('back次数{}'.format(press_back_time))
            self.back_homepage(press_back_time)
        else:
            t_log.info('在whatsapp主页')

    def open_camera_and_send_picture(self):
        time.sleep(2)
        self.u2d_helper.assert_icon_exist('xpath', '//android.widget.Button[@text="OK"]', click=True)
        t_log.info('打开相机图标')
        time.sleep(2)
        self.u2d_helper.click_wait('//*[@resource-id="com.whatsapp:id/menuitem_camera"]', wait_after_click=2)
        t_log.info('打开相机选择第一张图片')
        time.sleep(2)
        self.u2d_helper.click_wait('//*[@resource-id="com.whatsapp:id/thumb"]', pre_wait=1)
        t_log.info('点击图片预览并发送')
        self.u2d_helper.click_wait('//*[@resource-id="com.whatsapp:id/send"]', pre_wait=2, wait_after_click=5)
        exist, element = self.u2d_helper.assert_icon_exist('xpath',
                                                           '//*[@resource-id="com.whatsapp:id/contactpicker_row_ephemeral_status"]')
        if exist:
            t_log.info('选择最近联系人')
            element.click()
        elif self.u2d.xpath('(//*[@resource-id="com.whatsapp:id/contactpicker_text_container"])[2]').exists:
            t_log.info('选择最近联系人2')
            self.u2d.xpath('(//*[@resource-id="com.whatsapp:id/contactpicker_text_container"])[2]').click(timeout=5)
        elif self.u2d.xpath('(//*[@resource-id="com.whatsapp:id/contactpicker_text_container"])[4]').exists:
            t_log.info('选择最近联系人3')
            self.u2d.xpath('(//*[@resource-id="com.whatsapp:id/contactpicker_text_container"])[4]').click(timeout=5)
        else:
            raise Exception('选择最近联系人失败')
        t_log.info('点击发送图片')
        self.u2d_helper.click_wait('//*[@resource-id="com.whatsapp:id/send"]', wait_after_click=5)

    def click_pictrue(self):
        t_log.info('查看对话框的图片')
        # self.u2d_helper.click_wait('//*[@resource-id="com.whatsapp:id/image"]', wait_after_click=2)
        if self.u2d(resourceId='com.whatsapp:id/text_and_date').exists():
            self.u2d(resourceId='com.whatsapp:id/text_and_date').click(timeout=3)
        else:
            t_log.info('没有图片')
            raise Exception('查看图片失败')

    def return_chats_list_top(self):
        t_log.info('点击chats回到对话列表顶部')
        self.u2d(descriptionContains='Chats').click(timeout=5)

    def click_top_conversation_list(self):
        self.return_chats_list_top()
        t_log.info('点击第一个对话列表')
        self.u2d_helper.click_wait('//*[@resource-id="com.whatsapp:id/conversations_row_date"]', wait_after_click=2)

    @deprecated('建议拆分点击列表和发送信息的功能，已经有发送信息的功能')
    def slide_top_conversation_list_and_send_message(self, text='test text input'):
        t_log.info('滑动第一个对话列表')
        self.u2d.swipe(0.5, 0.3, 0.5, 0.7)
        t_log.info('点击对话框')
        message = self.u2d.xpath('//android.widget.EditText')
        if message.wait(timeout=5):
            message.click(timeout=5)
            time.sleep(2)
            u2utils.input_text(self.u2d, text)
        self.u2d.sleep(2)
        t_log.info('发送消息')
        self.u2d_helper.click_wait('//*[@resource-id="com.whatsapp:id/conversation_entry_action_button"]',
                                   wait_after_click=1)

    def check_at_homepage(self):
        result, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.whatsapp:id/toolbar_logo"]',
                                                      double_ckeck=True)
        if result:
            t_log.debug('已在WhatsApp主页')
        else:
            raise Exception('未在WhatsApp主页')
        time.sleep(2)

    def search_contact(self, contact_name):
        """
        搜索联系人进入会话
        """
        # 如果首页已经有这个名字了，该控件会被获取到2次，反而会报错，所以不需要搜索
        if not self.u2d.xpath(f'//*[@text="{contact_name}"]').exists:
            self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.whatsapp:id/menuitem_search"]', click=True)
            time.sleep(1)
            # self.u2d.send_keys(contact_name)
            u2utils.input_text(self.u2d, contact_name)
            time.sleep(1)
            adb.exec_cmd(self.device_id, 'input keyevent 66')

        self.u2d_helper.click_wait(f'//*[@text="{contact_name}"]', pre_wait=2, timeout=10)

    @deprecated
    def search_contact2(self, contact_name):
        self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.whatsapp:id/menuitem_search"]', click=True)
        time.sleep(1)
        u2utils.input_text(self.u2d, contact_name)
        time.sleep(1)
        adb.exec_cmd(self.device_id, 'input keyevent 66')
        time.sleep(2)
        contacts = self.u2d.xpath('//*[@resource-id="com.whatsapp:id/conversations_row_content" or @resource-id="com.whatsapp:id/contactpicker_text_container"]')
        # contacts = self.u2d(text=contact_name)
        if contacts.exists:
            contacts.click()
        else:
            t_log.info("没有搜索到联系人")
        time.sleep(2)

    def voice_call(self):
        """
        语音通话
        """
        time.sleep(2)
        if not self.u2d.xpath('//*[@content-desc="Voice call"]').exists:
            self.u2d_helper.press_back_key()
            time.sleep(1)
        self.u2d_helper.assert_icon_exist('xpath', '//*[@content-desc="Voice call"]', click=True)
        time.sleep(1)
        voice_call_icon = self.u2d(text="Voice call")
        if voice_call_icon.wait(timeout=3):
            voice_call_icon.click()
            time.sleep(1)
        self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="android:id/button1"]', click=True)

    def video_call(self):
        """
        视频通话
        """
        time.sleep(2)
        if not self.u2d.xpath('//*[@content-desc="Video call"]').exists:
            self.u2d_helper.press_back_key()
            time.sleep(1)
        self.u2d_helper.assert_icon_exist('xpath', '//*[@content-desc="Video call"]', click=True)
        time.sleep(1)
        self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="android:id/button1"]', click=True)

    def answer_call(self):
        """
        接听电话
        """
        self.u2d_helper.click_wait('//*[@text="Answer" or @text="Video"]', pre_wait=1, timeout=8, post_wait=1)

    def end_call(self):
        """
        挂断电话
        """
        try:
            if not self.u2d.xpath(
                    '//*[@resource-id="com.whatsapp:id/footer_end_call_btn" or @resource-id="com.whatsapp:id/end_call_button" or @content-desc="Leave call"]').exists:
                self.u2d.click(0.50, 0.50)
                time.sleep(1)

            self.u2d.xpath(
                '//*[@resource-id="com.whatsapp:id/footer_end_call_btn" or @resource-id="com.whatsapp:id/end_call_button" or @content-desc="Leave call"]').click()
        except Exception:
            raise Exception('No end call button found(没找到挂断电话的按钮)')

    def send_message(self, text):
        """
        发送信息
        """
        self.u2d.xpath('//android.widget.EditText').click()
        self.u2d_helper.input_text(text)
        time.sleep(1)
        self.u2d_helper.click_wait('//*[@resource-id="com.whatsapp:id/conversation_entry_action_button"]', timeout=3)

    def click_communities_tab(self):
        """
        点击 communities tab
        """
        self.u2d.xpath('//*[@text="Communities"]').click(timeout=1)
        time.sleep(2)

    def click_chats_tab(self):
        """
        点击 chats tab
        """
        self.u2d.xpath('//*[@text="Chats"]').click(timeout=1)
        time.sleep(2)

    def share_photos_with_friends(self, is_conversion_page: bool = False, friend_name: str = ''):
        """
        @param is_conversion_page: 已经在会话首页
        @param friend_name: 要进入的好友名称，否则默认点会话框第一个
        有可能传的是视频，没做区分
        """
        self.u2d_helper.grant_common_permissions(self.app_package)

        if not is_conversion_page:
            if friend_name:
                self.search_contact(friend_name)
            else:
                # 默认点第一个
                if self.u2d.xpath('//*[@resource-id="com.whatsapp:id/conversations_row_contact_name" '
                                      'or @resource-id="com.whatsapp:id/contact_row_container"]').exists:
                    self.click_top_conversation_list()
                else:
                    raise Exception('首页没有会话框，也没有搜索朋友')

        self.u2d_helper.click_wait('//*[@resource-id="com.whatsapp:id/camera_btn" or @content-desc="Camera"]', timeout=8, post_wait=1)
        self.u2d_helper.click_wait('//*[@text="Photo"]', timeout=5, post_wait=1)
        self.u2d_helper.click_wait('//*[@resource-id="com.whatsapp:id/gallery_btn" or @content-desc="Gallery"]', timeout=5, post_wait=3)
        self.u2d_helper.click_wait("//*[contains(@content-desc, 'Photo')]")
        self.u2d_helper.click_wait('//*[@resource-id="com.whatsapp:id/send_media_btn"]')
        # self.u2d_helper.click_wait('//*[@resource-id="com.whatsapp:id/send" or @content-desc="Send" or @resource-id="com.whatsapp:id/media_item_view"]',
        #                            pre_wait=1, timeout=20, post_wait=1)


    def get_whatsapp_phone(self):
        """
        获取whatsapp手机号
        手机登录的账号对应的电话号码可能和本身卡的不一样，所以要在app里看
        """
        try:
            self.u2d.xpath('//*[@resource-id="com.whatsapp:id/menuitem_overflow"]').click()
            time.sleep(1)
            self.u2d.xpath('//android.widget.TextView[@text="Settings"]').click()
            time.sleep(1)
            self.u2d.xpath('//*[@resource-id="com.whatsapp:id/profile_info"]').click()
            time.sleep(1)

            country_code = ''
            phone_number = ''

            # 获取 WhatsApp 联系人名称
            if self.u2d(textContains='+').exists:
                contact_text = self.u2d(textContains='+').get_text()
                country_code, phone_number = self.u2d_helper.get_phone_number_and_countrycode(contact_text)

            self.u2d_helper.press_back_key(1)

            return country_code, phone_number
        except:
            raise Exception('Failed to get copilot whatsapp phone number')

    def check_google_storage_backup(self):
        """
        检查google storage backup的弹窗
        """
        if self.u2d.xpath('//android.widget.TextView[@text="Google storage backup"]').exists:
            self.u2d.xpath('//*[@resource-id="com.whatsapp:id/gdrive_new_user_setup_not_now_btn"]').click()

    def add_friends(self, aw_phone:AwAppPhone, friends_name, country_code, phone_number):
        """
        加好友是通过手机自带的通讯录添加联系人，whatsapp会同步显示
        前提可能是需要该账号不是关联的账号
        """
        try:
            aw_phone.restart_app_by_monkey()
            time.sleep(5)
            aw_phone.delete_contacts(friends_name)

            aw_phone.restart_app_by_monkey()
            time.sleep(2)
            aw_phone.add_a_new_contact(friends_name, country_code, phone_number)
        except:
            raise Exception('Failed to add a new friends, you can add it manually')