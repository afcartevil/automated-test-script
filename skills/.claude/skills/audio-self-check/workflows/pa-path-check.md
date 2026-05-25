# PA 参数路径检查

## 必需输入

- `代码基础路径`
- `项目名`

## 5.1 PA 宏控配置检查

1. 检查 `ProjectConfig.mk`：
   - 优先：`<代码基础路径>/vendor/vendor/transsion/projects/<项目名>/ProjectConfig.mk`
   - 备选：`<代码基础路径>/vendor/transsion/projects/<项目名>/ProjectConfig.mk`
2. 两个路径都不存在时，输出：`路径不存在`，并停止本 workflow。
3. 扫描宏控：
   - `TRAN_AUDIO_FS1589N_SUPPORT`
   - `TRAN_AUDIO_FS1599N_SUPPORT`
   - `TRAN_AUDIO_OCA72XXX_SUPPORT`
   - `TRAN_AUDIO_AW87XXX_SUPPORT`
4. 计算 `pa_param_dir`：
   - `TRAN_AUDIO_FS1589N_SUPPORT=yes` -> `fs1589n`
   - `TRAN_AUDIO_FS1599N_SUPPORT=yes` -> `fs1599n`
   - `TRAN_AUDIO_OCA72XXX_SUPPORT=yes` -> `oca72xxx`
   - `TRAN_AUDIO_AW87XXX_SUPPORT=yes` -> `aw87xxx`

## 5.2 aurisys_config 文件查找

查找以 `aurisys_config` 为前缀的 xml：

- `<代码基础路径>/vendor/vendor/transsion/projects/<项目名>/audio/<pa_param_dir>`
- `<代码基础路径>/vendor/transsion/projects/<项目名>/audio/<pa_param_dir>`

## 5.3 参数路径检查与修改

平台参数路径：

- 扫描 `mtk_bessound`、`mtk_speech_enh`、`aurisys_demo`。
- 若 `param_path="/vendor/etc/audio_param"`，改为 `/odm/etc/vconfig/audio/audio_param`。

PA 参数路径：

- `pa_param_dir` 为 `fs1589n` 或 `fs1599n`：
  - 扫描 `fsm_audio` 或 `smartpa_fsmsdg`，将对应 `param_path` 改为 `/odm/etc/vconfig/audio/pa_param`
- `pa_param_dir=oca72xxx`：
  - 扫描 `ocs_di`，将对应 `param_path` 改为 `/odm/etc/vconfig/audio/pa_param`
- `pa_param_dir=aw87xxx`：
  - 扫描 `smartpa_aw88xxx`，将对应 `param_path` 改为 `/odm/etc/vconfig/audio/pa_param`

## 处理规则

- 仅允许修改本 workflow 明确指定的 `param_path`，禁止修改其他内容。
