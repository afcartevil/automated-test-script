from tests.dzppt.therm.therm_env import ThermEnv
from tpytest.tpypre.pretest_runtime import PretestRuntime


class ThermPretestRuntime(PretestRuntime):
    def __init__(self):
        super().__init__()
        ...

    @property
    def therm_env(self) -> ThermEnv:
        return self.scheme_env
