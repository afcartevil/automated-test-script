# Manifest 输入契约（字段说明）

> 本文档描述本 skill 消费的 `job_manifest.json` 字段约定。
> Schema 文件位置：`schemas/job_manifest.schema.json`。

## 一、隐式约定

| 约定 | 说明 |
|---|---|
| **manifest 所在目录 = workspace 根** | 分析使用的 manifest 应在 `{WORKSPACE_ROOT}/{issue_key}/job_manifest.json`（工作区根）。若解压后多包一层 `{issue_key}/`，上提到工作区根后再分析 |
| **所有路径字段都是相对路径** | 相对于 manifest 所在目录，POSIX 风格（正斜杠） |
| **schema_version** | 当前 `1.1.0`，不向后兼容时会升版本 |

## 二、字段总览

```jsonc
{
  "schema_version": "1.1.0",          // 必填，固定 "1.1.0"
  "issue_key": "OS162-37733",         // 必填

  "final_log_root": "final_logs",     // 必填，相对 manifest 目录；固定为 "final_logs"

  "jira": {                           // 必填，全部子字段都在 schema 里强制存在（允许空字符串）
    "summary":          "...",        // 必填
    "description":      "...",        // 必填
    "comments_text":    "...",        // 必填
    "test_steps":       "...",        // 必填（启发式抽取，未命中则空字符串）
    "expected_result":  "...",        // 必填（同上）
    "actual_result":    "...",        // 必填（同上）
    "time_window": {                  // 必填
      "start": null,                  //  ↳ ISO 时间字符串 或 null
      "end":   null
    },
    "url_roles":         { "<url>": "DUT" | "REF" },
    "affected_versions": ["..."],
    "urls_by_type": {                 // 必填，4 个 key 必须存在
      "box":           [],
      "feishu_file":   [],
      "network_share": [],
      "http_direct":   []
    },
    "time_points":  [ {"value": "2026-04-15 14:04:38", "type": "datetime"}, ... ],
    "platform":     "CN6",            // 必填字段，允许空字符串
    "chip_vendor":  "MTK",            // 必填字段，允许空字符串
    "chip_model":   "MT6789",         // 必填字段，允许空字符串
    "sw_version":   "..."             // 必填字段，允许空字符串
  },

  "trace_exports": {                  // 必填
    "aggregated_files": {             // 必填，至少一个分组
      "DUT": {                        //  ↳ 分组名（DUT / REF / ...）
        "ota":     "DUT/ota.txt",     //  ↳ 文件 key → 相对路径
        "ps":      "DUT/ps.txt",
        "system":  "DUT/system.txt",
        "sip":     "DUT/sip.txt",
        "icd":     "DUT/icd.txt",
        "l1":      "DUT/l1.txt",
        "l2":      "DUT/l2.txt",
        "ps_raw":  "DUT/ps_raw.txt"
      },
      "REF": { ... }
    },
    "copied_support_files": {         // 可选
      "DUT": {
        "radio":      ["DUT/radio_log"],
        "main":       ["DUT/main_log"],
        "kernel":     ["DUT/kernel_log_1"],
        "exp_main":   ["DUT/__exp_main.txt"],
        "android_log":["DUT/ANDROID_LOG"],
        "pcap":       ["DUT/wlan_pcap.txt"]
      }
    }
  },

  "downloads":   { ... },             // 上游运行时元数据，本 skill 不依赖
  "extraction":  { ... },             // 同上
  "pcap_export": { ... },             // 同上
  "mddb":        { ... },             // 同上
  "analysis":    { ... },             // 本 skill 自己写入，不在契约约束范围

  "_meta": {                          // 必填
    "updated_at":          "2026-05-13T14:58:01",   // 必填
    "phase1_completed_at": "2026-05-13T14:58:01",
    "phase1_host":         "win-server-01"
  }
}
```

## 三、各层如何使用这些字段

### L0 基础指标
- 输入：`jira.description`、`jira.time_window`、`jira.time_points`、日志文件
- 输出：写入 `manifest.analysis.l0_baseline`

### L1 业务路由
- 输入：`jira.summary` + `jira.description` + L0
- 输出：写入 `manifest.analysis.l1_business`

### L2 各域分析
- 通用输入：`jira.test_steps` / `jira.expected_result` / `jira.actual_result` / `jira.time_window`、L0、L1、日志
- **L2-EE 特别需要**：`jira.platform` / `jira.chip_vendor` / `jira.chip_model` / `jira.sw_version`（飞书表格写入字段）
- 输出：写入 `manifest.analysis.l2_domains.{domain}`

### L3 汇总
- 输入：L0/L1/L2 全部结果
- 输出：写入 `manifest.analysis.l3_conclusion` + `manifest.analysis.final_report`

## 四、AI 调用日志的标准方式

通过 `log-search-read` 工具，绝对不要直接拼绝对路径：

```bash
# 正确做法 ✅
python analysis_skills/log-search-read/scripts/log_search_read.py \
  --manifest /mnt/data_store/OS162-37733/job_manifest.json \
  read --relative-path "DUT/ota.txt"
```

工具会自动从 manifest 解析根目录，AI 只需要提供 manifest 路径 + 相对路径。

## 五、错误处理建议

| 错误类型 | 出现位置 | AI 建议动作 |
|---|---|---|
| `WORKSPACE_ROOT` 未配置 | `run_pipeline.py` / 分析脚本启动期 | 让用户修 `.env` |
| 工作区缺 `job_manifest.json` | Step 0 失败 | 执行 `log-pipeline/run_pipeline.py` 或检查路径 |
| zip 嵌套过深 / 多个 manifest | 解压后校验失败 | 上提目录或重跑日志准备 |
| 关键字段（如 `jira.summary` / `aggregated_files`）缺失 | L0/L1/L2 playbook 读 manifest 时 | 在该层 `gaps` 中记录，降级 `confidence` |
| `jira.platform` 等软字段为空 | 写飞书时 | L2-EE 在写表格时跳过相关关键字，并在 `final_report` 中标注"未能识别平台/芯片" |
| 部分日志文件不存在 | log-search-read 读不到 | 各 playbook 应在 `gaps` 中记录证据缺失 |

## 六、Schema 演进

- 新增非必填字段 → 不需要升版本，向后兼容
- 新增必填字段 / 修改字段语义 → 升 `schema_version`，旧 manifest 在 `package_trace_outputs` 校验阶段报错
- 删除字段 → 升 `schema_version`，并更新本 skill 内各层 playbook
