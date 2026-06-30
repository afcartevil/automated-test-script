# 最小用例：框架特性

## 1. fixture 最小用法（设备 SN 与设备信息）

```python
def test_use_device_info(device_serial, phone_info):
    assert device_serial is not None
    assert "ro_build_display_id" in phone_info
```

## 2. 文件导出 fixture（file_puller）

```python
def test_pull_channel_file(file_puller):
    ok = file_puller(file_name="channel_list.xml")
    assert ok
```

## 3. 收集阶段自动跳过示例

```python
import pytest

@pytest.mark.L2
@pytest.mark.require_android_version_min(14)
def test_collect_stage_filtering():
    # 若设备或版本不满足，测试会在收集阶段被 skip
    assert True
```

## 4. 报告输出最小验证

```bash
python si_run.py --serial <设备SN> --testcase src/test_case/baseline/config/test_channel.py
```

检查默认报告路径是否生成：

```text
report/<display.id>/SDD_report.json
```

## 5. 自定义报告路径

```bash
pytest src/test_case/baseline/config/test_channel.py --device-serial <设备SN> --report-path ./report/custom/result.json
```

## 6. 失败重跑能力

```bash
python si_run.py --serial <设备SN> --test-type baseline --reruns 2 --reruns-delay 2
```
