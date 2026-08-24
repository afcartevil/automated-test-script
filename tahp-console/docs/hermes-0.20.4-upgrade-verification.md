# Hermes 0.20.4 平替验收清单

> 执行日期：2026-08-24  
> 机器：本机 Windows（Python 3.12.6 / Node v24.18.1）  
> 基线 commit：`72a61c84`（0.15.1）  
> 目标：上游 `v2026.8.18` / `hermes-agent 0.20.4`  
> 判定：只有「接得上 + 读得到 + 行为一致 + 业务能跑完」四条同时成立，才算可平替。

本文固化 L1–L4 检查命令、本机结果、发布说明与回滚步骤，供其它机器复用。

## 发布说明（固定文案）

- Hermes：**0.20.4**（`v2026.8.18`），Console 加载仓库内 `hermes-agent-main/run_agent.py` 及其 `.venv`，不要跑全局 `hermes update`。
- Python：**3.11–3.13**（推荐 3.12）。**不要使用 3.14**（官方 `requires-python = ">=3.11,<3.14"`，无 cp314 wheel）。
- 配置权威源仍是各 profile 的 `HERMES_HOME`（Windows 默认 `%LOCALAPPDATA%\hermes`）。
- 更新后须**重启 Console**。首次启动会因指纹变化重建 `.venv`。
- 其它机器：`cd tahp-console && npm run setup:agent -- --force`，然后重启。

## 本机结论（2026-08-24）

| 层 | 结果 | 说明 |
|---|---|---|
| L1 环境与来源 | **通过** | 缓存命中 0.20.4，探针 `missing=[]` |
| L2 自动化 | **通过（有已知环境噪声）** | `npm run build` 通过；升级相关 31 项必绿；全量 44 fail 与 vendor 无关 |
| L3-A 历史会话 | **通过** | 24 会话 / 874 消息，无丢失无重复 |
| L3-B 平台契约 | **通过（代码+测试+存活 Bridge）** | 聊天/approval/interrupt 的**人工点选**放到 24–48h 灰度 |
| L3-C CLI 协议 | **通过** | `profile list` 解析到 `default`，不走磁盘 fallback；`sessions export -` 退出码 0（24 行 JSON） |
| L3-D 业务入口 | **只读探测通过** | 诊断/适配/流水线/自检/任务/Skill 同步 HTTP 200；**未新开真实任务** |
| L4 灰度 | **已启动观察窗口** | Console 已在 0.20.4 运行（`/health`：`agent_bridge=running`） |

**尚未勾选、须在灰度期内由使用人完成的项**：普通聊天流式、终端 approval 默认拒绝、interrupt/steer、强制压缩后续聊、双 profile 并发、各业务「各跑一条真任务」。未通过任一条按第 5 节回滚。

---

## L1 环境与来源

```bash
cd tahp-console
npm run setup:agent
```

期望：`Agent 环境已就绪（跳过安装）`。

```bash
..\hermes-agent-main\.venv\Scripts\python.exe scripts\hermes-compat-probe.py --agent-root ..\hermes-agent-main --mode auto
```

期望：`ok: true`，`missing: []`。

本机结果：

