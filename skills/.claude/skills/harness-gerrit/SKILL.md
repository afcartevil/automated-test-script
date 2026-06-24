---
name: harness-gerrit
description: harness Gerrit 子 skill。覆盖 gerrit parse-url/get/search/files/diff/commit-message；用于查询公司 Gerrit CR、列 changed files、读取具体 diff、生成公司提交说明模板。MTK/QCOM 默认走 gerrit.transsion.com，SPRD/UNISOC 默认走 gerrit-cq.transsion.com；凭据优先 HARNESS_GERRIT_*，未配置时复用 HARNESS_QIZHI_USER / HARNESS_QIZHI_BASTION_PASSWORD。
version: 2.1.17
---

# Harness Gerrit 子 skill

Gerrit CR 查询、文件列表、提交说明模板是 CLI 可直接解决的问题：优先运行 `harness gerrit ...`，不要先 `knowledge route/search`。当前只提供查询和 message 生成；真正 commit / repo upload 还没有开放成通用命令，不能手拼 raw shell 绕过 remote runner 白名单。

## 常用命令

```text
harness --json gerrit parse-url "https://gerrit.transsion.com/c/platform/frameworks/base/+/123456"
harness --json gerrit get --change 123456 --platform QCOM
harness --json gerrit get --url "https://gerrit-cq.transsion.com/c/vendor/foo/+/123456"
harness --json gerrit search --query "owner:self status:open" --platform MTK --limit 10
harness --json gerrit search --query "project:vendor/foo status:open" --platform SPRD
harness --json gerrit files --change 123456 --platform QCOM
harness --json gerrit diff --change 123456 --file TranRadioNetDaemon/common/src/TranNet.cpp --platform QCOM
harness --json gerrit commit-message --id AR-202507-000103 --description "晕动舒缓2.0" --type func --affect-projects X6878 --test-suggestions "编译通过" --affect-platform QCOM
```

## 站点选择

- `--platform MTK` / `--platform QCOM`：默认 `https://gerrit.transsion.com`
- `--platform SPRD` / `--platform UNISOC`：默认 `https://gerrit-cq.transsion.com`
- 如果用户给了 Gerrit URL，`get/files` 会优先使用 URL 里的站点。
- 必要时可用 `--site main` / `--site cq` 或 `--gerrit-base-url <url>` 覆盖。

## 凭据

- 默认读取 `~/.tran_harness/env.yaml` / `gerrit.*`，环境变量为 `HARNESS_GERRIT_BASE_URL`、`HARNESS_GERRIT_CQ_BASE_URL`、`HARNESS_GERRIT_USERNAME`、`HARNESS_GERRIT_PASSWORD`、`HARNESS_GERRIT_AUTH_TYPE`。
- 没有 Gerrit 专用凭据时，CLI 会复用 `HARNESS_QIZHI_USER` 和 `HARNESS_QIZHI_BASTION_PASSWORD`。
- 不要在回答、反馈、日志摘要里回显 `--gerrit-password`、LDAP 密码或 bearer token。

## 边界

- 当前没有通用 `gerrit commit/upload/review` 命令；需要提交代码时先生成 `commit-message` 给用户确认。
- 上传到 Gerrit 必须等 remote-runner 白名单 action 或正式 `harness gerrit upload` 落地后执行，不能让 Agent 自己拼 `repo upload` / `git push refs/for/*`。

## CLI 契约自查

```text
harness --json commands describe gerrit get
harness --json commands describe gerrit search
harness --json commands describe gerrit files
harness --json commands describe gerrit diff
harness --json commands describe gerrit commit-message
```
