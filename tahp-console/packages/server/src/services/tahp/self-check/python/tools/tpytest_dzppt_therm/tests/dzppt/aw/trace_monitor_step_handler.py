import os.path
from typing import Optional

from perftest_tool.perfetto_tracer import PerfettoTracer
from powertrde.env import PROJ_DIR
from powertrde.utils import misc_utils, path_utils
from powertrde.utils.trde import adb
from tpytest.scheme.scheme_task_session_life import SchemeTaskSessionLife
from tpytest_extends.scheme.cases_scheme import MonitorStepHandler, MonitorStepContext
from tpytest_extends.utils import tests_utils


class TraceMonitorStepHandler(MonitorStepHandler):
    _overwrite_trace_capture_enabled = None

    def __init__(self):
        super().__init__()
        self.auto_pull_after_capture = True
        self.trace_name = None

    @classmethod
    def get_exist_tracer(cls, session_life: SchemeTaskSessionLife) -> Optional[PerfettoTracer]:
        _perf_tracer = getattr(session_life, '_perf_tracer', None)
        return _perf_tracer

    @classmethod
    def get_tracer_by_session_life(cls, session_life: SchemeTaskSessionLife) -> Optional[PerfettoTracer]:
        if not cls.get_is_trace_capture_enabled_by_session_life(session_life):
            return None
        _perf_tracer = getattr(session_life, '_perf_tracer', None)
        if _perf_tracer is None:
            _perf_tracer = PerfettoTracer(session_life.device_id,
                                          os.path.join(session_life.get_session_logs_dir(), 'trace'),
                                          local_config=str(cls.get_trace_config_pbtx_by_session_life(session_life)))
            setattr(session_life, '_perf_tracer', _perf_tracer)
        return _perf_tracer

    @classmethod
    def get_tracer(cls, step_context: MonitorStepContext):
        if not cls.get_is_trace_capture_enabled(step_context):
            return None
        session_life = cls.get_session_life(step_context)
        _perf_tracer = getattr(session_life, '_perf_tracer', None)
        if _perf_tracer is None:
            _perf_tracer = PerfettoTracer(session_life.device_id,
                                          os.path.join(session_life.get_session_logs_dir(), 'trace'),
                                          local_config=str(cls.get_trace_config_pbtx(step_context)))
            setattr(session_life, '_perf_tracer', _perf_tracer)
        return _perf_tracer

    @staticmethod
    def _wrap_trace_config_variant(full_pbtx):
        _env_keys = tests_utils.try_to_get_scheme_env_keys()
        if _env_keys:
            closest_pbtx_variant = path_utils.get_closest_variant_path_by_keys(path_utils.find_related_variants(str(full_pbtx)), _env_keys)
            if not closest_pbtx_variant:
                full_pbtx = None
            else:
                full_pbtx = closest_pbtx_variant[1]
        else:
            if not os.path.exists(full_pbtx):
                full_pbtx = None
        return full_pbtx

    @classmethod
    def get_trace_config_pbtx(cls, step_context: MonitorStepContext):
        short = cls.get_scheme_config_dict(step_context)['trace_capture']['config']
        assert short, "Trace config.pbtx must not be none or empty!"
        full_pbtx = os.path.join(step_context.case_ins.scheme_env.user_config.config_dir, os.path.normpath(short))
        full_pbtx = cls._wrap_trace_config_variant(full_pbtx)
        if not full_pbtx:
            raise FileNotFoundError(f"Trace config file '{full_pbtx}' not found!")
        return full_pbtx

    @classmethod
    def get_trace_config_pbtx_by_session_life(cls, session_life: SchemeTaskSessionLife):
        short = session_life.scheme_env.user_config.configured_config_dict['trace_capture']['config']
        assert short, "Trace config.pbtx must not be none or empty!"
        _nor_short = os.path.normpath(short)
        full_pbtx = os.path.join(session_life.scheme_env.user_config.config_dir, _nor_short)
        if not os.path.exists(full_pbtx):
            full_pbtx = os.path.join(PROJ_DIR, _nor_short)
        full_pbtx = cls._wrap_trace_config_variant(full_pbtx)
        if not full_pbtx:
            raise FileNotFoundError(f"Trace config file '{full_pbtx}' not found!")
        return full_pbtx

    @classmethod
    def get_scheme_config_dict(cls, step_context: MonitorStepContext):
        return step_context.case_ins.scheme_env.user_config.configured_config_dict

    @classmethod
    def get_session_life(cls, step_context: MonitorStepContext):
        return step_context.case_ins.session_life

    @classmethod
    def get_trace_capture_config(cls, step_context: MonitorStepContext):
        return cls.get_scheme_config_dict(step_context).get('trace_capture')

    @classmethod
    def get_is_trace_capture_enabled(cls, step_context: MonitorStepContext):
        # if not step_context.case_ins.scheme_env.is_case_phase_or_debug_setup_case:
        #     return False
        if cls._overwrite_trace_capture_enabled is not None:
            return cls._overwrite_trace_capture_enabled
        try:
            return bool(cls.get_scheme_config_dict(step_context)['trace_capture']['enabled'])
        except Exception:
            return False

    @classmethod
    def get_is_trace_capture_enabled_by_session_life(cls, session_life: SchemeTaskSessionLife):
        # if not session_life.scheme_env.is_case_phase_or_debug_setup_case:
        #     return False
        if cls._overwrite_trace_capture_enabled is not None:
            return cls._overwrite_trace_capture_enabled
        try:
            return bool(session_life.scheme_env.user_config.configured_config_dict['trace_capture']['enabled'])
        except Exception:
            return False

    @classmethod
    def overwrite_trace_capture_enabled(cls, enabled: bool):
        cls._overwrite_trace_capture_enabled = enabled

    def on_step_enter(self, step_context: MonitorStepContext):
        if not self.get_is_trace_capture_enabled(step_context):
            # 如果禁止了Trace抓取，则直接跳过
            return
        tracer = self.get_tracer(step_context)
        step_name = misc_utils.sanitize_filename(str(step_context.full_step_name))
        case_id = step_context.case_ins.case_short_node_id

        # 如果是非传音手机，每次抓取Trace之前都执行一次指令
        try:
            if not step_context.case_ins.scheme_env.is_transsion_os:
                adb.setprop(step_context.case_ins.scheme_env.device_id, 'persist.traced.enable', 1)
        except Exception:
            pass
        tracer.start_grab(f'{case_id}_{step_name}')

    def on_step_exit(self, step_context: MonitorStepContext, exception: Optional[Exception]):
        if not self.get_is_trace_capture_enabled(step_context):
            # 如果禁止了Trace抓取，则直接跳过
            return
        tracer = self.get_tracer(step_context)
        remote_trace_file = tracer.stop_grab()
        self.trace_name = remote_trace_file.split("/")[-1]
        if self.auto_pull_after_capture:
            tracer.pull_trace_async(remote_trace_file, delete_remote=True)
