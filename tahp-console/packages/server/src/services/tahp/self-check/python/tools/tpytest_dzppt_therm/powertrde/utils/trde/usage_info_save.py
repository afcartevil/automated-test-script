import json
import os
import threading
import time
import socket
import traceback

import requests

g_lock = threading.Lock()


def _pc_name():
    n = socket.gethostname()
    n2 = os.getlogin().strip()
    return f'{n}__{n2}'


def _pc_ip():
    ip = 'error ip'
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
        return ip


def _fetch_remote_text(url):
    try:
        # 发送HTTP GET请求
        response = requests.get(url)

        # 检查请求是否成功
        response.raise_for_status()

        # 返回文本内容
        return response.text
    except requests.exceptions.RequestException as e:
        # 抛出错误
        raise RuntimeError(f"Failed to fetch remote text: {e}")


def _serv_ip():
    _svr_ip_url = "http://gitlab.transsion.com/automation_extern/it_configs/raw/master/srv.txt"
    return _fetch_remote_text(_svr_ip_url)


class UsageSave:
    def __init__(self):
        self._start_ts = int(time.time())
        self._pc_name = _pc_name()
        self._pc_ip = _pc_ip()
        self._srv_ip = None
        self._case_name = ''
        self._case_name_ch = ''
        self._device_count = ''
        self._ta_count = ''
        self._is_debug = ''
        self._thread = threading.Thread(target=self._thread_cb)
        self._thread.setDaemon(True)
        self._started_flag = False
        self._stop_flag = False
        self._usage_id = ''
        self._remarks = ''
        self._save_flag = False

    @property
    def srv_ip(self):
        if self._srv_ip is None:
            try:
                self._srv_ip = _serv_ip().strip()
            except Exception as e:
                print(f'usage info save cannot get server ip: {e}')
                self._srv_ip = "127.0.0.1"
        return self._srv_ip

    def _save(self):
        if self._is_debug:
            api = f'http://{self._pc_ip}:8000/usage/save_usage/'
        else:
            api = f'http://{self.srv_ip}:8000/usage/save_usage/'
        internet_api = 'http://123.60.135.211:8000/usage/save_usage/'
        para = {
            "usage_id": self._usage_id,
            "desc": f"TRDE-{self._case_name_ch}-{self._case_name}",
            "pc_name": self._pc_name,
            "pc_ip": self._pc_ip,
            "start_ts": self._start_ts,
            "stop_ts": int(time.time()),
            "device_count": self._device_count,
            "ta_count": self._ta_count,
            'remarks': self._remarks,
        }

        headers = {
            'Content-Type': 'application/json; charset=utf-8'
        }
        data = json.dumps(para)
        response = None
        try:
            response = requests.request('POST', api, headers=headers, data=data, timeout=10.0)
        except Exception as e:
            print(f'save_usage_info(), remote url error: {e}')
            if not self._is_debug:
                response = requests.request('POST', internet_api, headers=headers, data=data, timeout=10.0)

        if response.status_code != 200:
            res = {}
            print(f'save_usage_info(), error: {response.status_code}')
        else:
            res = json.loads(response.text)
            self._usage_id = res['data']['usage_id']
            print(f'save_usage_info(), usage_id: {self._usage_id}') if self._is_debug else None
        return res

    def _thread_cb(self):
        try:
            self._start_ts = int(time.time())
            while True:
                self._save()
                wait_time = 60 if self._is_debug else 10 * 60
                for i in range(wait_time):
                    time.sleep(1)
                    if self._stop_flag:
                        self._save()
                        return
                    elif self._save_flag:
                        self._save_flag = False
                        break
        except BaseException:
            if not self._is_debug:
                traceback.print_exc()

    def start(self, case_name, case_name_ch, device_count, ta_count=0, remarks='', is_debug=False):
        g_lock.acquire()
        if not self._started_flag:
            print('usage_info.start()')
            try:
                self._started_flag = True
                self._case_name = case_name
                self._case_name_ch = case_name_ch
                self._device_count = device_count
                self._ta_count = ta_count
                self._is_debug = is_debug
                self._remarks = remarks
                self._thread.start()
            except:
                pass
        g_lock.release()

    def update_info(self, device_count=-1, ta_count=-1, remarks=None):
        print('usage_info.update_info()') if self._is_debug else None
        g_lock.acquire()
        self._device_count = device_count if device_count != -1 else self._device_count
        self._ta_count = ta_count if ta_count != -1 else self._ta_count
        self._remarks = remarks if remarks is not None else self._remarks
        self._save_flag = True
        g_lock.release()

    def finish(self):
        g_lock.acquire()
        if not self._stop_flag:
            print('usage_info.finish()') if self._is_debug else None
            self._stop_flag = True
            try:
                self._thread.join()
            except:
                pass
        g_lock.release()


def _test():
    usage = UsageSave()
    usage.start(case_name='test', case_name_ch='调试', device_count=0, ta_count=0)
    time.sleep(10)
    usage.finish()


if __name__ == '__main__':
    _test()

