---
name: base_pt5
description: 通过 PT5 MCP 解析 Monsoon .pt5 实测电流，输出短待机平均电流、采集时间戳及高低功耗子窗口（供 flow_power_standby_short 使用）。
runtime:
  is_critical: false
  on_failure: continue
---
## 适用场景

拆机实测：从工作区或指定路径自动查找 **`.pt5`** 文件，经 **Cursor PT5 MCP 服务**读取电流序列，计算并输出待机分析所需结构化字段：

- **`stdby_curr_ma`**：全程平均电流（mA）→ flow 中 **`Stdby_Curr`**
- **`base_curr_ma`**：底电流（滑窗最低均值，mA）
- **`capture_time_start` / `capture_time_end`**：采集起止绝对时间（用于与 APLog 灭屏段对齐）
- **高低功耗子窗口**（供下游 `base_cpuinfo` / `base_kernel_standby` 的 `-t` 使用）：
  - `min_power_time_start` / `min_power_time_end` / `min_power_value`
  - `max_power_time_start` / `max_power_time_end` / `max_power_value`

## 执行方式

### 步骤 1：确认 MCP 与依赖

1. 已安装 **Node.js**（`npx` 可用）
2. Cursor `mcp.json` 中已配置 **`pt5`** 服务（见下节 [MCP 配置](#mcp-配置)）
3. 安装 Python 依赖：

```bash
pip install -r scripts/requirements.txt
```

### 步骤 2：执行解析脚本

```bash
# 推荐：传入工作区根、downloads/、retest/ 或 APLog 目录，自动递归查找 .pt5
python scripts/base_pt5.py 'temp/<DATE>/<JIRA_KEY>'

# 或直接指定 .pt5 所在目录 / 文件
python scripts/base_pt5.py 'E:/jiradata/LK7KOS17-60/retest'
python scripts/base_pt5.py 'E:/jiradata/LK7KOS17-60/retest/xxx.pt5'
```

**默认行为**：`--tool standby`，结果以 **text 键值对** 打印到终端（编排层 / AI 直接读取 stdout）。

**超时**：视 pt5 文件大小，通常 30~120s；大文件（数百万采样点）可能更久。

### 步骤 3：等待脚本执行完成

- 脚本执行完成的标志：终端输出包含 `stdby_curr_ma:` 与 `pt5_file:` 行
- `success: false` 或 `error:` 表示未找到 pt5 或 MCP 调用失败

### 步骤 4：返回执行结果

```
base_pt5 执行完成，解析成功/失败
```

将终端中的 `stdby_curr_ma`、`capture_time_*`、高低功耗窗字段写入 flow 上下文，供 `flow_power_standby_short` 步骤 2 起使用。

## 关键要求

- **输出到终端**：默认 `--format text`，不写额外结果文件；禁止伪造字段
- **先 pt5 后 kernel**：在 `base_kernel_standby`（灭屏段匹配）之前执行，首次调用**不需要** `sleep_time_*`
- **无 pt5 则阻塞**：若无有效 `.pt5` 且无 JIRA/手动 `Stdby_Curr`，flow 应阻塞并提示复测
- **yaml 辅助**：同名或同 `test_id` 的 `.yaml` 若含 `collect_start_time` / `collect_end_time`，优先用于采集起止时间交叉校验；**高低功耗子窗口仍由 pt5 滑窗计算**
- **不要提前返回**：须等待 MCP 解析完成后再读取输出

## 脚本使用说明

### 依赖安装

```bash
pip install mcp numpy -i https://pypi.tuna.tsinghua.edu.cn/simple
# 或
pip install -r scripts/requirements.txt
```

### MCP 配置

官方包：[pt5-mcp-server（npm）](https://www.npmjs.com/package/pt5-mcp-server) · [GitHub](https://github.com/doudoufu/pt5-mcp-server)

在 Cursor 中编辑 `~/.cursor/mcp.json`（Windows：`%USERPROFILE%\.cursor\mcp.json`），**服务名必须为 `pt5`**（与 `base_pt5.py` 一致）。

#### 方式一：npx（推荐，免安装）

```json
{
  "mcpServers": {
    "pt5": {
      "command": "npx",
      "args": ["pt5-mcp-server"]
    }
  }
}
```

#### 方式二：全局安装

```bash
npm install -g pt5-mcp-server
```

```json
{
  "mcpServers": {
    "pt5": {
      "command": "pt5-mcp-server"
    }
  }
}
```

#### 方式三：本地源码（开发调试）

```bash
git clone https://github.com/doudoufu/pt5-mcp-server.git
cd pt5-mcp-server
npm install
npm run build
```

```json
{
  "mcpServers": {
    "pt5": {
      "command": "node",
      "args": ["D:/path/to/pt5-mcp-server/build/index.js"]
    }
  }
}
```

配置完成后重启 Cursor，或在 **Settings → MCP** 中确认 `pt5` 服务已连接。

`base_pt5.py` 默认读取 `~/.cursor/mcp.json`；自定义路径可用 `--config` 指定。

#### MCP 工具（供参考）

| 工具 | 说明 |
|---|---|
| `parse_pt5` | 解析 .pt5，返回 avg/min/max 电流等摘要 |
| `get_pt5_channels` | 列出可用测量通道 |
| `get_pt5_samples` | 按时间范围取采样（可降采样） |
| `export_pt5_csv` | 导出 CSV |
| `get_pt5_header` | 返回头信息与校准元数据 |
| `analyze_pt5_trend` | 电流趋势、峰值、周期性分析 |

`base_pt5.py` 的 `--tool standby` 在内部组合调用上述能力，flow 侧只需读脚本 stdout。

### 输入参数

| 参数 | 作用 |
|---|---|
| `path`（位置参数） | 工作区根、`downloads/`、`retest/`、日志目录，或单个 `.pt5` 文件 |
| `--tool` | 默认 `standby`；可选 `info`/`parse`/`channels`/`header`/`samples`/`trend`/`current` |
| `--format` | `text`（默认）或 `json` |
| `--window-sec` | 高低功耗滑窗长度（秒），默认 `10` |
| `--step-sec` | 滑窗步长（秒），默认 `2` |
| `--config` | MCP 配置文件路径，默认 `~/.cursor/mcp.json` |

## 输出说明

| 字段 | 说明 |
|---|---|
| `stdby_curr_ma` | 全程平均电流（mA）→ **`Stdby_Curr`** |
| `base_curr_ma` | 底电流：有效区间内滑窗最低均值（mA） |
| `capture_time_start` / `capture_time_end` | pt5 采集起止时间（`YYYY-MM-DD HH:MM:SS.mmm`） |
| `min_power_time_start` / `min_power_time_end` | 最低平均电流子窗起止 |
| `min_power_value` | 该子窗平均电流（mA） |
| `max_power_time_start` / `max_power_time_end` | 最高平均电流子窗起止 |
| `max_power_value` | 该子窗平均电流（mA） |
| `pt5_file` | 实际解析的文件路径 |

### 使用示例

#### 基本用法（短待机 flow 步骤 1）

```bash
python scripts/base_pt5.py 'temp/20260617/LK7KOS17-85'
python scripts/base_pt5.py 'temp/20260617/LK7KOS17-85/downloads'
```

#### 本地 jiradata 目录

```bash
python scripts/base_pt5.py 'E:/jiradata/LK7KOS17-60/retest'
```

#### JSON 输出（调试）

```bash
python scripts/base_pt5.py 'E:/jiradata/LK7KOS17-60/retest' --format json
```

#### 查看 pt5 原始摘要（非 standby 字段）

```bash
python scripts/base_pt5.py 'path/to/file.pt5' --tool parse --format json
```

### .pt5 查找规则

1. 若 `path` 本身为 `.pt5` 文件，直接使用
2. 否则从 `path` 向上查找 `downloads/` 并递归 `*.pt5`
3. 仍未找到则在 `path` 下递归 `*.pt5`
4. 多个候选时取**修改时间最新**的文件

### 与灭屏段匹配（flow 步骤 2，本 skill 不执行）

1. 本 skill 产出 `capture_time_start` ~ `capture_time_end`
2. `base_kernel_standby` 筛选 8.5~11.5 min / 55~65 min 有效 OFF 段：
   - **1 段** → 直接采用
   - **≥2 段** → 用 `capture_time_*` 与各段求重叠，选用重叠最大段

### 故障排除

- **`MCP 配置中未找到 'pt5' 服务`**：检查 `mcp.json` 中 `mcpServers.pt5` 是否存在；服务名须为 `pt5`（见 [npm README](https://www.npmjs.com/package/pt5-mcp-server)）
- **`未找到 .pt5 文件`**：确认 `base_download` 已下载，或路径指向含 `.pt5` 的 `downloads/` / `retest/`
- **MCP 启动失败**：确认 Node.js / `npx` 可用；优先用 `npx pt5-mcp-server` 方式；全局安装时执行 `npm install -g pt5-mcp-server`
- **采集起止时间异常**：检查同名 `.yaml` 的 `collect_start_time` / `collect_end_time`；无 yaml 时以 pt5 头 `captureDate` + 末采样时间为准
- **高低功耗窗起止相同**：增大 `--window-sec`（默认 10s）；确认 pt5 电流序列非空
