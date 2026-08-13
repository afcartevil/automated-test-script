# L2 Data 分析 AI 使用规则

## 维护约定

- **分析逻辑、步骤、关键字、判定规则、输出字段**：只改各层 `playbook.md`，不改 `SKILL.md`。
- **主控路由关键词**：只改 `references/playbook.md` §2。
- **输出 JSON 结构**：只改 `references/output-schema.md`。
- AI 执行时 **必须先读 playbook**，不得仅依赖 SKILL.md 中的摘要。

---

## 强制规则：严禁在分析过程中创建新脚本

**任何 L2 data skill 分析都严禁在分析过程中创建新的脚本。**

适用范围：`no_data` / `dl_data` / `ul_data` / `lte_reg` / `nr_reg` / `2g3g_reg` / `pingpong` 以及未来所有 L2 data 相关分析。

### 禁止创建的脚本类型

| 类型 | 示例 |
|------|------|
| 分析脚本 | `analyze_xxx.py`、`analyze_youtube_issue.py` |
| 检查脚本 | `check_xxx.py`、`check_dns_failure.py` |
| 测试脚本 | `test_xxx.py`、`verify_xxx.py` |
| 任何临时脚本 | 任何以 `.py` 结尾的新文件 |

### 为什么有这条规则

- 避免项目根目录充满临时脚本，难以维护
- 确保所有分析使用相同工具和方法，结果可对比
- 直接调用工具，不需要每次重复实现

---

## 可用工具

### 1. PCAP 分析工具（主要入口）

**文件**: `modem-l2-data-analysis/scripts/pcap_analyzer.py`

**功能**:
- TCP 连接分析（三段式：SYN/FIN/RST）
- DNS 查询分析（三段式：query / 成功响应 / 失败响应 / 超时）
- TCP 重传分析（三段式）
- 自动验证时间范围、计算时间偏移、创建三段式时间窗口

**命令行使用**:
```bash
python modem-l2-data-analysis/scripts/pcap_analyzer.py \
  <pcap_txt_file> \
  --problem-start "HH:MM:SS" \
  --problem-end "HH:MM:SS" \
  --protocols tcp dns retrans syn_timeout inventory
```

**参数说明**:

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `pcap_file` | PCAP txt 文件路径（必需） | — |
| `--problem-start` | 问题开始时间（必需） | — |
| `--problem-end` | 问题结束时间（必需） | — |
| `--margin-before` | 问题前窗口大小（秒） | 60 |
| `--margin-after` | 问题后窗口大小（秒） | 60 |
| `--protocols` | 要分析的协议 | `tcp dns retrans syn_timeout inventory` |

### 2. PCAP 时间工具

**文件**: `modem-l2-data-analysis/scripts/pcap_time_utils.py`

**功能**:
- `get_pcap_time_range()` — 完整扫描文件，获取首包/末包时间（无行数限制）
- `calculate_time_offset()` — 计算文件名时间与内容时间的偏移
- `verify_time_coverage()` — 验证 PCAP 是否覆盖问题前/中/后三段
- `TimeWindow.create_three_phase()` — 一键创建三段式时间窗口

**适用场景**: 所有需要单独处理 PCAP 时间的场景（通常 `pcap_analyzer.py` 已内置，无需单独调用）。

### 3. 日志搜索工具

**Skill**: `log-search-read`

**功能**: 搜索日志文件、读取日志片段、列出日志目录。

**适用场景**: 所有需要搜索 AP log / modem log 的场景。使用 `$log-search-read` skill，按各子 skill playbook 中的关键字逐步搜索。

**相关文档**:
- `references/pcap_analysis_framework.md` — PCAP 分析通用框架
- `sub_skills/no_data/references/pcap-analysis-checklist.md` — PCAP 检查清单

---

## 正确的分析流程

```
分析过程 = 调用工具 + 解读输出 + 生成报告
分析过程 ≠ 写新脚本
```

### Step 1：调用 pcap_analyzer.py

```bash
python modem-l2-data-analysis/scripts/pcap_analyzer.py \
  LOG/AI/DUT-FAIL-X6887-ZAIN-Good-SIGNAL-debuglogger/wireshark_export_txt/tcpdump_NTLog_V2_2026_0428_133642_start_1_cap.txt \
  --problem-start "13:42:13" \
  --problem-end "13:43:08" \
  --protocols tcp dns retrans syn_timeout inventory
```

### Step 2：解读输出

工具自动输出：
- PCAP 文件时间范围验证
- 时间偏移计算
- 三段式时间窗口（问题前/中/后）
- TCP 连接分析
- DNS 查询分析（含失败响应和超时）
- TCP 重传分析

### Step 3：根因分析

1. 对比基线（问题前 vs 问题中）
2. 追踪恢复（问题中 vs 问题后）
3. 判断根因

### 示例输出与解读

