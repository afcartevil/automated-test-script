import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase
from deprecated import deprecated


class CameraLocator(U2SelectorLocator):
    btn_shutter = U2Selector().xpath('//*[@resource-id="com.transsion.camera:id/shutter_button"]').bind()  # 拍摄按钮
    btn_switcher = U2Selector().xpath('//*[@resource-id="com.transsion.camera:id/btn_shutter_panel_camera_switcher"]').bind()  # 前后置切换
    thumbnail_shutter = U2Selector().xpath('//*[@resource-id="com.transsion.camera:id/previous_shutter_panel_thumbnail"]').bind()  # 左下角的缩略图


class AwAppCamera(CameraLocator, AwAppBase):
    aw_name = 'Camera'
    default_app_package = 'com.transsion.camera'

    def check_at_front_or_rear_camera(self, choose: str):
        """
        @param choose: front 前置摄像头，rear 后置
        检查是否在前置/后置摄像头，没有则直接翻转
        """
        assert choose in ('front', 'rear')

        rear_result = self.u2d.xpath('//*[@resource-id="com.transsion.camera:id/full_zoom_view" or @resource-id="com.transsion.camera:id/zoom_item_container" or @resource-id="com.transsion.camera:id/zoom_point_bar"]')
        if rear_result.exists and choose=="rear":
            t_log.debug('已在后置摄像头')
        elif not rear_result.exists and choose=="front":
            t_log.debug('已在前置摄像头')
        else:
            self.u2d_helper.click_wait('//*[@resource-id="com.transsion.camera:id/btn_shutter_panel_camera_switcher"]', timeout=4)
            time.sleep(1)

    def check_at_camera_mode(self):
        """
        切换到ai cam、照片的模式
        """
        self.u2d_helper.click_wait('//*[@text="AI CAM"]', timeout=4)
        time.sleep(1)

    def switch_mode(self,xpath:str):
        """
        切换到ai cam、照片的模式
        """
        self.u2d_helper.click_exists(xpath, timeout=30)
        time.sleep(1)

    def check_at_video_mode(self):
        """
        切换到video模式
        """
        self.u2d_helper.click_wait('//*[@text="VIDEO" or @text="Video"]', timeout=10)
        time.sleep(2)

    def take_picture_or_video(self):
        """
        照相或录像的按钮
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.transsion.camera:id/shutter_button"]', timeout=4, post_wait=1)

    def end_take_video(self):
        """
        结束录制视频
        """
        recording_time_result, _ = self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.transsion.camera:id/recording_time_group"]')
        if recording_time_result:
            self.u2d_helper.assert_icon_exist('xpath', '//*[@resource-id="com.transsion.camera:id/shutter_button"]', click=True)
        else:
            t_log.error('录制视频失败')
            raise XPathElementNotFoundError('录制视频失败')
        time.sleep(1)

    @deprecated('建议使用check_at_video_mode')
    def enter_video(self):
        self.und_u2.swipe_direction('right')

    def enter_previous(self):
        """
        从左下角预览界面进入相册
        """
        if not self.u2d.xpath('//*[@resource-id="com.transsion.camera:id/previous_shutter_panel_thumbnail"]').exists:
            self.u2d.click(0.50, 0.50)
            time.sleep(1)
        self.u2d_helper.click_wait('//*[@resource-id="com.transsion.camera:id/previous_shutter_panel_thumbnail"]', pre_wait=1, timeout=5, post_wait=1)

    def delete_latest(self):
        """
        删除相册最新的内容
        """
        if not self.u2d.xpath('//*[@text="Delete"]').exists:
            self.u2d.click(0.50, 0.50)
            time.sleep(1)

        self.u2d_helper.click_wait('//*[@text="Delete"]', pre_wait=1, timeout=5, post_wait=1)
        self.u2d_helper.click_wait('//*[@text="Delete" or @resource-id="com.gallery20:id/btn_positive"]', pre_wait=1, timeout=5, post_wait=1)
        time.sleep(1)

    def play_and_pause(self,duration:int = 10):
        self.u2d.shell('input keyevent 27')
        time.sleep(duration)
        self.u2d.shell('input keyevent 27')
        time.sleep(3)

    def wait_and_enter_photo_mode(self, timeout=30, retry_interval=1.0):
        self.click_xpath_with_retry('//*[@text="AI CAM" or @text="Photo" or @content-desc="PhotoMode"]', click=False, timeout=timeout, retry_interval=retry_interval)
