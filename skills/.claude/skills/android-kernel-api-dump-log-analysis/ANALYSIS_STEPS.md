# Kernel API Dump 详细分析步骤

## 总流程

1. 数据收集与版本基线
2. 读取 Plat_Parser_mpu（及 smpu）
3. 地址定位与归属确认
4. 根因分型与动作
5. MTK 协同边界判断
6. Jira 化输出

## 步骤1: 数据收集

### 操作

1. 收集 `_分析报告.txt`、`__exp_main.txt`、`SYS_KERNEL_LOG`。
2. 定位 KernelAPI DB 路径下的 `db.00.KernelAPI.dbg.DEC/Plat_Parser_mpu.txt`（路径以实际包为准）。
3. 支持 SMPU 的平台同时检查 `Plat_Parser_smpu.txt`。
4. 记录问题现象：崩溃时间、系统状态、操作步骤、复现情况。

### 输出

- 文件清单与是否齐全
- 平台与版本基线

## 步骤2: 快速判定与关键字段

### 操作

1. 打开 `Plat_Parser_mpu.txt`（或 `smpu`）。
2. 提取并记录：`emi_id`、`port_id`、`axi_id`、`region_id`、`domain_id`、`Read/Write violation`、`violation address`、`CRDISPATCH_KEY`。

### 结论句式（建议）

`<master模块> 对 <violation address> 发生 permission deny，该地址归属 region#<id>`

先明确 **master（发起访问方）**，再定位 **region owner（被保护内存归属）**。

## 步骤3: 地址定位与归属确认

### 操作

1. 在 `SYS_KERNEL_LOG` 中搜索 `violation address`（完整地址与前缀均可）。
2. 定位该地址落在哪段 `reserved` 内存区间及节点名（如 `drdi_memory`）。
3. 若当前 DB 缺少 LK/UART 映射：补同平台、同项目的 LK 或 UART 日志，确认区间由哪个模块申请。
4. 在代码树中按 reserved 名称检索申请与重映射路径（如 `ccci_plat_realloc_map_mem` 等平台实现）。

### 双向校验

- **master**: 访问逻辑、生命周期、地址是否越界。
- **region owner**: MPU 权限是否应允许该访问；若访问合法则需与 MTK 对齐权限策略。

## 步骤4: 常见根因分型与动作

| 分型 | 说明 | 动作 |
|---|---|---|
| 访问侧逻辑异常 | 错误地址、越界、生命周期错误 | 修正访问逻辑与边界保护 |
| 权限配置不匹配 | 访问合法但 region 未放行 | 模块 owner 与 MTK 对齐权限 |
| 地址归属识别不足 | 日志无法映射到模块 | 补 LK/UART 或升级 MTK 用内部表定模块 |

## 步骤5: MTK 协同边界

- 已拿到 `Plat_Parser_mpu/smpu` 且能定位 master（如通过 `CRDISPATCH_KEY`）：可先本地模块自检再提 MTK。
- 缺 parser、无法由地址映射 owner、或涉及芯片内部 region 对照表：直接升级 MTK 协助定模块归属。
- 提交 MTK 的 Jira 需附：`domain/region/axi/port/address`、核心日志片段、已完成的代码与日志排查结论，避免反复补料。

## 步骤6: Jira 输出检查

- **问题概述**（四要素）：master、违规地址与 R/W、目标 region 与疑似 owner、结论状态（已证实/待验证）。
- **关键证据**（三件套）：Parser 摘录 + `SYS_KERNEL_LOG` 地址归属 + 代码检索路径（函数/文件）。
- **建议行动项**：owner 自检、是否需 MTK 权限对齐、补充日志清单（LK/UART/完整 DB）。
