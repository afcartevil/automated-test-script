# 原生 Android 模块编译参考

当用户需要在单分支全量 checkout 里做原生 Android 编译时读这个参考，例如映射 workspace `<mapped-root>\<workspace>`，其 Linux 对应目录里有 `system/tran_build.sh`。

这里覆盖的是模块级编译，比如 `TeleService`、`telephony-common`、framework/service jar，或由 Java/Kotlin/C++ 改动引出的 APK。它和 rdtool 分区编排是两回事：rdtool 负责 setup 和分区组件构建，原生 Android 脚本负责编译 checkout 里的模块。

## 源背景

相关 SOP 参考：`https://transsioner.feishu.cn/docx/Yxjadx2RPo1SVvxH6nwcdqeWnhc`。

该 SOP 包含 `source tran_build ...` 的 component 编译、LD1.0/LD2.0 参数推导，以及 sys build flag 必须取以下值之一的要求：

```text
bleeding_edge | staging | fooding | stable
```

示例项目形态：

```text
<mapped-root>\<workspace>\system\tran_build.sh
```

在 Linux 上运行时，要从匹配的 workspace 路径执行，不要从 Windows 映射路径执行。

## 判定流程

1. 先确定改动文件路径和 checkout 根目录。像 `<mapped-root>\<workspace>\system\frameworks\...` 这样的 Windows 路径，要映射到 remote runner 或 bridge 里使用的 Linux workspace 根目录。
2. 从改动文件往上找最近的 `Android.bp` 或 `Android.mk`。
3. 提取模块名：
   - `Android.bp`：在相关模块块里找 `name: "..."`，例如 `android_app`、`java_library`、`java_library_static`、`cc_library`、`cc_binary` 或 `prebuilt_*`。
   - `Android.mk`：找 `LOCAL_MODULE := ...`、`LOCAL_PACKAGE_NAME := ...`，或定义产物的 make 变量。
4. 确认模块属于有原生脚本的构建分支，例如使用 `system/tran_build.sh` 时，模块应在 `system/` 对应分支内。
5. 如果用户要的是模块/APK/JAR 产物，就走原生模块编译；如果用户要的是分区级 `sys`、`odm`、`hal`、`krn`、`vext` 或打包，就走 rdtool component 编译。

## 项目构建脚本

对于单分支全量 checkout，优先使用项目脚本初始化对应 component 的编译环境：

```bash
cd <linux-workspace>/system
source tran_build.sh -l <lunch-target> -c <component> -j <jobs> -r <flag>
```

有些 SOP 会简写成 `source tran_build ...`；如果 checkout 里文件名就是 `tran_build.sh`, 就使用树里真实存在的脚本路径/名字。

SOP 里的常见参数：

- `-l <lunch-target>`: target/product name, derived from project make files or SOP examples.
- `-c <component>`: build component such as `sys`, `hal`, `krn`, `vext`, `odm`, or `vnd`.
- `-j <jobs>`: parallelism, often `32` on build servers.
- `-r <flag>`: sys flag; must be one of `bleeding_edge`, `staging`, `fooding`, `stable` when required.

SOP 模式示例：

```bash
source tran_build.sh -l mssi_64_64only_cn_armv82 -c sys -j 32 -r fooding
source tran_build.sh -l mgvi_64_64only_armv82 -c hal -j 32
source tran_build.sh -l mgk_64_k61 -c krn -j 32
source tran_build.sh -l k6878v1_64 -c vext -j 32
source tran_build.sh -l x6870_h781 -c odm -j 32
```

不要默认这些 lunch target 适用于所有项目。真正运行前先从当前 checkout 推导。

## 单模块/APK/JAR 编译命令

稳定策略是“两段式”：

1. `source tran_build.sh ...` 只用来初始化当前 checkout 的 lunch、环境变量和 component 上下文。
2. 初始化完成后，直接执行 Android 原生命令编译模块，例如 `make <module> -j<jobs>`、`m <module>`、`mm` 或 `mmm <path>`。

不要把单模块编译写成 `tran_build.sh --module <module>`、`source tran_build.sh ... --module <module>` 或 rdtool `pipe_main --stage build --module <module>`。这些入口在不同项目上行为不稳定，容易把路径、component 或产物目录带偏。除非用户明确要求验证这些参数，否则 agent 应默认走原生命令。

推荐模板：

