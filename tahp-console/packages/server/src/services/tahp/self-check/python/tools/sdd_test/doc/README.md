# 文档中心

此目录用于沉淀框架知识，降低新人和自动化 Agent 的上手成本。

## 文档索引

- `pytest-basics.md`：pytest 基础概念与常用命令。
- `framework-overview.md`：框架摘要、执行链路、关键模块职责。
- `framework-api.md`：框架提供的入口、fixture、hook、报告能力。
- `adb-api.md`：`adb_utils.py` 支持的方法清单与返回约定。
- `custom-markers.md`：设备能力 marker 与等级 marker（L2/L3）说明。
- `minimal-cases/README.md`：最小用例导航（全部为非 `.py` 文件）。

## 阅读建议

1. 新人先看：`framework-overview.md` -> `minimal-cases/README.md`
2. 编写新用例前看：`custom-markers.md`、`framework-api.md`
3. 需要拉设备信息时看：`adb-api.md`
4. 需要 pytest 语法时看：`pytest-basics.md`
