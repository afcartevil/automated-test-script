---
name: tp-adapt-factory-sysfs
description: >-
  Debug Transsion/MTK touch factory (工模) TP IC string, module vendor label, firmware and BV
  strings exposed through kernel sysfs attributes (tp_vendor, tp_firmware_version; fold devices
  add tp_name). Use when factory UI shows wrong TP IC/vendor/version, BV mismatch, UNKNOWN strings,
  or when correlating DTS supplier entries with sysfs and vendor get_firmware_version /
  get_base_version hooks.
disable-model-invocation: true
---

# Transsion TP 工模信息（Sysfs）调试 Skill

Transsion 核心在 MTK 平台上通过 **platform device 的 sysfs 属性组**向上层（工厂测试 / 信息页）暴露 TP 模组名与固件信息。用户口语中的「sys 节点」在此处多为 **sysfs**（`/sys/bus/platform/devices/.../`），另有部分能力在 **`/proc`**（如自检），与 TP 基本信息展示未必相关。

---

## 1. 先读哪些 sysfs 节点

在设备上枚举并读取（单次机况可能有多处 platform 触摸设备路径）：

```bash
adb shell 'find /sys/bus/platform/devices -maxdepth 2 \( -name tp_vendor -o -name tp_firmware_version -o -name tp_name \) 2>/dev/null'
adb shell cat /sys/bus/platform/devices/*/tp_vendor 2>/dev/null
adb shell cat /sys/bus/platform/devices/*/tp_firmware_version 2>/dev/null
adb shell cat /sys/bus/platform/devices/*/tp_name 2>/dev/null
```

历史上存在 **`/sys/devices/platform/mtk-tpd`** 指向主或副触摸 platform 设备的 **symlink**；主次屏/折叠项目在 `transsion_mtk_platform` 与 `transsion_mtk_sub_device` 中都会创建名为 `mtk-tpd` 的链接，实际指向以当前代码执行顺序为准。若读到的信息与预期不符，应以 **`find`** 找到的 **真实 pdev 路径**为准，而不要只依赖 `mtk-tpd`。

### 节点语义（内核实现）

**`tp_vendor`（main：`transsion_mtk_node.c`；sub：`transsion_mtk_sub_device.c`）**

- 成功时格式：`supplier_vendor_CURIC_SUPNUM`（源代码为 `sprintf("%s_%s_%02d", supplier_vendor, ic_name_upper, supplier_num)`）。
- **`supplier_vendor`**：来自 DTS `supplier-vendor-<i>`（模组厂文案，例如 TM / BOE / TXD）。
- **`ic_name`**：`controller->cur_ic` 截取至多 16 字节并 **转成大写**（IC 代号字符串，非 PID 寄存器）。
- **`supplier_num`**：DTS 里 `supplier-<i>` 条目的序号 `i`。

若主控未初始化：**返回 `UNKNOWN`**（`controller_init_state == false` 或 controller 为空）。

**`tp_firmware_version`**

- 依赖 **`tran_controller_ops.get_firmware_version`**（片上运行 FW）与 **`get_base_version`**（文件系统/基底版本 BV，语义随 vendor）。
- Goodix：**还会用 `get_config_version`**；无 algo 时为  
  `0x<fw>_0x<cfg>,bv:0x<fw>_0x<cfg>`。
- 非 Goodix：通常为 `0x<fw>,bv:0x<bv>`。
- **注意**：在主屏实现中，若 **启动模式为 `TRAN_NORMAL_MODE` 且** `get_algo_version` **返回非空**，字符串会多出 **Algo/Func** 行；工厂模式（`TRAN_FACTORY_MODE`）等可走 **不带 Algo** 的分支，`tp_firmware_version` 与常温显示可能不一致，属既有逻辑而非必然故障。

折叠副屏侧的 `tp_firmware_version_show` **没有** algo 拼接分支（仅 bv/fw/config 格式化）。

**`tp_name`（仅折叠等场景 `transsion_mtk_sub_device`）**

- 返回 **MAIN/SUB** 两套 `supplier_vendor_IC_SUPNUM`，用于双触控器并存时一次性查看。

---

## 2. 与 DTS / 匹配的对应关系（根因最常出在这里）

