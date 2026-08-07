# EasyAdapter 质量评测层设计与实现方案

> 状态：已实现（2026-08）  
> 范围：智能诊断（LLM judge）+ AI 适配（客观信号）+ 检索路由（离线客观）+ 评测集导入导出 + 检索 CI 门禁  
> 不覆盖：完整流水线重跑（adapt→build→selfcheck）、诊断/适配进 CI（待脱敏集与判官校准）

---

## 1. 背景与目标

### 1.1 问题

智能诊断的质量控制原先只有两条路径：

1. 人工审核门（人眼看报告）
2. 用户在对话里追加 `corrections`（补信息继续分析）

无法回答一个基本问题：

> 改了 skill / 换了模型 / 调了 prompt / 改了路由之后，质量是变好还是变坏？

这使得 skill 资产继续膨胀时，质量只能靠人力线性兜底，无法形成可度量的改进闭环。适配与检索路由同样缺少回归信号。

### 1.2 目标


| 能力          | 判定标准                                                    |
| ----------- | ------------------------------------------------------- |
| 分域评测        | `suite`：`bug-analysis` / `adapt` / `retrieval`，评测集与结果隔离 |
| 批量重跑 / 离线打分 | 诊断重跑 Agent；适配可 rerun 或离线客观分；检索纯本地路由断言                   |
| 变体对比        | 两次评测可按「模型 + skill 指纹 + 判分口径」对比                          |
| 回归门禁        | CLI `--baseline` 回退超阈值时 exit ≠ 0；检索另有离线 CI 门禁           |
| 下钻          | 失败用例可打开评分明细；诊断/适配可跳原报告                                  |
| 团队共享        | 脱敏 bundle 导入导出（不把真实 JIRA/log 直接入库）                      |




### 1.3 非目标

- 不做绝对合格判定（LLM judge 只提供**相对信号**；客观分亦按固定 rubric）
- 真实业务评测集默认不入库（落在 `.tahp-config/evals/`，gitignore）
- 诊断 / 适配 **暂不**进 CI（依赖脱敏基准集 + 稳定判官）；检索窄切已进 CI
- V1 不适配流水线整链重跑（adapt→build→selfcheck 真跑设备/编译机）

---



## 2. 架构

三套 suite 共用存储 / 对比 / UI 骨架，打分与执行分叉：

```
.tahp-config/evals/{suite}/cases/{caseId}.json
        │
        ├─ bug-analysis ──► runner.ts ──并发≤2──► Agent Bridge ──► judge.ts (LLM)
        ├─ adapt        ──► adapt-runner（rerun Agent 或 offline 冻结信号）──► adapt-objective
        └─ retrieval    ──► retrieval-runner（同步 routeIntent + rankSkills）──► retrieval-objective
        │
        ▼
reports/evals/{suite}/{runId}/
  ├── summary.json
  └── cases/{caseId}.json
        │
        ├──► CLI：npm run eval:{bug|adapt|retrieval}（走 BFF REST）
        ├──► 检索 CI：npm run eval:retrieval:ci（离线，不启 BFF）
        └──► UI /tahp/evals（suite 切换、对比、校准、导入导出）
```

关键约束：

- **诊断 / 适配批跑必须在 BFF 进程内**——Agent Bridge 只在那里存活；`eval-run.mjs` 只是 REST 客户端。
- **检索批跑与 CI 门禁不依赖 Bridge / LLM**，可本地或 CI 直接跑。
- **判官模型与被评模型应分开配置**（仅 LLM judge 路径），避免同源偏袒。
- bug-analysis 结果仍可读 legacy 扁平目录 `reports/evals/{runId}/`（兼容旧落盘）。

---



## 3. 数据模型



### 3.1 评测用例

路径：`{工程根}/.tahp-config/evals/{suite}/cases/{caseId}.json`  
（根 `.gitignore` 的 `.tahp-config/`；**真实集不入库**。仓内可提交脱敏基准包，见 §12.2。）

