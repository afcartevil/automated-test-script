---
name: telephony-version-adapter
description: "Android通信模块版本升级适配助手，支持AOSP Diff分析、API迁移规则匹配、批量Patch生成"
version: "0.1.0"
module: telephony
engine: adaptation
source: manual
status: active
---

# 通信模块版本适配Skill

## 触发条件
版本升级, Android N→N+1, AOSP适配, API迁移, 接口变更, 废弃API替换

## 适配协议

Step 1: 加载约束 — 读取 constraints/telephony/version-adaptation.yaml
Step 2: AOSP Diff分析 — 提取API/接口/行为/废弃API变更
Step 3: 影响面评估 — 定位受影响代码文件
Step 4: 策略分类 — 全自动(>95%) / 半自动(70-95%) / 人工(<70%)
Step 5: Patch生成 — API替换/import更新/null check/注解添加
Step 6: 验证 — 编译100%通过 + 回归≥95%

## 质量红线
- 不能删除传音自研业务逻辑
- 新增API必须有@RequiresApi注解
- 废弃API迁移必须grep确认零残留
- 不能引入新编译警告

## 约束文件引用
- constraints/telephony/version-adaptation.yaml
- constraints/shared/api-migration-rules/telephony-migration.yaml
- constraints/telephony/code-adaptation.yaml
