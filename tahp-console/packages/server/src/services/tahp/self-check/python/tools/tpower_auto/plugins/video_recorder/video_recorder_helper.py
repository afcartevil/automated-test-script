import os
import time
from typing import Optional

from powertrde.env import TOOLS_DIR
from powertrde.utils import misc_utils


class VideoRecorderHelper:
    _instance = None

    def __init__(self):
        super().__init__()
        self.last_save_dir = os.getcwd()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def force_kill_running_recording(self):
        for p in misc_utils.search_all_running_process('video_recorder.exe'):
            p.terminate()

    @property
    def is_recording(self):
        return misc_utils.is_process_running('video_recorder.exe')

    def update_record(self, record_duration_in_second: float, change_save_dir: Optional[str] = None):
        if change_save_dir:
            self.last_save_dir = change_save_dir

        misc_utils.run_command_detached(
            f"start /min cmd /c {os.path.join(TOOLS_DIR, 'video_recorder.exe')} {self.last_save_dir} {record_duration_in_second}",
            shell=True)

    def stop_record(self, wait_for_stop=False, force_stop=False):
        if self.is_recording:
            if force_stop:
                self.force_kill_running_recording()
                return
            misc_utils.run_command_detached(
                f"start /min cmd /c {os.path.join(TOOLS_DIR, 'video_recorder.exe')} stop 1",
                shell=True)
            if wait_for_stop:
                for i in range(30):
                    time.sleep(0.5)
                    if not self.is_recording:
                        break
                else:
                    self.force_kill_running_recording()
