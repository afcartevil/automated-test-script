import inspect
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TypeVar, Type, cast, Dict, Any

from powertrde import env
from powertrde.utils import misc_utils
from tpytest.cases_steps import CasesPhone
from tpytest.preset_recorder import PresetRecordGroups
from tpytest.tpypre.pretest_runtime import PretestRuntime
from tpytest.tpytest_runtime import TPytestRuntime
from tpytest_extends.scheme.scheme_extend_test_env import get_scheme_extend_env


@dataclass
class StepTimeData:
    step_name: str
    sub_step_name: str
    expect_time: float
    actual_time: float
    gap_time: float
    error_message: str


@dataclass
class MonitorStepData:
    step_name: str
    start_time: str
    end_time: str
    duration: float
    error_message: str


class TimedStepContext:
    def __init__(self, step_name: str, start_time: float, expect_time: float):
        self.step_name = step_name
        self.start_time = start_time
        self.expect_time = expect_time

    @property
    def left_time(self) -> float:
        """
        返回距离期望时长还剩余多少秒，若已超时则返回0。
        如果在short debug模式中，则模拟返回一个很小的时间，用作快速跑测
        """
        is_short_debug = TPytestRuntime.get_instance().current_scheme_env.is_short_test_debug
        if is_short_debug:
            if self.expect_time < 4:
                return self.expect_time
            return max(4.0, self.expect_time / 60)

        elapsed = time.monotonic() - self.start_time
        remaining = self.expect_time - elapsed
        return max(0.0, remaining)


class MonitorStepHandler:
    def on_step_enter(self, step_context: 'MonitorStepContext'):
        ...

    def on_step_exit(self, step_context: 'MonitorStepContext', exception: Optional[Exception]):
        ...


class CustomMonitorStepHandler(MonitorStepHandler):
    def __init__(self, on_enter_callback: callable, on_exit_callback: callable):
        super().__init__()
        self.on_enter_callback = on_enter_callback
        self.on_exit_callback = on_exit_callback

    @staticmethod
    def _invoke_callback(callback: callable, **available_args):
        """
        根据回调函数的签名，从 available_args 中筛选出需要的参数，动态调用回调函数。
        """
        if not callable(callback):
            raise ValueError(f"Provided callback {callback} is not callable.")

        # 获取回调函数的签名
        sig = inspect.signature(callback)
        # 根据签名筛选出需要的参数
        filtered_args = {
            name: value
            for name, value in available_args.items()
            if name in sig.parameters
        }
        # 调用回调函数
        return callback(**filtered_args)

    def on_step_enter(self, step_context: 'MonitorStepContext'):
        """
        进入步骤时调用
        """
        if not self.on_enter_callback:
            return
        # 提供可用参数
        available_args = {
            "step_context": step_context,
        }
        # 动态调用 on_enter_callback
        self._invoke_callback(self.on_enter_callback, **available_args)

    def on_step_exit(self, step_context: 'MonitorStepContext', exception: Optional[Exception]):
        """
        离开步骤时调用
        """
        if not self.on_exit_callback:
            return
        # 提供可用参数
        available_args = {
            "step_context": step_context,
            "exception": exception,
        }
        # 动态调用 on_exit_callback
        self._invoke_callback(self.on_exit_callback, **available_args)


class MonitorStepContext:
    def __init__(self, case_ins: 'CasesScheme', step_name: str, start_time: float,
                 step_handler: Optional[MonitorStepHandler]):
        self.case_ins = case_ins
        self.step_name = step_name
        self.start_time = start_time
        self.full_step_name = self.case_ins.current_monitor_steps_name
        self.step_handler = step_handler
        self.end_time = 0.0

    @property
    def elapsed_time(self):
        if self.end_time:
            return self.end_time - self.start_time
        return time.monotonic() - self.start_time

    def on_step_enter(self):
        if self.step_handler:
            self.step_handler.on_step_enter(self)

    def on_step_exit(self, exception: Optional[Exception]):
        if self.step_handler:
            self.step_handler.on_step_exit(self, exception)


