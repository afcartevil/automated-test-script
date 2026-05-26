---
name: carrier-porting-assistant
description: "运营商需求移植助手，支持运营商定制需求的分析、代码移植、合规检查"
version: "0.1.0"
module: telephony
engine: adaptation
source: manual
status: active
funcType: "AI自动化适配"
category: "通信"
---

# 运营商需求移植Skill

## 触发条件
运营商移植, carrier porting, VoWiFi, 分钟提醒, USSD, STK定制, Airtel, Vodafone, MTN

## 移植协议

Step 1: 加载约束 — 读取 constraints/telephony/carrier-porting.yaml
Step 2: 需求解析 — 定位源代码/配置/依赖关系
Step 3: 策略分类 — 自动(>0.85) / 半自动(0.70-0.85) / 人工(<0.70)
Step 4: 代码移植 — Carrier overlay/carrier_config/CARRIER注释
Step 5: 合规检查 — 编译/generic回归/定制测试/合规标准

## 质量红线
- 不能影响generic基础功能
- 不硬编码运营商参数
- 所有定制代码必须有CARRIER注释标记
- 必须通过CarrierConfigManager标准机制

## 约束文件引用
- constraints/telephony/carrier-porting.yaml
- constraints/telephony/code-adaptation.yaml
- constraints/shared/android-platform.yaml
