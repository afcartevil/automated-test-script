# Bitflip Analysis Tool (BAT) v5.5.3 for GKI Platform

联发科（MediaTek）DRAM Bitflip 分析工具，用于在 MTK GKI 平台的 Android 设备上进行内存压力测试
与 bitflip 失效分析。工具本体为闭源 Java 程序（`BitflipAnalysisTool.jar`，主类
`com.mediatek.bat.Main`），通过 adb 控制被测设备，自动完成条件遍历、压力测试、日志收集与
结果判定。

- 版本：v5.5.3（部分批处理脚本头部注释仍标注 v4.5.5/v5.4.0，以 jar 实际版本为准）
- 作者：mtk71029 <yanghui.li@medaitek.com>
- 适用平台：MT6789、MT6835、MT6855、MT6858、MT6878、MT6879、MT6881、MT6886、MT6895、
  MT6897、MT6899、MT6983、MT6985、MT6989、MT6991、MT6993、MT6995

> **警告：本工具没有帮助/演示模式。任何一次运行（包括 `java -jar ... -h`）都会立刻开始真实
> 的硬件测试**——自动搜索 adb 设备、检查 root、重启手机、安装 APK 并执行数小时的压力测试。
> 请勿在未接好被测设备、未做好准备时随手运行。

## 运行环境

- Windows 主机，`java` 与 `adb` 已加入 PATH
- 被测设备：MTK GKI 平台、userdebug 固件、已 root（adb root 可用）
- 手机默认检查电量；EVB 开发板请使用 `run_single_evb.bat`（`-ib true` 跳过电量检查）
- 设备需具备 MTK 专属节点：`dconfig`、`/proc/cpuhvfs/*`、debugfs、`cpu_hwtest.ko` 等

## 目录结构

| 目录/文件                     | 说明                                                                                                                                                                                             |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `BitflipAnalysisTool.jar` | 工具本体，所有 `run_*.bat` 都是对它的封装                                                                                                                                                                    |
| `run_*.bat`               | 各种预设参数的启动脚本（见下表）                                                                                                                                                                               |
| `MT####/`                 | 各平台条件脚本：`ConditionConfig.xlsx` 定义测试条件（OPP/电压等），`.bat` 在主机执行（`adb -s %1 shell ...`），`.sh` 推送到设备端执行（`#!/system/bin/sh`）                                                                          |
| `TestCase/`               | 设备端测试程序（memtester32/64、stressapptest32/64、mtk_mem_test、mem_corruption_check、APK 等）、`TestCaseConfig.xlsx`（用例配置）及生命周期脚本：`setup.bat`（开始时执行一次）、`each_boot_setup.bat`（每次重启后执行）、`cleanup.bat`（结束时执行） |
| `BAT-Data_<时间戳>/`         | 每次运行生成的结果目录（见"测试结果"）                                                                                                                                                                           |

## 使用方法

### 启动脚本

| 脚本                                                                   | 用途                                              |
| -------------------------------------------------------------------- | ----------------------------------------------- |
| `run_single.bat`                                                     | 单台设备测试                                          |
| `run_single_evb.bat`                                                 | EVB 开发板（跳过电量检查）                                 |
| `run_mulit.bat <序列号>`                                                | 按 adb 序列号指定单台设备（文件名 "mulit" 拼写为历史遗留，勿改）         |
| `run_multi_auto.bat`                                                 | 自动枚举 `adb devices`，为每台设备弹出一个 `run_mulit.bat` 窗口 |
| `run_single_force_test_all.bat` / `run_mulit_force_test_all*.bat`    | `-ig true`：忽略根因检查，强制跑全部用例                       |
| `run_single_retest_fail_case.bat` / `run_mulit_retest_fail_case.bat` | `-rp retest-setting.xlsx`：只重测上次失败的项（见"失败重测"）    |

也可以直接命令行运行，例如：

```bat
java -jar BitflipAnalysisTool.jar -o true -i 30 -s <设备序列号>
```

### 命令行参数

（摘自各 `run_*.bat` 头部注释；`-t` 与 `-rp` 为 v5.4.0 新增）

