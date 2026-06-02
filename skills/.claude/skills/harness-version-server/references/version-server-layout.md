# 版本服务器目录模型参考

当 `harness version-server find-latest` 或 `get-pack-json` 找不到用户期望的版本，或者你需要解释版本路径是怎么推断出来的时候，读这个参考。

## 先查结构化命令

先用结构化命令，不要先猜路径：

- `harness version-server list-projects --brand <brand>`
- `harness version-server list-versions --project <project> --version-type <type> --limit <n>`
- `harness version-server find-latest --project <project> --version-type <type> --variant <variant>`
- `harness version-server get-pack-json --project <project> --version-type <type> --variant <variant> --output pack.json`
- 当目标是编译 userdebug/root，但同 OS/分支只有 user pack 时，可用 `--variant user` 获取 pack；最终产物 variant 由 rdtool build/package 阶段的 `--variant` 决定。

只有当 CLI 返回 `not_found`、空列表，或者结果与已知用户上下文冲突时，才考虑目录模型推理。先检查 CLI JSON 的 `candidates`：如果 `available_tos_versions`、`available_variants`、`available_branches` 已经证明请求的 pack variant 不存在，但同 OS/分支存在 `user` 或其它可用 variant，优先改用可用 variant 拿 pack；不要再扫 SMB 目录找一个 CLI 已经排除的同名 variant `pack.json`。

## 已知根路径

客户端事实来源是 `version_server/client.py`：

- `//10.150.98.24/sw_ver_sh` 是 MTK/QCOM 项目的原始版本索引根。
- 重庆发布路径不是默认索引根；如果目录里有 `releasenote.json`，就从里面读。
- 常见导出发布路径会指向 `//10.205.4.40/sw_version/CI/...`。

没有传 `--server-root` 时，客户端会搜索已知原始根。除非用户明确给了根路径，或者当前环境确实有挂载问题，否则不要强制覆盖。

## 目录模型

期望层级如下：

```text
<server-root>/<brand>/<project>/<version-type>/<version-directory>/.pipe/pack.json
```

常见品牌是 `TECNO`、`itel` 和 `Infinix`。品牌和项目名尽量大小写不敏感。

常见版本类型：

- `TEST`: transfer-test / zhuance / test builds
- `DEV`: 开发版本；目录名变化比 `TEST` 更大，不要只依赖标准 `tOS...[]` 解析器。
- `KOM`: KOM builds
- `ASAN`: ASAN builds

版本目录名通常长这样：

```text
tOS<major.minor.patch>.<iteration>[SPxx][<timestamp>_<build-number>_<variant>]
```

示例：

```text
tOS16.3.0.114[2026.05.12.14.20.34_36729_user]
```

解析字段是 `tos_version`、`iteration`、可选的 `SPxx`、`timestamp`、`build_number` 和 `variant`。有效 variant 常见为 `user`、`userdebug` 和 `eng`；整机代码通常不因 `user/userdebug/root` 改变，variant 更常用于选择最终编译/打包产物。

`TEST` 目录通常比较规整。`DEV` 目录可能用项目名、分支名、日构建名或临时命名。CLI 会把非标准 `DEV` 目录当作尽力候选，Agent 应该检查目录证据，不要把解析失败直接当成不存在。

源目录里还可能有：

```text
<version-directory>/releasenote.json
```

用它来发现重庆发布路径。JSON schema 可能变化，所以要扫描字符串值里是否包含 `10.205.4.40` 或 `sw_version/CI`。

## 受控 fallback

当直接查询没命中时：

1. 先读 CLI 返回的 `candidates`。若它已经给出近邻版本和可用 OS/variant/分支，优先据此修正查询；目标输出 variant 缺失时，先尝试同 OS/分支的 `user` pack。
2. 只有 CLI 无候选、候选明显矛盾、或用户给了具体版本目录时，才列请求品牌下的项目；如果用户没明确品牌，再列所有已知品牌。
3. 项目名先做大小写不敏感的精确匹配，只有精确失败后才看相近命名漂移。
4. 列出解析到的项目下的版本类型目录，确认用户想要的是 `TEST`、`DEV`、`KOM` 还是 `ASAN`。
5. `TEST` 优先用解析字段；`DEV` 则看最近目录、名字、修改时间、`.pipe/pack.json`、`releasenote.json` 和明显的 variant token。
6. 只有目录名真的携带 iteration 或 variant 信息时才手工过滤；不要因为目录名里没有 `user` 或 `userdebug` 就把一个看起来很新的 `DEV` 候选删掉。
7. 读取选中的源版本目录里的 `releasenote.json`，如果有就报告 `release_path` / `chongqing_path`。
8. 如果最新目录里没有 `.pipe/pack.json`，先检查 CLI 返回的 `attempted_pack_json_paths`；仍不存在时换同 OS/分支其它可用 variant（优先 `user`）再取 pack；仍失败才判断该版本不可用于 pack 下载，不要扩大递归扫描。
9. 保留你实际检查过的完整路径，并在最终回答里说明 fallback 过程。

不要递归扫描大范围网络根目录。不要用 `Get-ChildItem -Recurse` 查找 `pack.json`。只在当前请求需要的 brand/project/version-type 子树里做受控核验。

## pack.json 用法

标准 pack 文件是：

```text
<version-directory>/.pipe/pack.json
```

它是 rdtool workspace setup 的输入。重要字段包括 `project_name`、`product_name`、`android`、`platform`、`chipset`、`markets` 和 `part_conf[].component`。不要把 pack 文件名或来源 variant 当成最终输出 variant 的硬约束。

如果本地 workspace 需要 setup，但 CLI 拿不到 pack 文件，就说明路径，并参考 rdtool fallback 里的 `pipe_main --stage setup --cfg-url <version-path>` 或 `--cfg-path <parent>`。

如果同时有上海 `source_path` 和重庆 `release_path`，都要报告。`source_path` 用于 `.pipe/pack.json` 和 rdtool 配置发现；`release_path` 用于用户要发布版或归档路径时。

## 反馈

当结构化 CLI 漏掉真实场景、但 fallback 成功时要记反馈。写清查询字段、目录模型哪个层级不同，以及应该补哪个 CLI 命令。除非必要，不要贴完整私有路径，敏感段落做概括即可。
