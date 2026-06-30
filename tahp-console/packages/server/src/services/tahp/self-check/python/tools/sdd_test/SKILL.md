---
name: spd-table-to-pytest-cases
description: 将 SPD 功能清单表转换为本仓库的 pytest Android 设备侧自动化测试用例。用户提供包含分级、Feature / 功能点、业务领域、适配条件/前置条件、SPD支持的特性编码、宏控开关、测试步骤、预期结果、平台适配等列的表格，或要求生成 SDD/SPD/ADB/pytest 自动化用例时使用。
---

# SPD 表格转 Pytest 用例

## 目标

将 SPD 功能清单中的每一行转换为本仓库可执行的 pytest 用例。生成 Python 测试代码，本项目是 `pytest + ADB + marker + JSON report` 框架。

## 开始前先看

生成或修改用例前，如果上下文不充分，先查看这些本地文件：

- `src/conftest.py`：fixture 与 pytest 收集阶段 hook
- `src/conftests/marker_check.py`：当前支持的设备能力 marker
- `src/conftests/device.py`：设备信息字段与 SPD 特性表加载逻辑
- `src/utils/adb/adb_utils.py`：ADB 工具方法
- `doc/custom-markers.md` 和 `doc/adb-api.md`：已文档化的框架 API

如果表格行无法用现有能力表达，先在 `src/utils/` 下补一个小而可复用的 helper，并更新对应文档，再生成测试用例。

## 输入表格列

期望输入列：

```text
分级 | Feature / 功能点 | 业务领域 | 功能简介 | 适配条件/前置条件 | SPD支持的特性编码 | 方案链接 | 宏控开关 | 测试步骤 | 预期结果 | 平台适配 | 备注
```

其中 `Feature / 功能点`、`功能简介`、`测试步骤`、`预期结果` 是核心测试意图。`分级`、`适配条件/前置条件`、`SPD支持的特性编码`、`平台适配` 应尽量转换为收集阶段的 skip 条件，也就是 pytest marker。

## 输出位置

测试文件放在 `src/test_case/` 下，按 `业务领域` 路由到最贴近业务含义的目录。目录名一律小写，优先使用稳定英文或通用拼音；避免中文、临时缩写和易变命名。已有目录能表达业务含义时优先复用，确需新增时按下表扩展。

| 业务领域       | 输出目录                     |
| -------------- | ---------------------------- |
| 基线           | `baseline/`                |
| 性能           | `performance/`             |
| 底软-Charger   | `disoft/charger/`          |
| 底软-Sensor    | `disoft/sensor/`           |
| 底软-内核-内存 | `disoft/kernel_mem/`       |
| 底软-内核-调度 | `disoft/kernel_sched/`     |
| 底软-通信      | `disoft/communication/`    |
| 底软-TP        | `disoft/tp/`               |
| 底软-LCM       | `disoft/lcm/`              |
| 底软-小系统    | `disoft/subsys/`           |
| 底软-内核-安全 | `disoft/kernel_security/`  |
| 底软-FP        | `disoft/fp/`               |
| 底软-马达      | `disoft/motor/`            |
| 底软-器件框架  | `disoft/device_framework/` |
| 底软-video     | `disoft/video/`            |
| 底软-audio     | `disoft/audio/`            |
| 底软-功耗      | `disoft/power/`            |
| 底软-温升      | `disoft/therm/`            |
| GMS认证        | `gms/`                     |
| 三方集成       | `third_party/`             |
| 应用集成       | `application/`             |
| 稳定性         | `stability/`               |

已存在且可复用的历史目录：

- `src/test_case/performance/info/`：底软集成、性能、平台适配、SPD 特性能力验证
- `src/test_case/baseline/config/`：配置、资源、开关、预装、区域化配置
- `src/test_case/baseline/info/`：设备信息、版本、属性一致性

如果表格业务领域无法命中映射表或历史目录，新增 `src/test_case/<mapped_domain>/` 下的最小必要子目录；内核相关优先放在 `disoft/kernel_*` 或 `disoft/kernel/<subdomain>/` 这类稳定目录下。

