---
name: harness-build-whole-device
description: harness 整机/rdtool 编译子 skill。覆盖整机拉代码、workspace setup/repo/build/resource/package/artifacts、pack.json、batch-repo/batch-build，以及分区组件级构建。优先级：harness build CLI > harness remote-runner exec allowlisted action > 用户批准的 Linux fallback。
version: 2.1.14
---

# Harness Whole-device Build 子 skill

整机拉代码、rdtool setup/repo/build/package 是 CLI 可直接解决的问题：优先运行 `harness build ...`、`version-server ...` 和 `remote-runner ...`，不要先 `knowledge route/search`。只有 CLI 参数缺口、rdtool 报错需要解释、或用户询问流程/SOP 时才读 references 或查知识库。

**需要 rdtool 流程/参数/平台分区 SOP 时，先查本仓知识包，不要默认去飞书现拉**：整机编译的 stage 详解、全参数、MTK/QCOM/UNISOC 组件矩阵、trprd/trreg/trcar/trcom 定制分区、版本服务器与 pack.json 约定都已沉淀在 `common/whole-device` 知识包（`rdtool-workflow.md` / `partition-architecture.md` / `version-server.md` / `version-naming.md`）。用 `harness --json knowledge search "整机编译"`（或 `trpart` / `pack.json` 等关键词）命中场景再读其 references；只有本地文档标注"待确认"或需要最新政策变更时才查飞书，并把长期知识回写到对应知识包。

## 执行模型

`harness build ...` 的实际工作全部发生在 **Linux build server** 上，CLI 只是 Windows 端的派发入口。所有路径、组件名、shell 片段最终都拼成 Linux 命令行 —— 一律按 Linux 习惯写：**正斜杠 `/`、区分大小写、不要写盘符**。`--mapped-root <mapped-root>` 只是"Windows 看同一台 Linux 机器的窗口"，不代表 `--workspace` 是 Windows 路径。

workspace 是一个**有状态的目录**，状态文件在 `<mapped-root>/<workspace>/.pipe/` 下。各子命令按"读 / 写 workspace 状态"分工：

| 子命令 | 角色 | 写状态？ | 接受的关键 flag |
|---|---|---|---|
| `status` | 读状态，排错入口 | — | — |
| `setup` | 初始化/更新 workspace | ✓（variant / local / cfg-file 写入） | `--cfg-file` `--variant` `--local` `--snapshot` `--confirm-workspace-path` |
| `repo` | 按状态拉组件源码 | ✗ | `--component` `--markets` `--snapshot` |
| `build` | 编译组件，可临时 override | ✗（override 不写回） | `--component` `--variant` `--local` `--module` `--fast` `--no-apk-use` |
| `package` | 出镜像 | ✗ | `--markets` `--variant` `--fast` `--pack-type` |
| `resource` | 从 SMB 拉 CI artifact | ✗ | `--smb-credential` |
| `artifacts` | 列产物 | — | — |

由此自动推出几个常见坑：

