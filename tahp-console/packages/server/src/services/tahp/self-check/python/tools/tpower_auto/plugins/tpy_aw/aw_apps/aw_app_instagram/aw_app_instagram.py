import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from tpy_aw.aw_app_base import AwAppBase
from tpy_aw.aw_apps.aw_app_instagram.u2_watchers_instagram import U2WatchersInstagram


class AwAppInstagram(AwAppBase):
    aw_name = 'Instagram'
    default_app_package = 'com.instagram.android'

    def check_at_homepage(self):
        result, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.instagram.android:id/feed_tab"]', click=True)
        if result:
            t_log.debug('已在Instagram主页')
        else:
            raise XPathElementNotFoundError('未在Instagram主页')
        time.sleep(2)

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

    def switch_to_shortvideo_page(self):
        self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.instagram.android:id/clips_tab"]', click=True)
        time.sleep(2)

    def switch_to_creation_page(self):
        """
        点到post的reels里
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.instagram.android:id/creation_tab"]', timeout=5)
        with self.u2_apply_watchers(names=["common_allow_all_button", "common_while_using_app_button", "instagram_turn_on_button", "common_ok_button"]):
            # REEL
            self.u2d_helper.click_wait('//*[@resource-id="com.instagram.android:id/cam_dest_clips"]', timeout=15)

    def open_camera_in_reel_page(self):
        """
        点击左上角的相机图标
        """
        self.u2d_helper.click_wait('//*[@content-desc="Open camera" or @content-desc="Camera" or @text="Start new video"]', timeout=5)

    def record_video_in_reel_page(self, record_time):
        result, record_btn = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.instagram.android:id/camera_shutter_button_container"]', click=False)
        record_btn.long_click(duration=int(record_time))
        time.sleep(2)

    def long_click_camera(self, hold_time=30):
        """
        长按录制时间
        @param hold_time: 长按时间(s)
        """
        x, y = self.u2d_helper.get_bounds_corner(
            '//*[@resource-id="com.instagram.android:id/camera_shutter_button_container"]', 'center')
        self.u2d.long_click(x, y, hold_time)

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
