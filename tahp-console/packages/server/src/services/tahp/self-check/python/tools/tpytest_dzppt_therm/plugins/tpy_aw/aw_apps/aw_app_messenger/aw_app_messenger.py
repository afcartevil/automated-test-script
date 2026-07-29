import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase
from tpytest_extends.scheme.cases_scheme import CasesScheme
from deprecated import  deprecated

class MessengerLocator(U2SelectorLocator):
    new_message_btn = U2Selector().xpath('//*[@content-desc="New message"]').bind()

class AwAppMessenger(MessengerLocator, AwAppBase):
    aw_name = 'Messenger'
    default_app_package = 'com.facebook.orca'

    def check_at_homepage(self):
        result, _ = self.u2d_helper.assert_icon_exist('descriptionContains', 'Chats', click=True)
        if result:
            t_log.debug('已在Messenger主页')
        else:
            raise XPathElementNotFoundError('未在Messenger主页')
        time.sleep(2)

    def check_expired_and_continue(self):
        """
        长时间不登录会提示expired,需要重新点登录
        """
        if self.u2d.xpath('//*[@text="Use another profile"]').exists:
            self.u2d_helper.click_wait('//*[@text="Continue"]')
            time.sleep(2)

    def search_friend(self, friend_name):
        """
        搜索好友
        """
        if self.u2d_helper.xpath_get('//*[@content-desc="Search"]'):
            self.u2d_helper.xpath_click_must('//*[@content-desc="Search"]')
        else:
            self.u2d.click(0.5, 0.148)
        time.sleep(1.5)
        self.u2d_helper.input_text(friend_name)
        time.sleep(2)
        adb.exec_cmd(self.device_id, 'input keyevent 66')
        time.sleep(5)

    def click_search_friends(self):
        """
        通过搜索按钮进来之后，搜索后的friends满足条件：在RecyclerView下的第一个以ViewGroup为父控件，子控件为BUtton，再往下为ImageView的元素
        """
        # 满足这个条件的第一个就是，一般不会变的
        self.u2d_helper.xpath_click_must('//androidx.recyclerview.widget.RecyclerView/android.view.ViewGroup/android'
                                         '.widget.Button/android.widget.ImageView', sleep_time=2)


    def click_friends(self, name):
        """
        在主页用文字识别找好友
        """
        self.und_u2.click_match_text(name, limit_area=(0, 0.2, 1, 1), match_times=5)

    @deprecated('拓展check_at_homepage')
    def check_messager_at_homepage(self):
        time.sleep(2)
        exist,_ = self.u2d_helper.assert_icon_exist('descriptionContains', 'Chats', click=False)
        # xpath = ("//*[starts-with(normalize-space(@content-desc),'Chats') "
        #          "or starts-with(normalize-space(@contentDescription),'Chats')]")
        # exist,_ = self.u2d_helper.assert_icon_exist('descriptionContains', xpath, click=False)
        if exist:
            t_log.info('已在messager主页')
            return True
        else:
            return False

    def back_homepage(self, press_back_time=0):
        if not self.check_messager_at_homepage():
            if press_back_time > 3:
                t_log.info("点击back键超过2次，重启messager")
                self.restart_app()
                return
            t_log.info('不在主页,点击back键')
            self.u2d_helper.press_back_key(times=1)
            press_back_time += 1
            t_log.info('back次数{}'.format(press_back_time))
            self.back_homepage(press_back_time)
        else:
            t_log.info('在messager主页')

    def send_message(self, text: str = "test text input"):
        """
        发送信息，前提是在好友页面
        """
        message = self.u2d.xpath('//android.widget.EditText')
        if not message.exists:
            self.u2d_helper.press_back_key()
            time.sleep(1)
        message.click(timeout=5)
        time.sleep(1)
        u2utils.input_text(self.u2d, text)
        time.sleep(2)
        send = self.u2d.xpath('//*[@content-desc="Send" or @content-desc="Envoyer"]')
        time.sleep(2)
        if send.exists:
            send.click()
        else:
            self.und_u2.click_match_template(self.tt('send_message'))

    def switch(self):
        self.u2d_helper.assert_icon_exist('descriptionContains','Tab 1 of 3',click=True)
        time.sleep(1)
        self.u2d_helper.assert_icon_exist('descriptionContains','Tab 2 of 3',click=True)
        time.sleep(1)
        self.u2d_helper.assert_icon_exist('descriptionContains','Tab 3 of 3',click=True)
        time.sleep(1)

    def end_call(self):
        if not adb.is_screen_on(self.u2d_helper.device_id):
            self.u2d_helper.screen_on_and_unlock()
            time.sleep(1)

        if not self.u2d.xpath('//*[@content-desc="End call"]').exists:
            self.u2d.click(0.50, 0.50)
        self.u2d_helper.click_wait('//*[@content-desc="End call"]', pre_wait=1)
        self.u2d_helper.click_wait('//*[@content-desc="Close"]', pre_wait=1, no_raise=True)
        time.sleep(1)

    @deprecated('拓展search_friend')
    def search_messenger_contact(self, contact_name):
        self.u2d_helper.assert_icon_exist('xpath','//android.view.ViewGroup[@text="Search" or @text="Rechercher"]',click=True)
        time.sleep(2)
        t_log.debug(contact_name)
        self.u2d.send_keys("".join(contact_name))
        time.sleep(2)
        adb.exec_cmd(self.device_id, 'input keyevent 66')
        time.sleep(5)
        elem = self.u2d.xpath('//*[@text="More people"]')
        if  elem.exists:
            bounds = elem.info
            center_x = (bounds.get('bounds').get("left") + bounds.get('bounds').get("right"))/2
            center_y = (bounds.get('bounds').get("top") + bounds.get('bounds').get("bottom"))/2
            self.u2d.click(center_x,center_y-150)
        else:
            elem = self.u2d.xpath('//*[@text="Personnes"]')
            bounds = elem.info
            center_x = (bounds.get('bounds').get("left") + bounds.get('bounds').get("right")) / 2
            center_y = (bounds.get('bounds').get("top") + bounds.get('bounds').get("bottom")) / 2
            self.u2d.click(center_x, center_y+100)
        # exist,ele = self.u2d_helper.assert_icon_exist('xpath', '(//android.widget.Button)[3]')
        # if exist:
        #     time.sleep(3)
        #     t_log.info('搜索到联系人')
        #     ele.click()
        # else:
        #     raise XPathElementNotFoundError('未搜索到联系人')

    def video_call(self):
        """
        视频通话
        """
        res,ele = self.u2d_helper.assert_icon_exist('xpath', '//*[@content-desc="Video call" or @content-desc="Appel vidéo"]')
        if res:
            t_log.info('点击视频通话')
            ele.click()
        else:
            raise XPathElementNotFoundError('点击视频通话失败')

    def audio_call(self):
        """
        语音通话
        """
        res,ele = self.u2d_helper.assert_icon_exist('xpath', '//*[@content-desc="Audio call"]')
        if res:
            t_log.info('点击语音通话')
            ele.click()
        else:
            raise XPathElementNotFoundError('点击语音通话失败')

    def answer_call(self):
        """
        接听电话弹窗
        """
        try:
            self.u2d_helper.click_wait('//*[@text="Answer"]', pre_wait=1, timeout=10, post_wait=1)
        except:
            raise Exception("没有电话弹窗提示，检查账号、网络、和好友是否是辅助机登录的账号\nNo call popup notification received. Please verify your account, network connection, and friend\'s nickname.")

    def view_chat_list_and_swipe(self):
        chat_icon=self.u2d(descriptionContains='Chats')
        if chat_icon.wait(timeout=5):
            chat_icon_x,chat_icon_y=chat_icon.center()
            self.u2d.double_click(chat_icon_x,chat_icon_y)
        self.u2d(className='androidx.recyclerview.widget.RecyclerView').child(index=3).click(timeout=5)
        message = self.u2d.xpath('//android.widget.EditText')
        if not message.wait(timeout=5):
            self.u2d_helper.press_back_key()
            time.sleep(3)
            self.u2d_helper.assert_icon_exist('xpath','(//android.widget.Button)[5]',click=True)
        t_log.debug('上下滑动消息页面')
        for i in range(6):
            self.u2d.swipe(0.5, 0.2, 0.5, 0.8, 0.2)
            time.sleep(1)
        for i in range(7):
            self.u2d.swipe(0.5, 0.8, 0.5, 0.2, 0.2)
            time.sleep(1)

    def send_photos(self):
        """
        发送相册里的图片，前提是已经在联系人界面
        """
        if not self.u2d.xpath("//*[contains(@content-desc, 'Photo taken')]").exists:
            self.u2d_helper.click_wait('//*[@content-desc="Open photo gallery."]', timeout=4)
            time.sleep(1)
        self.u2d_helper.click_wait("//*[contains(@content-desc, 'Photo taken')]", timeout=4)
        time.sleep(1)
        self.u2d_helper.click_wait('//*[@text="Send"]', timeout=4)

    def send_photo_or_video(self, mode='NORMAL', video_time=10):
        """
        拍摄视频发送，前提是已经在联系人界面
        """
        self.u2d_helper.click_wait('//*[@content-desc="Open camera."]', timeout=5)
        time.sleep(1)
        self.u2d_helper.click_wait(f'//*[@text="{mode}"]', timeout=4)
        self.u2d.xpath("//*[contains(@content-desc, 'Capture')]").click()
        if mode == 'VIDEO':
            time.sleep(video_time)
            self.u2d.xpath("//*[contains(@content-desc, 'Capture')]").click()
        time.sleep(2)
        self.u2d.xpath('//*[@text="Send" or @content-desc="Send"]').click()
        time.sleep(5)

    def view_sent_video(self):
        """
        查看已发送的视频，前提是已经在联系人界面，且刚刚发送了视频（没有加滑动查找视频和找不到的报错处理）
        """
        video = self.u2d.xpath('//*[@content-desc="Play video"]').wait(timeout=2)
        if video:
            self.u2d.xpath('//*[@content-desc="Play video"]').click()
        else:
            self.u2d.click(0.8, 0.7)

