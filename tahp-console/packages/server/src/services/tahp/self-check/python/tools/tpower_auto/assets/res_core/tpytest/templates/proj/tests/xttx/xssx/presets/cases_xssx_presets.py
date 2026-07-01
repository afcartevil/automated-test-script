from pretests.xttx.xssx.xssx_pretest_runtime import XssxPretestRuntime
from tests.xttx.xssx.cases_xssx import CasesXssx
from tpytest.pretest_mix_in import CasesPretestMixIn


class CasesXssxPresets(CasesXssx, CasesPretestMixIn):
    @property
    def pretest_runtime(self):
        return XssxPretestRuntime.get_instance()

    # ------------------------------------- Below is mock ----------------------------------------

    def pre_xssx_mock_1(self):
        ...

    def pre_xssx_mock_2(self):
        ...
