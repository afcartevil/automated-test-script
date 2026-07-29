import threading
from collections import defaultdict
from contextlib import contextmanager
from typing import Optional, List, Dict, Union
import uiautomator2 as u2
from deprecation import deprecated

from powertrde.framework.tran_logger import t_log
from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2utils import U2DeviceProtocol


class U2WatcherManager:
    """
    管理多条 U2WatcherDef，支持按 name/tag 查询、动态增删，
    并能为 u2.Device 提供临时注册/注销服务。
    """
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def purge_instance(cls):
        cls._instance = None

    def __init__(self):
        self._definitions: Dict[str, U2WatcherDef] = {}
        self._tag_index: Dict[str, List[str]] = {}
        self._lock = threading.RLock()
        self._lock_stack = threading.RLock()
        self.level_watcher = defaultdict(dict) #记录每一层with，有哪些watcher name,{'device1': {'1': ["ok"], '2': ['ok', 'gotit']}, 'device2': {'1': [ok]}}

    def add_def(self, wdef: U2WatcherDef) -> None:
        """
        添加或更新一条 U2WatcherDef，同时维护 tag 索引。
        """
        with self._lock:
            self._definitions[wdef.name] = wdef
            for tag in wdef.tags:
                self._tag_index.setdefault(tag, []).append(wdef.name)

    def extends_def(self, def_list: List[U2WatcherDef]) -> None:
        """
        添加或更新多条 U2WatcherDef，同时维护 tag 索引。
        """
        if def_list:
            with self._lock:
                for d in def_list:
                    self._definitions[d.name] = d
                    for tag in d.tags:
                        self._tag_index.setdefault(tag, []).append(d.name)

    def remove_def(self, name: str) -> None:
        """
        按名称删除一条定义，同时更新 tag 索引。
        """
        with self._lock:
            wdef = self._definitions.pop(name, None)
            if not wdef:
                return
            for tag in wdef.tags:
                if tag in self._tag_index:
                    self._tag_index[tag] = [n for n in self._tag_index[tag] if n != name]
                    if not self._tag_index[tag]:
                        del self._tag_index[tag]

    def get_by_name(self, name: str) -> Optional[U2WatcherDef]:
        return self._definitions.get(name)

    def get_by_tag(self, tag: str) -> List[U2WatcherDef]:
        """
        按标签返回对应的所有定义，按 priority 降序排序。
        """
        names = self._tag_index.get(tag, [])
        return sorted(
            (self._definitions[n] for n in names if n in self._definitions),
            key=lambda w: w.priority,
            reverse=True
        )

    def list_all(self) -> List[U2WatcherDef]:
        """
        列出所有定义，按 priority 降序。
        """
        return sorted(self._definitions.values(), key=lambda w: w.priority, reverse=True)

    def _device_existing_names(self, device: Union[u2.Device, U2DeviceProtocol]) -> List[str]:
        """
        返回 device 当前已注册 watcher 的名称列表。
        uiautomator2 内部存储在 device.watcher._watchers 中。
        """
        return [h["name"] for h in getattr(device.watcher, "_watchers", [])]

    # def register_to_device(
    #         self,
    #         device: Union[u2.Device, U2DeviceProtocol],
    #         names: Optional[List[str]] = None,
    #         tags: Optional[List[str]] = None,
    #         run: bool = True
    # ) -> None:
    #     """
    #     将指定 names 或 tags 对应的定义注册到 device。
    #     - names: 直接按名称列表匹配
    #     - tags:  按标签匹配，若同名也避免重复
    #     - names & tags 都为 None 时注册全部定义
    #     注册后如果 run=True，会调用 device.watcher.start() 让 watcher 后台轮询。
    #     """
    #     with self._lock:
    #         to_register: List[U2WatcherDef] = []
    #
    #         if names:
    #             for name in names:
    #                 wdef = self._definitions.get(name)
    #                 if wdef:
    #                     to_register.append(wdef)
    #
    #         if tags:
    #             for tag in tags:
    #                 for name in self._tag_index.get(tag, []):
    #                     wdef = self._definitions.get(name)
    #                     if wdef and wdef not in to_register:
    #                         to_register.append(wdef)
    #
    #         if names is None and tags is None:
    #             to_register = list(self._definitions.values())
    #
    #         # 按 priority 降序
    #         to_register.sort(key=lambda w: w.priority, reverse=True)
    #
    #         # # 移除 device 上同名的 watcher，避免重复
    #         # existing = self._device_existing_names(device)
    #         # for wdef in to_register:
    #         #     if wdef.name in existing:
    #         #         try:
    #         #             device.watcher.remove(wdef.name)
    #         #         except Exception:
    #         #             pass
    #
    #         # 注册到 device
    #         for wdef in to_register:
    #             wdef.register(device, _post_register)
    #
    #         if run:
    #             try:
    #                 device.watcher.start()
    #             except Exception:
    #                 pass
    #
    # def unregister_from_device(
    #         self,
    #         device: Union[u2.Device, U2DeviceProtocol],
    #         names: Optional[List[str]] = None,
    #         tags: Optional[List[str]] = None
    # ) -> None:
    #     """
    #     从 device 上移除指定 names 或 tags 对应的 watcher。若两者都 None，则移除所有已知定义的 watcher。
    #     """
    #     with self._lock:
    #         to_remove = set()
    #         if names:
    #             to_remove.update(names)
    #         if tags:
    #             for tag in tags:
    #                 to_remove.update(self._tag_index.get(tag, []))
    #         if names is None and tags is None:
    #             to_remove.update(self._device_existing_names(device))
    #
    #         for name in to_remove:
    #             try:
    #                 device.watcher.remove(name)
    #             except Exception:
    #                 pass

    @deprecated("该方法管理成本太高，请使用 apply_watchers() 替代")
    def start_watchers(
            self,
            device: Union[u2.Device, U2DeviceProtocol],
            *,
            names: Optional[List[str]] = None,
            tags_any: Optional[List[str]] = None,
            tags_all: Optional[List[str]] = None,
            tags_none: Optional[List[str]] = None,
            watchers: Optional[List[Union[U2WatcherDef, type]]] = None,
            is_import_all: bool = False
    ):
        """该方法管理成本太高，请使用 apply_watchers() 替代"""
        t_log.warning("start_watchers 方法管理成本太高，请使用 apply_watchers() 替代")
        return self._start_watchers(
            device,
            names=names,
            tags_any=tags_any,
            tags_all=tags_all,
            tags_none=tags_none,
            watchers=watchers,
            is_import_all=is_import_all
        )

    def _start_watchers(
            self,
            device: Union[u2.Device, U2DeviceProtocol],
            *,
            names: Optional[List[str]] = None,
            tags_any: Optional[List[str]] = None,
            tags_all: Optional[List[str]] = None,
            tags_none: Optional[List[str]] = None,
            watchers: Optional[List[Union[U2WatcherDef, type]]] = None,
            is_import_all: bool = False
    ):
        """
        参数：
        - device:                 u2.Device 实例
        - names:                  List[str]，按名称注册（OR 关系）
        - tags_any:               List[str]，任意标签匹配即可注册（OR 关系）
        - tags_all:               List[str]，必须同时包含所有标签才注册（AND 关系）
        - tags_none:              List[str]，只要包含其中任意标签就跳过注册
        - watchers:               List[U2WatcherDef 或 包含 watcher_def_list 属性的类]，
                                  用于临时注册（不加入 manager._definitions）
        - is_import_all:          bool，是否导入所有 name项
        """
        # 1. 停止并清空所有 watcher
        try:
            if self.current_watcher_level(device.serial) <= 1:  # 只有最外层的时候才reset以前的watcher
                device.watcher.stop()
                device.watcher.reset()
        except Exception:
            pass

        _post_register = []
        self.level_watcher[device.serial][self.current_watcher_level(device.serial)] = _post_register

        # 2. 从 manager 中筛选要注册的定义
        to_register: List[U2WatcherDef] = []

        # 如果提供 names，则优先按 names 注册
        if names:
            for name in names:
                wdef = self.get_by_name(name)
                if wdef:
                    to_register.append(wdef)
        else:
            # 否则按标签筛选
            all_defs = self.list_all()
            for wdef in all_defs:
                tags = set(wdef.tags or [])

                # tags_none 优先：若定义标签与 tags_none 有交集，则跳过
                if tags_none and tags.intersection(tags_none):
                    continue

                # tags_all：必须同时包含所有 tags_all
                if tags_all:
                    if not tags.issuperset(set(tags_all)):
                        continue

                # tags_any：只要包含任一标签即通过
                if tags_any:
                    if not tags.intersection(set(tags_any)):
                        continue

                # 若 tags_any/tags_all 其中条件满足，就注册
                if tags_all or tags_any or is_import_all:
                    to_register.append(wdef)

        # 按 priority 降序注册
        to_register.sort(key=lambda _w: _w.priority, reverse=True)

        for wdef in to_register:
            wdef.register(device, _post_register)

        # 3. 注册临时 watchers
        if watchers:
            for w in watchers:
                if isinstance(w, U2WatcherDef):
                    w.register(device, _post_register)
                else:
                    # 假设 “w” 是自定义类，具有 .watcher_def_list 属性
                    for sub_def in getattr(w, "watcher_def_list", []):
                        sub_def.register(device, _post_register)

        # 4. 启动所有 watcher
        try:
            if self.current_watcher_level(device.serial) <= 1:
                device.watcher.start()
            # t_log.debug(f"{device.serial}当前层级：{self.current_watcher_level(device.serial)}; _watchers：{device.watcher._watchers}")
        except Exception as e:
            t_log.error(f'Start watchers error: {e}')

    def stop_watchers(self, device: Union[u2.Device, U2DeviceProtocol]):
        """
        停止并清空所有 watcher
        """
        try:
            if self.current_watcher_level(device.serial) <= 1:  # 只有最外层的时候才reset以前的watcher
                device.watcher.stop()
                device.watcher.reset()
            else:
                watcher_names = self.level_watcher[device.serial][self.current_watcher_level(device.serial)]
                for name in watcher_names:
                    device.watcher.remove(name)
        except Exception as e:
            t_log.error(f'Stop watchers error: {e}')

    @contextmanager
    def apply_watchers(
            self,
            device: Union[u2.Device, U2DeviceProtocol],
            *,
            names: Optional[List[str]] = None,
            tags_any: Optional[List[str]] = None,
            tags_all: Optional[List[str]] = None,
            tags_none: Optional[List[str]] = None,
            watchers: Optional[Union[List[Union[U2WatcherDef, type]], U2WatcherDef, type]] = None
    ):
        """
        上下文管理：临时为 device 注册匹配条件的 watcher，并在退出时清理。

        参数：
          - device:                 u2.Device 实例
          - names:                  List[str]，按名称注册（OR 关系）
          - tags_any:               List[str]，任意标签匹配即可注册（OR 关系）
          - tags_all:               List[str]，必须同时包含所有标签才注册（AND 关系）
          - tags_none:              List[str]，只要包含其中任意标签就跳过注册
          - watchers:               List[U2WatcherDef 或 包含 watcher_def_list 属性的类]，
                                    用于临时注册（不加入 manager._definitions）

        规则：
          1. 先停止并 reset device 上所有 watcher。
          2. manager 中的定义会被筛选后注册：
             - 如果 names 不为 None，则任何 name 在 names 中的都会注册；
             - 否则按标签匹配：
               • 如果 tags_any 不为 None，则只要定义的 tags 有任一元素在 tags_any 中就注册；
               • 如果 tags_all 不为 None，则定义的 tags 必须包含 tags_all 所有元素才注册；
               • 如果 tags_none 不为 None，则定义的 tags 不能包含 tags_none 中的任一元素；
               • 如果 tags_any/tags_all 都为 None，就注册 manager 中所有定义。
          3. 执行 watchers 参数中传入的临时 watcher（如果有），直接调用 .register(device)。
          4. 调用 device.watch.start() 让所有刚注册的 watcher 生效。
          5. yield 控制权给调用方。
          6. finally：
             - 调用 device.watch.stop() + device.watch.reset() 清空所有 watcher；
             - （可选）如果想恢复进入前已有的 watcher，请在注释区解开并实现；
             - 临时 watchers 无需额外处理，因为 .reset() 已清空它们。
        """
        if not isinstance(watchers, list):
            watchers = [watchers]

        with self._lock_stack:
            level = self.current_watcher_level(device.serial)+1
            self.level_watcher[device.serial][level] = []

        self.start_watchers(device=device, names=names, tags_any=tags_any, tags_all=tags_all, tags_none=tags_none,
                            watchers=watchers)

        try:
            yield
        finally:
            self.stop_watchers(device=device)
            with self._lock_stack:
                del(self.level_watcher[device.serial][level])

            # 如果需要恢复先前存在的 watcher，可在此进行：
            # saved_names = [...]  # 在方法开头记录 device.watch._watchers
            # for name in saved_names:
            #     orig_def = self.manager.get_by_name(name)
            #     if orig_def:
            #         orig_def.register(device)
            # try:
            #     device.watch.start()
            # except Exception:
            #     pass

            # 临时 watchers 会被 reset() 一并清除，无需额外移除

    def current_watcher_level(self, serial) -> int:
        return len(self.level_watcher[serial])

    def remove_watchers(
            self,
            device: Union[u2.Device, U2DeviceProtocol],
            *,
            names: Optional[List[str]] = None,
            watchers: Optional[List[Union[U2WatcherDef, type]]] = None
    ):
        """
        参数：
        - device:                 u2.Device 实例
        - names:                  List[str]，按名称移除
        - watchers:               List[U2WatcherDef 或 包含 watcher_def_list 属性的类]，
                                  用于移除临时注册
        """

        # 2. 从 manager 中筛选要注册的定义
        un_register: List[U2WatcherDef] = []

        # 如果提供 names，则优先按 names 注册
        if names:
            for name in names:
                wdef = self.get_by_name(name)
                if wdef:
                    un_register.append(wdef)

        # 按 priority 降序注册
        un_register.sort(key=lambda _w: _w.priority, reverse=True)

        for wdef in un_register:
            wdef.unregister(device)

        # 3. 移除临时 watchers
        if watchers:
            for w in watchers:
                if isinstance(w, U2WatcherDef):
                    w.unregister(device)
                else:
                    # 假设 “w” 是自定义类，具有 .watcher_def_list 属性
                    for sub_def in getattr(w, "watcher_def_list", []):
                        sub_def.unregister(device)
