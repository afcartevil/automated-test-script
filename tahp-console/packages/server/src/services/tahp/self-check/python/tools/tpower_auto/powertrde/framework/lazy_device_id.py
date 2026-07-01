from functools import cached_property
from typing import Optional, Callable, Union, Protocol


class SerialProvider(Protocol):
    @property
    def serial(self) -> str:
        ...

    @staticmethod
    def is_serial_provider(instance):
        return hasattr(instance, 'serial')


class CachedSerialProvider(Protocol):
    @cached_property
    def serial(self) -> str:
        ...


class SerialProviderFactory(Protocol):
    @property
    def serial_provider(self) -> Union[None, SerialProvider, CachedSerialProvider]:
        ...

    @property
    def serial(self) -> str:
        ...


class LazyDeviceID:
    """
    延迟计算的设备 ID 类，支持直接传入字符串或工厂函数，避免在不必要时计算 device_id。

    - 如果传入字符串，则 `device_id` 立即赋值。
    - 如果传入工厂函数，则在 **第一次访问** `device_id` 时，才会调用该函数计算值。

    用户也可以在运行时 **手动赋值** `device_id`，这样后续的访问不会再调用工厂函数。

    示例:
        >>> lazy_id = LazyDeviceID(lambda: "GeneratedDevice123")
        >>> print(lazy_id.device_id)  # 第一次访问时计算
        "GeneratedDevice123"

        >>> lazy_id.device_id = "ManualOverride123"
        >>> print(lazy_id.device_id)  # 后续访问不再调用工厂函数
        "ManualOverride123"
    """

    def __init__(self, factory_func: Union[
        None, str, SerialProvider, CachedSerialProvider, Callable[[], str], Callable[[], SerialProvider], Callable[
            [], CachedSerialProvider]] = None, call_factory_every_time=False):
        """
        :param factory_func: 设备 ID 值，可以是字符串 (立即赋值) 或 无参数返回字符串的工厂函数 (延迟计算)
        :param call_factory_every_time: 是否在调用device_id时，每次都使用工厂函数来计算最新的device_id值
        """
        self.call_factory_every_time = call_factory_every_time
        self._cached_device_id: Optional[str, callable] = None  # 用于存储计算后的设备 ID
        self._factory_func: Optional[
            Union[Callable[[], str], Callable[[], SerialProvider], Callable[[], CachedSerialProvider]]] = None  # 工厂函数
        self._cached_serial_provider: Optional[Union[SerialProvider, CachedSerialProvider]] = None  # 序列号提供器

        if isinstance(factory_func, str):
            self._cached_device_id = factory_func  # 直接赋值
        if SerialProvider.is_serial_provider(factory_func):
            self._cached_device_id = factory_func.serial
            self._cached_serial_provider = factory_func  # 直接赋值为序列号提供器
        elif callable(factory_func):
            self._factory_func = factory_func  # 仅在访问时计算
        else:
            self._cached_device_id = ""  # 默认为空字符串

    @property
    def serial_provider(self):
        if self._cached_serial_provider is None and self._factory_func:
            _ = self.device_id
        if self._cached_serial_provider is not None:
            sp = getattr(self._cached_serial_provider, 'serial_provider', None)
            return sp or self._cached_serial_provider
        return self._cached_serial_provider

    @property
    def device_id(self) -> str:
        """
        获取设备 ID。如果未初始化，则调用工厂函数进行计算。
        """
        if self._cached_device_id is None and self._factory_func:
            _mid_result = self._factory_func()
            if SerialProvider.is_serial_provider(_mid_result):
                if self.call_factory_every_time:
                    self._cached_device_id = (lambda: _mid_result.serial)
                else:
                    self._cached_device_id = _mid_result.serial
                self._cached_serial_provider = _mid_result
            else:
                if self.call_factory_every_time:
                    self._cached_device_id = self._factory_func
                else:
                    self._cached_device_id = _mid_result
        if self._cached_device_id is None:
            return ''
        return self._cached_device_id() if callable(self._cached_device_id) else self._cached_device_id

    @device_id.setter
    def device_id(self, value: str):
        """
        直接手动赋值设备 ID，覆盖工厂函数的计算结果。
        """
        self._cached_device_id = value

    def __str__(self) -> str:
        """允许 `LazyDeviceID` 直接转换为字符串"""
        return self.device_id

    def __repr__(self) -> str:
        return f"LazyDeviceID({repr(self._cached_device_id)})"
