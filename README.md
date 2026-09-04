# EasyAdapter

传音 Android 底软集成部的 **AI 辅助适配平台**。面向大版本升级，把底软改动从「人工翻代码」变成可追踪的工作台：Agent 做适配与合入，人做审核入库。

日常入口是 Web Console（`tahp-console`）。Windows 双击仓库根目录 [`run_adapter.bat`](run_adapter.bat) 即可拉起服务与托盘。

```
浏览器
  └── EasyAdapter Console  (:8650)
        ├── 适配调试（Agent + Skill）
        ├── Modem 升级（tools/modem-patch-tool）
        └── GKI 升级（tools/gki-patch-tool）
```

---

## 三大核心

首页三张主卡片对应三条主线。任务都是 **自动合入 / 适配 → 人工审核 → 入库**，不自动越过审核门。

| 能力 | Console | 做什么 |
|------|---------|--------|
| [适配调试](#1-适配调试) | `/tahp/adapt-debug`、`/tahp/pipeline` | 把源版本的功能、特性、运营商定制改到目标版本；需要时再串编译、烧录、自检、Gerrit |
| [Modem 升级](#2-modem-升级) | `/tahp/modem-baseline` | AP 基线升级后，Modem 仓 patch 自动合入并提交 |
| [GKI 升级](#3-gki-升级) | `/tahp/gki-patch` | GKI patch 质量分析、选 Tag、合入提交 |

### 1. 适配调试

把 **源版本 → 目标版本** 的底软改动交给 Agent：通信 / 驱动 / 内核等域按表单前置条件改代码，产出修改清单与适配报告。

两条入口，场景不同：

| 入口 | 路由 | 适用 |
|------|------|------|
| **AI 适配调试** | `/tahp/adapt-debug` | 单次、按 JIRA / 需求交互调试。选工作区与业务域，可从中心载入前置，启动后看 Agent 过程与文件改动。完成后到「报告」核对，入库走审核与 Gerrit。 |
| **适配流水线** | `/tahp/pipeline` | 把「选项目 → 拉前置代码 → AI 适配 → 编译 → 烧录 → 自检 → 审核 → 提交 Gerrit」串成可自动流转的工作流。某步没就绪会降成人工门；失败后按界面推荐的恢复点续跑，避免整条重来。 |

流水线只做编排，编译 / 刷机 / 自检复用已有能力。Agent 不可用时适配任务失败，不降级成「BFF 直接调模型」。

报告目录：`reports/adapt-agent/`。

### 2. Modem 升级

TONES / MergeTool 完成 AP 基线升级后，经中心把通知推到本机 Console。**不会自动开合入**。研发在「Modem升级」工作台采用通知、核对仓与项目后，再分阶段执行 `md_merge.sh` 合入；冲突按阶段面板处理；**人工审核通过后入库**。

- 子页：工作台 / 运行历史 / 配置中心
- 也可在工作台手动粘贴通知文本
- 采用后仍待确认；核对并启动后再点「确认完成」才从待办消失
- 实现：`tools/modem-patch-tool/`（由 Console 调用，不依赖本机另装一份工具）

接入说明：[tools/modem-patch-tool/EA_INTEGRATION.md](tools/modem-patch-tool/EA_INTEGRATION.md)

### 3. GKI 升级

同样以 TONES 任务为主。Console「GKI 升级」内嵌 GKI Patch Tool：先分析质量与稳定性、选最优 Tag，再合入提交；crash 走故障诊断。**人工审核通过后入库**。

| 侧栏 | 作用 |
|------|------|
| 工作台 | 外部通知、任务列表、填 Tag 后去分析 / 合入 |
| patch 分析 | 单 SHA 或 tag 区间质量分析 |
| 故障诊断 | 死机日志 → 疑似 patch → 归因 |
| patch 入库 | 合入、冲突 AI、编译验证 |
| 数据库 | 历史 patch |
| 设置 | 环境（集成模式下 LLM / SSH 由 EasyAdapter 一键配置注入） |

首次进入会拉起本机 GKI 服务（默认 `127.0.0.1:8651`）。工具源码在 `tools/gki-patch-tool/`，随 Console 启动，无需再开一份独立进程。

接入说明：[tools/gki-patch-tool/EA_INTEGRATION.md](tools/gki-patch-tool/EA_INTEGRATION.md)

---

## 使用

### Windows（日常）

1. 双击 [`run_adapter.bat`](run_adapter.bat)（检查环境、构建、后台启动、托盘、打开浏览器）
2. 托盘（紫底 EA）：打开控制台 / 重启 / 更新并重启 / 停止
3. 首次使用：Console **配置 → 模型管理** 配 Provider；**配置 → 一键配置** 填域账号、SSH、JIRA 等，保存并启动 Skill 配置检查

开机自启、日志路径见 [`Windows使用说明.txt`](Windows使用说明.txt)。

### 开发模式

```bash
cd tahp-console
npm install
npm run setup
npm run dev          # 前端 :5173，BFF :8650
```

生产：`npm run build && npm run start`。

常用环境变量：`PORT`（默认 8650）、`AUTH_DISABLED=1`（内网免鉴权）、`TAHP_PROJECT_ROOT`（仓库根）、`TAHP_PYTHON`。

---

## 仓库结构（与三大核心相关）

```
easyadapter/
├── run_adapter.bat              Windows 日常启动
├── tahp-console/                Web Console（Vue 3 + Koa BFF）
├── hermes-agent-main/           Hermes Agent（适配调试执行，默认少改）
├── skills/.claude/skills/       业务 Skill 运行时（同步中心落盘，不入库）
├── tools/modem-patch-tool/      Modem 合入工具（EA 集成版）
├── tools/gki-patch-tool/        GKI 分析 / 合入工具（EA 集成版）
├── reports/                     适配等任务报告
├── .tahp/                       本机统一配置（gitignore）
└── AGENTS.md                    研发 / Agent 导航
```

---

## 其它 Console 能力

三大核心之外还有公共能力（智能诊断、质量验测、代码拉取、校准数据）和运营入口（报告、质量评测、Skills、对话搜索）。它们服务主线，不是首页主卡片。完整面板与编码规范见 [AGENTS.md](AGENTS.md)、[tahp-console/DEVELOPMENT.md](tahp-console/DEVELOPMENT.md)。

使用手册：Console **使用手册**（`/tahp/manual`）。

---

## 许可证

`tahp-console` 基于 Hermes Web UI，许可证 [BSL-1.1](tahp-console/LICENSE)。
