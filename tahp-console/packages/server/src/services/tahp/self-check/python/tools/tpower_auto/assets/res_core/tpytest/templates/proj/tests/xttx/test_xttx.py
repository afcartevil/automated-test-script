from tests.xttx.cases_xttx import CasesXttx
from tpytest_extends.scheme.test_scheme import TestScheme


class TestXttx(TestScheme):
    option_bind_cs_class = CasesXttx

    @property
    def cs(self) -> CasesXttx:
        return self.get_bound_cs()
