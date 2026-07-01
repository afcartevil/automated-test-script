

from tpy_aw.aw_apps.aw_app_camera.aw_app_camera import AwAppCamera


class AwAppCameraVivo(AwAppCamera):
    aw_name = 'Camera'
    variant_key = 'vivo'
    default_app_package = "com.android.camera"
    def enter_video(self):
        if self.u2d.xpath('//*[@text="Agree"]').exists:
            self.u2d.xpath('//*[@text="Agree"]').click_exists(timeout=3)
        self.u2d(description="VideoMode").click_exists(timeout=3)

