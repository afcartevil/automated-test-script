# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    get_dumpsys_package,
    get_cmd_overlay_lookup,
)


@pytest.mark.require_android_version_min(16)
def test_gms_overlay_comms_check(device_serial):

        '''
        # default phone
        '''
        mDefaultDialer_value = get_cmd_overlay_lookup(device_serial, "string", "config_defaultDialer")
        logging.info(f"mDefaultDialer_value: {mDefaultDialer_value}")

        get_defaultDialer_versionName = get_dumpsys_package(device_serial, mDefaultDialer_value, "versionName")
        logging.info(f"get_defaultDialer_versionName: {get_defaultDialer_versionName}")

        '''
        # default Contacts
        '''
        mSystemContacts_value = get_cmd_overlay_lookup(device_serial, "string", "config_systemContacts")
        logging.info(f"mSystemContacts_value: {mSystemContacts_value}")

        get_SystemContacts_versionName = get_dumpsys_package(device_serial, mSystemContacts_value, "versionName")
        logging.info(f"get_SystemContacts_versionName: {get_SystemContacts_versionName}")

        if get_defaultDialer_versionName == "" \
                or get_SystemContacts_versionName == "":
            pytest.fail("test_gms_overlay_comms_check check fail")