- **嵌套 workspace** 写 `project/KM9_NEW`，不写 `project\KM9_NEW`；分隔符按 Linux 来。
- **先自动发现本机映射盘和 runner**：用户要求“拉代码/编版本”但没有给出本机映射路径时，先运行 `harness --json remote-runner discover`。如果已经发现可用 runner 或唯一明确的映射盘候选，直接用发现结果继续检查状态；不要先问用户“mapped-root 是哪个”。
- **发现疑似误装 runner 要停下来**：如果 `remote-runner discover/status/check` 返回 `approved_for_runner: false`、`suspicious_runner_root: true` 或 `REMOTE_RUNNER_MAPPED_ROOT_NOT_APPROVED`，不要把这个 runner 用于 build/setup/repo，也不要把它的路径传给 `--mapped-root`。用人话告诉用户“发现的 runner 像是装在个人子目录或单仓目录里，不能用”，然后询问正确的服务器映射盘路径；不要在 skill 里固化任何个人 UNC 路径。
- **问用户时说人话**：只有 discover 找不到映射盘/runner，或多个候选无法判断时，才问用户“Linux 服务器代码目录在你本机映射成哪个盘或路径？例如 `Z:\` 或 `\server\share`”。不要把问题写成“rdtool 映射根 / mapped-root 是哪个”，也不要让用户在“我提供 mapped-root 字符串”和“让 harness discover”之间做选择。
- **先问有没有现成整机代码，不要无目的搜索**：确认本机映射路径后，如果用户没有给出整机 workspace，先询问用户是否已有可复用的整套代码；有则请用户给 workspace 名/相对路径（必要时给 Linux 侧 `/work/code/...`），没有则再确认新建位置和目录名。不要枚举用户本机映射盘目录、Linux 构建机目录、`pack.json` 或历史 workspace 来猜用户想用哪套代码。
- **不要猜 `--mapped-root` 或 `--workspace`**：盘符、映射路径和 workspace 名都是用户个人环境。`harness --json remote-runner discover` 用于发现 runner 通信入口和已安装状态；没有用户确认时，不要把 discover 输出里的目录名当作要复用或新建整机代码的位置。
- **不要把 discover 候选当成整机 workspace 父目录**：`remote-runner discover` 返回的是 runner 安装/可达位置和映射根下的已有顶层目录清单，不等于可以新建整机代码的父目录。`workspaces` 数组里的任何目录名都只是现状枚举；即使目录名叫 `projects`、`workspaces`、`ws` 或看起来像项目集合，也不能当作“常见约定”或默认父目录。只有用户在当前对话里明确指定“就在这个相对路径下新建/复用”，才允许在那里 setup/repo/build。
- **泛化父目录必须带确认参数**：如果用户明确确认的 workspace 路径确实是 `projects/...`、`workspaces/...` 或 `ws/...`，执行 `build setup/repo/build/batch/resource/package` 时必须加 `--confirm-workspace-path`。没有用户确认时不要加这个参数；CLI 会返回 `BUILD_WORKSPACE_PATH_NEEDS_CONFIRMATION` 并生成本地反馈草稿，要求先确认准确路径。
- **新建整机 workspace 必须二次确认位置**：需要新建目录做 rdtool setup/update 实验时，先向用户确认“在哪个 share 根/整机 workspace 父目录下创建”和“目录名”。默认倾向用户确认的 share 根下的独立新目录；不要把测试目录建进已有配置仓、单仓或项目列表仓。
- **齐治 bridge 未连接就硬停止**：`build setup/repo/build`、`remote-runner bridge-install/check/exec` 或任何 Linux 命令需要齐治 bridge 但 `bridge.ready` 不是 true 时，只能提示用户在可信本地终端运行并保持 `harness remote-runner bridge-serve`，直到看到 `[bridge] READY` 后再继续。不要由 Agent 自动拉起 bridge，不要追问 `exec.cmd` 路径，不要继续列 pack/setup/build 后续步骤，也不要询问“是否复用现有 workspace / 要新建到哪个目录”。等 bridge READY 后，再从版本查询和 workspace 确认流程继续。
- **pack 选择和最终编译 variant 分开处理**：`userdebug/user/root` 这些整机代码通常是同一套，`pack.json` 主要决定项目/OS/分支/组件集合，不必强行找同名 variant 的 pack。最终产物 variant 由 `build build`、`batch-build`、`package` 的 `--variant` 决定。
- **缺少版本维度时必须确认**：很多项目同时有不同 OS 版本、主干/量产分支和 TEST/DEV/KOM/ASAN 版本类型。用户没有明确说 OS 版本（如 A16/tos16/hios16/16.3.0）、主干/量产（trunk/release）或版本类型（转测/DEV/KOM/ASAN）时，先用 `version-server list-versions/find-latest` 的候选信息整理可选组合并询问用户确认；不要默认替用户选择 A16、主干、量产或 TEST。
- **`--variant` / `--local` 只在写状态或临时 override 的子命令上有效**。`setup` 可写入默认 variant；`repo` 阶段不要再传 —— `repo` 只按状态拉源码，传了会报 `unrecognized arguments`。
- **参数表不全是"通用 flag"**：见上表，每个子命令的 flag 是它自己角色决定的。不确定时跑 `harness --json build <子命令> --help` 或 `harness commands describe build <子命令>`，不要凭其它子命令的经验外推。
- **排错先 status**：rdtool 报错或参数缺失，先 `harness --json build status --mapped-root <root> --workspace <ws>` 看 workspace 现在的状态再决定下一步，不要直接重发 setup。
- **代码工作区可以复用，但必须确认**：整机编版本需要有本地/远端 workspace 代码，但不是每次都重新拉。用户可能已经有整套代码，rdtool 也支持指定已有本地代码工作区。若当前会话里你之前拉过代码，或 `remote-runner discover/status` 找到已有 workspace，先把候选 `<mapped-root>/<workspace>`、项目、分支/版本、组件状态报告给用户，确认是否复用。
- **更新已有代码前先问本地改动**：已有 workspace 可能代码太旧，需要 `batch-repo` / repo sync 更新；但如果用户改过某些仓库，更新可能失败或需要先处理本地改动。不要默认对已有 workspace 直接同步。先问用户是否允许更新，以及本地改动如何处理（保留不动、用户已提交、另建 workspace、或用户确认可以由 rdtool 更新）。
- **已有代码不等于已有 pack.json**：有些整机代码是用户直接 `repo sync` 拉下来的，workspace 里可能没有 `pack.json` 或 `.pipe/info.json`。这种情况下不能仅凭目录存在就开始编译；仍要用版本服务获取目标项目对应的 `pack.json`，或在用户批准的 rdtool fallback 中使用原生 `pipe_main --stage setup --cfg-url/--cfg-path`。
- **已有代码必须核对项目/OS/分支**：用户指定已有代码时，编译前必须检查它是不是目标项目、目标 OS/分支对应的代码。不要因为 workspace 的默认 variant 与目标输出 variant 不同就判定代码不可复用；最终输出 variant 可以在 build/package 阶段 override。当前 `build status` 只能读 `pack.json` 和 `.pipe/info.json`；如果没有 pack 或状态不足以证明分支正确，需要通过受控 runner action/用户批准的 Linux 检查读取各 repo 分支状态，再让用户确认是否继续。
- **pack.json 要随目标项目/OS/分支更新**：不同项目、不同 OS、主干/量产、市场和组件集合的 `pack.json` 都可能不同。复用已有代码时，也要重新拿目标项目/OS/分支对应的 `pack.json`，用 `build setup --cfg-file ...` 对已有 workspace 做 setup/update；不要拿旧项目或旧 OS/分支的 pack 继续编。但不要把 `pack.json` 的 variant 当作最终产物 variant 的硬条件。
- **SCMP/配置平台能力边界**：rdtool 原生支持 `--cfg-url`、`--cfg-path/--cfg-grep`、`--code-dir` 等配置/代码来源参数，但当前 harness CLI 的 `build setup` 只封装 `--cfg-file`。需要从 SCMP/配置平台直接拉最新配置时，先说明 CLI 暂未暴露该能力；优先用 version-server/Spug 拿 `.pipe/pack.json`。若必须走原生 rdtool 参数，按“用户批准的 Linux fallback”或新增 runner action/CLI 契约处理，不要把 raw 命令塞进 `remote-runner exec`。
- **`--cfg-file` 必须让 Linux runner 读得到**：不要把 Windows 本地临时路径传给 `build setup --cfg-file`。cfg 文件应放在 mapped-root/workspace 内，或传 workspace 相对路径；CLI 会把映射根下的 Windows 路径转换成 Linux 可读的相对路径，发现本地盘路径时会拒绝并要求先放进 workspace。
- **清理误建 workspace 优先走 Linux 侧**：误建目录含大量小文件时，不要优先用 Windows 映射盘递归删除；bridge READY 时优先通过受控 bridge/runner 方式在 Linux 侧清理，或先反馈缺少语义化 `build cleanup` 子命令，不要让用户在 Windows 侧手工慢删。

## 整机拉代码并编译的固定流程

用户说“拉一套 <project> 代码并编 userdebug/user 版本”时，按下面顺序执行，不要在中途改成让用户手工操作：

0. 先自动发现本机映射路径和 runner：运行 `harness --json remote-runner discover`。如果发现可用 runner 或唯一明确的映射盘候选，且没有 `approved_for_runner: false`、`suspicious_runner_root: true` 或 `REMOTE_RUNNER_MAPPED_ROOT_NOT_APPROVED`，才用该 `<mapped-root>` 继续；只有发现不到、候选不明确或候选被标记为疑似误装时，才问用户“Linux 服务器代码目录在你本机映射成哪个盘或路径？例如 `Z:\` 或 `\server\share`”。不要要求用户理解 `mapped-root` 术语。
   然后确认代码来源：询问用户“是否已有现成的整机代码 workspace 可以复用”。如果有，请用户提供 workspace 名/相对路径，必要时补 Linux 侧 `/work/code/<linux_user>/<project_workspace>`；如果没有，再询问希望在哪个 share 根/整机 workspace 父目录下新建以及目录名。不要为了替用户找代码而扫描用户本机映射盘目录、Linux workspace、`pack.json` 或历史目录。
1. 再用版本服务拿目标项目/OS/分支对应的 `pack.json`。如果用户没有指定 OS 版本、主干/量产分支或 TEST/DEV/KOM/ASAN 版本类型，先列候选并向用户确认，不要直接默认 `--version-type TEST`、A16、主干或量产。确认后再按目标输出 variant 查询：
   `harness --json version-server get-pack-json --project <project> --version-type <confirmed-type> --tos-version <confirmed-os> --branch-kind <confirmed-branch-kind> --variant <variant> --output <local-pack-json>`。
   只有用户说 A16/tos16/hios16，或已确认该 OS 时，才加 `--tos-version 16`；只有用户说主干/量产，或已确认该分支类型时，才使用 `--version-type ALL --branch-kind trunk|release`。如果返回 `not_found` 但 `candidates` 里同 OS/分支有 `user` 或其它 variant，改用可用 variant（优先 `user`）再取 pack，并在答复里说明“代码相同，最终仍用 `--variant <目标>` 编译”。不要再用 `Get-ChildItem` 或手工 SMB 扫描找 `pack.json`。
   如果用户明确指定 DEV/KOM/ASAN 或特定迭代，再改对应参数；不要手工拼版本服务器路径。
2. 用第 0 步确定的 `<mapped-root>` 检查 runner。discover 候选只用于定位通信入口，不自动决定整机 workspace 父目录。只有用户已经确认要复用/新建的位置后，才把对应 `<mapped-root>`、`<workspace>` 用于 status/setup/repo/build；不要把 discover 输出里的任何目录名自动用作整机 workspace 根。不要回答“因为 discover 列出了某个目录，所以我选择它作为父目录”；discover 没有这个语义。
3. 跑 `harness --json remote-runner status --mapped-root <mapped-root>`。如果 `is_available` 不是 true，不要停下来等用户：
   - 传音构建机默认走齐治时，先看 `harness --json remote-runner discover` 的 `bridge.ready`；如果已经是 `true`，直接跑 `bridge-install`，不要再询问 `exec.cmd` 路径。未 READY 时硬停止当前流程，只提示用户在可信本地终端运行并保持 `harness remote-runner bridge-serve`，直到看到 `[bridge] READY` 后再继续；此时不要列后续 pack/setup/build 计划，不要询问复用现有目录或新建目录。
   - 只在缺少登录凭据、OTP、或无法推导 `<linux-share-root>` 时询问用户补充信息；不要让用户登录 Linux 执行脚本，也不要由 Agent 自动拉起 bridge。
4. runner 可用后，先判断是否已有可复用整套代码：
   - 若用户明确给了已有 workspace，或 discover/status 显示已有 workspace，先跑 `harness --json build status --mapped-root <mapped-root> --workspace <workspace>`，把项目、分支/版本、variant、已拉组件、缺失组件和明显错误报告给用户确认。
   - 如果 `pack_json_exists` 或 `pipe_initialized` 为 false，不要把该目录当作已可编译 workspace；它可能只是 repo sync 出来的代码。先确认是否要用目标版本 `pack.json` 对它执行 setup/update，或另建 workspace。
   - 如果 workspace 与目标项目/分支/OS 明显不匹配，或用户希望干净环境，询问是否新建 workspace；不要直接覆盖旧 workspace。默认 variant 不同不等于代码不匹配。
   - 如果已有状态无法证明各 repo 分支正确，先说明风险并请求确认是否检查/更新分支；不要直接编译。
   - 如果 workspace 匹配且用户确认“代码已是最新/不用更新”，可以跳过 `batch-repo`，直接按完整组件集合 `batch-build`。
   - 如果需要更新已有代码，先确认用户是否有未提交本地改动；没有确认前不要启动会触发 repo sync 的 `repo`/`batch-repo`。本地改动存在时，优先建议另建 workspace 或让用户确认已自行提交/备份后再更新。
5. 需要初始化或切换 workspace 状态时再：
   `harness --json build setup --mapped-root <mapped-root> --workspace <workspace> --cfg-file <local-pack-json> --variant <variant>`；
   若 `<workspace>` 以 `projects/`、`workspaces/` 或 `ws/` 开头，只有在用户已明确确认该完整路径时才追加 `--confirm-workspace-path`。
   然后读取 `pack.json` 的 `part_conf[].component` 得到组件集合；这个集合是版本配置给出的下限，不一定覆盖 rdtool 整机流水线的所有传音定制分区。MTK 整机编译默认要把 `trprd,trreg` 也纳入计划，QCOM 常见也要包含 `trprd,trreg`；只有用户明确说明项目不需要某个 tr 分区，或者 workspace/status/pack 证明该项目没有该分区时，才跳过。不要默认只编 `sys`，也不要把 pack.json 缺少 `trprd/trreg` 解读成无需编译。
   如果 `part_conf` 不可读，先用 `harness --json build status --mapped-root <mapped-root> --workspace <workspace>` 查 workspace 状态，再按项目平台选择常见全量组合（MTK 常见 `sys,hal,krn,vext,odm,trprd,trreg`；QCOM 常见 `sys,vnd,le,odm,nonhlos,trprd,trreg`），不要把 `sys` 当作整机默认。
   `batch-repo` / `batch-build` 的 `--markets` 和 `--local` 是整条命令的全局参数；遇到 tr 分区要按参数差异拆命令，不要把 `--markets op` 误加到 `trprd` 或基础分区。常见 MTK 本地 system 编译流程：基础分区先按普通参数 batch；`trprd` build 另跑 `--local`；`trreg` repo/build 另跑 `--markets op`，build 阶段同时带 `--local`；最终 `package` 带 `--markets op`。
   `batch-repo` 会自动合并同源 repo 组：MTK 下 `vnd/odm/hal/krn/vext/vendor` 只投递一个代表组件拉代码，其它组件在结果里标记 `repo_deduped` / `repo_covered_by`；`sys` 与 vendor 源码组是不同锁，可以在 runner 多 worker 时并行拉。不要为了“完整组件集合”手工把同源组件拆成多条 repo 命令。
6. 每次成功确认或新建 workspace 后，在当前对话里记录 `<mapped-root>/<workspace>`、项目、版本/分支、variant、组件集合和是否执行过 repo 更新；后续同项目编译先拿这条记录询问用户是否复用。每个阶段失败先看 JSON 返回和 trace/log 路径；不要重复询问用户已完成哪个脚本。

## 命令示例

整机一次性流水线优先用 `build pipeline`（repo→build→package→notify 状态机，自动处理树级并发、trpart `--local`/`--markets`、失败 abort 与 `failed_stage`/`detected_failure_signal` 透传）；下面的 `batch-repo`/`batch-build`/`resource`/`package` 零件命令留给单 stage 调试或 pipeline 不适用时回落。

```text
harness --json remote-runner discover
harness build setup --mapped-root <mapped-root> --workspace <workspace> --cfg-file pack.json
harness --json build status --mapped-root <mapped-root> --workspace <workspace>
harness --json build setup --mapped-root <mapped-root> --workspace <workspace> --cfg-file pack.json
# 首选：一条命令跑完整机本地全编(resource 默认关；含 trreg 必带 --markets)
harness --json build pipeline --mapped-root <mapped-root> --workspace <workspace> --confirm-workspace-path --components <base-components>,trprd,trreg --variant userdebug --parallel-profile <mtk|qcom> --markets op
# 回落零件命令(单 stage 调试)
harness --json build batch-repo  --mapped-root <mapped-root> --workspace <workspace> --components <base-components-plus-trprd> --parallel-profile <mtk|qcom> --max-parallel 3
harness --json build batch-repo  --mapped-root <mapped-root> --workspace <workspace> --components trreg --markets op --parallel-profile <mtk|qcom> --max-parallel 1
harness --json build batch-build --mapped-root <mapped-root> --workspace <workspace> --components <base-components> --variant userdebug --parallel-profile <mtk|qcom> --max-parallel 3
harness --json build batch-build --mapped-root <mapped-root> --workspace <workspace> --components trprd --variant userdebug --local --parallel-profile <mtk|qcom> --max-parallel 1
harness --json build batch-build --mapped-root <mapped-root> --workspace <workspace> --components trreg --variant userdebug --local --markets op --parallel-profile <mtk|qcom> --max-parallel 1
harness --json build resource --mapped-root <mapped-root> --workspace <workspace>
harness --json build package --mapped-root <mapped-root> --workspace <workspace> --markets op --fast
harness --json build artifacts --mapped-root <mapped-root> --workspace <workspace>

# 只有用户明确说“只编 sys / 只编某个分区 / 调试某个组件”时才用单组件命令：
harness --json build repo   --mapped-root <mapped-root> --workspace <workspace> --component sys
harness --json build build  --mapped-root <mapped-root> --workspace <workspace> --component sys --variant userdebug
```

## 已知 component

`sys`、`odm`、`hal`、`krn`、`vext`、`vnd`、`le`、`nonhlos`、`trprd`、`trreg`、`trcar`、`trcom`。新项目可能引入更多；先查 `pack.json` 的 `part_conf[].component`。

## Fallback 优先级

1. `harness build ...` CLI 命令；
2. `harness remote-runner exec --action <allowlisted-action> --args <json>`；
3. 用户批准的 Linux `pipe_main` 命令；
4. 重复操作 → 在 deployed runner 的 `config/actions.local.yaml` 注册新 action。

不要发明任意 shell；不要把 raw 命令塞进 `remote-runner exec`。详见 `references/rdtool-runner-model.md`。

## 反馈

```text
harness --json feedback create --scenario rdtool --problem-type missing-tool-option \
  --tool "harness build build" --detail "..."
```
