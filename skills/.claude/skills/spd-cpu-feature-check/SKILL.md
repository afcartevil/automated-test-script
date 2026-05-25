---
name: spd-cpu-feature-check
description: 指导手机 SPD「CPU / 调度」维度功能检查：覆盖感知调度 3.0（属性、init.svc、enable、Aegean dumpsys 接口与清单人工项）、性能统计 perf log、CPU 调度健康标准、cgroup 分组策略；每项提供独立可执行脚本（adb 连机），输出 PASS/FAIL/BLOCKED 与证据片段。用户提到 SPD CPU、SPD 调度、transched、perf log、tran_health_sched、Aegean cgroup、感知调度 3.0、trans_sched、uias_test_api 检查时使用。
---

# SPD-CPU / 调度 Feature 功能检查

## 权威来源

下列四项的检查命令、期望结果与内核维测支持关系，以你提供的 SPD 维测表格截图为依据（`kernel-5.15` / `6.1` / `6.6` / `6.12` 均为表内「专项支持」）。若后续飞书表格与截图不一致，**以当前产线表格为准**，并同步更新本 Skill 中的脚本常量。

## 前置条件

- 已安装 `adb`，设备 USB 调试已开，`adb devices` 可见一台设备。
- 脚本使用 **Python 3**（与 `spd-memory-feature-check` 相同调用方式）。
- 部分节点（`dmesg`、部分 `sysfs`）在无 root 或 SELinux 限制下可能拿不到完整输出；脚本会将不可执行记为 **BLOCKED** 或 **FAIL** 并在输出中注明。

## 内核版本门控

四个脚本均会执行 `adb shell uname -r`，解析 `major.minor`，仅在集合 `{5.15, 6.1, 6.6, 6.12}` 内继续检查；否则 **BLOCKED**（与表格「专项支持」范围一致）。

## TOS / tos16 分支与版本截取

与 **tos16** 相关的分支（如 TOS16.3 dumpsys 路径、cgroup **tos16.1** 前后策略等），脚本需解析设备 **TOS 主次版本（major.minor）**。除环境变量 **`SPD_TOS_VERSION`** 与专用属性（`ro.transsion.tos.version`、`ro.vendor.transsion.tos.version`、`ro.build.tranos.version`、`ro.tranos.version`）外，**统一增加**从手机截取版本信息的方式：

- **命令**（在 PC 侧一条 adb，推荐）：  
  `adb shell sh -c 'getprop | grep version'`  
  或在已进入的 `adb shell` 内执行：`getprop | grep version`
- **截取**：在输出中查找含 **主次版本号** 的行（常见如 **`ro.build.display.id`**、**`ro.vendor.build.id`**、**`ro.build.version.incremental`** 等，具体以机型为准），读取形如 **`16.3`**、**`17.0`** 的片段，用于与 **tos16 / TOS16.3 / tos16.1** 等表格描述对照。
- **脚本实现**：`check_cpu_sched_health.py`、`check_cgroup_policy.py` 与内存 **`check_memory_allocate.py`** 共用 **`.cursor/skills/spd-shared/scripts/tos_detect.py`**，按「`SPD_TOS_VERSION` → 专用 TOS 属性 → `getprop | grep version` 解析」顺序得到 `(major, minor)`；解析逻辑与表格冲突时 **以飞书表格为准**。

## 一键执行四项

在项目根目录：

```bash
python .cursor/skills/spd-cpu-feature-check/scripts/run_all_spd_cpu_checks.py
```

依次运行下面四个脚本并打印分项退出码汇总（取最大码为进程退出码；汇总行为英文标识：`transched` / `perf_log` / `cpu_sched_health` / `cgroup_policy`，避免 Windows 控制台编码问题）。

## 独立脚本（每项一条命令）

在项目根目录执行（路径相对仓库）：

### 1. 感知调度 3.0

```bash
python .cursor/skills/spd-cpu-feature-check/scripts/check_transched.py
```

脚本自动覆盖维测清单 **「检查接口」** 三类项；**「检查功能」「检查稳定性」** 需 root / 双窗交互 / 多台样机，见下文「清单对照（人工）」。

**脚本自动判定（与清单图一致）**

