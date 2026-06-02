# Rdtool 与 Remote Runner 模型

当常见的 `harness build ...` 命令或已注册 runner action 不能直接表达构建请求时，读这个参考，例如整机 workspace 里新引入了一个 component 需要编译。

## 执行模型

Rdtool 应该跑在 Linux 构建机上。Windows 映射路径只是 workspace 定位器，不是本地运行 rdtool 的地方。

原生入口是：

```bash
/opt/ci/civenv/bin/python3 /opt/ci/rdtool/pipe_main
```

常见 shell alias：

```bash
alias pipe_main='/opt/ci/civenv/bin/python3 /opt/ci/rdtool/pipe_main'
```

优先级按下面顺序：

1. `harness build ...` CLI 命令。
2. `harness remote-runner exec --action <allowlisted-action> --args <json>`。
3. 通过已建立的 bridge/session 执行用户批准的 Linux fallback 命令。
4. 如果这个操作会重复，就在 `config/actions.local.yaml` 或 `config/actions.d/*.yaml` 里新增本地 runner action。

不要隐藏任意 shell。如果某个 fallback 应该变成产品行为，就记反馈，补一个新的 CLI 参数或 action。

执行优先级取决于传输和契约，不取决于底层是不是 Linux 脚本。优先用 remote-runner action；只有在没有 action 时，才把 `bridge-exec` 用于用户明确批准的一次性命令或诊断。

## 通用 component 编译

构建模型是通用的，`--component` 不只限于速查里列的例子。现有封装行为来自 `mcp/tools/rdtool_build.py` 和远端 action 配置：

- Repo download: `pipe_main --component <component> --stage repo [--markets <markets>] [--snapshot]`
- Component build: `pipe_main --component <component> --stage build [--markets <markets>] [--local] [--variant <variant>] [--module <module>] [--no-apk-use] [--fast]`
- Package: `pipe_main --stage package [--markets <markets>] [--fast] [--pack-type native] [--variant <variant>]`

已知 component 包括 `sys`、`odm`、`hal`、`krn`、`vext`、`vnd`、`le`、`nonhlos`、`trprd`、`trreg`、`trcar` 和 `trcom`，但某些项目可能会新增更多。遇到未知 component，先看 `pack.json` 的 `part_conf[].component` 或 workspace 状态输出确认名字。

## Market 和 Variant

- `trreg`、`trcar` 和 `trcom` 经常需要 `--markets`。
- 不要把 market 编进 component 名字，比如不要写成 `trreg-op`。
- `trprd` 一般不能带 `--markets`。
- 如果 `sys` 已经在本地做过 local signing，相关 `tr*` 分区也可能需要 `--local`。
- 构建 variant 可能是 `user`、`userdebug`、`root`、`fans`、`user_root`、`user_fans`，取决于项目支持。

## component 没有暴露时怎么做

1. 先运行 `harness build status --mapped-root <root> --workspace <workspace>`，如果能看见 component 就先确认。
2. 如果 component 已经出现在 `pack.json` 或 status 输出里，先试通用 CLI 路径：

```text
harness build repo --mapped-root <root> --workspace <workspace> --component <component>
harness build build --mapped-root <root> --workspace <workspace> --component <component>
harness build batch-repo --mapped-root <root> --workspace <workspace> --components sys,vnd,nonhlos --parallel-profile qcom --max-parallel 3
harness build batch-build --mapped-root <root> --workspace <workspace> --components sys,vnd,nonhlos --parallel-profile qcom --max-parallel 3
```

3. 如果 CLI 拒绝了某个需要的原生参数，但 action 支持，就用 `harness remote-runner exec` 和现有白名单 action + 结构化 args。
4. 如果没有 action 支持，就给出精确的 Linux `pipe_main` 命令供用户批准或执行，并针对缺失的 harness 契约创建反馈。

## Action 注册表

内置 action 定义在 `knowledge_packs/remote-runner-linux/assets/remote-runner/config/actions.yaml`。

用户扩展应该放在部署后的 runner 目录里，不要放到 harness 源码树：

- `config/actions.local.json`
- `config/actions.local.yaml`
- `config/actions.d/*.json`
- `config/actions.d/*.yaml`

CLI 和 legacy MCP 仍然必须提交 `action_id` + 结构化 `args`；不要通过 generic action 偷塞任意 shell 字符串。

## 源码参考

- `docs/rdtool-build.md`：命令映射和未支持参数策略。
- `references/native-android-build.md`：通过 `system/tran_build.sh` 这类项目脚本进行原生 Android 模块构建的模型。
- `mcp/tools/rdtool_build.py`：封装参数名和原生命令语义。
- `knowledge_packs/remote-runner-linux/assets/remote-runner/config/actions.yaml`：内置 action 注册表。
- `knowledge_packs/remote-runner-linux/assets/remote-runner/scripts/rdtool_runner.py`：Linux 侧实现。
