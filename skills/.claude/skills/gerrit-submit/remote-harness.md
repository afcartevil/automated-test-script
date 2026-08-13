# Windows 映射盘 → Harness 远程 Git

当目标仓库在映射根（Windows `<mapped_root>\...` ↔ Linux `/work/code/<linux_user>/...`）或本机 git 因 `alternates` / ownership 不可用时，用 harness 在 **Linux 构建机** 上完成 status / diff / commit / push。

**多机兼容铁律：禁止写死盘符、用户名、UNC。** 一律使用当次 `discover` 返回的字段。

## 路径对照（全部来自 discover）

| 概念 | discover 字段 / 推导 | 说明 |
|---|---|---|
| Windows 映射根 | `mapped_root` | 可能是 `Z:\`、`Y:\` 或 `\\host\user` |
| Linux 映射根 | `inferred_remote_workspace` | 形如 `/work/code/<linux_user>`，必须是映射根 |
| runner 根 | `runner_root` 或 `<mapped_root>\tran_harness\remote-runner` | 忽略 `suspicious_runner_root` 候选 |
| 仓库（Win） | `<mapped_root>\<project_path>` | 正反斜杠按本机 |
| 仓库（Linux） | `<linux_root>/<project_path>` | 正斜杠 |
| `project_path` | 相对映射根 | 例：`project/km9/system/vendor/.../MdmConfig` |

从用户给出的 Windows 仓路径推导 `project_path`：

1. 去掉 `mapped_root` 前缀（大小写/尾斜杠不敏感）
2. 把 `\` 换成 `/`，去掉前导 `/`
3. 得到相对路径后再拼 Linux 绝对路径

## 选用哪个 discover 候选

按序：

1. `approved_for_runner == true`（或等价可写映射根）
2. `runner_available == true` 且 **没有** `suspicious_runner_root`
3. `mapped_root` 能覆盖用户仓库路径
4. 记下 `mapped_root` + `inferred_remote_workspace`（= linux_root）

有多个合格候选时优先覆盖用户路径的那个；不要用指向项目子目录的误装 runner。

## Bridge vs Runner（少走弯路）

```text
harness --json remote-runner discover
```

| 情况 | 动作 |
|---|---|
| `runner_available == true` | **直接**用 `remote-runner exec` / skill 脚本；**不要**因 `bridge.ready == false` 先停住空等 |
| runner 不可用，且 `bridge.ready != true` | 提示用户打开 harness 配置中心/托盘连接齐治 Bridge；轮询 discover 或等用户说「已连接」后继续；**不要**自动 `config ui` / `bridge-serve`（除非用户明确要求且无 GUI） |
| bridge READY 但 runner 未起 | `bridge-install --remote-workspace <linux_root> --force`（linux_root 来自 discover，勿写死） |
| exec 失败且日志像 bridge/队列挂死 | 再引导用户检查 Bridge / 重试 discover |

`bridge.ready == false` 但 runner 队列仍可完成 job（常见 shell probe 误超时）→ 以实际 `exec` 成败为准。

## 强制：Windows 安全调用（禁止 PS 内嵌 JSON）

PowerShell 会弄坏 `--args-json '{...}'`。**禁止**在 PS 里手写带花括号的 JSON 参数。

本 skill 自带固定 helper（**不是**每次在映射盘新建的临时脚本）：

```text
<script_dir>/scripts/harness_remote.py
```

`<script_dir>` = 本 `SKILL.md` 所在目录（`.cursor/skills/gerrit-submit` 或仓库内 `skills/.claude/skills/gerrit-submit` 等，以实际加载路径为准）。

### status / diff

```text
python <script_dir>/scripts/harness_remote.py exec ^
  --mapped-root "<mapped_root>" ^
  --action workspace.project_status ^
  --args-json "{\"project_path\":\"<project_path>\"}" ^
  --timeout 120 --read-log
