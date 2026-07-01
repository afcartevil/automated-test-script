from tests.xttx.xssx.xssx_env import XssxEnv
from tpytest.tpypre.pretest_runtime import PretestRuntime


class XssxPretestRuntime(PretestRuntime):
    def __init__(self):
        super().__init__()
        ...

    @property
    def xssx_env(self) -> XssxEnv:
        return self.scheme_env