```
【问题前窗口】 18:41:15 ~ 18:42:15
  FIN 包数: 32

【问题中窗口】 18:42:15 ~ 18:43:10
  FIN 包数: 6
  DNS 失败响应: 12  (NXDOMAIN/SERVFAIL/REFUSED 等)
  最后失败响应: 18:42:47

【问题后窗口】 18:43:10 ~ 18:44:10
  DNS 失败响应: 0
```

解读：
- FIN 从 32 → 6，下降 81%，连接正常关闭大幅减少
- DNS 失败最后时间 18:42:47，问题结束 18:43:10，相差 23 秒 → DNS 失败是直接原因

---

## 错误 vs 正确对比

### 错误做法

```python
# 在分析过程中临时创建脚本
# analyze_youtube_white_screen.py

with open('LOG/AI/xxx/tcpdump.txt') as f:
    for line in f:
        if "DNS" in line and "13:42" in line:
            print(line)
```

问题：硬编码路径和时间、只适用于单个问题、无法复用、污染目录。

### 正确做法

```bash
python modem-l2-data-analysis/scripts/pcap_analyzer.py \
  LOG/AI/xxx/tcpdump.txt \
  --problem-start "13:42:13" \
  --problem-end "13:43:08" \
  --protocols dns
```

---

## 需要新功能时的处理方式

如果现有工具确实不满足需求，必须遵守以下规则后才能创建新脚本：

1. **在分析开始之前创建**，不能在分析过程中临时创建
2. **必须通用**，适用于该分类下所有问题，不能针对具体问题硬编码
3. **放置位置**：`modem-l2-data-analysis/scripts/` 目录，不能放在项目根目录
4. **命名规范**：使用通用名称（如 `pcap_http_analyzer.py`），不使用具体问题名称
5. **更新文档**：同步更新本文件和 `README.md` 中的工具说明

扩展示例（在 `pcap_analyzer.py` 中添加新分析器）：

```python
class HTTPAnalyzer(PCAPAnalyzer):
    """HTTP 分析器"""

    def analyze(self):
        # 实现 HTTP 分析逻辑
        pass

    def print_results(self):
        # 打印 HTTP 分析结果
        pass
```

---

## AP / main_log 关键字速查（按 playbook 步骤）

分析时 **必须用 `$log-search-read`** 在问题时间窗内搜索；下表为各 Setup 的推荐关键字（非穷尽）。

### no_data — Setup 1（AP）

| 步骤 | 关键字 / 模式 | 用途 |
|------|----------------|------|
| 1.1 | `onInternetValidationStatusChanged`、`+VALIDATED`、`isNetworkConnected`、`LinkUpBandwidth` | 网络是否已验证 |
| 1.2 | `PROBE_DNS`、`UNSOL_DATA_CALL_LIST_CHANGED`、`mDataRegState`、`resolv_cache_lookup: Waiting` | 数据业务 / DNS 队列 |
| 1.3 | `doRecovery`、`dataStallAction` | 自愈是否触发 |
| 1.4 | `TLS Handshake failed`、`SSL_connect write error`、`Connecting to {`、`Disconnecting {` | Private DNS / DoT |
| 1.5 | `TranApkDataController`、`flow_up`、`flow_down`、`CronetUrlRequest`、`ERR_TIMED_OUT`、`YT.onesie` | 应用零流量 / 超时 |

### no_data — Setup 2.4（PCAP）

| 类型 | 关键字 / 工具参数 |
|------|-------------------|
| 通用 | `pcap_analyzer.py --protocols tcp dns retrans syn_timeout` |
| DoT | `853`、`domain-s(853)`、`DNS-over-TLS` |
| HTTPS | `Client Hello`、`SNI=`、`youtubei.googleapis.com` |
| SYN 超时 | 查看工具输出 `SYN 无响应` 按 IP:端口分组 |

### dl_data — Step 1.5 交叉检查

当 Step 4 无线指标正常或 modem 未导出时，复用 no_data Setup 1.4 / 1.5 关键字；**重点看 `flow_down`**。

### ul_data — Step 1.5 交叉检查

当 Step 4 无线指标正常或 modem 未导出时，复用 no_data Setup 1.4 / 1.5 关键字；**重点看 `flow_up`**（同时对照 `flow_down` 以区分真 UL 慢 vs 全局无数据）。

### 常见 APP 包名（过滤 uid / 日志）

| APP | 包名 |
|-----|------|
| YouTube | `com.google.android.youtube` |
| TikTok | `com.zhiliaoapp.musically` / `com.ss.android.ugc.trill` |
| Instagram | `com.instagram.android` |
| Netflix | `com.netflix.mediaclient` |

---

## 速查

| 场景 | 应该做 | 不应该做 |
|------|--------|---------|
| 分析 PCAP | 调用 `pcap_analyzer.py` | 手动写解析脚本 |
| 搜索日志 | 使用 `log-search-read` skill | 写 grep 脚本 |
| 处理时间 | 调用 `pcap_time_utils.py` | 手动计算时间偏移 |
| 需要新功能 | 分析前创建通用工具 | 分析中临时创建脚本 |
| 生成报告 | 直接写 Markdown | 写脚本生成报告 |