```json
{
  "id": "eval-tel-001",
  "suite": "bug-analysis",
  "title": "VoLTE 掉话",
  "source": {
    "type": "jira",
    "jira_key": "XXX-123",
    "problem_description": "可选补充描述",
    "origin_task_id": "task-bug-..."
  },
  "rubric": [
    {
      "id": "root_cause",
      "weight": 3,
      "must": true,
      "criterion": "指出根因为 modem 侧 NAS 重附着失败，而非 RIL 层"
    }
  ],
  "labels": ["telephony", "regression-suite"],
  "created_at": "2026-08-07T00:00:00.000Z",
  "had_corrections": true,
  "mode": "rerun"
}
```


| 字段                 | 说明                                                                |
| ------------------ | ----------------------------------------------------------------- |
| `suite`            | `bug-analysis` | `adapt` | `retrieval`                            |
| `source.type`      | `jira` / `local` / `adapt_agent` / `pipeline` / `retrieval_query` |
| `rubric[].must`    | 必过项未通过 → 整例直接 `fail`                                              |
| `rubric[].scoring` | `objective` | `llm`（适配/检索客观项用 `objective`）                        |
| `mode`             | `rerun`（重跑业务）| `offline`（冻结信号 / 本地路由；pipeline 与 retrieval 默认）     |
| `had_corrections`  | 诊断：带补充轮次的历史任务，天然负样本                                               |
| `criterion`        | 写给判官的自然语言；**越具体判官越稳**                                             |


仓内模板：

- `[rubric-template.json](../packages/server/src/services/tahp/eval/rubric-template.json)`（诊断）
- `[adapt-rubric-template.json](../packages/server/src/services/tahp/eval/adapt-rubric-template.json)`（适配）



### 3.2 评测结果

路径：`{reportsDir}/evals/{suite}/{runId}/`

**summary.json**（字段示意）

```json
{
  "run_id": "eval-adapt-1754...",
  "suite": "adapt",
  "status": "completed",
  "variant": {
    "model": "claude-...",
    "judge_model": "gpt-...",
    "skills_hash": "a1b2c3d4e5f6",
    "prompt_version": "adapt-obj-v1"
  },
  "total": 20,
  "passed": 15,
  "warned": 2,
  "failed": 2,
  "errored": 1,
  "avg_score": 0.82,
  "pass_rate": 0.75,
  "cases": []
}
```

**变体指纹**（`prompt_version` 因 suite 而异）：


| 字段               | 含义                                                                   |
| ---------------- | -------------------------------------------------------------------- |
| `model`          | 被评模型标签                                                               |
| `judge_model`    | 判官模型（客观-only suite 可空）                                               |
| `skills_hash`    | `skillsDir` 下 `SKILL.md` 摘要                                          |
| `prompt_version` | 诊断：`JUDGE_PROMPT_VERSION=v1`；适配：`adapt-obj-v1`；检索：`retrieval-obj-v1` |


指纹不一致时 UI / CLI 提示「分数差异不能单一归因」。

### 3.3 判分规则（共用聚合）


| 结论     | 条件                                    |
| ------ | ------------------------------------- |
| `fail` | 任一 `must` 未通过，或加权总分 < 0.6，或 rubric 为空 |
| `warn` | 无 must 失败，且 0.6 ≤ 总分 < 0.8            |
| `pass` | 无 must 失败，且总分 ≥ 0.8                   |


LLM 判官未给出的 rubric 项按未通过计。  
判官调用失败记用例 `error`，**不记 0 分**。

人工校准三档（UI「判 pass / warn / fail」）与上表同义，用于和判官结论算一致率。

---



## 4. 模块与文件

```
packages/server/src/services/tahp/eval/
  types.ts                 # 三 suite 共用模型
  store.ts                 # 按 suite 读写评测集 / 结果
  fingerprint.ts
  judge.ts                 # LLM-as-judge（诊断）
  case-builder.ts          # 诊断：历史报告 → 用例
  runner.ts                # 诊断批跑
  adapt-objective.ts       # 适配客观分
  adapt-case-builder.ts
  adapt-runner.ts
  retrieval-objective.ts   # 检索客观分
  retrieval-case-builder.ts
  retrieval-runner.ts
  retrieval-ci-gate.ts     # CI-safe 离线门禁
  bundle.ts                # 脱敏导入导出
  compare.ts / calibration.ts
  rubric-template.json / adapt-rubric-template.json
  index.ts

packages/server/src/routes/tahp/eval.ts
packages/client/src/api/tahp/eval.ts
packages/client/src/views/tahp/EvalsView.vue
scripts/eval-run.mjs
fixtures/evals/retrieval-ci-baseline.json

tests/server/eval-judge.test.ts
tests/server/eval-compare.test.ts
tests/server/eval-calibration.test.ts
tests/server/eval-adapt-objective.test.ts
tests/server/eval-retrieval-objective.test.ts
tests/server/eval-bundle.test.ts
tests/server/eval-retrieval-ci-gate.test.ts
```

