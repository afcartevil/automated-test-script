# Modem L2 Data 分析

AI 驱动的主控 + 子 skill 架构。主控负责路由与汇总，具体分析在各子 skill 的 playbook 中执行。

## 维护约定（日常改规则只看 playbook）

| 改什么 | 改哪个文件 |
|--------|-----------|
| 主控路由 / 关键词 / 汇总 | `references/playbook.md` |
| manifest 输出结构 | `references/output-schema.md` |
| 某子场景分析步骤 / 关键字 / 输出 | `sub_skills/<id>/references/playbook.md` |
| 工具用法 | `AI使用规则.md` |

**不要改**：主控 `SKILL.md`、子 skill `SKILL.md`（除非新建子 skill 或改 description 元数据）。

AI 以 **playbook 为分析逻辑唯一来源**；SKILL.md 仅提供入口与边界。

## 目录结构

```
modem-l2-data-analysis/
├── SKILL.md                            # L2 data 主控 skill
├── AI使用规则.md                        # 禁止临时脚本、工具使用规范
├── README.md                           # 本文档
├── references/
│   ├── playbook.md                     # 主控路由与汇总规则
│   ├── output-schema.md                # manifest 输出结构
│   └── pcap_analysis_framework.md      # PCAP 分析通用框架
├── scripts/
│   ├── pcap_analyzer.py                # PCAP 三段式分析（TCP/DNS/重传等）
│   ├── pcap_time_utils.py              # PCAP 时间处理
│   └── run_l2_data_analysis.py         # 占位/调试脚本（非 AI 主路径）
└── sub_skills/
    ├── no_data/                        # 无数据问题
    ├── dl_data/                        # 下行速率慢
    ├── ul_data/                        # 上行速率慢
    ├── lte_reg/                        # LTE 注册
    ├── nr_reg/                         # NR 注册
    ├── 2g3g_reg/                       # 2G/3G 注册
    └── pingpong/                       # 4G/5G 来回切换
```

每个子 skill 包含 `SKILL.md` 与 `references/playbook.md`。

## 执行模型

1. AI 读取主控 `SKILL.md` + `references/playbook.md`，按关键词路由子 skill。
2. AI 逐个读取并执行子 skill 的 `SKILL.md` + `references/playbook.md`。
3. 日志搜索使用 `$log-search-read` skill；PCAP 分析使用 `scripts/pcap_analyzer.py`。
4. AI 汇总结果，按 `references/output-schema.md` 写回 `manifest.analysis.l2_domains.data`。

## 重要规则

- **严禁**在分析过程中创建临时脚本（详见 `AI使用规则.md`）。
- 存在 PCAP txt 文件（`*_cap.txt`）时，相关子 skill 必须执行 PCAP 三段式分析。
- `severity` 全 skill 统一：`critical` | `major` | `minor`。

## 通用工具

### PCAP 分析

```bash
python modem-l2-data-analysis/scripts/pcap_analyzer.py \
  <pcap_txt_file> \
  --problem-start "HH:MM:SS" \
  --problem-end "HH:MM:SS" \
  --protocols tcp dns retrans syn_timeout inventory
```

### 日志搜索

使用 `$log-search-read` skill，按各子 skill playbook 中的关键字逐步搜索。

## 子 Skill 一览

| 子 skill | 适用场景 |
|----------|----------|
| `no_data` | 无法上网、无数据、白屏/无法加载、单 APP 零流量 |
| `dl_data` | 下行速率慢、缓冲卡顿（能加载但慢） |
| `ul_data` | 上行速率慢、上传失败 |
| `lte_reg` | LTE/4G 注册失败 |
| `nr_reg` | NR/5G 注册失败 |
| `2g3g_reg` | 2G/3G 注册失败 |
| `pingpong` | 4G/5G 来回切换 |

## 相关文档

- `references/playbook.md` — 主控路由规则
- `references/output-schema.md` — 输出结构
- `references/pcap_analysis_framework.md` — PCAP 分析框架
- `sub_skills/no_data/references/pcap-analysis-checklist.md` — PCAP 检查清单

## 时间窗口（快速参考）

- 问题前：`[problem_start - 60s, problem_start]`
- 问题中：`[problem_start, problem_end]`
- 问题后：`[problem_end, problem_end + 60s]`
