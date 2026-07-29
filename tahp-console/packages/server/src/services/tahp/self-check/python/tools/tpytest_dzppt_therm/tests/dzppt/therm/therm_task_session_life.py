from tests.dzppt.therm.therm_reporter import ThermReporter
from tpytest.scheme.scheme_task_session_life import SchemeTaskSessionLife


class ThermTaskSessionLife(SchemeTaskSessionLife):
    def __init__(self):
        super().__init__()

    def on_session_start(self):
        super().on_session_start()
        ...

    def on_session_end(self):
        super().on_session_end()
        if not self.is_bound_cs_class_pretest and self.scheme_env.is_case_phase_or_debug_setup_task:
            # 自动生成excel报告
            try:
                reporter = ThermReporter(self.get_log_dir())
                reporter.parse_reporter_units()
                reporter.write_reporter_excel()
            except Exception as e:
                self.logger.exception(f'therm_report.gen_data_report error: {e}', ext_event=True)
                self.logger.error_with_tag(f'therm_report.gen_data_report error: {e}', ext_event=True)


