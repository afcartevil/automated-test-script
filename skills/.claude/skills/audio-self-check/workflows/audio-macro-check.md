# 音频软件宏控检查



## 必需输入



`代码基础路径`、`项目名`、`音频软件配置表`（目录含 xlsx，或 `KEY=value` 文本列表，见 `examples.md`）



## ProjectConfig.mk 路径



优先 `vendor/transsion/projects/<项目名>/`，备选 `vendor/vendor/transsion/projects/<项目名>/`；双路径不存在则停止。



## 取表与解析



- **文本**：直接读宏名与期望值（多为 `TRAN_*`）。

- **目录**：`Get-ChildItem -LiteralPath` 枚举（勿 Glob 外盘）；忽略 `~$*.xlsx`；xlsx 占用则复制到 `%TEMP%` 再解析。

- **xlsx**：`zipfile` + `sharedStrings` + `sheet*.xml`；B 类表 0 个 `TRAN_*` 为正常。



## 表类型与对比



| 类型 | 特征 | 做法 |

|------|------|------|

| **A Tran** | 含 `TRAN_*` / `KEY=value` | 与 `ProjectConfig.mk` 逐条 diff |

| **B 平台硬件** ；sheet2；`MTK_*`/PA/I2C，无 `TRAN_*` | 仅 diff **MTK_***（C 列拆宏名，D 列取值）；硬件项仅备注；**不**强行比 Tran 宏 |



用户要查 `TRAN_AUDIO_*` 但表为 B 类：说明无法完成 Tran 一章对比，可摘录工程内 Tran 宏现状；勿报「扫描失败」。



## 结论要求



- 写明 **表类型 A/B**、**对比维度**；差异列「宏名 / 期望 / 实际」。

- 仅对比，不改代码与表；中文输出；差异待用户确认。


