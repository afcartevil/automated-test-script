from typing import List

from powertrde.framework.import_init_meta import ImportInitMeta
from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_manager import U2WatcherManager


class U2WatcherRegister(metaclass=ImportInitMeta):
    """
    “更魔法”的批量注册基类：
      - 子类可声明若干 U2WatcherDef（name 可留空）
      - 属性名称若没有指定 name，将自动填为该属性名
      - .build() 会将所有定义自动 add_definition 到指定 manager（或全局单例）
    """
    _has_registered_this_class = False
    watcher_def_list = None

    @classmethod
    def _import_init(cls):
        if cls.__name__ != 'U2WatcherRegister':
            cls._collect_definitions()
            cls.register_if_needed()

    @classmethod
    def _collect_definitions(cls):
        """
        遍历当前类属性，找出所有 U2WatcherDef，对 name 为空的用属性名填充，
        然后按 priority 降序返回。
        """
        defs: List[U2WatcherDef] = []
        for attr_name, attr_val in vars(cls).items():
            if isinstance(attr_val, U2WatcherDef):
                # 如果定义时未填写 name，则使用属性名
                if not attr_val.name:
                    attr_val.name = attr_name
                defs.append(attr_val)
        cls.watcher_def_list = sorted(defs, key=lambda w: w.priority, reverse=True)

    @classmethod
    def register_if_needed(cls):
        if not cls._has_registered_this_class:
            cls._has_registered_this_class = True
            U2WatcherManager.get_instance().extends_def(cls.watcher_def_list)
