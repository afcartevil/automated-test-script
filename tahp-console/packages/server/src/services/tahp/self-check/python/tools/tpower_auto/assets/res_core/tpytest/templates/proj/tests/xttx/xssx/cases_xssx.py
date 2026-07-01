from typing import cast

from tests.xttx.cases_xttx import CasesXttx
from tests.xttx.xssx.xssx_config import XssxConfig
from tests.xttx.xssx.xssx_env import XssxEnv


class CasesXssx(CasesXttx):
    def __init__(self):
        super().__init__()
        ...

    @property
    def scheme_env(self) -> XssxEnv:
        return self.get_scheme_env()

    @property
    def user_config(self) -> XssxConfig:
        return self.get_scheme_env().user_config

    @classmethod
    def get_scheme_env(cls) -> XssxEnv:
        return cast(XssxEnv, super().get_scheme_env())

