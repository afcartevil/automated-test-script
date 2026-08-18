# SPN Workflow 使用文档

## 能力范围

`spn-workflow` 用于处理 Android 运营商名称相关问题，覆盖：

- 状态栏、锁屏、通知栏显示错误；
- 手动搜网显示 MCC+MNC 或错误运营商；
- SIM 名称、Subscription displayName/nameSource 异常；
- MVNO、子品牌和云网 SPN；
- MTK/QCOM SPN 移植、注入和配置问题；
- 从 Jira、日志分析到代码 diff、验证和 Gerrit 提交。

工作流参考 carrierconfig 的方式，将分析、改码和提交放在一个受门禁控制的入口中。

## 使用前准备

1. Harness 已安装并完成 Jira、Gerrit、Spug/Project Info 配置。
2. 提供 Jira key 或 URL。
3. 提供完整复现日志的文件或目录。
4. 需要改码时，准备与 Jira 问题版本对应的源码 workspace。
5. 需要提交时，remote-runner 可用。

环境诊断：

```text
harness --json doctor
harness --json remote-runner discover
```

## CLI 接入（Harness knowledge route）

`spn-workflow` 已接入 Harness CLI 知识路由，路径 `connectivity/sub/spn`：

```text
# 浏览 SPN 工作流场景（SkillHub 发布后生效；本地调试见下）
harness --json knowledge route --path connectivity/sub/spn

# 读取 workflow 编排（本地 knowledge pack 立即可用）
harness --json knowledge read connectivity/sub/spn/workflow.yaml --source local

# SkillHub 上传前门禁
harness --json skillhub gate D:\Users\jie.wang15\.cursor\skills\spn-workflow --namespace team-com-dev --slug spn-workflow
```

四个 CLI 场景：`spn-workflow-intake` / `spn-workflow-analysis` / `spn-workflow-patch` / `spn-workflow-submit`，对应状态机各阶段与 `workflow.yaml` 中的 Harness 命令映射。

## 推荐提问方式

只分析：

```text
分析 TOS170-9761 的 SPN 显示问题，日志目录是 <log-path>。
```

分析并生成修改：

```text
分析 TOS170-9761，日志在 <log-path>。确认根因后，在对应版本 workspace 生成修复 diff，不要提交。
```

确认 diff 后提交：

```text
diff 已确认。根据 Jira 问题版本解析各 repo 的目标分支，完成自检和模块编译，展示提交计划后提交 Gerrit。
```

追加 patch set：

```text
按新的复测日志修正现有 SPN CR <gerrit-url>，先展示 diff，确认后追加 patch set。
```

## 标准执行结果

### 1. 分析阶段

输出应包含：

- Jira 摘要和问题版本；
- MTK/QCOM 判定依据；
- SIM MCCMNC、驻网 MCCMNC、EF_SPN、NITZ/EONS；
- 从 SIM 初始化到 UI 显示的时间线；
- 链路断点、根因及置信度；
- 精确修复落点和复测建议。

### 2. 修改阶段

输出应包含：

- 每个 repo project 的修改文件；
- diff/stat；
- 每处改动与根因的对应关系；
- 编码规范检查结果；
- 风险和回归范围。

该阶段不会自动 commit 或 push。

### 3. 提交阶段

只有用户确认 diff 后才进入：

- 根据 Jira 问题版本查询项目和分支事实；
- 对照 workspace manifest，逐 repo 确认 Gerrit 目标分支；
- 运行最小自检和可执行的模块编译；
- 展示最终提交计划；
- 用户确认后，通过 Harness 创建或更新 Gerrit CR。

## 分支解析说明

Jira 版本名、TOS 主分支和 Gerrit repo 分支不是同一个概念。

工作流不会把 `LK7k-17.0.0.xxx` 直接拼成分支，而是依次核对：

1. Jira 问题版本；
2. `project-info detail` 项目平台和分区分支；
3. `version-server` 中该版本的主分支事实；
4. `branch-server info` 的精确分支及父分支；
5. 当前 workspace manifest 中每个 repo 的 revision。

存在多个候选时必须由用户确认，不自动选择 trunk、release、sys 或 vnd。

## 安全约束

- 日志和 Jira 附件只读。
- 分析不自动改码。
- diff 未确认不提交。
- 不使用 `git add .`。
- 不手拼 Gerrit push 命令。
- 每个 git project 独立 CR。
- 不把账号、token、设备 SN 或个人绝对路径写入报告和提交说明。

## 常见阻塞

- Jira 无版本字段：可以完成分析；提交前需要用户确认版本。
- 日志无法识别平台：补充 `properties` 或包含 RIL/SST 的 radio 日志。
- workspace 与 Jira 版本不一致：停止改码/提交，先切换正确 workspace。
- remote-runner 不可用：可以输出分析和修改建议，不能声称已生成远端 diff。
- SkillHub 未认证：不影响本地使用；公共发布前需配置 SkillHub token。