文件名使用小写 ASCII，格式为 `test_<domain>_<feature>.py`。如果中文无法稳定翻译，优先使用 SPD 特性编码；没有编码时使用稳定短名称，例如 `test_spd_generated_cases.py`。

## 列映射规则

- `分级`：`L1` 不加等级 marker；`L2` 加 `@pytest.mark.L2`；`L3` 加 `@pytest.mark.L3`。
- `Feature / 功能点`：用于生成函数名、docstring 和失败提示。
- `业务领域`：用于选择输出目录，也可用于文件分组。
- `功能简介`：写入 docstring，作为用例背景。
- `适配条件/前置条件`：优先映射为已有 marker；无对应 marker 时才在用例内 `pytest.skip()`。
- `SPD支持的特性编码`：生成 `@pytest.mark.require_spd_feature_support(["CODE"])`；多个编码按英文逗号、中文逗号、分号、斜杠或换行拆分。
- `宏控开关`：额外信息，写入docstring，作为用例背景。
- `测试步骤`：生成操作逻辑。遇到 `adb命令执行：find ... -name ...` 且预期结果是完整路径时，优先转换为 `is_file_exist()` / `is_dir_exist()` 这类 ADB 基础方法获取 bool，再单独 `assert` 判断 bool；只有无法映射到现有基础方法时，才调用 `adb_shell()` 保存结果并断言。
- `预期结果`：若是文件或目录路径存在性，优先断言基础方法返回的 bool；对于复杂的验证逻辑、编写对应的逻辑代码处理，最后将结果断言。若是逻辑过于复杂、可以在业务逻辑判断末使用pytest.fail() | pytest.warn() | pytest.skip()等方法直接处理。
- `平台适配`：`MTK`、`QCOM`、`UMS`、`SPRD` 映射为 `@pytest.mark.require_build_brand("...")`；原始 SoC 平台值使用 `@pytest.mark.require_soc_paltform([...])`。
- `备注`：只有影响执行行为时才写成注释；否则放入 docstring。
- `方案链接`: 忽略，不要读取链接。

## 框架已支持能力

新增代码前，优先复用这些已有能力：

- Fixture：`device_serial`、`phone_info`、`pms_info`、`execution_environment`、`file_puller`
- 等级 marker：L1 不加 marker，L2/L3 使用 `@pytest.mark.L2`、`@pytest.mark.L3`
- 设备能力 marker：`require_android_version_min`、`require_ram_min`、`require_build_brand`、`require_fps`、`require_tOS_version_min`、`require_go_device`、`require_non_go_device`、`require_slim_device`、`require_non_slim_device`、`require_soc_paltform`、`require_kernel_version_min`、`require_kernel_version_in`、`require_features`、`require_soc_model_min`、`require_spd_feature_support`、`require_packages`
- ADB helper：`getprop`、`adb_shell`、`execute_command`、`is_file_exist`、`is_dir_exist`、`ls_dir`、`adb_cat`、`get_feature`、`is_package_exist`
- SPD 支持性过滤：`require_spd_feature_support` 会读取 SPD 列表，并按当前设备市场判断是否支持

## 生成规则

1. 每条有效表格行生成一个 pytest 函数。
2. 保留原始业务描述，写入函数 docstring。
3. 优先使用收集阶段 marker 跳过不适配设备，少用运行时 `if`。
4. 用例逻辑明确，业务处理和断言要分开，不能将处理逻辑与断言整合为一个方法。
5. 不生成只有 `pass` 的占位测试。
6. 严格一行表格生成一个 pytest 用例，不要自动把一行拆成多个测试；如果一行包含多个独立预期，最多在最终说明中建议用户后续拆解。
7. ADB 类用例必须把执行和断言分开写。简单文件/目录/属性/包/feature 存在性检查，优先使用 `is_file_exist()`、`is_dir_exist()`、`getprop()`、`is_package_exist()`、`get_feature()` 等现有 ADB 基础方法获取结果变量，例如 `is_support = is_file_exist(...)`，然后 `assert is_support`；不要为了这类用例额外封装统一查询和 assert 方法。
8. 断言只关注业务预期是否满足；ADB 命令执行失败、异常或超时不单独作为业务断言，除非用户表格明确要求验证命令执行状态。失败信息应说明业务输出不符合预期，并展示期望值与实际输出，方便排查。
9. 不要在用例文件内生成公用的assert方法，每个用例应该保持独立。

