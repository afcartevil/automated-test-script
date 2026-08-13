---
name: near-bt-opp-transfer
description: "蓝牙OPP文件传输异常分析: 蓝牙通过OPP协议发送或接收文件过程中出现的异常分析，包括SDP查询、OBEX会话、传输链路、文件路径解析等 | 蓝牙传输/蓝牙发送/蓝牙接收/文件传输/蓝牙分享/bluetooth transfer/OPP/OBEX | 当用户报告与「蓝牙OPP文件传输异常分析」相关的日志分析需求时使用"
funcType: "AI故障分析"
category: "通信"
---

# 蓝牙OPP文件传输异常分析

## 适用范围

本场景用于分析蓝牙 OPP 文件发送和接收链路，覆盖文件/设备选择、URI 解析、任务入库、SDP 查询、transport 建链、OBEX 会话、文件读写和完成通知。

典型问题包括：

- 分享文件到蓝牙后传输失败。
- 接收文件确认后失败。
- 对端设备不支持或 SDP 查询超时。
- socket connect exception、OBEX session error。
- 文件路径、MIME、provider 权限导致无法读写。

## 不适用场景

- 蓝牙主开关异常：优先 `near-bt-switch`。
- 设备未配对或连接失败：优先 `near-bt-device-connect`。
- 仅文件管理器/分享入口异常且无 OPP 日志：应先定位应用/Provider。

## 前置条件

### 必需日志

- `bugreport*.txt`
- `mainlogcat-log*`
- `main_log*`
- `sys_log*`
- `systemlogcat-log*`
- `0-android_main.log*`
- `0-android_system.log*`

## 分析步骤

```text
- [ ] 检查设备和文件选择
- [ ] 检查 batch 创建和任务入库
- [ ] 检查 SDP 查询
- [ ] 检查 transport 建链
- [ ] 检查 OBEX 会话和文件收发
- [ ] 检查完成通知
```

---

## 分析前最小证据集

优先确认：

- 发送还是接收，文件名、大小、MIME 类型。
- 目标设备名称/MAC，是否已配对/已连接。
- 用户是否确认接收。
- 发生时间点，传输失败前后 1-2 分钟日志。
- `mainlogcat-log*`、`systemlogcat-log*` 覆盖 OPP 服务日志。

若当前日志只有 I 级及以上，不能因缺少 D 级 OBEX/SDP 细节直接判错；先建议 `adb shell setprop persist.log.tag D` 复测，再基于现有 I/W/E 证据分析。

---

## 快速命中判断

出现以下信号可认为命中 OPP 传输链路：

- `BluetoothOppReceiver.*DEVICE_SELECTED`
- `BluetoothOppUtility.*getFilePathFromUri`
- `BtOppBatch.*New Batch created`
- `BtOppService.*Service start transfer`
- `SdpManager.*Starting search for UUID`
- `BtOppTransfer.*TRANSPORT_CONNECTED`
- `BtOppObexClient.*Start!`
- `BtOppObexClient.*SendFile finished`
- `BtOppObexServer.*Receiving file completed`

---

## 正常链路参考

正常 OPP 发送/接收链路应包含：

1. 用户选择目标设备和文件，`BluetoothOppReceiver` 收到 device selected intent。
2. 文件 URI 被解析，`BluetoothOppUtility.getFilePathFromUri` 获取有效路径和类型。
3. OPP batch 创建，`BtOppService` 开始传输任务。
4. SDP 查询目标设备 OPP 服务。
5. RFCOMM/L2CAP transport 建立，出现 `TRANSPORT_CONNECTED`。
6. OBEX client/server session 创建并连接成功。
7. 文件发送或接收完成，出现 `SendFile finished` 或 `Receiving file completed`。
8. 完成后状态广播/通知更新。

---

## 标准分析流程

### Step 1：检查设备和文件选择

- **目标**：确认用户选择了目标设备和有效文件。
- **关键证据**：`DEVICE_SELECTED`、`getFilePathFromUri`。
- **判断**：缺少 URI/路径证据时，不能直接归因蓝牙传输链路，优先检查文件权限或分享入口。

### Step 2：检查 batch 创建和任务入库

- **目标**：确认传输任务进入 OPP 服务。
- **关键证据**：`BtOppBatch.*New Batch created`、`BtOppService.*Service start transfer`。
- **判断**：入口存在但无 batch，偏数据库、任务队列或 OPP service。

### Step 3：检查 SDP 查询

- **目标**：确认对端 OPP 服务可发现。
- **关键证据**：`SdpManager.*Starting search for UUID`、`Search timed out`。
- **判断**：SDP 超时或 native 未初始化，偏对端服务、蓝牙栈初始化或 SDP 查询链路。

### Step 4：检查 transport 建链

- **目标**：确认 RFCOMM/L2CAP 连接建立。
- **关键证据**：`TRANSPORT_CONNECTED`、`socket create/connect exception`。
- **判断**：socket 异常偏 transport、远端拒绝、链路断开或蓝牙连接状态。

### Step 5：检查 OBEX 会话和文件收发

- **目标**：确认 OBEX session 创建、连接、put/get 和文件读写是否完成。
- **关键证据**：`BtOppObexClient.*Start!`、`OBEX session connect error`、`SendFile finished`、`Receiving file completed`。
- **判断**：OBEX 错误偏协议会话；openInput/openOutput 错误偏文件权限、路径、存储或 MIME。

### Step 6：检查完成通知

- **目标**：确认传输完成后状态通知和数据库状态更新。
- **关键证据**：`BluetoothOpp.*sendIntentIfCompleted`。
- **判断**：传输完成但 UI 未更新，偏完成通知或数据库状态同步。

---

## 常见断点地图

| 断点 | 典型证据 | 建议归因方向 |
|---|---|---|
| 文件/设备选择缺失 | 无 device selected / getFilePath | 分享入口、文件 URI、权限 |
| SDP 失败 | `Search timed out` / `Native not initialized` | 对端 OPP 服务、SDP、蓝牙栈初始化 |
| transport 失败 | socket create/connect exception | RFCOMM/L2CAP 链路或远端拒绝 |
| OBEX 失败 | `OBEX session create/connect error` | OBEX 协议会话问题 |
| 文件读写失败 | openInput/openOutput error | 文件权限、路径、存储、MIME 类型 |
| 完成通知缺失 | 无 `sendIntentIfCompleted` | OPP 数据库/通知/UI 更新 |

---

## 输出要求

- 先区分发送端 client 问题还是接收端 server 问题。
- 不要在缺少 URI/路径证据时直接归因蓝牙协议栈。
- 每个原因必须关联阶段：URI、batch、SDP、transport、OBEX、文件读写、完成通知。
- 建议动作最多 3 条，优先包含复测 D 级日志、换小文件/纯英文文件名、确认对端支持 OPP。

---

## 证据约束

- 没有文件 URI/路径解析证据时，不能把问题归因到蓝牙传输链路。
- 没有 SDP/transport 证据时，不能确认已经进入 OPP 协议建链。
- 发送失败和接收失败要区分 client/server 侧日志。
- 正常案例只用于对比链路完整性，不是当前问题事实。
