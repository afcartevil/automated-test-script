import time

from tpy_aw import U2WatchersCommon
from tpy_aw.aw_app_base import AwAppBase
from tpy_aw.aw_apps.aw_app_snapchat.u2_watchers_snapchat import U2WatchersSnapchat


class AwAppSnapchat(AwAppBase):
    aw_name = 'Snapchat'
    default_app_package = 'com.snapchat.android'

    def click_camera_tab(self):
        """
        点击相机tab (如果已在相机tab，则不做任何操作)
        """
        camera = self.u2d.xpath('//*[@resource-id="com.snapchat.android:id/camera_capture_button" or @content-desc="Camera Capture"]').wait(timeout=2)
        if not camera:
            self.u2d.xpath('//*[@resource-id="com.snapchat.android:id/ngs_camera_icon_container" or @text="Camera"]').click()
            time.sleep(1)

    def click_chat_tab(self):
        """
        点击聊天tab
        """
        self.u2d.xpath('//*[@resource-id="com.snapchat.android:id/ngs_chat_icon_container" or @text="Chat"]').click(
            timeout=2)
        time.sleep(2)

    def take_photo(self):
        """
        拍照
        """
        with self.u2_apply_watchers(watchers=[U2WatchersSnapchat.snapchat_skip_btn, U2WatchersCommon.common_allow_button, U2WatchersSnapchat.snapchat_location_btn]):
            self.click_camera_tab()
            self.u2d.xpath('//*[@resource-id="com.snapchat.android:id/camera_capture_button" or @content-desc="Camera Capture"]').click()
            time.sleep(2)

    def send_photo_to_stories(self):
        """
        发送照片到故事
        """
        with self.u2_apply_watchers(
                watchers=[U2WatchersSnapchat.snapchat_skip_btn, U2WatchersSnapchat.snapchat_location_btn]):
            self.u2d.xpath('//*[@text="Stories" or @text="Story"]').click()
            time.sleep(2)
        add = self.u2d.xpath('//*[@text="Add"]').wait(timeout=2)
        if add:
            self.u2d.xpath('//*[@text="Add"]').click()
            time.sleep(2)

    def enter_chat_box(self, chat_name=None):
        """
        点击聊天框
        """
        if chat_name:
            self.und_u2.click_match_text(chat_name, target_score=0.9)
        else:
            # 进第一个联系人
            self.u2d.xpath('//androidx.recyclerview.widget.RecyclerView/android.widget.FrameLayout[2]').click(timeout=2)
        with self.u2_apply_watchers(watchers=[U2WatchersSnapchat.snapchat_okay_btn]):
            time.sleep(3)
