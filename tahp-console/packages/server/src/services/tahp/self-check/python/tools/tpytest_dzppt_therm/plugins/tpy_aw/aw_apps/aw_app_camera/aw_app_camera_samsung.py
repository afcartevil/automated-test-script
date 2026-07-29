from tpy_aw.aw_apps.aw_app_camera.aw_app_camera import AwAppCamera, CameraLocator
import time
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.framework.tran_logger import t_log
from uiautomator2 import XPathElementNotFoundError


class CameraSamsungLocator(CameraLocator):
    btn_shutter = U2Selector().xpath('//*[@resource-id="com.sec.android.app.camera:id/shutter_container" or @resource-id="com.sec.android.app.camera:id/shutter_circle_stroke"]').bind()  # 拍摄或者录像按钮
    btn_switcher = U2Selector().xpath('//*[@resource-id="com.sec.android.app.camera:id/switch_camera" or @content-desc="switch camera button"]').bind()  # 前后置切换
    thumbnail_shutter = U2Selector().xpath('//*[@resource-id="com.sec.android.app.camera:id/photo_album" or @content-desc="camera thumbnail button"]').bind()  # 左下角的缩略图


class AwAppCameraSamsung(CameraSamsungLocator, AwAppCamera):
    aw_name = 'Camera'
    variant_key = 'Samsung'
    default_app_package = "com.sec.android.app.camera"

    def enter_video(self):
        if self.u2d.xpath('//*[@text="Agree"]').exists:
            self.u2d.xpath('//*[@text="Agree"]').click_exists(timeout=3)
        self.u2d(description="Video").click_exists(timeout=3)

    def check_at_front_or_rear_camera(self, choose: str):
        """
            @param choose: front 前置摄像头，rear 后置
            检查是否在前置/后置摄像头，没有则直接翻转
        """
        assert choose in ('front', 'rear')

        rear_result = self.u2d.xpath('//*[@content-desc="PHOTO_RESOLUTION"]')
        if rear_result.exists and choose == "rear":
            t_log.debug('已在后置摄像头')
        elif not rear_result.exists and choose == "front":
            t_log.debug('已在前置摄像头')
        else:
            self.btn_switcher.click()
            time.sleep(1)

    def check_at_camera_mode(self):
        """
            切换到ai cam、照片的模式
        """
        if self.u2d.xpath('//*[@text="AI CAM"]').exists:
            self.u2d_helper.click_wait('//*[@text="AI CAM"]', timeout=4)
            time.sleep(1)
        else:
            t_log.warning("未发现ai cam模式！")

    def check_at_video_mode(self):
        """
            切换到video模式
        """
        self.u2d_helper.click_wait('//*[@text="VIDEO"]', timeout=4)
        time.sleep(2)

    def take_picture_or_video(self):
        """
            照相或录像的按钮
        """
        self.btn_shutter.click(timeout=4)

    def end_take_video(self):
        """
            结束录制视频
        """
        recording_time_result, _ = self.u2d_helper.assert_icon_exist('xpath',
                                                                     '//*[@resource-id="com.sec.android.app.camera:id/record_tip_time"]')
        if recording_time_result:
            self.u2d_helper.assert_icon_exist('xpath',
                                              '//*[@resource-id="com.sec.android.app.camera:id/video_stop"]',
                                              click=True)
        else:
            t_log.error('录制视频失败')
            raise XPathElementNotFoundError('录制视频失败')

    def play_and_pause(self,duration:int = 10):
        width, height = self.u2d.window_size()
        t_log.debug(f'window size: {width}x{height}')
        self.u2d.click(0.5,0.83)
        time.sleep(duration)
        self.u2d.click(0.5,0.83)
        time.sleep(3)
