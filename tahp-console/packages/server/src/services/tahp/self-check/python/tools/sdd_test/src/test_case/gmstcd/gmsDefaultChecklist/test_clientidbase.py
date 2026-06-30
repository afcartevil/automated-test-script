# -*- coding: utf-8 -*-
import pytest
import logging

from src.utils.adb.adb_utils import (
    getprop,
)


@pytest.mark.require_android_version_min(15)
def test_clientidbase(device_serial,phone_info):
    android_version = getprop("ro.product.build.version.release", device_serial)
    logging.info(f"android_version: {android_version}")
    # if int(android_version) < 15:
    #     pytest.skip(f"Android版本 {android_version} 低于 14, 跳过测试")

    mClientidbase = getprop("ro.com.google.clientidbase", device_serial)
    logging.info(f"mClientidbase: {mClientidbase}")
    assert mClientidbase == "android-transsion"


@pytest.mark.require_android_version_min(15)
def test_clientidbaseam(device_serial,phone_info):
    mClientidbaseam = getprop('ro.com.google.clientidbase.am',device_serial)
    logging.info(f"mClientidbaseam: {mClientidbaseam}")

    if phone_info.get("special_market") == "cocl":
        assert mClientidbaseam == "android-americamovil-{country}"


@pytest.mark.require_android_version_min(15)
def test_clientidbasems(device_serial,phone_info):
    mClientidbasems = getprop('ro.com.google.clientidbase.ms',device_serial)
    logging.info(f"mClientidbasems: {mClientidbasems}")

    if phone_info.get("special_market") == "cocl":
        assert mClientidbasems == "android-americamovil-{country}-rvc3"


@pytest.mark.require_android_version_min(15)
def test_clientidbasevs(device_serial,phone_info):
    mClientidbasevs = getprop('ro.com.google.clientidbase.vs',device_serial)
    logging.info(f"mClientidbasevs: {mClientidbasevs}")

    if phone_info.get("special_market") == "cocl":
        assert mClientidbasevs == "android-americamovil-{country}-rvc3"

@pytest.mark.require_android_version_min(15)
def test_clientidbasecr(device_serial,phone_info):
    mClientidbasecr = getprop('ro.com.google.clientidbase.cr',device_serial)
    logging.info(f"mClientidbasecr: {mClientidbasecr}")

    if phone_info.get("special_market") == "zavc" \
            or phone_info.get("rsa_level") == "ZAVC":
        assert mClientidbasecr == "android-vf-{country}-rvc2"
