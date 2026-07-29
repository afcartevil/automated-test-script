import inspect
import logging
import os
import re
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from re import Pattern
from typing import Optional, Any, List, Iterable, Union

LOG_LEVEL_MAP = {
    'D': logging.DEBUG,
    'I': logging.INFO,
    'W': logging.WARNING,
    'E': logging.ERROR,
    'C': logging.CRITICAL
}

LOG_LEVEL_SHORT = {v: k for k, v in LOG_LEVEL_MAP.items()}


class ObfuscatingFilter(logging.Filter):
    """
    将 LogRecord 的 message 替换为 confuse_string(message)。
    - confuse_fn: Callable[[str], str]
    - levels: optional iterable of logging level numbers to apply to (e.g. {logging.INFO})
    - logger_name_pattern: optional regex Pattern or string; only records whose record.name matches are processed
    - marker_skip: if True, skip messages that already start with the marker (no double obfuscation)
    - preserve_original: if True, stores original text into record.__orig_msg (for possible later use)
    """
    def __init__(self,
                 confuse_fn,
                 *,
                 levels: Optional[Iterable[int]] = None,
                 logger_name_pattern: Optional[Union[Pattern, str]] = None,
                 marker: Optional[str] = None,
                 marker_skip: bool = True,
                 preserve_original: bool = True):
        super().__init__()
        self.confuse_fn = confuse_fn
        self.levels = set(levels) if levels is not None else None
        self.logger_pat = re.compile(logger_name_pattern) if isinstance(logger_name_pattern, str) else logger_name_pattern
        self.marker = marker
        self.marker_skip = marker_skip
        self.preserve_original = preserve_original

    def filter(self, record: logging.LogRecord) -> bool:
        # optional level check
        if self.levels is not None and record.levelno not in self.levels:
            return True
        # optional logger name check
        if self.logger_pat is not None and not self.logger_pat.search(record.name):
            return True

        try:
            # get fully formatted message from record (this uses record.msg and record.args)
            orig = record.getMessage()
        except Exception:
            # if getMessage fails, skip obfuscation to avoid breaking logging
            return True

        # skip if marker present and marker_skip True
        if self.marker and self.marker_skip and isinstance(orig, str) and orig.startswith(self.marker):
            return True

        try:
            obf = self.confuse_fn(orig)
        except Exception:
            # On failure, do not break logging; leave original
            return True

        # store original if requested
        if self.preserve_original:
            # keep previous original if present
            if not hasattr(record, "__orig_msg"):
                record.__orig_msg = orig

        # replace record.msg / record.args so subsequent format uses obfuscated text
        record.msg = obf
        record.args = ()
        return True


