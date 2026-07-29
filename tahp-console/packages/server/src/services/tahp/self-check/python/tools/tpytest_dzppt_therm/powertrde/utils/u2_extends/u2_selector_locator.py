import inspect
from contextlib import contextmanager
from typing import Dict, Optional, Callable, List, Union

from powertrde import env
from powertrde.utils.simple_event_center import SimpleEventCenter, SimpleEventListener
from powertrde.utils.u2_extends.u2_bound_selector import U2BoundSelector
from powertrde.utils.u2_extends.u2_selector import U2Selector, U2ElementEvent
import uiautomator2 as u2

from powertrde.utils.u2_extends.u2utils import U2DeviceProtocol


class U2SelectorLocator:
    """
    页面定位器基类：
      - 接受 Device
      - 在初始化时，将所有 U2Selector 属性自动绑定成 BoundU2Selector
    """
    _shared_event_center = SimpleEventCenter()

    def __init__(self):
        super().__init__()
        self.bound_selectors: Dict[str, U2BoundSelector] = {}
        self._local_event_center: SimpleEventCenter = SimpleEventCenter()
        self._event_centers: Optional[List[SimpleEventCenter]] = None
        self._namespace: Optional[str] = None
        self.__post_init__()

    def __post_init__(self):
        """尝试自动绑定selectors"""
        _get_u2d = getattr(self, 'get_u2d', None)
        if _get_u2d:
            _aw_name = getattr(self, 'aw_name', None)
            if _aw_name:
                self.namespace = _aw_name
            self.bind_u2_selectors(_get_u2d)

    @property
    def namespace(self):
        return self._namespace or self.__class__.__name__

    @namespace.setter
    def namespace(self, value: Optional[str]):
        self._namespace = value

    def _get_locator_event_centers(self) -> List[SimpleEventCenter]:
        if self._event_centers is None:
            self._event_centers = [self._local_event_center, self._shared_event_center]
        return self._event_centers

    def add_u2_element_listener(self, on_event_callback: Callable[[U2ElementEvent], None]):
        listener = SimpleEventListener('', on_event_callback)
        self._local_event_center.add_listener_directly(listener)
        return listener

    @staticmethod
    def add_shared_u2_element_listener(on_event_callback: Callable[[U2ElementEvent], None]):
        listener = SimpleEventListener('', on_event_callback)
        U2SelectorLocator._shared_event_center.add_listener_directly(listener)
        return listener

    @contextmanager
    def listen_u2_element_event(self, on_event_callback: Callable[[U2ElementEvent], None]):
        listener = self.add_u2_element_listener(on_event_callback)
        try:
            yield
        finally:
            listener.dispose()

    @classmethod
    @contextmanager
    def listen_shared_u2_element_event(cls, on_event_callback: Callable[[U2ElementEvent], None]):
        listener = cls.add_shared_u2_element_listener(on_event_callback)
        try:
            yield
        finally:
            listener.dispose()

    def bind_u2_selectors(self, u2d_or_factory: Union[Union[u2.Device, U2DeviceProtocol], Callable[[], Union[u2.Device, U2DeviceProtocol]]]):
        """
        收集本类所有 U2Selector 类属性并实例化为 BoundU2Selector
        """
        for cls in inspect.getmro(self.__class__):  # 从子类到基类顺序
            for name, val in cls.__dict__.items():
                if name not in self.bound_selectors:
                    if isinstance(val, U2Selector):
                        self._add_clone_selector(val, name, u2d_or_factory)
                    elif isinstance(val, U2BoundSelector):
                        self._add_clone_selector(val.selector, name, u2d_or_factory)

    def _add_clone_selector(self, source: U2Selector, name: str, u2d_or_factory: Union[Union[u2.Device, U2DeviceProtocol], Callable[[], Union[u2.Device, U2DeviceProtocol]]]):
        clone_selector = source.clone()
        clone_selector.namespace = self.namespace
        clone_selector.name = name
        clone_selector.get_event_centers = self._get_locator_event_centers
        bound = U2BoundSelector(clone_selector, u2d_or_factory)
        clone_selector.bound_selector_attached_to = bound
        clone_selector.locator_attached_to = self
        setattr(self, name, bound)
        self.bound_selectors[name] = bound

    @staticmethod
    def gen_bound_u2_selector(selector: U2Selector, u2d_or_factory: Union[Union[u2.Device, U2DeviceProtocol], Callable[[], Union[u2.Device, U2DeviceProtocol]]]):
        """
        构建一个新的BoundU2Selector
        """
        bound = U2BoundSelector(selector, u2d_or_factory)
        return bound

    @property
    def u2_scope_flag(self):
        return env.get_user_env_arg('u2_scope_flag', '')

    @u2_scope_flag.setter
    def u2_scope_flag(self, value):
        env.set_user_env_arg('u2_scope_flag', value)
