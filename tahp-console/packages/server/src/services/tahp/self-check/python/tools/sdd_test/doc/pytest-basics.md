# pytest 基础知识

本文件仅保留本项目高频使用的 pytest 知识点，详细语法请参考官方文档。

## 1. fixture

- `@pytest.fixture(scope="session")`：会话级共享，适合设备信息、报告器等。
- fixture 可依赖 fixture，例如 `phone_info(device_serial)`。
- `yield` 前为 setup，后为 teardown。

## 2. 常用 marker

- `@pytest.mark.skip(reason="...")`：无条件跳过。
- `@pytest.mark.skipif(condition, reason="...")`：条件跳过。
- `@pytest.mark.xfail(reason="...")`：预期失败。

本框架业务 marker 见：`custom-markers.md`。

## 3. 常用命令

```bash
# 运行目录
pytest src/

# 运行单用例
pytest src/test_case/baseline/config/test_channel.py::test_xxx

# 查看收集结果（不执行）
pytest --collect-only src/

# 按名称过滤
pytest -k "channel and not uninstall" src/

# 按 marker 过滤
pytest -m "L2" src/

# 显示跳过原因
pytest -rs -vv src/
```

## 4. 常用调试参数

- `-s`：显示 print 输出。
- `--tb=line|short|no|native`：控制异常栈显示。
- `--maxfail=1`：首个失败后停止。

## 5. 配置入口

- 全局配置：`pytest.ini`
- 全局插件入口：`src/conftest.py`
