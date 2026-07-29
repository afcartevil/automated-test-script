import time

from tpy_aw.aw_apps.aw_app_camera.aw_app_camera import AwAppCamera, CameraLocator


class CameraOppoLocator(CameraLocator):
    ...


class AwAppCameraOppo(CameraOppoLocator, AwAppCamera):
    aw_nickname = 'OppoCamera'
    variant_key = 'oppo'
    default_app_package = "com.oplus.camera"

    ...

    def check_at_video_mode(self):
        """
        切换到video模式
        """
        self.u2d.shell('am start -a android.media.action.VIDEO_CAPTURE')

    def switch_mode(self,xpath:str):
        """
        切换到ai cam、照片的模式
        """
        self.u2d.shell('am start -a android.media.action.IMAGE_CAPTURE')

    def take_picture_or_video(self):
        """
        照相或录像的按钮
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.oplus.camera:id/shutter_button"]', timeout=4, post_wait=1)

    def enter_previous(self):
        """
        从左下角预览界面进入相册
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.oplus.camera:id/thumbnail"]',pre_wait=1, timeout=5, post_wait=1)

    def wait_and_enter_photo_mode(self, timeout=30, retry_interval=1.0):
        self.click_xpath_with_retry('//*[@resource-id="com.oplus.camera:id/camera_menu_right_enter_button_filter"]', click=False, timeout=timeout, retry_interval=retry_interval)

    def check_at_camera_mode(self):
        """
        切换到照片的模式
        """
        self.u2d_helper.click_wait('//*[@resource-id="com.oplus.camera:id/camera_menu_right_enter_button_filter"]', timeout=4)
        time.sleep(1)

