# Bootup Issue 典型案例

## 案例1: 卡 Logo 后循环重启

### 现象
设备开机停留 Logo，约 20-40 秒后自动重启，稳定复现。

### 分析过程
1. 串口与 `kernel_log` 对齐时间线，判定失败阶段在 Kernel。
2. 在 `last_kmsg/pstore` 搜到 `watchdog` 与驱动 `probe timeout`。
3. 对应版本 `vmlinux` 映射异常地址，定位到目标驱动初始化链路。

### 结论
- 根因方向: 驱动初始化时序异常（高置信度）
- 动作: 驱动 owner 修复时序并做冷开机回归

## 案例2: 可进 Recovery 但系统不可进

### 现象
可进入 Recovery/Fastboot，正常系统启动失败并反复重启。

### 分析过程
1. 判定为 Recovery 分支问题，优先检查分区一致性。
2. `kernel_log` 命中 `dm-verity device corrupted`。
3. 执行分区回读后确认镜像与分区数据不一致。

### 结论
- 根因方向: 分区完整性异常（中-高置信度）
- 动作: 分区修复与镜像一致性重校验，补充 OTA/刷机链路排查
