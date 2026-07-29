from tests.dzppt.dzppt_env import DzPptEnv
from tests.dzppt.therm.therm_config import ThermConfig
from tests.dzppt.therm.therm_task_session_life import ThermTaskSessionLife
from tpytest.scheme.scheme_test_env import get_scheme_env


class ThermEnv(DzPptEnv):
    option_user_config_class_type = ThermConfig
    option_user_session_life_class_type = ThermTaskSessionLife

    def __init__(self):
        super().__init__()
        ...

    @property
    def user_config(self) -> ThermConfig:
        return super().user_config

    def try_fill_devices(self, forced=False):
        super().try_fill_devices(forced=forced)
        ...


# ------------------------------------------------------------------------

def get_therm_env() -> ThermEnv:
    env_ins = get_scheme_env()
    if not isinstance(env_ins, ThermEnv):
        raise Exception(f'Current scheme env class is {env_ins.__class__.__name__} but not {ThermEnv.__name__}')
    return env_ins
