# AI适配调试 · 前置信息收集模板

## 产物

| 文件 | 说明 |
|------|------|
| `AI适配调试_前置信息收集模板.xlsx` | 可下发业务同事填写的 Excel |
| `generate_adapt_prereq_xlsx.py` | 重新生成脚本（字段与 Console 内置域对齐时改此脚本） |

生成命令：

```bash
# Windows
"%LOCALAPPDATA%\Programs\Python\Python312\python.exe" generate_adapt_prereq_xlsx.py
```

## 设计要点

1. **与 Console 字段 key 1:1**：`field_key` 对应 `form_data` / `AdaptLayoutFieldDef.name`。
2. **项目编码关联**：`01_项目登记.project_code` = 各业务域表第一列，支持一机多域。
3. **分工作区前缀**：`AD_*`（适配调试）、`FA_*`（特性适配）、`CC_*`（运营商）。
4. **可机读表头**：域表第 8–12 行为元数据（key/中文/必填/类型/示例），第 13 行起为数据。
5. **枚举下拉**：`select` 列带数据验证，便于自动回填时用原值（如 `upgrade`）。
6. **`99_字段字典`**：全量目录，供后续导入程序做校验与列映射。

## 建议回填流程（后续开发）

```
Excel → 按 project_code + workspace_id + domain_id
     → form_data[field_key] = value（跳过空）
     → 校验 required=Y
     → 调用/写入 Adapt 任务启动参数
```

## 覆盖域（adapt-debug）

TP / 振动 / LCM / 指纹 / 音频 / 充电 / Sensor / 安全 / 小系统 / Modem / 通信框架  

另含特性适配 TP、ECC、APN 扩展 Sheet；ECC 多号码见 `02_ECC条目`。
