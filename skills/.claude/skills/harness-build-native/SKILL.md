---
name: harness-build-native
description: harness native Android 模块编译子 skill。覆盖 system/tran_build.sh、Android.bp/Android.mk 模块发现、TeleService/telephony-common/framework jar/APK 等单分支 checkout 内模块级 Java/Kotlin/C++ 编译。优先级：已有 CLI/registered action > 用户批准的一次性 Linux fallback。
version: 2.1.17
---

# Harness Native Android Build 子 skill

当用户改了 framework/app/native 模块，任务通常是模块级编译，不是整机 rdtool workspace 的分区组件编译。先定位 checkout 和模块，再通过 Linux 侧 runner 或受控 bridge 执行。

## 判定

- `Android.bp` / `Android.mk` / `LOCAL_MODULE` / `name: "..."` → native 模块编译。
- `TeleService`、`telephony-common`、framework/service jar、APK → native 模块编译。
- `sys/hal/krn/vext/odm/vnd/nonhlos/trprd/trreg` 分区组件、`pack.json`、`batch-repo/batch-build` → 回到 `harness-build-whole-device`。

## 固定流程

1. 确认改动文件所在 Linux checkout。Windows 映射路径要映射到 remote runner/bridge 里的 Linux workspace，不要在 Windows PowerShell 直接跑脚本。
2. 从改动路径向上查最近的 `Android.bp` 或 `Android.mk`，提取模块名。
3. 确认项目是否有 `system/tran_build.sh` 或等价脚本；参数和 lunch target 按 `references/native-android-build.md` 推导。
4. 单模块/APK/JAR 编译不要依赖 `tran_build` 的 `module` 参数，也不要走 rdtool `--module`；稳定路径是先 `source tran_build.sh ...` 初始化环境，再执行 Android 原生 `make/m/mm/mmm <module>`。
5. 如果已有 registered runner action 能表达，就用 `harness remote-runner exec --action ... --args-json ...`；否则只在用户明确批准精确命令后，用 bridge/session 执行一次性 Linux fallback。

## 边界

- 不要把 native 模块问题改写成整机 `batch-build`，除非模块无法定位且用户确认要编整个分区。
- 不要把 raw shell 塞进 `remote-runner exec`；`remote-runner exec` 只接受 registered action。
- 需要反复执行的 native 编译命令，应沉淀为 runner action 或 CLI 契约。
