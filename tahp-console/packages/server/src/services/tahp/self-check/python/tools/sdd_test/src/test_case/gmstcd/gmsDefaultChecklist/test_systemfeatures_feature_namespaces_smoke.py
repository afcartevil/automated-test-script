# -*- coding: utf-8 -*-
import re

import pytest

from src.utils.adb.adb_utils import adb_shell, getprop


def _shell_output(device_serial, command):
    result = adb_shell(device_serial, command, no_retry=True)
    return (result.get("output") or result.get("error") or "").strip()


@pytest.mark.require_android_version_min(15)
def test_feature_namespaces_consistency_smoke(device_serial):
    """
    ID:TOS1600-SYSFEATURE-NAMESPACE
    DESCRIPTION:[CTS]SystemFeaturesTest#testFeatureNamespaces
    FIDELITY:L2- (adb-only namespace validation)
    """
    features_out = _shell_output(device_serial, "pm list features")
    if not features_out:
        pytest.skip("pm list features returns empty output")

    device_features = set()
    for line in features_out.splitlines():
        line = line.strip()
        if line.startswith("feature:"):
            feature_name = line[len("feature:"):].strip()
            if "=" in feature_name:
                feature_name = feature_name.split("=", 1)[0].strip()
            if feature_name:
                device_features.add(feature_name)

    if not device_features:
        pytest.skip("No feature entries parsed from pm list features output")

    is_rel = getprop("ro.build.version.codename", device_serial) == "REL"
    android_allowed_prefix = ("android.hardware.", "android.software.")
    valid_android_feature_pattern = re.compile(r"^android\.[a-z0-9_.]+$")
    violations = []
    for feature_name in device_features:
        if not feature_name.startswith("android"):
            continue
        if (not is_rel) and feature_name == "android.software.preview_sdk":
            continue
        if valid_android_feature_pattern.match(feature_name) is None:
            violations.append(feature_name + " -> invalid-format")
            continue
        if not feature_name.startswith(android_allowed_prefix):
            violations.append(feature_name + " -> invalid-namespace-prefix")

    if violations:
        violations.sort()
        pytest.fail("\n".join(violations))
