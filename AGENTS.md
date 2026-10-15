# TAHP / EasyAdapter — Agent 指南

> 生产路径：**tahp-console (BFF) → Hermes Agent → skills/**。日常入口 `run_adapter.bat`（Windows）。根 README 面向使用者，本文件面向改代码的 Agent。

## 强制规则（改代码前必读）

`.cursor/rules/` 是仓库编码规范，OpenCode 不会自动加载，须手动阅读对应文件：

| 规则 | 何时必读 |
|------|----------|
| `00-change-control.mdc` | **任何改动前**：声明功能域、预估改动文件（≤8，超出须说明理由）、敏感链检查 |
| `tahp-verify-commit.mdc` | 验证命令、提交与 MR 规范（始终生效） |
| `tahp-console-dev.mdc` | 改 `tahp-console/**` |
| `tahp-paths-config.mdc` | 改 `paths.ts` / `jira-workspace.ts` / `unified-config.ts` / `agent-bridge/**` / Skill 路径 |
| `tahp-skills-hermes.mdc` | 改 `skills/.claude/skills/**` |
| `tahp-self-check.mdc` | 改 AI 自检（另须读 `.cursor/skills/device-self-check/`） |

提交纪律：**仅当用户明确要求才 `git commit`**；MR 用模板 `.gitlab/merge_request_templates/Default.md`，默认目标分支 `master`。

## 结构与禁区

```
tahp-console/                    Web 控制台（Vue3 客户端 packages/client/src + Koa BFF packages/server/src）
  server/src/services/tahp/      ← TAHP 业务逻辑；services/hermes/ ← Hermes Agent 桥
  tests/                         ← Vitest 用例（tests/**/*.test.ts，分 client/server/shared/e2e）
