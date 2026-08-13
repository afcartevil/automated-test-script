# 典型案例

## 案例1：指纹无法录入

### 现象

在设置中添加指纹进行录入，按压指纹光斑处，光斑正常高亮，但是无指纹录入进度。

### 分析过程

按 [ANALYSIS_STEPS.md](ANALYSIS_STEPS.md) 步骤1、2 核对 kernel 与 main 日志；驱动与 HAL 均显示初始化成功，但 HAL 初始化阶段 `spmt` 为未校准状态。

### 根因

指纹未校准。

### 关键日志

```
Line  8384: 04-10 06:46:37.025664  1733  1733 I [TRAN_HAL][FingerprintCore]: [init] spmt 0
```

---

## 案例2：OTA 升级后设置中指纹丢失，需重新录入

### 现象

通过 OTA 升级后，升级前录入的指纹丢失，需重新录入指纹。

### 分析过程

对比升级前、升级后 kernel log 中 Trustonic TEE 加载指纹相关 TA 时的 `UUID=` 记录。

### 根因

升级前后指纹 TA 的 UUID 不一致。

### 关键日志

**升级前 kernel log**：

```
Line  8875: <5>[    6.136885][  T275] Trustonic TEE: 105(4)|LOADH ASLR 1101, UUID=05060000-0000-0000-0000-000000000000, code offset 0x000E0000, mclib offset 0x0f4d8000
```

**升级后 kernel log**：

```
Line 13627: <5>[   19.848676][  T276] Trustonic TEE: 105(4)|LOADH ASLR 1001, UUID=05063976-0000-0000-0000-000000000000, code offset 0x009B3000, mclib offset 0x0fe9e000
```
