import time

from powertrde.utils.trde import adb
from tpy_aw.aw_apps.aw_app_desimu.aw_app_desimu import AwAppDesimu
from tpy_aw.aw_helpers.aw_helper_vivo.aw_helper_vivo import AwHelperVivo


class AwHelperVivoFuntouch(AwHelperVivo):
    aw_name = 'vivo'
    variant_key = 'funtouch'

    def set_all_volume_level(self, level: int):
        self.set_media_volume_level(level)
        self.set_call_volume_level(level)
        self.set_ring_volume_level(level)
        self.reboot_and_wait_complete()

    def set_media_volume_level(self, level: int):
        adb.exec_cmd(self.device_id, f'settings put system volume_music_remote_submix {level}')
        adb.exec_cmd(self.device_id, f'settings put system volume_music_speaker {level}')
        adb.exec_cmd(self.device_id, f'settings put system volume_music {level}')


    def set_call_volume_level(self,  level: int):
        adb.exec_cmd(self.device_id, f'settings put system volume_voice {level}')
        adb.exec_cmd(self.device_id, f'settings put system volume_voice_speaker {level}')


    def set_ring_volume_level(self, level: int):
        adb.exec_cmd(self.device_id, f'settings put system volume_ring_headset {level}')
        adb.exec_cmd(self.device_id, f'settings put system volume_ring_speaker {level}')
        adb.exec_cmd(self.device_id, f'settings put system volume_ring {level}')


    def insert_sms(self, count=1):
        aw_desimu:AwAppDesimu = self.get_casted_app_aw(AwAppDesimu)
        self.grant_manage_external_storage(aw_desimu.app_package)
        aw_desimu.enter_app()
        aw_desimu.set_user_data(message_count=count)

    def reboot_and_wait_complete(self, execute_reboot=True):
        if execute_reboot:
            adb.reboot_phone(self.device_id)
            time.sleep(10)
        try:
            adb.DISABLE_ADB_ERROR_OUTPUT = True
            for i in range(120):
                time.sleep(1)
                if adb.is_boot_completed(self.device_id):
                    time.sleep(5)
                    break
            else:
                raise Exception('Failed to complete the reboot within 120 seconds!')
        finally:
            adb.DISABLE_ADB_ERROR_OUTPUT = False