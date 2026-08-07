## Modem Patch Tool In EA

该目录是 `EasyAdapter` 内维护的 `Modem Patch Tool` 仓内版本。

### 目录定位
- 工具根目录：`tools/modem-patch-tool`
- `EA` 的 `Modem基线` 页面与后端默认调用这里的脚本和配置
- 不再依赖研发个人机器上的外部 `D:\Software\Modem Patch Tool\...` 路径

### 使用约定
- 默认配置来源：`config/baseline_upgrade.json`
- 合入入口：目标 modem 仓内 `tools/md_merge.sh`（工具只做填参 + 冲突非交互化 + `--apm-continue`）
- 启动脚本：
  - `debug_stop_after_merge.py`
  - `debug_continue_after_merge.py`
- 运行数据、日志、任务记录不写回本目录，而是由 `tahp-console` 服务端写入自己的数据目录

### 维护约束
- 该目录作为 EA 内集成版本，后续对 Modem Patch Tool 的修改应优先在这里进行
- 不提交本机缓存、运行历史、`node_modules`、`__pycache__`、`.env` 等运行态文件
