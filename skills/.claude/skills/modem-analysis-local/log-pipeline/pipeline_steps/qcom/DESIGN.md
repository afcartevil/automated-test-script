# 高通 Modem Log 导出工具

## 1. 概述

将高通 QXDM/QUTS 格式的 modem log 文件（`.qmdl2`、`.qdss`）导出为可读文本文件。

**依赖**: QUTS（Python API 默认 `C:/Program Files/Qualcomm/QUTS/Support/python`；旧版在 `C:/Program Files (x86)/Qualcomm/QUTS/Support/python`）、Python 3.8+

---

## 2. 快速开始

```bash
# 导出所有类型
python export_modem_log.py mdlog/

# 导出指定类型
python export_modem_log.py mdlog/ --type log

# 按 ID 过滤（必须配合 --type）
python export_modem_log.py mdlog/ --type log --id 0x184E

# 内容关键词搜索（普通字符串，不区分大小写）
python export_modem_log.py mdlog/ --search vsim_dbg

# 内容关键词搜索（正则表达式，需加 --regex）
python export_modem_log.py mdlog/ --search "SUB [01]" --regex
python export_modem_log.py mdlog/ --search "vsim_dbg:.*ENTER" --regex
```

---

## 3. 命令行参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `input` | 输入文件或目录（必填） | `mdlog/` |
| `output` | 输出目录（可选，默认 `<input>_output`） | `D:\output\` |
| `--type` | Item Type（可多次使用，支持逗号分隔） | `--type log,qtrace` |
| `--id` | 过滤 ID，与 `--type` 按顺序配对 | `--id 0x184E,0xB132` |
| `--search` | 内容关键词搜索（不区分大小写） | `--search vsim_dbg` |
| `--regex` | 将 `--search` 的关键词作为正则表达式处理 | `--search "SUB [01]" --regex` |
| `--quts-path` | 手动指定 QUTS 路径 | `--quts-path "C:\..."` |

---

## 4. Item Type 说明

QUTS 中每条 Diag 数据包属于一种 Item Type，对应 `DiagPacketType` 枚举值。

| `--type` 参数 | 类型名称 | QXDM 中的分类 | ID 格式示例 |
|--------------|---------|--------------|------------|
| `all` | 所有类型（默认） | - | - |
| `log` | Log Packets | Log Packets | `0x184E`（十六进制） |
| `qtrace` | QTrace | QTrace | `107/1`（ClientID/BufferID） |
| `event` | Event Reports | Event Reports | `1001`（十进制） |
| `debug-msg` | Debug Messages | F3 Messages | `3007/2`（SubsysID/Level） |
| `diag-request` | Diag Requests | Diag Requests | `0x4B`（命令码） |
| `diag-response` | Diag Responses | Diag Responses | `0x4B` |
| `subsys-request` | Subsystem Requests | Subsystem Requests | `75/1`（CmdCode/SubCmd） |
| `subsys-response` | Subsystem Responses | Subsystem Responses | `75/1` |
| `subsysv2-request` | SubsystemV2 Requests | SubsystemV2 Requests | - |
| `subsysv2-response` | SubsystemV2 Responses | SubsystemV2 Responses | - |
| `subsysv2-dresp` | SubsystemV2 Delayed Responses | SubsystemV2 Delayed Resp | - |
| `qsh-metric` | QSH Metrics | QSH | - |
| `qsh-event` | QSH Events | QSH | - |

> **注意**：
> - Log Packet ID 以 `0x` 开头（十六进制）
> - QTrace ID 格式为 `ClientID/BufferID`，如 `107/1`
> - Event ID 为纯十进制整数
> - 不同 ID 格式不可混用于同一 `--type`

---

## 5. `--type` 与 `--id` 配对规则

`--id` 必须与 `--type` 成对使用（不能单独使用 `--id`）。多个 `--type` 和 `--id` 按出现顺序一一对应：

| 命令 | 配对结果 |
|------|---------|
| `--type log --id 0x184E` | `log → [0x184E]` |
| `--type log --id 0x184E,0xB132` | `log → [0x184E, 0xB132]`（同一类型多个 ID） |
| `--type log --type qtrace --id 0x184E` | `log → [0x184E]`，`qtrace → [0x184E]`（共用 ID） |
| `--type log --id 0x184E --type qtrace --id 107/1` | `log → [0x184E]`，`qtrace → [107/1]`（分别指定） |
| `--type log,qtrace --id 0x184E --id 107/1` | `log → [0x184E]`，`qtrace → [107/1]` |

---

## 6. 输出格式

### 文件名规则

```
<原始文件名>[_<类型>][_<ID>][_search_<关键词>].txt
```

| 命令 | 输出文件名 |
|------|----------|
| `mdlog/` | `diag_log_20260326_...txt` |
| `--type log` | `diag_log_20260326_..._log.txt` |
| `--type log --id 0x184E` | `diag_log_20260326_..._log_0x184E.txt` |
| `--type log,qtrace` | `diag_log_20260326_..._log_qtrace.txt` |
| `--type log --id 0x184E --type qtrace --id 107/1` | `diag_log_20260326_..._log_qtrace_ids.txt` |
| `--search vsim_dbg` | `diag_log_20260326_..._search_vsim_dbg.txt` |

### 数据包格式（默认单行，供 log-search-read）

Pipeline 默认 **每条 Diag 包一行**：`Summary` / `Parsed` 内的换行会压成空格，字段之间用 ` | ` 分隔。

```
[<类型>] [<时间戳>] ID=<ID>[ Sub=<SubID>]  <数据包名称> | Summary: <摘要> | <解析详情…>
```

示例（`--type all` 导出）：
```
[RESPONSE] [2026/05/21 07:46:45.377500] ID=125  Extended Message Report Config Response | Summary: Length: 8 Success
[QTRACE] [2026/03/26 06:14:17.030237] ID=42/0  MMODE/STRM/High/CM | Summary: [cmph.c 14898] PH_PROC: vsim_dbg: sub 0 | File Name = cmph.c Line Number = 14898 Format = PH_PROC: vsim_dbg: ...
```

需要 QXDM 风格多行可读格式时，设置环境变量 `QCOM_EXPORT_MULTILINE=1` 或 CLI `--multiline`。

> `Sub=X` 仅在 QUTS API 提供 `subscriptionId` 时显示（如 Log Packet）；QTrace 通常无此字段。

---

## 7. 运行示例

### 示例 1：导出所有数据包

```bash
python export_modem_log.py mdlog/
```

```
[配置] 类型-ID 配对: [('all', '所有')]
找到 2 个 log 文件，输出目录：D:\MDLogExport\mdlog_output
[OK] QUTS 客户端已初始化（后处理模式）

