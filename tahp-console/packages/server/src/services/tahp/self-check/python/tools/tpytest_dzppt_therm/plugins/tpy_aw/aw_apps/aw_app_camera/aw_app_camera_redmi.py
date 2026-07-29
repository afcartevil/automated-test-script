from tpy_aw.aw_apps.aw_app_camera.aw_app_camera import AwAppCamera, CameraLocator
import time
from powertrde.utils.u2_extends.u2_selector import U2Selector
from powertrde.framework.tran_logger import t_log
from uiautomator2 import XPathElementNotFoundError


class CameraRedmiLocator(CameraLocator):
    ...

class AwAppCameraVivo(CameraRedmiLocator, AwAppCamera):
    aw_name = 'Camera'
    variant_key = 'redmi'
    default_app_package = "com.android.camera"

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