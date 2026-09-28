# BAT 移植高通平台计划（基于实测侦察）

目标：让 Bitflip Analysis Tool v5.5.3 在高通项目上跑起来。
调测设备（已实测）：Infinix X6878，高通 volcano 平台，Android 16，userdebug 已 root，
8 核 CPU，内存 7534MB。

## 0. 可行性结论

**可以复用 jar 编排框架，需要重写全部"条件脚本"，并接受部分定位能力降级。**

| 组件 | 高通可用性 | 依据（已核实） |
|---|---|---|
| jar 平台识别 | ✅ 可用 | jar 读 `ro.board.platform` 并大写为目录名（`mt6878`→`MT6878\`）；本机为 `volcano` → 新建 **`VOLCANO\`** 目录即可自动匹配，`-mt volcano` 可强制 |
| memtester64 / stressapptest64 | ✅ 直接可用 | 开源 ARM64 通用程序，判定串（`Status: PASS/FAIL`）与平台无关 |
| mtk_mem_test | ⚠️ 可用但降级 | 核心 pattern 写读比对通用；`draminfo`/`Bitflip DQ` 物理定位依赖 MTK EMI 节点（`emicen_addr2dram`），高通上报错退出该功能 |
| mem_corruption_check | ⚠️ 可用但降级 | 支持 dmabuf heap（本机 `/dev/dma_heap/system` 存在）且**有 malloc 回退**；物理地址映射同样依赖 MTK EMI |
| `TestCase\setup.bat` | ✅ 基本可用 | `dconfig` 缺失已被脚本容错（走 "unknown" 分支）；两个 APK 为通用 Android 应用 |
| `TestCase\each_boot_setup.bat` | ❌ 需改造 | `insmod cpu_hwtest.ko`、`/sys/class/usb_boost/` 为 MTK 专属，高通上必失败 |
| Suspend-Stress | ❌ 需改造 | `usb_off.sh` 依赖 `vendor.mediatek.suspend_stress` 属性和 MTK 节点 |
| APU-Stress / CPU-Idle | — 默认已关 | TestCaseConfig 中 CanUse=0，保持关闭 |
| 条件脚本（`MT####\*.bat/.sh`） | ❌ 全部重写 | 全部基于 MTK 节点（`/proc/cpuhvfs/*`、`helio-dvfsrc`、`spm_resource_req`…），需换成高通 cpufreq/kgsl/cpuidle 节点 |
| last_kmsg 抓取 | ⚠️ 路径不同 | 高通无 `/proc/last_kmsg`，但有 `/sys/fs/pstore/console-ramoops-0` |
| mrdump / dram_para / dram K | ❌ 不可用 | MTK 专属；用 `-a false -k false` 绕开，高通侧改用 pstore/ramdump 分析 |

## 1. 分阶段计划（预计 3~4 天）

### Phase 1：MVP 最小闭环 —— 验证 jar 编排能跑通（0.5 天）

目的：先不求功能完整，只验证"识别平台 → setup → 跑一个用例 → 出结果表"全链路不硬失败。

