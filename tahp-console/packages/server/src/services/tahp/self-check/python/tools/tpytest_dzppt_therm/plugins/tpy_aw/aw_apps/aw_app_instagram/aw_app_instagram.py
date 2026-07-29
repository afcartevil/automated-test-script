import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from powertrde.utils.u2_extends import u2utils
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw import U2WatchersCommon
from tpy_aw.aw_app_base import AwAppBase
from tpy_aw.aw_apps.aw_app_instagram.u2_watchers_instagram import U2WatchersInstagram


class InstagramLocator(U2SelectorLocator):
    creation_tab_btn = U2Selector().xpath('//*[@resource-id="com.instagram.android:id/creation_tab" or @resource-id="com.instagram.android:id/action_bar_buttons_container_left"]').bind()
    camera_btn_on_creation_tab = U2Selector().xpath(
        '//*[@resource-id="com.instagram.android:id/gallery_picker_grid_item_container"] | '
        '//*[@resource-id="com.instagram.android:id/unified_camera_button"]').bind()
    # 适配不同手机中creation_tab中的相机按钮
    post_btn_on_creation_tab = U2Selector().xpath('//*[@content-desc="POST"]').bind()
    camera_shutter_btn = U2Selector().xpath('//*[@resource-id="com.instagram.android:id/camera_shutter_button"]').bind()


