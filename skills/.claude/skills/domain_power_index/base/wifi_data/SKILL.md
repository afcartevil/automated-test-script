---
name: base_wifi_data
description: 计算WiFi数传功耗
---
## 适用场景
使用 `wifi_data.py` 计算WiFi数传功耗，支持以下功能：

- 自动合并多个 .cap 文件（使用 mergecap 工具）
- 解析 .cap 文件并生成 linli.txt
- 计算指定时间范围内的数传功耗
- 支持仅指定开始时间或结束时间的情况

## 前置条件

### Python 依赖
```bash
pip install pyshark -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 主机工具（非 Python 库）

`tshark`、`mergecap` 来自 **Wireshark** 安装包自带的命令行程序。检测逻辑在 `scripts/wireshark_cli.py`（与 `wifi_data.py` 同目录；与 modem 侧副本需保持同步，勿单独当业务入口）。

### 运行前检测（推荐）

在分析 cap **之前**先执行（无需日志路径）：

```bash
python scripts/wifi_data.py --check-wireshark-cli
```

可选自动安装（仅 Windows，且系统有 `winget`）：

```bash
python scripts/wifi_data.py --check-wireshark-cli --auto-install-wireshark
```

退出码 `0` 表示工具可用；非 `0` 则在结论中记录「数传量化阻塞」并跳过 WiFi 数传量化。

## 路径与待机类型

- **仅用于 `standby_type=WIFI`（WiFi 待机）**；蜂窝/Data 待机请用 `base_modem_data`。
- `-d` 推荐传工作区根 `temp/<DATE>/<KEY>/` 或 `converted/NTLog/`；脚本优先使用 `converted/NTLog/` 下扁平化后的 `.cap`（优先 wlan/wifi 命名）。
- 探测 cap（不分析）：`python scripts/wifi_data.py -d <工作区> --detect-caps`

## 执行方式

在技能目录下执行（或使用仓库内脚本的绝对路径）：

```bash
python wifi_data.py [options]
```

## 参数说明

| 参数 | 作用 | 生效条件 |
|---|---|---|
| `-d DIR`, `--directory DIR` | 指定日志路径（cap文件路径或包含cap文件的文件夹路径） | 分析时必填 |
| `-t START END`, `--time START END` | 指定开始时间和结束时间（格式：YYYY-MM-DD HH:MM:SS） | 可选，若只指定一个时间，则视为开始时间 |
| `--wireshark-dir DIR` | 指定 Wireshark 安装目录（包含 tshark/mergecap） | 可选 |
| `--auto-install-wireshark` | Windows 下若缺少 tshark/mergecap，尝试 winget 安装 Wireshark CLI | 可选 |
| `--check-wireshark-cli` | 仅检测/安装主机 Wireshark CLI，不分析 cap（无需 `-d`） | 可选 |

## 使用示例

```bash
# 运行前检测
python scripts/wifi_data.py --check-wireshark-cli

# 仅指定日志路径，计算所有时间的数传功耗
python wifi_data.py -d E:\path\to\folder

# 指定开始时间和结束时间，计算该时间范围内的数传功耗
python wifi_data.py -d E:\path\to\file.cap -t "2026-03-04 17:42:14" "2026-03-05 09:09:57"

# 仅指定开始时间，计算开始时间之后的数传功耗
python wifi_data.py -d E:\path\to\folder -t "2026-03-04 17:42:14"

# 仅指定结束时间，计算结束时间之前的数传功耗
python wifi_data.py -d E:\path\to\folder -t "" "2026-03-05 09:09:57"

# Wireshark 已安装但未加入 PATH
python wifi_data.py -d E:\path\to\folder --wireshark-dir "C:\Program Files\Wireshark"
```

## 输出说明

执行脚本后，会输出以下格式的信息：

```
Start_time: 2026-03-11 19:02:29, End_time: 2026-03-11 20:02:29, WiFi_transfer_power: 28.59mA
```

## 注意事项

- 如果存在多个 `.cap` 文件，会自动使用 `mergecap` 工具合并
- 脚本优先选择以 `tcp` 开头的 cap 文件进行分析
- 如果指定路径下存在 `linli.txt` 文件，会直接使用该文件进行计算
- 如果不存在 `linli.txt` 文件，会自动解析 `.cap` 文件生成
- 时间格式必须为 `YYYY-MM-DD HH:MM:SS`，否则会报错
- 正式分析时也可加 `--auto-install-wireshark`（Agent 检测到缺工具时会自动重试该参数）