| 参数               | 含义                             | 默认值                  |
| ---------------- | ------------------------------ | -------------------- |
| `-s serialname`  | 多机测试时指定设备序列号                   | —                    |
| `-o true/false`  | 是否强制亮屏                         | false                |
| `-i seconds`     | 手机重启最小等待时间                     | 30                   |
| `-r count`       | 遍历条件下每项重复测试次数                  | 5                    |
| `-f true/false`  | 快速测试模式                         | false                |
| `-m true/false`  | 是否启用 mrdump                    | false                |
| `-c true/false`  | 是否清理测试日志                       | false                |
| `-a true/false`  | 是否执行第二阶段根因分析                   | true                 |
| `-d true/false`  | 是否将 dram k log 存入 dram_para 分区 | false                |
| `-k true/false`  | 是否清理 dram_para 分区及 dram full k | true                 |
| `-t temp`        | 温度高于该值需降温后再测（°C）               | 52                   |
| `-mt platform`   | 强制指定平台脚本目录，如 mt6893            | 按设备指纹自动选择            |
| `-cf file`       | 指定平台目录下的条件配置文件                 | ConditionConfig.xlsx |
| `-tf file`       | 指定 TestCase 目录下的用例配置文件         | TestCaseConfig.xlsx  |
| `-ig true/false` | 忽略根因检查，强制测试全部用例                | false                |
| `-ib true/false` | 忽略电量检查（EVB 用）                  | false                |
| `-rp file`       | 上次可复现失败的测试结果文件（重测用）            | —                    |
| `-p path`        | 日志保存路径                         | —                    |

## 配置说明（改 Excel，不是改代码）

