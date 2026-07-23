---
name: gerrit-submit
description: >-
  将 git 修改按传音研发代码提交规范生成 commit message，并提交到 Gerrit
  （git push <remote> HEAD:refs/for/<branch> 或 repo upload）。Windows/映射盘
  上 git 不可用时，自动改走 harness remote-runner 在 Linux 构建机完成
  status/diff/commit/push；用 skill 自带 scripts/harness_remote.py，不在映射盘
  创建临时 .sh/prepare 脚本；路径全部来自 discover，兼容任意 Windows 主机。
  remote 与目标分支由 agent 自动解析；用户已要求提交时，不因缺分支、Jira
  与 diff 不匹配、改动风险等向用户二次确认。当用户要提交/upload 到 Gerrit、
  推 refs/for、写规范 commit、repo upload 时使用。
---

# Gerrit 本地 / 远程提交

按 [研发代码提交规范](https://transsioner.feishu.cn/wiki/VMclwfBRxi65BNks0dSc2aGynid) 填模板、commit，再 push 到 Gerrit review 分支。字段细则见 [commit-template.md](commit-template.md)。Windows/映射盘远程执行细节见 [remote-harness.md](remote-harness.md)。

与 `harness-gerrit` 的边界：那边只做 CR **查询**；**本 skill 负责按本模板生成 message + commit + 上传**。不要用 `harness gerrit commit-message` 渲染（扩展字段不同）。

## 必要输入与「不打断」原则

| 输入 | 是否必须 | 说明 |
|---|---|---|
| **ID**（AR ID 或 BUG ID） | 必须 | 只能是 AR/BUG，禁止 task ID。**仅缺 ID 时停止并询问** |
| **目标分支** | 可选 | 未给 → 自动推断（见下）；**禁止**因缺分支向用户确认后停住 |
| TYPE / AFFECT_PROJECTS / DESCRIPTION / TEST_SUGGESTIONS | 可选 | 未给则根据 **实际 diff** 推断并落盘；推断不出时用安全默认值（见步骤 3），**禁止**停下来问 |
| 扩展四行 | 可选 | 默认值见模板；多分支 upload 时 chery-pick 行改为「是」 |

**用户已明确要求「提交 / upload / 推 Gerrit」时，以下情况一律继续完成，不得二次确认、不得停任务：**

1. **用户未给出远程目标分支** — 自行解析后直接 push。
2. **Jira/AR 描述与本地改动不匹配** — `ID` 仍用用户给的；`DESCRIPTION` / `TYPE` / `TEST_SUGGESTIONS` **以实际 diff 为准** 填写；可在最终回报里一句带过「单号描述与 diff 不一致」，但**不要**因此拦提交。
3. **改动可能有风险**（误删、半截注释、看起来无关的文件等）— 照样 commit + upload；仅在最终回报中如实摘要 diff，**不要**征求「是否仍要提交」。

**remote 名不是用户输入。** 从仓库自动解析；仅当多个 remote 对同一分支名且无法用 upstream / 唯一 gerrit URL 判定时，才问一次 remote（这是唯一允许因 remote 询问的情况）。

## 工作流（复制清单并跟踪）

```
- [ ] 1. 收集 ID；判定执行环境（本机 git vs harness 远程）
- [ ] 2. 若需远程：discover → 选 approved mapped_root；runner 可用则继续（勿因 bridge 探针误报空等）
- [ ] 3. 解析 remote + 目标分支；拉 status/diff（远程用 harness_remote.py exec --read-log）
- [ ] 4. 按 diff 填模板并拼接 message（可展示，不阻塞）
- [ ] 5. stage + commit + push（本机 git，或 harness_remote.py submit；禁止映射盘临时 .sh）
- [ ] 6. 回报 Change URL / Change-Id / 分支；确认 actions.local.json 已清理
```

### 1. 收集 ID；判定执行环境

- **无 ID → 停止**，请用户提供 AR ID（如 `AR-202506-002681`）或 Jira BUG ID。
- 在目标仓库根探测本机 git 是否可用：

```bash
git -c safe.directory=* status
git -c safe.directory=* rev-parse --is-inside-work-tree
```

**改走 harness 远程**（满足任一即切换，细节见 [remote-harness.md](remote-harness.md)）：

- 路径落在映射盘 / UNC 共享，且对应 Linux `/work/code/<user>/...`
- `dubious ownership` / `bad object HEAD` / `unable to normalize alternate object path`（常见 `/opt/git/mirror/...`）
- 本机 `git status` / `diff` / `commit` / `push` 失败或明显不可用
- 用户明确要求用 harness / 远程服务器操作 git

本机可用则优先本机；远程路径下的读写与 commit/push **全部在 Linux 侧完成**，不要在 Windows 上改 `.git/objects/info/alternates` 或 `git config --global safe.directory` 硬扛。

### 2. Harness 远程与桥接（仅远程模式）

按 [remote-harness.md](remote-harness.md) 执行，摘要：

1. `harness --json remote-runner discover`
2. 选用 **approved / 非 suspicious** 候选；记录 `mapped_root`、`inferred_remote_workspace`（**禁止写死**）
3. **`runner_available == true` → 直接继续** status/diff/submit；不要只因 `bridge.ready != true` 停住
4. runner 不可用且 bridge 未 READY → 提示用户连齐治 Bridge，轮询/等待后自动继续原任务（不要问「还要不要提交」）
5. bridge READY 但 runner 未起 → `bridge-install --remote-workspace <linux_root> --force`
6. **一律**用本 skill 的 `scripts/harness_remote.py`（或 Python `subprocess` argv）调用 harness；**禁止** PowerShell 内嵌 `--args-json '{...}'`
7. **禁止**在映射盘创建 `*_submit.sh` / `prepare_*.py`；提交用 `harness_remote.py submit`

### 3. 解析 remote / 分支；工作区与 hook

**不要向用户索要 remote 名**；自行解析（**禁止写死 `origin`**）：

本机模式：

```bash
git remote -v
git branch -vv
git branch -a
git rev-parse --abbrev-ref @{upstream}   # 有上游时
```

远程模式：优先读映射盘 `.git` 元数据（见 remote-harness.md），再用 `workspace.project_status` / `project_diff`。

#### 自动解析 remote（优先级从高到低）

1. 当前分支有 upstream → 从 `@{upstream}` 拆出 remote 名  
   - `origin/master` → remote=`origin`，branch=`master`  
   - `48_origin/SP9832E_1H10_Natv_16B_S1` → remote=`48_origin`，branch=`SP9832E_1H10_Natv_16B_S1`
2. 用户给的目标写成 `remote/branch`（且 `remote` 在 `git remote` 列表中）→ 按 `/` 拆
3. 用户只给了 branch 名（或未给）→ 在 `git branch -a` 找 `remotes/<remote>/<branch>`：
   - **唯一命中** → 用该 remote  
   - **多个 remote 同名分支** → 列候选再问（唯一需要用户介入 remote 的情况）  
   - **零命中** → 仅一个 remote，或仅一个 URL 含 `gerrit` → 用它；否则再问 remote
4. 用户主动说了 remote → 覆盖自动结果

#### 解析目标分支（未给也不要停）

按优先级自动选，**选中即用，不询问**：

1. 用户给出的分支列表（空格/逗号/`、` 分隔）
2. `@{upstream}` 的远程分支名（去掉 remote 前缀）
3. repo 工作区：`refs/remotes/m/master` 解出的跟踪分支（常为 `origin/<manifest-branch>`）
4. `.git/refs/remotes/origin/HEAD`、当前检出分支名、最近一次成功 fetch 的相关分支
5. 仍无法判定 → 优先含 `trunk` / `master` / manifest revision 的 gerrit 远程分支；再不行用 `master`

多目标时每个分支各自解析 remote；回报时写明 `remote → refs/for/<branch>`。

#### 工作区

本机：

```bash
git status
git diff
git diff --cached
git log -5 --oneline
```

远程：`harness_remote.py exec ... workspace.project_status|project_diff --read-log`。

- 无改动且无未推送 commit → 停止说明（这是无事可做，不是「确认类」打断）
- 确认 `commit-msg` hook；缺失则在 **Linux 仓**安装后再 commit：

```bash
scp -p -P 29418 <user>@gerrit.transsion.com:hooks/commit-msg .git/hooks/
```

站点：`gerrit.transsion.com`（MTK/QCOM）；`gerrit-cq.transsion.com`（SPRD/UNISOC）。

**禁止** `git config` 改全局/`commit.template`（除非用户明确要求）。

### 4. 填模板并展示终稿（不阻塞）

根据 **实际 diff** 填写（规则见 [commit-template.md](commit-template.md)）：

1. `ID` = 用户提供的 ID（与 Jira 摘要是否匹配无关）
2. `DESCRIPTION` = 一句话说明 **diff 实际改了什么**（不要编造与 diff 无关的 Jira 故事）
3. `TYPE` = 枚举之一；吃不准时：修 bug 倾向 `fix`，注释/结构整理 `refactor`，纯配置 `conf`，新功能 `func`
4. `AFFECT_PROJECTS` = 从路径/仓名/Jira 项目 key 推断；仍不行用 `ALL`
5. `TEST_SUGGESTIONS` = 可执行检查点；可简短但不要空
6. 扩展四行默认：

```text
[是否自检]：是
[是否影响其它项目]:否
[是否影响其它平台]:否
[是否chery-pick其它分支]:否
```

按模板**直接拼接** message。可向用户展示终稿与 `remote → refs/for/<branch>`，但用户已要求提交时 **展示后立即 commit/push**，不要等待「确认 / 没反对」。仅当用户只说「帮我写个 commit / 生成 message」时才只输出 message、不 push。

### 5. Commit + 上传

只用本次要上传的改动；勿加入密钥/`.env` 等。

**本机：**

```bash
git add <相关文件>
git commit -F <msgfile>   # 优先 -F；避免 PS heredoc
git push <remote> HEAD:refs/for/<branch>
```

验证：`git log -1` 含规范字段、扩展四行，且 hook 已追加 `Change-Id: I...`。

**远程（映射盘）：** 使用 skill 自带 helper，**不要**在映射盘写临时 shell：

```text
python <skill_dir>/scripts/harness_remote.py submit \
  --mapped-root "<from discover>" \
  --linux-root "<inferred_remote_workspace>" \
  --project-path "<rel path>" \
  --remote "<remote>" \
  --branch "<branch>" \
  --add <file> \
  --message-file <local-msg.txt>
```

细节与多机路径规则见 [remote-harness.md](remote-harness.md)。

可选：`%topic=<topic>`。Android 多 project 可用 `repo upload ... --cbr -y`；不可用则各仓分别 push。

多分支 = 同一 commit 分别 push；此时 `[是否chery-pick其它分支]` 为「是」。

### 6. 回报

每个目标报告：执行环境（本机 / harness）、`mapped_root`（若远程）、`remote`、分支、成功/失败、Gerrit Change URL、`Change-Id`、message 摘要。若 Jira 与 diff 不一致或 diff 看起来有风险，**仅在回报中注明**，不要回滚已成功的 upload。任一分支出错 → 继续其余，最后汇总失败与重试命令。

确认临时 `actions.local.json` 已删除；映射盘无本次 `*_submit.sh`。

## 安全与边界

- **仅在用户明确要求提交/upload/推 Gerrit 时**执行 commit 与 push。
- 不 `push --force`；不跳过 hooks（除非用户明确要求 `--no-verify`）。
- 不在回复中回显 Gerrit / LDAP / 齐治密码。
- 不擅自改全局 git config；不删生产 mirror；临时 action 用完即清。
- 不在映射盘落临时 `.sh` / `prepare_*.py`；只用 skill 内固定 `scripts/harness_remote.py`。
- `bridge-exec` 为 raw shell 逃生口：带 `--i-understand-this-runs-raw-shell`；commit/push 主路径走 remote-runner + helper。

## 异常引导

| 现象 | 处理 |
|---|---|
| 缺少 ID | 停止，请提供 AR/BUG ID |
| 本机 git 坏 / 映射盘 | 切 harness 远程；`runner_available` 则继续；仅 runner 不可用且 bridge 未就绪时引导并等待 |
| 无 upstream 且未给分支 | **自动推断**（步骤 3），不要停问 |
| Jira 与 diff 不符 / 改动有风险 | **继续提交**；回报里说明 |
| remote 歧义 | 列候选问一次 remote |
| 缺少 Change-Id | 装 hook 后 amend（仅限本 skill 刚创建且未 push）或新 commit |
| TYPE/字段被拦截 | 对照模板改 message 后同一 Change-Id 再 push |
| 认证失败 | 核 remote URL / ssh；MTK 主站 vs CQ 站 |
| PS 弄坏 args-json / CRLF 弄挂 bash | 改用 `scripts/harness_remote.py`；不要手写映射盘 `.sh` |
| 非 fast-forward | `fetch` + rebase 再 upload，勿对非 `refs/for/*` force push |

## 依赖

- 本机：`git`；可选 `repo`；远程另需 `python` + `node` + `@transsion/harness-cli`
- 远程：齐治 Bridge（runner 拉起/恢复时）、remote-runner；可读 [harness-runner](../harness-runner/SKILL.md)（若本机 skills 树中有）
- **不依赖** `harness gerrit commit-message`
- 固定脚本：`scripts/harness_remote.py`（随 skill 分发；可设 `HARNESS_JS` 指向 harness.js）
