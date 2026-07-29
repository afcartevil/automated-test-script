from typing import List, Union, Tuple, Callable

from uiautomator2.xpath import XMLElement

from powertrde.utils.u2_extends.u2_selector import U2Selector
import uiautomator2 as u2

from powertrde.utils.u2_extends.u2utils import U2DeviceProtocol


class U2BoundSelector:
    """
    与 Device 绑定后的 U2Selector，提供常用操作：
      - click、long_click、set_text、clear_text
      - swipe、scroll（方向）、children、parent
      - info、exists_then_click
    """

    def __init__(self, selector: U2Selector, u2d_or_factory: Union[Union[u2.Device, U2DeviceProtocol], Callable[[], Union[u2.Device, U2DeviceProtocol]], None]):
        super().__init__()
        self.selector = selector
        self._u2d_or_factory = u2d_or_factory

    @property
    def u2d(self):
        if isinstance(self._u2d_or_factory, U2DeviceProtocol):
            return self._u2d_or_factory
        elif callable(self._u2d_or_factory):
            return self._u2d_or_factory()
        return None

    @u2d.setter
    def u2d(self, value: Union[Union[u2.Device, U2DeviceProtocol], Callable[[], Union[u2.Device, U2DeviceProtocol]], None]):
        self._u2d_or_factory = value

    @property
    def namespace(self):
        return self.selector.namespace

    @property
    def name(self):
        return self.selector.name

    @property
    def full_name(self):
        return self.selector.full_name

    def with_params(self, **params) -> 'U2BoundSelector':
        """
        基于模板 selector 应用动态参数，返回新的 BoundUiSelector
        """
        new_sel = self.selector.with_params(**params)
        return self.__class__(new_sel, self.u2d)

    def get(self, timeout: float = 5.0, raise_on_not_found: bool = True, post_wait: float = 0.0) -> Union[u2.UiObject, u2.xpath.XMLElement, None]:
        return self.selector.get(self.u2d, timeout, raise_on_not_found, post_wait)

    def exists(self) -> bool:
        return self.selector.exists(self.u2d)

    def all(self) -> List[XMLElement]:
        return self.selector.all(self.u2d)

    def wait(self, timeout: float = 10.0, raise_on_false_result: bool = False, post_wait: float = 0.0) -> bool:
        return self.selector.wait(self.u2d, timeout, raise_on_false_result, post_wait)

    def wait_gone(self, timeout: float = 10.0, raise_on_false_result: bool = False, post_wait: float = 0.0) -> bool:
        return self.selector.wait_gone(self.u2d, timeout, raise_on_false_result, post_wait)

    def click(self, timeout: float = 5.0, wait_before_click: float = 0.0, wait_after_click: float = 0.0,
              offset: Tuple[float, float] = (0.5, 0.5), no_raise: bool = False) -> Union[u2.UiObject, u2.xpath.XMLElement, None]:
        """单击操作"""
        return self.selector.click(self.u2d, timeout, wait_before_click, wait_after_click, offset, no_raise)

    def click_wait(self, timeout: float = 5.0, wait_before_click: float = 0.5, wait_after_click: float = 0.0, offset: Tuple[float, float] = (0.5, 0.5), no_raise: bool = False):
        """单击操作，但点击前会默认等待0.5秒（可调）"""
        return self.selector.click_wait(self.u2d, timeout, wait_before_click, wait_after_click, offset, no_raise)

    def click_exists(self, timeout: float = 0.0, wait_before_click: float = 0.0, wait_after_click: float = 0.0, offset: Tuple[float, float] = (0.5, 0.5)):
        """单击操作，但不会抛出异常"""
        return self.selector.click(self.u2d, timeout, wait_before_click, wait_after_click, offset, True)

    def info(self, timeout: float = -1.0):
        """获取元素信息"""
        return self.selector.info(self.u2d, timeout)

    def bounds(self, timeout: float = -1.0) -> Tuple[int, int, int, int]:
        """获取元素包围框"""
        return self.selector.bounds(self.u2d, timeout)

    def get_text(self, timeout: float = -1.0) -> str:
        """获取元素文本"""
        return self.selector.get_text(self.u2d, timeout)

    # def long_click(self, timeout: float = 5.0, duration: float = 1.0) -> None:
    #     """长按操作，duration 秒"""
    #     self.get(timeout).long_click(duration)
    #
    # def set_text(self, text: str, timeout: float = 5.0) -> None:
    #     """设置输入文本"""
    #     self.get(timeout).set_text(text)
    #
    # def clear_text(self, timeout: float = 5.0) -> None:
    #     """清空文本框"""
    #     self.get(timeout).clear_text()
    #
    # def swipe(self, sx: int, sy: int, ex: int, ey: int, duration: float = 0.5) -> None:
    #     """指定起止坐标滑动"""
    #     self._d.swipe(sx, sy, ex, ey, duration)
    #
    # def scroll(self, direction: str, **kwargs) -> None:
    #     """滚动：up/down/left/right"""
    #     getattr(self._d, f'scroll_{direction}')(**kwargs)
    #
    # def children(self) -> List[Any]:
    #     """获取子节点列表"""
    #     return self.get().children()
    #
    # def parent(self) -> Any:
    #     """获取父节点"""
    #     return self.get().parent()
    #
    # def info(self, timeout: float = 3.0) -> Dict[str, Any]:
    #     """返回元素属性信息"""
    #     return self.get(timeout).info
    #
    # def exists_then_click(self, timeout: float = 3.0) -> bool:
    #     """
    #     如果存在则点击，返回是否点击成功
    #     """
    #     if self.exists(timeout):
    #         self.click(timeout)
    #         return True
    #     return False
