import os
import threading
import time

from powertrde.utils.trde.trde_utils import OUTPUT_DIR, ADB_EXE


class DeviceLogMonitor:
    # start only one time, store in context
    def __init__(self, device_id, adb_shell_cmd):
        self.device_id = device_id
        self.adb_shell_cmd = adb_shell_cmd
        self._parse_func = None
        self._reconnect_flag = False

        self._temp_lines = []
        self._output_log_file_name = ''
        self._sub_dir = ''

        self._thread = threading.Thread(target=self._thread_func)
        self._thread.setDaemon(True)
        self._thread.start()

    def set_reconnect_flag(self):
        self._reconnect_flag = True

    def _connect_logcat(self):
        cmd = f'{ADB_EXE} -s {self.device_id} shell {self.adb_shell_cmd}'
        f = os.popen(cmd)
        return f

    def _thread_func(self):
        f = self._connect_logcat()
        while 1:
            if self._reconnect_flag:
                from .logs import log
                log('-' * 20 + f'{self.device_id}, reconnect pc')
                self._save_line('-' * 20 + 'reconnect pc', flush=True)
                self._reconnect_flag = False
                f = self._connect_logcat()

            line = f.readline()
            if not self._parse_func:
                time.sleep(0.1)
                continue
            if not line or not line.strip():
                continue

            self._save_line(line)
            self._parse_func(line)

    # monitor in test_case
    def monitor(self, func_parse_line, output_dir=''):
        self._sub_dir = output_dir
        self.flush()
        self._output_log_file_name = ''
        self._parse_func = func_parse_line

    def save_info(self, info):
        self._save_line(str(info), True)

    def _get_output_file(self):
        if not self._output_log_file_name:
            d = self._sub_dir if self._sub_dir else OUTPUT_DIR
            from . import trde_utils
            self._output_log_file_name = os.path.join(
                d,
                trde_utils.file_name_transform(f'monitor_{self.device_id}_{trde_utils.cur_date_time_string_key()}.txt'))
        return self._output_log_file_name

    def _save_line(self, line, flush=False):
        if not line or not line.strip():
            return

        if not line.endswith('\n'):
            line += '\n'

        from . import trde_utils
        line = trde_utils.cur_date_time_string() + ' ' + line
        self._temp_lines.append(line)

        if len(self._temp_lines) > 200 or flush:
            self.flush()

    def flush(self):
        if not self._temp_lines:
            return

        n = self._get_output_file()
        with open(n, 'a+') as f:
            f.writelines(self._temp_lines)
            if os.path.getsize(n) > 10 * 1024 * 1024:
                self._output_log_file_name = ''
        self._temp_lines.clear()
