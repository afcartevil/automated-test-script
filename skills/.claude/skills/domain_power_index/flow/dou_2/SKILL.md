---
name: flow_power_dou
description: DOU分析已拆分为独立可运行脚本（场景对比/功耗/CPU/结果组装/HTML/Bugreport AudioMix/应用下载）
---

## 适用场景

DOU 3.0 高/低功耗版本对比分析：场景 Excel 对比、TopN 筛选、射频功耗、CPU/电流/AI 归因、HTML 报告、**Bugreport AudioMix 持锁时间轴**与应用下载检测。

## 输入

- **高功耗目录** `<high>`、**低功耗目录** `<low>`（含 `meta_report/testReport.xlsx`、`phone_logs`、`.pt5` 等）
- **平台**：MTK / 高通 / 展锐
- **环境变量**：`DOU_AI_API_KEY`（可选，见 `ai_config.json`）；JIRA 相关见编排层 `base_jirainfo`

## 执行流程

见下文「推荐执行顺序（拆分后）」与各节脚本说明。

## 输出

产物落在 `<high>` 根及 `screen_on` / `screen_off` 分卷目录（见「输出目录硬规则」）。

## 门禁

TopN 每个 suffix 须具备 CPU + spike + AI JSON；亮/灭屏各一份 `topn_summary.json`；HTML 后须跑 Bugreport Wakelock（**high + low**，有 bugreport 时）；全流程最后 `app_download_result.json`。

## 执行方式约束（必须遵守）

- **不要在后台运行**：禁止使用 `Start-Job` / `Start-Process` / `&` / `start` 等方式把脚本丢到后台执行；必须在当前终端前台同步运行，确保能直接看到报错与输出顺序。
- **允许等待更久**：这些脚本可能耗时较长（尤其是 CPU/AI/汇总与 HTML 组装链路），执行时应直接等待完成，不要为了“快点继续操作”而后台化。
- **如需保存终端输出**：可以在前台同步执行的前提下，把输出重定向到文件（例如 `| Out-File -FilePath ... -Encoding UTF8` 或 `*> ...`），但仍然必须等待命令返回成功/失败码后再进入下一步。
## 结果展示

离线 HTML 报告由 `tool1_2/run_final_html.py` 生成（见 §8）。命令均在 **tran_sw_skillhub 包根**（含 `analysis/` 目录）下执行。

## 功能说明（已拆分）
[重要]运行不要中断
[重要]运行不要中断
[重要]运行不要中断
`tool1_2/app.py` 已删除，按推荐执行顺序运行，并在需要时生成最终 HTML。  
现在按功能拆分为以下独立入口，均可单独运行并独立产出结果文件。

- `analysis/domain/power/flow/dou_2/tool1_2/run_scene_compare.py`
- `analysis/domain/power/flow/dou_2/tool1_2/run_power_analysis.py`
- `analysis/domain/power/flow/dou_2/tool1_2/run_topn_select.py`
- `analysis/domain/power/flow/dou_2/tool1_2/run_cpu_analysis.py`
- `analysis/domain/power/flow/dou_2/tool1_2/run_ai_analysis.py`（**兼容入口**：须已有 `current_cpu_spike_*.json`，单次综合 AI；推荐改用下方 `--with-ai`）
- `analysis/domain/power/flow/dou_2/tool1_2/run_collect_results.py`
- `analysis/domain/power/flow/dou_2/tool1_2/run_topn_summary.py`（**TopN 综合总结**，调用内部 API）
- `analysis/domain/power/flow/dou_2/tool1_2/run_final_html.py`
- `analysis/domain/power/flow/dou_2/tool1_2/run_current_cpu_spike.py`（PT5 电流 + 已有 CPU JSON + 差异分段；**`--with-ai` = 单场景唯一 AI**，一次调用同时落盘 `ai_analysis_*` + `current_cpu_spike_ai_*`）
- `analysis/domain/power/flow/dou_2/tool1_2/run_current_cpu_spike_ai.py`（仅补跑综合 AI，读已有 spike+cpu；见 §5 / §9）
- `analysis/domain/power/flow/dou_2/tool1_2/run_bugreport_audiomix.py`（**DOU 第 9 步**：AudioMix 持锁时间轴；见 §11）
- `analysis/domain/power/flow/dou_2/tool1_2/run_bugreport_longwake.py`（**DOU 第 9 步补充**：全部 longwake；见 §11）
- `analysis/domain/power/flow/dou_2/tool1_2/run_app_download.py`（**全流程最后（第 10 步）**：高功耗 phone_logs 下载/安装检测；见 §10）
- `analysis/domain/power/flow/dou_2/bugreport_audiomix/run_bugreport_audiomix.py`（低层：AudioMix；见 `bugreport_audiomix/SKILL.md`）
- `analysis/domain/power/flow/dou_2/bugreport_audiomix/run_bugreport_longwake.py`（低层：全部 longwake；见 `bugreport_audiomix/SKILL.md`）
- `analysis/domain/power/flow/dou_2/tool1_2/run_dou_jira_prepare.ps1`（**仅 JIRA 单号**时：下载/匹配路径/解压/转换）

## PT5 电流解析（MCP pt5，必须遵守）

`.pt5` 电流曲线**统一走 `pt5-mcp-server` 官方 Monsoon 解析器**（与 Cursor MCP 服务 `pt5` 同源），禁止再用旧版 `pt5_reader.py` 里的手工二进制截取。

| 场景 | 用法 |
|------|------|
| **Cursor Agent 内探查/预览** | 直接调用 MCP `pt5`：`parse_pt5`、`get_pt5_samples`、`analyze_pt5_trend`、`export_pt5_csv` 等 |
| **DOU 脚本链路**（`run_current_cpu_spike.py` 等） | `scripts/pt5_reader.py` → `scripts/pt5_mcp_cli.mjs` → 全局 `pt5-mcp-server` |

前置条件（本机一次即可）：

```powershell
npm install -g pt5-mcp-server
# Cursor 已配置见仓库 .cursor/mcp.json
```

脚本侧快速自检：

```powershell
python analysis/domain/power/flow/dou_2/scripts/pt5_reader.py "<meta_report下某.pt5>" 60
```

## AI 分析 API 配置（必须）

**单场景综合 AI**（电流图就绪后 `--with-ai`，**每场景只调 1 次 API**）、TopN 综合总结 **统一调用传音内部 OpenAI 兼容网关**，不再依赖「复制提示词到对话」。  
禁止对同一场景再分别跑「仅 CPU AI」+「仅电流 AI」两次调用。

默认配置见本目录 `ai_config.json`：

| 项 | 默认值 |
|----|--------|
| Base URL | `https://sw-aimodel.transsion-os.com/v1` |
| 模型 | `deepseek-v4-flash` |

**API Key** 优先级：`--api-key` 参数 > 环境变量 `DOU_AI_API_KEY` / `OPENAI_API_KEY` > 本目录 `ai_config.json` 的 `api_key` 字段。

```powershell
setx DOU_AI_API_KEY "<your-api-key>"
# 可选覆盖
setx DOU_AI_BASE_URL "https://sw-aimodel.transsion-os.com/v1"
setx DOU_AI_MODEL "deepseek-v4-flash"
```

当前 PowerShell 会话临时生效：`$env:DOU_AI_API_KEY = "<your-api-key>"`  
也可直接维护 `ai_config.json`（本 skill 已配置，Agent 无需再问 Key）。  
脚本也支持 `--api-key` / `--base-url` / `--model` 参数覆盖。
## 输出目录硬规则（必须遵守）

**本流程生成的所有产物文件必须落在高功耗目录（`high`）下**；其中 **TopN / CPU / AI / results / 分卷总结 / 分卷 HTML** 按亮/灭屏分目录存放。

### 目录结构