## 用例验证

生成或修改 pytest 用例后，必须先做静态检查，再执行环境与实机验证流程，不允许只做语法检查后结束：

1. 静态检查新增或修改的用例文件：

   - 使用 `ReadLints` 检查最近编辑文件的 lint 问题。
   - 执行 `python -m py_compile <testcase_path>` 做 Python 语法编译检查。
   - 若静态检查失败，先修复问题并重新检查；最终回复需要说明静态检查结果。
2. 检查 ADB 设备连接：

   - 执行 `adb devices`
   - 若没有 `device` 状态的设备，停止实机验证，并在最终回复中明确说明“未检测到可用设备”，同时给出已完成的静态检查结果。
3. 检查 Python/pytest 环境：

   - 执行 `python --version`
   - 执行 `python -c "import pytest; print(pytest.__version__)"`
   - 若环境不可用，停止执行用例，并在最终回复中说明具体失败命令和错误摘要。
4. 执行本次新增或修改的用例文件：

   - 使用实际设备 SN 替换 `<设备SN>`
   - 使用本次生成/修改的测试文件路径替换 `<testcase_path>`
   - 命令格式：`python si_run.py --serial <设备SN> --testcase <testcase_path>`
   - 若用例被收集阶段 marker_checker 跳过，不能视为执行通过；最终回复必须说明 skip 状态、跳过原因、触发的 marker 或依赖字段，并提醒用户按原因处理，例如更换满足条件的设备、补全设备信息字段、确认 SPD 特性清单/市场配置，或调整表格中的适配条件。
5. 验收一致性：

   - 不论用例是否执行成功。对比用户输入表格、生成的用例代码、实机执行结果三者是否一致。
   - 若不一致，修改用例后重新执行验证。
   - 若执行结果为 skipped，需要判断跳过原因是否与表格的分级、平台适配、适配条件、SPD 特性编码一致；一致时在最终回复中说明“用例生成正确但当前设备不适配”，不一致时按问题修正 marker 或用例逻辑后重新执行验证。
   - 最多循环 3 次；仍无法解决时，最终回复必须输出阻塞原因、关键命令输出摘要和建议用户处理的信息。
6. 补完框架能力后，同步更新 `doc/` 下对应文档，并执行针对性语法或 lint 检查。
7. 最终回复必须包含：

   - 生成/修改的用例文件
   - 静态检查结果：lint 与语法编译检查。一行输出
   - ADB 设备检查结果 和 Python/pytest 环境检查结果。一行输出
   - `si_run.py` 执行结果，或未执行原因
   - 若结果为 skipped，输出跳过原因、对应 marker/条件、是否符合输入表格预期，以及建议用户如何处理
   - 当存在符合逻辑的失败用例时，要重点强调用户失败用例可能会阻断版本释放，让用户重点检查。

## 冒烟与补充场景考虑条件

默认先忠实转换表格中的显式用例，不随意扩展额外用例。遇到以下情况时，再把冒烟规则和补充场景纳入生成范围：