| 清单小节 | 命令/等价行为 | 期望摘要 |
|----------|----------------|----------|
| 检查版本 | 对 `getprop` 全量解析后，按关键字 `transched` 或 `trans_sched` 过滤输出 | `init.svc.vendor.trans_sched` **或** `init.svc.vendor.trans_sched_aidl` 为 `running`（AIDL/HIDL 产线差异）；`ro.product.transched.support`、`ro.vendor.transched.support` 为 `1`；`ro.vendor.transched.version` 存在且为产线版本串（**不强制**为 `v2.0`，与图注「版本号不严格固定」一致，脚本校验 `v` 加数字点分形式）。 |
| 检查开关 | `cat /proc/trans_scheduler/enable` | 十六进制在允许集合内：清单图所列 **`0xff`、`0x1ff`、`0x2ff`、`0x3ff`、`0x7ff`**，并保留历史表内其它已支持掩码（`0x11`…`0x7f` 等）。 |
| 检查接口连通性 | `dumpsys activity aegean#uias_test_api`（设备侧 `sh -c` 包裹，避免 `#` 被 shell 注释） | 输出含 **SchedCapHIDL**、**isReady() completed**、**getTranSchedState() result:**、**setTranSchedState(255) result: true**、**dumpTranSchedUxInfo() result: true** 等核心行；清单中其余 API 行脚本作扩展项统计，缺失时 **不判 FAIL**。若回显为 **`no dumper for feature:aegean#uias_test_api`**（当前镜像未注册测试 dumper），脚本 **不记 FAIL**，仅提示换带该接口的镜像或设 `SPD_SKIP_TRANCHED_DUMPSYS=1`。 |

**环境变量（可选）**

- `SPD_SKIP_TRANCHED_DUMPSYS=1`：跳过 dumpsys 步骤（仅做属性 + `enable`），用于无 Aegean 测试接口的镜像或自动化流水线快速门控。

#### 清单对照：检查功能（人工 / 需 root）

以下为图中 **「检查功能」** 原文要点，脚本不替代长驻 `dmesg` / `trace_pipe` 与开应用操作，执行后把关键行写入巡检记录即可。

1. **环境**：root；按需打开内核调试（与当前 `enable` 掩码对应）  
   - 若 `enable` 为 `0xff`：`echo 1 > /proc/trans_scheduler/debug`  
   - 若为 `0x1ff`、`0x2ff`、`0x3ff`、`0x7ff`：`echo 63 > /proc/trans_scheduler/debug`  

2. **辅助功能（dmesg）**（示例均为一窗 `dmesg -w` 接管道过滤，另一窗操作）  
   - pick：`dmesg -w | grep trans_sched | grep -E pick`，打开应用（如设置），期望出现含 `pick_next_ux_for` 的日志。  
   - UX share(0)：`dmesg -w | grep trans_sched | grep -E 'ux share|0'`，开应用，期望 `ux share(0)`。  
   - UX share(1/2)：`dmesg -w | grep trans_sched | grep -E 'ux share|1|ux share|2'`，进出应用，期望 `ux share(1)`、`ux share(2)`。  
   - futex：`dmesg -w | grep trans_sched | grep futex`，开应用，期望 `dump_futex_list` 等。  

3. **target 功能**  
   - init/clear ux：`dmesg -w | grep trans_sched | grep -E 'init ux|clear ux'`，进出应用，期望 `set_ux_tags_by_pid` 相关 `init ux` / `clear ux`。  
   - SurfaceFlinger：`dmesg -w | grep trans_sched | grep dump_sf`，另一终端执行 `TransSchedTest 11` 或 `uaxtool 11`，期望 `dump_sf_targets` 为非零。  
   - App Binder：同上思路 `grep dump_ab`，期望 `dump_ab_targets` 非零。  

4. **内核 trace**  

```text
echo 1 > /sys/kernel/tracing/events/trans_sched/enable
echo 1 > /sys/kernel/tracing/tracing_on
```

   - `cat /sys/kernel/tracing/trace_pipe | grep find_available_cpu` → 期望 `find_available_cpu`。  
   - 同管道 grep `task_inlock_protect` → 期望 `task_inlock_protect`。  
   - grep `update_task_load` → 期望 `update_task_load`。  

5. **性能静态/动态识别**  
   - 打开重载应用（如 Unity 游戏）；一窗 `dmesg -w | grep trans_sched | grep dump_ux`，另一窗 `TransSchedTest 11` 或 `uaxtool 11`；期望 `dump_ux_record` 中出现如 `UnityGfxDeviceW` 等线程名，以及含 `ux_reckon_default` 的日志。  

