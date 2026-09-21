# checklist-scmp-sync

根据飞书全功能特性 checklist，查询 TONES SCMP 各市场支持情况，并回写「此特性是否支持 / 备注」。

把 **整个 `checklist-scmp-sync` 目录**拷到目标项目即可（含 `run.py`、`checklist_scmp_sync/`、`tests/`）。本目录不包含 `lark-cli` 和 `tones-scmp`，这两项是运行依赖，需在目标机器单独安装。

## 运行依赖

| 依赖 | 用途 | 说明 |
|------|------|------|
| Python 3.10+ | 运行本 CLI | 无需额外 pip 包 |
| `lark-cli` | 读/写飞书表格 | 需在 PATH 中，且已 `lark-cli auth login`，账号对该文档有编辑权限 |
| `tones-scmp` | 查 SCMP 市场支持 | 默认找 `~/.cursor/skills/tones-scmp/scripts/run.py`；找不到时设环境变量 `TONES_SCMP_CLI` |

Windows 下请用 `python -u run.py ...`，或直接用本目录的 `run.py`（已设置无缓冲输出），否则 Web UI 会攒齐才刷进展。

## 命令

试跑（不写飞书）：

```bash
python -u run.py --url "https://transsioner.feishu.cn/wiki/xxxx" --dry-run
```

真正回写：

```bash
python -u run.py --url "https://transsioner.feishu.cn/wiki/xxxx"
```

常用参数：

| 参数 | 说明 |
|------|------|
| `--url` | 必填。飞书 Wiki / 表格链接 |
| `--dry-run` | 只出报告，不改飞书 |
| `--project X6879` | 覆盖标题里的项目编码 |
| `--tos-version 16.3.0` | 覆盖标题里的 tOS 版本；`16.3` 会规范成 `16.3.0`，`17` 会规范成 `17.0.0` |
| `--sheet-name Audio` | 只处理指定 sheet，可重复 |
| `--include-hidden` | 包含隐藏表、名称带「废弃」的 sheet |
| `--tones-cli <path>` | 指定 `tones-scmp/scripts/run.py` |
| `--format jsonl` | 默认。运行中逐行输出进展 |
| `--format json` | 结束后才把完整报告打到 stdout；JSONL 进展仍写入日志文件 |
| `--log-file <path>` | JSONL 日志路径；默认 `logs/checklist-scmp-sync-<时间戳>.jsonl` |
| `--no-log-file` | 不写日志文件 |

标题需能解析出项目编码和 tOS，例如：`X6879-tOS17 全功能特性checklist_V2.5 副本`。默认跳过「变更记录」、隐藏表、名称含「废弃」的 sheet。

## 默认输出：JSONL 进展流

stdout **每行一条 JSON**，立即 flush。前端按行解析即可。

每条都有：

- `event`：事件类型
- `message`：可直接展示的中文文案

### 事件一览

| event | 何时出现 | 前端建议 |
|-------|----------|----------|
| `start` | 开始读飞书 | 进度条起步 |
| `workbook` | 读到文档标题 | 显示标题 |
| `parsed` | 解析出项目 / tOS | 显示 `project`、`tos_version` |
| `scmp_login` | 登录 SCMP | 「正在登录」 |
| `scmp_resolve` / `scmp_resolved` | 匹配规格 | 显示 SPD 项目名 |
| `scmp_loading` / `scmp_loaded` | 拉市场清单 | 这一步可能较久 |
| `plan` | 确定要处理的 sheet 列表 | `sheet_count` 作总分母 |
| `sheet_start` | 开始某张表 | `index` / `total` |
| `row` | 处理到一行特性编码 | 可用 `message` 刷日志 |
| `row_skip` | 无编码 / 占位符，不回写 | 排查漏写 |
| `log_file` | 日志文件已创建 | `path` |
| `sheet_write` | 正在回写飞书 | 仅非 dry-run |
| `sheet_done` | 一张表结束 | 更新该表计数 |
| `sheet_error` | 某张表失败 | 标红，继续其它表 |
| `done` | 全部结束 | `ok`、`summary`，进度 100% |
| `report` | 完整结果 | 落库 / 展示明细，字段同 `--format json` 的 `data` |
| `error` | 致命失败（标题解析失败、SCMP 找不到唯一规格等） | 终止任务 |

