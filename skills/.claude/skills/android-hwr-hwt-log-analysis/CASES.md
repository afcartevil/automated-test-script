# HWR 典型案例

## 案例1: CPU1 喂狗中断导致 HWR

### 现象
设备运行中出现 HWT，随后升级为 HW reboot。

### 分析过程
1. `SYS_KERNEL_LOG` 检索 `wdt/wdtk`，发现 CPU1 后续喂狗缺失。
2. 向上追溯 CPU1 最后一次正常喂狗时间与关键错误日志。
3. 在同时间窗内发现 CPU1 相关 timeout/failed 线索。

### 结论
CPU1 长期阻塞导致喂狗链路中断，触发 HWT->HWR 升级复位。

## 案例2: systracker 地址定位到 UFS 链路

### 现象
复位后 `SYS_LAST_CPU_BUS` 出现 systracker 地址。

### 分析过程
1. 从 `lastpc/systracker` 提取可疑地址。
2. 结合 DTS/寄存器映射定位到 UFS 相关地址范围。
3. `SYS_KERNEL_LOG` 同时出现 UFS timeout 错误。

### 结论
总线/存储访问超时引发 CPU 长等待，最终导致 HWR。

## 案例3: 偏移计算后定位到业务函数

### 现象
仅有关键 PC 地址，无法直接得知业务模块。

### 分析过程
1. 从 `SYS_REBOOT_REASON` 提取 `oops_in_progress` 地址。
2. 与 `vmlinux` 同符号地址计算 kernel offset。
3. 关键 PC 减 offset 后 addr2line，命中业务函数。

### 结论
完成“地址 -> 函数 -> 模块”闭环，可转模块 owner 修复。