#### 清单对照：检查稳定性（人工）

图中 **「检查稳定性」** 可见部分要求环境准备为 **6 台** 同型号样机；具体压测步骤以产线最新稳定性方案为准，本 Skill 仅保留清单中的环境约束说明，避免与未公开的内部用例冲突。

### 2. 性能统计 perf log

```bash
python .cursor/skills/spd-cpu-feature-check/scripts/check_perf_log.py
```

- 检查：`dmesg | grep '[K]'`（`[K]` 为 grep 字面匹配技巧）。
- 期望：存在类似 `[K] Usage PID Name Total:10000(ms) ...` 的日志行（脚本使用正则 + 宽松子串兜底）。

### 3. CPU 调度健康标准

```bash
python .cursor/skills/spd-cpu-feature-check/scripts/check_cpu_sched_health.py
```

- **维测表三项（须全部 PASS 脚本才退出 0）**：
  1. `getprop ro.product.transchedmetrics.support` 期望为 **`1`**。
  2. **TOS16.3 及以上**：`dumpsys tran_system_server_service_manager -service trancpufreqtime help`；**低于 16.3**：`dumpsys tran_service_manager trancpufreqtime help`。脚本按 **`SPD_TOS_VERSION` → 专用 TOS 属性 → `getprop | grep version`** 解析主次版本后**优先**走对应路径；解析不到则**依次尝试**两种 dumpsys。
  3. **sysfs**：维测要求可成功进入 **`/sys/kernel/tran_health_sched/`**；脚本用 **`cd /sys/kernel/tran_health_sched && pwd`** 校验，并 **`ls /sys/kernel/tran_health_sched`** 校验可访问。
- **dumpsys 期望内容（维测表）**：回显中须含 **`usage: trancpufreqtime`** 形态（不区分大小写）及子命令关键字 **process、kthread、cpu_loading、cpu、debug、clear、help**（`cpu` 为词边界，避免仅命中 `cpu_loading`）；若仅有异常栈而无上述 help 正文则该项 **FAIL**。

环境变量（可选）：`SPD_TOS_VERSION=16.3.1` 强制指定 TOS 版本字符串，用于 dumpsys 分支。

### 4. cgroup 分组策略

```bash
python .cursor/skills/spd-cpu-feature-check/scripts/check_cgroup_policy.py
```

- **tos16.1 以前**：`cat /vendor/etc/task_profiles.json` 需为合法 JSON，且包含表中所指新分组相关标记（脚本检测 `TRAN_SBG` / `TRAN_SBG_H_POLICY`）；并执行 `settaskprofile 1 TRAN_SBG_H_POLICY`，期望输出含 `Profile TRAN_SBG_H_POLICY is applied successfully!`。
- **tos16.1 及以后**：`getprop ro.tr_perf.aegean.cg.kernel.support` 期望为 `1`。
- TOS 主次版本从与第 3 项相同的来源解析（**`SPD_TOS_VERSION`、专用 TOS 属性、`getprop | grep version`**，见上文「TOS / tos16 分支与版本截取」）；读不到时先走「16.1+」属性路径，失败再尝试旧路径。

环境变量（可选）：`SPD_TOS_VERSION=16.0.0` 用于强制分支。

## 检查工作流（Agent / 人工）

1. 确认设备与 adb；记录机型、内部版本号、`uname -r`；**tos16 相关项**建议保存 `adb shell sh -c 'getprop | grep version'` 关键行以便对照表格。
2. 按上表顺序执行四个脚本，保存终端完整输出。
3. 每项结论：**PASS**（退出码 0）、**FAIL**（退出码 1）、**BLOCKED**（退出码 2，多为 adb/内核门控/权限）。
4. 汇总为简短报告：每项一行结论 + 关键证据（属性值、`init.svc.vendor.trans_sched`、`enable` 十六进制、dumpsys Aegean 片段、dmesg 匹配行、`trace_pipe` 片段、settaskprofile 回显等）。

## 与 SPD-内存 Skill 的关系

- `spd-memory-feature-check`：内存维度清单与脚本。
- `spd-cpu-feature-check`：CPU / 调度维度；二者可同一次 SPD 巡检并列执行，互不依赖。
