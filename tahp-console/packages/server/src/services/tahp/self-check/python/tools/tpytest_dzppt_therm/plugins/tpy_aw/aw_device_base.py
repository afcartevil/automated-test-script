from contextlib import contextmanager
from typing import Optional, List, Union, TypeVar, cast, Type

from powertrde.utils.u2_extends.u2_watcher_def import U2WatcherDef
from powertrde.utils.u2_extends.u2_watcher_manager import U2WatcherManager
from tpytest.aw_framework.aw_base import AwBase

T = TypeVar('T')


class AwDeviceBase(AwBase):
    def __init__(self):
        super().__init__()
        from tpy_aw.u2d_test_helper import U2DTestHelper
        self.u2d_helper: Optional[U2DTestHelper] = None

    def get_app_aw(self, app_name: str, variant: Optional[str] = None, no_raise: bool = False, app_nickname: Optional[str] = None, base_type: Optional[type] = None):
        try:
            from tpy_aw.aw_registry import get_aw_app
            return get_aw_app(self.u2d_helper, app_name, variant, app_nickname, base_type)
        except Exception:
            if not no_raise:
                raise
        return None

    def get_casted_app_aw(self, cast_type: Type[T], app_name: Optional[str] = None, variant: Optional[str] = '',
                          no_raise: bool = False, app_nickname: Optional[str] = '') -> Optional[T]:
        return cast(cast_type, self.get_app_aw(app_name or cast_type.aw_name, (cast_type.variant_key if variant is None else variant), no_raise, (cast_type.aw_nickname if app_nickname is None else app_nickname), cast_type))

    @property
    def device_id(self):
        return self.u2d_helper.device_id

    @property
    def device_real_sn(self):
        return self.u2d_helper.device_real_sn

    def get_u2d(self):
        return self.u2d_helper.u2d

    @property
    def u2d(self):
        return self.get_u2d()

    @property
    def und_u2(self):
        return self.u2d_helper.und_u2

    @property
    def und(self):
        return self.u2d_helper.und

    @property
    def u2_watcher_manager(self):
        return U2WatcherManager.get_instance()

    def u2_apply_watchers(self, *, names: Optional[List[str]] = None, tags_any: Optional[List[str]] = None,
                          tags_all: Optional[List[str]] = None, tags_none: Optional[List[str]] = None,
                          watchers: Optional[Union[List[Union[U2WatcherDef, type]], Union[U2WatcherDef, type]]] = None):
        return self.u2_watcher_manager.apply_watchers(self.u2d, names=names, tags_any=tags_any, tags_all=tags_all,
                                                    tags_none=tags_none, watchers=watchers)

