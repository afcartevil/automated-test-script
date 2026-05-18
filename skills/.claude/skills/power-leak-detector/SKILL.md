---
name: power-leak-detector
description: "分析Android设备功耗异常、WakeLock泄漏、电池续航问题的根因定位"
version: "0.1.0"
module: power-mgmt
engine: diagnostic
source: manual
status: active
---

# 功耗泄漏检测Skill

## 触发条件
功耗异常, 耗电快, WakeLock泄漏, 续航问题, 休眠唤醒异常, 待机电流高

## 前置检查
1. Battery Historian数据: adb shell dumpsys batterystats
2. Bugreport(可选)
3. 复现步骤

## 分析协议
Step 1: 功耗分类(Application→Framework→HAL/Kernel)
Step 2: 产出报告(根因层级/修复类型/严重程度/根因描述≥50字/修复建议≥30字)

## 约束文件引用
- constraints/power-mgmt/module.yaml
- constraints/power-mgmt/bug-analysis.yaml
