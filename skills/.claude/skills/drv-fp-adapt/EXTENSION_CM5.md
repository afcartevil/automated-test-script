# CM5 升级调试 — 飞书摘录与长片段

**定位**：指纹 P1 **主要调试**以主文档 [AI辅助指纹P1调试 / 升级项目指纹调试](https://transsioner.feishu.cn/wiki/A74wwMGsLiTCBXkMJjVccUDfnKd) 为准；本文为 CM5 专项**参考**摘录。

来源：[CM5 升级调试](https://transsioner.feishu.cn/wiki/RQjRw7YfjiXUOUkaTjIc9c6onSg)（与主 SOP 不一致时以飞书最新为准）

## 背景（文档原文要点）

- CM5 **非归一化**升级到榫卯；**HIDL → AIDL**；升级后与**归一化驱动不兼容**，**必须使用非归一化** `tran_common` / `tran_fp_legacy` 路径。
- 设备树 **`compatible`** 决定加载哪套驱动：`tran_fp` → 归一化；`tran_fp_legacy` → 非归一化（与主 SOP 一致）。

## 硬件引脚（文档表格 — Goodix SPI 示例）

| 信号 | GPIO |
|------|------|
| 复位 RST | 45 |
| 中断 IRQ | 13 |
| SPI_MISO | 37 |
| SPI_MOSI | 36 |
| SPI_CS | 35 |
| SPI_CLK | 34 |

具体以项目原理图为准。

## 编译（文档示例）

- 打开 **vnd** 分支代码目录示例：`vendor/transsion/projects/cm8_h973`（仅作路径示例；实际以当前项目 `vnd_*.mk` / `full_*.mk` 为准）。
- 从 `full_*.mk` 取 `SYS_TARGET_PROJECT`，从 `vnd_*.mk` 取 `HAL_TARGET_PROJECT`、`KRN_TARGET_PROJECT`、`VEXT_TARGET_PROJECT`，从 `odm_*.mk` 取 ODM 侧 `VEXT_TARGET_PROJECT`。
- 文档示例宏与命令（**按项目替换**）：

```text
sys  SYS_TARGET_PROJECT := mssi_64_64only_cn_armv82
mgvi HAL_TARGET_PROJECT := mgvi_64_64only_armv82
mgk  KRN_TARGET_PROJECT := mgk_64_entry_level_k612
Vext VEXT_TARGET_PROJECT := k6789v1_64
Odm  VEXT_TARGET_PROJECT := cm5_h8918
```

```bash
source tran_build -l mgvi_64_64only_armv82 -c hal -j 32
source tran_build -l mgk_64_entry_level_k612 -c krn -j 32
source tran_build -l k6789v1_64 -c vext -j 32
source tran_build -l cm5_h8918 -c odm -j 32
```

- 全编打包脚本：将 `build2.sh` 放代码根目录，示例：`./build2.sh cm5_h8918 full`。
- 详细编译：文档指向 **(MTK基线) A16 编译 SOP**（内部链接需在飞书打开）。

## 移植非归一化驱动 `tran_common`（kernel-6.12 示例）

1. 将 `tran_common` 放到 `kernel/kernel_device_modules-6.12/drivers/input/fingerprint/`。
2. `drivers/input/fingerprint/Kconfig` 增加：`source "$(KCONFIG_EXT_PREFIX)/drivers/input/fingerprint/tran_common/Kconfig"`。
3. `drivers/input/fingerprint/Makefile` 增加：`obj-$(CONFIG_TRAN_FINGERPRINT_LEGACY) += tran_common/`。
4. `drivers/input/fingerprint/BUILD.bazel`：增加 `define_mgk_ddk_ko(name = "tran_fp", srcs = [...])`（完整 `srcs`/copts/ko_deps 以文档与仓库为准，块较大见飞书原文）。
5. `arch/arm64/configs/mgk_64_k612_defconfig`（**按实际 defconfig 名替换**）增加：`CONFIG_TRAN_FINGERPRINT_LEGACY=m`。
6. `tran_common/Makefile`：按文档修改（与仓库当前 Makefile 对齐）。
7. `kernel/kleaf/mgk_64.bzl`：增加 `"//kernel_device_modules-{}/drivers/input/fingerprint:tran_fp".format(kernel_version)`（并视情况注释旧 `tran_fp.ko` 行）。
8. `vendor/transsion/projects/cm5_h8918/ko_order_table.csv` 增加一行（路径按实际 kernel 模块目录调整）：

```text
tran_fp.ko,/../kernel_device_modules-6.12/drivers/input/fingerprint/tran_fp.ko,ramdisk,Y,Y,user/userdebug/eng
```

## 汇顶指纹库（Goodix）— 文档要点

1. `hardware/interfaces/biometrics/fingerprint/aidl/transsion/FingerprintEngine.cpp` 中宏：

```cpp
#define GOODIX_FINGERPRINT_HARDWARE_MODULE_ID  "gf_fingerprint"
```

2. 在 `vendor/transsion/projects/cm5_h8918/` 下新建 `fp/`，存放 TA、CA、rc、manifest 等（文档含目录截图占位）。
3. 新增 `fp/Android.bp`：使用 `soong_config_module_type` + `fp_config_cc_prebuilt_library_shared` 预置 `libgf_hal`、`libvendor.transsion.hardware.biometrics.fingerprint`、`gf_fingerprint.default`（`hw/` 安装路径等见飞书全文）。
4. `device-vext.mk`：`PRODUCT_COPY_FILES`（`vendor.goodix.rc`、`manifest_opt.xml`）、`PRODUCT_PACKAGES`、`SOONG_CONFIG_fpconfig`、debug/release 下 **tabin/drbin** 拷贝到 `odm/app/mcRegistry/`（UUID 以供应商交付为准）。

## 上层属性（设置里添加指纹闪退 — 光学 + HBM）

文档说明本地编译可能打不进属性，需 **adb** 手动设置：

```bash
stop
setprop ro.tr_fingerprint.optical.feature.support 1
setprop ro.tr_fingerprint.local.hbm.support 1
start
```

## 工模 APK（无震动、无法录入 — 校准）

1. 路径：`vendor/transsion/system_modules/common/fingerprint/third_finger_apk` 添加 **GFLincoln-aidl-apk-v400.apk** 与 `Android.mk`（`LOCAL_MODULE`、`BUILD_PREBUILT` 等见飞书）。
2. `vendor/transsion/system_modules/common/device.mk`：`PRODUCT_PACKAGES += GFLincoln-aidl-apk-v400`。
3. **Sensor.json**（文档路径示例：`vendor/transsion/vendor_modules/tranfac/TranfacVnd/config/project/mtk/CM5/feature/Sensor.json`）：**删除** `"tranfac.sensor.fingerprint.tran_common_tee": ""`，使工模走**供应商 APK** 流程。
4. 开机工模校准、关机工模：文档引用「指纹开机工模校准」「指纹关机工模测试方法」（飞书内链）。

## 关机工模 — `ftm_transsion_fingerprint.c`

- 定义 `GOODIX_PATCH`：`/odm/lib64/libgf_hal.so`（64 位）或 `/odm/lib/libgf_hal.so`（32 位）。
- 实现 `goodix_test()`：`dlopen` → `dlsym("gf_factory_test_entry")` → 调用 → `dlclose`；在 `fingerprint_test()` 中调用并判断 `FTM_TEST_PASS/FAIL`。
- 完整 C 代码见飞书原文。

## 提交与评审

- Topic 搜索：<https://gerrit.transsion.com/q/topic:cm5-%25E5%258D%2587%25E7%25BA%25A7%25E6%25A6%25AB%25E5%258D%25AF>
- 内核示例变更：<https://gerrit.transsion.com/c/MTK_CODE/quark/kernel_device_modules-6.12/+/1329172>