- 每个生成用例都必须有明确通过/失败判定标准，不能只描述“检查是否正常”。
- 设备依赖必须显式体现：能用 marker 表达的用 marker，不能表达的在测试内 `pytest.skip()`，并写清跳过原因。
- 用户要求“补充场景”“完整覆盖”“回归用例”时，在表格显式场景之外补充正向、负向、边界和中断恢复场景。
- 正向场景覆盖标准输入、正常流程和预期结果，通常可作为 L1 或主用例。
- 负向场景覆盖无效输入、未授权访问、网络断开/超时、设备资源不足等；若框架无法自动制造条件，只生成可执行的 ADB/属性/文件类检查，或在输出中说明需要人工/环境配合。
- 边界场景覆盖最小值/最大值、空列表/单条/大量数据、首次使用/重复操作；只有表格信息足以形成可执行断言时才生成代码。
- 中断恢复场景覆盖来电/通知打断、前后台切换、横竖屏切换、低电量/充电状态；本框架缺少 UI/事件注入能力时，不强行生成不可执行代码，应提示需要新增框架能力。
- 批量表格转换时，如果没有明确要求扩展覆盖，只在最终说明里提示“可补充的场景类型”，不要自动新增大量非表格用例。

## 常见生成模式

### ADB 路径存在性检查

表格中的测试步骤虽然写成 `adb命令执行：find ... -name ...`，但如果预期结果是一个明确路径，优先生成基础方法获取 bool 的风格，保持和现有用例一致。

```python
# coding=utf-8
import pytest

from src.utils.adb.adb_utils import is_file_exist


@pytest.mark.require_build_brand("MTK")
def test_backlight_led_chip_tran_led_cmd(device_serial):
    """
    背板灯效芯片: 灯效底层驱动能力适配
    测试步骤: adb命令执行 find /sys/devices/platform/odm -name tran_led_cmd
    """
    expected_output = "/sys/devices/platform/odm/odm:tran_led_core/tran_led_cmd"

    is_support = is_file_exist(device_serial, expected_output)
    assert is_support, "背板灯效芯片校验失败"
```

### ADB 命令输出包含期望文本

只有预期结果不是简单路径存在性，或者现有 ADB 基础方法无法表达时，才使用 `adb_shell()` 直接校验命令输出。

```python
# coding=utf-8
import pytest

from src.utils.adb.adb_utils import adb_shell


@pytest.mark.require_build_brand("MTK")
def test_backlight_led_chip_tran_led_cmd(device_serial):
    """
    背板灯效芯片: 灯效底层驱动能力适配
    测试步骤: adb命令执行 find /sys/devices/platform/odm -name tran_led_cmd
    """
    shell_command = "find /sys/devices/platform/odm -name tran_led_cmd"
    expected_output = "/sys/devices/platform/odm/odm:tran_led_core/tran_led_cmd"

    result = adb_shell(device_serial, shell_command, no_retry=True)
    actual_output = result["output"].strip()

    assert expected_output in actual_output, (
        f"背板灯效芯片校验失败: 输出不符合预期; "
        f"expected contains: {expected_output}; actual: {actual_output}"
    )
```

业务断言规则：

- ADB 查询结果只作为业务判断输入，默认不对 `result["success"]`、`exception_type` 或 `exception_msg` 单独断言。
- `expected_output not in actual_output` 时，判定为业务预期未满足，失败信息展示期望内容和实际输出。
- 只有当表格明确要求校验命令是否执行成功、是否超时或是否报错时，才生成对应的执行状态断言。

### 属性或宏控开关检查

```python
from src.utils.adb.adb_utils import getprop


def test_feature_switch(device_serial):
    assert "1" == getprop("ro.example.feature.support", device_serial), "功能宏控开关校验失败"
```

### 带 SPD 特性支持过滤的用例

```python
import pytest


@pytest.mark.require_spd_feature_support(["SPD_CODE"])
def test_spd_feature_case(device_serial):
    ...
```

## 缺少能力时如何补框架

如果表格使用了当前框架不支持、但可复用的动作类型，应新增框架 helper，而不是把复杂逻辑散落到每个测试里：

- ADB shell 查询：扩展 `src/utils/adb/adb_utils.py`；断言仍写在测试用例中，保持执行逻辑可读
- 新设备能力过滤条件：扩展 `src/conftests/marker_check.py`，并加入 `CHECKER_LIST` 和 `DEVICE_MARKERS`
- marker 需要的新设备信息字段：扩展 `src/conftests/device.py` 的 `get_device_info()`
- 新文件格式加载：扩展 `src/utils/fileloader/`
