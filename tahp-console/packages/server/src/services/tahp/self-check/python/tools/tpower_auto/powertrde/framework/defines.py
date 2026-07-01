import inspect
from abc import ABC, abstractmethod
from contextlib import contextmanager
from enum import Enum
from typing import TypeVar, Generic, Optional, NamedTuple

from powertrde.framework.logs_protocol import LogsProtocol


class Context:
    pass


@contextmanager
def region(name: str = "", pre_action=None, post_action=None):
    """
    自定义代码区域上下文管理器，可在进入和退出区域时执行指定操作。

    参数:
      name: 区域名称，用于显示或日志记录。
      pre_action: 进入区域时调用的函数，接收 name 参数；若为 None，则默认打印 "# region {name}"
      post_action: 退出区域时调用的函数，接收 name 参数；若为 None，则默认打印 "# endregion {name}"
    """
    if pre_action:
        sig = inspect.signature(pre_action)
        params = sig.parameters
        params_count = len(params)

        # 根据参数数量调用函数
        if params_count == 0:  # 无参数
            pre_action()
        elif params_count == 1:  # 一个参数
            pre_action(name)
    try:
        yield
    finally:
        if post_action:
            sig = inspect.signature(post_action)
            params = sig.parameters
            params_count = len(params)

            # 根据参数数量调用函数
            if params_count == 0:  # 无参数
                post_action()
            elif params_count == 1:  # 一个参数
                post_action(name)


class HasHandledException(Exception):
    _class_initialized: bool = False
    _logs_module: LogsProtocol = None

    @classmethod
    def class_initialize(cls):
        if not cls._class_initialized:
            cls._class_initialized = True
            cls._logs_module = LogsProtocol.get_default_logs_module()

    def __init__(self, *args, need_output: bool = False, handled_exception: Optional[Exception] = None):
        self.class_initialize()
        super().__init__(*args)
        self.need_output = need_output
        self.handled_exception = handled_exception

    def log_self(self):
        if self.handled_exception is not None:
            self._logs_module.log_exception(self, exc_info=self.handled_exception)
        else:
            self._logs_module.log_exception(self, exc_info=self)

    def log_handled_exception_if_exists(self):
        if self.handled_exception is not None:
            self._logs_module.log_exception(self, exc_info=self.handled_exception)

    def __str__(self):
        super_str = super().__str__()
        if self.handled_exception is None:
            return super_str
        if super_str:
            return f"{super_str}|{self.handled_exception}"
        return str(self.handled_exception)


class TextMatchMode(Enum):
    FULL = 0,
    INCLUDE = 1,
    START_WITH = 2,
    END_WITH = 3


class IInterface(ABC):
    pass


class IHasTextMatchMode(IInterface):
    @property
    def text_match_mode(self) -> TextMatchMode:
        return TextMatchMode.FULL

    def check_text_match(self, text: str, match_text: str) -> bool:
        return check_text_match(text, match_text, self.text_match_mode)


def check_text_match(text: str, match_text: str, match_mode: TextMatchMode) -> bool:
    if match_mode == TextMatchMode.FULL:
        return text == match_text
    elif match_mode == TextMatchMode.INCLUDE:
        return match_text in text
    elif match_mode == TextMatchMode.START_WITH:
        return text.startswith(match_text)
    elif match_mode == TextMatchMode.END_WITH:
        return text.endswith(match_text)
    return False


class IConfig(IInterface):
    pass


TConfig = TypeVar('TConfig', bound=IConfig)


class IHasConfig(Generic[TConfig], IInterface):
    @property
    @abstractmethod
    def config(self) -> TConfig:
        pass

    def modify_config(self, **kwargs) -> 'IHasConfig':
        config = self.config
        for key, value in kwargs.items():
            setattr(config, key, value)
        return self


class IHasParent(IInterface):
    @property
    @abstractmethod
    def parent(self) -> Optional['IHasParent']:
        pass

    @parent.setter
    @abstractmethod
    def parent(self, value: 'IHasParent'):
        pass


class HostPort(NamedTuple):
    host: str
    port: int
