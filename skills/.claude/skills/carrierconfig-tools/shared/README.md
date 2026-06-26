# Shared Resources

本目录存放各 CarrierConfig skill 共用的数据与脚本，随 `skills/` 目录一起拷贝即可。

| 路径 | 说明 |
|------|------|
| `data/carrier_keys_matrix.xlsx` | 矩阵表（Project / CarrieId_Ims / Carrier_Config / carrier_keys / jira_issue_notes） |
| `scripts/refresh_matrix.py` | 从 Android 源码刷新 carrier_keys 数据的离线工具 |
| `scripts/requirements.txt` | 脚本依赖（openpyxl） |

各 skill 引用矩阵文件时，统一使用相对于 **skills 根目录** 的路径：

```
shared/data/carrier_keys_matrix.xlsx
```
