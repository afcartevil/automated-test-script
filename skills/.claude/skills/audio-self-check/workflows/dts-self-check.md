# DTS 音效自检

## 必需输入

- `代码基础路径`
- `项目名`
- `升级前音效代码路径`（用于升级前后对比）

## 前提条件（宏控门禁）

在执行 DTS 检查前，必须先读取 `ProjectConfig.mk` 宏控：

1. 检查 `ProjectConfig.mk` 路径：
   - 优先：`./<代码基础路径>/vendor/vendor/transsion/projects/<项目名>/ProjectConfig.mk`
   - 备选：`./<代码基础路径>/vendor/transsion/projects/<项目名>/ProjectConfig.mk`
2. 若两条路径都不存在，输出：`路径不存在`，并停止本 workflow。
3. 读取以下宏控并按规则门禁：
   - 当 `TRAN_AUDIO_DOLBY_SUPPORT=yes` 时：执行杜比音效检查，不执行 DTS 音效检查（本 workflow 直接停止）。
   - 当 `TRAN_DTS_SUPPORT=yes` 时：执行 DTS 音效检查，不执行杜比音效检查（本 workflow 继续执行）。
   - 其他情况：输出 `TRAN_DTS_SUPPORT未开启，跳过DTS音效检查`，并停止本 workflow。

## 2.1 submix 通道检查

1. 检查 `TranThread.cpp`：
   - 优先：`<代码基础路径>/system/vendor/transsion/system_modules/audio/frameworks/av/servics/audioflinger/TranThread.cpp`
   - 备选：`<代码基础路径>/vendor/transsion/system_modules/audio/frameworks/av/servics/audioflinger/TranThread.cpp`
2. 若文件不存在，输出：`文件不存在`，并停止本 workflow 的后续步骤。
3. 仅检查 `DEVICE_OUT_ALL_AVOID_DTSAUDIO` 定义：
   - 不包含 `AUDIO_DEVICE_OUT_REMOTE_SUBMIX`：`已去除submix通道支持`
   - 包含 `AUDIO_DEVICE_OUT_REMOTE_SUBMIX`：`当前未去除submix通道支持`
4. 与 `升级前音效代码路径` 对应 `TranThread.cpp` 中同定义做对比：
   - 一致：`升级前后DTS音效通道配置一致`
   - 不一致：`升级前后DTS音效通道配置不一致`

## 2.2 DTS 参数路径检查

1. 计算 `dts_project`：`项目名` 在 `_` 前的前缀。
2. 检查 `customer.cfg`：
   - 优先：`<代码基础路径>/vendor/transsion/vendor_modules/common/audiodts/tuning/<dts_project>/customer.cfg`
   - 备选：`<代码基础路径>/vendor/vendor/transsion/vendor_modules/common/audiodts/tuning/<dts_project>/customer.cfg`
3. 扫描是否存在 `tuningPath=/odm/etc/asset/audio/dts`：
   - 存在：`dts音效参数加载路径检查通过`
   - 不存在：`dts音效参数加载路径有误，请检查`
4. 若不存在，允许在文件末尾追加：
   - `tuningPath=/odm/etc/asset/audio/dts`

## 处理规则

- 2.1 中路径不存在时，必须停止 2.1 分支后续判定，不得臆造“是否去除 submix”结论。
- 2.2 仅允许追加 `tuningPath` 这一项，禁止改动其他配置行。
