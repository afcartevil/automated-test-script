from tpytest.base_test import BaseTestPhone
from tpytest.case_request import CaseRequest
from tpytest.task_session_life import TaskSessionLife
from tpytest_extends.scheme.cases_scheme import CasesScheme
from tpytest_extends.scheme.scheme_extend_test_env import get_scheme_extend_env


class TestScheme(BaseTestPhone):
    option_bind_cs_class = CasesScheme

    @property
    def cs(self) -> CasesScheme:
        return self.get_bound_cs()

    def _setup_session_life(self, case_request: CaseRequest, task_session_life: TaskSessionLife):
        get_scheme_extend_env().last_task_session_life = task_session_life
        super()._setup_session_life(case_request, task_session_life)
