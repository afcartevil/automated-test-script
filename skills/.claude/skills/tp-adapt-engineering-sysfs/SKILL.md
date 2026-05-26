---
funcType: "AI自动化适配"
category: "驱动"
---
﻿---
name: tp-adapt-engineering-sysfs
description: >-
  Guides Transsion MTK touch driver porting and failure analysis when engineering
  mode cannot read TP firmware or vendor strings from sysfs
  (`tp_firmware_version`, `tp_vendor` under `mtk-tpd`). Use when merging or adapting
  `transsion` / `tran_touch` across branches, sysfs missing or empty/UNKNOWN, symlink
  points to wrong screen, reads race probe, or midtest TP info breaks after TP changes.
---

# Transsion TP 工程模式 sysfs（固件 / 模组信息）适配与调试

上层工程模式通过读取下列节点展示 TP 固件信息与模组厂商信息（措辞与路径按需求保留）：

- `sys/devices/platform/mtk-tpd/tp_vendor`
- `sys/devices/platform/mtk-tpd/tp_firmware_version`

等价于设备上通常为：

- `/sys/devices/platform/mtk-tpd/tp_vendor`
- `/sys/devices/platform/mtk-tpd/tp_firmware_version`

## 内核侧职责归属

1. **主屏 / 常用路径（`transsion` core）**  
   - 实现文件：`drivers/input/touchscreen/transsion/core/platform/mediatek/transsion_mtk_node.c`  
   - `mtk_node_create()`：`sysfs_create_group()` 把 `tp_firmware_version`、`tp_vendor` 挂在 **主平台设备** `pdata->pdev` 的 `kobj` 上；再 `sysfs_create_link(&platform_bus.kobj, &pdata->pdev->dev.kobj, "mtk-tpd")`，于是用户态看到 **`/sys/devices/platform/mtk-tpd/...`**。  
   - 内容由 `g_tran_ts.controller[TRAN_MAIN_CONTROLLER]` 提供（`supplier`、`cur_ic`、`vendor_name`、`ops->get_firmware_version` / `get_base_version` / `get_config_version`、可选 algo 相关回调）。

2. **折叠副屏分支**  
   - `transsion_mtk_sub_device.c` 中 `mtk_sub_node_create()` 同样创建 `mtk-tpd` **同名** link，但指向 `sub_pdev`；并可能多一个 `tp_name` 属性。  
   - 适配时核对 **谁先创建 symlink**、主副是否冲突；工程模式读的若是副屏链路，内容与 `TRAN_SUB_CONTROLLER` 一致。

3. **历史 / 双栈目录**  
   - 部分分支仍存在 `tran_touch/platform/mediatek/transsion_mtk_node.c`（逻辑与上文类似，可能有本地静态缓冲等差异）。Cherry-pick 时以 **当前分支实际编译进 ko 的那份 `.c`** 为准。

4. **与 input 名称的关系**  
   - `transsion_core.h` 中宏：`TPD_DEVICE`（如 `mtk-tpd2`）与 `TPD_SUB_DEVICE`（`mtk-tpd`）描述 **platform / 设备命名约定**； sysfs 工程的 **`mtk-tpd` 路径来自上述 `sysfs_create_link`，不要仅根据 input 节点名臆断。

## 分支适配检查清单（kernel）

Porting 或合入后按序自查：

- [ ] **编译链接**：对应 `Makefile` 是否包含 `transsion_mtk_node.o`（及副屏时的 `transsion_mtk_sub_device.o`），目标模块是否随项目 `ko_order` / `insmod` 顺序加载。  
- [ ] **probe 路径**：`transsion_mtk_platform.c`（或等价平台文件）是否在主屏初始化流程里调用 `mtk_node_create(pdata)`；折叠项目是否按设计调用 `mtk_sub_platform_init`。  
- [ ] **节点是否存在**：`ls /sys/devices/platform/mtk-tpd` 是否包含 `tp_vendor`、`tp_firmware_version`。  
- [ ] **主控已就绪**：`tp_firmware_version_show` 在 main 路径上若 `controller_init_state` 为假会 **返回长度 0**（读出来为空）；`tp_vendor` 无有效 `supplier` 等会落到 **`UNKNOWN`**。  
- [ ] **厂商格式**：Goodix 分支下固件字符串常为 `0xXX_0xXX,bv:0xXX_0xXX`；其它厂商多为 `0xXX,bv:0xXX`；带 algo 时在 **非 factory 且 `TRAN_NORMAL_MODE`** 下会附加 `Algo:` / `Func:` 行。  
- [ ] **折叠 symlink**：若主副都注册 `mtk-tpd` link，确认产品期望读主屏还是副屏，避免“工程模式显示与当前屏不一致”。

## 与上层/现象对照

