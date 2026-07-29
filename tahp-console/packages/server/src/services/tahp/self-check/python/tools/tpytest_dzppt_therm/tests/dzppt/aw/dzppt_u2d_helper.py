from typing import TYPE_CHECKING
from tpy_aw.u2d_test_helper import U2DTestHelper

_MixinBase = U2DTestHelper


def _type_checking():
    if not TYPE_CHECKING:
        # 运行时实际继承自 object
        global _MixinBase
        _MixinBase = object


_type_checking()


class DzpptU2DTestHelper(_MixinBase):
    ...


def put_res():
    from tpytest.scheme.scheme_test_env import get_scheme_env
    get_scheme_env().c