#!/usr/bin/python
# -*- coding: UTF-8 -*-

import logging
import os
from logging import handlers

from powertrde.utils.trde.trde_utils import OUTPUT_DIR, LOG_FILE

LOG_LEVEL_INFO = 'info'
LOG_LEVEL_ERROR = 'error'
LOGGER_NAME_GLOBAL = 'log_Global'
LOG_FORMAT = '%(asctime)s - %(levelname)s: %(message)s'
format_str = logging.Formatter(LOG_FORMAT)


class _Logs:
    g_instance = None

    def __init__(self):
        if not os.path.exists(OUTPUT_DIR):
            os.makedirs(OUTPUT_DIR)
        if not os.path.exists(LOG_FILE):
            with open(LOG_FILE, 'w+'):
                pass
        self.device_ids = []
        self._create_global_logger()
        self._all_to_shell = False

    @staticmethod
    def _get_log_shell_handler():
        shell_handler = logging.StreamHandler()  # 往屏幕上输出
        shell_handler.setFormatter(format_str)  # 设置屏幕上显示的格式
        return shell_handler

    @staticmethod
    def _get_log_file_handler(file_path_name):
        file_handler = handlers.RotatingFileHandler(
            filename=file_path_name, backupCount=50, maxBytes=10 * 1024 * 1024,
            encoding='utf-8')
        file_handler.setFormatter(format_str)
        return file_handler

    def _create_global_logger(self):
        logger = logging.getLogger(LOGGER_NAME_GLOBAL)
        logger.setLevel(logging.DEBUG)  # 设置日志级别
        logger.addHandler(self._get_log_shell_handler())
        logger.addHandler(self._get_log_file_handler(LOG_FILE))

    def _create_logger_for_device(self, device_id):
        logger = logging.getLogger(device_id)
        logger.setLevel(logging.DEBUG)  # 设置日志级别
        device_id = device_id.replace(':', '-')
        if self._all_to_shell:
            logger.addHandler(self._get_log_shell_handler())
        log_file = os.path.join(OUTPUT_DIR, f'log_{device_id}.txt')
        with open(log_file, 'w+'):
            pass
        logger.addHandler(self._get_log_file_handler(log_file))
        return logger

    def _get_logger(self, device_id=''):
        if not device_id:
            logger = logging.getLogger(LOGGER_NAME_GLOBAL)
        else:
            if device_id not in self.device_ids:
                self._create_logger_for_device(device_id)
                self.device_ids.append(device_id)
            logger = logging.getLogger(device_id)
        return logger

    def all_log_to_shell(self):
        if not self._all_to_shell:
            self._all_to_shell = True
            for device_id in self.device_ids:
                logger = logging.getLogger(device_id)
                logger.addHandler(self._get_log_shell_handler())

    def log_debug(self, info, device_id=''):
        logger = self._get_logger(device_id)
        logger.debug(info)

    def log_warning(self, info, device_id=''):
        logger = self._get_logger(device_id)
        logger.warning(info)

    def log(self, info, device_id=''):
        logger = self._get_logger(device_id)
        logger.info(info)

    def log_error(self, info, device_id="", exc_info=None):
        logger = self._get_logger(device_id)
        logger.error(info, exc_info=exc_info)
        if device_id:
            logger.error('Error of {}:'.format(device_id))
            logger = self._get_logger(LOGGER_NAME_GLOBAL)
            logger.error(info, exc_info=exc_info)

    def log_exception(self, exception, device_id='', exc_info=True):
        logger = self._get_logger(device_id)
        logger.exception(exception, exc_info=exc_info)
        if device_id:
            logger.error('Exception of {}:'.format(device_id))
            logger = self._get_logger(LOGGER_NAME_GLOBAL)
            logger.exception(exception, exc_info=exc_info)


def _get_logger():
    if not _Logs.g_instance:
        _Logs.g_instance = _Logs()
    return _Logs.g_instance


def show_all_to_shell():
    _get_logger().all_log_to_shell()


def log_debug(info, device_id=''):
    _get_logger().log_debug(info, device_id)


def log_warning(info, device_id=''):
    _get_logger().log_warning(info, device_id)


def log(info, device_id=''):
    _get_logger().log(info, device_id)


def log_error(info, device_id='', exc_info=None):
    _get_logger().log_error(info, device_id, exc_info)


def log_exception(exception, device_id='', exc_info=True):
    _get_logger().log_exception(exception, device_id, exc_info)