分层：纯函数（打分 / 解析 / 脱敏）与 I/O（Bridge / LLM / 磁盘）分离；单测只测纯函数与离线路由。

---



## 5. API

前缀：`/api/tahp/eval`  
多数接口带 `?suite=`（或 body.`suite`）；默认兼容 `bug-analysis`。  
响应：`{ success, data }` / `{ success: false, error }`。

### 评测集


| 方法     | 路径                        | 说明                                          |
| ------ | ------------------------- | ------------------------------------------- |
| GET    | `/cases?suite=`           | 列表 + `default_rubric`                       |
| GET    | `/cases/:caseId?suite=`   | 详情                                          |
| PUT    | `/cases/:caseId`          | 改 title / labels / rubric / mode            |
| DELETE | `/cases/:caseId?suite=`   | 删除                                          |
| GET    | `/candidates?suite=`      | 可转存候选（诊断报告 / 适配报告·流水线 / 检索种子）               |
| POST   | `/cases/from-report`      | 按 suite 转存：`task_id` / `run_id` / `seed_id` |
| POST   | `/retrieval/import-seeds` | 一键导入缺失检索种子                                  |
| GET    | `/bundle/export?suite=`   | 导出脱敏包（`redact=0` 可关脱敏）                      |
| POST   | `/bundle/import`          | 导入 bundle；`overwrite` 可选                    |




### 批跑


| 方法   | 路径                                 | 说明                                                      |
| ---- | ---------------------------------- | ------------------------------------------------------- |
| GET  | `/runs?suite=`                     | 评测记录                                                    |
| POST | `/runs`                            | 启动：`case_ids` / `judge_model` / `concurrency` / `suite` |
| GET  | `/runs/:runId`                     | summary                                                 |
| POST | `/runs/:runId/abort`               | 中止                                                      |
| GET  | `/runs/:runId/cases/:caseId`       | 评分明细                                                    |
| GET  | `/runs/:runId/compare?baseline=`   | 与 baseline 对比                                           |
| PUT  | `/runs/:runId/cases/:caseId/label` | 人工独立打分                                                  |
| GET  | `/runs/:runId/calibration`         | 一致率 / 是否可信                                              |


Socket.IO `/tahp-run` 事件：`eval.started` / `eval.case_started` / `eval.case_done` / `eval.completed` / `eval.failed`。

### 反馈闭环

`continueBugAnalysis` 追加 corrections 时发射：

```ts
emit(taskId, 'task.correction', {
  round, correction, jira_key, eval_candidate: true
})
```

评估层据此把该任务标为诊断评测候选。

---



## 6. 使用指南



### 6.1 Console

1. 侧栏 **质量评测**（`/tahp/evals`）
2. Suite 下拉顺序：**AI 适配 → 智能诊断 → 检索路由**（默认 **AI 适配**）
3. 「管理评测集」：
  - 诊断 / 适配：从右侧历史报告「转为案例」
  - 检索：「一键导入缺失种子」或单条转为案例
  - 「导出（脱敏）」/「导入」共享评测集
4. 诊断用例需编辑评分标准（`criterion` 写具体）
5. 「开始评测」：诊断判官尽量与被评模型不同；诊断/适配并发建议 ≤ 2；检索可更高
6. 诊断：评测后做人工独立打分（≥10 例），看「判官校准」条（一致率 ≥80% → 可信）
7. 「与 baseline 对比」看回归 / 改善；诊断/适配可点「原报告」



### 6.2 CLI（需 BFF）