class AwAppInstagram(InstagramLocator, AwAppBase):
    aw_name = 'Instagram'
    default_app_package = 'com.instagram.android'

    def check_at_homepage(self, raise_exception=True):
        result, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.instagram.android:id/feed_tab"]',
                                                      click=True)
        if result:
            t_log.debug('已在Instagram主页')
            return True
        elif raise_exception:
            raise Exception('不在Instagram首页')

        return False

    def auto_login(self, google_email, google_password, google_name=None):
        """
        自动登录
        """
        if self.u2d.xpath('//*[@text="Log in"]').exists:
            self.u2d.xpath('//android.widget.EditText').all()[0].click()
            self.u2d_helper.input_text(google_email)
            time.sleep(1)
            self.u2d.xpath('//android.widget.EditText').all()[1].click()
            self.u2d_helper.input_text(google_password)
            time.sleep(1)
            self.u2d.xpath('//*[@text="Log in"]').click()
            time.sleep(3)
            self.u2d.xpath('//android.view.View[@text="Save"]').click_exists()
        # 有存储记录且选择该账号登录
        elif self.u2d.xpath('//*[@text="Continue"]').exists:
            self.u2d.xpath('//*[@text="Continue"]').click()
        elif self.u2d.xpath('//*[@text="Choose a saved password for Instagram"]').exists:
            self.u2d(textContains='@gmail.com').click()
            time.sleep(10)

    def back_homepage(self, press_back_time=0):
        """
        press_back_time是当前点击次数
        不在首页则点击back，最多点击4次
        """
        if not self.check_at_homepage(False):
            if press_back_time > 4:
                t_log.info("点击back键超过4次，重启instagram")
                self.restart_app()
                return
            t_log.info('不在主页,点击back键')
            self.u2d_helper.press_back_key(times=1)
            press_back_time += 1
            t_log.info('back次数{}'.format(press_back_time))
            self.back_homepage(press_back_time)
        else:
            t_log.info('在instagram主页')

    def switch_to_shortvideo_page(self):
        self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.instagram.android:id/clips_tab"]', click=True)
        time.sleep(2)

    def switch_to_creation_page(self):
        """
        点到post的reels里
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.instagram.android:id/creation_tab" or @resource-id="com.instagram.android:id/action_bar_buttons_container_left"]', timeout=5)
        with self.u2_apply_watchers(
                names=["common_allow_all_button", "common_while_using_app_button", "instagram_turn_on_button",
                       "common_ok_button", "instagram_start_new_video_btn"]):
            # REEL
            self.u2d_helper.click_wait('//*[@resource-id="com.instagram.android:id/cam_dest_clips"]', timeout=15)

    def open_camera_in_reel_page(self):
        """
        点击左上角的相机图标
        """
        try:
            self.u2d_helper.click_wait('//*[@content-desc="Open camera" or @content-desc="Camera" or @text="Start new video"]', pre_wait=1, timeout=5)
        except Exception as e:
            self.und_u2.click_match_template(self.tt("camera"), target_score=0.9, match_times=4)

    def long_click_camera(self, hold_time=30):
        """
        长按录制时间
        @param hold_time: 长按时间(s)
        """
        x, y = self.u2d_helper.get_bounds_corner(
            '//*[@resource-id="com.instagram.android:id/camera_shutter_button_container"]', 'center')
        self.u2d.long_click(x, y, hold_time)

    def open_template_in_reel_page(self):
        """
        点击上方的模板图标
        """
        self.u2d_helper.click_wait('//*[@text="Templates"]', timeout=5)
        time.sleep(2)

    def choose_first_template(self):
        """
        选择第一个模板
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.instagram.android:id/template_browser_clips_item_container"]',
                                   timeout=10)
        time.sleep(2)

    def add_media_to_reels(self, photo_count=1, video_count=0):
        """
        添加媒体到Reels页面
        @param photo_count: 照片数量
        @param video_count: 视频数量
        """
        self.u2d_helper.click_wait('//*[@text="Add media"]', timeout=5)
        time.sleep(2)
        for _ in range(10):
            media_list = self.u2d.xpath('//android.widget.GridView/android.view.ViewGroup').all()
            for media in media_list:
                if media.info['childCount'] == 3 and photo_count > 0:
                    media.click()
                    photo_count -= 1
                    time.sleep(1)
                if media.info['childCount'] > 3 and video_count > 0:
                    media.click()
                    video_count -= 1
                    time.sleep(1)
            if photo_count == 0 and video_count == 0:
                break
            else:
                self.und_u2.swipe_direction('up', speed=200)
        else:
            raise Exception(f'There are not enough media to add: {photo_count} photos and {video_count} videos')

    def share_reels(self):
        """
        在post录制视频后点击分享，不确定其他的能不能使用，如果可以服用建议在这个基础上脱耦、拓展
        """
        for _ in range(5):
            if self.u2d.xpath('//*[@text="Next"]').wait(timeout=2):
                self.u2d_helper.click_wait('//*[@text="Next"]', timeout=4)
                time.sleep(2)
            else:
                break

        with self.u2_apply_watchers(watchers=[U2WatchersCommon.common_ok_button]):
            try:
                self.u2d_helper.click_wait('//*[@resource-id="com.instagram.android:id/share_button"]', timeout=4)
            except Exception:
                time.sleep(2)
                self.u2d_helper.press_back_key(times=1)
                time.sleep(1)
                self.u2d_helper.click_wait('//*[@resource-id="com.instagram.android:id/share_button"]', timeout=6)
            time.sleep(2)
            result, share_btn = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.instagram.android:id/clips_nux_sheet_share_button"]', click=False)
            if result:
                share_btn.click()
                time.sleep(2)
        # share_result, _ = self.u2d_helper.assert_icon_exist('xpath',
        #                                                     '//*[@resource-id="com.instagram.android:id/status_text"]',
        #                                                     double_ckeck=False, click=False)
        # if share_result:
        #     t_log.info('分享reels成功')
        # else:
        #     t_log.error('分享reels失败')
        #     raise Exception('分享reels失败')

    def click_search_tab(self):
        """
        点击搜索tab
        """
        self.u2d.xpath('//*[@resource-id="com.instagram.android:id/search_tab"]').click(timeout=1)
        time.sleep(2)

    def click_home_tab(self):
        """
        点击主页tab
        """
        self.u2d.xpath('//*[@resource-id="com.instagram.android:id/feed_tab"]').click(timeout=1)
        time.sleep(2)

    def search_user(self, search_name, friends_name=None):
        """
        搜索用户，search_name和用户的名字可能不一样，大小写敏感。
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.instagram.android:id/search_tab"]', timeout=5)
        self.u2d_helper.click_wait('//*[@resource-id="com.instagram.android:id/action_bar_search_hints_text_layout"]',
                                   timeout=5, pre_wait=1)
        time.sleep(2)
        self.u2d_helper.input_text(search_name)
        time.sleep(2)
        adb.exec_cmd(self.device_id, 'input keyevent 66')

        if friends_name:
            self.u2d_helper.click_wait(f'//*[@text="{friends_name}"]', timeout=10, post_wait=1.5)
        else:
            self.u2d_helper.click_wait(f'//*[@text="{search_name}"]', timeout=10, post_wait=1.5)

        # 断言
        self.u2d_helper.wait_ui_obj('//*[@text="Message"]', timeout=30, raise_on_not_exist=True)

    def enter_user_first_video(self):
        """
        进入用户的第一个视频
        """
        self.u2d_helper.click_wait(
            '//*[contains(@content-desc,"Reel by") or resource-id="com.instagram.android:id/image_button"]', timeout=10,
            pre_wait=1)

        # assert
        self.u2d_helper.wait_ui_obj(
            '//*[@resource-id="com.instagram.android:id/action_bar_title" or @content-desc="Posts"]', timeout=8,
            raise_on_not_exist=True)

    def comment(self, text='test'):
        """
        评论
        """
        # 最多尝试10次查找评论按钮
        for _ in range(10):
            comment = self.u2d.xpath('//*[@content-desc="Comment"]').wait(timeout=2)
            if comment:
                self.u2d.xpath('//*[@content-desc="Comment"]').click()
                time.sleep(1)
                break
            # 轻微上滑继续查找
            self.und_u2.swipe_direction('up', speed=200)
            time.sleep(1)

        # 检查评论是否被限制
        limited_text = self.u2d(text="Comments on this post have been limited.").wait(timeout=2)
        if not limited_text:
            u2utils.input_text(self.u2d, text)
            time.sleep(1)

    def click_reels_tab(self):
        """
        点击Reels tab
        """
        self.u2d.xpath('//*[@resource-id="com.instagram.android:id/clips_tab"]').click(timeout=1)
        time.sleep(2)
