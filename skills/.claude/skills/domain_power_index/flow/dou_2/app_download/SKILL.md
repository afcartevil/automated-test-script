---
name: flow_power_app_download
description: >-
  从 sys/main log 判定应用下载与安装：灭屏 Usf_Hiber/importantScene speed>100、
  mainlog state:DOWNLOADING、installation completed for。
  用于 DOU 高功耗归因中的下载流量排查；结论须写清时间段、包名、uid/pid、有无安装。
  归属 flow/dou_2（非 power/base）。
---

# flow_power_app_download — 应用下载/安装日志判定（dou_2）

## 输入

| 项 | 说明 |
|----|------|
| DOU high 根 | `...\DOU高功耗文件夹\<项目名>\` |
| APLog | `phone_logs\mobile_log*\mobilelog\APLog_*\` |
| `-d` | 可传 high 根 / `phone_logs` / `mobilelog` / 某个 `APLog_*` |

## 执行流程

1. 扫描 `sys_log*` 亮灭屏区间（Going to sleep / Waking up）
2. 扫 `Usf_Hiber/importantScene` + `speed>100`，**仅保留灭屏命中**
3. 扫 `main_log*` 的 `state:DOWNLOADING` + `Package:`
4. 扫 `installation completed for`
5. 运行 `run_app_download.py` 或 `download_traffic.py` 落盘结论

## 输出

- `<high>\app_download_result.json`
- `<high>\app_download_result.txt`

## 门禁

全流程最后一步执行；结论须写清时间段、包名、uid/pid、有无安装。

## 适用场景

- DOU 高功耗分析中，判断是否存在**应用下载**、**谁在下**、**何时下**、**是否安装完成**
- 仅需读 `APLog` 下 `sys_log*` / `main_log*`，不依赖 cap / pt5

## 判定规则（必须遵守）

1. 查找 **sys log** 关键字：`Usf_Hiber/importantScene`，该行有 `speed`：
   - 仅当 **`speed > 100`** 才计入下载；
   - **且只在灭屏时**才算下载（亮屏命中丢弃）。  
   灭屏判定来自同批 `sys_log` 的 `PowerManagerService: Going to sleep` / `Sleeping` → 灭屏，`Waking up from Asleep` → 亮屏。  
   **只有本条规则要求灭屏**；下面 2、3 不限亮灭屏。
2. 查找 **main log** 关键字：`state:DOWNLOADING`，从同行 `Package:` 取下载包名（及可选 `reason=`）。
3. 查找 **sys log** 关键字：`installation completed for`，可见什么应用安装完成。

## 字段含义（写结论前必读）

| 名称 | 是什么 | 从哪来 | 注意 |
|------|--------|--------|------|
| **uid** | Android **应用身份 ID** | `Usf_Hiber/... uid:10297`；`u0a297` → uid=`10000+297` | 回答「谁在下」的主标识 |
| **pid** | **进程号** | `Start proc <pid>:<package>/u0aXXX` | 不是 Usf_Hiber 行头数字 |
| **speed** | 流量活跃速度 | `speed :168` | **仅 `>100` 且灭屏** 才计入 Usf_Hiber 下载 |
| **package** | 应用包名 | statusbar / Start proc / `Package:`（DOWNLOADING） | 结论必须写包名 |
| **reason** | 商店下载原因 | `state:DOWNLOADING` 同行 `reason=su_auto_update` 等 | 可选 |
| **灭屏** | 屏幕关闭时段 | `PowerManagerService` Going to sleep / Sleeping ↔ Waking up | **仅过滤 Usf_Hiber** |

## 日志形态（实机）

### 1) sys — 灭屏流量活跃（主信号，优先）

```
PowerManagerService: Going to sleep due to power_button ...
PowerManagerService: Sleeping (uid 1000)...
Usf_Hiber/importantScene: isTrafficActive uid:10290 speed :168
Usf_Hiber/importantScene: uid:10290 speed :168
Usf_Hiber/importantScene: statusbar progressing: packageName=com.google.android.youtube ,uid:10258
PowerManagerService: Waking up from Asleep ...
```

| 条件 | 判定 |
|------|------|
| `speed > 100` **且** 落在灭屏区间 | 该 uid 在下载/数传 |
| `speed ≤ 100` 或 亮屏 | **不计** |

### 2) main — `state:DOWNLOADING`（取包名，不限亮灭屏）

```
Finsky:background: ... [Package:com.android.vending, isid:...] state:DOWNLOADING, status=DOWNLOADING, ..., reason=su_auto_update, ...
```

| 片段 | 判定 |
|------|------|
| `state:DOWNLOADING` | 正在下载 |
| `Package:<pkg>` | 下载包名 |
| `reason=` | 可选原因（如 `su_auto_update`） |

### 3) sys — 安装完成（不限亮灭屏）

```
PackageManager: installation completed for package:com.android.vending. Final code path: /data/app/...
```

## 结论描述要求（必须写具体）

1. **什么时间段有下载**（灭屏 Usf_Hiber 与 mainlog DOWNLOADING 分开写）  
2. **在下载什么**（包名 + uid；商店类写 reason）  
3. **uid / pid** 含义  
4. **有无安装**（`installation completed for`）

展示以**表格**为主：开始时间 / 结束时间 / max_speed / hits（不写跨度）。

## 推荐脚本

**DOU 全流程最后一步（推荐）** — 产物强制落高功耗根目录：

```powershell
python analysis/domain/power/flow/dou_2/tool1_2/run_app_download.py "<high>"
# → <high>\app_download_result.json
# → <high>\app_download_result.txt
```

可选参数：

| 参数 | 默认 | 含义 |
|------|------|------|
| `--speed-min` | `100` | Usf_Hiber 仅 `speed >` 该值 |
| `--gap-sec` | `120` | 同 uid/包 命中间隔合并 |
| `--min-sec` | `3` | Usf_Hiber 单段时长短于此时长不计 |

底层：

```powershell
python analysis/domain/power/flow/dou_2/app_download/scripts/download_traffic.py `
  -d "<high>" --format text -o "<high>\app_download_result.txt"
```

## 更快查找顺序

| 优先级 | 动作 |
|--------|------|
| 1 | 扫 `sys_log*`：亮灭屏（Going to sleep / Waking up） |
| 2 | 扫 `sys_log*`：`Usf_Hiber/importantScene` + `speed>100`，**仅保留灭屏命中** |
| 3 | 扫 `main_log*`：`state:DOWNLOADING` + `Package:` |
| 4 | 扫 `installation completed for` |

```powershell
rg -n "PowerManagerService: (Going to sleep|Sleeping|Waking up from Asleep)" -g "sys_log*"
rg -n "Usf_Hiber/importantScene:.*speed\s*:\s*(1[0-9]{2}|[2-9][0-9]{2}|[1-9][0-9]{3,})" -g "sys_log*"
rg -n "state:DOWNLOADING" -g "main_log*"
rg -n "installation completed for package:" -g "sys_log*"
```

## 与其它 skill 关系

| skill | 关系 |
|-------|------|
| `base_wifi_data` / `base_modem_data` | 量化空口数传；本 skill 归因「哪个应用、何时在下」 |
| `base_download`（编排） | JIRA 附件下载，与本 skill **无关** |
| 本目录归属 | `flow/dou_2/app_download/` |
| `flow/dou_2` §10 | 全流程最后一步；Look「下载安装」Tab |
