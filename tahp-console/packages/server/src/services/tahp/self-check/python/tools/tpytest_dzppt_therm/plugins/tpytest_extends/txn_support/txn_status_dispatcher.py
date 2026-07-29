from typing import Optional

from powertrde.framework.i18n import I18n
from powertrde.utils.simple_event_center import SimpleEventCenter, SimpleEventListener, SimpleEvent
from tpytest.test_case_counter import TestCaseCounter
from txn_sync.transaction_synchronizer import IPCClient


class TxnStatusDispatcher:
    def __init__(self, team_name: str, scheme_name: str, device_id: str, is_retest: bool, server_address: tuple):
        self.counter_listener: Optional[SimpleEventListener] = None
        self.vm_listener: Optional[SimpleEventListener] = None
        self.team_name = team_name
        self.scheme_name = scheme_name
        self.device_id = device_id
        self.last_runtime_phase = ''
        self.last_runtime_phase_desc = ''
        self.last_test_counter = None
        self.is_retest = is_retest
        self.server_address = server_address
        self._cached_ipc = None

    @property
    def txn_uuid(self):
        return f'tpytest_{self.team_name}_{self.scheme_name}_{self.device_id}'

    @property
    def ipc(self):
        try:
            if self._cached_ipc is None:
                self._cached_ipc = IPCClient(self.server_address, timeout=1.0)
            return self._cached_ipc
        except Exception:
            return None

    def start(self):
        self.counter_listener = SimpleEventListener('test_counter_event',
                                                    lambda e: self.on_test_counter_changed(e.kwargs['counter']))
        SimpleEventCenter.get_instance().add_listener_directly(self.counter_listener)

        self.vm_listener = SimpleEventListener('scheme_vm_event', self._on_vm_event)
        SimpleEventCenter.get_instance().add_listener_directly(self.vm_listener)

        self.reset_status()

    def stop(self):
        self.counter_listener.dispose()
        self.vm_listener.dispose()

    def _on_vm_event(self, e: SimpleEvent):
        vm_key = e.kwargs['key']
        if vm_key == 'runtime_phase':
            ori_phase = e.kwargs['value']
            self.last_runtime_phase = ori_phase

            if ori_phase == 'checking':
                self.on_runtime_phase_changed(I18n.gen_str('Case Checking', '用例检查中'))
            if ori_phase == 'pretest':
                self.on_runtime_phase_changed(I18n.gen_str('Pretesting', '预测试中'))
            elif ori_phase == 'case':
                self.on_runtime_phase_changed(
                    I18n.gen_str('Cases Re-testing', '用例复测中') if self.is_retest else I18n.gen_str('Cases Testing', '用例测试中')
                )
            elif ori_phase == 'case_phase_teardown':
                self.on_runtime_phase_changed(I18n.gen_str('Case Task Ending', '测试收尾中'))
            elif ori_phase == 'case_phase_end':
                self.on_runtime_phase_changed(I18n.gen_str('Tests Finished', '测试完成'))
            elif ori_phase.startswith('exception_case'):
                self.on_runtime_phase_changed(I18n.gen_str('Tests Exception', '测试异常'))
            elif ori_phase.startswith('exception_'):
                self.on_runtime_phase_changed(I18n.gen_str('Pretests Exception', '预测试异常'))

    def on_runtime_phase_changed(self, runtime_phase_desc: str):
        self.last_runtime_phase_desc = runtime_phase_desc
        self.dispatch_status()

    def on_test_counter_changed(self, test_counter: TestCaseCounter):
        self.last_test_counter = test_counter
        self.dispatch_status()

    def dispatch_status(self):
        try:
            self.ipc.update_handler(self.txn_uuid, progress=float(self._get_percent()), status=self._get_status_display_text())
        except Exception:
            self._cached_ipc = None

    def reset_status(self):
        try:
            self.ipc.register_handler(self.txn_uuid, name=self.device_id, reset=True)
        except Exception:
            self._cached_ipc = None

    def _get_status_display_text(self):
        if self.last_test_counter:
            total_count = self.last_test_counter.total_count
            pass_count = self.last_test_counter.pass_count
            fail_count = self.last_test_counter.fail_count
            _test_progress_desc = f"{self.last_runtime_phase_desc}: {pass_count + fail_count}/{total_count}, P({pass_count})/F({fail_count})"
        else:
            _test_progress_desc = self.last_runtime_phase_desc
        return _test_progress_desc

    def _get_percent(self):
        if not self.last_test_counter:
            return 0
        total_count = self.last_test_counter.total_count
        pass_count = self.last_test_counter.pass_count
        fail_count = self.last_test_counter.fail_count
        _percent = (pass_count + fail_count) * 100 // total_count if total_count != 0 else 0
        if _percent == 100 and (self.last_runtime_phase.startswith('case') or self.last_runtime_phase == 'pretest') and self.last_runtime_phase != 'case_phase_end':
            _percent = 99
        return _percent


if __name__ == '__main__':
    _i = IPCClient(('tcp', '127.0.0.1', 57124))
    _i.register_handler('tpytest_dzppt_perf_ASALE3741B000022', name='ASALE3741B000022')
    _i.update_handler('tpytest_dzppt_perf_ASALE3741B000022', progress=5.0)
