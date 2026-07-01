import time
from deprecated import deprecated

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase
from tpytest_extends.scheme.cases_scheme import CasesScheme

class FacebookLocator(U2SelectorLocator):
    btn_search = U2Selector().xpath('//*[@content-desc="Search Facebook"]').bind()
    people = U2Selector().xpath('//*[@content-desc="People search results" or @text="People search results"]').bind()
    friends = U2Selector().desc_contains('{param_text}').bind()

class AwAppFacebook(FacebookLocator, AwAppBase):
    aw_name = 'Facebook'
    default_app_package = 'com.facebook.katana'

    def auto_login(self, google_email, google_password, google_name):
        """
        接口逻辑
        1. 该账户登录过:
            i. 设置直接弹出的弹窗点击该账号登录
            ii. app内已经保存过，在app内选择google名字
        2. 没有登录过
        """
        # 如果没有登录
        if self.u2d.xpath(f'//android.widget.TextView[@text="{google_email}"]').exists:
            self.u2d.xpath(f'//android.widget.TextView[@text="{google_email}"]').click()
            self.u2d_helper.click_wait('//*[@text="Save"]', timeout=15, post_wait=1)
            time.sleep(8)
        elif self.u2d.xpath(f'//*[@text="{google_name}"]').exists:
            self.u2d.xpath('//android.view.View[@text="Log in"]').click()
            time.sleep(8)
        elif self.u2d.xpath('//android.view.View[@text="Log in"]').exists:
            # 没有save的账号
            self.u2d.xpath('//*[@text="Mobile number or email"]').click()
            u2utils.input_text(self.u2d, google_email)
            time.sleep(1)
            adb.exec_cmd(self.device_id, 'input keyevent 66')
            time.sleep(1)
            u2utils.input_text(self.u2d, google_password)
            adb.exec_cmd(self.device_id, 'input keyevent 66')
            self.u2d.xpath('//android.view.View[@text="Log in"]').click()
            self.u2d_helper.click_wait('//*[@text="Save"]', timeout=15, post_wait=1)
            time.sleep(8)

        self.pop_choose_language()
        self.u2d_helper.wait_ui_obj('//*[@content-desc="Facebook logo"]', timeout=15)

    def pop_choose_language(self):
        """
        开屏时提示选择语言，即使登录过也可能会弹
        """
        self.u2d.xpath('//*[@content-desc="Continue in English (US)"]').click_exists(timeout=2)
        # 需要点三下
        self.u2d.xpath('//*[@content-desc="Skip"]').click_exists(timeout=1)
        self.u2d.xpath('//*[@content-desc="Skip"]').click_exists(timeout=1)
        self.u2d.xpath('//*[@content-desc="Skip"]').click_exists(timeout=1)

    @deprecated(reason='已经有一个检查homepage，建议使用另一个;不建议使用全路径')
    def check_fb_at_homepage(self):
        self.u2d.swipe(0.5, 0.3, 0.5, 0.7)
        time.sleep(1)
        result1, home1 = self.u2d_helper.assert_icon_exist('descriptionContains', 'Home, tab ')
        result2, home2 = self.u2d_helper.assert_icon_exist('xpath', '//android.widget.FrameLayout[4]/android.widget.LinearLayout[1]/android.widget.FrameLayout[1]/android.widget.FrameLayout[1]/android.widget.LinearLayout[1]/android.widget.FrameLayout[1]/android.widget.LinearLayout[1]/android.widget.LinearLayout[1]/android.widget.FrameLayout[2]/android.widget.LinearLayout[1]/android.widget.FrameLayout[1]')
        if result1:
            t_log.debug('已在facebook主页')
            home1.click()
        elif result2:
            t_log.debug('已在facebook主页')
            home2.click()
        else:
            raise XPathElementNotFoundError('未在facebook主页')
        time.sleep(2)

    def search_friend(self, search_name, friend_name=None):
        """
        搜索好友，到好友界面
        搜索名可能和好友名不一样, 好友名可以为中文，搜索名只能是英文，默认searchname=friendname
        """
        try:
            self.btn_search.click_wait(timeout=2)
            time.sleep(1)
            self.u2d(className='android.widget.EditText').click()
            self.u2d_helper.input_text(search_name)
            time.sleep(2)
            adb.exec_cmd(self.device_id, 'input keyevent 66')
            time.sleep(5)
            self.people.click()
            self.friends.with_params(param_text=friend_name if friend_name else search_name).click_wait(timeout=2)
            t_log.debug('找到好友')
            time.sleep(1)
        except Exception:
            raise Exception('Failed to found friends(找好友失败)')

    def check_facebook_at_homepage(self, raise_exception=True):
        """
        检查是否在首页
        """
        icon = self.u2d.xpath('//*[@content-desc="Facebook logo" or @descriptionContains="Messaging "]')
        if icon.exists:
            t_log.info('已在facebook主页')
            return True
        elif raise_exception:
            raise Exception('不在facebook首页')

        return False

    def back_homepage(self, press_back_time=0):
        """
        press_back_time是当前点击次数
        不在首页则点击back，最多点击4次
        """
        if not self.check_facebook_at_homepage(False):
           if press_back_time > 4:
               t_log.info("点击back键超过2次，重启facebook")
               self.restart_app()
               return
           t_log.info('不在主页,点击back键')
           self.u2d_helper.press_back_key(times=1)
           press_back_time += 1
           t_log.info('back次数{}'.format(press_back_time))
           self.back_homepage(press_back_time)
        else:
           t_log.info('在facebook主页')

    def commend(self, text):
        """
        评论某动态
        """
        self.search_commend()
        time.sleep(2)
        self.commend_message(text)

    def search_commend(self, swipe_times=0):
        """
        搜索动态，找到评论按钮，但未开始评论
        """
        time.sleep(2)
        t_log.info("滑动主页")
        self.u2d.swipe(0.5, 0.8, 0.5, 0.2, 0.2)
        time.sleep(2)
        commend = self.u2d(descriptionContains='Comment')
        if commend.exists():
            t_log.info('找到评论按钮')
            commend.click()
        elif swipe_times < 5:
            t_log.info('没有找到评论按钮,滑动主页')
            swipe_times += 1
            self.search_commend(swipe_times)
        else:
            raise XPathElementNotFoundError('没有找到评论按钮')

    @deprecated('不通用，可以拓展back_homepage')
    def press_back_key_to_homepage(self,back_key_times=0):
        self.u2d_helper.press_back_key()
        back_key_times += 1
        time.sleep(2)
        commend = self.u2d(descriptionContains='Comment')
        if commend.exists():
            return
        elif self.check_facebook_at_homepage(False):
            return
        elif back_key_times>3:
            raise Exception('没有返回主页')
        else:
            self.press_back_key_to_homepage(back_key_times)

    @deprecated('descriptionContains 是否通用，建议改为通用的之后再去掉废弃')
    def commend_message(self, text):
        """
        确定已经有评论按钮后，点击评论
        """
        t_log.info('点击评论输入框')
        message = self.u2d.xpath('//android.widget.AutoCompleteTextView')
        if message:
            message.click(timeout=5)
            time.sleep(2)
            t_log.info('输入评论')
            u2utils.input_text(self.u2d, text)
            time.sleep(2)
            self.u2d_helper.click_wait('//*[contains(@content-desc, "Show stickers")]', timeout=4)
            time.sleep(4)
            self.u2d_helper.assert_icon_exist('descriptionContains', 'Avatar is looking up and holding their hands above their head, red hearts are floating out from their hands.', click=True)

    def brush_vedio(self):
        t_log.info("滑动视频")
        self.u2d.swipe(0.5, 0.8, 0.5, 0.2)
        time.sleep(5)

    @deprecated('assert_icon_exist如果没有检测到控件不会报错，会直接点最后的图片，确认这是需要的吗')
    def create_story(self):
        """
        post新图片
        """
        t_log.info("点击create story")
        recyclerview_exist, _ = self.u2d_helper.assert_icon_exist('xpath', '(//androidx.recyclerview.widget.RecyclerView)[2]',
                                                     click=False)
        create_story_exist,element = self.u2d_helper.assert_icon_exist('descriptionContains', 'Create story')
        if recyclerview_exist:
            if create_story_exist:
                element.click()
            else:
                list_element = self.u2d.xpath('(//androidx.recyclerview.widget.RecyclerView)[2]')
                center = list_element.center()
                t_log.info('center:{} {}'.format(center[0], center[1]))
                for i in range(4):
                    self.u2d.swipe(center[0], center[1], center[0]+300, center[1], 0.3)
                    time.sleep(1)
                time.sleep(3)
                if create_story_exist:
                    element.click()

        time.sleep(2)
        t_log.info("选择排在第一的图片")
        self.u2d.xpath('//android.widget.GridView/*[3]').click()

    def swipe_story(self):
        t_log.info("滑动story")
        exist,_ = self.u2d_helper.assert_icon_exist('xpath', '(//androidx.recyclerview.widget.RecyclerView)[2]',
                                                  click=False)
        if exist:
            list_element = self.u2d.xpath('(//androidx.recyclerview.widget.RecyclerView)[2]')
            center = list_element.center()
            t_log.info('center:{} {}'.format(center[0], center[1]))
            for i in range(4):
                self.u2d.swipe(center[0]+300, center[1], center[0], center[1],0.3)
                time.sleep(1)
        else:
            raise XPathElementNotFoundError('没有找到create story view')

    @deprecated('复用search_friend')
    def search(self):
        t_log.info("点击搜索按钮")
        self.u2d(descriptionContains='Search').click(timeout=5)
        search = self.u2d.xpath('//android.widget.EditText')
        if search:
            search.click(timeout=5)
            time.sleep(2)
            t_log.info('输入搜索内容')
            u2utils.input_text(self.u2d, 'LadyGaga')
            time.sleep(5)
            self.u2d_helper.und_u2.click_match_text('Lady Gaga',limit_area=(0.1, 0.1, 0.5, 0.7),match_times=3)
            time.sleep(1)
        t_log.info('点击用户主页')
        time.sleep(3)
        exist, _ = self.u2d_helper.assert_icon_exist('descriptionContains', 'Musician/band', click=True)
        if exist:
            t_log.info('找到用户主页')
        elif self.u2d_helper.und_u2.click_match_text('Lady Gaga', limit_area=(0.1, 0.1, 0.5, 0.7),
                                                     match_times=3).success:
            t_log.info('找到用户主页')
        else:
            t_log.error('没有找到用户主页')
        t_log.info("滑动10次用户主页")
        for i in range(10):
            self.u2d.swipe(0.5, 0.8, 0.5, 0.2, 0.2)
            time.sleep(1)
        self.u2d_helper.press_back_key()
        t_log.info("滑动10次搜索主页")
        for i in range(10):
            self.u2d.swipe(0.5, 0.8, 0.5, 0.2,0.2)
            time.sleep(1)

    def voice_call(self):
        """
        使用静态图片打语音电话，图片有变化拓展图片库
        """
        playbacker = CasesScheme().prg.get_static(self.aw_name)
        self.u2d_helper.und_u2.click_match_template(playbacker.get('voice_call'))
        time.sleep(1)

    def video_call(self):
        """
        使用静态图片打视频电话，图片有变化拓展图片库
        """
        playbacker = CasesScheme().prg.get_static(self.aw_name)
        self.u2d_helper.und_u2.click_match_template(playbacker.get('video_call'))
        time.sleep(1)

    def answer_call(self):
        """
        接听电话
        """
        self.u2d_helper.click_wait('//*[@text="Answer"]', pre_wait=1, timeout=8, post_wait=1)

    def end_call(self):
        """
        挂断电话， 先尝试用控件关闭，没有控件则图片识别
        """
        max_attempts = 3

        for attempt in range(max_attempts):
            # 首先尝试查找控件
            if self.u2d.xpath('//*[@content-desc="End call"]').exists:
                self.u2d.xpath('//*[@content-desc="End call"]').click()
                time.sleep(1)
                break

            # 如果没有控件，尝试图片识别
            if self.u2d_helper.und_u2.match_template(self.tt('end_call'), target_score=0.85, limit_area=(0.74, 0.82, 1, 1)):
                self.u2d_helper.und_u2.click_match_template(self.tt('end_call'), target_score=0.85, limit_area=(0.74, 0.82, 1, 1))
                time.sleep(1)
                break

            # 如果都没找到，可能按钮被隐藏了，点击中心唤醒
            if attempt < max_attempts - 1:
                self.u2d.click(0.5, 0.5)
                time.sleep(1)
            else:
                print("多次尝试后仍未找到挂断按钮")

        # 处理通话结束后的关闭操作
        time.sleep(1)
        if self.u2d.xpath('//*[@content-desc="Close"]').exists:
            self.u2d.xpath('//*[@content-desc="Close"]').click()
            return
        result = self.u2d_helper.und_u2.match_template(self.tt('close_call'), target_score=0.85, limit_area=(0.78, 0, 1, 0.12))
        if result:
            self.u2d_helper.und_u2.click_match_template(self.tt('close_call'), target_score=0.85, limit_area=(0.78, 0, 1, 0.12))
            time.sleep(1)

    def post_picture(self):
        """
        在首页post一张图片
        """
        # 前提是在首页
        self.u2d_helper.grant_common_permissions(self.app_package)

        self.u2d_helper.click_wait('//*[@content-desc="Create, Double tap to create a new post, story, or reel"]', timeout=10, post_wait=1)

        self.u2d_helper.click_wait('//*[@content-desc="Post" or @text="Post"]', timeout=5, post_wait=1)

        self.u2d_helper.click_wait('//*[@content-desc="Photo/video"]', timeout=5, post_wait=1)

        self.u2d.click(0.15, 0.2)

        self.u2d_helper.click_wait('//*[@content-desc="POST"]', timeout=5, post_wait=1)

    def share_picture_with_friends(self, is_friend_page:bool = False, friend_name:str = 'yuanchuangui'):
        """
        进入好友界面发送图片
        """
        self.u2d_helper.grant_common_permissions(self.app_package)
        # 进入好友界面
        if not is_friend_page:
            try:
                self.search_friend(friend_name)
            except Exception:
                # 最后一步可能获取不到
                self.u2d.click(0.35, 0.25)

        self.u2d_helper.click_wait('//*[@content-desc="Message"]', timeout=8)
        self.u2d_helper.click_wait('//*[@content-desc="Open photo gallery."]', timeout=10, post_wait=1)
        time.sleep(2)
        self.u2d.click(0.15, 0.78)
        self.u2d_helper.click_wait('//*[@content-desc="Send"]', timeout=8)

    def click_short(self):
        """
        进入短视频界面
        """
        self.und_u2.click_match_template(self.tt('icon_video'), match_times=3, target_score=0.85,
                                         limit_area=(0, 0.08, 0.85, 0.20))
