---
name: harness-mtk-auto-cr
description: harness MTK 自动提单子 skill。覆盖 harness mtk-cr doctor/sync/serve/pipeline/offer/fetch；JIRA BUG → MTK eService CR。知识包 infra/mtk-auto-cr。不要手写 python mtk_cr.py 或把 runtime 写入业务仓。
version: 2.1.17
---

# Harness MTK auto-CR 子 skill

MTK 自动提单随 harness 安装在 `knowledge_packs/infra/mtk-auto-cr/runtime/`（`scripts/mtk_cr.py`）。**只通过 `harness mtk-cr` 调用**；说明见 `docs/mtk-auto-cr.md` 与知识包 `SKILL.md`。

## 何时进入

- 用户提到 MTK CR、自动化提单、sync、链接触发、eService 提交；
- 需要 `harness mtk-cr pipeline <JIRA-KEY>`、`offer`、`sync`、`doctor`；
- 与 `harness-jira` 区分：jira 子命令只读查询 issue；**写备注、提 MTK、sync 服务** 走本 skill。

## 命令速查

```text
harness --json mtk-cr doctor
harness mtk-cr sync --interval 300
harness mtk-cr serve
harness mtk-cr offer --dry-run
harness mtk-cr pipeline TOS163-30725
harness mtk-cr fetch TOS163-30725 --print
```

参数不确定时：

```text
harness --json commands describe mtk-cr
harness mtk-cr help sync
```

## 配置

- 个人 JIRA：`knowledge_packs/infra/mtk-auto-cr/runtime/scripts/config.yaml`
- 部门 MTK 共用：同目录 `eservice.shared.yaml`
- 依赖：`pip install -e ".[mtk-auto-cr]"`；`harness doctor` 含 `mtk-auto-cr` 检查项
- 覆盖路径：`HARNESS_MTK_AUTO_CR_ROOT` 或 `--mtk-auto-cr-root`

## 推荐流程（链接触发）

1. 本机常驻：`harness mtk-cr sync --interval 300`（备注内 `http://127.0.0.1:8765/trigger/...` 仅本机有效）
2. `harness mtk-cr offer` 为名下 MTK BUG 加触发链接备注（可先 `--dry-run`）
3. 用户在 JIRA 点击链接 → 本机 pipeline 提交 MTK

**不要**把 `trigger_server.host` 改成他人 IP；**不要**替全队在一台机跑 offer。

## 边界

- 禁止在业务仓复制 `mtk-auto-cr/runtime/` 或 `python mtk_cr.py`；禁止用 lark-cli 访问 JIRA。
- 长驻命令 `sync`/`serve`/`watch` 在 `--json` 下流式透传，勿等待整段 JSON。
- 勿在输出/反馈中回显 `config.yaml` 密码、token、Cookie。

## 反馈

```text
harness --json feedback create --scenario mtk-auto-cr --problem-type missing-tool-option \
  --tool "harness mtk-cr pipeline" --detail "..."
```
