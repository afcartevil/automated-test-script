# Bootup Issue 详细分析步骤

## 总流程

1. 数据收集与版本基线
2. 三步法快速判定
3. 分阶段深挖
4. 场景化专项检查
5. Jira 闭环输出

## 步骤1: 数据收集与基线

### 操作
1. 收集串口、`pl_lk`、`kernel_log*`、`main_log*`。
2. 补充 `SYS_LAST_KMSG`、`SYS_KERNEL_LOG`、`SYS_REBOOT_REASON`。
3. 场景化收集 `SYS_CUR_PLLK`、`__exp_main.txt`、`_分析报告.txt`。
4. 校验日志与 `vmlinux/ko` 是否同版本。

### 输出
- 日志齐套性清单（缺失项明确列出）
- 版本一致性结论

## 步骤2: 三步法快速判定

### 2.1 先判阶段
- 上电前期: 无振动/无背光/无 Logo
- LK(ABL): 有上电迹象但未进入系统阶段日志
- Kernel: 卡 Logo 或重启前停在内核路径
- init-Framework: zygote/system_server 前后失败
- Recovery 分支: 可进 Recovery/Fastboot 但系统不可进

### 2.2 再找失败点
- 取“第一条致命日志”优先。
- 若无明确致命日志，取“最后一个里程碑日志”作为边界。

### 2.3 最后收敛动作
- 归口到: 软件配置 / 驱动时序 / 分区一致性 / 硬件电路。

## 步骤3: 分阶段深挖

### A. 上电前期
- 重点: 电池电压、电流曲线、按键通路、PMIC `PON/POFF/PG`。
- 典型动作: 优先硬件电源链闭环，再看软件。

### B. LK(ABL) 阶段
- 重点: `boot/recovery/vbmeta/metadata` 一致性与签名链。
- 典型动作: 校验镜像和槽位，排除镜像不匹配。

### C. Kernel 阶段
- 重点: `last_kmsg/pstore` 中 `panic/watchdog/probe timeout/mount`。
- 典型动作: 锁首个异常线程或函数，必要时做符号映射。

### D. init-Framework 阶段
- 重点: `logcat` 首个 crash，`zygote/system_server` 启动链。
- 典型动作: 定位 first crash，区分服务拉起失败和配置错误。

### E. Recovery 可进分支
- 重点: A/B 槽位、动态分区、`dm-verity`、userdata 加密状态。
- 典型动作: 分区回读、镜像完整性校验、必要时清理数据验证。

## 步骤4: 场景化专项检查

1. 低电不开机  
   - 关键词: `check_low_battery`, `vbat`
   - 动作: 电池健康度 + 供电链路排查

2. 温度触发关机  
   - 关键词: `shutdown,thermal`
   - 动作: NTC/温感链路 + 温控策略核查

3. 文件系统挂载失败  
   - 关键词: `fs_mgr_mount_all returned unexpected error`
   - 动作: 分区健康与镜像一致性校验

4. dm-verity 损坏重启  
   - 关键词: `dm-verity device corrupted`
   - 动作: 分区回读，确认损坏来源

5. 按键异常误触发重启  
   - 关键词: `androidboot.bootreason=reboot_longkey`
   - 动作: 脱离按键复测，确认按键硬件链路

## 步骤5: Jira 闭环输出

最少包含:
1. 问题阶段 + 首个失败点
2. 关键证据（至少 2 条日志 + 1 个文件/截图）
3. 初步结论（高/中/低置信度）
4. 下一步动作（owner + 优先级 + 验证方式）

规则:
- 证据不足必须标注“待验证项”。
- 禁止仅凭单条日志写死根因。