| 位置 | 内容 |
|------|------|
| `<high>\`（根） | `scene_compare_result.json`、`DOU3.0版本数据对比.xlsx`、`power_analysis_result.json`（全局一份）、**`bugreport_audiomix_result.json` / `bugreport_audiomix_result.txt`（AudioMix 持锁结论摘要）**、**`bugreport_longwake_result.json`（全部 longwake 摘要）**、**`app_download_result.json` / `app_download_result.txt`（下载安装检测，全流程最后一步）** |
| `<low>\`（根） | **`bugreport_audiomix_result.*` / `bugreport_longwake_result.json`（第 9 步 wakelock，与 high 对称）** |
| `<high>\screen_on\` | **亮屏** TopN、`cpu_analysis_*`、`ai_analysis_*`、`results_json.json`、`topn_summary.json`、分卷 HTML、`current_cpu_spike_*`、`current_cpu_spike_ai_*`、`current_cpu_spike_result.json` |
| `<high>\screen_off\` | **灭屏** 同上 |

执行时的硬要求：
- 场景对比、射频功耗仍在 `<high>` 根目录。
- `run_topn_select.py` 带 `--screen 亮屏` 或 `--screen 灭屏` 时，默认输出到对应子目录（无需手写 `--output`）。
- `run_cpu_analysis.py` 对亮/灭屏场景使用 `--screen 亮屏` / `--screen 灭屏`（或 `--results-dir <high>\screen_on`）。
- `run_collect_results.py` / `topn_summary.json` / `run_final_html.py` 的输入输出路径指向**同一分卷目录**。
- `run_current_cpu_spike.py` 产物（`current_cpu_spike_<suffix>.json` 含 `diff_segments` / `cpu_scene_compare`、汇总 `current_cpu_spike_result.json`、可选 `current_cpu_spike_ai_*`）落在**同一分卷目录**，供在线看板「电流+CPU」板块展示。
- `run_app_download.py` 产物（`app_download_result.json` / `.txt`）落在**高功耗根目录**，供在线看板「下载安装」Tab 展示结论描述；**禁止**写本地 temp。
- `run_bugreport_audiomix.py` / `run_bugreport_longwake.py`：**高/低各一份**摘要（`bugreport_audiomix_result.*`、`bugreport_longwake_result.json`）；推荐 `... <high> --low <low>`。未传 `--low` 时从 prepare/scene_compare/power_analysis 回退；解析不到则只跑 high（WARN）。详细时间轴在各自 `phone_logs/.../bugreports/`（主 txt=`bugreport_main.txt`）；无 bugreport 时写 `skipped=true` 后退出 0。
- 亮屏/灭屏分卷目录 `screen_on` / `screen_off` 各自独立落盘；根目录旧产物仍可作为兼容分卷读取。

已有根目录产物迁移（可选）：

```powershell
& "...\tool1_2\migrate_to_screen_dirs.ps1" -HighDir "<高功耗目录>"
# 预览: 加 -WhatIf
```
迁移后需对两个分卷分别补跑 `run_collect_results.py` 与 TopN 综合总结。

## Windows/PowerShell 字符集硬规则（必须遵守）

目标：**避免中文在终端显示为 `?`，并且避免把乱码“写进” `ai_analysis_*.json` / `topn_summary.json` / HTML。**

### 1) 先把 PowerShell 会话切到 UTF-8（建议每次开新终端先执行一次）

```powershell
# 让控制台和 PowerShell 管道都按 UTF-8 处理输出
chcp 65001
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()

# 强制 Python 用 UTF-8（Windows 下非常关键）
$env:PYTHONUTF8 = "1"
```

### 2) 不要手敲中文文件名（尤其是 Excel 路径）

- 正确做法：从 `scene_compare_result.json` 的 `scene_excel_path` 读取真实路径，再传给 `run_topn_select.py`。

```powershell
$high = "<高功耗目录>"
$sceneExcel = python -c "import json;print(json.load(open(r'$high\scene_compare_result.json','r',encoding='utf-8'))['scene_excel_path'])"
python analysis/domain/power/flow/dou_2/tool1_2/run_topn_select.py "$sceneExcel" --topn 3
```

### 3) 打印/拼接提示词块与 JSON 时，统一按 UTF-8 读写

- PowerShell 读取文件优先用（避免 `type` 在部分机器上显示乱码）：

```powershell
Get-Content "<高功耗目录>\cpu_analysis_3796.json" -Encoding UTF8
```

### 4) 如果你用 PowerShell here-string / pipeline 传 Python 代码给 `python -`

- 这种方式会被 PowerShell 当前编码影响：**中文常量可能直接变成 `?`，并被写入 JSON/HTML**。
- 建议：尽量不要在这类脚本里写中文常量；如必须写中文，务必先执行本节第 1 条的 UTF-8 设置后再运行。

## 0) JIRA 单号前置自动化（给定单号时必须先执行）

用户只给 **JIRA 单号**、未给 high/low 路径时，**必须先**完成本节，再进入下文「推荐执行顺序」。禁止跳过下载/解压/转换直接跑 `run_scene_compare.py`。

### 固定 SMB 目录（必须遵守）

| 角色 | 共享路径 |
|------|----------|
| **高功耗 high 根目录** | `\\10.205.4.20\sw_temp\底软通信开发部\lzx\DOU高功耗文件夹` |
| **低功耗 low 根目录** | `\\10.205.4.20\sw_temp\底软通信开发部\lzx\DOUtestPASS数据` |

- **high**：从 JIRA 描述下载/解压后的 DOU 日志目录，必须落在「DOU高功耗文件夹」下（形如 `...\DOU高功耗文件夹\<测试目录名>\`）。
- **low**：不在 JIRA 里下载；Agent **必须**在「DOUtestPASS数据」下递归查找匹配目录（见下）。

### 一键前置脚本（推荐）

```powershell
chcp 65001 | Out-Null
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"

$skillHub = "<tran_sw_skillhub 包根>"   # 含 analysis/ 与 orchestrate/ 的目录
$key  = "X6879OS161-3796"                            # 用户给的 JIRA 单号

& "$skillHub\analysis\domain\power\flow\dou_2\tool1_2\run_dou_jira_prepare.ps1" -JiraKey $key
```

脚本顺序（前台同步，不得后台）：

1. `base_jirainfo`：`-i <KEY> -f summary -f description`
2. **high**：在 `DOU高功耗文件夹` 下查找已含 `testReport.xlsx` 的子目录 → **命中则跳过下载**；否则 `base_download` 将 JIRA 描述中的链接下载到该根目录
3. **low**：在 `DOUtestPASS数据` 下递归扫描含 `testReport.xlsx` 的目录，按 summary 中**对比版本**（如 `对比tOS16.1`）、**项目名**（如 `X6879`）、**SN**、是否含 `PowerMonitor` 等打分，取得分最高者
4. **解压** `phone_logs/mobile_log*.zip`（已解压则跳过）
5. **MTK 时间转换**：若目录内无 `*_linli_666.txt` 但有 `kernel_log_*`/`events_log_*`，对 high/low **分别**执行 `mtk_kernellog_convert/scripts/time_convert.py`

落盘：`<high>\dou_prepare_result.json`（含 `high`/`low` 绝对路径、`path_resolve`、`prepare` 状态）。后续步骤从该文件或脚本输出的 `HIGH=` / `LOW=` 读取路径。

仅重做匹配/解压/转换、不重新下载时：

```powershell
& "...\run_dou_jira_prepare.ps1" -JiraKey $key -SkipDownload
```

### 手动分步（脚本失败时）

```powershell
# 1) 读 JIRA
python analysis/base/jirainfo/scripts/jira_info.py -i <KEY> -f summary -f description

# 2) 下载到 high 根（仅当该目录下尚无完整 DOU 包时）
python analysis/base/download/scripts/download.py '<description全文>' '\\10.205.4.20\sw_temp\底软通信开发部\lzx\DOU高功耗文件夹'

