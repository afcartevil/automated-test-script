# -*- coding: utf-8 -*-
import pytest
import logging


from src.utils.adb.adb_utils import (
    adb_shell_settings_get_secure
)


@pytest.mark.require_android_version_min(15)
@pytest.mark.require_go_device()
def test_LowRamVerifyDisabled(device_serial):

    '''
    # Case 1: testLowRamVerifyDisabled
    # ID: TOS1510-30910
    # DESCRIPTION: GtsPermissionTestCases-com.google.android.permission.gts.DefaultPermissionGrantPolicyTest#testLowRamVerifyDisabled
    '''

    mVoice_interaction_service  = adb_shell_settings_get_secure(device_serial, "voice_interaction_service")
    logging.info("mVoice_interaction_service=" + mVoice_interaction_service)

    if mVoice_interaction_service is not None:
        reason = "voice_interaction_service is not None, Gts testLowRamVerifyDisabled test fail"
        pytest.skip(reason)
