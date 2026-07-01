import logging
import os.path
from typing import Optional

from powertrde.framework.tran_logger.log_device import LogDevice, MultiLogDevice
from powertrde.framework.tran_logger.tran_logger import TranLogger


class DeviceLogger(TranLogger):
    def __init__(self, log_device: LogDevice, **kwargs):
        """
        :param log_device: 设备实例（可为单设备 LogDevice 或多设备 MultiLogDevice）
        """
        # 将设备名称作为 log_group 传入父类（除了pc，此为保留字符，会自动置为空字符串，防止大量污染log console）
        dn = log_device.device_name
        if dn != 'pc':
            kwargs.setdefault('log_group', dn)
        super().__init__(**kwargs)
        self.device: LogDevice = log_device
        self.last_screenshot_path = ''

    def _parse_log_kwargs_to_extra_args(self, kwargs: dict) -> Optional[dict]:
        super()._parse_log_kwargs_to_extra_args(kwargs)
        temp_device_name = kwargs.pop('device', None)
        if temp_device_name:
            self._gen_extra_args(kwargs)['device'] = temp_device_name
        screenshot = kwargs.pop('screenshot', None)
        if screenshot:
            self._gen_extra_args(kwargs)['screenshot'] = screenshot
        error_shot = kwargs.pop('error_shot', None)
        if error_shot:
            self._gen_extra_args(kwargs)['error_shot'] = error_shot
        return kwargs.get('extra', None)

    def _log(self, level: int, msg: str, *args, **kwargs):
        """
        通用日志记录方法，支持 MultiLogDevice 设备的临时切换，并增强 tag 机制。
        """
        # 仅在需要写入文件且目录不存在时创建目录
        self._make_file_log_dir_if_needed(level)

        ori_kwargs = kwargs
        ori_msg = msg
        if self.chain_loggers:
            kwargs = kwargs.copy()

        extra = self._parse_log_kwargs_to_extra_args(kwargs)
        temp_device_name = None if not extra else extra.get('device', None)
        tag = None if not extra else extra.get('tag', None)
        screenshot = None if not extra else extra.get('screenshot', None)
        error_shot = None if not extra else extra.get('error_shot', None)

        selected_device_manager = None
        previous_device_name = None

        # 仅当 self.device 是 MultiLogDevice 时，进行设备切换
        if isinstance(self.device, MultiLogDevice):
            selected_device_manager = self.device  # 记录 MultiLogDevice 实例
            previous_device_name = self.device.selected_device_name  # 记录原选定设备

            if temp_device_name and temp_device_name in self.device.devices:
                self.device.selected_device_name = temp_device_name  # 临时切换设备

            # 获取当前选中的设备名称
            selected_name = self.device.selected_device_name

            # 处理 tag
            if selected_name and selected_name != 'pc':
                if tag:
                    tag = f"{selected_name}][{tag}"  # 在原 tag 前缀添加设备名
                else:
                    tag = selected_name  # 强制增加设备名称作为 tag
                self._gen_extra_args(kwargs)['tag'] = tag

        # 处理 screenshot
        if screenshot:
            if self._base_log_dir and level >= self._file_level and self._write_log_file_enabled:
                try:
                    file_name_suffix = '' if not isinstance(screenshot, str) else screenshot
                    _log_dir = self._log_dir
                    if file_name_suffix.find('/') >= 0:
                        file_name_suffixes = file_name_suffix.split('/')
                        file_name_suffix = file_name_suffixes.pop()
                        if file_name_suffixes:
                            _log_dir = os.path.join(self._log_dir, *file_name_suffixes)
                    elif file_name_suffix.find('\\') >= 0:
                        file_name_suffixes = file_name_suffix.split('\\')
                        file_name_suffix = file_name_suffixes.pop()
                        if file_name_suffixes:
                            _log_dir = os.path.join(self._log_dir, *file_name_suffixes)

                    self.last_screenshot_path = self.device.save_screenshot(save_dir=_log_dir or ".", file_name_suffix=file_name_suffix, error_shot=error_shot)
                    msg += f" [screenshot: {self.last_screenshot_path}]"
                except Exception as e:
                    msg += f" [screenshot failed: {e}]"
            else:
                msg += " [screenshot skipped: no file writing capability]"

        self._logger.log(level, msg, *args, **kwargs)

        # 记录完日志后，如果切换过设备，则恢复原设备
        if selected_device_manager:
            selected_device_manager.selected_device_name = previous_device_name

        if self.chain_loggers:
            if self.chain_tag:
                ori_tag = ori_kwargs.get('tag')
                if ori_tag:
                    ori_kwargs['tag'] = f'{self.chain_tag}][{ori_tag}'
                else:
                    ori_kwargs['tag'] = self.chain_tag
            for cl in self.chain_loggers:
                cl._log(level, ori_msg, *args, **ori_kwargs)

    def info_with_screenshot(self, msg: str, *args, **kwargs) -> None:
        """记录 info 级别日志，并附带截图"""
        self._log(logging.INFO, msg, *args, screenshot=True, **kwargs)

    def error_with_exception_capture(self, msg: str, *args, **kwargs) -> None:
        """记录 error 级别日志，并附带截图"""
        self._log(logging.ERROR, msg, *args, screenshot=True, **kwargs)

    def exception_with_exception_capture(self, msg: str, *args, **kwargs) -> None:
        """记录 exception 级别日志，并附带截图，且包含异常信息"""
        kwargs.setdefault('exc_info', True)  # 修复 exc_info=True 的调用
        self._log(logging.ERROR, msg, *args, screenshot=True, **kwargs)
