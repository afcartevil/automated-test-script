# Kernel API Dump 典型案例

## 案例1: Read violation + reserved 区间定位

### 现象

AP 读 `0x9006f380` 触发 permission deny，`CRDISPATCH_KEY` 指向 EMI MPU Violation。

### 分析过程

1. 读取 `Plat_Parser_mpu.txt`，记录 `region_id`、`domain_id`、Read violation 与地址。
2. 在 `SYS_KERNEL_LOG` 搜索该地址或前缀，找到 `reserved` 区间与节点名（如某 `drdi_memory` 段）。
3. 代码中检索 reserved 名称，定位到平台重映射实现（如 CCCI 相关路径）。
4. 判断 master 访问是否越界或生命周期错误；否则与 region owner 对齐权限。

### 结论要点

- 输出 master 与 region 归属证据链
- 明确是访问逻辑问题还是权限策略问题

## 案例2: 缺 LK 无法确认申请人

### 现象

DB 中 `SYS_KERNEL_LOG` 无完整 LK 映射，无法确认 reserved 由谁申请。

### 分析过程

1. 同平台同项目补抓 LK 或 UART，搜索 reserved 节点与 `emi_mpu_set_protection` 类日志。
2. 仍不足时，携带 Parser 全字段升级 MTK 定 owner。

### 结论要点

本地结论降级为“待验证”，列出已做检索与缺失项。
