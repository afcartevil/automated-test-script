---
name: tp-adapt-bringup
description: Drives Transsion/MTK touch-panel bring-up from reference selection through code/DTS/DWS/firmware/KO changes, probe/touch/sysfs validation, and failure routing. Use when TP 驱动 bring up、新机首次点亮触摸、port 参考机型、adaptive-ts 上电、移植 transsion touchscreen、或需要从零串起 DTS + 驱动 + 工模基础能力。
---

# Transsion/MTK TP Bring-up 主流程

本 skill 是 **TP 新项目 bring-up 的主编排**：目标不是罗列知识，而是把触控做到可交付的最小闭环：

```text
编译能过 → 模块能加载 → controller 能匹配 → input 能上报 → 工程/工模基础信息可读
```

每轮只推进一个阶段。若某阶段失败，只加载一个最匹配的子 skill，不要同时展开多个方向。

## 0. 先定任务边界

### 必要输入

缺信息时只追问最关键的一项。优先级如下：

1. 目标 `<project>` 和分支：如 tOS16 / u0.vnd / `kernel_device_modules-6.12` / `-6.1`
2. 参考项目：同 TP IC、同 I2C/SPI、同屏型优先
3. TP IC、模组厂、LCM 名、总线号、RST/INT GPIO
4. 产品范围：只要基础触摸，还是还包含手势、FOD、大面积、容值工模
5. 当前状态：未改代码 / 已编译失败 / 已刷机 probe fail / 有触摸但 sysfs 异常

若用户没有参考项目，先用本地树或 OpenGrok 找同 IC + 同分支参考；找不到时把“无可靠参考”列为阻塞风险。

### Done 定义

基础 bring-up 的最低 Done：

- `fc-tp-driver` Pass：驱动 probe 成功，input 设备注册
- `fc-tp-touch` Pass：`ABS_MT` 坐标可上报
- `fc-tp-sysfs` Pass：`tp_vendor`、`tp_firmware_version` 非空且非 `UNKNOWN`

产品要求工模/手势/FOD/大面积时，在基础 Done 后再进入对应专项 skill。

## 1. 建参考差异清单

先生成参考项目与目标项目的“同类文件清单”，再动代码。不要凭记忆只改 DTS。

| 类别 | 必查文件或目录 | 产物 |
|------|----------------|------|
| KO | `vendor/transsion/projects/<project>/ko_order_table.csv` | TP vendor `.ko` 与 `adaptive-ts.ko` 行 |
| DTS | `kernel_device_modules-*/arch/arm64/boot/dts/mediatek/tp/*touch*dtsi` | controller 节点、supplier、总线、GPIO、供电 |
| DWS | `vendor/mediatek/proprietary/**/<project>/**.dws` / `codegen.dws` | TP 全部相关 net（总线 SPI/I2C + RST/INT/电源 GPIO）三份一致性 |
| 固件 | `vendor/transsion/projects/<project>/tp_fw/` 或同等目录 | 固件文件名、拷贝目标、DTS fwname |
| 拷贝规则 | `device-vext.mk` / 项目 `*.mk` | `PRODUCT_COPY_FILES` 到 `odm/firmware/` |
| 驱动 | `drivers/input/touchscreen/transsion/core/` 与 `vendor/<ic>/` | `vendor_name`、`support_ic[]`、`tran_controller_ops` |

路径不确定时读取 `~/.cursor/kb/tp-vib-harness/references/tp-path-reference-20260520.md`；需要查远端源码时加载 `tool-opengrok`。

输出阶段产物：

```markdown
### 参考差异清单
- 分支/内核目录：
- 目标项目：
- 参考项目：
- TP IC / 总线：
- 待改文件：
- 参考机关键字段：KO / supplier / fwname / GPIO / firmware
```

## 2. 静态移植顺序

按下面顺序改。前一层不成立时，不要跳到后一层调 sysfs 或工模。

### 2.1 KO 与构建

目标：TP vendor `.ko` 和 `adaptive-ts.ko` 会被编译并在正常开机早期加载。

检查和修改：

- `ko_order_table.csv` 包含 vendor TP `.ko` 和 `adaptive-ts.ko`
- `KO path` 指向当前分支的 `kernel_device_modules-*`
- `Odm/Ramdisk`、`BootTime.completed`、`Recovery` 与参考项目一致，TP 通常投递 `odm`、早期加载、Recovery 不加载
- vendor 目录和 core 目录被 `BUILD.bazel` / `Makefile` 覆盖

失败路由：表项、路径、加载时机不清楚时，加载 `tp-adapt-ko-order`。

### 2.2 Touch DTS

目标：内核能实例化正确的 TP controller，且 Transsion core 能匹配当前 LCM/模组/IC。

必核字段：

