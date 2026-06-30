# 框架摘要

## 1. 框架定位

这是一个以设备属性校验为主的 `pytest` 自动化框架：

- 通过 ADB 获取设备属性
- 在收集阶段根据 marker 过滤不适配用例
- 执行后输出统一 JSON 报告

## 2. 执行总流程

1. `si_run.py` 解析命令行，拼接 pytest 参数。
2. 注入 `--device-serial`（未传入时自动取首台设备）。
3. 进入 `src/conftest.py`：
   - 注册自定义 marker
   - 创建报告收集器
   - 收集阶段执行等级过滤 + 设备能力过滤
4. 执行用例并通过 hook 聚合结果。
5. 会话结束写入 JSON 报告。

## 3. 关键模块职责

- `si_run.py`：命令入口和参数路由。
- `src/conftest.py`：pytest 生命周期编排。
- `src/conftests/device.py`：设备信息装配与环境 fixture。
- `src/conftests/marker_check.py`：设备能力 marker 判定函数集合。
- `src/conftests/test_level.py`：L1/L2/L3 等级策略与周/日版本判断。
- `src/conftests/report.py`：测试结果聚合与落盘。
- `src/utils/adb/adb_utils.py`：ADB 方法封装。

## 4. 等级策略（当前生效）

- 默认未标记：`L1`
- `@pytest.mark.L2`：扩展用例
- `L3`：占位用例，当前跳过

版本判定基于 `ro.build.display.id`：

- 以 `)` 结尾：周版本 -> 执行 `L1 + L2`
- 其他：日版本 -> 仅执行 `L1`

## 5. 报告摘要

默认输出：`report/<display.id>/SDD_report.json`

主要字段：

- `AlltestCase`
- `failed`
- `ignore`
- `summary.totalNum / failedCount / ignored / passRate`
