---
name: android-fingerprint-log-analysis
description: "MTK-指纹: 分析指纹无法录入与OTA后指纹丢失，覆盖tran_fp驱动probe、tran_hal、TEE UUID、spmt校准 | tran_fp/tran_hal/biometrics/fingerprint/spmt/uuid/指纹/录入失败 | 当用户报告MTK设备指纹无法录入、OTA后指纹丢失时使用"
funcType: "AI故障分析"
category: "驱动"
---

# 指纹问题日志分析（MTK）

## 适用范围

- **问题类型**：指纹驱动与HAL链路异常、校准与TA UUID相关问题
- **适用场景**：
  - 指纹无法录入
  - OTA升级后指纹丢失
- **适用芯片平台**：MTK

## 前置条件

分析前需确认以下日志文件可用：

| 日志文件 | 必需性 | 用途 |
|----------|--------|------|
| kernel log | 必需 | 检查指纹驱动是否成功加载，电源、复位、中断、SPI是否正常，chip_id是否获取成功 |
| main log | 必需 | 检查指纹HAL初始化是否成功，指纹服务是否正常，TA是否加载成功 |

## 问题有效性确认

在开始分析前，先确认问题有效性：**能成功获取 chip_id 可排除硬件问题**（驱动与TEE侧日志中应能看到与 chip_id / IC name 相关的成功记录后再做软件侧结论）。

## 分析工作流

按顺序执行：

1. **确认驱动初始化正常**：在 kernel log 中搜索 `tran_fp`，依据 probe、DTS 解析、GPIO/电源/复位/SPI/netlink 与 `tran_fp_probe success`、TEE 侧 `tran_read_goodix_chipid` / IC name 等判断驱动与硬件通信状态。详见 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md) 步骤1。
2. **确认 HAL 初始化正常**：在 main log 中搜索 `tran_hal`、`android.hardware.biometrics.fingerprint`（可同时 grep 多关键字），核对 openHal、设备节点打开、`getVendorChipId success`、`spmt`、`TA_VERSION`、Binder 注册与 `Fingerprint() done!` 等。详见 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md) 步骤2。
3. **对照常见问题表**：将现象与日志特征与 [COMMON_ISSUES.md](COMMON_ISSUES.md) 对照，缩小根因范围。
4. **参考典型案例**：复杂或边界情况参阅 [CASES.md](CASES.md)。

## 关键字速查

完整关键字与逐条日志示例、字段解读见 [KEYWORDS.md](KEYWORDS.md)。

核心关键字（grep 参考）：`tran_fp|tran_hal||android.hardware.biometrics.fingerprint|spmt|uuid|tabin`

## 输出格式

按以下模板输出分析结论：

### 指纹问题 日志分析报告

#### 基本信息

- **分析时间**：[时间]
- **日志来源**：[文件列表]
- **问题描述**：[用户描述]
- **芯片平台**：MTK（如日志可佐证）

#### 分析过程

**步骤1：确认驱动初始化正常**

- 搜索目标：在 kernel log 中搜索 `tran_fp`
- 搜索结果：[找到/未找到，条数或摘要]
- 关键日志：

```
[关键行]
```

- 步骤结论：[本步结论]

**步骤2：确认 HAL 初始化正常**

- 搜索目标：在 main log 中搜索 `tran_hal`、`android.hardware.biometrics.fingerprint`
- 搜索结果：[找到/未找到，摘要]
- 关键日志：

```
[关键行]
```

- 步骤结论：[本步结论]

#### 分析结论

- **问题根因**：[根因描述]
- **证据摘要**：[支持结论的关键日志行]
- **置信度**：高 / 中 / 低（依据证据充分程度）
- **建议措施**：[后续处理建议]

#### 参考信息

- 常见问题对照：[COMMON_ISSUES.md](COMMON_ISSUES.md)
- 典型案例：[CASES.md](CASES.md)

## 扩展文档

SOP 原文档「七、扩展文档」为占位；若有正式链接，分析时可由用户提供后一并纳入证据与建议依据。

**SOP 来源**：[指纹问题分析SOP](https://transsioner.feishu.cn/wiki/XtlEwkn82i5Lwwkm80scTFfXnpf)（飞书 Wiki，已通过文档内容转换获取）
