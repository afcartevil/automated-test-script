---
name: gerrit-submit
description: >-
  将本地 git 修改按传音研发代码提交规范生成 commit message，并提交到 Gerrit
  （git push <remote> HEAD:refs/for/<branch> 或 repo upload）。remote 名由
  agent 从当前仓库自动解析（upstream / git remote / git branch -a），用户
  无需提供。用户需提供 AR ID/BUG ID；目标分支可多个，未提供则用当前上游
  远程分支。当用户要提交/upload 到 Gerrit、推 refs/for、写规范 commit、
  repo upload 时使用。
---

# Gerrit 本地提交

按 [研发代码提交规范](https://transsioner.feishu.cn/wiki/VMclwfBRxi65BNks0dSc2aGynid) 填模板、本地 commit，再 push 到 Gerrit review 分支。字段细则见 [commit-template.md](commit-template.md)。

与 `harness-gerrit` 的边界：那边只做 CR **查询**；**本 skill 负责按本模板生成 message + 本地 commit + 上传**。不要用 `harness gerrit commit-message` 渲染（扩展字段不同）。

## 必要输入

| 输入 | 是否必须 | 说明 |
|---|---|---|
| **ID**（AR ID 或 BUG ID） | 必须 | 只能是 AR/BUG，禁止 task ID。缺则停止并询问 |
| **目标分支** | 可选 | 可多个。未给 → 当前 `@{upstream}` 的远程分支名 |
| TYPE / AFFECT_PROJECTS / DESCRIPTION / TEST_SUGGESTIONS | 可选 | 未给则根据 diff 推断；AFFECT_PROJECTS 无法推断时再问 |
| 扩展四行（自检/影响项目/影响平台/chery-pick） | 可选 | 未给则用模板默认值；多分支 upload 时 chery-pick 行改为「是」 |

**remote 名不是用户输入。** Agent 必须在当前仓库用 `git remote` / `git branch -vv` / `git branch -a` / `@{upstream}` **自动解析**（`origin`、`48_origin`、`gerrit` 等任意名）。仅在多个候选无法唯一确定时才向用户确认。

## 工作流（复制清单并跟踪）

```
- [ ] 1. 收集 ID；agent 自动解析 remote + 目标分支
- [ ] 2. 检查工作区与 Change-Id hook
- [ ] 3. 分析 diff，填满模板字段
- [ ] 4. 按模板拼接 commit message，向用户展示终稿
- [ ] 5. stage + commit（仅用户已要求提交时）
- [ ] 6. git push <remote> HEAD:refs/for/<branch>（每个目标）
- [ ] 7. 回报 Change URL / 分支结果
```

### 1. 收集 ID；自动解析 remote 与分支

- **无 ID → 停止**，请用户提供 AR ID（如 `AR-202506-002681`）或 Jira BUG ID。
- **不要向用户索要 remote 名**；先跑下面命令自行解析（**禁止写死 `origin`**）：

```bash
git remote -v
git branch -vv
git branch -a
git rev-parse --abbrev-ref @{upstream}   # 有上游时
```

#### 自动解析 remote（优先级从高到低）

1. 当前分支有 upstream → 从 `@{upstream}` 拆出 remote 名（最常见、优先用）。  
   - `origin/master` → remote=`origin`，branch=`master`  
   - `48_origin/SP9832E_1H10_Natv_16B_S1` → remote=`48_origin`，branch=`SP9832E_1H10_Natv_16B_S1`
2. 用户给的目标写成 `remote/branch`（且 `remote` 在 `git remote` 列表中）→ 按 `/` 拆。
3. 用户只给了 branch 名（或未给分支、仅知目标名）→ 在 `git branch -a` 找 `remotes/<remote>/<branch>`：
   - **唯一命中** → 用该 remote，继续，不询问  
   - **多个 remote 同名分支** → 列出候选再问（唯一需要用户介入 remote 的情况）  
   - **零命中** → 若 `git remote` 只有一个 → 用它；若多个但仅一个 URL 含 `gerrit` → 用它；否则列出 `git remote -v` 请用户选一次
4. 用户偶尔主动说了 remote（如「用 48_origin」）→ 覆盖自动结果。

解析成功后直接使用，例如：

```bash
git push 48_origin HEAD:refs/for/SP9832E_1H10_Natv_16B_S1
```

#### 解析目标分支

- 用户给了 → 拆成列表（空格/逗号/`、` 分隔），去重；若带已存在的 `remote/` 前缀则同时锁定 remote。
- 未给 → 用当前 upstream 的分支名（去掉 remote 前缀）。
- 无 upstream 且未给分支 → 停止询问分支名（仍不要先问 remote）。

多目标分支时：**每个分支各自自动解析 remote**；展示终稿时写明 `remote → refs/for/branch` 对照表（告知用户 agent 选了哪个 remote，而不是反过来问 remote）。

### 2. 工作区与 hook

在**实际有改动的 git 仓库根**执行（Android 多仓时对每个要上传的 project 分别做；整树可用 `repo status` 定位）：

```bash
git status
git diff
git diff --cached
git log -5 --oneline
```

- 无改动且无未推送 commit → 停止说明。
- 确认 Gerrit `commit-msg` hook 存在（通常 `.git/hooks/commit-msg`）。缺失时安装后再 commit，否则缺少 `Change-Id:` 会被拒：

```bash
# 示例：从 Gerrit 拉取 hook（按实际站点调整）
scp -p -P 29418 <user>@gerrit.transsion.com:hooks/commit-msg .git/hooks/
```

站点：`gerrit.transsion.com`（MTK/QCOM）；`gerrit-cq.transsion.com`（SPRD/UNISOC）。

**禁止** `git config` 改全局/`commit.template`（除非用户明确要求改配置）。

### 3. 填模板

根据 diff 填写（规则见 [commit-template.md](commit-template.md)）：

1. `ID` = 用户提供的 ID  
2. `DESCRIPTION` = 一句话说明改了什么、为何改  
3. `TYPE` = 枚举之一（`func|fix|opti|port|refactor|revert|patch|apm|conf|test|NativeInssue`）  
4. `AFFECT_PROJECTS` = 项目/平台/`ALL`  
5. `TEST_SUGGESTIONS` = 可执行的测试建议  
6. 扩展四行（默认如下；按实改「是/否」）：

```text
[是否自检]：是
[是否影响其它项目]:否
[是否影响其它平台]:否
[是否chery-pick其它分支]:否
```

不确定 `AFFECT_PROJECTS` 或 `TYPE` 时**先问再提交**，不要猜错触发拦截。

### 4. 拼接并展示终稿

按 [commit-template.md](commit-template.md) **直接拼接**完整 message，**不要**调用 `harness gerrit commit-message`。

**向用户展示完整 message，以及 `remote → refs/for/<branch>` 对照表**；用户未反对且已明确要求「提交/upload」则继续。仅说「帮我写个 commit」时只输出 message，不 push。

### 5. Commit

只用用户要求提交时的改动；勿加入密钥/`.env` 等。

```bash
git add <相关文件>
git commit -m "$(cat <<'EOF'
ID:...
DESCRIPTION:...
TYPE:...
AFFECT_PROJECTS:...
TEST_SUGGESTIONS:...
[是否自检]：是
[是否影响其它项目]:否
[是否影响其它平台]:否
[是否chery-pick其它分支]:否
EOF
)"
```

Windows PowerShell 无 `cat <<EOF` 时，把 message 写入临时文件再 `git commit -F <file>`，用完删除。

验证：`git log -1` 应含规范字段与扩展四行，且 hook 已追加 `Change-Id: I...`。

### 6. 上传 Gerrit

**单仓 git（默认）：** 对每个「remote + 分支」组合（`<remote>` 来自步骤 1，**不是**固定 `origin`）：

```bash
git push <remote> HEAD:refs/for/<branch>
# 例：git push 48_origin HEAD:refs/for/SP9832E_1H10_Natv_16B_S1
```

可选 topic（多分支同一 topic 时）：

```bash
git push <remote> HEAD:refs/for/<branch>%topic=<topic>
```

**Android `repo` 工作区：** 若用户在 repo 根且改动跨多 project，用：

```bash
repo upload [<project>...] --cbr -y
# 或指定分支：repo upload -b <branch> ...
```

以当前环境惯用方式为准；`repo upload` 不可用时退回各 project 内 `git push <remote> HEAD:refs/for/<branch>`。

多分支 = **同一 commit 分别 push 到多个 `refs/for/<branch>`**（remote 按各自分支解析），不要为每个分支重写无关 commit，除非用户要求 cherry-pick。多分支 upload 时把 `[是否chery-pick其它分支]` 设为 `是`。

### 7. 回报

每个目标报告：`remote`、分支、成功/失败、Gerrit Change URL（若输出中有）、`Change-Id`、最终 commit message 摘要。任一分支出错 → 继续其余，最后汇总失败项与重试命令（含正确的 `<remote>`）。

## 安全与边界

- **仅在用户明确要求提交/upload/推 Gerrit 时**执行 commit 与 push。
- 不 `push --force`、不改已合并的 Change（更新同一 Change 靠同一 `Change-Id` 再 push）。
- 不跳过 hooks（`--no-verify`），除非用户明确要求。
- 不在回复中回显 Gerrit 密码 / LDAP / token。
- 远程 runner / 堡垒机场景若禁止手拼 push，改走已放行的 harness/remote-runner 流程，并告知用户。

## 异常引导

| 现象 | 处理 |
|---|---|
| 缺少 ID | 停止，请提供 AR/BUG ID |
| 无 upstream 且未给分支 | 停止，请提供目标分支 |
| remote 歧义（同名分支在多个 remote，且无法用 upstream/唯一 gerrit URL 判定） | 列出 `git branch -a` / `git remote -v` 候选，请用户选一次；平时不要主动问 remote |
| 推错 remote / `repository not found` | 用 `git remote -v` 核对 URL，改用正确 remote 重试 |
| 缺少 Change-Id | 安装 `commit-msg` hook 后 `git commit --amend`（仅限本 skill 刚创建且未 push 的 commit）或新建 commit |
| TYPE/字段被拦截 | 对照 [commit-template.md](commit-template.md) 修正后同一 Change-Id 再 push |
| 认证失败 | 检查该 `<remote>` 的 URL、ssh key / HTTP 凭据；MTK/QCOM vs CQ 站点是否搞错 |
| 非 fast-forward / 依赖旧 patch | `git fetch <remote>` 后 rebase 再 upload，勿 force push 到 `refs/for/*` 以外的方式 |

## 依赖

- 本地 `git`；可选 `repo`
- 已配置到公司 Gerrit 的 remote 与 hook
- **不依赖** `harness gerrit commit-message`
