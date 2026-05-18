---
name: kernel-panic-tracer
description: "分析Android内核panic、kernel oops、驱动crash的根因定位和修复建议"
version: "0.1.0"
module: kernel-driver
engine: diagnostic
source: manual
status: active
---

# 内核Panic追踪Skill

## 触发条件
kernel panic, 内核崩溃, oops, 驱动crash, driver probe failed, null pointer dereference

## 前置检查
1. 确认内核版本: uname -r
2. 获取panic日志: adb shell dmesg | grep -A 50 'Kernel panic'
3. 确认复现步骤
4. 获取defconfig(可选)

缺少 kernel_version/panic_log/repro_steps 时停止分析。

## 分析协议

Step 1: 从panic日志提取PC/LR/Call Trace/寄存器状态
Step 2: 层级判定(Driver→Subsystem→Core)
Step 3: 产出报告(根因层级/修复类型/严重程度/根因描述≥50字/修复建议≥30字)

## 约束文件引用
- constraints/kernel-driver/module.yaml
- constraints/kernel-driver/bug-analysis.yaml
