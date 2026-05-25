---
name: vib-adapt-lra-driver
description: Guides Transsion/MTK LRA haptic driver adaptation—ko_order_table, DTS+DWS pins vs richtap_haptic_hv, lra_fw, and dmesg probe triage. Use for 线性马达驱动适配、LRA port、probe failed、ko表、DWS、lra_fw、haptic_ram.bin、irq/reset-gpio、richtap_haptic_hv；HAL/HE 无振见 vib-log-fault，ERM 见 vib-adapt-rotor-driver。
disable-model-invocation: false
---

# LRA 驱动适配

**用途**：新机/移植 **内核侧** 线性马达点亮（KO → 引脚 → 驱动/固件 → adb 验证）。  
**路径**：`~/.cursor/kb/tp-vib-harness/references/vibrator-path-reference-20260520.md`

**不归本 skill**：转子 ERM、纯 HAL/HE 无振（`vib-log-fault`）、仅宏控（`vib-adapt-projectconfig`）、节点权限（`vib-adapt-haptic-rc` / `fc-vib-selinux`）。

## Bring-up 顺序

```
KO/宏控 → DTS 与三处 DWS 一致 → 驱动+IC+固件对齐 → dmesg 定阶段 → fc-vib-*
```

```bash
adb shell lsmod | grep -iE "richtap|haptic|aw869"
adb shell dmesg | grep -iE "haptic|richtap|awinic|aw869" | tail -30
```

## 1. KO 与编译

- 表：`vendor/transsion/projects/<project>/ko_order_table.csv`（列含义 → **`tp-adapt-ko-order`**）
- 行含 `richtap_haptic_hv` / `tran_lra` / `aac_haptic` 等；`KO path` 指向当前 `kernel_device_modules-*`
- 常见：`odm` + `BootTime.completed=Y`；与 `TRAN_RICHTAP_SUPPORT` 一致
- 缺行：`drivers/misc/mediatek/richtap_haptic_hv/BUILD.bazel`（`richtap_haptic_hv`）+ `CONFIG_RICHTAP_HAPTIC_HV`
- 无模块 / 无 probe → 先查表与宏控，再看 dmesg

## 2. DTS + DWS（同改同查）

文件：`arch/arm64/boot/dts/mediatek/tp/tran_*_touch.dtsi`（常与 TP 同文件）。

**从 DTS 记下**（须与 DWS、LK 一致）：

| 项 | 示例 |
|----|------|
| `&i2cN` + `reg` | `i2c7`, `0x5A` |
| `irq-gpio` / `reset-gpio` | `&pio 4` / `&pio 22` |
| `lra,info = <type bus rst>` | `<1 7 22>` → **i2c7 + gpio22** |

**DWS**：三份须 diff 一致（细则 → **`tp-adapt-dws-pin`**）：

1. `vendor/mediatek/proprietary/tools/dct/dws/<platform>/<project>/<project>.dws`
2. `…/bootable/bootloader/preloader/custom/<project>/dct/dws/codegen.dws`
3. `…/custom/<project>/kernel/dct/dct/codegen.dws`

搜索 net：`VIBR` / `HAPTIC` / `LRA`。约定：**RST**=输出低+下拉；**INT**=EINT/输入+上拉；**I2C**=与 `&i2cN` 同通道；**LDO**=与 `regulator_vibrator` 一致（**`vib-adapt-dts-regulator`**）。

**驱动树**：A16 → `drivers/misc/mediatek/richtap_haptic_hv/`；u0 → `…/tran_lra/`。  
`BUILD.bazel` 中 `aw8692x.c` 等须与 DTS `aw8692x_*` / `aw8693x_*` 前缀一致。

## 3. 固件

- **机型目录**：`vendor/transsion/projects/<project>/lra_fw/`（`fw/` + `lra.mk` → `device-vext.mk`）
- 勿仅用驱动树内 `richtap_haptic_hv/fw/` 当量产源
- 驱动默认 `aw_ram_name = "haptic_ram.bin"` → 机上 `/odm/firmware/` 有名且可加载
- HE（`/vendor/etc/vibrator/*.he`）属上层，probe 后用 **`fc-vib-he`**

## 4. 五维对齐 + 日志定因

port/改码时五项同参考机对齐：**DWS** | **BUILD 编入的 aw869*.c** | **`haptic_hv.h` AW_*_DRIVER_ENABLE** | **DTS + lra,info** | **lra_fw 文件名**。

| dmesg 关键字 | 优先查 |
|--------------|--------|
| 无 probe / 无 ko | §1 KO、宏控 |
| `parse gpio` / `rst\|int request failed` | §2 DTS+DWS、脚冲突 |
| `read chip id fail` / `unexpected chipid` / `ctrl_init failed` | 供电、I2C、DWS RST、BUILD/ENABLE |
| `unqualified chip` / `qualify check failed` | 料号、假焊 |
| `request IRQ` failed | irq-gpio、DWS INT |
| `failed to read haptic_ram.bin` / `check sum err` | §3 lra_fw |
| `probe completed` 无振 | ram_init、**fc-vib-effect**；仍无 → HAL/HE |

Probe 顺序（对照最早失败行）：`parse_dt_gpio` → GPIO req → `ctrl_init` → `check_qualify` → `parse_chipid` → `irq_config` → `ram_load`。  
CHIPID、宏、`ram_load` 细节见 [code-analysis.md](code-analysis.md)。

定制宏（合码看 diff）：`AAC_RICHTAP_SUPPORT`（`/dev/aw8697_haptic`）、`AW_DOUBLE`（`vibrator_l/r`）、`KERNEL_OVER_5_10`（`vibrator_single`）。

## 5. 验证与升级

| 步骤 | skill / 命令 |
|------|----------------|
| 驱动 probe | **fc-vib-driver** |
| 能振 | **fc-vib-effect** |
| HE | **fc-vib-he** |
| 权限 | **fc-vib-rootperm** / **fc-vib-selinux** |
| 日志定责应用层 | **vib-log-fault** |

## 输出模板

```markdown
**LRA 驱动适配** · vib-adapt-lra-driver

**结论**：[KO / DWS+DTS / 固件 / 驱动 / 上层]
**证据**：dmesg 摘录 / 与参考机 diff 要点

**已改**：
- ko_order_table：…
- DWS（三处）+ *_touch.dtsi：…
- lra_fw / 驱动：…

**验证**：[ ] fc-vib-driver  [ ] fc-vib-effect
```