- [x] `npm run setup:agent` 跳过安装
- [x] `.tahp/agent-paths.json`：`version=2`，`hermesVersion=0.20.4`，`lockFingerprint` 有值
- [x] 探针 `ok: true`，`missing: []`（source + runtime）
- [x] `run_agent.py` 在 `E:\easyadapter\hermes-agent-main\`
- [ ] 已知告警（不作为回归）：链接 SQLite **3.45.3** < 建议 3.51.3+，不阻塞 Bridge

## L2 自动化门禁

```bash
cd tahp-console
npm test
npm run build
```

升级相关必绿（本机 2026-08-24）：

```
npm test -- tests/scripts/hermes-compat-probe.test.ts tests/scripts/hermes-agent-fingerprint.test.ts tests/scripts/hermes-python-range.test.ts tests/server/skill-injector.test.ts tests/server/run-chat-compression.test.ts tests/server/run-chat-bridge-delta.test.ts tests/server/run-chat-model-config.test.ts tests/server/run-chat-content-blocks.test.ts tests/server/sessions-db-lineage.test.ts tests/server/session-detail-db.test.ts
```

- [x] 上述 10 个文件：**31 passed / 2 skipped**
- [x] `npm run build` 通过
- [x] `sessions-db.test.ts` 有 1 条 Windows 路径断言失败（期望 `/tmp/...`，实为 `\tmp\...`），与 Hermes 版本无关
- [x] 全量 `npm test`：`22 failed | 155 passed`，`44 failed | 1003 passed`。失败集含客户端缺失模块、本机 KB/报告污染、`python3` ENOENT 等。`agent-bridge-manager` / `agent-bridge-profile-env` / `hermes-plugins-env` 与基线 `72a61c84` **源码一致**，属环境泄漏（真实 `HERMES_AGENT_ROOT`），**不作为 0.20.4 回归**。

判读规则：只允许上述已知环境性失败；出现**新的** Bridge/会话/Skill 失败即视为回归。

## L3-A 历史会话（最高风险）

备份：`D:\Users\admin\.tahp-hermes-upgrade-backup-0.15.1\localappdata-hermes\state.db`（0.15.1 冻结，16.5 MB）。

1. 复制到临时 `HERMES_HOME`，用 0.20.4 `SessionDB` 打开（会做 schema 演进）。
2. 用 stdlib sqlite 对比打开前后 `sessions` / `messages` 行数与每会话条数。
3. 用 Console 同款 SQL（`listSessionSummaries` / `SELECT * FROM messages ORDER BY id` / FTS）再读一遍。
4. 对正在跑的 Console 打会话列表与详情。

本机结果：

| 检查 | 结果 |
|---|---|
| 打开前 | 24 sessions / 874 messages |
| 0.20.4 SessionDB 打开后 | 24 / 874，**problems=[]** |
| 新增表（可接受） | `async_delegations`, `compression_locks`, `gateway_hygiene_state`, `gateway_routing`, `session_model_usage`, `session_turn_leases`, `system_prompts` |
| 删除表 | 无 |
| Console SQL 列表 | 24 条，无重复 id |
| 样本 `tahp-skill-config-jira-ops` | 162 条，按 id 有序，无重复；角色 `user,assistant,tool,...` |
| FTS `jira` | 535 hits |
| 存活 Console `GET /api/hermes/sessions` | 200，4 条可见根会话 |
| `GET /api/hermes/sessions/:id` | 200，消息数与 `message_count` 一致（18） |

不通过 → 立即回滚，不要继续 L3-B。

## L3-B / L3-C 平台与 CLI

### C. CLI（已测）

```text
hermes profile list     # 退出码 0，profile-list-parser 解析到 default，usedDiskFallback=false
hermes sessions export -  # 退出码 0，24 行 JSON
```

- [x] `profile list` 不走磁盘 fallback
- [x] `sessions export -` 退出码 0

### B. 平台能力

代码契约（本机已核对，未改 `hermes_bridge.py`）：

- [x] approval 超时默认 **deny**（`tahp-bug-` / `tahp-gerrit-` 前缀例外为 `once`，与升级前一致）
- [x] `interrupt` / `steer` 动作仍在 Bridge
- [x] 压缩 hook 使用 `**kwargs`（兼容 0.20.4 `_compress_context` 签名）
- [x] Skill 注入跳过官方 `harness-*` / `asf-*`（`isOfficialHarnessSkillId`）
- [x] `/health`：`version=v0.20.4 (2026.8.18)`，`gateway=running`，`agent_bridge=running`

灰度期内人工勾选（重启后的 Console 上操作）：

- [ ] 普通聊天：正文流式 + reasoning 流式
- [ ] 终端工具触发 approval：默认拒绝 / 超时未变松
- [ ] 停止（interrupt）与引导（steer）
- [ ] 强制压缩后能继续对话
- [ ] 重启 Console 后恢复同一会话
- [ ] 两个 profile 并发：模型 / Key / Skill 不串
- [ ] Skill 热注入：业务 Skill 生效；官方 harness Skill 仍跳过

## L3-D 业务入口（只读探测 2026-08-24）

未新开诊断/适配任务（避免占用模型和 JIRA）。以下接口在已升级 Console 上均为 **HTTP 200**：

| 入口 | 探测 |
|---|---|
| 智能诊断 | `GET /api/tahp/bug-analysis/channel-config`，`GET /api/tahp/bug-analysis/jira-config/status` |
| AI 适配 | `GET /api/tahp/adapt/config/get` |
| 适配流水线 | `GET /api/tahp/adapt-pipeline/runs`，`/capabilities`，`/workflow` |
| 质量验测 / 自检 | `GET /api/tahp/self-check` |
| 任务中心 | `GET /api/tahp/task-inbox` |
| Skill 同步 | `GET /api/tahp/skills/sync-status`（connected，226 skills） |
| GKI | `GET /api/tahp/gki-patch/status` |
| Modem | `GET /api/tahp/modem-baseline/defaults`，`/runs` |

落盘路径未改：

- 报告：工程 `reports/`（本机仍有 `bug-analysis/`、`adapt-pipeline/`、`self-check/`）
- JIRA 日志：工程 `jira_workspace/`

灰度期内各跑一条真任务并勾选：

- [ ] 智能诊断 `/tahp/bug-analysis`
- [ ] AI 适配调试 `/tahp/adapt-debug`
- [ ] 适配流水线（可从推荐点续跑）
- [ ] 质量验测 / AI 自检
- [ ] 任务中心、Skill 同步中心
- [ ] Modem / GKI（若当期有基线）

每条核对：报告在 `reports/`，JIRA 日志在 `{工程根}/jira_workspace/`，凭据不串。

## L4 灰度与推广

观察 24–48 小时：

- [ ] Bridge 是否反复重启（`/health` 的 `agent_bridge`）
- [ ] 任务错误率 / 耗时是否明显变差
- [ ] 是否出现重复消息
- [ ] `.venv` 是否被反复重建（指纹应稳定，二次 `setup:agent` 应跳过）

通过后再铺其它机器。每台：

```bash
cd tahp-console
npm run setup:agent -- --force
```

然后重启 Console。

## 5. 回滚

命中任一条即回滚，不做临时兼容补丁：

- Bridge 起不来或反复重启
- 历史会话打不开，或消息重复 / 丢失
- profile 配置或 API Key 串
- approval 被绕过或默认变为自动同意（聊天会话）
- 压缩失败导致对话中断
- 核心任务成功率明显下降

步骤：

1. vendor 与 TAHP 改动回退到 `72a61c84`
2. 恢复 `D:\Users\admin\.tahp-hermes-upgrade-backup-0.15.1`
3. `cd tahp-console && npm run setup:agent -- --force`（**禁止复用 0.20.4 的 `.venv`**）
4. 重启 Console，复跑 L1 + L3-A + 一条诊断、一条适配