# 3) low：在 DOUtestPASS数据 下查找（须含 meta_report\testReport.xlsx，建议另有 phone_logs）
# 4) 解压 + linli_666：见下文「0) DOU 分析前置条件」B/C 节
```

**门禁**：`dou_prepare_result.json` 中 `high`/`low` 均有效，且两边 `prepare.*.linli_count > 0`（或已确认无 kernel 日志）后，才进入场景对比。

---

## 云文档下载失败时的日志兜底查找（必须遵守）

当 JIRA 描述只提供云文档/飞书文件夹链接时，优先按 **§0 JIRA 单号前置自动化** 下载到 `DOU高功耗文件夹`；如果云文档下载失败（例如 `403 forbidden`、无权限、链接不可直接下载），并且用户没有额外提供本地 high/low 文件夹路径，则**不要直接结束分析**，必须按云文档名称到共享目录中查找：

```text
\\10.207.190.10\sw_log\dzppt\dou3\
```

查找规则：
- 以云文档/飞书文件夹显示名称、JIRA 标题中的版本号/项目名/单号等关键字作为候选名称，在上述共享目录下递归查找匹配目录。
- 找到候选目录后，优先选择同时包含 `meta_report\testReport.xlsx` 与 `phone_logs\mobile_log*.zip` 的目录作为 high/low 输入目录。
- 如果只找到一个版本目录，继续在同级目录或相邻目录中按对比版本名称查找另一个 low/high 目录。
- 若多个目录都命中，列出候选目录与命中依据，优先选择目录名最匹配云文档名称且文件结构完整的目录；仍无法判断时再向用户确认。
- 若共享目录也未找到可用 high/low 目录，最终再输出“日志无法获取/未找到匹配目录”的阻塞结论。

PowerShell 查找示例（按实际云文档名称替换 `$keyword`）：

```powershell
$root = "\\10.207.190.10\sw_log\dzppt\dou3"
$keyword = "<云文档名称或版本关键字>"
Get-ChildItem -Path $root -Recurse -Directory -ErrorAction SilentlyContinue |
  Where-Object { $_.Name -like "*$keyword*" -or $_.FullName -like "*$keyword*" } |
  Select-Object -First 20 FullName
```

## 0.1) DOU 日志解压与 MTK 转换（必须先做，否则跑不完全程）

> 若已执行 `run_dou_jira_prepare.ps1`，解压与转换通常已完成；本节用于手工路径或复核。  
> 常见问题：能生成 Excel/TopN，但 CPU 分析报 `版本1没有找到相关日志文件` —— **通常是未解压 `phone_logs/mobile_log*.zip` 或未生成 `*_linli_666.txt`。**

### A) high/low 目录必须包含的关键文件/目录

- 场景报告 Excel：**优先** `meta_report/testReport.xlsx`；若无则自动选用同目录下**含 `report` 工作表**的其它 `.xlsx`（排除 `DOU3.0版本数据对比` 等产物）。两边都必须能解析到，否则 `run_scene_compare.py` 报错。
- `phone_logs/mobile_log*.zip`（**至少 high 必须有**；建议 low 也有，保证 CPU 对比可跑）
- `phone_logs/mobile_log*/bugreports/bugreport*.zip`（**high/low 均可能有**；第 9 步前须解压为 `bugreport*.txt`）

### B) 必须先解压缩（mobile_log 与 bugreport **同一规则**：zip → 同目录下去后缀文件夹，已存在则跳过）

**统一规则**（PowerShell 与 Python `scripts/dou_unzip.py` 一致）：

```text
phone_logs/mobile_log1.zip          → phone_logs/mobile_log1/
phone_logs/mobile_log1/bugreports/bugreport-xxx.zip → .../bugreport-xxx/
```

**解压 `phone_logs/mobile_log*.zip` + `bugreports/bugreport*.zip`（high + low，已解压会跳过）：**

```powershell
function Expand-DouZipIfNeeded([string]$ZipPath) {
  if (-not (Test-Path -LiteralPath $ZipPath)) { return $null }
  $dir = Split-Path -LiteralPath $ZipPath -Parent
  $base = [System.IO.Path]::GetFileNameWithoutExtension($ZipPath)
  $out = Join-Path $dir $base
  if (-not (Test-Path -LiteralPath $out)) {
    Expand-Archive -LiteralPath $ZipPath -DestinationPath $out -Force
  }
  return $out
}

$high = "<高功耗目录>"
$low  = "<低功耗目录>"
foreach($p in @($high,$low)){
  $z = Get-ChildItem -File (Join-Path $p "phone_logs") -Filter "mobile_log*.zip" -ErrorAction SilentlyContinue | Select-Object -First 1
  if($z){
    $out = Expand-DouZipIfNeeded $z.FullName
    if($out){ Write-Output "unzipped mobile_log: $out" }
  } else {
    Write-Output "WARN: not found mobile_log*.zip under $p\\phone_logs"
  }
  Get-ChildItem -Path (Join-Path $p "phone_logs") -Recurse -File -Filter "bugreport*.zip" -ErrorAction SilentlyContinue |
    ForEach-Object {
      $bout = Expand-DouZipIfNeeded $_.FullName
      if($bout){ Write-Output "unzipped bugreport: $bout" }
    }
}
```

> `run_dou_jira_prepare.ps1` 使用同一 `Expand-DouZipIfNeeded`；第 9 步 Python 调用 `scripts/dou_unzip.py`（先 mobile_log 再 bugreport）。

### C)（仅 MTK）确认/生成 `*_linli_666.txt`（CPU 分析的硬前置）

CPU 分析（`run_cpu_analysis.py`）对 MTK 平台会在 high/low 目录中查找 `*_linli_666.txt` 格式的 kernel 日志；若缺失，会报：
- `版本1没有找到相关日志文件`
- 或 `版本2没有找到相关日志文件`

**1）先检查是否已存在 `*_linli_666.txt`：**

```powershell
$high = "<高功耗目录>"
$low  = "<低功耗目录>"

foreach($p in @($high,$low)){
  $cnt = (Get-ChildItem -Recurse -File $p -Filter "*_linli_666.txt" -ErrorAction SilentlyContinue | Measure-Object).Count
  Write-Output "$p linli_666_count=$cnt"
}
```

**2）如果 `*_linli_666.txt` 为 0，但目录里存在原始 `kernel_log_*` / `events_log_*`，则先做时间戳转换生成：**

```powershell
$high = "<高功耗目录>"
$low  = "<低功耗目录>"

