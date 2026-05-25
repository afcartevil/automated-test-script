---
name: tp-adapt-ko-order
description: Verifies Transsion project ko_order_table.csv entries for touch-panel (TP) modules when debugging shutdown paths where TP .ko must not be loaded or must match a fixed early-load pattern. Guides CSV row checks (odm/ramdisk, BootTime.completed, Recovery), paths under kernel_device_modules touchscreen/transsion, and on-device sanity checks. Use when adapting a new project, merging KO tables, or when JIRA/logs mention shutdown/reboot with TP driver, insmod/modprobe of focaltech/goodix/nvt/chsc adaptive-ts, or ko_order_table.
disable-model-invocation: true
---

# Transsion TP KO 表与关机路径核对

## KO 表位置

- **`ko_order_table.csv` 一般在 `vendor/transsion/projects/<project>/` 下**（与 `<project>` 同级的其它项目配置也可能在此目录）。
- 若当前仓库目录名为全小写，则实际路径多为 **`vendor/transsion/projects/<project>/ko_order_table.csv`**，以本树为准。

## 何时使用

- 适配/调试 **关机或复位** 相关问题时，需要确认 **TP 相关 `.ko` 的装载策略与表一致**。
- 正在改上述路径下的 **`ko_order_table.csv`**，或对比参考机型表项。

## 表结构（列名以仓库内 CSV 为准）

首行必须为以下列（顺序一致）：

| 列 | 含义 |
|----|------|
| `KO name (*.ko)` | 模块文件名，如 `focaltech_ft3683g.ko`、`adaptive-ts.ko` |
| `KO path` | 相对路径，通常指向 `../kernel_device_modules-*` 下构建产物 |
| `Odm/Ramdisk in Normal(vendor/ramdisk)` | 正常开机投递分区：`odm` 或 `ramdisk` |
| `Need loaded before BootTime.completed(Y/N)` | 是否需在 `BootTime.completed` 之前加载：`Y` / `N` |
| `Recovery(Y/N)` | Recovery 是否加载：`Y` / `N` |
| `Build mode` | 如 `user/userdebug/eng` |

## TP 相关行的识别

将下列视为 **TP 栈** 模块（需与 TP 驱动行一起核对，顺序与依赖以项目脚本为准）：

- 路径含 `drivers/input/touchscreen/transsion/vendor/…` 的厂商 TP `.ko`
- `adaptive-ts.ko`（路径往往在 `…/touchscreen/transsion/core/`）

## 参考配置（与以下示例一致地核对）

以下两行是 **正常机型表中 TP 与 core 的典型写法**；适配新项目时应对齐列含义与取值模式（具体 `.ko` 文件名与中间路径随 IC/项目变化）：

```csv
KO name (*.ko),KO path,Odm/Ramdisk in Normal(vendor/ramdisk),Need loaded before BootTime.completed(Y/N),Recovery(Y/N),Build mode
focaltech_ft3683g.ko,/../kernel_device_modules-6.1/drivers/input/touchscreen/transsion/vendor/focaltech/ft3683g_spi/focaltech_ft3683g.ko,odm,Y,N,user/userdebug/eng
adaptive-ts.ko,/../kernel_device_modules-6.1/drivers/input/touchscreen/transsion/core/adaptive-ts.ko,odm,Y,N,user/userdebug/eng
```

**核对要点：**

1. **`Odm/Ramdisk`**：TP 栈参考为 **`odm`**；勿在未确认启动架构的情况下把 TP 误放到 **`ramdisk`**，避免与关机/恢复路径期望不一致。
2. **`Need loaded before BootTime.completed`**：参考为 **`Y`**（与「开机尽早可用」策略一致）。若业务要求 **关机阶段不应再触发装载**，问题通常在上层触发 `insmod`/服务拉起或表被重复注入，需在 **运行日志** 中区分「早已加载」与「关机时才加载」。
3. **`Recovery`**：参考为 **`N`**；TP 一般 **不进 Recovery 装载列表**，与充电/Type-C 等常显 `Y` 的项区分。
4. **`KO path`**：须与当前工程的 **`kernel_device_modules-*` 目录版本**（如 `6.1`）及 vendor 子路径一致；合并分支后重点 diff。

## 静态检查清单

- [ ] 项目中是否存在 **重复的 TP `.ko` 名** 或 **遗漏 `adaptive-ts.ko`**（若平台使用 adaptive 栈）
- [ ] TP 行的 **`Recovery`** 是否为预期（多为 `N`）
- [ ] TP 行是否误用 **`ramdisk`**
- [ ] **列数与逗号**：无多余/缺失列，路径中逗号应已避免

## 运行期辅助（关机/重启调试）

按实际问题选用（需可抓串口的阶段才可看全）：

- **内核日志**：关机或复位前后是否出现 **首次** `insmod` / `init_module` / 驱动 probe 与 TP `.ko` 名称；若为关机瞬间才出现，怀疑用户空间或 late init 脚本补装模块。
- **`/proc/modules` 或 `lsmod`**：在仍可调 adb 的时机看 TP 相关模块是否已 resident；与「关机时才加载」报辞对照。

## 输出结论建议格式

```markdown
## ko_order_table 核对结论

- 项目/路径：`vendor/transsion/projects/<project>/ko_order_table.csv`
- TP 相关行：[列出 KO name + Odm/Ramdisk + BootTime + Recovery]
- 与参考模式一致性：[一致 / 差异说明]
- 若异常：[更可能根因：表项 / 装载脚本 / 关机时序 / 其他]
```