1. 新建 `VOLCANO\` 目录，做最小 `ConditionConfig.xlsx`：
   - 第一个工作表只留一行条件（如 `CPU-DVFS | 1`），其余删除；
   - 对应子表只留一行：`Default | dummy_setting.bat`；
   - 从 `MT6878\` 复制 `dummy_setting.bat` 过来。
2. 复制 `TestCase\TestCaseConfig.xlsx` 为 `TestCase\TestCaseConfig_qcom.xlsx`，只留
   Google-Stressapptest 的 CanUse=1，其余全部 0。
3. 运行（显式关闭 MTK 专属路径）：
   ```bat
   java -jar BitflipAnalysisTool.jar -mt volcano -tf TestCaseConfig_qcom.xlsx -r 1 -a false -k false -o true -i 30
   ```
4. 检查 `BST_Log.txt`：
   - 是否打印 `Force select platform: volcano` 且读到 `VOLCANO\ConditionConfig.xlsx`；
   - setup/each_boot_setup 中的 MTK 命令失败是否仅打印错误而不中断（参照 MTK 机上
     `DMLR: Error: ...` 也继续的先例，大概率容错）；
   - stressapptest 是否执行并打出 `Status: PASS`；
   - 是否生成 `--BST.xlsx` 且 Result=1。
5. **卡点预案**：若日志出现 `Can not get the device platform` 之类硬失败且 `-mt` 无法绕过，
   转入 Plan B（见第 3 节）。

### Phase 2：内存用例逐个手动验证（0.5 天）

在高通机上逐一手动跑，核对输出与 TestCaseConfig 的 PASS/FAIL pattern 匹配：

```bat
adb push TestCase\stressapptest64 /data/local/tmp/stressapptest
adb shell chmod 755 /data/local/tmp/stressapptest
adb shell /data/local/tmp/stressapptest -s 60 -M 2048 -m 8
adb push TestCase\memtester64 /data/local/tmp/memtester & adb shell /data/local/tmp/memtester 256m
adb push TestCase\mtk_mem_test /data/local/tmp/ & adb shell /data/local/tmp/mtk_mem_test -s 30 -l 0 -m 512 -t 8 -i 0
adb push TestCase\mem_corruption_check /data/local/tmp/ & adb shell /data/local/tmp/mem_corruption_check -s 30 -l 0 -m 512 -t 8 -i 8000 -r 50 -p
```

确认项：
- 各二进制在高通 arm64 上能执行、能打出各自的 PASS 串（`Status: PASS`、`All Test OK.`、
  `test pass, bye bye`、`all mem_corruption_check test OK.`）；
- mtk_mem_test / mem_corruption_check 打印 `physical_to_dram Error` 后**继续跑**而非退出
  （若退出，则这两个用例 CanUse 置 0，只保留开源用例）；
- mem_corruption_check 的 dmabuf heap 名称参数是否需要从默认改为 `system`；
- 全部可用后，把 TestCaseConfig_qcom.xlsx 中对应用例逐个打开。

### Phase 3：高通条件脚本重写（核心工作，1~2 天）

在 `VOLCANO\` 下按 ConditionConfig 逐个实现（节点路径已在本机实测存在）：

| 条件/脚本 | 高通实现 |
|---|---|
| CPU 满频（对应 Fix_OPP0） | `policy0/4/7`：`echo performance > scaling_governor`，`scaling_min_freq` = 各 policy 最高档（policy0 实测最高 1804800） |
| CPU 最低频（对应 Fix_OPP15） | `scaling_min_freq` = `scaling_max_freq` = 最低档（policy0 实测 441600） |
| CPU DVFS 恢复/Auto | governor 恢复 `schedutil`（先 `cat scaling_available_governors` 确认），min/max 恢复默认 |
| CPU DVFS 高低扫（Stress） | 循环交替写 min/max 为最高/最低档，模拟 MTK 的 hilo_test |
| CPU 热插拔 / Fix ALL ON | `echo 0/1 > /sys/devices/system/cpu/cpuN/online`（cpu1~cpu7 已实测有 online 节点） |
| GPU DVFS | `/sys/class/kgsl/kgsl-3d0/devfreq/{min,max}_freq`，档位 264000000~1150000000 共 10 档 |
| 低功耗开关 | `echo 1 > /sys/devices/system/cpu/cpuX/cpuidle/stateY/disable`（state0~2） |
| Suspend-Stress | 重写 `usb_off.sh`：去掉 mediatek 属性，用 `echo mem > /sys/power/state`（本机支持 freeze/mem/disk）+ rtcwake 定时唤醒 |
| VCORE-FS / MMDVFS / APU | 高通无直接等价物，ConditionConfig 中 `Can Use = 0` 关闭（二期可映射 bus/devfreq） |

同步更新 `VOLCANO\ConditionConfig.xlsx`：只保留已实现的条件并指向新脚本；未实现的置 0。

### Phase 4：全量回归与基线（0.5 天）

- 完整遍历 `-r 2`（稳定后可 5），确认无 adb 异常中断、结果表每轮 Result=1；
- 验证失败重测流程（`-rp retest-setting.xlsx`）在高通上同样可用；
- 如需内核日志，手动抓 `adb shell cat /sys/fs/pstore/console-ramoops-0` 存档；
- 在一台已知良品机上建立 PASS 基线，作为后续对比标准。

### Phase 5：文档收尾

- README 增补"高通平台"章节（目录、参数差异、已知限制）；
- 本计划文件更新为最终实施记录。

## 2. 高通侧已知限制（接受降级）

1. **bitflip 检出能力不受影响**（pattern 写读比对与平台无关）；
2. **失效物理定位降级**：无 DRAM channel/rank/row/DQ 映射（MTK EMI 专属）；
3. **无 mrdump / dram_para K 值对比**：`Need Trigger Panic` 建议置 0，失效分析改用
   pstore/ramdump（QPST）；
4. **DVFS 控制粒度较粗**：MTK 用 `cpu_hwtest.ko`/`cpuhvfs` 直接控 OPP，高通走标准 cpufreq
   接口，档位切换延迟更高，扫频强度略低；
5. 电量检查、温度降额（`-t 52`）为 jar 通用逻辑，高通上行为一致。

## 3. Plan B：jar 硬失败时的脱 jar 方案

若 Phase 1 证明 jar 对非 MTK 平台有硬性依赖无法绕过，则放弃 jar，直接编排：

PowerShell/Python 循环执行：`条件设置脚本(Phase 3 产物)` → `adb push + 运行开源测试二进制`
→ `grep PASS/FAIL pattern`（直接复用 TestCaseConfig 里的判定串）→ 结果写 CSV/Excel。
`TestCase\` 下的 stressapptest64/memtester64 与日志判定串可全部复用，1~2 天可搭出等价流程，
只是少了自动重测、dram_para 等高级功能。

## 4. 执行检查单

- [x] `VOLCANO\ConditionConfig.xlsx`（最小）+ `dummy_setting.bat`
- [x] `TestCase\TestCaseConfig_qcom.xlsx`（启用 6 个已验证用例）
- [x] Phase 1 MVP 跑通，`--BST.xlsx` 生成且 Result=1（`BAT-Data_2026-09-28_10-40-04`，1 轮 6 用例全 PASS）
- [x] 4 个内存二进制手动验证通过（详见下方实施记录）
- [x] 条件脚本全部高通化并逐一冒烟验证
- [ ] 良品机 PASS 基线建立（依赖 MVP/全量跑）
- [ ] README/文档更新

## 5. 实施记录（2026-09-23，volcano 调试机实测）

**二进制验证（全部 PASS，判定串与 TestCaseConfig 一致）**：
- `stressapptest64 -s 20 -M 512 -m 8` → `Status: PASS - please verify no corrected errors`
  （尾部有 `Failed to open /sys/bus/platform/drivers/dramc_drv/dram_type`，MTK 节点缺失，非致命）
- `memtester64 -m 8 -s 15 128m` → `All Test OK.`
- `mtk_mem_test -s 15 -m 256 -t 8` → `test pass, bye bye`
- `mem_corruption_check -s 15 -m 256 -t 8 -p` → `test pass, bye bye`（dmabuf 不可用时自动回退 malloc）

**条件脚本冒烟（全部通过并已恢复默认）**：
- CPU 锁满频：cur_freq = 1804800/2400000/2707200，governor=performance ✓
- CPU 锁最低频：441600/480000/480000 ✓；Auto 恢复 walt+默认区间 ✓
- GPU 锁满频 min_freq=1150000000 ✓，恢复 264000000~1150000000 ✓
- cpuidle state1/2 disable/enable ✓
- 热插拔循环：cpu0-only ↔ 0-7 周期切换 ✓（`CPU_Hotplug_Stress.bat` 用 `%~dp0` 定位 sh，
  jar 运行时 cwd=平台目录，相对路径亦可工作）

**产物清单**：
- `VOLCANO\ConditionConfig.xlsx` —— MVP 最小配置（仅 CPU-DVFS/Default→dummy，1 轮即结束）
- `VOLCANO\ConditionConfig_full.xlsx` —— 完整遍历（CPU-DVFS×CPU-Hotplug×GPUDVFS×低功耗，
  首轮 8 组合），用 `-cf ConditionConfig_full.xlsx` 启用
- `VOLCANO\*.bat` × 10 + `cpu_hotplug_loop.sh` —— 高通条件脚本
- `TestCase\TestCaseConfig_qcom.xlsx` —— 用例配置（6 用例启用；Suspend-Stress 默认关）
- `TestCase\usb_off_qcom.sh` + `run_suspend_stress_qcom.bat` —— 高通 suspend 变体
  （用 `sys.usb.config` 断/复 USB；**未经监督验证，先手动试跑再考虑打开**）

**MVP 执行命令（确认后运行）**：
```bat
java -jar BitflipAnalysisTool.jar -mt volcano -tf TestCaseConfig_qcom.xlsx -r 1 -a false -k false -o true -i 30
```
全量把 `-cf ConditionConfig_full.xlsx` 加上、`-r` 按需调整。

## 6. 踩坑记录（MVP 排障，后续维护必读）

1. **Excel 布尔单元格**：jar 用 POI `getBooleanCellValue` 读开关列——`ConditionConfig` 的
   `Can Use`、各条件子表的 `Continuous Execution`/`First Stage Test`、`TestCaseConfig` 的
   `CanUse`/`Need Trigger Panic` 都必须是 **Excel 布尔值（TRUE/FALSE）**。写成数字 1/0 会在
   `ConditionManager.init` 抛 `typeMismatch`，**主线程死掉但 JVM 不退出，表现为"运行无响应"
   （首次卡 30 分钟即此原因）**。
2. **stressapptest 内存量**：jar 按 Total Mem/2 传入（7680→3840M），volcano 机 MemAvailable
   仅 ~2.5GB，SAT 3840M + GPU 压力 APK 触发极端 direct reclaim，被传音内存守护机制强制重启
   （pstore 证据：`TranMemoryInfo over direct reclaim ratio limitation` → `sysrq: Kill All Tasks`
   → 有序关机，**非 kernel panic、非 bitflip**）。对策：高通变体脚本固定降档——
   `run-google-stressapptest(-2)-qcom.bat` 用 `-M 1536`、`run_mem_corruption_check_qcom.bat`
   大块用 `-m 2048`，TestCaseConfig_qcom 的 Script 列已指向这些变体。换用更大可用内存的设备时
   可酌情回调。
3. **无害告警**：每轮开始 jar 尝试 pull MTK 的 `current_dram_para`，高通无此节点，stderr 打
   `SyncException: Remote object doesn't exist!` 后继续，不影响流程。
4. **last_kmsg 正常**：jar 在高通上能抓到内核日志（pstore），结果目录有 `last_kmsg-*`。
