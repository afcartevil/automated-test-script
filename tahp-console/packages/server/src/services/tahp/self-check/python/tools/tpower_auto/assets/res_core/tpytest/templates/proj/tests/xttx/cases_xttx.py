from tests.xttx.xttx_env import XttxEnv
from tests.xttx.aw.xttx_u2d_helper import XttxU2DTestHelper
from tpytest_extends.scheme.cases_scheme import CasesScheme


class CasesXttx(CasesScheme):
    @property
    def scheme_env(self) -> XttxEnv:
        return self.get_scheme_env()

    @classmethod
    def get_scheme_env(cls) -> XttxEnv:
        return super().get_scheme_env()

    @property
    def u2d_helper(self) -> XttxU2DTestHelper:
        return super().u2d_helper

    @property
    def c_u2d_helper(self) -> XttxU2DTestHelper:
        return super().c_u2d_helper

    @property
    def o_u2d_helper(self) -> XttxU2DTestHelper:
        return self.o_u2d_helper
