---
name: base_modem_data
description: 计算蜂窝数传功耗
---
## 适用场景
使用 `modem_data.py` 计算蜂窝数传功耗，支持以下功能：

- 自动合并多个 .cap 文件（使用 mergecap 工具）
- 解析 .cap 文件并生成 linli.txt
- 计算指定时间范围内的数传功耗
- 支持仅指定开始时间或结束时间的情况

## 前置条件

### 主机工具（非 Python 库）

`tshark`、`mergecap` 来自 **Wireshark 安装包** 自带的命令行程序，不是 `pip install` 的 Python 库。检测逻辑在 `scripts/wireshark_cli.py`（与 `modem_data.py` 同目录，仅作 import，勿单独当业务入口）。

| 命令 | 作用 |
|------|------|
| `tshark` | 解析 `.cap` 抓包 |
| `mergecap` | 多个 `.cap` 合并 |

安装方式：

- **Windows**：安装 [Wireshark](https://www.wireshark.org/) 或 `winget install WiresharkFoundation.Wireshark`；可用 `--auto-install-wireshark`（需 winget）。
- **Linux / WSL**（支持 `--check-wireshark-cli` 与数传分析，需本机已装 CLI）：

```bash
sudo apt update
sudo apt install -y wireshark tshark
# 若提示无 tshark 包，可试: sudo apt install -y wireshark-common
tshark -v && mergecap -v
```

安装后若命令不在默认 PATH，用 `modem_data.py --wireshark-dir /usr/bin` 或设置 `WIRESHARK_HOME`。

### 运行前检测（推荐）

在 `invoke base_modem_data` 分析 cap **之前**先执行（无需日志路径）：

```bash
python scripts/modem_data.py --check-wireshark-cli
```

可选自动安装（**仅 Windows**，且系统有 `winget`；Linux 请用 apt 手动安装）：

```bash
python scripts/modem_data.py --check-wireshark-cli --auto-install-wireshark
```

退出码 `0` 表示 `tshark` 与 `mergecap` 均可用；非 `0` 则不要进入数传分析，在结论中记录「数传量化阻塞」。

手动快速检查：

```bash
tshark -v
mergecap -v
```

说明：

- 脚本会优先从 `PATH`、常见 Wireshark 安装目录，以及环境变量 `WIRESHARK_HOME` / `WIRESHARK_DIR` 中查找
- 若仍找不到，可通过 `--wireshark-dir` 手动指定安装目录
- 正式分析时也可在 `modem_data.py` 上加 `--auto-install-wireshark`（Agent 在检测到缺工具时会自动重试该参数）

## 路径与待机类型

- **仅用于 `standby_type=DATA`（蜂窝/移动数据待机）**；WiFi 待机请用 `base_wifi_data`。
- `-d` 推荐传工作区根 `temp/<DATE>/<KEY>/` 或 `converted/NTLog/`；脚本优先使用 `converted/NTLog/` 下扁平化后的 `.cap`。
- 探测 cap（不分析）：`python scripts/modem_data.py -d <工作区> --detect-caps`

## 执行方式

在技能目录下执行（或使用仓库内脚本的绝对路径）：

```bash
python modem_data.py [options]
```

## 参数说明

| 参数 | 作用 | 生效条件 |
|---|---|---|
| `-d DIR`, `--directory DIR` | 指定日志路径（cap文件路径或包含cap文件的文件夹路径） | 必须指定 |
| `-t START END`, `--time START END` | 指定开始时间和结束时间（格式：YYYY-MM-DD HH:MM:SS） | 可选，若只指定一个时间，则视为开始时间 |
| `--wireshark-dir DIR` | 指定 Wireshark 安装目录（目录中应包含 `tshark` / `mergecap`） | 可选 |
| `--auto-install-wireshark` | Windows 下若缺少 `tshark` / `mergecap`，尝试使用 `winget` 自动安装 Wireshark CLI | 可选 |
| `--check-wireshark-cli` | 仅检测/安装主机 Wireshark CLI，不分析 cap（无需 `-d`） | 可选 |

## 使用示例

```bash
# 仅指定日志路径，计算所有时间的数传功耗
python modem_data.py -d E:\path\to\folder

# 指定开始时间和结束时间，计算该时间范围内的数传功耗
python modem_data.py -d E:\path\to\file.cap -t "2026-03-04 17:42:14" "2026-03-05 09:09:57"

# 仅指定开始时间，计算开始时间之后的数传功耗
python modem_data.py -d E:\path\to\folder -t "2026-03-04 17:42:14"

# 仅指定结束时间，计算结束时间之前的数传功耗
python modem_data.py -d E:\path\to\folder -t "" "2026-03-05 09:09:57"

# Wireshark 已安装但未加入 PATH，直接指定安装目录
python modem_data.py -d E:\path\to\folder --wireshark-dir "C:\Program Files\Wireshark"

# Windows 下缺少 Wireshark CLI 时，自动安装后继续分析
python modem_data.py -d E:\path\to\folder --auto-install-wireshark
```

## 输出说明

执行脚本后，会输出以下格式的信息：

```
Start_time: 2026-03-11 19:02:29, End_time: 2026-03-11 20:02:29, data_transfer_power: 28.59mA
```

或不指定时间范围时：

```
Start_time: all, End_time: all, data_transfer_power: 36.74mA
```

## 注意事项

- 如果存在多个 `.cap` 文件，会自动使用 `mergecap` 工具合并
- 脚本优先选择以 `tcp` 开头的 cap 文件进行分析
- 如果指定路径下存在 `linli.txt` 文件，会直接使用该文件进行计算
- 如果不存在 `linli.txt` 文件，会自动解析 `.cap` 文件生成
- 时间格式必须为 `YYYY-MM-DD HH:MM:SS`，否则会报错
- 若系统里已有 Wireshark，但命令不在 PATH，可通过 `--wireshark-dir` 或环境变量 `WIRESHARK_HOME` / `WIRESHARK_DIR` 指定
- `--auto-install-wireshark` 当前只支持 Windows，并依赖系统可执行 `winget`
- Windows 下若 netlog 解压路径过深，建议先把 `NTLog_*` 复制到较短目录（如 `temp/<DATE>/<KEY>/converted/NTLog/`）后再分析

## 常见失败

- `tshark` 不在 PATH：无法解析 `.cap`
- `mergecap` 不在 PATH 且目录中有多个 `.cap`：无法合并多个抓包
- `winget` 不可用：自动安装无法执行，需要手动安装 Wireshark 或通过 `--wireshark-dir` 指定安装目录
- 只有 `.cap` 但无可解析包：不会生成 `linli.txt`