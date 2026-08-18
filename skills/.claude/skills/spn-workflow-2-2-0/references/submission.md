# Jira 版本、分支与 Gerrit 提交规范

## 目标

确保代码提交到 Jira 问题实际发生的版本分支，而不是根据版本字符串猜分支。

## 分支解析流程

### 1. Jira 版本事实

从 Jira 记录：

- 项目代号；
- affected version / fix version；
- 完整软件版本；
- Android/TOS 大版本；
- trunk/release 等明确描述。

affected version 和 fix version 冲突时不得自行选择。默认修复 affected version 对应维护线；如果 Jira 明确指定 fix version，则以 fix version 为候选并报告差异。

### 2. 项目与分区矩阵

执行：

```text
harness --json project-info search "<project>"
harness --json project-info detail --project <project>
```

记录平台、芯片、`branches_by_partition`、每个 branch 的 `partition`、`branch_kind` 和来源。

### 3. 版本服务

按 Jira 给出的条件查询，不补默认值：

```text
harness --json version-server list-versions --project <project> --version-type <type> --limit 20
```

`version.spug.branch` 只能作为 TOS/系统主分支证据，不能直接套用到 vendor、nonhlos 或 kernel repo。

### 4. 精确分支

执行：

```text
harness --json branch-server info --branch <candidate>
```

核对：

- 精确 branch；
- platform、TOS version；
- parent/upstream manifest；
- branch kind；
- sys/vnd/nonhlos/krn 分区。

### 5. Workspace 一致性

workspace 必须对应 Jira 版本。通过 Harness 的 repo/git 状态能力读取 manifest revision 与 repo project，禁止仅凭目录名判断。

每个待修改 repo 输出：

```text
repo project
partition
workspace revision
project-info candidate
branch-server exact branch
resolution: matched / ambiguous / mismatch
```

只有 `matched` 才允许提交。

## 歧义处理

以下情况必须停止并请用户确认：

- Jira 没有问题版本；
- affected version 与 fix version 指向不同维护线；
- 同时存在 trunk/release；
- 同项目存在 sys/vnd 等多个分区候选；
- workspace manifest 与 Jira 版本不一致；
- 某个 repo project 的 Gerrit branch 不存在；
- 用户希望跨版本回合但未说明目标线。

不得默认选择最新分支、trunk、sys 或当前 checkout。

## 提交计划模板

```markdown
## SPN Gerrit 提交计划

- Jira：<key>
- 问题版本：<version>
- 平台：<MTK/QCOM>
- Workspace：<logical workspace name>

### Repo 1
- Project：<repo project>
- Partition：<sys/vnd/...>
- Target branch：<exact branch>
- Files：<paths>
- Verification：<checks/build>
- Action：create CR / upload patch set

### 风险
- <branch or verification risk>
```

## 提交前自检

- diff 只包含确认过的文件；
- 无嵌套方法、缺失 import、无效空值或错误线程切换；
- Jira 注释格式符合当前仓，start/end 成对；
- SPN、PLMN、displayName、carrierName 和 nameSource 语义未混淆；
- MTK/QCOM 路径未混改；
- 每个 repo 单独提交；
- 编码规范 mandatory 项通过；
- 最小模块编译通过，或已说明无法执行的原因。

## Harness 提交

生成提交说明：

```text
harness --json gerrit commit-message \
  --id <JIRA_KEY> \
  --description "<one-line fix>" \
  --type fix \
  --affect-projects "<projects>" \
  --test-suggestions "<tests>" \
  --affect-platform <platform>
```

首次创建 CR：

```text
harness --json gerrit create \
  --mapped-root <mapped-root> \
  --workspace-path <linux-workspace> \
  --project-path <repo-project> \
  --branch <exact-branch> \
  --message "<generated-message>" \
  --paths <explicit-paths>
```

已有 CR 追加 patch set：

```text
harness --json gerrit upload \
  --mapped-root <mapped-root> \
  --workspace-path <linux-workspace> \
  --project-path <repo-project> \
  --branch <exact-branch> \
  --paths <explicit-paths>
```

`--paths` 必须显式列出文件，禁止传 `.`，除非 Harness 契约和提交计划已证明该 repo 只有目标变更且用户明确确认。

## 输出

提交完成后报告：

- repo project、目标分支和 commit；
- Gerrit CR 链接；
- Change-Id；
- 编译/自检结果；
- 未执行验证；
- 刷机复测步骤。
