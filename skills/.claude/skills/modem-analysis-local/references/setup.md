# 环境准备

## Python

```powershell
cd <skill-root>
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

需要 Box 网盘自动下载时，取消 `requirements.txt` 中 `playwright` 注释并执行：

```powershell
python -m playwright install chromium
```

## 配置文件

1. `copy .env.example .env`
2. `copy .env log-pipeline\.env`（pipeline 与 analysis 共用 `WORKSPACE_ROOT`）

## 外部工具（日志准备）

| 工具 | 用途 | 环境变量 |
|------|------|----------|
| 7-Zip | 解压 rar/7z | `SEVEN_ZIP_EXE` |
| ELT / NLT | MTK trace 导出 | `ELT_HOME`, `NLT_HOME` |
| Wireshark | PCAP → txt | `WIRESHARK_PATH` |
| QUTS | QCOM diag 导出 | `QUTS_PYTHON_PATH` |

检查（若 log-pipeline 带了检查脚本）：

```powershell
python log-pipeline\_shared\check_environment.py
```

## 工作区

- 使用本地盘路径，避免直接把 `WORKSPACE_ROOT` 指到 UNC
- 单 issue 约占用数 GB，确保磁盘空间充足
