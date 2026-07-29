from powertrde.utils.trde import adb
from tpy_aw.aw_helpers.aw_helper_vivo.aw_helper_vivo import AwHelperVivo


class AwHelperVivoOrigin(AwHelperVivo):
    aw_name = 'vivo'
    variant_key = 'origin'

    def set_all_volume_level(self, level: int):
        self.set_call_volume_level(level)
        self.set_ring_volume_level(level)
        self.set_media_volume_level(level)
        self.u2d.sleep(3)
        # VIVO需要重启才能恢复
        self.reboot_and_wait_complete()
        self.u2d.sleep(3)
        self.screen_on_and_unlock()

    def set_call_volume_level(self, level: int):
        adb.exec_cmd(self.device_id, f'settings put system volume_voice_speaker {level}')

    def set_ring_volume_level(self, level: int):
        adb.exec_cmd(self.device_id, f'settings put system volume_ring_bt_a2dp {level}')
        adb.exec_cmd(self.device_id, f'settings put system volume_ring_bt_a2dp_hp {level}')
        adb.exec_cmd(self.device_id, f'settings put system volume_ring_headphone {level}')
        adb.exec_cmd(self.device_id, f'settings put system volume_ring_headset {level}')
        adb.exec_cmd(self.device_id, f'settings put system volume_ring_speaker {level}')

    def set_media_volume_level(self, level: int):
        adb.exec_cmd(self.device_id, f'settings put system volume_music_speaker {level}')