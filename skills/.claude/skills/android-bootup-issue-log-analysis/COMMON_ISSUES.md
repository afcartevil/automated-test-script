# Bootup Issue 常见问题对照

| 序号 | 现象 | 关键日志特征 | 根因方向 | 建议动作 |
|---|---|---|---|---|
| 1 | 长按电源无反应 | 无有效启动里程碑，电源寄存器异常 | 供电/按键/PMIC 硬件链路 | 先硬件闭环，再软件复核 |
| 2 | 卡 Logo 或循环重启 | `Kernel panic` / `watchdog` / `probe timeout` | 内核驱动或时序异常 | 锁首个异常线程并映射函数 |
| 3 | 动画循环 | zygote 或 system_server 链路失败 | framework 服务拉起失败 | 定位 first crash 与依赖缺失 |
| 4 | 挂载失败不开机 | `fs_mgr_mount_all returned unexpected error` | 分区/文件系统异常 | 分区完整性与镜像一致性校验 |
| 5 | dm-verity 重启 | `dm-verity device corrupted` | 分区数据损坏或校验不一致 | 分区回读并核对来源 |
| 6 | 多次 longkey 重启 | `androidboot.bootreason=reboot_longkey` 多次出现 | 按键误触发或硬件故障 | 脱离按键复测并排查按键链路 |

## 快速原则

- 先判阶段，再定根因，不跨阶段硬推结论。
- 至少使用两类日志交叉验证（如串口 + kernel/main）。
- 证据不足时输出“待验证项”，不写死根因。