foreach($p in @($high,$low)){
  $cnt = (Get-ChildItem -Recurse -File $p -Filter "*_linli_666.txt" -ErrorAction SilentlyContinue | Measure-Object).Count
  if($cnt -eq 0){
    python analysis/base/mtk_kernellog_convert/scripts/time_convert.py $p
  }
}
```

> 说明：`time_convert.py` 会处理 `kernel_log_*` / `events_log_*`，**包含** `kernel_log_YYYY_MMDD_HHMMSS.curf`（如 `kernel_log_2026_0128_021444.curf`），并跳过已生成的 `*_linli_666.txt`。

---

## 推荐执行顺序（拆分后）

1. 运行 `run_scene_compare.py`：生成 `DOU3.0版本数据对比.xlsx`
2. 运行 `run_topn_select.py`：从 Excel 里筛选出 `top_scenes_json`（包含 `suffix/desc/power_mah`）
3. 运行 `run_power_analysis.py`：产出 `power_analysis_result.json`（供你后续做功耗对比汇总；当前 TopN 汇总脚本不强依赖）
4. **必须完成：逐个 TopN 场景的 CPU 分析（不可跳过；本步不调场景 AI）**  
   对 `top_scenes_json` 里的每个 `suffix`，必须产出：
   - `cpu_analysis_<suffix>.json`：运行 `run_cpu_analysis.py` 生成  
   **长待机分支**：若命中「4.5) 长待机场景」，本步之后（或与第 5 步并行条件允许时）另跑长待机脚本，落盘 `standby_analysis_<suffix>.json`（**与场景综合 AI 分开**，仍可单独调 API）。  
   **门禁条件**：TopN 中每个 `suffix` 须具备 `cpu_analysis_<suffix>.json`。
5. **必须完成：电流图 + CPU 时段关联 + 单场景综合 AI（每场景只调 1 次 AI）**  
   对亮屏/灭屏分卷分别运行 `run_current_cpu_spike.py ... --with-ai`：  
   - 结构化：`current_cpu_spike_<suffix>.json`（底电、spike 窗口、diff_segments、CPU 关联）  
   - **综合 AI（一次）**：同时落盘 `ai_analysis_<suffix>.json` 与 `current_cpu_spike_ai_<suffix>.json`（**同一结论**，提示词 `COMBINED_SCENE_SYSTEM_PROMPT`）  
   **禁止**再单独跑旧的「仅 CPU」`run_ai_analysis`（无 spike）或再跑第二次电流 AI。  
   **前置**：第 4 步 CPU JSON 就绪；high/low `meta_report` 含对应 `.pt5`；本机已装 `pt5-mcp-server`。  
   **门禁**：每个 TopN `suffix` 须有 `current_cpu_spike_<suffix>.json` + `ai_analysis_<suffix>.json`；长待机另须 `standby_analysis_<suffix>.json`。
6. 运行 `run_collect_results.py`：把 `cpu_analysis_*.json` + `ai_analysis_*.json` 组装成 `results_json.json`；若存在 `standby_analysis_<suffix>.json`，合并 `standby_result`。
7. **必须完成：亮屏 / 灭屏各自一份总结论（不可跳过、不可只跑一个）**  
   对 `screen_on` 与 `screen_off` **分别**运行 `run_topn_summary.py`（推荐 `--high <高功耗目录> --both`），各落盘一份 `topn_summary.json`。  
   **门禁条件**：两个分卷目录下均有 `topn_summary.json` 且 `success=true`（某分卷无 TopN 场景时可跳过该分卷，但不得用亮屏总结代替灭屏或反之）。
8. 运行 `run_final_html.py`：对亮/灭屏分卷分别渲染 HTML（并默认打开浏览器）
9. **必须完成：Bugreport 持锁时间轴（不可跳过本步命令；无 bugreport 则自动 skip）**
   - **AudioMix**（场景对齐 + 异常判定）：`run_bugreport_audiomix.py <high> --low <low>`
   - **全部 Long Wakelock**（大类总览）：`run_bugreport_longwake.py <high> --low <low>`
   - **低功耗必须跑**：手工给 high/low 时**务必显式 `--low`**；未传时回退读 `<high>` 根下 `dou_prepare_result.json` → `scene_compare_result.json` → `power_analysis_result.json` 的 `low`。若仍解析不到，**只会跑 high**（终端 WARN），Look「低功耗 Wakelock」为空。
   - 运行前自动解压 `phone_logs/mobile_log*/bugreports/bugreport*.zip`（主 txt 落到 `bugreport_main.txt`，规避 UNC 长路径）
   **落盘强制**：`<高>/` 与 `<低>/` 各一份 `bugreport_audiomix_result.*`、`bugreport_longwake_result.json`；详细产物在各自 `phone_logs/.../bugreports/.../` 下。
   **门禁**：若某 side 的 `phone_logs` 下存在 bugreport，则该 side 的 audiomix JSON 中 `skipped` 不得为 true。详见 §11 与 `bugreport_audiomix/SKILL.md`。
10. **必须完成：应用下载/安装检测（不可跳过，放在全流程最后）**  
   运行 `run_app_download.py`，扫描高功耗 `phone_logs` 的 sys/main log，产出结论描述（何时下载、下什么、uid/pid、有无安装）。  
   **落盘强制**：`<高功耗目录>/app_download_result.json` 与 `app_download_result.txt`（**禁止**写仓库 `temp/` 或本机其它目录）。  
   **看板**：Look「下载安装」Tab 展示 `narrative` 结论描述。详见 §10 与 `app_download/SKILL.md`。

### 亮屏业务场景归因 SOP

TopN 在完成 CPU + 电流 + 综合 AI 后，对每个 suffix 执行：

[`scenario/SKILL.md`](scenario/SKILL.md)（**SOP-DOU-SCENARIO-01**：读 YAML 操作 → 路由 → 对齐 diff_segments → 子 skill → KI → 标准结论）

| 行为 | 目录 |
|------|------|
| SOP 正文 | [`scenario/SKILL.md`](scenario/SKILL.md) |
| 主页待机 | `scenario/scenario-dou-app-idle-home/` |
| Feed/主界面滑动 | `scenario/scenario-dou-feed-scroll/` |
| 视频滑动+小窗 | `scenario/scenario-dou-video-scroll-pip/` |
| 拍照+图库 | `scenario/scenario-dou-camera-gallery/` |
| 发布视频动态 | `scenario/scenario-dou-content-publish/` |
| 云文档浏览 | `scenario/scenario-dou-document-browse/` |
| 地图导航 | `scenario/scenario-dou-maps-nav/` |
| 商店+应用下载 | `scenario/scenario-dou-store-download/` |
| 浏览器网页 | `scenario/scenario-dou-web-browse/` |
| 图片视频剪辑 | `scenario/scenario-dou-media-edit/` |

---

## 1) 场景对比（独立）

脚本：

```text
python analysis/domain/power/flow/dou_2/tool1_2/run_scene_compare.py "<高功耗目录>" "<低功耗目录>" <平台> [--output "<json输出路径>"]
```

输入：
- `high`：高功耗目录（必填）
- `low`：低功耗目录（必填）
- `platform`：`MTK/高通/展锐`（可选，默认 `MTK`）

输出：
- 默认输出：`<高功耗目录>/scene_compare_result.json`
- 核心字段：
  - `scene_excel_path`：生成的 `DOU3.0版本数据对比.xlsx` 路径
  - `scene1_excel_path`、`scene2_excel_path`

约束：
- 必须保证 `DOU3.0版本数据对比.xlsx` 位于 `<高功耗目录>`；后续 TopN 选择默认把 `topn_scenes_top<N>.json` 输出到 Excel 同目录，因此 Excel 不在 `<高功耗目录>` 会导致产物到处生成。

Excel 末尾追加列（场景对比自动生成）：
- `版本1场景时间`：高功耗版 report 表 `starttime` ~ `endtime`（格式 `YYYY-MM-DD HH:MM:SS 至 ...`）
- `版本2场景时间`：低功耗版 report 表 `starttime` ~ `endtime`（未匹配场景为空）
- `场景亮灭屏`：desc/name 不含灭屏关键字 → `亮屏`，否则 `灭屏`（与 TopN `--screen` 判定一致）
- `对亮屏电流影响(mA)`：亮屏场景填 `功耗差异mAh / 全部亮屏场景总时长(h)`，灭屏场景为空
- `对灭屏电流影响(mA)`：灭屏场景填 `功耗差异mAh / 全部灭屏场景总时长(h)`，亮屏场景为空  
  亮/灭屏总时长 = 同类型各场景 `duration_sec` 之和（来自 report 表）

---

## 2) Modem/Wi-Fi 功耗分析（独立）

脚本：

```text
python analysis/domain/power/flow/dou_2/tool1_2/run_power_analysis.py "<高功耗目录>" ["<低功耗目录>"] [--output "<json输出路径>"]
```

输入：
- `high`：高功耗目录（必填）
- `low`：低功耗目录（可选；不填时走单目录模式，`low=high`）

输出：
- 默认输出：`<高功耗目录>/power_analysis_result.json`
- 核心字段：
  - `single_folder_mode`：是否单目录模式
  - `result`：`power_analysis.py` 的完整分析结果

---

## 3) TopN 选择（独立）

### 可忽略场景（脚本问题）

编辑技能目录下 `ignorable_scenes.json`（与 `SKILL.md` 同级）。其中 `rules` 命中的场景：

- **TopN 选取时跳过**（不占 TopN 名额，不进入后续 CPU/AI 深度分析）
- **最终 HTML 仍会展示**，标注为脚本问题，并显示 Excel 中的「对亮屏电流影响(mA)」「对灭屏电流影响(mA)」

`rules` 每条支持：`suffix`、`name`、`name_contains`、`desc`、`desc_contains`；可选 `reason` 覆盖默认说明。

**自动 error 场景（每次分析临时生效）**：`run_scene_compare.py` / `run_topn_select.py` 会读取 high/low 的 `testReport.xlsx` → `report` 表中 `result=error` 的行，**临时追加**到 `ignorable_scenes.json`（并在 `<high>/ignorable_auto_session.json` 记录本次写入）。`run_final_html.py` 成功生成 HTML 后**自动删除**本次写入的规则；手动配置的 `rules` 不受影响。

### 场景脚本问题（Look 看板 · 仅人工判定）

- **不再自动标注**「疑似脚本问题」（电流趋势算法不参与脚本问题结论）。
- **每个场景必须人工选择**：标题旁下拉「是脚本问题 / 不是 / 待定」，写入 `manual_scene_notes.json` 的 `is_script_issue`。
- 人工选「是」后标题显示 **【脚本问题】**；导出时与上文**可忽略场景**一并归入 **「场景脚本问题」**。

### 脚本

```text
python .../run_topn_select.py "<DOU3.0对比Excel路径>" --topn <N> --screen 亮屏 [--ignorable-config "<json路径>"]
python .../run_topn_select.py "<DOU3.0对比Excel路径>" --topn <N> --screen 灭屏
```

输入：
- `scene_excel_path`：`DOU3.0版本数据对比.xlsx` 路径（由 `run_scene_compare.py` 生成）
- `--topn`：默认 3
- `--screen`：**推荐必填**，`灭屏/亮屏` 或 `off/on`；指定后默认输出到 `<high>/screen_on/` 或 `<high>/screen_off/`
- `--ignorable-config`：可选，默认同目录 `ignorable_scenes.json`

输出：
- 无 `--screen`：`<high>/topn_scenes_top<N>.json`（兼容旧布局）
- 有 `--screen`：`<high>/screen_on|screen_off/topn_scenes_top<N>.json`，JSON 内含 `screen_bucket`、`results_dir`
- 输出 JSON 结构：`{ "top_scenes": [...], "ignored_scenes": [...] }`（`run_collect_results` / `run_final_html` 仍兼容旧版纯 `list`）
  - `top_scenes` 每项：`suffix`、`desc`、`power_mah`（用于后续 AI 提示）
  - `ignored_scenes` 每项：同上，另含 `impact_on_ma`、`impact_off_ma`、`screen_label`、`ignore_reason`

**长待机扫描**：TopN 产出后，对 `top_scenes` 逐条按本文「4.5) 长待机场景」判定；命中的 suffix 进入长待机分析分支，不得仅走通用 CPU+AI。

---

## 4) CPU 分析（独立）

脚本：

```text
python analysis/domain/power/flow/dou_2/tool1_2/run_cpu_analysis.py "<高功耗目录>" "<低功耗目录>" <平台> <suffix> [--scene-excel "<DOU3.0对比Excel路径>"] [--output "<json输出路径>"]
```

输入：
- `high`：高功耗目录（必填）
- `low`：低功耗目录（必填）
- `platform`：平台（可选，默认 `MTK`）
- `suffix`：场景后缀（如 `3796`，支持传 `_3796`）
- `--scene-excel`：可选；不填会自动先执行一次场景对比生成 Excel

输出：
- 默认输出：`<高功耗目录>/cpu_analysis_<suffix>.json`
- 核心字段：
  - `scene_excel_path`
  - `cpu_data`（`CPULogAnalyzer.analyze()` 完整结果）

---

## 4.5) 长待机场景（`flow_power_standby_long_dou`）

**Skill 接口**：`analysis/domain/power/flow/standby_long_dou/SKILL.md`（`flow_power_standby_long_dou`）

**DOU 桥接脚本**：`scripts/dou_standby_long.py` + `tool1_2/run_standby_analysis.py`

### 判定（TopN 后扫描）

同时满足：

1. **灭屏**（desc/name 含灭屏/熄屏/screen off，与 TopN `--screen 灭屏` 一致）
2. **长待机语义**（desc/name 含「待机」「长待机」「standby」等）**或** `duration_sec ≥ 3600`（1h）**或**（含待机语义且 `duration_sec ≥ 30min`）

命中的 suffix **不得仅用通用 CPU+综合 AI 代替**，须另跑长待机分支。

### 默认口径（与 standby_long_dou 一致）

| 项 | DOU 默认 |
|----|----------|
| `standby_type` | **WIFI** |
| `threshold_ma` | **25**（显式 DATA 时为 30） |
| 时间窗 | testReport `starttime`~`endtime`（**禁止** kernel 自动截取覆盖） |
| 平均功耗 | 仅来自 pt5 `stdby_curr_ma`（**禁止** batteryinfo） |
| pt5 失败 | 不阻塞；整段用户时间窗降级，电流记 N/A |

### 运行

```powershell
# 灭屏 TopN 批量（推荐落盘到 screen_off）
python analysis/domain/power/flow/dou_2/tool1_2/run_standby_analysis.py `
  "<高功耗目录>" `
  --top-scenes "<高功耗目录>\screen_off\topn_scenes_top3.json" `
  --screen 灭屏

# 单场景
python .../run_standby_analysis.py "<高功耗目录>" --suffix <suffix> --screen 灭屏 --force
```

