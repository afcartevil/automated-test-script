---
name: flow_power_game_background
description: 游戏场景后台应用：四步排查（自启动/内存/下载/GC 风暴）与唤醒交叉分析。
---
## 功能描述
flow 步骤 9。在游戏测试时段 `T_game` 内按四步排查后台应用行为；并保留唤醒/服务聚合分析。

## 分析流程

**输入**：events log、main log。

| 步骤 | 名称 | 日志源 | 关键词 |
|------|------|--------|--------|
| 1 | 后台自启动 | events | `am_proc_start` / `am_proc_died` / `am_schedule_service_restart` |
| 2 | 内存占用 | events | `am_pss`（PSS÷1000000≈MB） |
| 3 | 后台下载 | main | `Download`；含 `GCloud` 为腾讯游戏下载服务 |
| 4 | GC 风暴 | main | `concurrent mark`；>5次/min 或短时密集触发 |

### 步骤 1 统计项
- 各应用 **启动次数**、**死亡次数**
- 启动→死亡 **存活时长**
- **启动后未死亡** 的进程
- `am_schedule_service_restart`：死亡后重新加入重启队列

### 步骤 2 统计项
同一应用 T_game 内 PSS 采样：**avg / min / max MB**

### 步骤 3 判定
`T_game` 内出现 `Download` 或 `GCloud` → 测试期间后台下载

### 步骤 4 判定
GC 次数、间隔；**平均 >5次/min** 或 **短时大量 GC** → GC 风暴

## 配置文件
- `references/keyword-patterns.yaml`
- `references/background-behavior-thresholds.yaml`
- `references/analysis-standards.yaml`

## 输入参数
1. **log_path**（可选）：默认 `flow/game/mobilelog/<APLog_*>`，示例 `.../flow/game/mobilelog/APLog_2026_0622_201151__6`
2. **--window-json**（可选）：默认 `<log_path>/analysis/game_time_window.json`
3. **--game-package**（可选）

## 输出结果
`analysis/game_background.json`：
- **`background_investigation`**：`step1_process_autostart` … `step4_gc_storm`
- **`top_background_packages`** 等原有聚合字段

## 使用方法
```bash
python analysis/domain/power/flow/game/game_background/scripts/game_background.py
```
