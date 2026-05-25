# Log Collection Reference

## 1. 目的

本文件用于统一海外售后问题分析时的日志抓取与取证要求，避免出现“现象描述很多、关键证据没有”的情况。

核心原则：

1. **先确定问题时间点，再抓日志。**
2. **优先保留全链路证据，不要只截一段局部日志。**
3. **每次复现都要记录操作步骤、现象视频、版本信息。**
4. **跨层问题至少同时拿 Android log + Modem / Network 侧日志。**

---

## 2. 通用最小取证集

无论是哪一类通信问题，建议至少补齐这些信息：

- 问题现象（具体到“不能拨号”“不识卡”“Baseband Unknown”“搜网列表异常”等）
- 问题时间点
- 机型、软件版本、baseband 版本
- 平台：MTK / SPRD / Qcom
- SIM 卡、运营商、卡槽
- DUT / REF 对比结果
- 复现步骤
- 视频或截图
- 对应日志包

---

## 3. 建议抓取的日志类型

## 3.1 Android 侧

优先抓取：

- `main_log`
- `radio_log`
- `system_log`
- `events_log`（怀疑 crash 时）
- `crash_log`（怀疑 crash 时）

资料中给出的通用 Android log 抓取命令：

```bash
adb logcat -b main -b radio -b system -v time > android_log.txt
```

## 3.2 Modem / 底层侧

按问题域补充：

- `modem log`
- `modem dump log`
- `_EE_INVALID` 目录
- `__exp_main.txt`
- `SYS_KERNEL_LOG`
- `taglog`（粉丝日志场景）
- `minidump`（大数据场景）
- `net log / OTA / 协议日志`（Call / IMS / 网络类）

---

## 4. 按问题域的抓取建议

## 4.1 Call / IMS 类

至少建议抓：

- `main_log`
- `radio_log`
- `system_log`
- `modem log`
- `net log / OTA / IMS 协议日志`

重点用于查看：

- Telecom / Telephony 上层流程
- `INVITE / PRACK / CANCEL / RELEASE / DISCONNECT`
- `DATA_CALL_REQ / DATA_CALL_CNF`
- `HTTP GET / PUT / 401 / 403 / 404`（补充业务 / XCAP）

## 4.2 Network / APN / 搜网类

至少建议抓：

- `radio_log`
- `main_log`
- `system_log`
- `modem log`
- `net log`

重点用于查看：

- `OPERATOR`
- `ServiceStateTracker / SST`
- `DATA_REGISTRATION_STATE`
- `NetworkScanHelper`
- `QUERY_AVAILABLE_NETWORKS_WITH_ACT`
- `ApnSetting / DataProfile`

## 4.3 SIM 类

至少建议抓：

- `android_log.txt`（main / radio / system）
- `modem log`
- AT / URC 相关日志

重点用于查看：

- `+ESIMS` / `+ECIND`
- `AT+CPIN?`
- `AT+EPINC` / `AT+XX`
- `UiccController`
- `ACTION_SIM_STATE_CHANGED`
- `SIMRecords`

## 4.4 Stability / Modem EE 类

必须确认日志包中有：

- `main_log`
- `modem dump log`
- `_EE_INVALID` 目录
- `__exp_main.txt`
- `SYS_KERNEL_LOG`
- `taglog` / `minidump`（如适用）

重点用于查看：

- `Modem exception`
- `[ASSERT]`
- `[Fatal error]`
- `ccci_mdinit`

---

## 5. 取证时的操作建议

## 5.1 复现前

1. 确认设备连接正常：`adb devices`
2. 明确复现步骤和时间点记录方式
3. 开启所需日志能力（如 modem log、telephony log）
4. 预留足够存储空间，避免日志被截断

## 5.2 复现中

1. 记录准确时间点
2. 保存现象视频或关键截图
3. 避免在复现过程中频繁切后台、重启设备，除非复现步骤要求
4. 若问题是偶发型，尽量从复现前一段时间开始连续抓日志

## 5.3 复现后

1. 第一时间导出日志，避免覆盖
2. 保留原始目录结构，特别是 dump / minidump / taglog
3. 对日志包做简要说明：问题时间点、机型、版本、平台、运营商、场景
4. 若是 EE 类问题，补记录 ASSERT 文件、行号、P1/P2/P3

---

## 6. 常见漏抓项

下面这些经常导致“无法继续分析”：

- 没有问题时间点
- 只有截图，没有视频或日志
- 只有 Android log，没有 modem / 协议日志
- 复现后重启了设备，导致关键日志丢失
- 没保留 `_EE_INVALID` / `__exp_main.txt` / `minidump`
- 没记录软件版本和 baseband 版本
- 没做 DUT / REF 对比

---

## 7. 输出建议

对外要求补日志时，建议明确写清：

1. 需要哪些日志文件
2. 问题时间点怎么记录
3. 是否需要视频 / 截图
4. 是否需要对比机结果
5. 是否需要保留原始 dump 目录

别只说一句“请抓 log”。那种说法工程价值基本等于没说。 
