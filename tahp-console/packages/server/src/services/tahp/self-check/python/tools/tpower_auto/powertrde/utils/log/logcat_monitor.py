import subprocess
import threading
from datetime import datetime
from powertrde.env import ADB_EXE

class LogcatMonitor:
    def __init__(self):
        self.stop_event = threading.Event()
        self.found_time = None
        self.found_line = None

        self.stop_gc_event = threading.Event()
        self.found_completed = None
        self.found_stopped = None
        self.found_timeout = None

    def get_current_year(self, device_id):
        # 获取设备当前时间的年份
        result = subprocess.run([ADB_EXE, '-s', device_id, 'shell', 'date', '+%Y'], capture_output=True, text=True, encoding='utf-8')
        if result.returncode != 0:
            raise Exception(f"ADB命令执行失败: {result.stderr}")
        current_year = int(result.stdout.strip())
        return current_year

    def get_toast_time(self, device_id, keyword, wait_time=20):
        try:
            self.current_year = self.get_current_year(device_id)

            # 启动一个线程来读取logcat
            logcat_thread = threading.Thread(target=self._read_logcat, args=(device_id, keyword))
            logcat_thread.start()

            # 等待指定时间或直到找到关键字
            logcat_thread.join(timeout=wait_time)

            # 如果线程还在运行，设置停止事件
            if logcat_thread.is_alive():
                # print("超时未找到关键字")
                self.stop_event.set()
                logcat_thread.join()  # 等待线程终止

            return self.found_time, self.found_line
        except Exception as e:
            # print(f"发生错误: {e}")
            return None, None

    def _read_logcat(self, device_id, keyword):
        # print("开始监听logcat")
        # 启动adb logcat命令
        subprocess.run([ADB_EXE, '-s', device_id, 'shell', 'logcat', '-c'], capture_output=True, text=True)

        process = subprocess.Popen([ADB_EXE, '-s', device_id, 'shell', 'logcat', '-v', 'time'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf-8')
        try:
            for line in iter(process.stdout.readline, ''):
                if self.stop_event.is_set():
                    break
                res = [k for k in keyword if k in line]
                if len(res)>0:
                    # print("找到关键字")
                    # 找到关键字，提取时间戳
                    time_str = f"{self.current_year} " + line.split(' ')[0] + ' ' + line.split(' ')[1]
                    log_time = datetime.strptime(time_str, "%Y %m-%d %H:%M:%S.%f")

                    # 将时间转换为UNIX时间戳（毫秒）
                    self.found_time = int(log_time.timestamp() * 1000)
                    self.found_line = line
                    # 停止监控
                    self.stop_event.set()
                    break
        finally:
            # 确保进程被终止
            process.terminate()
            # print("停止监听logcat")

    def exe_gc(self, device_id, wait_time=20):
        try:
            # 启动一个线程来读取logcat
            logcat_thread = threading.Thread(target=self._read_logcat_gc, args=(device_id,))
            logcat_thread.start()

            # 等待指定时间或直到找到关键字
            logcat_thread.join(timeout=wait_time)

            # 如果线程还在运行，设置停止事件
            if logcat_thread.is_alive():
                # print("超时未找到关键字")
                self.stop_gc_event.set()
                logcat_thread.join()  # 等待线程终止

            return self.found_stopped #判断如果为true，表示执行成功
        except Exception as e:
            return None

    def _read_logcat_gc(self, device_id):
        # print("开始监听logcat")
        # 启动adb logcat命令
        subprocess.run([ADB_EXE, '-s', device_id, 'shell', 'logcat', '-c'], capture_output=True, text=True)

        process = subprocess.Popen([ADB_EXE, '-s', device_id, 'shell', 'logcat', '-v', 'time'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True, encoding='utf-8')
        try:
            for line in iter(process.stdout.readline, ''):
                if self.stop_event.is_set():
                    break
                # if
                res = []
                # res = [k for k in keyword if k in line]
                if len(res)>0:
                    # print("找到关键字")
                    # 找到关键字，提取时间戳
                    time_str = f"{self.current_year} " + line.split(' ')[0] + ' ' + line.split(' ')[1]
                    log_time = datetime.strptime(time_str, "%Y %m-%d %H:%M:%S.%f")

                    # 将时间转换为UNIX时间戳（毫秒）
                    self.found_time = int(log_time.timestamp() * 1000)
                    self.found_line = line
                    # 停止监控
                    self.stop_event.set()
                    break
        finally:
            # 确保进程被终止
            process.terminate()
            # print("停止监听logcat")


# # 使用示例
# device_id = '1207125414000521'  # 替换为实际的设备ID
# monitor = LogcatMonitor()
# toast_time, log_line = monitor.get_toast_time(device_id, "Show toast", wait_time=5)
# if toast_time:
#     print(f"找到关键字的时间（毫秒）: {toast_time}")
#     print(f"完整日志行: {log_line}")
# else:
#     print("在指定时间内未找到关键字。")