核心在 `tran_parse_dt()`（`transsion_core.c`）解析：

- `supplier-num`
- `supplier-<i>`：字符串内需能匹配 **LCM 名称**、`any`、以及 **vendor 名**（`vendor_name` 必须在 `supplier_info` 中出现）
- `supplier-vendor-<i>`：对应 sysfs 里的 **模组厂前缀**

主控与 supplier、IC 字符串的绑定在 **`match_tp_controller()` / `check_support_ic()`**：LCM、`supplier_info`、驱动里填的 **`vendor_name` 与 `support_ic[]`** 须一致，否则 **`cur_ic`、`supplier` 错误或未匹配**， sysfs 即为 **UNKNOWN** 或 **错误模组名**。

---

## 3. Vendor 钩子在哪儿填（对照版本号对不对）

在各 vendor 的 `*_transsion.c`（或等价文件）里的 **`tran_controller_ops`**：

- **`get_firmware_version`**：多读 IC FW 寄存器或驱动内缓存的运行版本。
- **`get_base_version`**：常为 **镜像/BV**，与 DTS `supplier-vendor-fwname-*` 指向的打包资源一致性问题常体现为 **BV 与工模不符**。
- **`get_config_version`**：Goodix 等 config 分区相关。

若 sysfs 长度为 0 或永远是 `0x00`：多数是 **指针未赋值**（旧 port）、**初始化失败**，或工厂模式下 **未及时读 IC**。

---

## 4. Goodix 另类的 `TranssionCustom.c`（与核心 mtk 路径并存时需警惕）

部分方案在 **`TranssionCustom.c`** 中 **自建** `mediatek,touch` 的 platform 驱动（`mtk-tpd2`），单独注册 **`tp_vendor` / `tp_firmware_version` / `tp_final_firmware_version`**，其中 **`tp_vendor` 可走 LCM 名字查表**，与 **`transsion_mtk_node.c` 的动态 supplier 逻辑可能不一致**。

若工程同时存在两套路径：工厂 APK 读的 **究竟是哪颗 platform 设备的 sysfs**，要以 **属性注册 probe** 与 **实际链接名** 为准；对比 **`find` 结果** 与 **内核 `ts_info` / `TRAN_INFO` 日志**。

---

## 5. 建议的日志关键词（kernel log）

搜索（或请用户提供）：

- `[tran_touch` / `tran_touch-INFO` / `tran_touch-ERROR`
- `match supplier`、`vendor_name`、`supplier_info`、`controller_init_state`
- `fw:0x`、`bv:0x`（`tp_firmware_version_show` 内打印）
- Goodix：`ts_info`、`chip_info`、`config_id`

---

## 6. 输出给用户的分析结论模板

1. **实际读到的 sysfs 路径 + 三字段原文**（`tp_vendor` / `tp_firmware_version` / 如有 `tp_name`）。
2. **期望的 supplier / IC / 版本** 分别应对应 DTS 哪几条属性、当前 LCM 名字是什么（bootargs / `touch,lcm_name`）。
3. **判定**：初始化失败（UNKNOWN）、DTS 与 `vendor_name`/IC 列表不匹配、`get_*_version` 未实现或工厂模式分支差异、双 platform 节点冲突、或 Goodix 查表与核心动态逻辑不一致。
4. **建议修改面**：DTS `supplier-*` / `supplier-vendor-*`、对应 vendor `*_transsion.c` 的 ops、或统一工厂读节点到单一实现。

---

## 7. 代码锚点（仓库内）

- 主屏 sysfs：`drivers/input/touchscreen/transsion/core/platform/mediatek/transsion_mtk_node.c`
- 副屏 / 折叠 + `tp_name`：`.../transsion_mtk_sub_device.c`
- Supplier 解析与匹配：`drivers/input/touchscreen/transsion/core/transsion_core.c`（`tran_parse_dt`、`match_tp_controller`）
- 数据结构：`drivers/input/touchscreen/transsion/core/include/transsion_core.h`（`tran_controller_ops`、`supplier_list`、`TRAN_FACTORY_MODE`）
- Goodix 可选第二套节点：`drivers/input/touchscreen/transsion/vendor/goodix/gt9916_common/TranssionCustom.c`
