# DRV_FP_Adapt — 文档摘录与长示例

**主文档** [AI辅助指纹P1调试](https://transsioner.feishu.cn/wiki/A74wwMGsLiTCBXkMJjVccUDfnKd) 为 Skill **主要调试依据**；下文大块 DTS/JSON/KO/`tran_core` 等摘录与主文档二、章一致。第三节典型项目的**参考**链接见本节次段。

来源：<https://transsioner.feishu.cn/wiki/A74wwMGsLiTCBXkMJjVccUDfnKd>

**典型项目参考**（主文档**第三节**所链；与一、二章主流程互为补充）：需要 CM5 / X6885 / 归一化榫卯等案例或额外细节时查阅 [EXTENSION_CM5.md](EXTENSION_CM5.md)、[EXTENSION_X6885.md](EXTENSION_X6885.md)、[EXTENSION_NORMALIZED_SUNMAO.md](EXTENSION_NORMALIZED_SUNMAO.md) 及飞书：<https://transsioner.feishu.cn/wiki/RQjRw7YfjiXUOUkaTjIc9c6onSg> · <https://transsioner.feishu.cn/wiki/G2p1wEUC5iERW7kqhpMcyPkfnxd> · <https://transsioner.feishu.cn/wiki/DXGIwLBtqiitppkWO90cx6k3nZf>。

## 非归一化 DTS 示例要点（x6885）

- 升级前路径示例：`.../kernel-5.10/arch/arm64/boot/dts/mediatek/x6885_h8923.dts`，节点 `compatible = "tran_fp"`。
- 升级后路径示例：`kernel/kernel_device_modules-6.12/arch/arm64/boot/dts/mediatek/x6885_h8923.dts`，节点改为 **`compatible = "tran_fp_legacy"`**，pinctrl 中 SPI 子节点名在文档示例里为 `fingerprint_spi_default: spimode_default`（注意与升级前 `tran_fp_spimode_default` 等差异），MI/MO 顺序以硬件为准。

完整节点与 `&pio` 块见原 Wiki（文档含大段可复制 DTS）。

## 归一化 DTS 示例要点（x6876）

- 升级前后均为 `compatible = "tran_fp"`，`&spi1` 与 `vmch-supply`、`history-support` 等保持文档示例一致。

## 非归一化 Sensor.json（光学）

主 SOP 通用示例（仅光学键）：

```json
{
  "featureConfig": {
    "tranfac.sensor.fingerprint.optical": ""
  },
  "featureForce": {},
  "featureExclude": {}
}
```

若 CM5 等典型项目在 `Sensor.json` 上有额外约束，见 [EXTENSION_CM5.md](EXTENSION_CM5.md)。

## 归一化 Sensor.json（光学）

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

## 归一化 Sensor.json（电容）

```json
{
  "featureConfig": {
    "tranfac.sensor.fingerprint.tran_common_tee": ""
  },
  "featureForce": {},
  "featureExclude": {}
}
```

## KO 表示例（摘自文档）

非归一化 `ko_order_table.csv` 行示例：

```text
tran_fp.ko,/../kernel_device_modules-6.12/drivers/input/fingerprint/tran_fp.ko,ramdisk,Y,Y,user/userdebug/eng
```

归一化：

```text
tran_fp_v2.ko,/../kernel_device_modules-6.1/drivers/input/fingerprint/tran_common_v2/tran_fp_v2.ko,odm,Y,N,user/userdebug/eng
```

## tran_core.c 需注释块（文档原文）

在 `vendor/transsion/vendor_modules/fingerprint/transsion/ta/tran_common/tran/tran_core.c` 中注释：

```c
/*  err = (tran_error_t) tran_extra_cmd(E_SET_CONFIG, config_cmd, sizeof(tran_set_config_cmd_t), NULL, 0);
if (err != TRAN_SUCCESS) {
    TRAN_LOGE(LOG_TAG "[%s] tran_extra_cmd failed", __func__);
    err = TRAN_ERROR_INVALID_DATA;
    break;
}
*/
```

## Goodix 路径示例（文档）

升级前参考：

- `vendor/transsion/bsp/fingerprint/transsion/ta/goodix/libs/ARM_V8A_AARCH64/optics/cfg/gf_config_ex.c`
- `vendor/transsion/bsp/fingerprint/transsion/ta/goodix/libs/ARM_V8A_AARCH64/optics/inc/gf_config_ex.h`
- `.../optics/gw9598/debug/libtran_vnd.a` 与 `release/libtran_vnd.a`

升级后：

- `vendor/transsion/vendor_modules/fingerprint/transsion/ta/goodix/libs/ARM_V8A_AARCH64/optics/cfg/gf_config_ex.c`
- `vendor/transsion/vendor_modules/fingerprint/transsion/ta/goodix/libs/ARM_V8A_AARCH64/optics/inc/gf_config_ex.h`
- `.../gw9598/debug|release/libtran_vnd.a`

不同 IC 文件名可能不同，按项目替换。
