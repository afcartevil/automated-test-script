# 产物仓创建报告

## 基本信息
- **BOM 名称**: {BOM_Name_Target}
- **源路径**: {SourceFolder}
- **目标路径**: {TargetFolder}
- **复制时间**: {DateTime}

## 复制结果
| 项目 | 状态 |
|------|------|
| 源文件夹 | {Exists} |
| 目标路径 | {Exists} |
| 复制文件数 | {FileCount} |

## 操作日志
{Log}

## 注意事项
1. 请确认产物已编译完成
2. 目标文件夹如有同名将被覆盖
3. 建议定期备份产物仓

---

## 产物仓结构示例
```
{BOM_Name_Target}/
├── config/
│   ├── modem_config.xml
│   └── rf_params.cfg
├── firmware/
│   └── modem.bin
├── include/
│   └── modem_api.h
├── lib/
│   └── libmodem.so
└── tools/
    └── rf_calibration_tool.exe
```