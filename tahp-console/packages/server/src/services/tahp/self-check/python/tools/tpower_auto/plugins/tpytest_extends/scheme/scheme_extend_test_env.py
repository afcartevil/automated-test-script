from tpytest.scheme.scheme_test_env import SchemeTestEnv, get_scheme_env
from tpy_aw.u2d_test_helper import U2DTestHelper


class SchemeExtendTestEnv(SchemeTestEnv):
    @property
    def u2d_helper(self) -> U2DTestHelper:
        return super().u2d_helper

    @property
    def c_u2d_helper(self) -> U2DTestHelper:
        return super().c_u2d_helper


# ------------------------------------------------------------------------

def get_scheme_extend_env() -> SchemeExtendTestEnv:
    env_ins = get_scheme_env()
    if not isinstance(env_ins, SchemeExtendTestEnv):
        raise Exception(
            f'Current scheme env class is {env_ins.__class__.__name__} but not {SchemeExtendTestEnv.__name__}')
    return env_ins
