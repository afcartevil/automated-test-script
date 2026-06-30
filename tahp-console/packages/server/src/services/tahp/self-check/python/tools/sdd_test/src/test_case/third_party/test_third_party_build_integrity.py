# coding=utf-8
from src.utils.adb.adb_utils import getprop


def test_build_integrity_for_third_party_integration(device_serial):
    """
    三方集成冒烟: 检查 Magisk、非官方签名、编译类型、机型属性和调试/root 状态。
    测试步骤: adb shell getprop 查询相关属性。
    预期结果:
    - ro.boot.magisk 未处于 Magisk 引导状态。
    - ro.build.fingerprint 和 ro.build.tags 不包含 test-keys。
    - ro.build.type 不是 userdebug 或 eng。
    - ro.product.model 和 ro.product.vendor.model 一致。
    - ro.debuggable 不是 1。
    - ro.secure 不是 0。
    """
    magisk_status = getprop("ro.boot.magisk", sn=device_serial).strip()
    fingerprint = getprop("ro.build.fingerprint", sn=device_serial).strip()
    build_tags = getprop("ro.build.tags", sn=device_serial).strip()
    build_type = getprop("ro.build.type", sn=device_serial).strip()
    product_model = getprop("ro.product.model", sn=device_serial).strip()
    vendor_model = getprop("ro.product.vendor.model", sn=device_serial).strip()
    debuggable = getprop("ro.debuggable", sn=device_serial).strip()
    secure = getprop("ro.secure", sn=device_serial).strip()

    failures = []

    if magisk_status.lower() not in ("", "0", "false", "no"):
        failures.append(f"ro.boot.magisk 处于异常状态: actual={magisk_status}")

    if "test-keys" in fingerprint:
        failures.append(f"ro.build.fingerprint 包含 test-keys: actual={fingerprint}")

    if "test-keys" in build_tags:
        failures.append(f"ro.build.tags 包含 test-keys: actual={build_tags}")

    if build_type in ("userdebug", "eng"):
        failures.append(f"ro.build.type 为调试编译版本: actual={build_type}")

    if product_model != vendor_model:
        failures.append(
            "ro.product.model 和 ro.product.vendor.model 不一致: "
            f"ro.product.model={product_model}; "
            f"ro.product.vendor.model={vendor_model}"
        )

    if debuggable == "1":
        failures.append("ro.debuggable=1，调试模式已打开")

    if secure == "0":
        failures.append("ro.secure=0，设备可能允许通过 adb root")

    assert not failures, "三方集成构建完整性校验失败: " + "; ".join(failures)
