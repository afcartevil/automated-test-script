import time

from uiautomator2 import XPathElementNotFoundError

from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends.u2_selector_locator import U2SelectorLocator
from tpy_aw.aw_app_base import AwAppBase
from deprecated import deprecated
class CameraLocator(U2SelectorLocator):
    ...


class AwAppCamera(AwAppBase):
    aw_name = 'Camera'
    default_app_package = 'com.transsion.camera'

    def check_at_front_or_rear_camera(self, choose:str):
        """
        @param choose: front 前置摄像头，rear 后置
        检查是否在前置/后置摄像头，没有则直接翻转
        """
        assert choose in ('front', 'rear')

        rear_result = self.u2d.xpath('//*[@resource-id="com.transsion.camera:id/full_zoom_view" or @resource-id="com.transsion.camera:id/zoom_item_container"]')
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

    def check_at_video_mode(self):
        """
        切换到video模式
        """
        self.u2d_helper.click_wait('//*[@text="VIDEO" or @text="Video"]', timeout=4)
        time.sleep(2)

    def take_picture_or_video(self):
        """
        照相或录像的按钮
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.transsion.camera:id/shutter_button"]', timeout=4)

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

    @deprecated('建议使用check_at_video_mode')
    def enter_video(self):
        self.und_u2.swipe_direction('right')
