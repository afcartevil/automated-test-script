---
name: com-data-sim-contact-add
description: "SIM卡添加联系人异常分析: 覆盖SIM卡添加联系人全流程：MtkIccProvider插入请求、MtkIccPhoneBookIM更新USIM PB记录、MtkAdnRecordCache查找与更新ADN、MtkRecordLoader写入EF线性记录、MtkAdnRecord构建ADN字符串、EVENT_UPDATE_DONE结果确认等 | 联系人/SIM卡联系人/添加联系人/写入联系人/电话本/PhoneBook/ADN/IccProvider | 当用户报告与「SIM卡添加联系人异常分析」相关的日志分析需求时使用"
---

# SIM卡添加联系人异常分析

## 适用范围

本场景用于分析 SIM 电话本写入链路，覆盖从上层 Provider 插入请求，到 PhoneBookIM、ADN cache、RecordLoader、EF 写入和最终 `EVENT_UPDATE_DONE` 的完整过程。

典型问题包括：

- 添加 SIM 联系人失败或保存后消失。
- 仅某些姓名/号码失败，怀疑编码或长度问题。
- SIM 容量满、EF 写入失败、卡无响应。
- 双卡场景写入到错误 subId/slotId。

## 不适用场景

- SIM 未识别或卡状态异常：优先 `com-data-sim-recognition`。
- 联系人 App UI 展示异常但没有 SIM 写入请求：只能定位到 UI/Provider 入口或日志不足。
- Google/本机联系人数据库写入问题，不涉及 `icc/pbr` 或 SIM EF：不应按本场景归因。

## 前置条件

### 必需日志

- `bugreport*.txt`
- `radio-log*`
- `main_log*`
- `mainlogcat-log*`
- `sys_log*`
- `systemlogcat-log*`
- `0-android_main.log*`
- `0-android_system.log*`

## 分析步骤

```text
- [ ] 检查 Provider 插入请求
- [ ] 检查 PhoneBookIM 更新请求
- [ ] 检查 ADN cache 与 EF 写入
- [ ] 检查 ADN 字符串构建
- [ ] 检查 EVENT_UPDATE_DONE 结果
```

---

## 分析前最小证据集

优先确认：

- 保存联系人时间点、目标卡槽、subId。
- 联系人姓名、号码长度、是否含特殊字符或非 GSM 字符。
- SIM/USIM 类型、剩余容量、是否可读写。
- `main_log*`、`radio-log*`、`systemlogcat-log*` 是否覆盖写入时间。

若仅有 I 级日志，不能直接因缺少 `MtkRecordLoader` D 级细节判错；先建议 `adb shell setprop persist.log.tag D` 复测抓取，再基于已有 Provider/PhoneBookIM 证据分析。

---

## 快速命中判断

出现以下信号可认为进入 SIM 联系人写入链路：

- `MtkIccProvider.*insert.*icc/pbr`
- `MtkIccProvider.*updateUsimPBRecordsBySearchWithError`
- `MtkIccPhoneBookIM.*updateUsimPBRecordsBySearchWithError`
- `MtkAdnRecordCache.*updateAdnBySearch`
- `MtkRecordLoader.*updateEF`
- `MtkAdnRecord.*BuildAdnString`
- `MtkIccPhoneBookIM.*EVENT_UPDATE_DONE`

---

## 正常链路参考

正常 SIM 联系人写入链路应包含：

1. Contacts/Provider 发起插入请求，出现 `MtkIccProvider.insert` 或 `icc/pbr`。
2. Provider 获取目标 `subId` / `slotId`，进入 `updateUsimPBRecordsBySearchWithError`。
3. `MtkIccPhoneBookIM` 接收更新请求，调用 `MtkAdnRecordCache.updateAdnBySearch`。
4. `MtkRecordLoader` 获取 EF 线性记录大小并准备写入。
5. `MtkAdnRecord` 构建 ADN 字符串，处理姓名、号码和编码。
6. EF 写入完成，`EVENT_UPDATE_DONE` 返回 success。
7. Provider 返回插入成功，上层联系人列表刷新。

---

## 标准分析流程

### Step 1：检查 Provider 插入请求

- **目标**：确认添加联系人请求进入系统。
- **关键证据**：`MtkIccProvider.*insert.*icc/pbr`、`getRequestSubId`。
- **判断**：缺少入口日志时，不能归因 SIM 写入失败，优先检查 UI/Provider/时间窗口。

### Step 2：检查 PhoneBookIM 更新请求

- **目标**：确认 Provider 请求下发到 Telephony 电话本服务。
- **关键证据**：`MtkIccPhoneBookIM.*updateUsimPBRecordsBySearchWithError`。
- **判断**：Provider 有请求但 PhoneBookIM 无响应，偏 subId/slotId、跨进程调用或权限链路。

### Step 3：检查 ADN cache 与 EF 写入

- **目标**：确认已经进入 SIM EF 记录更新。
- **关键证据**：`MtkAdnRecordCache.*updateAdnBySearch`、`MtkRecordLoader.*updateEF`。
- **判断**：未进入 EF 写入时，不要直接判断 SIM 卡写失败，应先定位电话本缓存或请求参数。

### Step 4：检查 ADN 字符串构建

- **目标**：确认姓名/号码编码和长度是否可写入。
- **关键证据**：`MtkAdnRecord.*BuildAdnString`、`stringToGsm8BitPacked`。
- **判断**：构建失败常见于姓名过长、号码非法、编码不支持、字段超 EF 限制。

### Step 5：检查 EVENT_UPDATE_DONE 结果

- **目标**：确认最终写入成功或失败原因。
- **关键证据**：`EVENT_UPDATE_DONE`、`update done result`、success/error。
- **判断**：success 表示写入链路完成，若 UI 不显示转上层刷新/读取问题；failure 继续看容量满、卡无响应、EF 写入错误、权限或卡状态。

---

## 常见断点地图

| 断点 | 典型证据 | 建议归因方向 |
|---|---|---|
| Provider 入口缺失 | 无 `MtkIccProvider.*insert` | 应用入口、权限、时间窗口 |
| PhoneBookIM 未接收 | Provider 有请求但无 PhoneBookIM | subId/slotId 或跨进程调用异常 |
| EF 未写入 | 无 `updateEF` | ADN cache、请求参数、电话本服务异常 |
| ADN 构建失败 | `BuildAdnString` 异常 | 姓名/号码长度、编码、字符集 |
| 更新失败 | `EVENT_UPDATE_DONE` 非 success | SIM 容量、卡响应、EF 写入、卡状态 |

---

## 输出要求

- 先区分失败发生在 Provider、PhoneBookIM、ADN 构建、EF 写入还是 UI 刷新。
- 对“容量满/编码异常/卡无响应/EF 写入失败”必须给出对应日志证据。
- 缺少 `EVENT_UPDATE_DONE` 时，只能说明结果证据不足。
- 建议动作最多 3 条，优先包含复测抓 D 级日志、确认 subId/slotId、使用短姓名/纯数字号码对比。

---

## 证据约束

- 没有 Provider insert 证据，不能确认添加联系人请求进入系统。
- 没有 EF 写入日志，不能判断 SIM 卡写入失败。
- 没有 `EVENT_UPDATE_DONE`，不能确认成功或失败原因。
- 必须区分“应用未发起请求”和“Telephony/SIM 写入失败”。
