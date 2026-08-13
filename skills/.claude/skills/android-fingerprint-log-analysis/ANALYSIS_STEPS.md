# 详细分析步骤

## 分析流程概览

1. 在 **kernel log** 中按 `tran_fp` 追踪驱动 probe 与硬件通路（DTS、GPIO、电源、复位、SPI、netlink、TEE chip_id）。
2. 在 **main log** 中按 `tran_hal` 与 `android.hardware.biometrics.fingerprint` 追踪 HAL 初始化、设备节点、chip_id、校准状态 `spmt`、TA 版本与服务注册。

## 步骤1：确认驱动初始化正常

### 目标

确认内核指纹驱动是否成功完成 probe，设备是否已被内核识别并注册。

### 操作

1. 打开 kernel log。
2. 搜索关键字：`tran_fp`。
3. 按时间顺序核对：`tran_fp_probe` 进入、`tran_fp_parse_dts_file`、pinctrl、中断、电源、复位高低电平、SPI 默认状态、netlink 创建、`tran_fp_probe success`。
4. 继续在同一日志中查找 TEE 侧与 chip_id / IC name 相关行（如 `tran_read_goodix_chipid`、`IC name`）。

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 出现 `tran_fp_probe success` 等完整成功链，且后续可见 TEE 侧 IC name / chip_id 成功 | 驱动已成功完成初始化；硬件通信正常倾向 | 进入步骤2 |
| 出现 `tran_fp_parse_dts_file failed` | 驱动初始化失败 | 优先排查 DTS、驱动加载、SPI 设备注册 |
| 出现 `parse dts success`，但未见 `tran_fp_probe success` | DTS 解析成功但 probe 未完整结束 | 继续检查后续报错点：GPIO、电源、复位、netlink 初始化等 |
| 出现 `IC name`（chip_id 获取成功语义） | SPI 通信正常，chip_id 获取成功 | 可与步骤2交叉验证 HAL 侧 `getVendorChipId success` |
| 出现 `TRAN_IOC_ENABLE_SPI_CLK` 但看不到 chip id | SPI 时钟已打开，芯片识别未完成 | 排查 reset 时序、SPI 参数等 |

### 补充说明

- SOP 原文在步骤1判断中列出 `TRAN_IOC_ENABLE_SPI_CLK` 与 chip id 的组合场景；若日志中存在该关键字但无后续 chip id，按上表「SPI 时钟打开但芯片识别未完成」处理。

## 步骤2：确认 HAL 初始化正常

### 目标

确认指纹 HAL 初始化是否成功，并成功打开内核设备节点，TA 是否加载成功。

### 操作

1. 打开 main log。
2. 搜索关键字：`tran_hal`、`android.hardware.biometrics.fingerprint`（可同时使用多条 grep，或一条包含两者的模式）。
3. 核对：`openHal` → `Success to open device` → `getVendorChipId success` → `spmt` → `TA_VERSION` 与 TRAN_CMD 类成功语义 → `Fingerprint() done!` 与 Binder/AIDL 注册。

### 判断条件

| 条件 | 结论 | 下一步 |
|------|------|--------|
| 出现 `openHal` | HAL 初始化已启动 | 继续核对设备节点与 chip_id |
| 出现 `Success to open device` | 设备节点成功打开；HAL 与 kernel 通路正常 | 继续核对 chip_id 与 TA |
| 出现 `getVendorChipId success` | SPI 通信正常，chip_id 获取成功（与步骤1可互证） | 继续核对校准与 TA |
| 出现 `spmt 1` | 指纹已校准 | 若用户仍无法录入，结合 COMMON_ISSUES 与其他字段排查 |
| 出现 `spmt 0` | 指纹未校准 | 对照 COMMON_ISSUES 中「指纹无法录入」项 |
| 出现 `TA_VERSION`，且 TRAN_CMD 命令执行成功 | TA 加载成功 | 继续核对服务注册完成 |
| 出现 `Fingerprint() done!` | HAL 初始化流程结束 | 结合现象给出结论或对照常见问题表 |

### 日志示例引用

正常与异常样例见 [KEYWORDS.md](KEYWORDS.md) 中「指纹驱动加载」「指纹 HAL 初始化」两节。