- 板级 DTS 已 include 目标 `*_touch.dtsi`
- I2C/SPI 节点、`reg`、`cs-gpio` 与硬件一致
- `reset-gpio`、`irq-gpio`、`interrupt-parent` 与原理图一致
- `vdd-supply`、`vio-supply` 或 GPIO 电源脚与 LCM/TP 上电约束一致
- `supplier-num`、`supplier-<i>`、`supplier-vendor-<i>`、`supplier-vendor-fwname-<i>` 与 LCM 名、模组厂、固件文件名一致
- 折叠项目区分主副 controller，明确 `mtk-tpd` symlink 读哪个 platform device

失败路由：

- supplier / sysfs 字符串 / BV 对不上：`tp-adapt-factory-sysfs`
- `mtk-tpd` 链接或工程模式读取路径异常：`tp-adapt-engineering-sysfs`
- 供电顺序、亮灭屏上电异常：`tp-adapt-power-sequence`

### 2.3 DWS 与 GPIO

目标：DTS 中 TP 控制器用到的**全部引脚**（通信总线 + 控制/电源 GPIO）与三份 DWS 完全一致；不只核对 RST/INT/电源。

**从 DTS 先列完整引脚表**（对照 `*_touch.dtsi` 与 `pinctrl`）：

| 类别 | DTS 常见属性 / 节点 | DWS 需核对的 net（命名因项目而异） |
|------|---------------------|-----------------------------------|
| SPI | `spi@…` 子节点、`cs-gpio`、`pinctrl` | `CTP_SPI_CLK` / `SPI_CLK`、`MOSI`、`MISO`、`CS`（或 `TP_SPI_*`） |
| I2C | `i2c@…` 子节点、`reg`、`pinctrl` | `CTP_I2C_SCL` / `SCL`、`SDA`（或 `TP_I2C_*`） |
| 控制 | `reset-gpio` | `TP_RST` / `CTP_RST` |
| 中断 | `irq-gpio`、`interrupt-parent` | `TP_INT` / `CTP_EINT` |
| 电源/电轨控制 | `vtouch-supply`、`vdd-supply`、`avdd-supply`；vendor 常见 `*iovdd-gpio` / `*vddio-gpio` / `*vdd-gpio` / `*avdd-gpio` / `*enable-gpio` / `*power-gpio` | `TP_AVDD`、`TP_VDDI`、`TP_EN`、`TP_PWR` 等 |

规则：

- **总线脚**：MODE 须为 **SPI / I2C 复用**（与 DTS 挂接的 `spi*` / `i2c*` 控制器一致），**不得**被 UART/GPIO 等占用；SPI 的 **CS** 若 DTS 用 `cs-gpio` 单独控脚，DWS 须与 DTS GPIO 号、方向一致
- **SPI 与 I2C 二选一**：按硬件只核对实际总线那一组；port 参考机为 SPI 时，禁止只抄 RST/INT 而漏 SPI 四线
- **RST**：GPIO 输出，默认低或按复位极性，下拉
- **INT**：输入中断，上拉，EINT/GPIO 编号与 DTS 一致
- **AVDD/VDDI 与供电使能脚**：先按 DTS 实际属性核对（常见 `vtouch-supply` / `vdd-supply` / `avdd-supply` + vendor `*iovdd-gpio` / `*vddio-gpio` / `*enable-gpio` / `*power-gpio`）；GPIO 控电源常见为输出低 + 下拉，纯 PMIC LDO 供电则 DWS 不虚构对应 GPIO
- 同项目三处 DWS / `codegen.dws` 中 **上述全部 TP 相关 net** 逐项一致；用 `TP_` / `CTP_` / `TOUCH` / `SPI` / `I2C` 关键字搜全，避免第四条副本未同步

失败路由：加载 `tp-adapt-dws-pin`。改 DTS 后必须同步核对 DWS，不能只改一边。

### 2.4 固件与 ODM 拷贝

目标：驱动请求的固件、DTS `supplier-vendor-fwname-*`、打包进设备的文件名三者一致。

检查和修改：

- 固件源文件在 `vendor/transsion/projects/<project>/tp_fw/` 或项目等价目录
- `PRODUCT_COPY_FILES` 目标优先对齐参考项目，常见为 `odm/firmware/<file>`
- 机上刷机后可在 `/odm/firmware/` 或驱动实际请求目录看到该文件
- 多 supplier 时，每个 supplier 的 fwname 都能对应到真实文件

若 probe 成功但版本/BV 不对，优先回到 DTS fwname、拷贝规则、vendor `get_base_version` 三处核对。

### 2.5 Vendor 驱动匹配

目标：Transsion core 选中正确 controller，vendor 驱动完成 probe 并注册 input。

必核代码点：