流程：`testReport` 取时段 → `meta_report` 匹配 pt5 → `base_pt5.py --tool standby` →（可选）`wakeup_source.py` 全窗/高低窗 → **一次**长待机 AI（`STANDBY_DOU_SYSTEM_PROMPT`）→ 落盘 **`standby_analysis_<suffix>.json`**（与综合 AI **分开**）。

### 产物

| 文件 | 说明 |
|------|------|
| `standby_analysis_<suffix>.json` | `is_long_standby`、`standby_type`、`standby_result.ai_reply`（standby_long_dou 模板） |
| `results_json.json` | `run_collect_results.py` 自动合并 `standby_result` |

Look 报告/HTML：**电流+CPU** 与 **CPU 对比** 区块均展示「长待机分析（standby_long_dou）」独立块（不计入综合 AI）。

---

## 5) 单场景综合 AI（每场景只调 1 次 API）

**硬规则**：每个 TopN 场景的场景级 AI **只调用一次**。输入同时包含：
- `cpu_analysis_<suffix>.json`（全场景 CPU 对比摘要）
- `current_cpu_spike_<suffix>.json`（电流底电 / spike / diff_segments / 时段 CPU）

输出**同一结论**写两份（供 collect / HTML 兼容）：
- `ai_analysis_<suffix>.json`
- `current_cpu_spike_ai_<suffix>.json`

**Instagram 发布视频动态（00589）**：若存在 `record_flat_ai_<suffix>.json`，综合 AI 落盘时会自动在 `ai_reply` 末尾追加 `【长按录制平缓段专项】` 段（见 §9 与 `compose_combined_ai_reply`）。

### 已知问题库（AI 总结前必须对照）

编辑技能目录下 `known_issues.md`（与 `SKILL.md` 同级）。单场景综合 AI 与 TopN 总结调用前，`ai_client.py` 会自动把该文件注入系统提示。

- **命中**：结论标注「已知问题」，按条目判定/处理建议写，不当作新回归根因深挖。
- **门禁**：条目「特征 / 判定要点」中的量化门槛（如 KI-001 的 CPU **≥ 约 70%**）须同时满足；仅进程名相似但未达门槛 → **不得**判定为已知问题。
- **未命中**：按正常综合分析段落继续。
- **维护**：新现象追加 `KI-xxx` 条目即可，无需改脚本。

提示词：`scripts/ai_client.py` → `COMBINED_SCENE_SYSTEM_PROMPT` / `analyze_scene_combined_json`（含 `system_prompt_with_known_issues`）。

**推荐入口**（与 §9 同一步）：`run_current_cpu_spike.py ... --with-ai`  
**仅补跑 AI**（已有 spike）：`run_current_cpu_spike_ai.py` 或 `run_ai_analysis.py`（须已有 spike，否则报错退出）。

**长待机**：`standby_analysis_<suffix>.json` 仍单独归因，**不计入**上述「两次场景 AI」；与综合 AI 结论不可混写。

强约束：
- **禁止**对同一场景先跑「仅 CPU AI」再跑「仅电流 AI」。
- **禁止**再使用「复制提示词块到对话」的方式做 AI 分析。
- **禁止把结论只停留在对话里**：必须落盘。
- **落盘位置强制**：与 `cpu_analysis_<suffix>.json` 同目录（亮/灭屏分卷）。

### A) 运行脚本（推荐跟电流图一步完成）

```powershell
$high = "<高功耗目录>"
foreach ($vol in @(
  @{ dir = "screen_on";  label = "亮屏" },
  @{ dir = "screen_off"; label = "灭屏" }
)) {
  $dir = Join-Path $high $vol.dir
  $topn = Join-Path $dir "topn_scenes_top3.json"
  if (!(Test-Path $topn)) { continue }
  python analysis/domain/power/flow/dou_2/tool1_2/run_current_cpu_spike.py `
    $high --top-scenes $topn --cpu-dir $dir --with-ai
}
```

**仅补跑综合 AI（不重解析 PT5）：**

```powershell
python analysis/domain/power/flow/dou_2/tool1_2/run_current_cpu_spike_ai.py `
  --spike-dir "<高功耗目录>\screen_on" `
  --top-scenes "<高功耗目录>\screen_on\topn_scenes_top3.json" `
  --embed --force
```

可选：`--force` / `--force-ai`、`--api-key`、`--model`。

### B) `ai_analysis_<suffix>.json` 最小结构

```json
{
  "success": true,
  "suffix": "3796",
  "cpu_json": "Z:\\...\\cpu_analysis_3796.json",
  "spike_json": "Z:\\...\\current_cpu_spike_3796.json",
  "power_difference_mAh": 12.3,
  "ai_mode": "combined",
  "ai_result": {
    "success": true,
    "ai_reply": "（综合分析结论：电流时段 + CPU 进程）"
  }
}
```

