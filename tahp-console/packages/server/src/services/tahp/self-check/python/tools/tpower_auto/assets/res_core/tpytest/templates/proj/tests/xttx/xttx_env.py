from typing import cast
from tests.xttx.aw.xttx_u2d_helper import XttxU2DTestHelper
from tpytest.scheme.scheme_test_env import get_scheme_env
from tpytest_extends.scheme.scheme_extend_test_env import SchemeExtendTestEnv


class XttxEnv(SchemeExtendTestEnv):
    option_user_u2d_helper_class_type = XttxU2DTestHelper

    def __init__(self):
        super().__init__()
        ...

    @property
    def u2d_helper(self) -> XttxU2DTestHelper:
        return cast(XttxU2DTestHelper, super().u2d_helper)

    @property
    def c_u2d_helper(self) -> XttxU2DTestHelper:
        return cast(XttxU2DTestHelper, super().c_u2d_helper)


# ------------------------------------------------------------------------------

def get_xttx_env() -> XttxEnv:
    env_ins = get_scheme_env()
    if not isinstance(env_ins, XttxEnv):
        raise Exception(f'Current scheme env class is {env_ins.__class__.__name__} but not {XttxEnv.__name__}')
    return env_ins