T = TypeVar('T')


class CasesScheme(CasesPhone):
    _get_aw_app_method = None

    def __init__(self):
        super().__init__()
        self.current_monitor_steps = []
        self._first_aw_app = None
        self._c_first_aw_app = None
        self.has_lock_use_copilot = False  # 是否已通过手机租借服务获得了辅助机的使用权

    @classmethod
    def get_app_info(cls, app_name: str, no_raise: bool = False):
        from tpytest_extends.scheme.apps_static_info import AppsStaticInfo
        return AppsStaticInfo.get_app_info_no_raise(app_name) if no_raise else AppsStaticInfo.get_app_info(app_name)

    @classmethod
    def get_c_app_info(cls, app_name: str, no_raise: bool = False):
        from tpytest_extends.scheme.apps_static_info import AppsStaticInfo
        c_device_id = cls.get_scheme_env().c_device_id
        return AppsStaticInfo.get_app_info_no_raise(app_name, variant_device_sn=c_device_id) if no_raise else AppsStaticInfo.get_app_info(app_name, variant_device_sn=c_device_id)

    @staticmethod
    def _get_get_aw_app_method():
        if CasesScheme._get_aw_app_method is None:
            CasesScheme._get_aw_app_method = env.load_member('tpy_aw.aw_registry.get_aw_app')
        return CasesScheme._get_aw_app_method

    @classmethod
    def get_app_aw(cls, app_name: str, variant: Optional[str] = None, no_raise: bool = False):
        try:
            return cls._get_get_aw_app_method()(cls.get_u2d_helper(), app_name, variant)
        except Exception:
            if not no_raise:
                raise
        return None

    @classmethod
    def get_casted_app_aw(cls, cast_type: Type[T], app_name: Optional[str] = None, variant: Optional[str] = None, no_raise: bool = False) -> Optional[T]:
        return cast(cast_type, cls.get_app_aw(app_name or cast_type.aw_name, variant, no_raise))

    @classmethod
    def get_c_app_aw(cls, app_name: str, variant: Optional[str] = None, no_raise: bool = False):
        try:
            return cls._get_get_aw_app_method()(cls.get_c_u2d_helper(), app_name, variant)
        except Exception:
            if not no_raise:
                raise
        return None

    @classmethod
    def get_c_casted_app_aw(cls, cast_type: Type[T], app_name: Optional[str] = None, variant: Optional[str] = None, no_raise: bool = False) -> Optional[T]:
        return cast(cast_type, cls.get_c_app_aw(app_name or cast_type.aw_name, variant, no_raise))

    @property
    def current_monitor_steps_name(self):
        return '/'.join(self.current_monitor_steps)

    @classmethod
    def get_scheme_env(cls):
        return get_scheme_extend_env()

    @classmethod
    def get_user_config(cls):
        return cls.get_scheme_env().user_config

    @classmethod
    def get_user_configured_dict(cls):
        return cls.get_scheme_env().user_config.configured_config_dict

    @property
    def user_config(self):
        return self.get_user_config()

    @property
    def user_configured_dict(self):
        return self.get_user_configured_dict()

    @property
    def scheme_env(self):
        return self.get_scheme_env()

    @property
    def u2d_helper(self):
        return self.scheme_env.u2d_helper

    @classmethod
    def get_u2d_helper(cls):
        return cls.get_scheme_env().u2d_helper

    @property
    def res_provider(self):
        return self.scheme_env.res_provider

    @property
    def logs_uploader(self):
        return self.scheme_env.logs_uploader

    @property
    def c_u2d_helper(self):
        return self.scheme_env.c_u2d_helper

    @classmethod
    def get_c_u2d_helper(cls):
        return cls.get_scheme_env().c_u2d_helper

    @property
    def prg(self) -> PresetRecordGroups:
        return self.scheme_env.preset_record_groups

    @property
    def session_logs_dir(self):
        return self.session_life.get_session_logs_dir()

    @property
    def meta_report_dir(self):
        return self.session_life.get_meta_report_dir()

    @property
    def collects_report_dir(self):
        return self.session_life.get_collects_report_dir()

    @property
    def pretest_runtime(self):
        return PretestRuntime.get_instance()

    def record_pretest_result(self, is_pass_or_none: bool):
        target = self.case_request.pretest_config_helper.target
        self.pretest_runtime.record_pretest_result(target, self.case_name, is_pass_or_none)

    def on_setup(self):
        super().on_setup()
        if self.scheme_env.runtime_phase == 'pretest':
            self.record_pretest_result(False)
            if self.case_request.is_retry_test:
                self.scheme_env.pretest_counter.update_current_case_report(self.case_report)
            else:
                self.scheme_env.pretest_counter.require_next_case(self.case_report)
        elif self.scheme_env.runtime_phase == 'case':
            if self.case_request.is_retry_test:
                self.scheme_env.test_counter.update_current_case_report(self.case_report)
            else:
                self.scheme_env.test_counter.require_next_case(self.case_report)

        if self.scheme_env.is_case_phase_or_debug_setup_task and self.scheme_env.is_auto_lock_copilot_on_copilot_case_setup and self.case_request.is_need_copilot:
            if not self.c_device_id:
                self.logger.warning(
                    f'[{self.logger_header} {self.case_request.case_short_node_id}] This test case requires the involvement of a COPILOT PHONE. However, it seems that your test environment has not detected any copilot phones.')
            else:
                # 尝试自动锁定辅助机
                self.logger.info(f'[{self.logger_header} {self.case_request.case_short_node_id}] Try waiting and get access to the copilot phone...')
                lock_use_copilot_func = getattr(self, 'lock_use_copilot', None)
                if lock_use_copilot_func:
                    try:
                        misc_utils.observe_blocking_func(lock_use_copilot_func, interval=30)
                    except Exception as e:
                        self.logger.exception(f'[{self.logger_header} {self.case_request.case_short_node_id}] Failed to obtain the access to the copilot phone {self.c_device_id}, reason: {e}')
                        raise
                    else:
                        self.has_lock_use_copilot = True
                        self.logger.info(f'[{self.logger_header} {self.case_request.case_short_node_id}] Successfully obtained the access to the copilot phone {self.c_device_id}')
                else:
                    self.logger.error(f'[{self.logger_header} {self.case_request.case_short_node_id}] Unable to find "lock_use_copilot" method, perhaps your case class does not inherit from PhoneDispatcherMixIn.')

    def on_post_teardown_anyway(self):
        super().on_post_teardown_anyway()
        if self.has_lock_use_copilot:
            unlock_use_copilot_func = getattr(self, 'unlock_use_copilot', None)
            if unlock_use_copilot_func:
                try:
                    unlock_use_copilot_func()
                    self.logger.info(f'[{self.logger_header} {self.case_request.case_short_node_id}] Release the access to the copilot phone {self.c_device_id}')
                except Exception as e:
                    self.logger.exception(
                        f'[{self.logger_header} {self.case_request.case_short_node_id}] Failed to release the access to the copilot phone {self.c_device_id}, reason: {e}')

    def on_make_report(self):
        super().on_make_report()
        if self.is_auto_write_report_file:
            self.case_report.save_unit_report(self.session_life)
            self.session_life.write_session_report_for_in_process()

        if self.scheme_env.runtime_phase == 'pretest':
            if self.case_report.is_pass:
                self.scheme_env.pretest_counter.gain_pass_count()
                self.record_pretest_result(True)
            elif not self.need_retry_next:
                self.scheme_env.pretest_counter.gain_fail_count()
        elif self.scheme_env.runtime_phase == 'case':
            if self.case_report.is_pass:
                self.scheme_env.test_counter.gain_pass_count()
            elif not self.need_retry_next:
                self.scheme_env.test_counter.gain_fail_count()

    @property
    def first_test_aw_app(self):
        if self._first_aw_app is None:
            from tpy_aw.aw_registry import get_aw_app_by_app_info
            self._first_aw_app = get_aw_app_by_app_info(self.u2d_helper, self.first_test_app_info)
        return self._first_aw_app

    @property
    def first_test_app_name(self):
        return self.case_request.first_test_app

    @property
    def first_test_app_info(self):
        return self.case_request.first_test_app_info

    @property
    def first_copilot_aw_app(self):
        if self._c_first_aw_app is None:
            from tpy_aw.aw_registry import get_aw_app_by_app_info
            self._c_first_aw_app = get_aw_app_by_app_info(self.c_u2d_helper, self.first_copilot_app_info)
        return self._c_first_aw_app

    @property
    def first_copilot_app_name(self):
        return self.case_request.first_copilot_app

    @property
    def first_copilot_app_info(self):
        return self.case_request.first_copilot_app_info

    @property
    def need_retry_next(self):
        return self.case_request.need_retry_next

    def on_log_case_start(self):
        self.logger.info(
            f'※-S- [{self.logger_header} {self.case_request.case_short_node_id}]{self.case_request.case_desc_one_line_with_bracket} Start',
            ext_event=True, tag=self.scheme_env.sn_log_tag)

    def on_log_case_end(self):
        skip_text = ' (by skip)' if self.case_report.is_skip else ''
        self.logger.info(
            f'※-E- [{self.logger_header} {self.case_request.case_short_node_id}]{self.case_request.case_desc_one_line_with_bracket} End: {self.case_report.test_result}{skip_text} in {int(self.case_report.test_duration)}s',
            ext_event=True, tag=self.scheme_env.sn_log_tag)

    def expect_time_action(self, action_name: str, yield_action, expect_time: float, loop: bool):
        """
        执行一个基于生成器的动作，确保总执行时长满足期望时间。

        参数：
          action_name: 必填，动作名称，用于标识和日志输出。
          yield_action: 一个生成器函数、生成器对象，或者普通函数，定义动作过程。
                        在动作过程中可 yield 一个 float，表示需要原子等待的秒数。
          expect_time: 期望总时长（单位：秒），必填。
          loop: 如果为 False，则执行一次动作（不足期望时额外等待）；若为 True，则无限循环动作，
                每次循环均检查时间，直到达到期望时长退出。

        在任何提前退出时，会通过 print 输出退出原因、期望时长、实际执行时长及两者差值。
        """
        start_time = time.monotonic()

        def print_exit(reason, exception):
            elapsed = time.monotonic() - start_time
            diff = elapsed - expect_time
            self.logger.info(
                f"[{self.case_request.case_short_node_id}] Time Action '{action_name}' Exiting: {reason}. Expected: {expect_time:.3f}s, Actual: {elapsed:.3f}s, Gap: {diff:.3f}s",
                ext_event=True)
            if self.case_report.data and hasattr(self.case_report.data, 'step_time_datas'):
                self.case_report.data.step_time_datas.append(
                    StepTimeData(step_name=self.current_monitor_steps_name, sub_step_name=action_name,
                                 expect_time=expect_time, actual_time=elapsed,
                                 gap_time=diff, error_message='' if not exception else str(exception)))

        def get_generator(action):
            """
            根据传入的 action 支持三种类型：
              - 如果 action 是可调用的且是生成器函数，则返回其生成器；
              - 如果 action 是可调用的但不是生成器函数，则包装成一个只执行一次的生成器；
              - 如果 action 不是可调用的，则假定它是一个生成器对象，直接返回。
            """
            if callable(action):
                if inspect.isgeneratorfunction(action):
                    return action()
                else:
                    # 普通函数包装为生成器，注意：包装后，函数只在调用 next() 时执行一次
                    def wrapper():
                        action()  # 执行普通函数
                        return  # 直接结束生成器
                        yield  # 此处永远不会执行，仅用于声明这是个生成器

                    return wrapper()
            else:
                return action

        while True:
            current_elapsed = time.monotonic() - start_time
            if current_elapsed >= expect_time:
                print_exit("Time reached before starting action", None)
                return

            # 获取本次动作的生成器（支持普通函数、生成器函数、生成器对象）
            try:
                g = get_generator(yield_action)
            except Exception as e:
                print_exit(f"Exception when initializing action: {e}", e)
                raise

            # 执行动作生成器
            try:
                while True:
                    # 每次获取下一步前，先检查总时长是否已达期望
                    if time.monotonic() - start_time >= expect_time:
                        print_exit("Time reached during action execution", None)
                        return
                    try:
                        wait_time = next(g)
                    except StopIteration:
                        # 动作执行完毕
                        break

                    # 如果 yield 返回的是一个数字，则执行原子等待
                    if isinstance(wait_time, (int, float)):
                        deadline = time.monotonic() + wait_time
                        while time.monotonic() < deadline:
                            if time.monotonic() - start_time >= expect_time:
                                print_exit("Time reached during atomic wait in action", None)
                                return
                            time.sleep(min(0.1, deadline - time.monotonic()))
                    else:
                        # yield 的值不是数字，直接进入下一步
                        pass
            except Exception as e:
                print_exit(f"Exception during action execution: {e}", e)
                raise

            # 动作执行完毕后，检查是否超时
            if time.monotonic() - start_time >= expect_time:
                print_exit("Time reached right after action execution", None)
                return

            if not loop:
                # 非循环模式：如果动作结束后仍未达到期望时长，则等待剩余时间
                deadline = start_time + expect_time
                while time.monotonic() < deadline:
                    time.sleep(0.1)
                print_exit("Action completed and waited until expected time", None)
                return
            else:
                # 循环模式：检查时间，若仍有时间则继续下一次动作循环
                if time.monotonic() - start_time >= expect_time:
                    print_exit("Time reached after loop iteration", None)
                    return
                # 否则继续下一次循环

    @contextmanager
    def timed_step(self, step_name: str, expect_time: float, wait_on_finished_if_needed=True, ignore_short_debug=False):
        """
        计时上下文管理器：
          - step_name: 必填，步骤名称，用于标识该步骤
          - expect_time: 必填，期望的执行时长（秒）
          - wait_on_finished_if_needed: 选填，如果在区域内没有达到时长要求，将自动等待直到期望时长

        执行完毕后，会打印实际时长、期望时长及二者之差（gap）。
        如果内部代码抛出异常，同样会打印上述信息，并附带异常说明，随后继续抛出异常。
        同时返回一个 TimedStepContext 对象，该对象的 remaining_time() 方法可以在 with 块内动态获取距离期望时长还剩余多少秒。
        """
        self.current_monitor_steps.append(step_name)

        step_names = self.current_monitor_steps_name

        if not ignore_short_debug:
            is_short_debug = self.scheme_env.is_short_test_debug
            if is_short_debug:
                if expect_time > 6:
                    wait_on_finished_if_needed = False

        if expect_time <= 0:
            expect_time = 0.1

        self.logger.info(
            f"[{self.case_short_node_id}] Timed Step '{step_names}' start, excepted {expect_time:.1f}s",
            ext_event=True)
        start_time = time.monotonic()
        step_context = TimedStepContext(step_names, start_time, expect_time)
        try:
            yield step_context
        except Exception as e:
            elapsed = time.monotonic() - start_time
            diff = elapsed - expect_time
            error_message = str(e).replace('\n', '; ')
            self.logger.error_with_tag(
                f"[{self.case_short_node_id}] Timed Step '{step_names}' failed: elapsed {elapsed:.3f}s, expected {expect_time:.3f}s, gap {diff:.3f} sec. Exception: {error_message}",
                ext_event=True)
            if self.case_report.data and hasattr(self.case_report.data, 'step_time_datas'):
                self.case_report.data.step_time_datas.append(
                    StepTimeData(step_name=step_names, sub_step_name='', expect_time=expect_time, actual_time=elapsed,
                                 gap_time=diff, error_message=error_message))
            raise
        else:
            elapsed = time.monotonic() - start_time
            diff = elapsed - expect_time
            need_warn = (abs(diff) > 10)
            if wait_on_finished_if_needed and diff < 0:
                time.sleep(-diff)
                message = f"[{self.case_short_node_id}] Timed Step '{step_names}' early completed and wait: elapsed {elapsed:.3f}s, wait {(-diff):.3f}s, expected {expect_time:.3f}s"
            else:
                message = f"[{self.case_short_node_id}] Timed Step '{step_names}' completed: elapsed {elapsed:.3f}s, expected {expect_time:.3f}s, gap {diff:.3f}s."

            if need_warn:
                self.logger.warning(message, ext_event=True)
            else:
                self.logger.info(message, ext_event=True)

            if self.case_report.data and hasattr(self.case_report.data, 'step_time_datas'):
                self.case_report.data.step_time_datas.append(
                    StepTimeData(step_name=step_names, sub_step_name='', expect_time=expect_time, actual_time=elapsed,
                                 gap_time=diff, error_message=''))
        finally:
            self.current_monitor_steps.pop()

    @contextmanager
    def monitor_step(self, step_name: str, step_handler: Optional[MonitorStepHandler] = None, pre_wait: float = 0, post_wait: float = 0):
        self.current_monitor_steps.append(step_name)

        step_names = self.current_monitor_steps_name

        self.logger.info(
            f"[{self.case_short_node_id}] Monitor Step '{step_names}' start",
            ext_event=True)
        step_context = MonitorStepContext(self, step_name, time.time(), step_handler)
        step_context.on_step_enter()
        try:
            if pre_wait > 0:
                time.sleep(pre_wait)
            yield step_context
            if post_wait > 0:
                time.sleep(post_wait)
        except Exception as e:
            step_context.on_step_exit(e)
            step_context.end_time = time.time()
            error_message = str(e).replace('\n', '; ')
            self.logger.error_with_tag(
                f"[{self.case_short_node_id}] Monitor Step '{step_names}' failed: elapsed {step_context.elapsed_time:.3f}s. Exception: {error_message}",
                ext_event=True)
            if self.case_report.data and hasattr(self.case_report.data, 'monitor_step_datas'):
                self.case_report.data.monitor_step_datas.append(
                    MonitorStepData(step_name=step_names,
                                    start_time=datetime.fromtimestamp(step_context.start_time).isoformat(),
                                    end_time=datetime.fromtimestamp(step_context.end_time).isoformat(),
                                    duration=step_context.elapsed_time, error_message=error_message))
            raise
        else:
            step_context.on_step_exit(None)
            step_context.end_time = time.time()
            message = f"[{self.case_short_node_id}] Monitor Step '{step_names}' completed: elapsed {step_context.elapsed_time:.3f}s."
            self.logger.info(message, ext_event=True)
            if self.case_report.data and hasattr(self.case_report.data, 'monitor_step_datas'):
                self.case_report.data.monitor_step_datas.append(
                    MonitorStepData(step_name=step_names,
                                    start_time=datetime.fromtimestamp(step_context.start_time).isoformat(),
                                    end_time=datetime.fromtimestamp(step_context.end_time).isoformat(),
                                    duration=step_context.elapsed_time, error_message=''))
        finally:
            self.current_monitor_steps.pop()

    def shorten_sleep(self, duration: float):
        if self.scheme_env.is_short_test_debug:
            act_duration = min(duration, 4)
        else:
            act_duration = duration
        time.sleep(act_duration)

    def shorten_loop_action(self, action: callable, loop_count: int):
        if self.scheme_env.is_short_test_debug:
            act_loop_count = min(loop_count, 2)
        else:
            act_loop_count = loop_count
        for _ in range(act_loop_count):
            action()

    def has_trunk_flag(self, flag: str):
        return self.scheme_env.has_trunk_flag(flag)

    def run_collector_for_case(self, data_collector, suffix: str, override_params: Optional[Dict[str, Any]] = None):
        data_collector.run_all(label=self.gen_node_collect_label_name_for_case(suffix), override_params=override_params)

    def gen_node_collect_label_name_for_case(self, suffix: str):
        if suffix:
            suffix = '-' + suffix
        elif suffix is None:
            suffix = ''
        return f'case-{misc_utils.get_date_time_filename_str()}-{self.case_short_node_id}{suffix}'
