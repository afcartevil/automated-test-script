---
name: transsion-harness
description: 传音 Android / 整机 / 组件 / 应用仓内的开发任务总入口 skill。把模糊问题路由到 harness-* 子 skill：知识查询走 harness-knowledge；整机版本路径走 harness-version-server；rdtool / native Android 编译走 harness-build；本地刷机 / 设备冒烟 / APK 签名走 harness-device；remote runner / 齐治 bridge 走 harness-runner；OpenGrok 源码取证走 harness-opengrok；Jira issue 读取/搜索走 harness-jira；Gerrit CR 查询/文件列表/提交说明模板走 harness-gerrit；MTK 自动提单 / sync / pipeline 走 harness-mtk-auto-cr；安装诊断 / 配置 / 反馈走 harness-install。
version: 2.1.17
---

# Transsion Harness 路由总入口

把 Harness CLI 当作传音开发任务的执行入口。任何子任务都先映射到一个领域子 skill，然后在子 skill 内优先执行结构化 CLI。

## 调用契约

本环境中每一次 Harness CLI 调用都必须使用下面的完整前缀：

```text
harness
```

示例写成 `harness doctor` 时保留整个前缀；为了便于 Agent 解析，优先在前缀后立即插入 `--json`：

```text
harness --json doctor
```

## 子 skill 路由表

版本类型速记：`TEST`, `DEV`, `KOM`, `ASAN`；variant 速记：`user`, `userdebug`, `eng`。

| 场景 | 子 skill | 触发关键词 |
|---|---|---|
| 知识查询、领域路由、问题诊断 | harness-knowledge | route、search、symptom、知识、领域 |
| 整机版本路径、`.pipe/pack.json` | harness-version-server | 转测、TEST、DEV、find-latest、pack.json |
| 编译场景路由 | harness-build | build、setup、repo、tran_build、Android.bp |
| 整机拉代码、rdtool workspace、分区组件编译 | harness-build-whole-device | 拉代码、整机、rdtool、pack.json、batch-repo、batch-build |
| native Android 模块编译 | harness-build-native | tran_build、Android.bp、Android.mk、TeleService、framework jar、APK |
| 本地刷机、设备冒烟、APK 签名 | harness-device | flash、smoke、remount、probe、adb、fastboot、online sign |
| remote runner、齐治 bridge | harness-runner | runner、bridge、qizhi、Linux workspace、mapped-root |
| OpenGrok 源码搜索 | harness-opengrok | opengrok、源码、cross-reference |
| Jira issue 读取/搜索 | harness-jira | jira、Jira URL、issue、JQL、USICPRO |
| Gerrit CR 查询/提交说明 | harness-gerrit | gerrit、CR、Code-Review、repo upload、Change-Id |
| MTK CR 自动提单、sync、pipeline、offer | harness-mtk-auto-cr | MTK CR、自动提单、sync、链接触发、eService |
| 安装、诊断、配置、版本发现、反馈 | harness-install | install、doctor、version check、config、feedback |

## CLI-first 路由原则

用户已经明确要做版本查询、编译、刷机/设备、runner/齐治、OpenGrok、Jira issue 查询/搜索、Gerrit CR 查询/提交说明、MTK 自动提单、安装诊断或配置时，**直接进入对应子 skill 并调用 CLI**，不要先查知识库。知识库只用于下面三类情况：

- 你无法判断该进哪个子 skill；
- CLI 参数契约不覆盖用户需求，或命令返回的错误需要 SOP/规则解释；
- 用户明确要求查知识、规则、背景或领域经验。

只有真正模糊任务时才跑：

```text
harness --json knowledge route "<用户问题>"
```

`recommended_skill` 字段会直接告诉你跳哪个子 skill。

## Shortcut 速查

常用自然语言入口可以先用 shortcut，再由 CLI 薄重写到结构化命令：

```text
harness --json +latest <project>
harness --json +route "<query>"
```

- `+latest` 等价于 `version-server find-latest --version-type TEST --variant userdebug`，用于默认查最新转测 userdebug 版本。
- `+route` 等价于 `knowledge route "<query>"`，只用于无法直接判断领域时先拿 `recommended_skill` 再跳到对应 harness-* 子 skill。

## 命令契约自查

子 skill 速查不够 / 不确定参数时，先用：

```text
harness --json commands describe <command path>
```

例如 `harness --json commands describe build build` 拿到完整 args / required / choices / default / examples。Agent **不要凭记忆猜参数**。

## 边界

- Harness 工具运行在开发者自己的电脑上。`<mapped-root>` 类路径指映射的 Linux workspace，不是 harness 源码仓。
- 不要要求用户把 AGENTS.md、docs、skills 或知识文件放进业务仓。
- 不要绕过 `schemas/`、CLI 参数契约或 runner action 白名单。
- 保持证据可追溯：总结中保留 `trace_id`、runner 路径、日志路径、commit ID 和验证输出。

## 反馈

当问题暴露未来产品需要沉淀的能力时，使用：

```text
harness --json feedback submit --scenario <场景> --problem-type <类型> --title <短标题> --detail <详细描述>
```

不要在反馈正文中包含 token、webhook URL、设备 SN 或完整私有路径。