`current_cpu_spike_ai_<suffix>.json` 含同一 `ai_result`（`ai_mode=combined`）。

## 6) 组装 results_json（独立）

硬要求（避免被“顺手略过”导致后面全断）：
- 这个步骤的目标是产出**唯一权威输入**：`results_json.json`。后续 TopN 总结与最终 HTML 都只认这个文件（以及 `topn_summary.json`）。
- 若缺任意 `suffix` 的 `cpu_analysis_<suffix>.json` 或 `ai_analysis_<suffix>.json`（综合 AI，见 §5），请先补齐第 4/5 步再运行本脚本。

脚本：

```text
python analysis/domain/power/flow/dou_2/tool1_2/run_collect_results.py "<top_scenes_json路径>" --cpu-dir "<cpu-json目录>" --ai-dir "<ai-json目录>" --output "<results_json输出路径>"
```

输入：
- `top_scenes_json`：由 `run_topn_select.py` 输出
- `--cpu-dir`：存放 `cpu_analysis_<suffix>.json` 的目录（**必须指向 `<高功耗目录>`**）
- `--ai-dir`：存放 `ai_analysis_<suffix>.json` 的目录（**必须指向 `<高功耗目录>`**）
- `--output`：可选；为满足“统一输出目录”，建议显式传 `<高功耗目录>\results_json.json`

输出：
- 默认输出：`<cpu-dir>/results_json.json`
- 输出 JSON 结构：`dict[suffix] -> {"cpu_data", "ai_result", "power_difference_mAh"[, "standby_result", "is_long_standby", "standby_type"]}`
- 长待机场景：同目录下 `standby_analysis_<suffix>.json` 存在时，`standby_result` 一并写入（与 `ai_result` 分离）

---

## 7) 分卷总结论（亮屏 / 灭屏各一份，内部 API）

流程（固定且不可变）：各分卷 `results_json.json` 就绪后，**前台同步**对 **亮屏、灭屏分别**运行 `run_topn_summary.py`，各落盘 `topn_summary.json`。

目标：产出**该分卷**跨场景总结论（不是全项目一份混写）。Look「电流+CPU」亮屏块 / 灭屏块顶部分别展示。

强约束：
- **禁止**只跑亮屏或只跑灭屏（有对应 TopN 产物时）。
- **禁止**把另一分卷的结论复制到本分卷。
- **禁止**再使用「复制提示词 + JSON 到对话」的方式做综合总结。
- **落盘位置强制**：`screen_on/topn_summary.json` 与 `screen_off/topn_summary.json` 各一份，与同目录 `results_json.json` 对齐。

### A) 运行脚本（推荐一次跑齐两分卷）

```powershell
$high = "<高功耗目录>"
python analysis/domain/power/flow/dou_2/tool1_2/run_topn_summary.py `
  --high $high --both
```

**单分卷（兼容）：**

```powershell
$dir = "<高功耗目录>\screen_on"   # 或 screen_off
python analysis/domain/power/flow/dou_2/tool1_2/run_topn_summary.py `
  "$dir\topn_scenes_top3.json" `
  "$dir\results_json.json" `
  --screen 亮屏 `
  --output "$dir\topn_summary.json"