```bash
cd <linux-workspace>/system
source tran_build.sh -l <lunch-target> -c sys -j <jobs> -r <flag>
make <module> -j<jobs>
```

如果当前 shell 支持 AOSP helper，也可以在 source 后使用：

```bash
cd <linux-workspace>/system
source tran_build.sh -l <lunch-target> -c sys -j <jobs> -r <flag>
m <module>
```

路径型编译可用：

```bash
cd <linux-workspace>/system
source tran_build.sh -l <lunch-target> -c sys -j <jobs> -r <flag>
mmm vendor/transsion/system_modules/tran_tsn/TranRadioNetApp
```

如果 `m/mm/mmm` 不存在或报未初始化，回退到 `make <module> -j<jobs>`；如果 `make <module>` 找不到目标，再回到 `Android.bp` / `Android.mk` 核对真实模块名。

## 参数推导

用项目 make 文件推导 `-l`：

LD2.0 风格：

- `SYS_TARGET_PROJECT` from `full_<project>.mk` gives the sys project/lunch target.
- `HAL_TARGET_PROJECT` from `vnd_<project>.mk` gives the hal target.
- `KRN_TARGET_PROJECT` from `vnd_<project>.mk` gives the kernel target.
- `VEXT_TARGET_PROJECT` from `vnd_<project>.mk` gives the vext target.
- `VEXT_TARGET_PROJECT` or equivalent in `odm_<project>.mk` gives the odm target depending on project layout.

LD1.0 风格：

- `SYS_TARGET_PROJECT` from `full_<project>.mk` gives the sys target.
- `MTK_TARGET_PROJECT` from `full_<project>.mk` gives the vnd target.
- `MTK_TARGET_PROJECT` from `odm_<project>.mk` gives the odm target.

SOP 里的 LD2.0 判定：在 vnd 代码里检查 `device/mediateksample/<platform>/vext_${chip_platform}/*.mk` 是否存在；存在则视为 LD2.0，否则视为 LD1.0。

## 模块编译策略

当用户改了代码并问该编什么时：

1. 用 `rg --files -g Android.bp -g Android.mk`，或者从改动目录做定向搜索，找到 build 文件。
2. 从 `Android.bp` / `Android.mk` 里解析模块名。
3. 先用 `tran_build.sh` 初始化归属 component 环境，再用原生 `make/m/mm/mmm` 编译模块；不要优先尝试 `tran_build` 的模块参数。
4. 如果原生命令也无法表达或模块目标不存在，就编译最小的归属 component，通过 `tran_build.sh` 或 `harness build build` 完成。
5. 对 `TeleService`、`telephony-common`、framework jar 这类 sys 侧模块，默认通常归 `sys`，但仍要从路径和 build 文件确认。

典型模块发现示例：

```text
packages/services/Telephony/Android.bp -> name: "TeleService"
frameworks/base/telephony/Android.bp or related make file -> name: "telephony-common"
```

这些只是示例。始终要对照当前 checkout 进行验证。

## 远端执行边界

原生编译必须在 Linux 上执行。优先选项：

- 如果已有 allowlisted remote-runner action 能表达原生模块编译，就优先用它。
- 如果没有，就在用户明确批准精确命令后，再用 `harness remote-runner bridge-exec --command "<linux command>" --i-understand-this-runs-raw-shell`。
- 如果要反复做原生模块编译，就在 deployed runner 的 `config/actions.local.yaml` 或 `config/actions.d/*.yaml` 里加结构化 allowlisted action，然后用 `harness remote-runner exec --action ... --args-json ...` 调用。

不要在 Windows PowerShell 里直接运行映射目录下的 `tran_build.sh`。
不要把任意 shell 伪装进 `remote-runner exec`；这个命令只接受已注册的 action ID 和结构化 args。
不要因为是原生 build script 就跳过 remote-runner；如果任务能表示成 action，它仍然应该放在 remote-runner 上。

## 反馈

当你发现了 harness 还没暴露的稳定原生编译形态时，创建反馈：

- `scenario`: `remote-runner` 或 `rdtool`
- `problem_type`: `missing-tool-option` 或 `missing-guidance`
- `tool`: `harness build` 或 `harness remote-runner`
- `detail`: 改动路径、发现的模块名、build 文件类型、脚本命令形态，以及是否应该变成 allowlisted action。

反馈里不要包含凭据、设备序列号或完整私有路径。
