---
name: harness-version-server
description: harness 整机版本服务器查询子 skill。覆盖 version-server list-projects/list-versions/find-latest/get-pack-json，把用户自然语言（转测/zhuance/TEST/DEV/userdebug/user/iteration/brand）映射到结构化参数。优先用 CLI；当 CLI 的 candidates 已说明目标 OS/variant/分支不存在时直接报告可用组合，不走目录扫描。
version: 2.1.14
---

# Harness Version Server 子 skill

## 何时进入

- 用户要查"最新转测版本"、"DEV 版本路径"、"pack.json 位置"；
- 知道项目名（CM8、LK7k、X6878 等）、版本类型（TEST/DEV/KOM/ASAN）、variant（user/userdebug/eng）；
- find-latest 没命中，需要根据 CLI 返回的 `candidates` 判断可用项目、OS、分支、variant。

版本查询是 CLI 可直接解决的问题：优先运行 `version-server ...`，不要先 `knowledge route/search`。只有 CLI 未覆盖用户语义、结果矛盾、或用户要求解释版本命名/SOP 时才读 references 或查知识库。

## 用户语言 → 参数

- "转测"、"zhuance"、"transfer-test" → `--version-type TEST`
- "DEV"、"开发版本" → `--version-type DEV`
- "KOM" / "ASAN" → 对应 `--version-type`
- "userdebug" / "user" / "root" 是最终输出 variant；查询 pack 时先按目标 variant 查，没命中时可改用同项目/OS/分支下可用的 `user` pack，最终编译仍传目标 `--variant`
- 项目名大小写不敏感
- 用户指定品牌才传 `--brand TECNO/itel/Infinix`；否则按项目前缀自动选（`X*` → INFINIX，其他 → TECNO）
- 用户要特定迭代号才加 `--iteration <number>`
- 只有用户已指定或已确认时才传 `--tos-version`、`--branch-kind`、`--version-type`；如果用户只给项目名，先用 `list-versions` / `find-latest` 返回的候选整理 OS 版本、主干/量产和 TEST/DEV/KOM/ASAN 组合，让用户选择。不要默认替用户选择 A16、主干、量产或 TEST。

## 命令速查

```text
# Shortcut：只在用户明确要“最新转测 userdebug”这类语义时使用
harness --json +latest CM8

harness --json version-server list-projects --brand TECNO
# OS version filter: 用户指定 tos16/A16/hios16.x -> --tos-version 16; exact 16.3.0 -> --tos-version 16.3.0
# Branch kind filter: 用户指定主干/latest trunk -> --branch-kind trunk; 用户指定量产/latest release -> --branch-kind release; use --version-type ALL when the user asks by branch kind.
harness --json version-server list-versions --project CM8 --version-type TEST --limit 20
harness --json version-server find-latest --project CM8 --version-type TEST --tos-version 16 --variant userdebug
harness --json version-server find-latest --project KM9 --version-type ALL --tos-version 16 --branch-kind trunk
harness --json version-server find-latest --project KM9 --version-type ALL --tos-version 16 --branch-kind release
harness --json version-server get-pack-json --project CM8 --version-type TEST --tos-version 16 --variant userdebug --output pack.json
harness --json version-server get-pack-json --project KM9 --version-type ALL --tos-version 16 --branch-kind trunk --variant user --output pack.json
```

## 返回中要报告什么

- `version_path`：源版本目录（上海 `\\10.150.98.24\sw_ver_sh`）
- `pack_json_path`：`.pipe/pack.json` 位置
- `release_path` / `chongqing_path`（如有）：重庆 `\\10.205.4.40\sw_version\CI` 发布路径
- `preferred_download_path` / `preferred_download_site`：ROM/刷机包下载优先路径，由本机 SMB RTT 探测在上海/重庆候选中选择；不要把它理解成固定重庆优先。
- `download_path_candidates` / `site_preference_order`：候选路径和实际 RTT 站点顺序，用于向用户解释为什么选这条下载路径。

## 用户要把 ROM 拉到本地刷机时

把请求路由到 `harness-device` 子 skill，按"拉 ROM 到本地（关键：先问用户路径）"那段处理。复制源优先使用 CLI 返回的 `preferred_download_path`；它是 RTT 驱动的下载路径，不是固定重庆或固定上海。**不要默默 `Copy-Item` 到 `%TEMP%` 或 C:** —— ROM 体积常 ≥ 5 GB，必须先和用户确认目录、检查剩余空间，再开始复制。

## 没命中时

当 `find-latest` / `get-pack-json` 返回 `not_found`：

1. 先读 JSON 里的 `query` 和 `candidates`，尤其是 `available_tos_versions`、`available_variants`、`available_branches`、`available_compile_options`、`versions[].source_path`；
2. 如果候选已经证明目标输出 variant 不存在，但同项目/OS/分支存在 `user` 或其它 variant，优先改用该可用 variant 获取 pack；报告“pack 来自 user，最终编译仍使用目标 `--variant`”；
3. 只有同项目/OS/分支也不存在可用 pack 时，才报告“当前没有匹配的 A16 pack”，并列出可用组合；
4. 如果命令参数明显缺失或语义映射错误，且用户原话已经指定对应维度，修正参数后重试一次，例如 A16 加 `--tos-version 16`，主干加 `--version-type ALL --branch-kind trunk`；如果用户没有指定 OS/分支/版本类型，不要修正成默认值，先让用户确认候选组合；
5. 只有在 CLI 无候选、候选与用户提供的明确版本事实冲突、或用户给了具体版本目录时，才按 `references/version-server-layout.md` 走受控 fallback。

受控 fallback 规则：

1. 先列项目；项目名先做大小写不敏感精确匹配；
2. 列出版本类型目录确认；
3. 解析版本目录名（`tOS<version>.<iter>[SPxx][<timestamp>_<build>_<variant>]`）；
4. 读 `releasenote.json` 发现重庆 release 路径；
5. 保留实际检查过的完整路径，在最终回答中说明 fallback 过程。

不要递归扫描大范围网络根；不要用 `Get-ChildItem -Recurse` 搜 `pack.json`；只在当前 brand/project/version-type 子树内做受控核验。

## 边界

- 默认不要手工拼接版本服务器路径；先用结构化 CLI 查 `find-latest` / `get-pack-json`。
- 默认不传 `--server-root`，除非用户明确给了根路径或当前环境需要覆盖。
- 不要把 harness 自身代码或调试材料写到 `\\10.150.98.24\...` 或 `\\10.205.4.40\...`。

## 反馈

```text
harness --json feedback create --scenario version-server --problem-type missing-guidance \
  --tool "harness version-server find-latest" --detail "..."
```
