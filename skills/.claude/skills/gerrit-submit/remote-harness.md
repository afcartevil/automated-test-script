# Windows 映射盘 → Harness 远程 Git

当目标仓库在映射根（Windows `Z:\...` ↔ Linux `/work/code/<user>/...`）或本机 git 因 `alternates` / ownership 不可用时，用 harness 在 **Linux 构建机** 上完成 status / diff / commit / push。

## 路径对照

| 侧 | 示例 |
|---|---|
| Windows 映射根 | `Z:\`（`harness remote-runner discover` 的 `mapped_root`） |
| Linux 映射根 | `/work/code/<linux_user>`（必须是映射根，不能深到项目子目录） |
| 仓库（Win） | `Z:\project\km9\system\vendor\mediatek\proprietary\packages\apps\Email` |
| 仓库（Linux） | `/work/code/<linux_user>/project/km9/system/vendor/mediatek\proprietary\packages\apps\Email` |
| runner 根 | `<mapped_root>\tran_harness\remote-runner` |

`project_path`（传给 workspace.* action）相对 **Linux 映射根**，例如：

`project/km9/system/vendor/mediatek/proprietary/packages/apps/Email`

## 桥接未就绪

```text
harness --json remote-runner discover
```

若 `bridge.ready` 不为 true：

1. 提示用户在本机打开 harness **配置中心 / 托盘** 连接齐治 Bridge（Agent **不要**自动 `harness config ui` 或 `bridge-serve`，除非用户明确要求且无 GUI 才用终端 `bridge-serve`）。
2. 轮询 `discover`（例如每 15–30s）或等用户说「好了」后再 `discover`。
3. `bridge.ready: true` 后继续；若 runner 未起来：  
   `harness --json remote-runner bridge-install --remote-workspace /work/code/<linux_user> --force`

## 只读：status / diff

已注册 action（`remote-runner exec`）：

- `workspace.project_status` — args: `{"project_path":"<rel>"}`
- `workspace.project_diff_stat` — 同上
- `workspace.project_diff` — 同上

CLI 摘要常只有 `command completed`；到映射盘读日志：

`<mapped_root>\tran_harness\remote-runner\logs\<job_id>.log`

## PowerShell 传参

`--args-json '{"project_path":"..."}'` 在 PowerShell 下常被解析坏（`Expecting property name...`）。用 Node 直调：

```text
node %APPDATA%\npm\node_modules\@transsion\harness-cli\bin\harness.js --json remote-runner exec --mapped-root Z:\ --action workspace.project_status --args-json "{\"project_path\":\"project/.../Email\"}" --timeout 120
```

或 Python `subprocess.run([...], ...)` 传入完整 argv。

## Commit + push（推荐临时 action）

1. 在 `<mapped_root>\tran_harness\remote-runner\tmp\` 写入：
   - `*_commit_msg.txt`（LF、UTF-8 无 BOM）
   - `*_submit.sh`：`cd` 到 Linux 仓路径 → `git add` → `git commit -F msg` → `git push <remote> HEAD:refs/for/<branch>`，stdout/stderr 写入同目录 `*_submit.log`
2. 写入 `config/actions.local.json`，例如：

```json
{
  "schema_version": 1,
  "actions": [
    {
      "action_id": "git.gerrit_submit_once",
      "enabled": true,
      "cwd": ".",
      "command": ["bash", "tran_harness/remote-runner/tmp/<script>.sh"],
      "timeout_sec": 300,
      "allow_args": false,
      "arg_schema": {},
      "env_allowlist": []
    }
  ]
}
```

3. 稍等 runner 重载配置后：  
   `remote-runner exec --action git.gerrit_submit_once --timeout 300`
4. 读 `*_submit.log` 取 Change URL / Change-Id
5. **删除** `actions.local.json` 与临时脚本（日志可留可删）

`bridge-exec` 默认约 10s 超时，不适合直接跑 `git push`；若用，需 `nohup`/后台 + 读日志，并带 `--i-understand-this-runs-raw-shell`。

## 分支线索（远程仓只读文件）

本机读映射盘 `.git` 元数据辅助推断（即使 objects 不可用）：

- `refs/remotes/m/master` → 常指向 `refs/remotes/origin/<manifest-branch>`（如 `tOS_mtk_A16_trunk`）
- `.git/config` → `[remote "..."]` URL（含 `gerrit` / `gerrit-cq`）
- detached HEAD 仍可 `git push <remote> HEAD:refs/for/<branch>`

## 禁止

- 为修本机 git 而移动/删除 `objects/info/alternates`（除非用户明确批准且无更好路径）
- `git config --global` 改 `safe.directory` / `commit.template`
- 把密码写进临时脚本或 action 文件
- 使用 `suspicious_runner_root` 指向项目子目录的 runner
