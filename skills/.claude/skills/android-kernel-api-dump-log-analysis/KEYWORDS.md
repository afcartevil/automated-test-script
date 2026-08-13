# Kernel API Dump 关键字速查

## 一级总检索串

```text
CRDISPATCH_KEY|EMI MPU|Kernel API|KernelAPI|violation address|Read violation|Write violation|emi_id|port_id|axi_id|region_id|domain_id|Plat_Parser_mpu|Plat_Parser_smpu|reserved|drdi_memory|permission deny
```

## 按步骤检索

### Parser 与分类

```text
Plat_Parser_mpu|Plat_Parser_smpu|CRDISPATCH_KEY:EMI MPU
```

### 地址与内存归属

```text
violation address|0x|reserved|memory|ccci|drdi_memory
```

### 报告与栈

```text
Detail Info|Backtrace|__exp_main|Kernel API Dump
```

## 字段说明（Parser 常见项）

| 字段 | 含义要点 |
|---|---|
| emi_id | EMI 实例标识 |
| port_id / axi_id | 访问端口与 AXI 标识 |
| region_id / domain_id | MPU region 与 domain，用于与内部表对照 |
| Read/Write violation | 读或写越权 |
| violation address | 触发拒绝的物理/逻辑地址（以日志为准） |
| CRDISPATCH_KEY | 工具/平台给出的 dispatch 关键字，常含 master 线索 |

## 示例与解读

### 1) EMI MPU + master 线索

```text
CRDISPATCH_KEY:EMI MPU Violation Issue/MT6893_M7_MFG_M1
```

解读: 将 `MFG_M1` 等关键字作为 master 侧优先自检与派单方向。

### 2) Read violation + 地址

```text
Read violation
violation address: 0x9006f380
```

解读: 在 `SYS_KERNEL_LOG` 中搜该地址或前缀，对齐 `reserved` 区间与节点名。

### 3) region 与 domain

```text
region_id: 10
domain_id: 0
```

解读: 与 MTK 内部 region 表对照时需作为必带参数提交。
