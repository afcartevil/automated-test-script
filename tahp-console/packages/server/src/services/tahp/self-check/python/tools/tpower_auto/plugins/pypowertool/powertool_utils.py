import os
import subprocess
import tempfile
import threading
import time
import pandas as pd
import re
from powertrde.env import TOOLS_DIR
import psutil

POWERTOOL_CMD_EXE = os.path.join(TOOLS_DIR, 'powertool', 'PowerToolCmd.exe')
POWERTOOL_EXE = os.path.join(TOOLS_DIR, 'powertool', 'PowerTool.exe')
PT5READER_EXE = os.path.join(TOOLS_DIR, 'powertool', 'Pt5Reader.exe')
TEMP_RECORD_DIR = os.path.join(tempfile.gettempdir(), 'powertool_record')
PT_DIR = os.path.join(TEMP_RECORD_DIR, 'pt')
if not os.path.exists(PT_DIR):
    os.makedirs(PT_DIR)
SAVE_FILE_PATH = os.path.join(PT_DIR, "DEFAULT.pt5")


class PowerToolManager:
    _default_instance = None

    @classmethod
    def get_default_instance(cls):
        if not cls._default_instance:
            cls._default_instance = cls()
        return cls._default_instance

    def __init__(self, file_path=SAVE_FILE_PATH):
        """
            file_path：传入长时间采集生产.pt5文件的绝对路径，如需调用其他方法则为默认
        """
        self.powertool_process = None
        self.powertool_thread = None
        self.file_path = file_path
        self.monitor_thread = None
        self.stop_monitor = False

    def _start_powertoolcmd(self, vout=4.2):
        def run_process():
            cmd = [POWERTOOL_CMD_EXE, f"/TEMPDIR={os.path.dirname(self.file_path)}", f"/VOUT={vout}", "/ISTART",
                   f"/SAVEFILE={os.path.basename(self.file_path)}", "/KEEPPOWER", "/USBPASSTHROUGH=OFF",
                    "/StartCurrentLim=8", "/RunCurrentLim=8","/NOEXITWAIT", "/trigger=ATA"]
            try:
                self.powertool_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.powertool_process.wait()
            except Exception as e:
                print(f"Error running PowerToolCmd: {e}")

        self.powertool_thread = threading.Thread(target=run_process)
        self.powertool_thread.daemon = True
        self.powertool_thread.start()
        time.sleep(1)

    def set_enable_usb_link(self, is_enable=True, vout=4.2):
        usb_pass_through = 'ON' if is_enable else 'OFF'

        def usb_link():
            cmd = [POWERTOOL_CMD_EXE, "/trigger=ATC1", f"/TEMPDIR={os.path.dirname(self.file_path)}",
                   "/SAVEFILE=temp.pt5", f"/VOUT={vout}", "/StartCurrentLim=8",
                   "/RunCurrentLim=8", f"/USBPASSTHROUGH={usb_pass_through}", "/KEEPPOWER", "/NOEXITWAIT"]
            try:
                self.powertool_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.powertool_process.wait()
            except Exception as e:
                print(f"Error running enable_usb_link: {e}")

            try:
                self.powertool_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.powertool_process.wait()
            except Exception as e:
                print(f"Error running enable_usb_link: {e}")

        if self.status():
            self.powertoolcmd_stop(vout=vout)

        usb_link()
        temp_file_path = os.path.join(os.path.dirname(self.file_path), 'temp.pt5')
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


    def set_enable_powermonitor_link(self, is_enable=True, vout=4.2):
        def enable_link():
            cmd = [POWERTOOL_CMD_EXE, "/trigger=ATC1", f"/TEMPDIR={os.path.dirname(self.file_path)}",
                   f"/SAVEFILE=temp.pt5", f"/VOUT={vout}", "/StartCurrentLim=8",
                   "/RunCurrentLim=8", "/USBPASSTHROUGH=OFF", "/KEEPPOWER", "/NOEXITWAIT"]
            # sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='gb2312')
            try:
                self.powertool_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.powertool_process.wait()
            except Exception as e:
                print(f"Error running enable_usb_link: {e}")

        def disable_link():
            cmd = [POWERTOOL_CMD_EXE, "/trigger=ATC1", f"/TEMPDIR={os.path.dirname(self.file_path)}",
                   "/SAVEFILE=temp.pt5", f"/VOUT={vout}", "/USBPASSTHROUGH=OFF", "/NOEXITWAIT"]
            try:
                self.powertool_process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                self.powertool_process.wait()
            except Exception as e:
                print(f"Error running disable_usb_link: {e}")

        if self.status():
            self.powertoolcmd_stop(vout=vout)

        if is_enable:
            enable_link()
        else:
            disable_link()
        temp_file_path = os.path.join(os.path.dirname(self.file_path), 'temp.pt5')
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


    def _kill_powertoolcmd(self):
        try:
            os.system('taskkill /F /IM PowerTool.exe >nul 2>nul')
            os.system('taskkill /F /IM PowerToolCmd.exe >nul 2>nul')
            print("PowerToolCmd process terminated successfully")
        except Exception as e:
            print(f"Error terminating PowerToolCmd: {e}")

        if self.powertool_thread and self.powertool_thread.is_alive():
            self.powertool_thread.join(timeout=2)

        self.powertool_process = None
        self.powertool_thread = None

    def _is_powertoolcmd_running(self):
        try:
            result = subprocess.run('tasklist | findstr "PowerToolCmd.exe"', shell=True,
                                    capture_output=True, text=True)
            return 'PowerToolCmd.exe' in result.stdout
        except Exception as e:
            print(f"Error checking PowerToolCmd status: {e}")
            return False

    def powertoolcmd_start(self):
        if self._is_powertoolcmd_running():
            print("Fail! PowerToolCmd is open")
            return False
        return self._start_powertoolcmd(4.2)

    def powertoolcmd_stop(self, link_usb_after_stop=False, vout=4.2):
        try:
            self._kill_powertoolcmd()
            if self._is_powertoolcmd_running():
                return False
            else:
                print(f"Success! PowerToolCmd is down")
                return True
        finally:
            if link_usb_after_stop:
                self.set_enable_usb_link(is_enable=True, vout=vout)

    def status(self):
        return True if self._is_powertoolcmd_running() else False

    def start_monitoring(self, log_file_path):
        self.monitor_thread = threading.Thread(target=self.monitor_file_size, args=(log_file_path,))
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def monitor_file_size(self, log_file_path):
        previous_size = -1
        while not self.stop_monitor:
            if os.path.exists(self.file_path):
                current_size = int(os.path.getsize(self.file_path) / 1024)  # KB
                self.log_system_status(log_file_path)
                self.log_powertoolcmd_status(log_file_path)
                print(f"current_size: {current_size} KB, previous_size: {previous_size} KB")
                if current_size == previous_size:
                    print("File size hasn't changed. Possible issue detected.")
                    break
                previous_size = current_size
            time.sleep(60)  # 每分钟检查一次文件大小

    def log_system_status(self, log_file_path):
        with open(log_file_path, "a") as file:
            # 获取系统内存状态
            memory_info = psutil.virtual_memory()
            file.write("Memory Information:\n")
            file.write(f"  Total: {memory_info.total / (1024 ** 3):.2f} GB\n")
            file.write(f"  Available: {memory_info.available / (1024 ** 3):.2f} GB\n")
            file.write(f"  Used: {memory_info.used / (1024 ** 3):.2f} GB\n")
            file.write(f"  Percentage: {memory_info.percent}%\n")

            # 获取系统CPU状态
            cpu_percent_total = psutil.cpu_percent(interval=0.1)
            file.write(f"Total CPU Usage: {cpu_percent_total}%\n")

    def log_powertoolcmd_status(self, log_file_path):
        with open(log_file_path, "a") as file:
            try:
                result = subprocess.run(
                    'wmic process where "name=\'PowerToolCmd.exe\'" get ProcessId,WorkingSetSize,CommandLine',
                    shell=True, capture_output=True, text=True
                )
                file.write("PowerToolCmd Process Information:\n")
                file.write(result.stdout)
            except Exception as e:
                file.write(f"Error retrieving PowerToolCmd status: {e}\n")

    def stop_monitoring(self):
        self.stop_monitor = True
        if self.monitor_thread:
            self.monitor_thread.join()

    @staticmethod
    def data_avg(df):
        return df['电流'].mean()

    def case_avg(self, df, start_index, end_index):
        case_df = df[(df['序号'] >= start_index) & (df['序号'] < end_index)]
        return self.data_avg(case_df)

    def read_all_data(self):
        # df保存到指定路径下，避免重复解析.pt5
        output_file = os.path.join(TOOLS_DIR, 'powertool', os.path.basename(self.file_path))
        with open(output_file, "w") as file:
            process = subprocess.Popen([PT5READER_EXE, self.file_path], stdout=file, stderr=subprocess.STDOUT)
            process.wait()
        with open(output_file, 'r') as file:
            lines = file.readlines()
        pattern = r'#(\d+)\s+([\d.]+)\s+sec\s+MAIN:\s+([\d.]+)\s+mA\s+([\d.]+)\s+V'
        extracted_data = list()
        for line in lines:
            match = re.match(pattern, line.strip())
            if match:
                index, t, current, voltage = match.groups()
                extracted_data.append((int(index), float(t), float(current)))
        df = pd.DataFrame(extracted_data, columns=['序号', '时间', '电流'])
        os.remove(output_file)
        # df.to_csv(r'C:\Users\song.zhou\Desktop\df.csv', index=False)
        return df

    def case_index(self):
        pass

    def check_powertoolcmd(self):
        pass