======================================================================
  输入: D:\MDLogExport\mdlog\diag_log_20260326_...qmdl2
  输出: D:\MDLogExport\mdlog_output\diag_log_20260326_...txt
======================================================================
  [OK] LogSession 已加载  (2.8s)
  [.] 过滤: 所有类型, 所有 ID
  [..] 等待 DataView 构建完成...
  [OK] 共匹配 1523847 个数据包  (8.4s)
  [..] 导出进度: 1523847/1523847  (100.0%)
  [OK] 写入完成  (62.3s)

======================================================================
导出完成：成功 2 个，失败 0 个
```

### 示例 2：按 ID 过滤 Log Packet

```bash
python export_modem_log.py mdlog/ --type log --id 0x184E
```

```
[配置] 类型-ID 配对: [('log', ['0x184E'])]
  [.] 过滤: Log Packets(ID=['0x184E'])
  [OK] 共匹配 27562 个数据包  (5.2s)
```

### 示例 3：多类型分别指定不同 ID

```bash
python export_modem_log.py mdlog/ --type log --id 0x184E,0xB132 --type qtrace --id 107/1
```

```
[配置] 类型-ID 配对: [('log', ['0x184E', '0xB132']), ('qtrace', ['107/1'])]
  [.] 过滤: Log Packets(ID=['0x184E', '0xB132']), QTrace(ID=['107/1'])
  [OK] 共匹配 31089 个数据包  (6.1s)
