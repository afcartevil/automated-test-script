import os.path
from datetime import datetime
from typing import Optional

from powertrde.framework.tran_logger.device_logger import DeviceLogger
from powertrde.framework.tran_logger.log_device import LocalLogDevice
from powertrde.framework.tran_logger.tran_logger import TranLogger


class TPytestRuntime:
    _instance: Optional['TPytestRuntime'] = None

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._runtime_session_id = ''
        self._runtime_logger: Optional[TranLogger] = None
        self.user_obj = {}

    @property
    def current_scheme_env(self):
        from tpytest.scheme.scheme_test_env import get_scheme_env
        return get_scheme_env()

    @property
    def runtime_session_id(self):
        if not self._runtime_session_id:
            time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            _scheme_name = self.current_scheme_env.scheme_name
            if not _scheme_name:
                _scheme_name = 'tpytest'
            self._runtime_session_id = f'host_{time_str}_{_scheme_name}'
        return self._runtime_session_id

    @runtime_session_id.setter
    def runtime_session_id(self, value: str):
        self._runtime_session_id = value

    @property
    def runtime_log_parent_dir(self):
        return self.current_scheme_env.get_runtime_log_parent_dir()

    @property
    def runtime_log_dir(self):
        return os.path.join(self.runtime_log_parent_dir, self.runtime_session_id)

    @property
    def runtime_logger(self):
        if not self._runtime_logger:
            pc_logger = LocalLogDevice(device_name='tpytest')
            self._runtime_logger = DeviceLogger(log_device=pc_logger,
                                                base_log_dir=self.runtime_log_dir,
                                                log_session_id='session_logs')
        return self._runtime_logger

    @runtime_logger.setter
    def runtime_logger(self, value: TranLogger):
        self._runtime_logger = value

    @property
    def task_session_logger(self):
        return self.current_scheme_env.logger

    @property
    def task_session_id(self):
        return self.current_scheme_env.session_id

    @property
    def task_session_log_root_dir(self):
        return self.current_scheme_env.get_log_root_dir()

    @property
    def task_session_logs_dir(self):
        return self.current_scheme_env.get_session_logs_dir()

    @property
    def task_session_meta_report_dir(self):
        return self.current_scheme_env.get_meta_report_dir()
