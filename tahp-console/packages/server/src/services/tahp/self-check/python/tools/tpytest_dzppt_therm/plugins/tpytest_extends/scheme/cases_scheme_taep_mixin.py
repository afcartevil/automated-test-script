import time
from datetime import datetime
from functools import cached_property
from typing import Optional

from powertrde import env


class _CasesSchemeTaepMixIn:

    def _on_taep_setup(self):
        self._on_taep_setup_hook()

    def _on_taep_setup_hook(self):
        ...

    def _on_taep_teardown(self):
        self._on_taep_teardown_hook()

    def _on_taep_teardown_hook(self):
        ...

    @cached_property
    def taep_case_path(self) -> Optional[str]:
        try:
            return self.case_request.fixture_request.node.get_closest_marker('taep_case').args[0]
        except Exception:
            return None

    @cached_property
    def is_taep_case(self):
        return bool(self.taep_case_path)

    @cached_property
    def taep_case_name(self):
        try:
            _p = self.taep_case_path
            _p_s = _p.rindex('.') + 1
            return _p[_p_s:]
        except Exception:
            return None

    @cached_property
    def taep_case_module(self):
        _p = self.taep_case_path
        _n = self.taep_case_name
        assert _p and _n, 'Can not parse case name from TAEP marker!'

        _m = None
        try:
            _m = env.load_module(self.taep_case_path)
        except Exception:
            pass
        assert _m, f'Can not load TAEP case from module path: {_p}'
        return _m

    @cached_property
    def taep_case_module(self):
        _p = self.taep_case_path
        _n = self.taep_case_name
        assert _p and _n, 'Can not parse case name from TAEP marker!'

        _m = None
        try:
            _m = env.load_module(self.taep_case_path)
        except Exception:
            pass
        assert _m, f'Can not load TAEP case from module path: {_p}'
        return _m

    @cached_property
    def taep_case_function(self):
        _f = getattr(self.taep_case_module, self.taep_case_name, None)
        assert _f, f'Can not load TAEP case function from module: {self.taep_case_module}'
        return _f

    @cached_property
    def taep_case_setup_function(self):
        _f = getattr(self.taep_case_module, 'setup_function', None)
        return _f

    @cached_property
    def taep_case_teardown_function(self):
        _f = getattr(self.taep_case_module, 'teardown_function', None)
        return _f

    def try_perform_auto_login(self, taep_app_aw_instance, account_info: Optional[dict] = None, forced: bool = False):
        device_id = taep_app_aw_instance.device_id
        package = taep_app_aw_instance.app_package
        app_id = taep_app_aw_instance.unique_id
        log_tag = f'{device_id}][AUTO LOGIN'
        self.logger.info(f'Perform auto login for app {app_id}|{package}', ext_event=True, tag=log_tag)
        try:
            device_marker_store = self.scheme_env.get_device_marker_store(device_id)
            login_mark = device_marker_store.get_login_mark(package)

            _is_check_to_auto_login = self.scheme_env.user_config.is_check_to_auto_login(bool(device_id == self.scheme_env.c_device_id))
            if _is_check_to_auto_login or forced:
                taep_app_aw_instance.restart_app()
                time.sleep(taep_app_aw_instance.app_info.launch_duration)
                if not taep_app_aw_instance.check_login():
                    taep_app_aw_instance.login(account_info)
                    self.logger.info(f'Login pass, now try perform RESTART and NOVICE GUIDE process', ext_event=True, tag=log_tag)

                    # 重复检查是否登录成功
                    taep_app_aw_instance.restart_app()
                    time.sleep(taep_app_aw_instance.app_info.launch_duration)
                    if not taep_app_aw_instance.check_login():
                        raise Exception(f'Auto Login failed for {app_id}|{package}')

                    taep_app_aw_instance.try_perform_novice_guide()
                    self.logger.info(f'Login Result: The automatic login and NOVICE GUIDE process has been SUCCESSFULLY COMPLETED.', ext_event=True, tag=log_tag)
                else:
                    self.logger.info(f'Login Result: No need for auto login as login has already been detected.', ext_event=True, tag=log_tag)
                    if not login_mark:
                        self.logger.info(f'BUT! Not found login mark, so try perform NOVICE GUIDE process!', ext_event=True, tag=log_tag)
                        taep_app_aw_instance.try_perform_novice_guide()
                        self.logger.info(f'Novice Guide Result: The NOVICE GUIDE process has been SUCCESSFULLY COMPLETED.', ext_event=True, tag=log_tag)
                        device_marker_store.set_login_mark(package, datetime.utcnow().isoformat() + 'Z')
        except Exception as e:
            self.logger.error_with_tag(f'Auto login failed... Reason: {e}', ext_event=True, tag=log_tag)
            raise e