```

### 示例 4：内容搜索

```bash
python export_modem_log.py mdlog/ --search vsim_dbg
```

```
[配置] 类型-ID 配对: [('all', '所有')]
       搜索关键词: 'vsim_dbg' (普通匹配)
  [OK] 共匹配 799843 个数据包  (9.1s)
  [OK] 写入完成  (22.3s)，匹配 1189 个包含 'vsim_dbg' 的数据包
```

### 示例 5：正则表达式搜索

需要加 `--regex` 标志来启用正则模式，否则 `--search` 的内容始终作为普通字符串处理：

```bash
# 匹配 SUB 0 或 SUB 1
python export_modem_log.py mdlog/ --search "SUB [01]" --regex

# 匹配 vsim_dbg 后紧跟 ENTER 的行
python export_modem_log.py mdlog/ --search "vsim_dbg:.*ENTER" --regex

# 匹配特定错误码
python export_modem_log.py mdlog/ --search "error.*code=\d+" --regex

# 不加 --regex 时，特殊字符视为普通字符串原样匹配
python export_modem_log.py mdlog/ --search "cm_slot_type= 1"
```

```
[配置] 类型-ID 配对: [('all', '所有')]
       搜索关键词: 'SUB [01]' (正则匹配)
  [OK] 写入完成  (18.5s)，匹配 2341 个数据包
```

### 示例 6：组合 type + id + search

```bash
python export_modem_log.py mdlog/ --type qtrace --id 107/1 --search vsim_dbg
```

---

## 8. 常见错误

| 错误信息 | 原因 | 解决方式 |
|---------|------|---------|
| `无法导入 QUTS 模块` | QUTS 未安装或路径错误 | 确认安装，或设置 `--quts-path` |
| `使用 --id 时必须指定 --type` | 单独使用 `--id` 而不带 `--type` | 添加具体 `--type`，如 `--type log` |
| `--type 和 --id 的数量不匹配` | `--type` 和 `--id` 个数不对应 | 见第 5 节配对规则 |
| `未找到任何数据包` | ID 不存在或文件类型不匹配 | 检查 ID 是否正确；`.qmdl2` 通常不含 QTrace |
| `AppException: Could not determine Log ID` | ID 格式与 type 不匹配 | 如 QTrace ID `107/1` 不能用于 `--type log` |

---

## 9. 架构说明

```
CLI (argparse)
  └─> parse_type_id_pairs()     解析 type/id 配对
  └─> collect_log_files()       扫描输入文件
  └─> QutsClient (POST_PROCESSING)
        └─> open_log_session()  打开 .qmdl2 / .qdss
        └─> build_packet_filter()  构建 DiagPacketFilter
        └─> DataView + DataViewWatcher  等待数据视图就绪
        └─> getDataViewItems()  分批读取（5000 包/批）
              └─> format_packet()  格式化 + 搜索过滤
              └─> 写入 .txt 文件
```

### 关键 QUTS API 规则

- `DiagPacketFilter.idOrNameMask` 中设置**空列表 `[]` 会过滤掉该类型**（非全部匹配）
- 全匹配使用 `DiagIdFilterItem(regexFilter=".*")`
- 指定 ID 使用 `DiagIdFilterItem(idOrName="0x184E")`
- `diagFilter` 不能为 `None`，否则抛出 `Missing diag filter definition`

---

## 10. 参考

- QXDM User Guide（`QXDMUserGuide.pdf`）
- QUTS Python API：`C:/Program Files/Qualcomm/QUTS/Support/python/Common/ttypes.py`
