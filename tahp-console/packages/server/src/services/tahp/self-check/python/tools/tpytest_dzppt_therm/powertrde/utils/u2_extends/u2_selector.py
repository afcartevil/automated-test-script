import copy
import time
from typing import Any, Dict, Optional, List, Callable, Union, Tuple

import uiautomator2 as u2
from uiautomator2 import XPathElementNotFoundError, UiObjectNotFoundError

from powertrde import env
from powertrde.utils.simple_event_center import SimpleEventCenter, SimpleEvent
from powertrde.utils.u2_extends import u2utils
from powertrde.utils.u2_extends.u2utils import U2DeviceProtocol


class U2ElementEvent(SimpleEvent):
    def __init__(self, u2_selector: 'U2Selector', u2_query: Union[u2.UiObject, u2.xpath.XPathSelector],
                 u2_element: Union[u2.UiObject, u2.xpath.XMLElement], *args, sender=None, **kwargs):
        super().__init__('', *args, sender=sender, **kwargs)
        self.u2_selector = u2_selector
        self.u2_query = u2_query
        self.u2_element = u2_element
        self.u2_scope_flag = env.get_user_env_arg('u2_scope_flag', '')

    @property
    def selector(self):
        return self.u2_selector

    @property
    def selector_name(self):
        return self.u2_selector.name

    @property
    def selector_namespace(self):
        return self.u2_selector.namespace

    @property
    def selector_full_name(self):
        return self.u2_selector.full_name


