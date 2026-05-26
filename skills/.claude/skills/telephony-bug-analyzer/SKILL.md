---
name: telephony-bug-analyzer
description: "分析Android telephony模块的Bug，包括通话、短信、数据连接、VoLTE/VoWiFi问题的根因定位和修复建议"
version: "0.1.0"
module: telephony
engine: diagnostic
source: manual
status: active
funcType: "AI故障分析"
category: "通信"
---

# 通信模块Bug分析Skill

## 触发条件
telephony bug, 通话异常, 短信失败, 数据连接, VoLTE掉话, VoWiFi问题, SIM卡异常, call drop, SMS failure, RIL错误

## 前置检查（必须按顺序完成）

1. 确认Modem固件版本: getprop gsm.version.baseband
2. 确认Android版本: getprop ro.build.version.release
3. 确认设备型号: getprop ro.product.model
4. 收集logcat: adb logcat -d -b radio,main,system
5. 确认复现步骤: 由用户/Bug报告提供

缺少 modem_firmware_version/repro_steps/logcat 中的任意一项时，立即停止分析并要求用户补充。

## 分析协议

### Step 1: 层级判定（严格按此顺序）

通话/短信/数据问题 → Framework层检查(RILJ层检查 → RILC层检查 → Modem层检查

### Step 2: 根因确认

证据强度: 强(logcat异常堆栈/代码逻辑错误/错误码匹配) / 中(日志异常模式/代码推导/已知pattern) / 弱(经验推断/平台类比，必须标注[SPECULATIVE])
根因判定必须基于强或中等证据。

### Step 3: 产出报告

必须产出: 复现概率(always/frequent/occasional/rare), 根因层级(Framework/RILJ/RILC/Modem/Network), 影响范围(单机型/系列机型/全平台), 修复类型(code_change/config_change/firmware_upgrade/network_side), 严重程度(critical/high/medium/low), 根因描述(≥50字), 修复建议(≥30字)

## 安全红线
通话可能被窃听 → 标记critical，通知安全团队
涉及SIM卡密钥/鉴权 → 标记critical，结果仅限指定接收人
可能导致网络拥塞/DoS → 标记high

## 约束文件引用
- constraints/telephony/module.yaml
- constraints/telephony/bug-analysis.yaml
- constraints/telephony/code-adaptation.yaml
- constraints/shared/coding-standards.yaml
