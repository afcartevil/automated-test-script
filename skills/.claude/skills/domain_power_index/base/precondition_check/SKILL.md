---
name: base_precondition_check
description: 自动检测测试前置条件
---
## 适用场景
从 mainlog 日志提取设备状态，与 JIRA 前置条件对比验证。支持检测飞行模式、数据流量、WIFI、蓝牙、GPS、NFC、SIM 卡、自动旋转屏幕、亮度和音量等级。多 mainlog 文件自动按时间顺序合并后检测。

## 检测项目
- **飞行模式**：检测设备是否开启飞行模式
- **数据流量**：检测移动数据连接状态
- **WIFI**：检测WIFI连接状态
- **蓝牙**：检测蓝牙开启状态
- **GPS**：检测定位服务开启状态
- **NFC**：检测NFC功能开启状态
- **SIM卡**：检测SIM卡是否插入
- **自动旋转屏幕**：检测屏幕自动旋转功能状态
- **亮度等级**：检测屏幕亮度值
- **音量等级**：检测设备音量格数

## 输入参数
1. **描述信息**：JIRA单的测试步骤信息，包含前置条件部分
2. **保存目录**：结果保存目录，脚本会在该目录下生成报告文件

## 输出说明
1. 前置条件是否满足的结果（"前置条件满足"或"前置条件不满足"）
2. 生成详细的前置条件检查报告，包含：
   - 检查结果摘要
   - 预期前置条件列表
   - 实际检测结果
   - 不满足的项（如果有）
3. 结果保存到指定目录下的 `precondition_check_result.txt` 文件

## 执行方式

本脚本使用 Python 标准库，无需额外安装依赖。

```bash
# 语法：python scripts/precondition_check.py <description> <save_dir>
python scripts/precondition_check.py "A)Preconditions：数据（开） WIFI（关） 蓝牙（关） GPS（关） NFC（关） 飞行模式（关） 插入一张SIM卡 自动旋转（关）" "temp/<DATE>/<KEY>"
```

## 工作原理
1. 从JIRA描述中提取前置条件信息
2. 在指定目录中递归查找mainlog文件
3. 如果找到多个mainlog文件，按文件修改时间排序并合并
4. 从合并后的mainlog内容中检测设备各状态
5. 比较实际检测结果与预期前置条件
6. 生成检查报告并保存到指定目录

## 注意事项
- 当找到多个mainlog文件时，会按文件修改时间排序并合并后进行检测
- 对于亮度和音量，暂时只检查是否检测到，不做具体值的比较
- 如果未找到mainlog文件，会返回"前置条件不满足"的结果
- 报告保存到 `temp/<DATE>/<KEY>/analysis/precondition_check_result.txt`（`save_dir` 为工作区根、相对 `temp/...` 或 JIRA KEY）

