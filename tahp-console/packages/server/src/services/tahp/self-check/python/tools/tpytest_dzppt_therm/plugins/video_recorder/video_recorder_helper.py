import os
import time
from typing import Optional

from powertrde import env
from powertrde.env import TOOLS_DIR
from powertrde.framework.tran_logger import t_log
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

    def _force_kill_running_recording(self):
        for p in misc_utils.search_all_running_process('video_recorder.exe'):
            p.terminate()

    @property
    def is_recording(self):
        return misc_utils.is_process_running('video_recorder.exe')

    def update_record_from_server(self, record_duration_in_second: float, change_save_dir: Optional[str] = None):
        t_log.info(
            f'VideoRecorderHelper 执行一次 update_record_from_server: record_duration_in_second:{record_duration_in_second}, change_save_dir:{change_save_dir}')
        if not env.is_run_on_windows():
            # 如果非Windows，直接不生效
            return

        if change_save_dir:
            self.last_save_dir = change_save_dir

        misc_utils.run_command_detached(
            f"start /min cmd /c {os.path.join(TOOLS_DIR, 'video_recorder.exe')} {self.last_save_dir} {record_duration_in_second}",
            shell=True)

    def update_record(self, record_duration_in_second: float, change_save_dir: Optional[str] = None):
        # 不再支持由测试端直接调起，改由video服务器控制
        pass
        # t_log.info(f'VideoRecorderHelper 执行一次 update_record: record_duration_in_second:{record_duration_in_second}, change_save_dir:{change_save_dir}')
        # if not env.is_run_on_windows():
        #     # 如果非Windows，直接不生效
        #     return
        #
        # if self.is_recording and not self.lock_video_recorder_use():
        #     # 如果摄像头正在被使用，但是不是被当前进程所使用时，则直接忽略
        #     return
        # else:
        #     # 独占摄像头使用资源
        #     self.force_lock_video_recorder_use()
        #
        # if change_save_dir:
        #     self.last_save_dir = change_save_dir
        #
        # misc_utils.run_command_detached(
        #     f"start /min cmd /c {os.path.join(TOOLS_DIR, 'video_recorder.exe')} {self.last_save_dir} {record_duration_in_second}",
        #     shell=True)

    def stop_record_from_server(self, wait_for_stop=False, force_stop=False):
        if not env.is_run_on_windows():
            # 如果非Windows，直接不生效
            return

        if self.is_recording:
            if force_stop:
                self._force_kill_running_recording()
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
                    self._force_kill_running_recording()

    def stop_record(self, wait_for_stop=False, force_stop=False):
        # 不再生效：不再支持由测试端调起
        pass
        # if not env.is_run_on_windows():
        #     # 如果非Windows，直接不生效
        #     return
        #
        # if self.is_recording and self.unlock_video_recorder_use():
        #     if force_stop:
        #         self._force_kill_running_recording()
        #         return
        #     misc_utils.run_command_detached(
        #         f"start /min cmd /c {os.path.join(TOOLS_DIR, 'video_recorder.exe')} stop 1",
        #         shell=True)
        #     if wait_for_stop:
        #         for i in range(30):
        #             time.sleep(0.5)
        #             if not self.is_recording:
        #                 break
        #         else:
        #             self._force_kill_running_recording()

    # def is_locked_video_recorder_use(self):
    #     return env.get_lazy_shared_pool().is_resource_owned_by_group("video_recorder")
    #
    # def lock_video_recorder_use(self):
    #     return env.get_lazy_shared_pool().acquire_resource("video_recorder", timeout=0)
    #
    # def force_lock_video_recorder_use(self):
    #     return env.get_lazy_shared_pool().force_acquire_resource("video_recorder", timeout=3)
    #
    # def unlock_video_recorder_use(self):
    #     return env.get_lazy_shared_pool().release_resource("video_recorder")

    def split_video(self):
        """
        主动触发视频分割。
        通过向共享内存写入分割标志，让正在运行的录像进程立即分割当前视频文件。

        Returns:
            bool: 如果当前正在录像并成功发送分割信号，返回 True；否则返回 False
        """
        if not env.is_run_on_windows():
            t_log.warning('非 Windows 系统，视频分割功能不可用')
            return False

        try:
            import mmap
            size = 1024
            shm = mmap.mmap(-1, size, tagname='transsion_video_shared_memory')

            # 在位置 500 写入分割标志 '1'
            shm.seek(500)
            shm.write(b'1')
            shm.close()

            t_log.info('已发送视频分割指令')
            return True
        except FileNotFoundError:
            t_log.warning('当前没有录像进程运行，无法执行分割操作（共享内存不存在）')
            return False
        except Exception as e:
            t_log.error(f'发送视频分割指令失败: {e}')
            return False

    def check_camera_hardware(self) -> bool:
        """检查摄像头硬件是否连接

        Returns:
            bool: True=摄像头在线, False=未检测到摄像头
        """
        if not env.is_run_on_windows():
            # 非Windows环境默认返回True(避免误判)
            return True

        try:
            # 策略1: 使用 pnputil (更稳健,无PowerShell依赖)
            # 命令: pnputil /enum-devices /class Camera /connected
            # 如果有设备，会输出详细信息；如果没有，通常输出很少或提示未找到
            import subprocess
            cmd = "pnputil /enum-devices /class Camera /connected"

            # 由于输出包含中文字符,需要尝试不同的编码解码
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, check=False)
                # 尝试用系统默认编码解码(gbk)
                output = result.stdout.decode('gbk', errors='ignore') + result.stderr.decode('gbk', errors='ignore')
            except Exception:
                # 回退到utf-8
                output = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""

            # 检查关键特征
            # 1. '/class Camera' 确保是摄像头类
            # 2. 'Instance ID' 或 '实例 ID' 表示有具体的设备条目
            # 3. 'Status: Started' 或 '状态: 已启动' 表示设备正常

            # 简单判断: 只要有 "Instance ID" 或 "实例 ID"，且不是空列表，就认为有设备
            if "Instance ID" in output or "实例 ID" in output:
                return True

            # 策略2: 如果 pnputil 失败，尝试 opencv (可能会有副作用，仅作保底)
            # import cv2
            # cap = cv2.VideoCapture(0)
            # if cap.isOpened():
            #     cap.release()
            #     return True

            return False

        except Exception as e:
            t_log.warning(f"摄像头硬件检测失败: {e}")
            return False


if __name__ == '__main__':
    # for i in range(100):
    #     VideoRecorderHelper.get_instance().update_record(100, f"E:\Desktop\logs")
    #     time.sleep(10)

    helper = VideoRecorderHelper.get_instance()
    # helper.update_record(3600, r"E:\Desktop\logs")
    # print("录像已启动...")
    #
    # # 等待 10 秒后主动分割视频
    # time.sleep(10)
    print("执行第 1 次主动分割...")
    helper.split_video()

    # 再等待 10 秒后再次分割
    time.sleep(10)
    print("执行第 2 次主动分割...")
    helper.split_video()
    #
    # 继续录像
    time.sleep(20)
    print("停止录像...")
    helper.stop_record_from_server()

