import hashlib
import json
import threading
import time
import uuid

import requests

from usagestats import USAGE_SDK_VERSION
from usagestats.utils import get_county, get_machine_uuid, create_session_id, usage_sdk_log, get_pc_user_name, \
    usage_sdk_log_exception, usage_sdk_log_init


class _UsageInfo:
    is_debug = False
    usage_event = 'test_cost_time'

    def __init__(self):
        assert not _usage_instance
        self.sdk_platform = 'python'
        self.sdk_version = USAGE_SDK_VERSION
        self.user_name = get_pc_user_name()
        self.country = get_county()
        self.device_type = 'pc'
        self.device_key = get_machine_uuid()
        self.session_id = ''
        self.start_time = 0
        self.last_update_time = 0
        self.tool_key = ''
        self.tool_version = ''
        self.user_id = ''
        self.mobile_model = ''

        self._is_running = False
        self._thread = threading.Thread(target=self._thread_cb)
        self._thread.setDaemon(True)
        self._thread.start()
        usage_sdk_log_init()
        usage_sdk_log(
            f'__init__(), sdk version:{self.sdk_version}, {self.user_name}, {self.country}, PC:{self.device_key}, event:{self.usage_event}')
        usage_sdk_log(f'====> is_debug:{_UsageInfo.is_debug}') if _UsageInfo.is_debug else None

    def _thread_cb(self):
        time.sleep(5)
        while True:
            wait_time = 5 * 60 if not self.is_debug else 10
            time.sleep(wait_time)
            try:
                self._update()
            except Exception as e:
                usage_sdk_log_exception(e)

    def _service_api(self):
        if self.is_debug:
            api = 'https://pfgatewayuat.transsion.com:9199/utp-task/openapi/auto/v1/events'
        else:
            api = 'https://pfgatewaysz.transsion.com:9199/utp-task/openapi/auto/v1/events'
        return api

    @staticmethod
    def _token():
        version = 'v1'
        timestamp = int(time.time())
        accessKey = '5wt6qcvf'
        secretKey = 'yRJKOBbldrlfsTsm6vzQtHYSzztwZx6q'
        nonce = uuid.uuid4().hex
        plainText = f'{version}|{timestamp}|{accessKey}|{nonce}|{secretKey}'
        sign = hashlib.md5(plainText.encode('utf-8')).hexdigest()
        utp_token = f'{version}|{timestamp}|{accessKey}|{nonce}|{sign}'
        return utp_token

    def _save(self):
        usage_sdk_log('_save()') if self.is_debug else None
        internet_api = self._service_api()
        para = {
            "toolKey": self.tool_key,
            "toolVersion": self.tool_version,
            "sdkPlatform": self.sdk_platform,
            "sdkVersion": self.sdk_version,
            "userId": self.user_id,
            "userName": self.user_name if not self.user_id else '',
            "country": self.country,
            "mobileModel": self.mobile_model,
            "deviceType": self.device_type,
            "deviceKey": self.device_key,
            "sessionId": self.session_id,
            "event": self.usage_event,
            "eventParams": {
                "startTime": self.start_time,
                "lastUpdateTime": self.last_update_time,
            },
        }
        headers = {'UTP-TOKEN': self._token(), 'Content-Type': 'application/json; charset=utf-8'}
        data = json.dumps(para)

        try:
            response = requests.post(internet_api, headers=headers, data=data)
            if response.status_code != 200:
                res = {}
                usage_sdk_log(
                    f'_save() error, service response status code: {response.status_code}， info: {response.text}')
            else:
                res = json.loads(response.text)
                if not res.get('success'):
                    usage_sdk_log(f'_save() error, service response info: {response.text}')
                else:
                    usage_sdk_log(f'_save(), save service success') if self.is_debug else None
        except Exception as e:
            usage_sdk_log_exception(e)
            res = {}
        return res

    def _update(self):
        _g_lock.acquire()
        if self._is_running:
            self.last_update_time = int(time.time())
            usage_sdk_log(f'update:{self.last_update_time}') if self.is_debug else None
            self._save()
        _g_lock.release()

    def start(self, tool_key, tool_version, mobile_model, user_id):
        if self._is_running:
            self.end()
        _g_lock.acquire()
        self.tool_key = tool_key
        self.tool_version = tool_version
        self.user_id = user_id if user_id else ''
        self.mobile_model = mobile_model

        self.session_id = create_session_id()
        self.start_time = int(time.time())
        self.last_update_time = self.start_time
        self._is_running = True
        usage_sdk_log(
            f'start(), session id:{self.session_id}, ts({self.start_time}, ), {tool_key}({tool_version}), {mobile_model}, user id:{user_id}')
        self._save()
        _g_lock.release()

    def end(self):
        usage_sdk_log(
            f'end(), session id:{self.session_id}, ts({self.start_time}, {self.last_update_time}),'
            f' {self.tool_key}({self.tool_version}), {self.mobile_model}, user id:{self.user_id}, '
            f'running:{self._is_running}')
        _g_lock.acquire()
        if self._is_running:
            self.last_update_time = int(time.time())
            self._save()
            self._is_running = False
        _g_lock.release()


_usage_instance: _UsageInfo | None = None
_g_lock = threading.Lock()


def set_debug_mode():
    _UsageInfo.is_debug = True


def set_event_install_apk():
    _UsageInfo.usage_event = 'install_apk'


def start(tool_key: str, tool_version: str, mobile_model: str, user_id=''):
    global _usage_instance
    if not _usage_instance:
        _usage_instance = _UsageInfo()
    _usage_instance.start(tool_key, tool_version, mobile_model, user_id)


def stop():
    if not _usage_instance:
        return
    _usage_instance.end()


def _test():
    session_infos = [
        ('debug_tool111', '1.1.111', 'Infinix X6877'),
        ('debug_tool222', '1.1.222', 'Infinix X6877'),
    ]
    # set_debug_mode()
    # set_event_install_apk()
    for n, v, m in session_infos:
        start(n, v, m)
        time.sleep(60)
        stop()


if __name__ == '__main__':
    _test()
