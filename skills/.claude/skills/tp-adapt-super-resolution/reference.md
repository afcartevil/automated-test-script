# 超级触控 / 超分 — 源码参考

分支 `tOS_mtk_A16_trunk`，根路径 `kernel/kernel_device_modules-6.12/drivers/input/touchscreen/transsion/`。

## OpenGrok

```text
python opengrok_query.py --branch tOS_mtk_A16_trunk --full supplier-resolution --path dts/mediatek/tp --top 10
python opengrok_query.py --branch tOS_mtk_A16_trunk --ref resolution_multiples --path transsion --top 15
python opengrok_query.py --branch tOS_mtk_A16_trunk --def tran_parse_dt --json
```

参考 dtsi：`tran_mt6878_cm7_touch.dtsi`、`tran_mt6897_cm8_touch.dtsi`、`tran_mt6789_x6855_touch.dtsi`（均为 `supplier-resolution-0 = <16>`）。

## 关键文件

| 文件 | 职责 |
|------|------|
| `core/transsion_core.c` | `tran_parse_dt()` 解析 `supplier-resolution-X` → `supplier_list.resolution_multiples` |
| `core/transsion_sub_device.c` | `tran_parse_sub_dt()` 子屏同样解析（`controller_type` 默认 1） |
| `core/include/transsion_core.h` | `struct supplier_list { u32 resolution_multiples; ... }` |
| `vendor/focaltech/ft3683g_spi/focaltech_core.c` | `fts_input_report_b()` 读 `controller.supplier->resolution_multiples` |
| `vendor/goodix/gt9916_common/goodix_ts_core.c` | `goodix_ts_report_finger()` 同上 |

## DTS 解析（`tran_parse_dt` / `tran_parse_sub_dt`）

```c
snprintf(supplierx, ..., "supplier-resolution-%d", i);
of_property_read_u32(np, supplierx, &resolution_multiples);
/* 缺省 → resolution_multiples = 1 */
tmpList->resolution_multiples = resolution_multiples;
```

## Supplier 匹配（`match_tp_controller`）

1. 按 LCM 名或 `any` 匹配 `supplier-X`
2. vendor 名须与 `supplier_info` 一致
3. `check_support_ic()` 后 `controller->supplier = supList`
4. vendor probe 完成方可读到 `resolution_multiples`

## Vendor 上报差异

**Focaltech**（`fts_input_report_b`）

- 从 `ft3683g_controller.supplier->resolution_multiples` 取值
- 上报 `ABS_MT_POSITION_X/Y` 用 IC 原始坐标（高精度）
- 日志 `x_info/y_info = raw / resolution_multiples`
- 工模：`TRAN_FACTORY_MODE` 时先除 N 再上报

**Goodix**（`goodix_ts_report_finger`）

- 从 `goodix_controller.supplier->resolution_multiples` 取值
- 正常模式：上报原始高精度坐标，日志坐标除 N
- 工模：上报前除 N

## display-coords 示例

`tran_mt6878_cm7_touch.dtsi`：

```dts
supplier-resolution-0 = <16>;
focaltech,display-coords = <0 0 17279 38975>;
```

IC 侧高精度协议（Focaltech `TOUCH_PROTOCOL_v2`）使用 12-bit 坐标，注释掉的 `events[i].x / FTS_HI_RES_X_MAX` 表明超分由 DTS 倍数 + display-coords 承接，而非驱动内硬编码缩放。

## 支持 resolution_multiples 的 vendor（A16 trunk）

focaltech（ft3683g / no_flash / thp）、goodix gt9916、chipone 9916、ilitek tddi、novatek、omnivision td4160
