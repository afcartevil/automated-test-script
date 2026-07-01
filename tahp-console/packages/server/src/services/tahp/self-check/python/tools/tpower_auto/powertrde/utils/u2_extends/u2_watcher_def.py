from dataclasses import field, dataclass
from typing import List, Union, Callable
import uiautomator2 as u2
from uiautomator2.xpath import XPathSelector


@dataclass
class U2WatcherDef:
    """
    定义一条基于 uiautomator2 XPath Watcher 的规则：
      - name: Watcher 唯一标识，用于注册和移除
      - xpaths: 一组 XPath 字符串，按序链式匹配（.when(xpath1).when(xpath2)...）
      - action: 可以是以下任意一种：
          1. Callable(d: Device, el: XPathSelector):  匹配成功后自定义回调
          2. "click":                                 点击最后匹配的元素
          3. 其他按键名称字符串（如 "home", "back", "enter", "delete"等），
             匹配成功后调用 device.press(key)
      - tags: 可选，用于分组查询
      - priority: 整数，注册顺序优先级，值越大先注册先触发
      - description: 可选文字说明
    """
    name: str = ""  # 允许空字符串，方便从属性名填充
    xpaths: List[str] = field(default_factory=list)
    action: Union[Callable[[u2.Device, XPathSelector], None], Callable[[u2.Device], None], Callable[[XPathSelector], None], Callable[[], None], str] = None
    tags: List[str] = field(default_factory=list)
    priority: int = 0
    description: str = ""

    def register(self, device: u2.Device, remove_exist_same_name_watcher=False) -> None:
        """
        将此 WatcherDefinition 注册到 u2.Device 上：
          1. 如果已存在同名 watcher，先移除
          2. 按 xpaths 链式调用 .when(...)
          3. 根据 action 类型做不同处理：
               - Callable 时调用 w.call(action)
               - "click" 时包装成点击函数
               - 其他按键字符串时包装成按键函数
        """
        if not self.name:
            raise ValueError('U2 Watcher name must not be empty!')

        w = device.watcher  # 获取 Watcher 实例
        if remove_exist_same_name_watcher:
            # 1) 移除同名（如果存在）
            try:
                w.remove(self.name)
            except Exception:
                pass

        # 2) 创建新的 XPathWatcher
        w_inst = w(self.name)
        # 3) 链式添加所有 xpaths
        for xp in self.xpaths:
            w_inst.when(xp)

        # 4) 结合 action 字段决定绑定方式
        if callable(self.action):
            # 直接把 callable 注册为回调，签名可接 d 和 el
            w_inst.call(self.action)

        elif isinstance(self.action, str):
            key = self.action.lower()
            if key == "click":
                def _inner_click(selector: XPathSelector):
                    selector.get_last_match().click()

                w_inst.call(_inner_click)
            else:
                # 当成按键名称，调用 device.press(key)
                # uiautomator2 支持的 key 值包括：
                # "home","back","left","right","up","down","center","search",
                # "enter","delete","del","recent","volume_up","menu","volume_down",
                # "volume_mute","camera","power"
                def _inner_press(d):
                    d.press(key)

                w_inst.call(_inner_press)
        else:
            raise ValueError(f"The action of Watcher '{self.name}' must be callable or a string of 'click'/key name")

    def unregister(self, device: u2.Device) -> None:
        """
        从 device 上移除此 watcher（按名称）。
        """
        try:
            if self.name:
                device.watcher.remove(self.name)
        except Exception:
            pass
