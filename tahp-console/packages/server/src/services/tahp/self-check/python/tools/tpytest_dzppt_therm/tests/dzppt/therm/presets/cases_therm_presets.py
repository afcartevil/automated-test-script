from pretests.dzppt.therm.therm_pretest_runtime import ThermPretestRuntime
from tests.dzppt.therm.cases_therm import CasesTherm
from tpytest.pretest_mix_in import CasesPretestMixIn


class CasesThermPresets(CasesTherm, CasesPretestMixIn):
    @property
    def pretest_runtime(self):
        return ThermPretestRuntime.get_instance()

    # ------------------------------------- Below is mock ----------------------------------------

    def pre_therm_mock_1(self):
        ...

    def pre_therm_mock_2(self):
        ...
