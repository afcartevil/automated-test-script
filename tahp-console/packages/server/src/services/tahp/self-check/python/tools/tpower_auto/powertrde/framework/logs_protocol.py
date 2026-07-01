import os
from typing import Optional

from typing_extensions import Protocol

from powertrde.framework.tran_logger.tran_logger import TranLogger


class LogsProtocol(Protocol):
    _default_logs_module: Optional['LogsProtocol'] = None
    _has_tried_get_default_logs_module = False

    @staticmethod
    def set_default_logs_module(logs_protocol: 'LogsProtocol'):
        LogsProtocol._has_tried_get_default_logs_module = True
        LogsProtocol._default_logs_module = logs_protocol

    @staticmethod
    def get_default_logs_module() -> 'LogsProtocol':
        # if not LogsProtocol._has_tried_get_default_logs_module:
        #     LogsProtocol._has_tried_get_default_logs_module = True
        #     try:
        #         module: Any = importlib.import_module("powertrde.plugins.trde.logs")
        #         LogsProtocol._default_logs_module = module
        #     except ImportError:
        #         LogsProtocol._default_logs_module = LogsProtocol()
        # return LogsProtocol._default_logs_module
        if LogsProtocol._default_logs_module is None:
            return TranLogger.get_default().logger_p
        return LogsProtocol._default_logs_module

    def log_error(self, info, device_id='', exc_info=None):
        ...

    def log(self, info, device_id=''):
        ...

    def log_exception(self, exception, device_id='', exc_info=True):
        ...

    def log_debug(self, info, device_id=''):
        ...

    def log_warning(self, info, device_id=''):
        ...

    def get_log_dir(self) -> str:
        return os.getcwd()


def logs_p():
    return LogsProtocol.get_default_logs_module()