hermes-agent-main/               Hermes Agent 运行时（默认禁止改，除非任务明确指派）
skills/.claude/skills/           业务 Skill 运行时（gitignore；分发只走 Console 同步中心，禁止 git 提交/拉取）
.cursor/skills/                  开发期 Skill（改 Console/自检代码时参考，不进生产加载路径）
tools/                           modem-patch-tool / gki-patch-tool（EA 集成版，由 Console 调用，勿另起独立进程）
knowledge-base/                  知识库（.kb-data/ 索引 JSON 禁止手改）
jira_workspace/  reports/  .tahp/  .tahp-config/  docs/   ← 全部 gitignore，勿提交
```

Skill 存在**双副本**：仓库 `skills/.claude/skills/` 与 `%LOCALAPPDATA%\hermes\skills/`（BFF 负责同步；路径排障见下）。

## 验证命令（均在 `tahp-console/` 下）

```bash
npm install && npm run setup     # 首次，或 Python/venv 变更后
npm test                         # Vitest 全量
npm test -- tests/server/device-self-check   # 单目录/单文件（路径过滤）
npm run build                    # vue-tsc + vite build + server tsc --noEmit + 打包；改 TS/路由/构建链必跑
npm run dev                      # client :5173，BFF :8650
```

- 广域改动再加：`npm run test:coverage`、`npm run test:e2e`（Playwright，mock BFF）。
- CI（`.github/workflows/ci.yml`，Node 20）只跑 `npm test` + `npm run eval:retrieval:ci`（检索评测门禁），**不跑 build** — build 是本地门禁。
- 可选 pre-commit：`powershell -File scripts/pre-commit-check.ps1`。

## 环境要点

- Node ≥ 20；Windows 需 Git Bash（Hermes 终端工具依赖，`run_adapter.bat` 会检查）。
- `run_adapter.bat` 启动顺序：`git-pull-safe.mjs`（自动检查更新）→ preflight → 装依赖 → Hermes/Skill/GKI 依赖 → build → 托盘。
- 常用环境变量：`TAHP_PROJECT_ROOT`（工程根）、`TAHP_PYTHON`、`PORT`（默认 8650）、`AUTH_DISABLED=1`（内网免鉴权）。
- GKI 服务由 Console 首次进入时拉起（`127.0.0.1:8651`），随 Console 生命周期。

## 业务模块

telephony / kernel-driver / power-mgmt / shared，权威常量在 `packages/server/src/services/tahp/constants.ts`。改模块列表须同步多处映射（`routes/tahp/knowledge.ts`、`services/tahp/bug-analysis.ts` 等，grep 模块名可见全部消费点）。

## 质量验测测试大类（self-check）

str4 / week / monkey / monkey_check / smoke / ota_upgrade / alarm / gms / power / power_feature / thermal / kernel_feature / pipeline_adapt / bitflip / ai_generated。权威注册点：BFF `device-self-check.ts`（`StandardTestType`、`TEST_TYPE_LABELS`、`MODULE_ORDER`、`typeOrder`、`getModulesForTestType`）与客户端 `self-check-utils.ts`（`STANDARD_TEST_TYPE_ORDER`），用例资产在 `self-check/case_config/` + `python/cases/`；新增/接入流程与能力门禁见 `.cursor/skills/self-check-test-integration/`。

- **bitflip（BAT bitflip 压测）**：MTK BitflipAnalysisTool v5.5.3 已 vendor 至 `python/tools/bitflip_bat/`（jar + 平台脚本，勿删改；运行输出 `BAT-Data_*/` 已 gitignore）；`-r` 重复次数经设置项 `bitflipRepeatCount`（默认 1）下发，用例超时 = **20h × -r**（`TAHP_BITFLIP_TIMEOUT_MS` 可覆盖）；结果表解析器在用例内（`cases/bitflip/bst/bst_runner.py`，纯 stdlib），逐轮结果写入 `detail.bitflip` 供报告页与导出 xlsx 展示。
- **alarm（休眠唤醒-重启测试）**：外部 PyInstaller 工具包（`alarmToolDir` 设置项引用，默认 `D:\rd_tool\alarm_v2.1.029`，勿 vendor 进仓）；sleep/reboot/shutdown 三模式**互斥单选**（服务端 `resolveStartModules` 缺省仅 sleep + 多选抛错；前端单选化），启动逻辑在 `python/tools/alarm/alarm_tool.py`（合并写工具 config.json 后启动；逆向 start.exe 实锤其设备枚举无过滤参数、会对所有已连接设备启动，故按在线设备数**双路径**：单设备且为目标机 → 走 start.exe 原生流程；**多设备 → 按 SN 直启**（复刻 start.exe 逐设备流程，所有命令 `-s SN`/`-device_id SN` 定向，不触碰其它在线设备；exit 4 多设备拒绝已废除，exit 5 改为目标机不在线）。**安装器坑（逆向 install_trde_apk 实锤）**：`resource/apk/` 下两个安装器 APK 发现用 `Path.cwd().glob('*.apk')`，必须以安装器自身目录为 cwd 运行，否则静默失败（退出码仍 0，输出"完成安装手机 X, success/fail"才是真结果）——直启流程已按此运行并校验成功标记 + `pm list` 双保险；安装器 `install_apk` 用 `adb -s <device_id>` 本身多设备安全。**启动判定**＝start.exe 路径：退出码 0 ＋ 完成横幅（GBK 双解码，traceback 为 usage 统计噪音勿当失败）；sleep 模式两路径统一**稳定期复检**：轮询见 alarm.sh 后再观察 10s，进程存活且 alarm.log 无 `INSTRUMENTATION_FAILED` 才算成功（instrument 瞬败会让脚本数秒退出，仅见进程是假 pass）；reboot/shutdown 设备随即断电无法事后确认，仅以流程完成/横幅为准。与 monkey 同款"启动成功即 pass、设备自治运行"语义，`endTest` 挂 `stopAlarmForDevice` 按机停止（**停止残留**：周期性 RTC 唤醒闹钟存于硬件清不掉，睡眠周期中途停止后数分钟内设备可能自行上电/重启一次，属工具固有行为，停止输出有提示）；case 超时 600s（含安装器）；不进 verify-auto-run `SUPPORTED_TEST_TYPES`（本地人工测试类型）。

## 路径与配置排障

配置异常按序查（细则见 `tahp-paths-config.mdc`）：

1. BFF 启动日志中的 `projectRoot` / `valid=`
2. `tahp-console/.env` → `TAHP_PROJECT_ROOT`
3. `{工程根}/.tahp/unified-config.json`
4. `%LOCALAPPDATA%\hermes\skills\jira-ops\.env` → `WORKSPACE_ROOT`
5. 重启 BFF 后确认落盘 `{工程根}/jira_workspace/<JIRA_KEY>/`

## 安全红线

1. 不在未验证 API 存在性的情况下生成代码
2. 不硬编码密钥 / Token / 设备标识
3. 安全相关 Bug 必须标记 Critical
4. Server 调外部命令用 `execFile`/`spawn` 参数数组，禁 shell 字符串拼接

## 文档

- [tahp-console/README_zh.md](tahp-console/README_zh.md) — 控制台使用说明
- [tahp-console/DEVELOPMENT.md](tahp-console/DEVELOPMENT.md) — Console 编码 / 测试 / PR 细则
- `docs/TECNO-AI-Harness-Platform-方案设计.md`、`docs/EasyAdapter-Architecture-Overview.html` — 方案与架构（`docs/` 不入库，仅本机存在）
