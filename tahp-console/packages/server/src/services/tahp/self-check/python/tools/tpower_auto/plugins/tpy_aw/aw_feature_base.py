from ctypes import cast
from typing import Type, Optional

from tpy_aw.aw_device_base import AwDeviceBase, T


class AwFeatureBase(AwDeviceBase):
    aw_category = 'feature'

    def get_feature_aw(self, ft_name: str, variant: Optional[str] = None, no_raise: bool = False):
        try:
            from tpy_aw.aw_registry import get_aw_feature
            return get_aw_feature(self.u2d_helper, ft_name, variant)
        except Exception:
            if not no_raise:
                raise
        return None

    def get_casted_feature_aw(self, cast_type: Type[T], ft_name: Optional[str] = None, variant: Optional[str] = None, no_raise: bool = False) -> Optional[T]:
        return cast(cast_type, self.get_feature_aw(ft_name or cast_type.aw_name, variant, no_raise))
