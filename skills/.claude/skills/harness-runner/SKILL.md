---
name: harness-runner
description: harness remote runner / 齐治堡垒机 bridge 子 skill。覆盖 remote-runner discover/install/check/status/exec/ssh-install/bridge-install/bridge-serve/bridge-diagnose/bridge-exec 命令。当操作属于 Linux 构建机时（整机编译、Linux workspace repo/git、整机大范围搜索、runner action）使用。优先级：CLI > registered action > 用户批准的 fallback 命令。
version: 2.1.14
---

# Harness Runner 子 skill

## 执行模型

remote-runner / bridge 这一组工具的 **执行端永远在 Linux build server 上**，CLI 是 Windows 端的派发入口。Windows 看到的 `<mapped-root>` 和 Linux 看到的 `/work/code/<linux_user>` 是**同一棵映射根目录树的两个视图**：

- `--mapped-root <drive>:\`：Windows 侧的映射根入口，CLI 用它定位 runner 部署根（`<mapped-root>\tran_harness\remote-runner`）。
- `--remote-workspace /work/code/<linux_user>`：Linux 侧映射根目录，由 SSH / qizhi bridge 直接部署和启动 runner。尖括号内容必须替换成真实账号，不能原样复制。
- 任何路径、命令字符串都是给 Linux shell 用的：**正斜杠、区分大小写、按 Linux 习惯写**。

由此自动推出几个常见坑：

- **路径分隔符**：`--remote-workspace` 永远 `/`，不要写 `\`；shell 命令里的 `~/`、`$USER`、`find ... -name` 都按 Linux 语义。
- **`--remote-workspace` 必须是映射根**，也就是 `/work/code/<linux_user>`；不能传 `/work/code/<linux_user>/<project-or-repo>`、具体项目 workspace、单仓目录或任何更深子目录。CLI 会拦截明显占位符和 Linux 子目录。
- **盘符不要写死**：每个人映射的盘符和登录账号都不同；示例里的 `<mapped-root>` / `<linux_user>` 是占位。要识别用户盘符跑 `harness remote-runner discover`，要拿 Linux 用户名用 `$USER` 占位。
- **部门共享 vs 个人盘**：部门共享盘通常对个人账号**只读**，`install` 会失败；个人盘可写。`discover` 优先选可写的；用户给的 `--mapped-root` 不可写时直接报错并提示换盘符。

## 何时进入

- 用户给出 Windows 映射根（`<mapped-root>`）但还没装 runner；
- Linux 侧编译 / repo / git / 大范围搜索；
- 没有映射但用户能通过齐治堡垒机登录；
- 已知 action 不能表达需求时，优先找语义化 CLI；只有没有语义化 CLI 时才 fallback 到 bridge-exec。

## 命令示例

```text
# 自动发现已部署的 runner
harness --json remote-runner discover

# 安装 / 状态 / 诊断（盘符用 discover 的结果，不要照抄任何示例盘符）
harness --json remote-runner install --mapped-root <drive>:\ --force
harness --json remote-runner status  --mapped-root <drive>:\
harness --json remote-runner check   --mapped-root <drive>:\

# 执行注册 action（结构化参数，不是 raw shell）
harness --json remote-runner exec --mapped-root <drive>:\ --action build.status --args-json "{}" --timeout 300

# SSH 直连部署（remote-workspace 必须是 Linux 映射根；替换尖括号内容后再执行）
harness --json remote-runner ssh-install --ssh-target user@host --remote-workspace /work/code/<linux_user>

