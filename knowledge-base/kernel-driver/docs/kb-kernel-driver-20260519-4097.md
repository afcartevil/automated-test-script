---
author: system
category: architecture
confidence: 0.8
created_at: '2026-05-19T09:47:23Z'
id: kb-kernel-driver-20260519-4097
module: kernel-driver
referenced_by: []
source: source_analyzed
tags:
- constraint
- kernel-driver
- yaml
title: bug-analysis
type: tech_doc
updated_at: '2026-05-19T09:47:23Z'
---

```yaml
preconditions:
  required_info:
    - name: "kernel_version"
      description: "内核版本"
      how_to_get: "uname -r"
      required: true
    - name: "panic_log"
      description: "Kernel panic日志"
      how_to_get: "adb shell dmesg | grep -A 50 'Kernel panic'"
      required: true
      error_msg: "缺少panic日志，无法进行内核Bug分析。"
    - name: "repro_steps"
      description: "复现步骤"
      how_to_get: "由用户/Bug报告提供"
      required: true
    - name: "defconfig"
      description: "内核配置文件"
      how_to_get: "cat /proc/config.gz | gunzip"
      required: false

analysis_rules:
  layer_detection_order:
    1:
      layer: "Driver"
      check: "检查驱动probe/初始化是否失败"
      indicators:
        - pattern: ".*driver.*probe failed.*"
        - pattern: ".*unable to handle kernel.*"
    2:
      layer: "Subsystem"
      check: "检查子系统层（regmap/clk/pinctrl）"
      indicators:
        - pattern: ".*regmap.*error.*"
        - pattern: ".*clk.*failed.*"
    3:
      layer: "Core"
      check: "检查内核核心（scheduler/mm/fs）"
      indicators:
        - pattern: ".*BUG:.*"
        - pattern: ".*kernel NULL pointer.*"
  prohibited:
    - "在未确认panic调用栈的情况下给出修复方案"
    - "修改排除范围内的驱动代码"
    - "在未验证defconfig启用选项的情况下建议配置变更"
  required_outputs:
    - name: "root_cause_layer"
      type: "enum"
      values: ["Driver", "Subsystem", "Core", "Hardware", "Unknown"]
    - name: "fix_type"
      type: "enum"
      values: ["code_change", "config_change", "dtb_change", "firmware_upgrade", "further_investigation"]
    - name: "severity"
      type: "enum"
      values: ["critical", "high", "medium", "low"]
    - name: "root_cause_description"
      type: "text"
      min_length: 50
    - name: "fix_suggestion"
      type: "text"
      min_length: 30

evaluation:
  bug_analysis_accuracy_target: 0.80
  test_dataset: eval-data/

```