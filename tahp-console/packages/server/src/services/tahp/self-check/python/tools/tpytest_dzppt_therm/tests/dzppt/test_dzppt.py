from tests.dzppt.cases_dzppt import CasesDzPpt
from tpytest_extends.scheme.test_scheme import TestScheme


class TestDzPpt(TestScheme):
    option_bind_cs_class = CasesDzPpt

    @property
    def cs(self) -> CasesDzPpt:
        return self.get_bound_cs()
