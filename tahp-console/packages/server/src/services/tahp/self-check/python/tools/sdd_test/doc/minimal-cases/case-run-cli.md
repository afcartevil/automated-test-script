# 最小用例：CLI 运行

## 1. 运行全部用例

```bash
python si_run.py --serial <设备SN>
```

## 2. 仅跑 baseline

```bash
python si_run.py --serial <设备SN> --test-type baseline
```

## 3. 仅跑 performance

```bash
python si_run.py --serial <设备SN> --test-type performance
```

## 4. 运行单文件

```bash
python si_run.py --serial <设备SN> --testcase src/test_case/baseline/config/test_channel.py
```

## 5. 附加重跑参数

```bash
python si_run.py --serial <设备SN> --reruns 2 --reruns-delay 2
```

## 6. 直接 pytest 调试

```bash
pytest -rs -vv src/test_case/baseline/config/test_channel.py --device-serial <设备SN>
```
