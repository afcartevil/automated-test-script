import time

from tpy_aw.aw_app_base import AwAppBase


class AwAppScreenRecorder(AwAppBase):
    aw_name = 'ScreenRecorder'
    default_app_package = 'com.transsion.screenrecorder'

    def stop_recording(self):
        self.u2d.xpath('//*[contains(@resource-id, "itemContent") or contains(@content-desc, "seconds")]').click(timeout=2)
        time.sleep(1)
        self.u2d.xpath('//*[contains(@resource-id, "btn_screen_record_pause") or contains(@resource-id, "status_img") or contains(@resource-id, "action2")]').click(timeout=2)
        time.sleep(3)

