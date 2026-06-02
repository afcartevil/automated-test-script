---
name: harness-build
description: harness 编译任务路由 skill。只负责把编译请求分流到 harness-build-whole-device（整机/rdtool/拉代码/pack.json/分区组件）或 harness-build-native（Android.bp/Android.mk/tran_build.sh/native 模块），避免一个超长 skill 同时覆盖互斥流程。
version: 2.1.14
---

# Harness Build 路由子 skill

编译请求先判断场景，再进入更小的子 skill。不要在这个路由 skill 里直接执行复杂流程。

## 路由

- 用户说“拉一套代码”“整机编译”“编 userdebug/user 版本”“rdtool setup/repo/build/package”“pack.json”“batch-repo/batch-build” → 进入 `harness-build-whole-device`。
- 用户说“编某个 APK/JAR/native 模块”“Android.bp/Android.mk”“TeleService”“telephony-common”“framework jar”“tran_build.sh” → 进入 `harness-build-native`。
- 不确定参数契约时先跑 `harness --json commands describe build <subcommand>`，不要凭其它子命令经验外推。

## 硬边界

- 整机版本路径和 `.pipe/pack.json` 先走 `harness-version-server` 或 `harness-build-whole-device` 里的固定流程，不要手工扫 SMB。
- Linux 构建机动作必须走 `harness build ...` 或 registered remote-runner action；只有用户明确批准一次性诊断时才用受控 fallback。
- Windows 映射盘只是定位 Linux workspace 的视图；不要在 Windows PowerShell 直接运行 Linux build 脚本。