| 现象 | 优先怀疑 |
|------|----------|
| 无 `mtk-tpd` 目录或属性 | 未调用 `mtk_node_create` / 对应 `.o` 未进模块 / **probe 完成前读节点** / probe 失败提前返回 |
| 属性存在但固件读为空或长度为 0 | 主通路里 `TRAN_MAIN_CONTROLLER` 未就绪：`!pController` 或 **`controller_init_state` 为假**（`tp_firmware_version_show` 会直接返回 0）；或 `ops->get_firmware_version` / `get_base_version` 未实现 |
| `tp_vendor` 为 UNKNOWN | **`supplier` 为空**、`cur_ic` 未填；控制器未 init；读到的是副屏 sysfs 但 **sub 控未起来** |
| 内容像“半套”或非预期 | **`g_tran_ts.boot_mode`** 非 `TRAN_NORMAL_MODE` 时不走 algo 拼接分支；Goodix / 非 Goodix 格式分支不一致；副屏走的是 `transsion_mtk_sub_device.c`，无主屏 algo 段 |
| 偶尔失败、复位后恢复 | App 早于 TP probe 去读；模块化 **late insmod**；上层只读一次无重试 |
| 合入新 IC 后格式不对 | 对照 `vendor_name`（如 goodix）分支与 `get_config_version` 是否实现 |

## 获取失败：分析与调试流程

对用户报告「工程模式拿不到固件 / 厂商」按下面顺序收口，每一步记下证据（命令输出或 log）再往下走。

### 1. 先分类失败形态

| 类型 | 典型表现 | 含义 |
|------|----------|------|
| A. 路径不存在 | `ls` / `cat` 报 No such file or directory | symlink / 属性未创建，或 sysfs 路径写错 |
| B. `cat tp_firmware_version` 无输出或上层显示空白 | sysfs 可读但 **show 返回 0**（主通路 init 未完成）常见 |
| C. `tp_vendor` 为 `UNKNOWN` | supplier 链或 IC 名未建好 |
| D. 有内容但与工单 / 实物不符 | symlink 指向 **副屏 pdev**（或最后被覆盖的 link），读的屏与界面不一致 |
| E. Permission denied | 少见；查 SELinux、`adb shell` 身份 |

### 2. 设备侧必做核对（ADB / shell）

```bash
ls -l /sys/devices/platform/mtk-tpd
readlink -f /sys/devices/platform/mtk-tpd
ls -ld /sys/devices/platform/mtk-tpd*
cat /sys/devices/platform/mtk-tpd/tp_vendor
wc -c /sys/devices/platform/mtk-tpd/tp_firmware_version
cat /sys/devices/platform/mtk-tpd/tp_firmware_version
lsmod | grep -i tran
dmesg | grep -i tran_touch | tail -n 80
```

**解读：** `readlink -f …/mtk-tpd` 落到哪个具体设备目录，用来判断是否读错主副屏。`wc -c tp_firmware_version` 为 **0** 时对主屏实现强烈暗示 **`controller_init_state` 尚未为真**。若存在 `tp_name`，对照 `MAIN:… SUB:…`。

### 3. 内核日志证据链

优先在 `kernel_log` / `dmesg` 检索：

1. **`main tp init failed do nothing`** → 主控未完成 init 仍去读固件节点。  
2. **sysfs 创建失败相关** → `sysfs_create_group` / `sysfs_create_link` 非零（同名 `mtk-tpd` link 已被占用等）。  
3. **`fw:0x`、`vendor_name:`** → 回调是否跑到、数值是否合理。  
4. vendor probe 阶段 **supplier `cur_ic` 赋值** 日志 → 直接关系 `UNKNOWN`。  
5. 折叠：副屏 notifier / resume 后主控 **`controller_init_state`**。

### 4. 代码侧快速对照（结论导向）

- **主屏** `transsion_mtk_node.c`：**`tp_firmware_version_show`** 在 `!pController || !controller_init_state` 时 **return 0**；有 `get_algo_version` 且 **`g_tran_ts.boot_mode == TRAN_NORMAL_MODE`** 才拼接 Algo。**`tp_vendor_show`** 强依赖 **`supplier` + `cur_ic`**（成功分支部分实现 **不带换行 `\n`**，若 APK 解析异常可比对原始字节）。  
- **副屏** `transsion_mtk_sub_device.c`：使用 **`TRAN_SUB_CONTROLLER`**，无主屏 algo 逻辑；别把主屏结论套用到折叠外屏 sysfs。

### 5. 结论输出最小模板

```markdown
- 失败类型：A/B/C/D/E（其一或组合）
- readlink：`…`
- tp_vendor / tp_firmware_version（含 wc -c）：…
- 相关 `[tran_touch]` log：…
- 根因归类：节点未注册 | init 时序 | supplier/ic | symlink 指向副屏 | boot_mode 分支 | 其它
```

## 日志与验证（速查）

- 关键字：`[tran_touch]`、`tran_touch-ERROR`、`tran_touch-INFO`、`main tp init failed`、`mtk_node_create`、`fw:0x`、`vendor_name:`、`supplier`。  
- 速验：`cat` / `wc -c`、`readlink -f`。  

## 与其它 Skill 的配合

- Probe 失败、中断、触摸全无、DTS 等：**`@tp-driver-debug-expert`**。  
- **本 Skill**：TP 大体可用前提下，专攻 **工程信息 sysfs 获取失败**：契约、 symlink、双控、`controller_init_state`、`supplier`、`boot_mode` 证据链。
