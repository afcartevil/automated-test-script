from abc import ABC, abstractmethod
from enum import Enum
from typing import TypeVar, Generic, Optional, NamedTuple, Union
import inspect
import traceback
from contextlib import contextmanager
from typing import get_origin, get_args

from powertrde.framework.logs_protocol import LogsProtocol


class Context:
    pass


def _ann_is_exception_type(ann) -> bool:
    """
    判断注解 ann 是否指向 Exception / BaseException 或者包含 Exception 的 Union。
    """
    if ann is inspect._empty:
        return False
    try:
        if isinstance(ann, type) and issubclass(ann, BaseException):
            return True
    except Exception:
        pass
    origin = get_origin(ann)
    if origin is Union:
        for a in get_args(ann):
            try:
                if isinstance(a, type) and issubclass(a, BaseException):
                    return True
            except Exception:
                pass
    return False


def _should_pass_exception_to_param(param: inspect.Parameter) -> bool:
    """
    判断某个参数是否更可能用来接收 exception：
     - 注解显示为 Exception / BaseException 或包含它的 Union
     - 或者参数名为常见的异常名（exc, exception, err, error, e）
    """
    if _ann_is_exception_type(param.annotation):
        return True
    name = param.name.lower()
    if name in {"exc", "exception", "err", "error", "e", "exc_info"}:
        return True
    return False


def _call_post_action(post_action, name: str, exc):
    """
    智能调用 post_action：
      - 0 参数 -> post_action()
      - 1 参数 -> 若参数看起来要 exception -> post_action(exc) 否则 post_action(name)
      - >=2 参数 -> post_action(name, exc)
    捕获 post_action 内部异常并打印堆栈（不阻止原始异常传播）。
    """
    if post_action is None:
        # 默认行为（如果你希望默认打印，可在这里打印）
        # print(f"# endregion {name}")
        return

    try:
        sig = inspect.signature(post_action)
    except (ValueError, TypeError):
        # 无法获取签名时尝试多种调用方式（宽容兼容）
        try:
            post_action(name, exc)
            return
        except TypeError:
            try:
                post_action(exc)
                return
            except TypeError:
                try:
                    post_action(name)
                    return
                except TypeError:
                    try:
                        post_action()
                        return
                    except Exception:
                        traceback.print_exc()
                        return

    params = list(sig.parameters.values())
    params_count = len(params)

    try:
        if params_count == 0:
            post_action()
        elif params_count == 1:
            p = params[0]
            if _should_pass_exception_to_param(p):
                post_action(exc)
            else:
                post_action(name)
        else:
            # >=2 参数：把 name, exception 作为前两个参数传入
            post_action(name, exc)
    except Exception:
        # 记录 post_action 的异常，但不吞掉原始异常
        print("[region] post_action raised an exception:")
        traceback.print_exc()


@contextmanager
def region(name: str = "", pre_action=None, post_action=None, *, catch_base_exceptions: bool = False):
    """
    自定义代码区域上下文管理器。

    - pre_action: 进入区域时调用，支持 0 或 1 个参数（若为1个则传入 name）。
    - post_action: 退出区域时调用，支持多种签名：
        - post_action()
        - post_action(name)
        - post_action(exc)
        - post_action(name, exc)
      当 with-block 抛出异常时，post_action 会在重新抛出异常前被调用。
      默认只捕获 Exception 并将其传给 post_action；若你确实想捕获 SystemExit/KeyboardInterrupt 等
      系统级异常，请显式传入 catch_base_exceptions=True。
    - catch_base_exceptions: bool, 是否捕获 BaseException（默认 False）。
    """
    # pre_action 调用（兼容 0/1 参数）
    if pre_action:
        try:
            sig = inspect.signature(pre_action)
            params = sig.parameters
            params_count = len(params)
            if params_count == 0:
                pre_action()
            elif params_count == 1:
                pre_action(name)
            else:
                # 兼容性尝试：尽量以 name 调用
                try:
                    pre_action(name)
                except TypeError:
                    pre_action()
        except Exception:
            print("[region] pre_action raised an exception:")
            traceback.print_exc()

    # 主体：分两种异常捕获策略
    try:
        yield
    except Exception as exc:
        # 仅捕获常规 Exception（不会捕获 KeyboardInterrupt/SystemExit）
        # 调用 post_action（如果签名支持传入 exception），然后重新抛出
        try:
            _call_post_action(post_action, name, exc)
        except Exception:
            traceback.print_exc()
        raise
    except BaseException as exc:
        # 仅当用户显式要求捕获 BaseException 时才处理，否则立即重新抛出（不调用 post_action）
        if catch_base_exceptions:
            try:
                _call_post_action(post_action, name, exc)
            except Exception:
                traceback.print_exc()
            # 重新抛出异常以保持语义
            raise
        else:
            # 不捕获，也不调用 post_action；直接将异常向外传播
            raise
    else:
        # 正常退出：调用 post_action，exc 为 None
        try:
            _call_post_action(post_action, name, None)
        except Exception:
            traceback.print_exc()


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
