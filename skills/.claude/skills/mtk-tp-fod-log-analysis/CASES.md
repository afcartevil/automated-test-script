# 典型案例

## 案例1：指纹无法录入

### 现象

设置中无法录入指纹。

### 分析过程

1. 筛选 `kernel_log` 中 TP 与 FOD 相关关键字。
2. 检查是否存在 `tran_fingerprint_status` 写入。
3. 检查设置录入阶段是否存在 `fod finger down` / `fod finger up`。
4. 结合筛选结果判断是否收敛到 TP 侧。

### 根因

DTS 中未开启相关的 FOD 特性配置。

### 关键日志

```text
筛选整份日志，没有指纹录入与按下事件

//关键字类似这样
"fod finger down"   "fod finger up"
```