```bash
cd tahp-console
npm run eval:bug
npm run eval:adapt
npm run eval:retrieval

npm run eval:bug -- --cases eval-tel-001 --baseline <runId> --max-regression 0.05
npm run eval:adapt -- --json
```


| 选项                                | 含义                                                     |
| --------------------------------- | ------------------------------------------------------ |
| `--suite`                         | `bug-analysis` | `adapt` | `retrieval`（npm script 已注入） |
| `--baseline` / `--max-regression` | 回归门禁（默认回退阈值 0.05）                                      |
| `--judge-model`                   | 判官（检索忽略）                                               |
| `--concurrency`                   | 并发（诊断/适配默认 2；检索默认更高）                                   |
| `--url` / `--token`               | BFF 与鉴权                                                |




### 6.3 检索 CI（不需 BFF）

```bash
cd tahp-console
npm run eval:retrieval:ci
```

已挂入根目录 `.github/workflows/ci.yml`。

### 6.4 环境变量


| 变量                          | 作用                                     |
| --------------------------- | -------------------------------------- |
| `TAHP_EVAL_DIR`             | 覆盖评测集根（会再拼 `/{suite}`，除非路径已以 suite 结尾） |
| `TAHP_EVAL_RESULTS_DIR`     | 覆盖结果根（同上）                              |
| `TAHP_EVAL_JUDGE_MODEL`     | 默认判官                                   |
| `TAHP_EVAL_MODEL`           | 被评模型标签                                 |
| `TAHP_EVAL_CONCURRENCY`     | 默认并发                                   |
| `TAHP_EVAL_CASE_TIMEOUT_MS` | 单例超时（默认 30 min；检索批跑不适用长超时）             |
| `TAHP_EVAL_SUITE`           | CLI 默认 suite                           |


---



## 7. 判官校准（诊断 LLM 路径）

1. 跑一轮诊断评测，覆盖 ≥ 10 个用例
2. 人工按 rubric **独立**打 pass / warn / fail（不要先看判官结论）
3. 一致率 ≥ 80% 且样本 ≥ 10 → 可信；否则先收紧 `criterion`

阈值（`calibration.ts`）：`MIN_AGREEMENT_RATE = 0.8`，`MIN_LABELED_SAMPLES = 10`。

检索 / 纯客观适配项不依赖判官校准。

---



## 8. 设计取舍


| 决策                      | 理由                                |
| ----------------------- | --------------------------------- |
| 评测集默认不入库                | 真实 JIRA / log 触碰安全红线；共享靠脱敏 bundle |
| 先评终点质量 / 路由对错           | 中间 tool 轨迹另议；检索单独 suite           |
| 诊断并发默认 2                | 避免抢 Agent Bridge                  |
| must 短路                 | 防幻觉：证据不过则整例 fail                  |
| error ≠ 0 分             | 判官挂了不污染质量曲线                       |
| CLI 走 REST              | Bridge 生命周期在 BFF                  |
| 口径版本写入 `prompt_version` | 新旧分数不可混比                          |
| 检索 CI 只跑 CI-safe 种子     | 不依赖本机 skills 落盘，避免 CI 抖动          |


---



## 9. 验证

```bash
cd tahp-console
npm test -- tests/server/eval-judge.test.ts \
            tests/server/eval-compare.test.ts \
            tests/server/eval-calibration.test.ts \
            tests/server/eval-adapt-objective.test.ts \
            tests/server/eval-retrieval-objective.test.ts \
            tests/server/eval-bundle.test.ts \
            tests/server/eval-retrieval-ci-gate.test.ts
npm run eval:retrieval:ci
npm run build
```

覆盖：JSON/围栏解析、must 短路、加权、回归对比、校准门槛、适配客观分、检索客观分、脱敏 bundle、检索 CI 门禁。

---



## 10. 适配评测（已实现）


| 模式        | 来源               | 打分                                              |
| --------- | ---------------- | ----------------------------------------------- |
| `rerun`   | adapt-agent 报告转存 | 重跑 `startAdaptAgentRun`；客观分：完成 / 有改动 / skill 命中 |
| `offline` | 流水线 run 转存（默认）   | 不重跑整链；对冻结的 build / selfcheck / pipeline 终态打分    |


