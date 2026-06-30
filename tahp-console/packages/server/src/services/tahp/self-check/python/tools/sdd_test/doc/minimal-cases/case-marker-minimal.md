# 最小用例：Marker

## 1. 等级 marker

```python
import pytest

def test_l1_default():
    # 未标记即 L1
    assert True

@pytest.mark.L2
def test_l2_case():
    assert True

@pytest.mark.L3
def test_l3_placeholder():
    assert True
```

## 2. 设备能力 marker 最小示例

```python
import pytest

@pytest.mark.require_android_version_min(14)
def test_android_version():
    assert True

@pytest.mark.require_ram_min(6)
def test_ram():
    assert True

@pytest.mark.require_build_brand("MTK")
def test_build_brand():
    assert True

@pytest.mark.require_fps(90)
def test_fps():
    assert True

@pytest.mark.require_tOS_version_min("V14.0")
def test_tos():
    assert True
```

```python
import pytest

@pytest.mark.require_go_device
def test_go_only():
    assert True

@pytest.mark.require_non_go_device
def test_non_go_only():
    assert True

@pytest.mark.require_slim_device
def test_slim_only():
    assert True

@pytest.mark.require_non_slim_device
def test_non_slim_only():
    assert True

@pytest.mark.require_non_cuttlefish
def test_skip_on_cuttlefish():
    # 在 CuttleFish 虚拟机上收集阶段 skip，其它设备正常执行
    assert True
```

```python
import pytest

@pytest.mark.require_soc_paltform(["ums9230", "mt6769"])
def test_soc_platform():
    assert True

@pytest.mark.require_kernel_version_min("5.10")
def test_kernel_min():
    assert True

@pytest.mark.require_kernel_version_in(["4.19", "5.10"])
def test_kernel_in():
    assert True

@pytest.mark.require_features(["android.hardware.camera.flash"])
def test_features():
    assert True

@pytest.mark.require_soc_model_min("G99")
def test_soc_model():
    assert True

@pytest.mark.require_packages(["com.android.settings"])
def test_packages():
    assert True
```

## 3. 组合示例  组合是 and 关系

```python
import pytest

@pytest.mark.L2
@pytest.mark.require_android_version_min(14)
@pytest.mark.require_ram_min(6)
def test_combo():
    assert True
```