```

可选参数：`--api-key`、`--base-url`、`--model`（同第 5 步）。

### B) 保存为 `topn_summary.json`（结构必须兼容）

```json
{
  "success": true,
  "screen_label": "亮屏",
  "summary": {
    "success": true,
    "ai_reply": "（本分卷总结论正文；开篇标明【亮屏】或【灭屏】）"
  },
  "top_scenes_json": "<高功耗目录>\\screen_on\\topn_scenes_top3.json",
  "results_json": "<高功耗目录>\\screen_on\\results_json.json"
}
```

---

## 8) 生成最终 HTML（独立）

脚本：

```text
python analysis/domain/power/flow/dou_2/tool1_2/run_final_html.py "<top_scenes_json>" "<results_json>" "<power_analysis_result.json>" "<topn_summary.json>" [--output "<html输出路径>"] [--no-open]
```

输入：
- `top_scenes_json`：由 `run_topn_select.py` 输出
- `results_json`：由 `run_collect_results.py` 输出
- `power_analysis_result.json`：由 `run_power_analysis.py` 输出
- `topn_summary.json`：由本文「7) TopN 综合总结（独立）」保存输出

输出：
- 默认输出：`topn_cpu_ai_results_<时间戳>.html`  
  为满足“统一输出目录”，建议显式传 `--output "<高功耗目录>\topn_cpu_ai_results_<时间戳>.html"`（或同名不带时间戳的固定文件名也可）。

---

## 9) 电流图 + CPU 时段关联（+ 综合 AI）

基于 high/low 的 meta_report `.pt5` 电流曲线与**已有** `cpu_analysis_<suffix>.json`，对比底电、找出高低版本电流差异最大的时段，按固定间隔做**差异分段**，并关联各时段/各分段内 CPU Perf 与进程对比。**不重新跑 CPU 分析**。

加 `--with-ai` 时：对 **CPU 摘要 + 电流 spike** 做**一次**综合 AI（见 §5），禁止再调第二次场景 AI。

技能脚本：`scripts/current_cpu_spike.py`  
AI 客户端：`scripts/ai_client.py`（`analyze_scene_combined_json` / `COMBINED_SCENE_SYSTEM_PROMPT`）  
入口：
- `tool1_2/run_current_cpu_spike.py`（数据 + **推荐** `--with-ai`）
- `tool1_2/run_current_cpu_spike_ai.py`（仅补跑综合 AI）

Look 看板：「电流+CPU」Tab — **Instagram 00589** 等场景展示两层 AI：
- **AI 分析（长按录制平缓段）**：专项结论（`record_flat_ai_*`）
- **AI 分析（电流+CPU）**：综合结论 + 平缓段专项合并全文（`current_cpu_spike_ai_*` / `ai_analysis_*`）

长待机另块，不计入上述合并。

### 数据来源（三路合并）

| 来源 | 路径/文件 | 用途 |
|------|-----------|------|
| **PT5 电流曲线** | high/low 的 `meta_report/*.pt5`（经 `pt5-mcp-server`） | 高低版本对齐电流、底电统计、差异曲线 |
| **已有 CPU 分析** | `cpu_analysis_<suffix>.json`（§4 产物，**不重新跑 CPU**） | 时段/分段内 Perf 块、Top 进程、全场景对比 |
| **场景元数据** | `testReport.xlsx` → `report` 表 | 场景名/描述、起止时间、时长、Excel 均流校准 |

### 结构化计算（`analyze_scene_current_cpu`）

1. **读 PT5**：对齐高低版本时长，用 report 均流校准，得到 `diff = 高 − 低`
2. **电流统计** → `current_summary`（底电最低、10s 窗平均底电、对齐均差、Excel 均差等）
3. **趋势对比** → `trend_compare`（可选统计：大形状相关等；**不用于脚本问题自动判定**）。脚本问题结论以 Look 人工下拉为准（`is_script_issue`）。
4. **滑动窗口** → `spike_windows`（默认 10s 窗、2s 步，Top3 差异最大时段）及 `dip_windows`（低版本更高时段）
5. **固定间隔分段** → `diff_segments`（默认 **10s/段**，与 Look 看板「差异分段」一致）：每段含 `mean_diff_ma`、`max/min_diff_ma`、`delta_from_prev_ma`（相对上段变化）
6. **关联 CPU**（读 `cpu_analysis`）：
   - `spike_windows[].cpu_in_window`：各最大差异窗口内高/低 Top 进程与 Perf 块
   - `diff_segments[].cpu_in_segment`：各分段内 Top 进程 + `process_compare_top`（**本段 vs 上段**进程均值变化，与看板「进程均值：本段相对上段变化」表一致）
     - 本段/上段 × 高/低 四个均值中，**某侧无该进程时按 0% 计**
     - **始终计算 Δ**：`delta_high_pct = 本段高% − 上段高%`，`delta_low_pct = 本段低% − 上段低%`；`cur_high_low_diff_pct = 本段高% − 本段低%`
   - `cpu_scene_compare`：全场景 CPU 对比（`averages_enhanced`）：`top_diff_processes`、`large_diff_processes`、`new_only_in_high`、`new_only_in_low`、`statistics`
   - `perf_timeline`：全程 Perf 块时间线
6. **降采样曲线** → `series.points`（≤6000 点，按桶保留 diff 峰/谷；供 Look 渲染，AI 提交时不带完整点列）

### 前置条件

- 第 4 步已产出 `cpu_analysis_<suffix>.json`（与 `--cpu-dir` 同目录）
- high/low 的 `meta_report` 下能找到对应场景的 `.pt5`（由 `pt5_reader.find_pt5_for_suffix` 匹配）
- 本机已 `npm install -g pt5-mcp-server`（解析链路与 MCP `pt5` 同源，见上文）
- AI 需配置环境变量 `DOU_AI_API_KEY`（见上文「AI 分析 API 配置」）

### A) 运行脚本（推荐：按亮/灭屏分卷批量）

`topn_scenes_top<N>.json` 文件名随 TopN 选取时的 `--topn` 变化（如 `top3` 或 `top10`），脚本按实际路径传入即可。

```powershell
chcp 65001 | Out-Null
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"

$high = "<高功耗目录>"

foreach ($vol in @(
  @{ dir = "screen_on";  label = "亮屏" },
  @{ dir = "screen_off"; label = "灭屏" }
)) {
  $dir = Join-Path $high $vol.dir
  $topn = Join-Path $dir "topn_scenes_top3.json"   # 或 topn_scenes_top10.json 等
  if (!(Test-Path $topn)) { continue }
  python analysis/domain/power/flow/dou_2/tool1_2/run_current_cpu_spike.py `
    $high `
    --top-scenes $topn `
    --cpu-dir $dir `
    --with-ai
}
```

**覆盖重跑（含新版分段字段 + 强制刷新综合 AI）：**

```powershell
python analysis/domain/power/flow/dou_2/tool1_2/run_current_cpu_spike.py `
  $high `
  --top-scenes "<高功耗目录>\screen_on\topn_scenes_top10.json" `
  --cpu-dir "<高功耗目录>\screen_on" `
  --with-ai --force-ai
```

**仅补跑综合 AI（已有 `current_cpu_spike_*.json`，不重新解析 PT5）：**

```powershell
python analysis/domain/power/flow/dou_2/tool1_2/run_current_cpu_spike_ai.py `
  --spike-dir "<高功耗目录>\screen_on" `
  --top-scenes "<高功耗目录>\screen_on\topn_scenes_top3.json" `
  --embed --force
```

**单场景：**

```powershell
python analysis/domain/power/flow/dou_2/tool1_2/run_current_cpu_spike.py `
  "<高功耗目录>" "<低功耗目录>" `
  --suffix 3796 `
  --cpu-dir "<高功耗目录>\screen_on" `
  --with-ai
```

低功耗目录可省略：脚本会从 `<high>\dou_prepare_result.json` 或 `scene_compare_result.json` 读取 `low`。

可选参数：

| 参数 | 说明 | 默认 |
|------|------|------|
| `--window-sec` | spike 差异统计滑动窗口（秒） | 10 |
| `--step-sec` | spike 窗口步长（秒） | 2 |
| `--top-windows` | 保留差异最大的 spike 窗口数 | 3 |
| `--output` | 单场景 JSON 输出路径 | `<cpu-dir>\current_cpu_spike_<suffix>.json` |
| `--summary-output` | 批量汇总 JSON | `<cpu-dir>\current_cpu_spike_result.json` |
| `--with-ai` | **单次综合 AI**：同时落盘 `ai_analysis_*.json` + `current_cpu_spike_ai_*.json` | 关 |
| `--force-ai` | 覆盖已存在的综合 AI 文件 | 关 |

### B) 落盘产物

| 文件 | 说明 |
|------|------|
| `current_cpu_spike_<suffix>.json` | 单场景：底电统计、曲线、spike 窗口、**差异分段**、CPU 关联、可选内嵌 `ai_result` |
| `ai_analysis_<suffix>.json` | 综合 AI 结论（与下一行同一 `ai_reply`） |
| `current_cpu_spike_ai_<suffix>.json` | 同上（HTML/兼容双读）；Instagram 平缓段专项 AI 合并后正文含 `【长按录制平缓段专项】` |
| `record_flat_ai_<suffix>.json` | Instagram 长按录制平缓段专项 AI（独立落盘，并合并进上两行） |
| `current_cpu_spike_result.json` | 批量汇总：`scenes` 索引各场景产物路径与摘要 |

单场景 JSON 核心字段：

- `current_summary`：`high_floor_ma` / `low_floor_ma` / `floor_diff_ma`（底电最低）、`high_avg_baseline_ma` / `low_avg_baseline_ma` / `avg_baseline_diff_ma`（10s 窗平均底电）、`aligned_avg_diff_ma`、`excel_*`
- `spike_windows`：差异最大的时段（含 `relative_time`、`mean_diff_ma`、`cpu_in_window`）
- `dip_windows`：低版本电流更高的时段
- `segment_interval_sec`：差异分段间隔（默认 10）
- `diff_segments`：固定间隔分段列表；每段含 `delta_from_prev_ma` 与 `cpu_in_segment.process_compare_top`（缺失进程均值按 0，Δ 仍计算）
- `cpu_scene_compare`：全场景高低 CPU 进程对比摘要
- `series.points`：降采样电流曲线（≤6000 点，峰谷保留；供 HTML 报告渲染）
- `perf_timeline`：与 CPU JSON 对齐的 Perf 块时间线（含 `high_blocks` / `low_blocks`）

### C) 综合 AI（内部 API，每场景 ×1）

流程：读 `current_cpu_spike_<suffix>.json` + `cpu_analysis_<suffix>.json` → `_slim_spike_for_ai` / `_slim_cpu_for_ai` → **一次** `analyze_scene_combined_json` → 同时落盘 `ai_analysis_*` 与 `current_cpu_spike_ai_*`。

**提交字段**：精简后的电流统计 / spike / diff_segments / cpu_scene_compare + CPU `averages_enhanced` 等（见 §5）。

**输出**：一份综合正文（底电→时段→异常/新增进程→高频与增长率→时段对齐→根因建议）。若存在 `record_flat_ai_<suffix>.json`，落盘时自动在末尾追加 `【长按录制平缓段专项】` 段。

落盘后自动合并进 `ai_analysis_*` 与 `current_cpu_spike_ai_*`；也可在综合 AI 补跑后由 `run_current_cpu_spike_ai.py` 自动拾取已有 `record_flat_ai_*` 合并。

### D) 与 HTML / 在线看板的关系

- 推荐顺序下，综合 AI 在 collect / TopN 总结 / HTML **之前**完成（见「推荐执行顺序」第 5→6→7→8 步）。
- 在线看板 **「电流+CPU」** 读取 spike 曲线与综合 AI（`ai_analysis_*` / `current_cpu_spike_ai_*` 同文，**含已合并的平缓段专项**）；Instagram 00589 另在上方面板展示专项 AI 块；长待机另块；未跑本步时该 Tab 显示空态提示。

---

## 10) 应用下载/安装检测（DOU 第 10 步，全流程最后）

在电流+CPU（§9）之后执行。扫描**高功耗** `phone_logs` 的 `sys_log*` / `main_log*`，判定下载时段、包名、uid/pid、有无安装。

**判定要点**（详见 `app_download/SKILL.md`）：

1. `Usf_Hiber/importantScene`：**`speed > 100` 且仅灭屏** 才计下载  
2. mainlog：`state:DOWNLOADING` → 下载包名（不限亮灭屏）  
3. `installation completed for` → 安装完成

子 skill：`app_download/SKILL.md`  
核心脚本：`app_download/scripts/download_traffic.py`  
入口：`tool1_2/run_app_download.py`

### 落盘硬规则（必须遵守）

| 文件 | 路径 |
|------|------|
| JSON | `<高功耗目录>/app_download_result.json` |
| TXT | `<高功耗目录>/app_download_result.txt` |

- **禁止**写入仓库 `temp/`、本机桌面或其它非 high 路径。
- Look 看板只从高功耗共享目录读上述产物。

### 运行

```powershell
chcp 65001 | Out-Null
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"

$high = "<高功耗目录>"
python analysis/domain/power/flow/dou_2/tool1_2/run_app_download.py $high
```

可选：`--speed-min 100`（Usf_Hiber 阈值）、`--gap-sec 120`（命中合并间隔）、`--min-sec 3`。

### 结论内容（须含）

1. 什么时间段有下载  
2. 在下载什么（包名 + uid）  
3. uid / pid / download_id 含义  
4. 有无安装、安装包名与时间  

### 与 Look 看板

- Tab **「下载安装」** 展示时间轴（横轴=时间，点击标注看详情）、`narrative` 摘要、Usf_Hiber / DOWNLOADING / 安装表。
- 概览产物格显示「下载安装」是否就绪；左侧项目徽章含「下载」。

### 门禁

- 全流程结束前须存在 `app_download_result.json`（或至少 `.txt`）；否则看板「下载安装」为空态。

---

## 11) Bugreport 持锁分析（DOU 第 9 步）

在 HTML 渲染（第 8 步）之后、应用下载检测（第 10 步）之前执行。**高/低功耗均须跑 wakelock**；扫描各自 `phone_logs` 下 bugreport，解析 Battery History 中 **longwake** 持锁。

### 为什么「低功耗 Wakelock」会空（常见踩坑）

| 原因 | 表现 | 处理 |
|------|------|------|
| 只跑了 `...py $high`，且 high 下**没有** `dou_prepare_result.json` / 或旧版脚本不认 `scene_compare` | 终端只打印「高功耗」一段；`<low>/bugreport_*_result.json` 不存在；Look「低功耗 Wakelock」空 | **显式 `--low $low`**（推荐）；或确保 `scene_compare_result.json` 已含有效 `low` 后重跑（当前脚本会回退读该文件） |
| 手工路径分析（用户直接给 high/low）未跑 JIRA prepare | 无 `dou_prepare_result.json`，旧逻辑无法自动发现 low | 同上，命令行带 `--low` |
| UNC 上整包解压 bugreport 因路径过长失败 | 解压半截 / 误选 `dumpstate_log` / `bugreport_audiomix.txt` 产物 | `dou_unzip.py` 只把主 txt 落到 `bugreports/bugreport_main.txt`（短文件名）；重跑第 9 步 |

**low 路径解析顺序（`resolve_dou_side_dirs`）**：`--low` → `dou_prepare_result.json` → `scene_compare_result.json` → `power_analysis_result.json`。解析失败时只跑 high，并打印 WARN。

### Bugreport 日志位置与解压

典型路径（high/low 对称）：

```text
<side>/phone_logs/mobile_log1/bugreports/bugreport-....zip
  → 主 txt 解压为同目录 bugreport_main.txt（短路径，供 AudioMix/Longwake）
  → （不再依赖把整个 FS/ 树解到超长 UNC 子目录）
```

- 第 9 步脚本（`scripts/dou_unzip.py`）会**自动**解压 mobile_log + 抽取 bugreport 主 txt。
- 查找时优先 `bugreport_main.txt`，并忽略 `dumpstate_log` / 本流程产物 `bugreport_audiomix.txt` / `bugreport_longwake.txt`。
- 手工前置见 §0.1 B 节。

### 11.1 全部 Long Wakelock

子脚本：`bugreport_audiomix/scripts/parse_longwake.py`  
**DOU 入口**：`tool1_2/run_bugreport_longwake.py`

| 文件 | 路径 |
|------|------|
| 摘要 JSON | `<高/低功耗目录>/bugreport_longwake_result.json` |
| 详细 JSON/TXT/HTML | `<bugreport目录>/bugreport_longwake.{json,txt,html}` |

```powershell
# 推荐：显式传 low（手工路径 / 无 prepare JSON 时必须）
python analysis/domain/power/flow/dou_2/tool1_2/run_bugreport_longwake.py $high --low $low
```

### 11.2 AudioMix 持锁（longwake 子类，含场景对齐）

在 HTML 渲染（第 8 步）之后、应用下载检测（第 10 步）之前执行。解析 **AudioMix** 持锁事件，输出时间轴与持锁方结论。

**判定要点**（详见 `bugreport_audiomix/SKILL.md`）：

1. 自动解压并搜索 `<side>/phone_logs/**/bugreport*.txt`（优先 `bugreport_main.txt`）
2. 时间轴：`+longwake` / `-longwake` / `longwake` → 持锁区间与时长分桶
3. 汇总：`Wake lock u0aXXX AudioMix: ...` → Battery Stats 累计
4. UID→包名：从 bugreport 内 `com.xxx/u0aXXX` 等自动映射
5. **场景对齐**使用**同 side** 目录下的 `meta_report/testReport.xlsx`

子 skill：`bugreport_audiomix/SKILL.md`  
核心脚本：`bugreport_audiomix/scripts/parse_audiomix.py`  
**DOU 入口**：`tool1_2/run_bugreport_audiomix.py`  
低层入口（直接传 bugreport 路径）：`bugreport_audiomix/run_bugreport_audiomix.py`

### 落盘硬规则（必须遵守）

| 文件 | 路径 |
|------|------|
| 摘要 JSON | `<高/低功耗目录>/bugreport_audiomix_result.json` |
| 摘要 TXT | `<高/低功耗目录>/bugreport_audiomix_result.txt` |
| 详细 JSON | `<bugreport目录>/bugreport_audiomix.json` |
| 详细 TXT（时间轴主视图） | `<bugreport目录>/bugreport_audiomix.txt` |
| 详细 HTML（泳道图） | `<bugreport目录>/bugreport_audiomix.html` |

- 摘要 JSON **必须**落在各 side 根目录；详细产物留在 bugreport 目录，摘要 JSON 的 `artifacts` 字段指向详细路径。
- JSON 含 `"side": "high"|"low"` 标识来源。
- 无 bugreport 时仍须运行本步：写入 `skipped: true` 的 JSON，退出码 0。

### 运行（DOU 标准）

```powershell
chcp 65001 | Out-Null
$OutputEncoding = [Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$env:PYTHONUTF8 = "1"

$high = "<高功耗目录>"
$low  = "<低功耗目录>"
# 必须两边都跑：显式 --low（勿只传 $high）
python analysis/domain/power/flow/dou_2/tool1_2/run_bugreport_audiomix.py $high --low $low
python analysis/domain/power/flow/dou_2/tool1_2/run_bugreport_longwake.py $high --low $low
```

可选：未传 `--low` 时按上文顺序从 high 根 JSON 回退；`--bugreport` 显式指定 high 侧 bugreport 目录/txt；`--output-json` / `--output-txt` 覆盖 high 摘要路径。

### 结论内容（摘要 TXT 须含）

1. Battery Stats Top 持锁方与累计时长  
2. 时间轴按 owner 合计与最长单段  
3. **DOU 场景对齐**：每条持锁区间标注重叠场景（suffix/desc/亮灭屏）  
4. **场景内异常**（时长 + 持锁方×场景匹配，见 `bugreport_audiomix/scripts/scene_align.py`）
5. 极长/长持锁（≥5min）区间列表
6. 详细 HTML/TXT 产物路径（Look 看板「Long Wakelock」Tab；AudioMix 子区块按需展开）

### 与 Look 看板

- Tab **「Long Wakelock」**：**高功耗 / 低功耗** 各一个可折叠区块，**默认均收起**；展开后含 Long Wakelock 主页面与 AudioMix 副页面
- 区块内子表（细分泳道、汇总表、全部 AudioMix 区间）亦**默认收起**
- 概览产物格：**Long Wakelock**、**AudioMix**；左侧项目徽章 **LongWake**
- API `/bugreport_longwake` / `/bugreport_audiomix` 必须返回 `sides.high` / `sides.low`；前端无 `sides` 时低功耗会显示为空（**旧 Look 进程需重启**）。健康检查 `GET /api/health` 的 `build` 字段可用于确认是否已加载新代码。

### 门禁

- 第 9 步命令**必须执行**（不可因「可能没 bugreport」而跳过脚本本身）。
- 若某 side 的 `phone_logs` 下存在 bugreport，则该 side 的 `bugreport_audiomix_result.json` 中 `skipped` 不得为 true。
- 全流程第 10 步仍须 `app_download_result.json`（仅 high）。

---

> 推荐执行顺序见「推荐执行顺序（拆分后）」：第 5 步电流图+综合 AI（每场景 ×1），**第 9 步 `run_bugreport_audiomix.py <high> --low <low>` + `run_bugreport_longwake.py <high> --low <low>`（两侧都必须跑）**，**第 10 步 `run_app_download.py` 为全流程最后**。
