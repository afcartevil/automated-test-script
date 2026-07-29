import threading
from typing import Dict, Type, Optional

from powertrde import env
from powertrde.utils.simple_event_center import SimpleEventCenter
from tpytest.preset_recorder import PresetRecordGroups, PresetRecorder

# 全局注册表：{ category: { name: { variant: cls } } }
_global_registry: Dict[str, Dict[str, Dict[str, Type]]] = {}
_lock = threading.Lock()


class AwMeta(type):
    """凡是声明了 aw_category/aw_name/variant_key 的子类，自动注册到全局表"""

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        if not cls.__name__.startswith('_') and 'Base' not in cls.__name__:
            # 用 getattr 查所有类（含继承）上的属性
            try:
                cat = getattr(cls, 'aw_category')
                nm = getattr(cls, 'aw_name')
                nnm = getattr(cls, 'aw_nickname')
                var = getattr(cls, 'variant_key')
            except AttributeError:
                return cls
            with _lock:
                _gr = _global_registry.setdefault(cat.lower(), {})
                _gr.setdefault(nm.lower(), {})[var.lower()] = cls
                if nnm:
                    _gr.setdefault(f'{nm}||{nnm}'.lower(), {})[var.lower()] = cls
                    _gr.setdefault(f'||||{nnm}'.lower(), {})[var.lower()] = cls
        return cls


class AwBase(metaclass=AwMeta):
    aw_category: str  # 'logic' 或 'app'
    aw_name: str  # 逻辑/应用名称，如 'login', 'facebook'
    aw_nickname: str = ''  # aw变体昵称，通过昵称可以将筛选范围进一步缩小，比如AW名为Camera的其中一个变体的昵称为VivoCamera
    variant_key: str = ''  # 变体标识，如 'default', 'samsung', 'vivo'
    _template_record_groups: Optional[PresetRecordGroups] = None
    base_shared_signals: SimpleEventCenter = SimpleEventCenter()
    _typed_signals_lock: threading.Lock = threading.Lock()

    @staticmethod
    def merge_aw_name_nickname(aw_name: Optional[str], aw_nickname: Optional[str], to_lower=True):
        if aw_name is None:
            aw_name = ''

        if aw_nickname:
            if aw_name:
                ret = f'{aw_name}||{aw_nickname}'
            else:
                ret = f'||||{aw_nickname}'
        else:
            ret = aw_name

        if to_lower:
            ret = ret.lower()
        return ret

    @classmethod
    def get_typed_signals(cls) -> SimpleEventCenter:
        """
        Lazily initialize and return a per-class SimpleEventCenter.

        Ensures that each subclass of AwBase has its own isolated SimpleEventCenter
        and that initialization is thread-safe.

        :return: SimpleEventCenter instance unique to this class
        """
        # First, try to retrieve without locking (fast path)
        ts = cls.__dict__.get('_typed_signals')
        if isinstance(ts, SimpleEventCenter):
            return ts

        # Slow path: acquire lock and double-check
        with AwBase._typed_signals_lock:
            ts = cls.__dict__.get('_typed_signals')
            if not isinstance(ts, SimpleEventCenter):
                ts = SimpleEventCenter()
                setattr(cls, '_typed_signals', ts)
        return ts

    @property
    def typed_signals(self):
        return self.get_typed_signals()

    @classmethod
    def get_template_record_groups(cls):
        if cls._template_record_groups is None:
            cls._template_record_groups = PresetRecorder.load_static_record_groups(
                env.has_user_env_debug_mode('fallback'))
        return cls._template_record_groups

    @classmethod
    def set_template_record_groups(cls, value: Optional[PresetRecordGroups]):
        cls._template_record_groups = value

    @classmethod
    def get_template_records(cls, group_name: str):
        return cls.get_template_record_groups().get(group_name)

    @classmethod
    def get_typed_template_records(cls):
        """
        获取类级别的“模板录制”类
        """
        return cls.get_template_record_groups().get(cls.aw_name)

    @classmethod
    def get_typed_template(cls, template_key: str, debug_fallback_value=None):
        return cls.get_typed_template_records().get(template_key, debug_fallback_value)

    @property
    def ttr(self):
        """
        同 get_typed_template_records
        获取类级别的“模板录制”类
        """
        return self.get_typed_template_records()

    @property
    def prg(self):
        """
        同 ttr
        获取类级别的“模板录制”类
        """
        return self.ttr

    def tt(self, template_key: str, debug_fallback_value=None):
        """
        同 get_typed_template
        从类级别的“模板录制”中获取录制记录
        """
        return self.get_typed_template(template_key, debug_fallback_value)

    @property
    def template_record_groups(self):
        return self.get_template_record_groups()

    @template_record_groups.setter
    def template_record_groups(self, value: Optional[PresetRecordGroups]):
        self.set_template_record_groups(value)

    @property
    def typed_template_records(self):
        return self.get_typed_template_records()