```

同理：`workspace.project_diff_stat` / `workspace.project_diff`。

CLI JSON 常只有 `command completed`；`--read-log` 会打印 `<mapped_root>\tran_harness\remote-runner\logs\` 下本次最新 job log（含真正的 status/diff 正文）。

等价手写（无 helper 时）：用 **Python `subprocess` 传完整 argv 列表**，或 `node <harness.js> ...`，`harness.js` 优先 `%APPDATA%\npm\node_modules\@transsion\harness-cli\bin\harness.js`，可用环境变量 `HARNESS_JS` 覆盖。

## 分支 / remote 只读推断（映射盘文件，不跑本机 git）

优先读仓内 `.git`（或 repo 的 project gitdir）元数据：

1. `refs/remotes/m/master` → 常为 `ref: refs/remotes/<remote>/<branch>`（如 `origin/tOS_mtk_A16_trunk`）
2. `.git/config` → `[remote "<name>"] url=...`（含 `gerrit` / `gerrit-cq`）
3. detached HEAD **不影响** `git push <remote> HEAD:refs/for/<branch>`

站点：`gerrit.transsion.com`（MTK/QCOM）；`gerrit-cq.transsion.com`（SPRD/UNISOC）。

## Commit + push：**不写临时 .sh**

### 默认路径（推荐，多机通用）

1. 按 [commit-template.md](commit-template.md) 在本机拼好 message（可写到 **本机临时文件**，如 `%TEMP%\gerrit_msg.txt`，LF 即可；**不要**为了提交在映射盘写 `*_submit.sh` / `prepare_*.py`）
2. 调用 skill 固定 helper：

```text
python <script_dir>/scripts/harness_remote.py submit ^
  --mapped-root "<mapped_root>" ^
  --linux-root "<inferred_remote_workspace>" ^
  --project-path "<project_path>" ^
  --remote "<remote>" ^
  --branch "<branch>" ^
  --add <file1> --add <file2> ^
  --message-file "%TEMP%\gerrit_msg.txt" ^
  --timeout 300
```

未传 `--add` 时远程执行 `git add -u`（仅已跟踪修改）。

helper 内部会：

- 把 commit message **base64** 嵌进 **临时** `config/actions.local.json` 的 `bash -lc`（**不落盘 .sh**）
- `remote-runner exec --action git.gerrit_submit_once`
- 解析 submit log 中的 Gerrit Change URL / `Change-Id`
- **删除** `actions.local.json`（唯一临时配置；submit log 可留）

### 禁止 / 避免

| 禁止 | 原因 |
|---|---|
| 在映射盘写 `*_submit.sh` / `prepare_and_submit.py` | CRLF 易导致 `set: pipefail`；每台主机重复造轮子 |
| PS 里嵌 `--args-json '{...}'` | 参数被拆坏 |
| 写死 `Z:\`、`/work/code/某用户` | 换主机即失败 |
| 使用 `suspicious_runner_root` 候选 | 误装到项目子目录 |
| 改 `.git/objects/info/alternates` 或 `git config --global safe.directory` | 应用远程路径，不要硬扛本机 git |
| 把密码写进 action / 日志说明 | 安全 |

### 仅当 helper 不可用时的手工兜底

若必须手写：只允许临时 `actions.local.json`，`command` 为 `["bash","-lc","echo <script_b64> | base64 -d | bash"]`，message 同样 base64；**二进制写入 JSON（LF）**；exec 后删除该文件。仍不要创建 `.sh`。

`bridge-exec` 默认短超时，**不作为** commit/push 主路径；仅诊断或经用户批准的 raw shell 逃生口（`--i-understand-this-runs-raw-shell`）。

## 回报解析

从 submit log / job log 提取：

- `https://gerrit.../+/NNNN`（Change URL）
- `Change-Id: I...`
- `remote` → `refs/for/<branch>`
- commit subject / 完整 message 摘要

## 清理清单

每次远程提交结束后确认：

- [ ] `config/actions.local.json` 已删除（或不存在）
- [ ] 映射盘 `tmp/` 下无本次新建的 `*_submit.sh` / `prepare_*.py`
- [ ] 回报里含 Change URL 与 Change-Id
