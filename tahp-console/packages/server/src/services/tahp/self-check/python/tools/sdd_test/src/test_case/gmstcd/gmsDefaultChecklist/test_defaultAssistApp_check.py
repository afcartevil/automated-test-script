# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    get_cmd_overlay_lookup,
)


@pytest.mark.require_android_version_min(15)
def test_defaultAssistApp_check(device_serial):

    # 检测 GMS Req 8.5. Default Assist app

    mConfig_forceVoiceInteractionServicePackage = get_cmd_overlay_lookup(device_serial,"string","config_forceVoiceInteractionServicePackage")
    logging.info("mConfig_forceVoiceInteractionServicePackage=" + mConfig_forceVoiceInteractionServicePackage)

    if mConfig_forceVoiceInteractionServicePackage is not None \
            and mConfig_forceVoiceInteractionServicePackage != "":
        reason = "config_forceVoiceInteractionServicePackage MUST NOT set!"
        pytest.fail(reason)

