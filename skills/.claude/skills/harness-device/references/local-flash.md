# 本地刷机参考

当用户要刷本地 ROM、询问刷机参数含义，或者要解释 Agent 的刷机规则来源时，读这个参考。

## CLI 契约

主命令：`harness device flash`

参数定义在 `cli/main.py`，由 `cli/device.py` 分发：

- `--sn` 必填，对应 `sn`。
- `--rom-path` 必填，对应 `rom_path`。
- `--backend` 取值 `auto`、`device_update`、`fastboot`，默认 `auto`。
- `--stage` 是可选的 `device_update` stage label。
- `--skip-partition` 可重复传入，变成 `skip_partitions: list[str]`；它会被 `device_update` 忽略。
- `--require-oem-unlock` 是 fastboot 的前置条件覆盖；它会被 `device_update` 忽略。
- `--acknowledge-base-layout` 只在顶层 BASE 刷机且同时存在市场 overlay 子目录时用于确认。
- `--variant` 取值 `user`、`userdebug`、`eng`。
- `--dry-run` 开启 runner 调试模式，预览时应优先使用。
- `--timeout` 是 action 超时时间，单位秒。

## 门面规则

`mcp/tools/flash.py` 是 CLI 共用的 legacy 门面。把它当成命令到 runner 的映射和结果结构来源：

- `auto` -> runner action `flash.local`
- `device_update` -> runner action `flash.device_update`
- `fastboot` -> runner action `flash.fastboot`
- `variant` 会根据显式输入或 `rom_path` 里的 token 归一化为 `user`、`userdebug`、`eng`。
- `user` variant 会输出刷机后的提示，因为 OOBE 和 USB 调试通常需要手工处理，后续 adb 自动化才能继续。
- 返回字段包含 `status`、`action_id`、`backend`、`dry_run`、`variant`、`post_flash_notes`、`output`、`duration_sec` 和 `artifacts`。

## 后端识别

`runners/local_flash/adapter.py` 是本地后端识别和安全检查的来源：

- 含 scatter XML 的文件或目录会选择 `device_update`。
- 含 `android-info.txt`、`flash_all.bat`、`flash_all.sh`，或含 `boot.img`、`super.img`、`vendor.img`、`userdata.img`、`cache.img` 等常见镜像名的目录会选择 `fastboot`。
- 未知布局会直接返回结构化错误，不会去试任意 shell 命令。
- 内置默认路径是 `runners/local_flash/device_update/device_update.exe` 和 `runners/local_flash/device_update/tools/fastboot/fastboot.exe`。
- 如果一个 ROM 同时有顶层 scatter 和带自己 scatter 的市场子目录，runner 会拒绝这个有歧义的 BASE 布局，除非 `--stage <market>` 匹配到检测到的市场，或者用户显式设置 `--acknowledge-base-layout`。

## 操作建议

- 先跑 dry run：`harness device flash --sn <sn> --rom-path <rom> --dry-run`。
- 默认优先 `--backend auto`；只有布局或用户要求明确时，才强制 `device_update` 或 `fastboot`。
- 处理市场 overlay 时，优先用 `--rom-path <rom>/<market>` 或 `--stage <market>`，不要优先用 `--acknowledge-base-layout`。
- 只有用户确认 BASE 是想刷的目标时，才用 `--acknowledge-base-layout`。
- 当 CLI 已经覆盖该操作时，不要自己发明原始 `adb`、`fastboot`、SP Flash Tool 或 shell 命令。
- 反馈里不要贴完整设备序列号或私有构建路径，做摘要即可。

## 可执行测试参考

- `tests/test_flash_local_apply.py` 覆盖门面、CLI/MCP 返回结构、后端 action 映射、variant 提示、dry-run 行为和边界情况。
- `tests/test_local_flash_runner.py` 覆盖后端识别、内置工具默认值、分层布局拒绝、预检和 runner 行为。