优先级：`pipeline passed` ≫ `build + selfcheck` ≫ `adapt completed + 有改动` ≫ soft LLM。

- 评测集：`.tahp-config/evals/adapt/cases/`
- 结果：`reports/evals/adapt/{runId}/`
- CLI：`npm run eval:adapt`
- 口径：`ADAPT_OBJECTIVE_VERSION = adapt-obj-v1`

---



## 11. 检索 / skill 路由评测（已实现）


| 维度           | 说明                                                                                                 |
| ------------ | -------------------------------------------------------------------------------------------------- |
| 运行           | 离线 `routeIntent` + `rankSkills`，不调 Agent / LLM                                                     |
| 来源           | 内置种子（对齐 intent-router / 域路由）+ 手工 query                                                             |
| 客观项          | intent（must）/ top1（must，可 N/A）/ topk / preferred / mode 覆盖                                         |
| 无 skill 排序意图 | `historical_case` / `concept_reference` / `direct_lookup` / `version_scope` / `integration_config` |


- 评测集：`.tahp-config/evals/retrieval/cases/`
- 结果：`reports/evals/retrieval/{runId}/`
- CLI：`npm run eval:retrieval`
- API：`POST /api/tahp/eval/retrieval/import-seeds`
- 口径：`RETRIEVAL_OBJECTIVE_VERSION = retrieval-obj-v1`

依赖本机 skills 的 top1 种子在 skill 缺失时 fail，属预期。

---



## 12. 后续可演进

1. ~~适配评测~~（V1）
2. ~~检索 / skill 路由评测~~（V1）
3. ~~评测集导入导出~~（`tahp-eval-bundle-v1`）
4. ~~接 CI（检索窄切）~~（`eval:retrieval:ci` + CI workflow）
5. **适配流水线重跑模式**（依赖编译机/设备）
6. **并行子代理**（与评估层正交）
7. **诊断/适配接 CI**（脱敏基准集 + 判官校准达标后）



### 12.1 导入导出

- UI：评测集「导出（脱敏）」/「导入」
- API：`GET /bundle/export` · `POST /bundle/import`
- 格式：`{ format: "tahp-eval-bundle-v1", suite, redacted, cases[] }`
- 脱敏：JIRA、绝对路径、邮箱、workspace/task id；省略 `frozen_signals`



### 12.2 检索 CI 门禁

```bash
npm run eval:retrieval:ci
```

- CI-safe 种子：intent / slash / mode（见 `RETRIEVAL_CI_SAFE_SEED_IDS`）
- 基准包：`fixtures/evals/retrieval-ci-baseline.json`
- skill top1 类种子仍走本机 `eval:retrieval`

---



## 13. 变更清单



### 诊断评估层（首版）


| 路径                                             | 动作                     |
| ---------------------------------------------- | ---------------------- |
| `packages/server/src/services/tahp/eval/**`    | 新增                     |
| `packages/server/src/routes/tahp/eval.ts`      | 新增                     |
| `packages/client/src/views/tahp/EvalsView.vue` | 新增                     |
| `scripts/eval-run.mjs` + `eval:bug`            | 新增                     |
| `bug-analysis.ts`                              | `task.correction` 候选钩子 |




### 适配 / 检索 / 导入导出 / CI


| 路径                                                                     | 动作                                       |
| ---------------------------------------------------------------------- | ---------------------------------------- |
| `adapt-*.ts` / `retrieval-*.ts` / `bundle.ts` / `retrieval-ci-gate.ts` | 新增                                       |
| `store.ts` / `types.ts`                                                | suite 分域                                 |
| `routes/tahp/eval.ts`                                                  | `?suite=`、seeds、bundle                   |
| `EvalsView.vue`                                                        | 三 suite + 导入导出                           |
| `eval:adapt` / `eval:retrieval` / `eval:retrieval:ci`                  | CLI                                      |
| `fixtures/evals/retrieval-ci-baseline.json`                            | 脱敏基准                                     |
| `.github/workflows/ci.yml`                                             | 检索门禁步骤                                   |
| 对应 `tests/server/eval-*.test.ts`                                       | 单测                                       |
| `.gitignore`                                                           | 允许提交 `tahp-console/docs/DESIGN-evals.md` |


