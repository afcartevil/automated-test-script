# -*- coding: utf-8 -*-
import logging

import pytest

from src.utils.adb.adb_utils import adb_shell

def test_BootClassPath_check(device_serial):
    """
    ID: TOS1600-905
    DESCRIPTION: [CTS]CtsClasspathsTestCases-com.android.os.classpath.ClasspathsTest#testBootclasspath
    """
    res = adb_shell(device_serial, "printenv BOOTCLASSPATH")
    bootclasspath = res["output"].strip()
    logging.info(f"BOOTCLASSPATH={bootclasspath}")

    if not bootclasspath:
        pytest.fail("$BOOTCLASSPATH is empty")

    elements = [p.strip() for p in bootclasspath.split(":") if p.strip()]

    # 验证 BOOTCLASSPATH 不包含 services.jar
    SERVICES_JAR = "/system/framework/services.jar"
    if SERVICES_JAR in elements:
        pytest.fail(f"BOOTCLASSPATH contains services.jar: {SERVICES_JAR}")

    # 验证 BOOTCLASSPATH 不包含重复的 jar 包
    seen = set()
    dups = set()
    for e in elements:
        if e in seen:
            dups.add(e)
        else:
            seen.add(e)
    if dups:
        pytest.fail("BOOTCLASSPATH contains duplicate entries: " + ",".join(sorted(dups)))

    # 验证必须包含的 jar 包且顺序正确
    LIBART_JAR       = "/apex/com.android.art/javalib/core-libart.jar"
    FRAMEWORK_JAR    = "/system/framework/framework.jar"
    ICU4J_JAR        = "/apex/com.android.i18n/javalib/core-icu4j.jar"
    SDKEXTENSIONS_JAR = "/apex/com.android.sdkext/javalib/framework-sdkextensions.jar"
    required = [LIBART_JAR, FRAMEWORK_JAR, ICU4J_JAR, SDKEXTENSIONS_JAR]

    pos = {p: i for i, p in enumerate(elements)}
    missing = [r for r in required if r not in pos]
    if missing:
        pytest.fail("BOOTCLASSPATH missing required entries: " + ",".join(missing))

    idx = [pos[r] for r in required]
    if not all(idx[i] < idx[i + 1] for i in range(len(idx) - 1)):
        pytest.fail(
            "BOOTCLASSPATH order incorrect: expected LIBART < FRAMEWORK < ICU4J < SDKEXTENSIONS"
        )

    # 验证路径前缀顺序
    required_prefix = [
        "/apex/com.android.art/",
        "/system/",
        "/system_ext/",
        "/apex/com.android.i18n/",
        "/apex/",
    ]
    prefix_indices = []
    for e in elements:
        idxp = next((i for i, pf in enumerate(required_prefix) if e.startswith(pf)), None)
        if idxp is None:
            pytest.fail(f"BOOTCLASSPATH jar path does not start with required prefix: {e}")
        prefix_indices.append(idxp)

    if any(prefix_indices[i] < prefix_indices[i - 1] for i in range(1, len(prefix_indices))):
        pytest.fail("BOOTCLASSPATH prefix order incorrect")

    logging.info("check BOOTCLASSPATH pass")
