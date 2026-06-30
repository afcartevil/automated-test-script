# 自定义 Marker 说明

## 1. 设备能力 Marker（来自 `marker_check.py`）

以下 marker 在收集阶段执行，条件不满足会自动 `skip`：

- `require_android_version_min(version)`
- `require_ram_min(size)`
- `require_build_brand(brand)`
- `require_fps(fps)`
- `require_tOS_version_min(version)`
- `require_go_device`
- `require_non_go_device`
- `require_slim_device`
- `require_non_slim_device`
- `require_non_cuttlefish`
- `require_soc_paltform(soc_paltform)`
- `require_kernel_version_min(version)`
- `require_kernel_version_in(versions)`
- `require_features(features)`
- `require_soc_model_min(soc_model)`
- `require_spd_feature_support(feature_codes)`
- `require_packages(packages)`

### 1.1 `require_non_cuttlefish`（CuttleFish 虚拟机）

**含义**：被此 marker 标记的用例**不会**在 MTK CuttleFish 类虚拟设备上执行；在收集阶段若判定为 CuttleFish，则自动 `skip`。未标记的用例不受影响。

**典型场景**：部分用例在虚拟机上会直接报错（硬件/驱动差异等），只需给这些用例加 marker，其余用例不必标记。

**判定逻辑**（实现于 `src/utils/adb/adb_utils.py` 的 `is_cuttlefish_device`，并写入 `get_device_info` 的 `is_cuttlefish` 字段）：

- `ro.product.vendor.model`：参考串 `MTK arm64 Cuttlestone 64-bit only` 须**包含于**设备返回值中（兼容前后缀等变体）。
- `ro.product.device`：须**等于** `cs_arm64_only`。
- 上述两条**同时满足**才视为 CuttleFish。

**用法示例**（单条用例）：

```python
import pytest

@pytest.mark.require_non_cuttlefish
def test_not_on_cuttlefish():
    # 在 CuttleFish 上会被 skip，在其它设备上正常执行
    assert True
```

**类级标记**（同模块下多条用例均需在非 CuttleFish 上跑时）：

```python
import pytest

@pytest.mark.require_non_cuttlefish
class TestHardwareOnly:
    def test_a(self):
        assert True

    def test_b(self):
        assert True
```

与其它设备 marker 一样，需能正确采集设备信息（例如通过 `--device-serial` 指定目标机）。

## 2. 用例等级 Marker（来自 `test_level.py`）

- `L2`：扩展用例
- `L3`：占位用例（当前跳过）

默认无等级 marker 即视为 `L1`。

## 3. 等级执行策略

- 周版本（`display.id` 以 `)` 结尾）：执行 `L1 + L2`，跳过 `L3`
- 日版本：执行 `L1`，跳过 `L2 + L3`

## 4. 最小示例

```python
import pytest

@pytest.mark.L2
@pytest.mark.require_android_version_min(14)
@pytest.mark.require_ram_min(6)
@pytest.mark.require_non_cuttlefish
def test_sample():
    assert True
```

更多最小用例见：`doc/minimal-cases/case-marker-minimal.md`（非 `.py` 文件）。