class U2Selector:
    """
    通用 U2 Selector 构造器，支持：
      - 传统属性 Selector（text、resourceId、className…）
      - 丰富 XPath Selector（包含、属性、索引、后代、兄弟等）
      - 自定义查询 Hook
      - 数据驱动配置
    设计原则：
      - 链式调用，便于可读可写
      - 延迟与 Device 绑定，提升复用性
    """

    def __init__(self, name: str = '', namespace: str = ''):
        super().__init__()
        # 命名空间
        self.namespace = namespace
        # 给该筛选器起个名
        self.name = name
        # 存储属性查询条件
        self._attrs: Dict[str, Any] = {}
        # 存储完整 XPath
        self._xpath: Optional[str] = None
        # 可选的自定义查询函数
        self._custom: Optional[Callable[[Union[u2.Device, U2DeviceProtocol]], Any]] = None
        # 当该 selector 正常获取到元素时，发送通知用到的EventCenter
        self._event_centers: List[SimpleEventCenter] = []
        # 临时使用的params
        self.params = None
        # Clone的实例专属的绑定，用于得知该selector附加到哪里
        self.locator_attached_to = None
        self.bound_selector_attached_to = None

    def get_attrs(self):
        return self._attrs

    def get_xpath(self):
        return self._xpath

    def get_event_centers(self):
        return self._event_centers

    @property
    def event_centers(self):
        return self.get_event_centers()

    def clone(self):
        ret = copy.copy(self)
        ret._attrs = dict(ret._attrs)
        return ret

    @property
    def full_name(self):
        return f'{self.namespace}.{self.name}'

    def try_send_element_event(self, u2_query: Union[u2.UiObject, u2.xpath.XPathSelector],
                               u2_element: Union[u2.UiObject, u2.xpath.XMLElement]):
        if self.event_centers:
            e = U2ElementEvent(u2_selector=self, u2_query=u2_query, u2_element=u2_element, sender=self)
            for ec in self.event_centers:
                e.reuse()
                ec.send_event(e)

    def with_params(self, **params) -> 'U2Selector':
        """
        返回根据 params 替换占位符的新 UiSelector
        """
        sel = copy.copy(self)

        # 复制事件中心
        sel._event_centers = list(sel._event_centers)

        # 替换 attrs 中的模板字符串
        sel._attrs = dict(sel._attrs)
        for k, v in sel._attrs.items():
            if isinstance(v, str):
                sel._attrs[k] = v.format(**params)
        # 替换 xpath 模板
        if sel._xpath:
            sel._xpath = sel._xpath.format(**params)
        # 把params存下来
        if sel.params:
            sel.params = dict(sel.params)
            sel.params.update(params)
        else:
            sel.params = params
        return sel

    # -------- 属性 Selector 方法 --------
    def text(self, txt: str) -> 'U2Selector':
        """元素文本完全匹配"""
        self._attrs['text'] = txt
        return self

    def text_contains(self, substring: str) -> 'U2Selector':
        """元素文本部分匹配"""
        self._attrs['textContains'] = substring
        return self

    def text_starts_with(self, prefix: str) -> 'U2Selector':
        """元素文本前缀匹配"""
        self._attrs['textStartsWith'] = prefix
        return self

    def resource_id(self, res_id: str) -> 'U2Selector':
        """通过资源 ID 精确匹配"""
        self._attrs['resourceId'] = res_id
        return self

    def class_name(self, cls: str) -> 'U2Selector':
        """通过类名匹配"""
        self._attrs['className'] = cls
        return self

    def description(self, desc: str) -> 'U2Selector':
        """内容描述精确匹配"""
        self._attrs['description'] = desc
        return self

    def desc_contains(self, substring: str) -> 'U2Selector':
        """内容描述部分匹配"""
        self._attrs['descriptionContains'] = substring
        return self

    def pkg(self, package: str) -> 'U2Selector':
        """应用包名匹配"""
        self._attrs['packageName'] = package
        return self

    def clickable(self, flag: bool = True) -> 'U2Selector':
        """可点击属性"""
        self._attrs['clickable'] = flag
        return self

    def enabled(self, flag: bool = True) -> 'U2Selector':
        """可用状态"""
        self._attrs['enabled'] = flag
        return self

    def focusable(self, flag: bool = True) -> 'U2Selector':
        """是否可获取焦点"""
        self._attrs['focusable'] = flag
        return self

    def scrollable(self, flag: bool = True) -> 'U2Selector':
        """是否可滚动"""
        self._attrs['scrollable'] = flag
        return self

    def checked(self, flag: bool = True) -> 'U2Selector':
        """复选框选中状态"""
        self._attrs['checked'] = flag
        return self

    def long_clickable(self, flag: bool = True) -> 'U2Selector':
        """是否支持长按"""
        self._attrs['longClickable'] = flag
        return self

    def index(self, idx: int) -> 'U2Selector':
        """同级元素索引（0-based）"""
        self._attrs['index'] = idx
        return self

    def instance(self, ins: int) -> 'U2Selector':
        """UiAutomator instance(n) 多实例匹配"""
        self._attrs['instance'] = ins
        return self

    def from_ui_object(self, ui_object: u2.UiObject) -> 'U2Selector':
        self._attrs = dict(ui_object.selector)
        return self

    def from_xpath_selector(self, xpath_selector: u2.xpath.XPathSelector) -> 'U2Selector':
        r = getattr(xpath_selector, '_base_xpath', None)
        if r is not None:
            self._xpath = str(r)
        else:
            self._xpath = None
        return self

    # -------- XPath Selector 方法 --------
    def xpath(self, path: str) -> 'U2Selector':
        """使用完整 XPath 表达式"""
        self._xpath = path
        return self

    def xpath_text_contains(self, expr: str) -> 'U2Selector':
        """XPath 中包含文本条件 (匹配 @text 属性)"""
        self._xpath = f"//*[contains(@text, '{expr}')]"
        return self

    def xpath_text(self, value: str) -> 'U2Selector':
        """XPath 中按 @text 属性精确过滤"""
        self._xpath = f"//*[@text='{value}']"
        return self

    def xpath_attr(self, name: str, value: str) -> 'U2Selector':
        """XPath 中按任意属性过滤"""
        self._xpath = f"//*[@{name}='{value}']"
        return self

    def xpath_text_starts_with(self, expr: str) -> 'U2Selector':
        """XPath 中文本前缀匹配 (匹配 @text 开头)"""
        self._xpath = f"//*[starts-with(@text, '{expr}')]"
        return self

    def xpath_text_ends_with(self, expr: str) -> 'U2Selector':
        """XPath 中文本后缀匹配 (匹配 @text 结尾)"""
        # substring(@text, string-length(@text) - string-length(expr) + 1) = expr
        self._xpath = (
            f"//*[substring(@text, string-length(@text) - string-length('{expr}') + 1) = '{expr}']"
        )
        return self

    def xpath_index(self, path: str, idx: int) -> 'U2Selector':
        """在给定 XPath 路径中选取第 idx 个节点 (1-based)"""
        self._xpath = f"({path})[{idx}]"
        return self

    def xpath_descendant(self, ancestor: str, descendant: str) -> 'U2Selector':
        """匹配后代节点"""
        self._xpath = f"{ancestor}//{descendant}"
        return self

    def xpath_following_sibling(self, node: str) -> 'U2Selector':
        """匹配后继兄弟节点"""
        self._xpath = f"//{node}/following-sibling::*"
        return self

    # -------- 自定义查询 Hook --------
    def custom(self, func: Callable[[Union[u2.Device, U2DeviceProtocol]], Any]) -> 'U2Selector':
        """传入自定义查询函数，覆盖默认逻辑"""
        self._custom = func
        return self

    # -------- 数据驱动 构造 --------
    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> 'U2Selector':
        """
        通过字典配置批量构造：
          {'text':'登录', 'resourceId':'com.app:id/btn'}
          {'xpath':'//button'}
        """
        sel = cls()
        if 'xpath' in config:
            sel.xpath(config['xpath'])
        for k, v in config.items():
            if k == 'xpath':
                continue
            if hasattr(sel, k):
                getattr(sel, k)(v)
            else:
                sel._attrs[k] = v
        return sel

    # -------- 内部查询逻辑 --------
    def _using_xpath(self) -> bool:
        return bool(self._xpath)

    @property
    def is_using_xpath(self):
        return self._using_xpath()

    def to_query(self, d: Union[u2.Device, U2DeviceProtocol]) -> Any:
        # 优先执行自定义查询
        if self._custom:
            return self._custom(d)
        # XPath 查询
        if self._using_xpath():
            return d.xpath(self._xpath)  # type: ignore
        # 属性查询
        return d(**self._attrs)

    # -------- 执行与操作 --------
    def new_not_found_error(self):
        return XPathElementNotFoundError({'xpath': str(self._xpath)}) if self._using_xpath() else UiObjectNotFoundError({'code': -32002, 'data': str(self._attrs)})

    def get(self, d: Union[u2.Device, U2DeviceProtocol], timeout: float = 5.0, raise_on_not_found: bool = True, post_wait: float = 0.0) -> Union[u2.UiObject, u2.xpath.XMLElement, None]:
        """等待并返回单一查询结果"""
        return self.get_by_query(self.to_query(d), timeout, raise_on_not_found, post_wait)

    def get_by_query(self, query, timeout: float = 5.0, raise_on_not_found: bool = True, post_wait: float = 0.0) -> Union[u2.UiObject, u2.xpath.XMLElement, None]:
        """等待并返回单一查询结果"""
        q = query
        if self._using_xpath():
            if raise_on_not_found:
                r = q.get(timeout=timeout)
                if post_wait > 0:
                    time.sleep(post_wait)
                    r = q.get(timeout=-1.0)
                self.try_send_element_event(q, r)
                return r
            else:
                if not q.wait(timeout=timeout):
                    return None
                if post_wait > 0:
                    time.sleep(post_wait)
                    if not q.wait(timeout=-1.0):
                        return None
                r = q.get_last_match()
                self.try_send_element_event(q, r)
                return r
        else:
            if raise_on_not_found:
                q.must_wait(timeout=timeout)
            else:
                if not q.wait(timeout=timeout):
                    return None
            if post_wait > 0:
                time.sleep(post_wait)
            self.try_send_element_event(q, q)
            return q

    def wait(self, d: Union[u2.Device, U2DeviceProtocol], timeout: float = 10.0, raise_on_false_result: bool = False,
             post_wait: float = 0.0) -> bool:
        """等待元素，返回是否成功等到元素"""
        q = self.to_query(d)
        if q.wait(timeout=timeout):
            if post_wait > 0:
                time.sleep(post_wait)
                if not q.exists:
                    if raise_on_false_result:
                        raise self.new_not_found_error()
                    return False
            return True
        else:
            if raise_on_false_result:
                raise self.new_not_found_error()
            return False

    def wait_gone(self, d: Union[u2.Device, U2DeviceProtocol], timeout: float = 10.0, raise_on_false_result: bool = False,
                  post_wait: float = 0.0) -> bool:
        """等待元素消失，返回是否成功等到元素消失"""
        q = self.to_query(d)
        if q.wait_gone(timeout=timeout):
            if post_wait > 0:
                time.sleep(post_wait)
                if q.exists:
                    if raise_on_false_result:
                        raise self.new_not_found_error()
                    return False
            return True
        else:
            if raise_on_false_result:
                raise self.new_not_found_error()
            return False

    def exists(self, d: Union[u2.Device, U2DeviceProtocol]) -> bool:
        """元素存在判断"""
        return self.to_query(d).exists

    def all(self, d: Union[u2.Device, U2DeviceProtocol]) -> List[Any]:
        """返回所有匹配元素列表"""
        if not self._using_xpath():
            raise Exception('Not support "all" for non-xpath selector!')
        return self.to_query(d).all()

    def click(self, d: Union[u2.Device, U2DeviceProtocol], timeout: float = 5.0, wait_before_click: float = 0.0, wait_after_click: float = 0.0,
              offset: Tuple[float, float] = (0.5, 0.5), no_raise: bool = False) -> Union[u2.UiObject, u2.xpath.XMLElement, None]:
        """单击操作"""
        q = self.to_query(d)
        return u2utils._wait_and_click(d, q, timeout=timeout, post_wait=wait_before_click,
                                       wait_after_click=wait_after_click, offset=offset, no_raise=no_raise,
                                       on_element_found=lambda elem: self.try_send_element_event(q, elem),
                                       perform_click=True)

    def click_wait(self, d: Union[u2.Device, U2DeviceProtocol], timeout: float = 5.0, wait_before_click: float = 0.5,
                   wait_after_click: float = 0.0, offset: Tuple[float, float] = (0.5, 0.5), no_raise: bool = False):
        """单击操作，但点击前会默认等待0.5秒（可调）"""
        return self.click(d, timeout, wait_before_click, wait_after_click, offset, no_raise)

    def click_exists(self, d: Union[u2.Device, U2DeviceProtocol], timeout: float = 0.0, wait_before_click: float = 0.0, wait_after_click: float = 0.0, offset: Tuple[float, float] = (0.5, 0.5)):
        """单击操作，但不会抛出异常"""
        return self.click(d, timeout, wait_before_click, wait_after_click, offset, True)

    def info(self, d: Union[u2.Device, U2DeviceProtocol], timeout: float = -1.0):
        """获取元素信息"""
        return self.get(d, timeout=timeout).info
        # if self._using_xpath():
        #     return self.get(d, timeout=timeout).info
        # else:
        #     if timeout > 0:
        #         return self.get(d, timeout=timeout).info
        #     else:
        #         return self.to_query(d).info

    def bounds(self, d: Union[u2.Device, U2DeviceProtocol], timeout: float = -1.0) -> Tuple[int, int, int, int]:
        """获取元素包围框"""
        if self._using_xpath():
            return self.get(d, timeout=timeout).bounds
        else:
            return self.get(d, timeout=timeout).bounds()
        # if self._using_xpath():
        #     return self.get(d, timeout=timeout).bounds
        # else:
        #     if timeout > 0:
        #         return self.get(d, timeout=timeout).bounds()
        #     else:
        #         return self.to_query(d).bounds()

    def get_text(self, d: Union[u2.Device, U2DeviceProtocol], timeout: float = -1.0) -> str:
        """获取元素文本"""
        if self._using_xpath():
            return self.get(d, timeout=timeout).text
        else:
            q = self.to_query(d)
            self.get_by_query(q, timeout=timeout)
            q.jsonrpc.getText(q.selector)
            # return self.to_query(d).get_text(timeout=timeout)

    def bind(self, d: Union[Union[u2.Device, U2DeviceProtocol], Callable[[], Union[u2.Device, U2DeviceProtocol]], None] = None):
        from powertrde.utils.u2_extends.u2_bound_selector import U2BoundSelector
        return U2BoundSelector(self, d)

    def __repr__(self):
        if self._using_xpath():
            return f"UiSelector(xpath='{self._xpath}')"
        return f"UiSelector(attrs={self._attrs})"
