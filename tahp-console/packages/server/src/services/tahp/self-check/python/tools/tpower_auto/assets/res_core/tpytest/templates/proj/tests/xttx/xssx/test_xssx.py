from tests.xttx.xssx.cases_xssx import CasesXssx
from tests.xttx.test_xttx import TestXttx


class TestXssx(TestXttx):
    option_bind_cs_class = CasesXssx

    @property
    def cs(self) -> CasesXssx:
        return self.get_bound_cs()
