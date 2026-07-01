from tests.xttx.xttx_env import XttxEnv
from tests.xttx.xssx.xssx_config import XssxConfig
from tpytest.scheme.scheme_test_env import get_scheme_env


class XssxEnv(XttxEnv):
    option_user_config_class_type = XssxConfig

    def __init__(self):
        super().__init__()
        ...

    @property
    def user_config(self) -> XssxConfig:
        return super().user_config

    def try_fill_devices(self, forced=False):
        super().try_fill_devices(forced=forced)
        ...


# ------------------------------------------------------------------------

def get_xssx_env() -> XssxEnv:
    env_ins = get_scheme_env()
    if not isinstance(env_ins, XssxEnv):
        raise Exception(f'Current scheme env class is {env_ins.__class__.__name__} but not {XssxEnv.__name__}')
    return env_ins
