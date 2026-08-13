# 归一化项目升级榫卯指纹调试 — 飞书摘录

**定位**：指纹 P1 **主要调试**以主文档 [AI辅助指纹P1调试 / 升级项目指纹调试](https://transsioner.feishu.cn/wiki/A74wwMGsLiTCBXkMJjVccUDfnKd) 为准；本文为归一化榫卯专项**参考**摘录。

来源：[归一化项目升级榫卯指纹调试](https://transsioner.feishu.cn/wiki/DXGIwLBtqiitppkWO90cx6k3nZf)（与主 SOP / 量产分支不一致时以飞书与量产为准）

## 背景

- **大版本升级**：升级前 A15 指纹为**归一化**，升级后仍为归一化并适配**榫卯**；若升级前为非归一化则升级后保持非归一化（例如 **CM5**）。
- **算法**：升级前后与**量产**同一版本；TA 使用升级前 **`.a`** 库编译，**HAL 共用**。

## 架构判定（与主 SOP 对齐）

- **驱动**：`kernel/.../tran_common_v2` 且 `compatible = "tran_fp"` → **归一化**；`tran_common` 且 **`compatible = "tran_fp_legacy"`** → 非归一化（文档表述）。
- **服务**：`android.hardware.biometrics.fingerprint-service`（AIDL）多为归一化；`@2.1-service`（HIDL）多为非归一化。
- **Log**：tag **`tran_hal`** 多为归一化；**`xxx_hal`** 多为非归一化。

## 器件与原理图

- 器件选型：[BOM 关键器件查询](https://bom.transsion.com/#/manage/keyDevices-query) 或升级项目信息中的器件表。
- 原理图确认：**中断、复位、SPI_CLK、SPI_CS、SPI_MOSI、SPI_MISO** 对应 GPIO。

## DWS（三处一致）

文档示例路径（**x6876_h786 / mt6878**，按项目替换）：

- `vendor/mediatek/proprietary/bootable/bootloader/preloader/custom/x6876_h786/dct/dct/codegen.dws`
- `vendor/mediatek/proprietary/tools/dct/dws/mt6878/x6876_h786.dws`
- `vendor/mediatek/proprietary/custom/x6876_h786/kernel/dct/dct/codegen.dws`

**须与 A15 保持一致**，否则可能引发时序问题。

## 驱动与 DTS

- 适配归一化或非归一化驱动后，**DTS** 可从 A15 拷贝，例如：  
  `kernel/kernel_device_modules-6.1/arch/arm64/boot/dts/mediatek/x6876_h786.dts`

## KO 表

在 `vendor/transsion/projects/x6876_h786/ko_order_table.csv` 增加（路径按实际 kernel 调整）：

```text
tran_fp_v2.ko,/../kernel_device_modules-6.1/drivers/input/fingerprint/tran_common_v2/tran_fp_v2.ko,odm,Y,N,user/userdebug/eng
```

## 指纹库编译（Goodix 示例路径）

从量产分支获取 **`libtran_vnd.a`**、`gf_config_ex.c` / `gf_config_ex.h`，并在 `gf_config_ex.c` 中按项目定义宏。文档示例路径：

- `vendor/transsion/vendor_modules/fingerprint/transsion/ta/goodix/libs/ARM_V8A_AARCH64/optics/cfg/gf_config_ex.c`
- `.../optics/inc/gf_config_ex.h`
- `.../optics/gw9598/debug/libtran_vnd.a` 与 `release/libtran_vnd.a`

- **参考提交（仅用于编 TA，文档写明无需合入）**：  
  <https://gerrit.transsion.com/c/TRAN_CODE/vendor/transsion/bsp/fingerprint/+/1437979>

- **编译**：编 **vext** 组件即可产出指纹库；产物示例：  
  `out_vext/target/product/k6878v1_64/vendor/app/mcRegistry`（产品名以实际 `out_vext` 为准）。
- 将生成的 TA 拷贝到例如：  
  `vendor/transsion/projects/x6876_h786/fp/ta/debug`（及 release 目录）。

## device-vext.mk（ODM 拷贝）

文档示例 `userdebug` / `else` 分支中 `PRODUCT_COPY_FILES` 将 **tabin / drbin** 拷到 `odm/app/mcRegistry/`（UUID 以项目为准）。

## ODM 加载 TA（须合入的逻辑）

- 在打开 TA 前设置本地 registry：若 `tranProjectInfo->tran_fp_load_ta_from_odm_path` 为真，则  
  `std::string local_registry = "/odm/app/mcRegistry"`，并调用 **`TEEC_TT_SetLocalRegistryPath(local_registry.c_str())`**。
- **参考提交（文档写明需合入）**：  
  <https://gerrit.transsion.com/c/TRAN_CODE/vendor/transsion/bsp/fingerprint/+/1439206>

## tran_fp_project_info.json

- 路径示例：`vendor/transsion/projects/x6876_h786/fp_fw/tran_fp_project_info.json`
- 增加 **`"tran_fp_load_ta_from_odm_path": 1`**，用于控制是否从 ODM 路径加载 TA。
- 修改 JSON 后需更新 **checksum**：将文件拷至  
  `vendor/transsion/vendor_modules/fingerprint/transsion/hal/inc/json_tools`，执行：  
  `./json-tool.o <json_file_name>`  
  获取新 checksum 并写回配置链。

## 工模

- 底层宏控参考「工模底层宏控适配榫卯 4.0 解耦」（飞书内图）。
- `ProjectConfig.mk`：

```makefile
TRAN_OPTICAL_FINGERPRINT_SUPPORT=yes
TRAN_FINGERPRINT_SUPPORT=tran_common_tee
```

- `vendor/transsion/vendor_modules/TranfacVnd/config/project/mtk/X6876/feature/Sensor.json`（光学示例）：

```json
{
  "featureConfig": {
    "tranfac.sensor.fingerprint.optical": "",
    "tranfac.sensor.fingerprint.tran_common_tee": ""
  },
  "featureForce": {},
  "featureExclude": {}
}
```

## Topic 与延伸阅读

- 提交 topic 搜索：  
  <https://gerrit.transsion.com/q/topic:X6876_p1_%25E8%25B0%2583%25E8%25AF%2595>
- 文档建议对照：**X6873 指纹归一化升级到榫卯项目调试**（飞书内链）。

## 补充：Trustonic 默认路径与 UUID（文档摘要）

- 设置路径后 **`TEEC_OpenSession()`** 打开指定 UUID 的 TA；UUID 定义见：  
  `vendor/transsion/vendor_modules/fingerprint/transsion/hal/inc/ChipIdNameUuid.h`
- 默认加载路径相关：`vendor/mediatek/proprietary/trustzone/trustonic/source/external/mobicore/common/600/ClientLib/src/driver.cpp`、  
  `.../Daemon/src/MobiCoreDriverDaemon.cpp`（文档用于理解默认路径与 ODM 覆盖关系）。
- A16 后不同指纹芯片 UUID 区分更细；**`tran_uuid`** 为小 TA UUID；**`getVendorChipId()`** 通过小 TA 取芯片 ID 再映射 TA UUID。
