# 性能测试文件分类说明

本目录包含性能测试相关的测试用例文件，按照不同的适配条件进行分类，便于管理和执行。

## 文件分类说明

### 1. 适配条件为All的测试文件
**文件**: `test_adaptation_conditions_all.py`

包含适用于所有设备和平台的通用性能测试用例，主要特点：
- 不限制特定Android版本
- 不限制特定芯片平台
- 适用于大多数设备配置

**包含的测试用例**:
- MTK kernel版本对应sbe版本校验
- 异常APP退后台30分钟查杀方案
- 近期任务前4个提升adj增强保活
- PowerHal加密校验
- powerhal云控检测
- 首次开机后dexopt
- TOPAPP cgroup uclamp设置校验
- 滑动帧间距优化
- 无障碍模式优化
- launcher/systemui/systemGC绑小核优化
- vmheap参数确认
- TranFling动效调整

### 2. 按Android大版本分类的测试文件
**文件**: `test_adaptation_platform_classified.py`

包含按Android版本(T、U、V、W等)分类的测试用例，主要特点：
- 针对特定Android版本的性能特性
- 包含版本间的兼容性检查
- 支持不同版本的功能差异

**包含的测试用例**:
- TranCpuBooster功能校验
- madvise属性配置检测
- PM版本功能验证(PM4.1与PM4.0互斥)
- 超级触控/AppTurbo控制
- 系统冻结1.0功能
- EsportsPro-游戏温控引擎
- SF binder优先级提升
- GPU completion binder调用
- Launcher异步动效
- fastkill+循环监听查杀
- 内存融合功能
- appcompact功能
- 应用主题资源缓存
- camera退出优化方案
- 滑动插帧功能
- dexopt专项优化
- 温升瞬态交互体验优化
- IO预读功能
- 应用预加载方案
- 关闭usap预加载

### 3. 按芯片平台分类的测试文件
**文件**: `test_adaptation_chip_platform_CPU.py`

包含针对特定芯片平台(G99、D8200等)的测试用例，主要特点：
- 基于芯片性能等级进行测试
- 支持不同芯片平台的功能差异
- 包含芯片优先级判断逻辑

**包含的测试用例**:
- dex2oat绑小核方案(G99及以上芯片)
- 高性能模式检测(D8200及以上芯片)
- PQE1.0功能检测(MTK G70+或展锐T606+)
- launcher新版精简动效(按芯片等级分级)

### 4. 有依赖feature的测试文件
**文件**: `test_adaptation_feature.py`

包含需要特定功能或包依赖的测试用例，主要特点：
- 依赖特定系统包(如com.transsion.trancare)
- 需要特定功能支持
- 包含复杂的条件判断逻辑

**包含的测试用例**:
- Griffin 4.0功能校验
- Griffin 4.1功能校验(需要芯片平台≥G99且RAM≥8GB)

## 测试标记说明

测试用例使用以下pytest标记进行条件筛选：

- `@pytest.mark.require_build_brand("MTK")` - 要求MTK平台
- `@pytest.mark.require_android_version_min(AndroidVersion.V)` - 要求Android V及以上版本
- `@pytest.mark.require_kernel_version_min("5.10")` - 要求内核版本5.10及以上
- `@pytest.mark.require_soc_model_min("G99")` - 要求芯片型号G99及以上
- `@pytest.mark.require_packages(["com.transsion.trancare"])` - 要求安装特定包
- `@pytest.mark.require_ram_min(4)` - 要求RAM至少4GB
- `@pytest.mark.require_non_go_device()` - 要求非Go设备

## 使用说明

1. **选择性执行**: 可以根据设备特性选择执行特定分类的测试文件
2. **条件过滤**: 使用pytest标记自动过滤不适用于当前设备的测试用例
3. **版本兼容**: 测试用例会自动检测Android版本差异并执行相应逻辑
4. **芯片适配**: 根据芯片平台优先级自动适配不同功能等级

## 注意事项

- 测试用例会根据实际设备条件自动跳过不适用的情况
- 部分测试用例包含警告机制，不会强制失败
- 建议在对应Android版本的设备上执行相应测试
- 芯片平台相关的测试需要设备支持相应的芯片型号
