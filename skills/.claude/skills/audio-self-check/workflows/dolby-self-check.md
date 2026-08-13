# Dolby 音效自检

## 必需输入

- `代码基础路径`
- `项目名`
- `升级前音效代码路径`

## 前提条件（宏控门禁）

在执行杜比检查前，必须先读取 `ProjectConfig.mk` 宏控：

1. 检查 `ProjectConfig.mk` 路径：
   - 优先：`./<代码基础路径>/vendor/vendor/transsion/projects/<项目名>/ProjectConfig.mk`
   - 备选：`./<代码基础路径>/vendor/transsion/projects/<项目名>/ProjectConfig.mk`
2. 若两条路径都不存在，输出：`路径不存在`，并停止本 workflow。
3. 读取以下宏控并按规则门禁：
   - 当 `TRAN_AUDIO_DOLBY_SUPPORT=yes` 时：执行杜比音效检查，不执行 DTS 音效检查（本 workflow 继续执行）。
   - 当 `TRAN_DTS_SUPPORT=yes` 时：执行 DTS 音效检查，不执行杜比音效检查（本 workflow 直接停止）。
   - 其他情况：输出 `TRAN_AUDIO_DOLBY_SUPPORT未开启，跳过杜比音效检查`，并停止本 workflow。

## 执行步骤

1. 检查 `DolbyDeviceConverter.h`：
   - 优先：`<代码基础路径>/vendor/vendor/mediatek/proprietary/external/audio_utils/common_utils/dolby/ds/include/DolbyDeviceConverter.h`
   - 备选：`<代码基础路径>/vendor/mediatek/proprietary/external/audio_utils/common_utils/dolby/ds/include/DolbyDeviceConverter.h`
2. 若两个路径都不存在，输出：`DolbyDeviceConverter.h不存在`，停止本 workflow。
3. 扫描 Android 15 参考文件中 `fromSystemDevice` 定义。
4. 对比以下项：`speaker`、`headphone`、`bluetooth`、`usb`、`wired_passthrough`、`wireless_passthrough`。
5. 输出：
   - 一致：`升级前后dolby音效通道配置一致`
   - 不一致：`升级前后dolby音效通道配置不一致`

## 处理规则

- 本 workflow 属于“仅对比”，禁止直接修改 `DolbyDeviceConverter.h`。
