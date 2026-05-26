---
name: android-sys-usb-config-gadget
description: "Android-USB-configfs: 分析sys.usb.config/configfs gadget/adbd/sys.usb.ffs.ready与UDC绑定链路 | configfs/gadget/adbd/ffs_ready/UDC/cdp_block/usb_ready | 当用户报告无UDC、ffs.ready未置位、soft-connect without gadget driver时使用"
funcType: "AI故障分析"
category: "驱动"
---

# Android sys.usb.config 与 Gadget/ADB 链路

## 作用

`sys.usb.config` 描述**当前要出的 USB 复合设备类型**（如 `adb`、`mtp,adb`、`none`）。**用户态不写 UDC 业务逻辑**：由 `init` 的 `.rc` 在属性变化时写 configfs、绑 UDC。  
`packages/modules/adb` 里 **adbd** 在需要 FunctionFS 时负责把描述符写入 `/dev/usb-ffs/adb/` 并 **`setprop sys.usb.ffs.ready 1`**，作为 init 绑 UDC 的前置条件。

## 关键文件（AOSP）

- 通用：`system/core/rootdir/init.usb.configfs.rc`（各产品可能由 vendor 复制/合并，如 `init.mt6858.usb.rc`）
- adbd：`packages/modules/adb/daemon/usb_ffs.cpp`（`open_functionfs()`）

## init 侧典型逻辑（configfs=1）

以 **仅 `adb`** 为例：

1. `sys.usb.config=adb` 且 `sys.usb.configfs=1` → **`start adbd`**
2. `sys.usb.ffs.ready=1` 且 `sys.usb.config=adb` 且 `sys.usb.configfs=1` → 写 configuration 字符串、**symlink `ffs.adb`** 到 config、**`write .../UDC ${sys.usb.controller}`**、`setprop sys.usb.state`

`sys.usb.config=none` 等 teardown 会 `stop adbd`、`sys.usb.ffs.ready=0`、写 UDC `none` 等（以实际 rc 为准）。

另有：`on property:init.svc.adbd=stopped` → `setprop sys.usb.ffs.ready 0`（adbd 退出时清 ready）。

## adbd 侧：`sys.usb.ffs.ready` 何时置 1

在 `usb_ffs.cpp` 的 `open_functionfs()` 中，在**首次**打开 control EP、成功写入 **USB descriptors** 与 **strings** 之后：

```text
SetProperty("sys.usb.ffs.ready", "1");
```

若写入 descriptors/strings 失败，不会置 `sys.usb.ffs.ready`，init 侧不会执行绑 UDC 的 trigger。

注意：若 `out_control` 已有效（分支 `if (out_control->get() < 0)` 不成立），会**跳过**整段含 `SetProperty` 的逻辑（重入/已打开场景需单独考虑）。

## 内核日志：read descriptors / read strings

内核 FunctionFS 在**用户态向 ep0 写入**描述符/字符串时，常打印 **`read descriptors`** / **`read strings`**。  
这表示 **FF 路径上有写入**，**不能**单独等价于「`sys.usb.ffs.ready` 已成功置 1」或「adbd 已正常跑完」——**必须以属性为准**：`getprop sys.usb.ffs.ready`、`sys.usb.state`、`init.svc.adbd`。

## 典型失败锚点

- **`udc ...: soft-connect without a gadget driver`**  
  UDC 被拉通/软连，但 **composite gadget 未就绪**（未 symlink/未绑 function、或 adbd 未把 ffs 准备好）。

- **`sys.usb.state` 长期 `none` 或 `sys.usb.config` 被置为 `none`**，而期望是 `adb`  
  对照 `persist.sys.usb.config` 与 Framework/UsbService 是否把 `sys.usb.config` 拉回。

- **`init.svc.adbd`** 为 `stopped` 且期望 USB adb  
  检查 adbd 是否被 `stop`、是否 crash、selinux、apex 挂载（`com.android.adbd`）等。

- **Framework 侧 `AdbDebuggingManager` / socket `No such file or directory`**  
  与 **local abstract socket** 未就绪有关，常与 **adbd 未正常提供 transport** 同时出现；需与 **ffs.ready / UDC** 交叉验证。

## 与 BC1.2 / cdp-block /「USB 出口」的关系

- **充电侧** `tc_chg_type_det.c` 中 `is_usb_rdy()` 与 **`cdp-block`** 门控：依赖 **gadget 侧 ready**（MTU3 等路径里清除 `cdp-block`）。  
- 若 **上层复合设备未绑 UDC**（`sys.usb.config` 链路未走完，或 `ffs.ready` 未置位导致 init 未写 UDC），**主机侧枚举/设备侧 gadget 就绪**可能不完整 → **`usb ready` 长期为 0** → **BC1.2 前置等待、`cdp-block` 相关日志** 与充电侧 skill 联动分析。

结论：**`sys.usb.config` 决定「出什么口」**；**`ffs.ready` + init rc** 决定 **device 模式是否真正绑定 UDC**；**充电 BC1.2** 依赖 **USB 侧就绪** 时，必须同时看 **本链路** 与 **`transsion-charger-orchestrator`** / **`mtu3-usb-device-core`**。

## 日志与属性排查清单

```text
- [ ] getprop sys.usb.config sys.usb.state sys.usb.configfs sys.usb.controller
- [ ] getprop sys.usb.ffs.ready init.svc.adbd persist.sys.usb.config
- [ ] kernel：soft-connect without a gadget driver / UDC 相关行
- [ ] init：processing action ... init.*.usb.rc（确认触发的是哪份 rc）
- [ ] 确认 vendor rc 是否与 AOSP init.usb.configfs.rc 语义一致（adb 是否依赖 ffs.ready）
```

## 转交

- 充电/BC12/cdp-block：`transsion-charger-orchestrator`
- MTU3/gadget pullup/cdp-block 清除：`mtu3-usb-device-core`
- PD/Type-C：`mediatek-pd-typec-protocol-6-12`

## 约束

- vendor `init.*.usb.rc` 可能与 AOSP 不完全一致，以**设备上实际执行的 rc** 为准。
- 本 skill 不替代 adbd 源码级调试，只固定**系统属性与 init 触发**关系。
