# AGENTS.md

MediaTek **Bitflip Analysis Tool (BAT) v5.5.3 for GKI Platform** — a closed-source, binary tool
distribution, not a source repo. There is no build, test, lint, or git. The entire tool is
`BitflipAnalysisTool.jar` (`com.mediatek.bat.Main`); everything else is wrappers, config, and
device-side scripts. Work here means editing config/scripts, not Java.

## CRITICAL: never run the jar to "try it"

- **Any invocation of `java -jar BitflipAnalysisTool.jar` or any `run_*.bat` immediately starts a
  real hardware test**: it auto-discovers adb devices, checks root, reboots the device, installs
  APKs, and runs stress tests for hours. There is **no `-h`/help/dry-run mode** — flags like `-h`
  are ignored and the test starts anyway (verified: a stray run rebooted a connected phone).
- Every `run_*.bat` ends with `pause` — scripts hang waiting for keypress under automation.
- Do not run anything here unless the user explicitly asks for a device test.

## Entry points (all just wrap `java -jar BitflipAnalysisTool.jar ...`)

| Script | Use |
|---|---|
| `run_single.bat` | one attached device |
| `run_single_evb.bat` | EVB boards (`-ib true`, skips battery-level check) |
| `run_mulit.bat <serial>` | one device by serial (the "mulit" typo is intentional — referenced by other scripts, do not rename) |
| `run_multi_auto.bat` | enumerates `adb devices`, spawns one `run_mulit.bat` window per device |
| `*_force_test_all*` | `-ig true` — ignore root-cause check, force all cases |
| `*_retest_fail_case*` | `-rp retest-setting.xlsx -r 20` — rerun only previously failed items |

CLI flags are documented in the header comment of every `run_*.bat`. Note the headers in older
scripts say v4.5.5; the retest script header (v5.4.0) documents two newer flags: `-t <temp>`
(cooldown threshold, default 52°C) and `-rp <file>` (retest result file).

## Configuration = Excel, not code

- `MT####\ConditionConfig.xlsx` — test conditions (OPP/voltage settings) per platform. Platform dir
  is auto-selected from the device build fingerprint (e.g. `mt6878` → `MT6878\`); override with
  `-mt`. Alternate file via `-cf`.
- `TestCase\TestCaseConfig.xlsx` — which stress cases run. Alternate via `-tf`.

## Directory roles

- `MT6789` … `MT6995/` — per-platform condition scripts. Host-side `.bat` files take the device
  serial as `%1` and issue `adb -s %1 shell ...`; `.sh` files are pushed to and run **on the
  device** (`#!/system/bin/sh`).
- `VOLCANO/` — **Qualcomm port** (not an MTK platform; `ro.board.platform=volcano`). Same layout as
  `MT####/`, scripts use Qualcomm nodes (cpufreq policy0/4/7, kgsl devfreq, cpu online, cpuidle).
  MVP config is `ConditionConfig.xlsx`; full traverse is `ConditionConfig_full.xlsx` (select via
  `-cf`). Qualcomm run needs `-mt volcano -tf TestCaseConfig_qcom.xlsx -a false -k false`.
  See `PORTING-to-Qualcomm.md` for status/limits (no EMI dram mapping, no mrdump/dram_para).
- `TestCase/` — device binaries (memtester32/64, stressapptest32/64, mtk_mem_test,
  mem_corruption_check, APKs) plus lifecycle hooks the jar calls: `setup.bat` (once at start),
  `each_boot_setup.bat` (after every reboot), `cleanup.bat` (at end).
- `BAT-Data_<timestamp>/` — created per run. Contains per-case log dirs, `last_kmsg-*`,
  `dram_para_list/`, `BST_Log.txt`, and the result workbook
  `<project>-<serial>--BST.xlsx`.

## Retest workflow (only documented inside `run_single_retest_fail_case.bat`)

1. Open the previous run's `BAT-Data_*\<project>-<serial>--BST.xlsx`.
2. Delete all PASS rows (and rows that failed due to adb exceptions); keep the header row.
3. Save as `retest-setting.xlsx` in this directory.
4. Run a `*_retest_fail_case.bat` (passes `-rp retest-setting.xlsx`).

## Editing gotchas

- Device-side `.sh` scripts are **LF-only**; host `.bat` files are **CRLF**. Preserve existing
  line endings or device-side `sh` will break.
- Config `.xlsx` files: the jar reads toggle columns (`Can Use`, `Continuous Execution`,
  `First Stage Test`, `CanUse`, `Need Trigger Panic`) via POI `getBooleanCellValue` — they must be
  **Excel booleans** (TRUE/FALSE). Numeric 1/0 throws `typeMismatch` in `ConditionManager.init` and
  leaves the JVM hung ("run does nothing"). Verified the hard way.
- `.old` files in `TestCase/` (e.g. `run_apu_vcore_test.sh.old`) are previous versions kept for
  reference — don't "clean them up".

## Prerequisites for actually running

Windows host with `java` and `adb` on PATH; a rooted userdebug MediaTek GKI device over adb;
battery check enforced on phones (use `-ib true` for EVB). Scripts assume MTK-specific device
nodes (`dconfig`, `/proc/cpuhvfs/*`, debugfs, `cpu_hwtest.ko`).
