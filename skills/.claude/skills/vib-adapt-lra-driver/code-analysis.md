# LRA 代码分析附录（bring-up 深入时读）

主流程见 [SKILL.md](SKILL.md)。仅在 dmesg 定不了阶段或需改 `haptic_hv.c` 时展开。

## 关键文件

| 文件 | 职责 |
|------|------|
| `haptic_hv.c` | `aw_i2c_probe`、`ctrl_init`、`ram_load`、`vibrator_init` |
| `haptic_hv.h` | `AW_*_DRIVER_ENABLE`、CHIPID、`AAC_RICHTAP_SUPPORT` |
| `aw8692x.c` 等 | `check_qualify`、`parse_dt` |
| `BUILD.bazel` | `richtap_haptic_hv` 源列表 |

## Probe 链

```
aw_i2c_probe → parse_dt_gpio → GPIO request → ctrl_init → check_qualify
→ parse_chipid → parse_dt → irq_config → misc_register → vibrator_init
→ ram_work_init → ram_load → probe completed
```

## CHIPID（`ctrl_init` / `parse_chipid`）

| ENABLE 宏 | 典型日志 |
|-----------|----------|
| `AW8692X_DRIVER_ENABLE` | `detected aw86926` 等 |
| `AW8693X_DRIVER_ENABLE` | `detected aw86936` 等 |
| `AW869X_DRIVER_ENABLE` | `detected aw8697` 等 |

`unexpected chipid`：I2C/供电/DWS 或 **未编入对应 aw869*.c / 未开 ENABLE**。

## 固件（`ram_load`）

`aw_ram_name`（默认 `haptic_ram.bin`）→ `request_firmware_nowait` → checksum → `container_update`。  
失败串：`failed to read` / `check sum err` / `ram firmware update failed`。

## 节点名

- RichTap：`/dev/aw8697_haptic`（`AAC_RICHTAP_SUPPORT`）
- LED：`vibrator_single`（`KERNEL_OVER_5_10`）或 `vibrator_l`/`r`（`AW_DOUBLE`）

## 快速 grep

```bash
rg "aw_err|unqualified|chip id" drivers/misc/mediatek/richtap_haptic_hv --glob "*.c"
rg "aw8692x_|haptic_hv@|lra,info" arch/arm64/boot/dts/mediatek/tp/
```