- `vendor_name` 能被 DTS `supplier-<i>` 或匹配逻辑识别
- `support_ic[]` 包含目标 IC 字符串
- `tran_controller_ops` 至少挂接基础 probe、suspend/resume、`get_firmware_version`、`get_base_version`
- dmesg 无 `not support`、`match failed`、`controller_init_state false`

设备侧证据：

```bash
adb shell dmesg | grep -iE "tran_touch|adaptive|tpd|fts|goodix|nvt|chsc|ili|probe|match|not support" | tail -80
adb shell getevent -lp | grep -iE "touch|tp|mtk-tpd"
```

失败路由：

- controller 未匹配或 sysfs `UNKNOWN`：`tp-adapt-factory-sysfs`
- probe fail 且伴随 GPIO/IRQ/供电异常：先 `tp-adapt-dws-pin`，再按证据进入 `tp-adapt-power-sequence`
- 单纯 no-touch 日志分析：若是 JIRA/日志任务，切 `jira/tp-log-touch`

## 3. 上机验证顺序

不要等所有可选功能都移完才验证。每完成一层就跑对应最小检查。

1. 模块加载：`fc-tp-driver`
2. 输入上报：`fc-tp-touch`
3. 基础信息：`fc-tp-sysfs`
4. 工模信息页：`fc-tp-factory-info`
5. 权限/节点：`fc-tp-selinux`

判定原则：

- `fc-tp-driver` 不过，不继续看触摸事件和 sysfs 文案
- `fc-tp-touch` 不过，先区分 input 未注册、IRQ 不来、坐标不上报
- `fc-tp-sysfs` 为 `UNKNOWN`，优先查 supplier 匹配和 `controller_init_state`
- `Permission denied` 或节点 label 异常，进入 `tp-adapt-selinux`

## 4. 可选能力入口

基础 Done 后再做可选项：

| 能力 | 进入条件 | 子 skill / 检查 |
|------|----------|-----------------|
| 灭屏手势 | 触摸基础链路已通，需要 gesture proc 或 KEY 上报 | `tp-adapt-gesture-driver` → `fc-tp-gesture` |
| 工模容值 | `/proc/tp_panel_test` 缺失、无结果或工模容值项失败 | `tp-adapt-factory-capacitance` → `fc-tp-factory` |
| 工程/工模基础信息 | TP IC、vendor、FW、BV 显示错误 | `tp-adapt-factory-sysfs` / `tp-adapt-engineering-sysfs` |
| FOD / 大面积 | 日志或专项问题明确指向这些功能 | 对应 `jira/tp-log-fod` / `jira/tp-log-large-area` 方法定位后再改专项代码 |

## 5. 阻塞处理

遇到阻塞时先给出“当前层级 + 缺失证据 + 下一步单一 skill”，不要泛泛建议重查全部。

| 阻塞现象 | 优先判断 | 下一步 |
|----------|----------|--------|
| 编译不过 | KO 路径、BUILD/Makefile、vendor 目录是否存在 | 修静态构建；必要时 `tp-adapt-ko-order` |
| dmesg 无 TP 模块 | `ko_order_table.csv`、镜像投递、模块是否 resident | `tp-adapt-ko-order` |
| probe fail | I2C/SPI、RST/INT、供电、IC ID | `tp-adapt-dws-pin` 或 `tp-adapt-power-sequence` |
| input 有但无坐标 | IRQ、report path、坐标协议 | 先 `fc-tp-touch`，再按日志切专项 |
| sysfs UNKNOWN | supplier/LCM/vendor_name/cur_ic 未匹配 | `tp-adapt-factory-sysfs` |
| 工模节点权限失败 | SELinux label / owner / proc 权限 | `tp-adapt-selinux` + `fc-tp-selinux` |

## 6. 输出模板

```markdown
## TP Bring-up 状态

**项目/分支**：
**参考项目**：
**TP IC / 总线 / LCM**：
**当前阶段**：参考差异 / 静态移植 / probe / touch / sysfs / 可选功能 / Done

### 已确认
- KO：
- DTS：
- DWS：
- 固件：
- 驱动匹配：
- 上机验证：

### 关键证据
[dmesg / getevent / sysfs / 文件 diff 摘录]

### 当前阻塞
[若无则写“无”]

### 下一步
[只给一个阶段或一个子 skill，并列出要看的文件或要跑的 fc 检查]
```

## 7. 与 Harness 的关系

- 任务类型：`adaptation-debug`
- 主场景：TP 新项目 bring-up / 首次点亮 / port 参考机型 / adaptive-ts 上电
- 明确是功能验证时，不走本 skill，按 `func-check-registry.md` 直接加载一个 `fc-tp-*`
- 明确是 JIRA 日志分析时，不走本 skill，按 `jira/tp-log-*` 处理
- 完成后按 harness 规则沉淀案例到 `~/.cursor/kb/tp-vib-harness/cases/tp/`
