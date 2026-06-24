# 工作流详细说明

> 本文档描述本 skill 的内部工作流。`SKILL.md` 是任务编排骨架。

## 一、整体流程

```
              用户给出 issue_key（或 manifest_path）
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│ Step 0: log-pipeline/run_pipeline.py                 │
│   Jira → 下载 → 解压 → trace → job_manifest.json     │
│   产出：$WORKSPACE_ROOT/<issue>/job_manifest.json    │
│   analyze-only / manifest 模式可跳过                 │
└──────────────────────────────────────────────────────┘
                       │
                       ▼
              记下 MANIFEST_PATH =
              $WORKSPACE_ROOT/<issue_key>/job_manifest.json
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│ Step 1: L0 基础指标                                  │
│   modem_state / calibration_state / sim_state        │
│   → manifest.analysis.l0_baseline                    │
└──────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│ Step 2: L1 业务路由                                  │
│   ee / call / data / sim / other                     │
│   → manifest.analysis.l1_business                    │
└──────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│ Step 3: L2 域内分析（按 L1 路由）                    │
│   ee   → modem-l2-ee-analysis                        │
│   call → modem-l2-call-analysis (+ subskills)        │
│   data → modem-l2-data-analysis (+ sub_skills)       │
│   sim  → modem-l2-sim-analysis                       │
│   other→ 跳过                                         │
│   → manifest.analysis.l2_domains.{domain}            │
└──────────────────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────┐
│ Step 4: L3 最终结论                                  │
│   汇总 + 生成 final_report                           │
│   → manifest.analysis.l3_conclusion                  │
│   → manifest.analysis.final_report                   │
└──────────────────────────────────────────────────────┘
```

## 二、Step 0 详解：日志准备

```powershell
python log-pipeline\run_pipeline.py --issue-key <issue_key>
```

**前置依赖**：

- skill 根目录与 `log-pipeline/` 均已配置 `.env`（至少 `WORKSPACE_ROOT`、`JIRA_*`）
- `WORKSPACE_ROOT` 使用本机盘符路径（推荐 SSD），避免直接指向 UNC
- 按需：7-Zip、ELT/NLT、Wireshark、QUTS（见 `references/setup.md`）

**成功判定**：

- `{WORKSPACE_ROOT}/{issue_key}/job_manifest.json` 存在且通过 schema 校验
- 失败则终止，将 pipeline 终端输出交给用户

**嵌套目录（常见）**：解压后若 manifest 落在 `{issue_key}/{issue_key}/` 下，应上提到 `{WORKSPACE_ROOT}/{issue_key}/job_manifest.json` 再进入 L0。

## 三、Step 1-4 详解

详见各自的 SKILL.md：

| Step | 子 skill | 入口文档 |
|---|---|---|
| 1 | L0 基础指标 | `analysis_skills/modem-l0-baseline/SKILL.md` |
| 2 | L1 业务路由 | `analysis_skills/modem-l1-business-judge/SKILL.md` |
| 3a | L2 ee   | `analysis_skills/modem-l2-ee-analysis/SKILL.md` |
| 3b | L2 call | `analysis_skills/modem-l2-call-analysis/SKILL.md` |
| 3c | L2 data | `analysis_skills/modem-l2-data-analysis/SKILL.md` |
| 3d | L2 sim  | `analysis_skills/modem-l2-sim-analysis/SKILL.md` |
| 4  | L3 结论 | `analysis_skills/modem-l3-conclusion/SKILL.md` |

每个子 skill 都有 `references/playbook.md` 详述具体步骤、关键字、判定规则。AI 必须按 playbook 亲自执行，**不要调用其内置 `scripts/run_*.py`**（仅作 legacy 调试用）。

## 四、manifest 路径策略

**核心规则**：manifest 内所有路径字段都是 POSIX 风格相对路径，基准是 manifest 文件所在目录。

| 读取方 | 解析方式 |
|---|---|
| `log_search_read.py` | 自动从 `--manifest` 推断根目录，AI 传 `--relative-path` 即可 |
| AI 直接读 manifest 中的某个文件 | 自行 `os.path.join(os.path.dirname(MANIFEST_PATH), rel_path)` |

## 五、错误恢复

| 阶段 | 失败 | 恢复策略 |
|---|---|---|
| Step 0 | 整体失败 | 终止流程，把脚本输出 + 日志路径汇报给用户 |
| Step 1 (L0) | 缺日志/缺字段 | 降级 `confidence`，在 `gaps` 中记录 |
| Step 2 (L1) | 路由不明确 | 走 `other`，跳到 L3 |
| Step 3 (L2) | 子场景缺数据 | 子 skill 标 `insufficient_evidence`，主控继续汇总 |
| Step 4 (L3) | 任何错误 | 必须给出 `final_report`，即使是"证据不足，建议补抓日志" |

## 六、参考资料

- 契约字段说明：`manifest-input-contract.md`
- 更新 manifest：`manifest-update-guide.md`
- Schema：`../schemas/job_manifest.schema.json`
- 日志准备细节：`../log-pipeline/README.md`