class TranLogger:
    _instances = {}
    _default_instance = None

    def __init__(
            self,
            name: Optional[str] = None,
            base_log_dir: Optional[str] = None,
            log_session_id: Optional[str] = None,
            log_group: Optional[str] = None,
            console_level: int = logging.DEBUG,
            file_level: int = logging.INFO,
            max_file_size_in_mb: int = 10,
            register: bool = False,
            only_one_log_file_name=''
    ):
        self._logger = logging.getLogger(f'TranLogger.{name}' if name else f"TranLogger.{id(self)}")
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        self.chain_loggers: List[TranLogger] = []
        self.chain_tag = ''

        self._write_log_file_enabled = True
        self._write_log_console_enabled = True

        self._base_log_dir = base_log_dir
        self.log_session_id = log_session_id or time.strftime("%Y%m%d")
        self.log_group = log_group or ''
        self.max_file_size_in_mb = max_file_size_in_mb  # 存储配置
        self._current_file_handler = None

        self._control_level = console_level
        self._console_handler = self._create_console_handler()
        self._logger.addHandler(self._console_handler)

        self._file_level = file_level
        self._log_dir = None
        self._logger_p = None
        self._only_one_log_file_name = only_one_log_file_name

        if self._base_log_dir:
            self._init_file_handler()

        # 实例注册逻辑
        self.name = name
        if register and name is not None:
            if name in self.__class__._instances:
                raise ValueError(f"Logger name '{name}' already registered")
            self.__class__._instances[name] = self

    @property
    def base_log_dir(self):
        return self._base_log_dir

    @property
    def log_dir(self):
        return self._log_dir

    @property
    def console_log_level(self):
        return self._file_level

    @console_log_level.setter
    def console_log_level(self, value: int):
        if self._control_level == value:
            self._control_level = value
            self._console_handler.setLevel(value)

    @property
    def file_log_level(self):
        return self._file_level

    @file_log_level.setter
    def file_log_level(self, value: int):
        if self._file_level == value:
            self._file_level = value
            if self._current_file_handler:
                self._current_file_handler.setLevel(value)

    @property
    def control_log_level(self):
        return self._control_level

    @control_log_level.setter
    def control_log_level(self, value: int):
        if self._control_level == value:
            self._control_level = value
            if self._console_handler:
                self._console_handler.setLevel(value)

    @property
    def write_log_file_enabled(self):
        return self._write_log_file_enabled

    @write_log_file_enabled.setter
    def write_log_file_enabled(self, value: bool):
        if self._write_log_file_enabled != value:
            self._write_log_file_enabled = value
            if value:
                if self._base_log_dir:
                    self._init_file_handler()
                elif self._current_file_handler:
                    self._logger.addHandler(self._current_file_handler)
            else:
                if self._current_file_handler:
                    self._logger.removeHandler(self._current_file_handler)

    @property
    def write_log_console_enabled(self):
        return self._write_log_console_enabled

    @write_log_console_enabled.setter
    def write_log_console_enabled(self, value: bool):
        if self._write_log_console_enabled != value:
            self._write_log_console_enabled = value
            if value:
                self._logger.addHandler(self._console_handler)
            else:
                self._logger.removeHandler(self._console_handler)

    @property
    def logger_p(self):
        """获取日志代理实例"""
        if not self._logger_p:
            from powertrde.framework.tran_logger.tran_logger_p import TranLoggerP
            self._logger_p = TranLoggerP(self)
        return self._logger_p

    @property
    def classical_logger(self):
        return self._logger

    def add_log_handler(self, level: int, handler: logging.Handler, with_formatter: bool = True):
        handler.setLevel(level)
        handler.addFilter(self._log_filter)
        if with_formatter:
            handler.setFormatter(self._create_formatter())
        self._logger.addHandler(handler)

    def _create_console_handler(self) -> logging.Handler:
        handler = logging.StreamHandler()
        handler.setLevel(self._control_level)
        handler.addFilter(self._log_filter)
        handler.setFormatter(self._create_formatter())
        return handler

    def _create_formatter(self) -> logging.Formatter:
        """重构后的格式化方法"""
        fmt = '[%(asctime)s][%(levelshort)s]'

        # 始终显示log_group（如果有配置）
        if self.log_group:
            fmt += f'[{self.log_group}]'
        fmt += '%(tagsection)s - %(message)s'
        return logging.Formatter(fmt, datefmt='%Y-%m-%d %H:%M:%S')

    def _init_file_handler(self):
        # 生成目录路径（但暂不创建）
        dir_name = self.log_session_id
        if self.log_group:
            dir_name += f"_{self.log_group}"
        self._log_dir = os.path.join(self._base_log_dir, dir_name)

        # 延迟创建处理器
        if self._only_one_log_file_name:
            self._filename_template = os.path.join(
                self._log_dir,
                self._only_one_log_file_name + ".log"
            )
            handler = logging.FileHandler(
                self._filename_template,
                encoding='utf-8',
                delay=True,
            )
        else:
            self._filename_template = os.path.join(
                self._log_dir,
                time.strftime("%Y%m%d_%H%M%S") + ".log"
            )
            handler = RotatingFileHandler(
                self._filename_template,
                maxBytes=self.max_file_size_in_mb * 1024 * 1024,
                backupCount=100,
                encoding='utf-8',
                delay=True
            )
        handler.setLevel(self._file_level)
        handler.addFilter(self._log_filter)
        handler.setFormatter(self._create_formatter())

        if self._current_file_handler:
            self._logger.removeHandler(self._current_file_handler)
        self._current_file_handler = handler
        self._logger.addHandler(handler)

    def _log_filter(self, record: logging.LogRecord) -> bool:
        # 转换日志等级缩写
        record.levelshort = LOG_LEVEL_SHORT.get(record.levelno, 'U')

        # 处理tag显示
        record.tagsection = f'[{getattr(record, "tag", "")}]' if hasattr(record, 'tag') else ''

        # 仅ERROR及以上级别处理源码位置
        if record.levelno >= logging.ERROR:
            record.source_info = self._get_safe_source_info(record)
        else:
            record.source_info = ""
        return True

    def _gen_extra_args(self, kwargs: dict):
        extra = kwargs.get('extra', None)
        if extra is None:
            extra = {}
            kwargs['extra'] = extra
        return extra

    def _parse_log_kwargs_to_extra_args(self, kwargs: dict) -> Optional[dict]:
        tag = kwargs.pop('tag', None)
        if tag:
            self._gen_extra_args(kwargs)['tag'] = tag

        keys_to_process = [key for key in kwargs if key.startswith('ext_')]
        for key in keys_to_process:
            new_key = key[len('ext_'):]
            self._gen_extra_args(kwargs)[new_key] = kwargs.pop(key)

        return kwargs.get('extra', None)

    def _make_file_log_dir_if_needed(self, log_level: int):
        if (self._base_log_dir and self._current_file_handler and self._write_log_file_enabled and
                log_level >= self._file_level and not os.path.exists(self._log_dir)):
            os.makedirs(self._log_dir, exist_ok=True)

    def _log(self, level: int, msg: str, *args, **kwargs):
        # 仅在需要写入文件且目录不存在时创建目录
        self._make_file_log_dir_if_needed(level)

        if self.chain_loggers:
            new_kwargs = kwargs.copy()
            self._parse_log_kwargs_to_extra_args(new_kwargs)
            self._logger.log(level, msg, *args, **new_kwargs)

            if self.chain_tag:
                ori_tag = kwargs.get('tag')
                if ori_tag:
                    kwargs['tag'] = f'{self.chain_tag}][{ori_tag}'
                else:
                    kwargs['tag'] = self.chain_tag
            for cl in self.chain_loggers:
                cl._log(level, msg, *args, **kwargs)
        else:
            self._parse_log_kwargs_to_extra_args(kwargs)
            self._logger.log(level, msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs):
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self._log(logging.ERROR, msg, *args, **kwargs)

    def error_with_tag(self, msg: str, error_tag='error', *args, **kwargs):
        """记录 error 级别日志，并且自动将额外的error_tag带入tag中"""
        tag = kwargs.get('tag', None)
        if tag:
            kwargs['tag'] = f'{tag}][{error_tag}'
        else:
            kwargs['tag'] = error_tag
        self._log(logging.ERROR, msg, *args, **kwargs)

    def exception(self, msg: str, *args, exc_info=True, **kwargs):
        kwargs.setdefault('exc_info', exc_info)
        self._log(logging.ERROR, msg, *args, **kwargs)

    @classmethod
    def get_default(cls) -> 'TranLogger':
        if cls._default_instance is None:
            cls._default_instance = TranLogger()
        return cls._default_instance

    @classmethod
    def set_default(cls, value: Optional['TranLogger']):
        cls._default_instance = value

    @classmethod
    def configure_default(
            cls,
            base_log_dir: Optional[str] = None,
            log_session_id: Optional[str] = None,
            log_group: Optional[str] = None,
            console_level: int = logging.DEBUG,
            file_level: int = logging.INFO,
            max_file_size_in_mb: int = 10
    ) -> None:
        instance = cls.get_default()
        need_reinit = False

        if base_log_dir != instance._base_log_dir:
            instance._base_log_dir = base_log_dir
            need_reinit = True

        if log_session_id is not None:
            instance.log_session_id = log_session_id or time.strftime("%Y%m%d")
            need_reinit = True

        if log_group is not None:
            instance.log_group = log_group or ''
            need_reinit = True

        if max_file_size_in_mb != instance.max_file_size_in_mb:
            instance.max_file_size_in_mb = max_file_size_in_mb
            need_reinit = True

        instance.file_log_level = file_level
        if need_reinit and instance._base_log_dir and instance.write_log_file_enabled:
            instance._init_file_handler()

        instance.control_log_level = console_level

    @classmethod
    def get_logger(cls, name: Optional[str] = None, *, auto_create: bool = False) -> 'TranLogger':
        """获取已注册的日志实例

        :param name: 日志器名称，None表示获取默认实例
        :param auto_create: 当实例不存在时是否自动创建默认配置实例
        """
        if name is None:
            return cls.get_default()
        exists = cls._instances.get(name)
        if exists:
            return exists
        if auto_create:
            new_logger = cls(name=name, register=True)
            return new_logger
        raise KeyError(f"No registered logger with name '{name}'. "
                       f"Available names: {list(cls._instances.keys())}")

    @classmethod
    def register_instance(cls, name: str, instance: 'TranLogger', overwrite: bool = False):
        """注册日志实例到全局管理"""
        if not overwrite and name in cls._instances:
            raise ValueError(f"Logger name '{name}' already exists")
        cls._instances[name] = instance

    @classmethod
    def get_registered_names(cls) -> list:
        """获取所有已注册的日志器名称"""
        return list(cls._instances.keys())

    @staticmethod
    def _get_safe_source_info(record: logging.LogRecord) -> str:
        """安全获取源码位置信息"""
        # 获取基础路径
        base_path = None

        # 方案1：尝试获取入口文件路径（适用于exe和普通脚本）
        if getattr(sys, 'frozen', False):
            # 打包成exe的情况
            base_path = Path(sys.executable).parent
        else:
            # 普通Python脚本运行
            stack = inspect.stack()
            for frame in stack[::-1]:
                if frame.filename == sys.argv[0]:
                    base_path = Path(frame.filename).parent
                    break

        # 方案2：回退到当前工作目录
        if base_path is None:
            base_path = Path.cwd()

        # 转换为相对路径
        try:
            src_path = Path(record.pathname).resolve()
            rel_path = src_path.relative_to(base_path)
            return f"{rel_path}:{record.lineno}"
        except Exception:
            return f"{os.path.basename(record.pathname)}:{record.lineno}"

    def __getattr__(self, name: str) -> Any:
        return getattr(self._logger, name)


# 初始化默认实例
TranLogger.configure_default()