# 齐治堡垒机 bridge
harness remote-runner bridge-serve            # 用户在可信本地终端手动拉起并保持窗口；Agent 不要自动启动
harness --json remote-runner bridge-install --remote-workspace /work/code/<linux_user>
harness --json remote-runner bridge-diagnose  # 固定只读诊断 runner/tmux/log；不需要用户批准 raw shell
harness --json remote-runner bridge-exec --command "pwd" --i-understand-this-runs-raw-shell   # 用户批准的一次性命令
```

## 齐治 bridge 配置文件

Agent 不要引导用户手动设置 HARNESS_QIZHI_* / OPEN_GROK_* 环境变量。`harness config setup-env` 会写入 `~/.tran_harness/env.yaml`，CLI 会自动读取该配置文件；环境变量只作为临时覆盖。

正确流程：

1. 先查已有配置：`harness --json config setup-env --print-only --non-interactive`。
2. 缺哪个值，就只问用户哪个具体值；密码类字段用当前客户端的安全输入/提问能力收集，不在回答中回显。
3. Agent 自己执行非交互命令：
   ```text
   harness --json config setup-env --non-interactive      --qizhi-user <user>      --qizhi-target-host <host>      --qizhi-target-password <cmdb-password>      --qizhi-bastion-password <ldap-password>
   ```
4. 只有想预览 `~/.tran_harness/env.yaml` 时才加 `--print-only`；正常自动化直接写配置文件，不要让用户复制环境变量命令。

需要配置的变量：

- `HARNESS_QIZHI_USER`
- `HARNESS_QIZHI_TARGET_HOST`
- `HARNESS_QIZHI_TARGET_PASSWORD`
- `HARNESS_QIZHI_BASTION_PASSWORD`（持久化 LDAP）
- `HARNESS_QIZHI_OTP`（仅一次性自动化，不持久化）

## 选择 runner / bridge / SSH 的顺序

1. `discover` 找已部署的；
2. 用户已有可写映射但没 runner → `install`；
3. 没有映射但 SSH 可达 → 仅在用户明确提供并批准 SSH 直连时使用 `ssh-install`；
4. SSH 不通但齐治可登 → 用户先手动启动 `bridge-serve` 到 READY，Agent 再执行 `bridge-install`；
5. runner/tmux/log 的固定只读诊断 → `bridge-diagnose`，不需要用户批准 raw shell；
6. 任务能表达成 registered action → `exec`；
7. 只在没有 action 或语义化 CLI 时才 `bridge-exec` + 用户明确批准。

Agent 自动化要求：

- 如果需要齐治登录，Agent 不要自动运行 `harness remote-runner bridge-serve`。停止当前工作，提示用户在可信本地终端手动启动并保持 bridge 窗口；只有用户确认已经 READY 或 `discover` 返回 `bridge.ready: true` 后才继续。
- 先用 `harness --json remote-runner discover` 检查 `bridge.ready`；如果用户已经启动 bridge 且 READY，Agent 直接复用它执行 `bridge-install --remote-workspace /work/code/<linux_user> --force`，不要再询问 `exec.cmd` 路径；如果未 READY，必须停止并提示用户连接。
- bridge READY 后，Agent 继续执行 `bridge-install --remote-workspace ... --force`，该命令会在 Linux 侧映射根启动并校验 runner；不要把 `start_remote_runner.sh` / `verify_remote_runner.sh` 作为“用户协助步骤”发给用户。
- 如果已有 Windows 映射盘，只把 `install --mapped-root ...` 当作部署文件到映射目录；启动 Linux 侧 runner 仍由 Agent 通过 `ssh-install` 或 `bridge-install` 完成。
- `status/check` 看到 `is_available: false`、`not_found`、`availability_reason=control_stop_exists`、队列不响应或刚执行过 `install` 后，如果 `bridge.ready` 不是 true，就停止并提示用户先连接 bridge；如果已经 READY，才继续 `bridge-install`。`check` 不会再写 `control/stop`，`bridge-install` 会在启动前清理陈旧 `control/stop` 并校验 runner。
- 可以询问用户补充缺失事实（例如 Linux 映射根 `/work/code/<linux_user>`、齐治账号、OTP），但不要把可由 CLI 完成的动作写成用户步骤。

## Action 与 raw shell 边界

- `remote-runner exec` 只接受 `action_id` + 结构化 `args`，**不接受**任意 shell 字符串。
- runner 不可用但 bridge 已 READY，且只需要查看 tmux 会话、runner 根目录、control 目录、队列积压、control-history 日志时，直接执行 `harness --json remote-runner bridge-diagnose`。这是固定只读诊断命令，不需要再问用户批准 `tmux has-session ...` 这种 raw shell。
- 如果 `bridge-diagnose` 里 active `remote_runner.py` 的 `--runner-root` 指向 `/work/code/<linux_user>/<project-or-repo>/tran_harness/remote-runner` 这类子目录，而预期 `runner_root` 是 `/work/code/<linux_user>/tran_harness/remote-runner`，说明 tmux session 被误装 runner 占用。不要继续投递 build；先停止错误 session，再通过 `bridge-install --remote-workspace /work/code/<linux_user> --force` 或映射根 start 脚本拉起正确 runner，然后重跑 `status/check/system.ping`。
- `bridge-exec` 命令需要用户事先批准，并且 CLI 必须带 `--i-understand-this-runs-raw-shell`；不要静默执行。
- 重复操作应当注册为 action（在 deployed runner 的 `config/actions.local.yaml`），不要把 raw 命令固化在 prompt 里。
- 不要把 harness 源码 / 调试脚本写到 `<mapped_root>/tran_harness/remote-runner`，那里是部署后的运行材料目录。

## 误装清理（具体历史坑，与执行模型无关，必须显式记住）

- **Git Bash MSYS 路径转换**：`--remote-workspace /work/...` 在 Git Bash 下会被 MSYS 转换为 `C:/Program Files/Git/work/...`，CLI 0.1.14+ 已加 `_validate_remote_workspace` 拦截。0.1.14 之前安装过的用户 Linux 机器上可能有错位目录 `~/C:/Program Files/Git/...`，**升级后一次性清理**：
  ```text
  # 检查（bridge READY 后）
  harness --json remote-runner bridge-exec --command "ls -la ~/ | grep -E '^d.*[A-Za-z]:$' || echo 'clean'" --i-understand-this-runs-raw-shell
  harness --json remote-runner bridge-exec --command "find ~/'C:' -maxdepth 6 -type d -name remote-runner 2>/dev/null" --i-understand-this-runs-raw-shell
  # 真删（盘符目录名含冒号必须单引号转义）
  harness --json remote-runner bridge-exec --command "du -sh ~/'C:' 2>/dev/null && rm -rf ~/'C:'" --i-understand-this-runs-raw-shell
  ```
- **`--remote-workspace` 传成了项目子目录**：传 `/work/code/<linux_user>/<project-or-repo>`、具体项目 workspace 或单仓目录时，runner 会落到子目录下，Windows 侧用 `Z:\` 这类映射根就检测不到。正确布局是 **映射根唯一一份** `<mapped_root>\tran_harness\remote-runner`，Linux 侧对应 `/work/code/<linux_user>/tran_harness/remote-runner`：
  ```text
  # Windows 侧识别：discover 返回里哪些 runner_root 含有项目/单仓子目录
  # "<drive>:\<mistaken-subdir>\tran_harness\remote-runner" → 误装
  harness --json remote-runner discover

  # Linux 侧识别（bridge READY 后；$USER 自动取当前账号）
  harness --json remote-runner bridge-exec --command "find /work/code/$USER -mindepth 2 -maxdepth 4 -type d -path '*/tran_harness/remote-runner'" --i-understand-this-runs-raw-shell
  # 出现在 /work/code/$USER/<subdir>/tran_harness/remote-runner 即误装；正确位置只能是 /work/code/$USER/tran_harness/remote-runner
  ```
  确认是误装后清理：
  ```text
  harness --json remote-runner bridge-exec --command "rm -rf /work/code/$USER/<mistaken-subdir>/tran_harness" --i-understand-this-runs-raw-shell
  Remove-Item -Recurse -Force <mapped-root>:\<mistaken-subdir>\tran_harness
  ```
  然后再按正常流程在映射根重装：`harness remote-runner ssh-install --remote-workspace /work/code/<linux_user>`（或 `bridge-install`）。**`remote-workspace` 必须停在用户映射根**，不能进入项目目录，也不能保留尖括号占位符。

## 反馈

```text
harness --json feedback create --scenario remote-runner --problem-type missing-tool-option \
  --tool "harness remote-runner exec" --detail "..."
```
