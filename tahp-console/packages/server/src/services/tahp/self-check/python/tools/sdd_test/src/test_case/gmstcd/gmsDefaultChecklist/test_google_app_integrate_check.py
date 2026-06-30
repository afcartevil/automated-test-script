# -*- coding: utf-8 -*-
import json
import logging
from pathlib import Path

import pytest

from src.utils.adb.adb_utils import (
    get_apkpath_by_package,
    get_dumpsys_package,
    get_feature,
    getprop,
    is_file_exist,
)


ARCORE_PACKAGE = "com.google.ar.core"
GOOGLE_LENS_LIG_FEATURE = "com.google.lens.feature.IMAGE_INTEGRATION"
GOOGLE_LENS_OEM_IMAGE_PACKAGE_PROP = "ro.com.google.lens.oem_image_package"
GOOGLE_LENS_LIG_XML_PATHS = [
    "/product/etc/permissions/com.android.lens.lig.xml",
    "/system_ext/etc/permissions/com.android.lens.lig.xml",
    "/system/etc/permissions/com.android.lens.lig.xml",
    "/vendor/etc/permissions/com.android.lens.lig.xml",
    "/odm/etc/permissions/com.android.lens.lig.xml",
]


def _project_root():
    return Path(__file__).resolve().parents[4]


def _load_optional_pms_info(device_serial):
    display_id = getprop("ro.build.display.id", device_serial)
    candidates = [
        _project_root() / "debug_pms.json",
        _project_root() / f"{display_id}_pms.json",
    ]

    for candidate in candidates:
        if not candidate.exists():
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            logging.warning(f"Failed to read PMS info from {candidate}: {error}")
    return None


def _get_pms_bool(pms_info, key):
    if not pms_info or key not in pms_info:
        return None

    value = pms_info[key]
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return bool(value)


def _get_google_lens_lig_xml_paths(device_serial):
    return [
        xml_path
        for xml_path in GOOGLE_LENS_LIG_XML_PATHS
        if is_file_exist(device_serial, xml_path)
    ]


def _split_package_property(package_property):
    return [
        package_name.strip()
        for package_name in str(package_property).split(",")
        if package_name.strip()
    ]


def test_ARCore_app_list_check(device_serial):
    build_type = getprop("ro.build.type", device_serial)
    logging.info(f"ro.build.type: {build_type}")

    if build_type != "user":
        pytest.skip("This is not a user build, skip test_ARCore_app_list_check")

    pms_info = _load_optional_pms_info(device_serial)
    is_join_ar_core = _get_pms_bool(pms_info, "is_join_ar_core")
    logging.info(f"pms is_join_ar_core: {is_join_ar_core}")

    if is_join_ar_core is None:
        pytest.skip("PMS field is_join_ar_core not found, skip ARCore app list check")

    arcore_path = get_apkpath_by_package(device_serial, ARCORE_PACKAGE)
    arcore_version = get_dumpsys_package(device_serial, ARCORE_PACKAGE, "versionName")
    logging.info(f"ARCore path: {arcore_path}")
    logging.info(f"ARCore versionName: {arcore_version}")

    if is_join_ar_core:
        pytest.skip("ARCore support project, skip negative preload interception")

    if arcore_path or arcore_version:
        pytest.fail(
            "Non-ARCore project should not preload Google Play services for AR, "
            f"path={arcore_path}, dumpsys={arcore_version}"
        )


def test_google_lens_lig_property_check(device_serial):
    build_type = getprop("ro.build.type", device_serial)
    logging.info(f"ro.build.type: {build_type}")

    if build_type != "user":
        pytest.skip("This is not a user build, skip google lens LIG property check")

    google_lens_feature = get_feature(device_serial, GOOGLE_LENS_LIG_FEATURE)
    google_lens_oem_image_package = getprop(
        GOOGLE_LENS_OEM_IMAGE_PACKAGE_PROP, device_serial
    )
    google_lens_lig_xml_paths = _get_google_lens_lig_xml_paths(device_serial)

    logging.info(f"{GOOGLE_LENS_LIG_FEATURE}: {google_lens_feature}")
    logging.info(
        f"{GOOGLE_LENS_OEM_IMAGE_PACKAGE_PROP}: {google_lens_oem_image_package}"
    )
    logging.info(f"com.android.lens.lig.xml paths: {google_lens_lig_xml_paths}")

    has_google_lens_feature = bool(str(google_lens_feature or "").strip())
    has_google_lens_property = bool(
        str(google_lens_oem_image_package or "").strip()
    )
    has_google_lens_lig_xml = bool(google_lens_lig_xml_paths)

    if has_google_lens_feature:
        if not has_google_lens_property:
            pytest.fail(
                "Lens image integration feature exists but "
                "ro.com.google.lens.oem_image_package is not set, "
                f"feature={google_lens_feature}, xml={google_lens_lig_xml_paths}"
            )

        package_name_list = _split_package_property(google_lens_oem_image_package)
        if not package_name_list:
            pytest.fail(
                "ro.com.google.lens.oem_image_package is empty after split, "
                f"property={google_lens_oem_image_package}"
            )

        missing_package_list = [
            package_name
            for package_name in package_name_list
            if not get_apkpath_by_package(device_serial, package_name)
        ]
        if missing_package_list:
            pytest.fail(
                "Lens image integration property invalid, "
                f"property={google_lens_oem_image_package}, "
                f"missing package={missing_package_list}"
            )
        return

    if has_google_lens_property or has_google_lens_lig_xml:
        pytest.fail(
            "Lens image integration is not supported, property/xml should both "
            f"be removed, feature={google_lens_feature}, "
            f"{GOOGLE_LENS_OEM_IMAGE_PACKAGE_PROP}={google_lens_oem_image_package}, "
            f"com.android.lens.lig.xml={google_lens_lig_xml_paths}"
        )
