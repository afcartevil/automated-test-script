from tests.dzppt.therm.cases_therm import CasesTherm
from tests.dzppt.test_dzppt import TestDzPpt


class TestTherm(TestDzPpt):
    option_bind_cs_class = CasesTherm

    @property
    def cs(self) -> CasesTherm:
        return self.get_bound_cs()