- **测试条件**：`MT####\ConditionConfig.xlsx` —— 定义遍历的 OPP/电压等条件。平台目录根据设备
  build fingerprint 自动匹配（如 `mt6878` → `MT6878\`），可用 `-mt` 强制指定、`-cf` 换用其他
  配置文件。
- **测试用例**：`TestCase\TestCaseConfig.xlsx` —— 定义启用哪些压力用例（CPU DVFS、CPU 热插拔、
  GPU DVFS、MM DVFS、memtester、suspend 等），可用 `-tf` 换用其他配置文件。

## 测试结果

每次运行生成 `BAT-Data_<年-月-日_时-分-秒>/`，内容包括：

- `<项目名>-<序列号>--BST.xlsx` —— 结果总表（PASS/FAIL 判定）
- `BST_Log.txt` —— 运行主日志
- 各用例日志目录（如 `CPU-DVFS_Stress_*`、`GPUDVFS_Stress_*`、`MMDVFS_Stress_*` 等）
- `last_kmsg-*` —— 每次重启后的内核日志
- `dram_para_list/`、`current_dram_para`、`current_dram_para_decode` —— DRAM 参数及解码结果

## 结果判定

按以下顺序判断一次测试的结果（以实际运行的目录 `BAT-Data_2026-09-25_09-07-06` 为例）：

1. **看结果总表**：打开 `BAT-Data_*\<项目名>-<序列号>--BST.xlsx`，每行是一轮条件组合
   （如 CPU-DVFS Stress/Fix-OPP0 × CPU-Hotplug Stress/Fix-CPU-ALL-ON）。**`Result` 列 = 1 表示
   该轮 PASS**；失败行的 `Comment` 列会写明原因。
2. **查主日志**：在 `BST_Log.txt` 中搜索 `result=false` 或 `FAIL`。每个用例结束都会打印
   `TestCase:TestCaseResult [result=true/false, reason=..., detail=...]`，全部 `result=true`
   且无 bitflip/corruption 记录即为正常。
3. **确认测试完整跑完**：正常结束时日志尾部会有 `cleanup.bat` 的清理动作（卸载测试 APK、
   `locksettings set-disabled false`、恢复刷新率等）。如果日志停在某用例中途、结果表行数
   少于计划轮数（条件组合数 × `-r` 重复次数，默认 5），说明测试被中断，已有结论只代表
   已完成部分。
4. **中断后的设备状态**：未执行清理时，设备可能仍锁屏禁用、锁定 60Hz、测试 APK 未卸载；
   不影响下次测试（`setup.bat` 会重新覆盖设置），也可手动运行 `TestCase\cleanup.bat` 恢复。

有失败项时按下面"失败重测流程"只重测失败项，不必全量重跑。

## 高通平台适配（VOLCANO\）

本目录额外包含一套**高通平台适配**（以 volcano 调试机验证），与 MT#### 目录平级、互不影响。
详细移植过程与限制见 `PORTING-to-Qualcomm.md`。

- `VOLCANO\` —— 高通条件脚本目录（jar 按 `ro.board.platform=volcano` 自动匹配，或用 `-mt volcano`
  强制）。CPU 用标准 cpufreq（policy0/4/7），GPU 用 kgsl devfreq，另有热插拔/cpuidle/suspend 脚本。
- `VOLCANO\ConditionConfig.xlsx` —— 最小验证配置（1 轮即结束，用于首次跑通）。
- `VOLCANO\ConditionConfig_full.xlsx` —— 完整遍历，用 `-cf ConditionConfig_full.xlsx` 启用。
- `TestCase\TestCaseConfig_qcom.xlsx` —— 高通用例配置（6 个已验证用例；Suspend-Stress 默认关，
  对应 `usb_off_qcom.sh`/`run_suspend_stress_qcom.bat`，需人工验证后手动打开）。

高通运行命令（最小验证）：

```bat
java -jar BitflipAnalysisTool.jar -mt volcano -tf TestCaseConfig_qcom.xlsx -r 1 -a false -k false -o true -i 30
```

注意事项：

- 高通用例脚本有 `*-qcom.bat` 变体（SAT 固定 `-M 1536`、mcc 大块 `-m 2048`）——jar 默认按总内存
  一半传参（3840M），在低可用内存机器上会触发内存守护强制重启，务必用 qcom 变体；
- 自制/修改配置 xlsx 时，`Can Use`、`Continuous Execution`、`First Stage Test`、`CanUse`、
  `Need Trigger Panic` 各列必须是 **Excel 布尔值**（TRUE/FALSE），写数字 1/0 会让 jar 抛异常后
  假死（详见 `PORTING-to-Qualcomm.md` 踩坑记录）。

高通侧已知降级：无 DRAM 物理地址/DQ 映射（MTK EMI 专属）、无 mrdump/dram_para
（故 `-a false -k false`），失效分析改用 pstore（`/sys/fs/pstore/console-ramoops-0`）。

## 失败重测流程

（仅记录在 `run_single_retest_fail_case.bat` 注释中）

1. 打开上一次失败测试的结果表，如
   `BAT-Data_2025-06-05_23-06-02\alps-k6991v1_64-0123456789ABCDEF--BST.xlsx`。
2. 删除所有 PASS 行（因 adb 异常而失败的行也一并删除），保留表头和真正失败的行；也可删掉
   PASS 的 stress 大类以精简流程。
3. 将修改后的文件放到工具目录并重命名为 `retest-setting.xlsx`。
4. 运行 `run_single_retest_fail_case.bat`（等效于 `-rp retest-setting.xlsx -r 20`，
   `-r` 为每项重复轮数）。

## 注意事项

- **没有 `-h` 帮助**：加任何参数都会直接开始测试；每个 `run_*.bat` 末尾都有 `pause`，自动化
  调用时会停在按键等待处。
- 测试会**重启设备**并安装/卸载 APK（`cpu-idle-test.apk`、`gpu-stress.apk`），结束时由
  `cleanup.bat` 恢复设置（锁屏、刷新率、usb vcore boost 等）。
- 编辑脚本时保持原有换行符：设备端 `.sh` 为 **LF**，主机 `.bat` 为 **CRLF**，改错会导致
  设备端 shell 执行失败。
- `TestCase/` 下的 `.old` 文件（如 `run_apu_vcore_test.sh.old`）是保留的旧版本，请勿清理。
- 单次完整测试耗时数小时，请确保设备电量/散热与 adb 连接稳定。
