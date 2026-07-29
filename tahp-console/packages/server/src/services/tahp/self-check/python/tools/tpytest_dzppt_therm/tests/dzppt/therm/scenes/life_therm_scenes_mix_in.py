from typing import Optional
from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde import adb
from tests.dzppt.therm.cases_therm import CasesTherm
from tests.dzppt.therm.therm_task_session_life import ThermTaskSessionLife


class LifethermScenesMixIn(CasesTherm):

    def on_pre_call(self):
        super().on_pre_call()

    def on_post_call(self, exception: Optional[Exception]):
        super().on_post_call(exception)
        if exception:
            t_log.info(f"\n*** {self.case_name} *** 用例运行失败！\n", ext_event=True)
            t_log.info(f"- result：【{exception}】", ext_event=True)

    def on_setup(self):
        adb.poweron_screen_and_unlock(self.device_id)
        t_log.info("=" * 60, ext_event=True)
        super().on_setup()

    def on_teardown(self):
        super().on_teardown()

    @classmethod
    def setup_session_life(cls, session_life: ThermTaskSessionLife):
        super().setup_session_life(session_life)

    @classmethod
    def teardown_session_life(cls, session_life: ThermTaskSessionLife):
        super().teardown_session_life(session_life)