`row` 示例：

```json
{"event":"row","sheet_name":"Audio","row":4,"code":"SF-202507-001364","support":"不支持","remark":"","message":"Audio 第4行 SF-202507-001364 → 不支持"}
```

`done` 示例：

```json
{"event":"done","ok":true,"summary":{"sheet_count":17,"feature_count":320,"supported":120,"unsupported":80,"partial":10,"missing":110,"failed_sheets":[]},"message":"全部处理完成"}
```

`report` 的 `data` 含每张表的 `items`（行号、编码、支持结论、各市场 0/1）。体积较大，适合任务结束后一次性保存，不要拿它刷进度条。

## 回写规则

| SCMP 结果 | 「此特性是否支持」 | 「备注」 |
|-----------|-------------------|----------|
| 各市场都支持 | 支持 | 清空 |
| 各市场都不支持 | 不支持 | 清空 |
| 部分市场支持 | 支持 | `部分市场支持：EU, OP` |
| 编码不在该规格中 | 不改 | `特性编码不存在` |
| 去空白后仍不是 `SF/SR-` + 数字 | 不改 | `特性编码格式不正确` |

一行有多个 `SF-` / `SR-` 编码时，只处理第一个，备注追加 `另有编码未处理：...`。先去掉空格/换行再识别，不要求 6 位序号，例如 `SF-202602-00101`、`SF-202507-00` + 换行 + `8776` 都会查。无编码、`/`、`待补充` 的行不回写，但会打 `row_skip` 日志。不写「检查结果」列。

## 日志（给其它项目集成）

默认同时输出两路，内容相同，每行一条 JSON：

1. **stdout JSONL**：给 Web UI / 管道实时读
2. **日志文件**：默认 `logs/checklist-scmp-sync-YYYYMMDD-HHMMSS.jsonl`，便于事后追溯

每条都有 `event`、`ts`、`message`。除进展事件外，跳过的行会发 `row_skip`（`reason` 为 `empty` / `placeholder` / `other`）。

```bash
# 默认：stdout + logs/ 下自动建文件
python -u run.py --url "https://transsioner.feishu.cn/wiki/xxxx"

# 指定日志路径
python -u run.py --url "https://..." --log-file "D:\logs\scmp-sync.jsonl"

# 只要 stdout，不写文件
python -u run.py --url "https://..." --no-log-file
```

集成方应保存 stdout 或 `--log-file`，不要只依赖终端回滚缓冲；完整明细在最后的 `report` 事件里。

## 退出码

| 码 | 含义 |
|----|------|
| 0 | 全部成功 |
| 1 | 致命错误（未开始扫表或无法定位 SCMP） |
| 2 | 已跑完，但有 sheet 失败 |

## 后端对接建议

1. 用管道按行读 stdout，`json.loads` 每一行。
2. 用 `event=plan` 的 `sheet_count` 和 `sheet_done` 的 `index/total` 画进度。
3. `message` 可直接进日志面板。
4. 收到 `done` 后把进度打满；收到 `report` 后保存完整结果。同时保存 `--log-file`（默认 `logs/`），不要只靠终端历史。
5. 先 `--dry-run`，用户确认后再去掉该参数真正写表。

Python 读流示例：

```python
import json, subprocess, sys

proc = subprocess.Popen(
    [sys.executable, "-u", "run.py", "--url", url, "--dry-run"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True,
    encoding="utf-8",
    bufsize=1,
)
for line in proc.stdout:
    event = json.loads(line)
    # 推给 WebSocket / SSE
    print(event.get("message"), flush=True)
proc.wait()
```

## 单元测试

```bash
python -m unittest discover -s tests -v
```
