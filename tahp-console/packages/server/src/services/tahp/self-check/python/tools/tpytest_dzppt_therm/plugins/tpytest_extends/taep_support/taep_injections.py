import os.path
import sys

from aw.basic_aw.boosts import aw_base_boosts
from aw.complex_aw.mid_aw.deivce_allocate.aw_device_allocate import AwDeviceAllocate
from powertrde import env
from powertrde.env import PROJ_DIR
from powertrde.utils.u2_extends import u2utils, u2patches
from tpytest.scheme.scheme_test_env import SchemeTestEnv

import TCoreCapaLib
from TCoreCapaLib import tuiautomator2
from TCoreCapaLib.dutdevice.dutdevice import DutDevice
from TCoreCapaLib.log import logger_set
import testcase


def inject_back_taep_root_path():
    root_path = os.path.join(env.PROJ_DIR, 'taep')
    if root_path not in sys.path:
        sys.path.insert(0, root_path)


def inject_back_u2_patches():
    u2patches.target_u2_module = tuiautomator2


def inject_back_tp_u2_connect():
    def _inner(device_id: str):
        return DutDevice(device_id)

    u2utils.connect_u2_device = _inner


def inject_front_loggers(_logger):
    logger_set.operator_record_logger._logger = _logger
    logger_set.tlogger._logger = _logger
    logger_set.adb_logger._logger = _logger
    logger_set.rec_logger._logger = _logger
    logger_set.tpytest_logger._logger = _logger


def inject_back_taep_case_setup():
    from tpytest_extends.scheme.cases_scheme_taep_mixin import _CasesSchemeTaepMixIn

    def _inner(self):
        DutDevice.image_path = os.path.join(PROJ_DIR, 'taep', 'resource', 'image', self.case_name)
        DutDevice.sn = self.device_id
        inject_front_loggers(self.logger)
        _sn_log_tag = self.scheme_env.sn_log_tag
        if _sn_log_tag:
            _tag = f'{_sn_log_tag}][TAEP'
        else:
            _tag = 'TAEP'
        self.logger.info(f'[{self.case_name}] Setup', tag=_tag)
        _f = self.taep_case_setup_function
        if _f:
            _f()

    _CasesSchemeTaepMixIn._on_taep_setup_hook = _inner


def inject_back_taep_case_teardown():
    from tpytest_extends.scheme.cases_scheme_taep_mixin import _CasesSchemeTaepMixIn

    def _inner(self):
        _sn_log_tag = self.scheme_env.sn_log_tag
        if _sn_log_tag:
            _tag = f'{_sn_log_tag}][TAEP'
        else:
            _tag = 'TAEP'
        self.logger.info(f'[{self.case_name}] Teardown', tag=_tag)
        _f = self.taep_case_teardown_function
        if _f:
            _f()

    _CasesSchemeTaepMixIn._on_taep_teardown_hook = _inner


def inject_front_config(_env_config_dict: dict):
    TCoreCapaLib.config = _env_config_dict


def inject_front_dutdevice_image_path_default_value():
    DutDevice.image_path = os.path.join(PROJ_DIR, 'taep', 'resource', 'image', '__placeholder__')


def inject_front_all_boosts():
    aw_base_boosts.inject_all_boosts()
    # ...


def inject_front_aw_device_allocate(_env: SchemeTestEnv):
    def _get_device_id():
        return _env.device_id

    def _get_c_device_id():
        return _env.c_device_id

    AwDeviceAllocate.device_id = _get_device_id
    AwDeviceAllocate.c_device_id = _get_c_device_id
    AwDeviceAllocate.is_hook = lambda: True


def pre_inject_all(_env: SchemeTestEnv):
    inject_back_u2_patches()
    inject_back_tp_u2_connect()
    inject_back_taep_case_setup()
    inject_back_taep_case_teardown()
    inject_front_config(_env.user_config.configured_config_dict)
    inject_front_dutdevice_image_path_default_value()
    inject_front_all_boosts()
    inject_front_aw_device_allocate(_env)


def post_inject_all(_env: SchemeTestEnv):
    inject_front_loggers(_env.logger.classical_logger)


def inject_taep_aw_factory():
    # FIXME
    d = DutDevice()
    d.click_by_img()
