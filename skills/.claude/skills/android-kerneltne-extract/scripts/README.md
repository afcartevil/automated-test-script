# android-kerneltne-extract scripts

## kerneltne_extract_all.sh

Linux 批处理脚本，执行以下动作：

1. 在日志根目录递归查找 `*.tne`
2. 按文件名前缀分类：
   - `0xffffff0c_*.tne` -> HANG
   - `0xffffff0d_*.tne` -> HWT
   - `0xffffff04_*.tne` -> KE
   - `0xffffff15_*.tne` -> OCP_REBOOT
3. 执行 `decompress <xxx.tne>`（若系统无 `decompress` 命令，则回退到 skill 内 `tools/decompress/linux/tne_decompress`）
4. 捕获解压后新增目录，并对每个目录执行：
   - `printf '\nq\n' | KSST64 path/dir_name/`

### Usage

```bash
bash kerneltne_extract_all.sh /path/to/LOG_ROOT
```

## 注意

- `KSST64` 固定使用 skill 内工具：`tools/SpOfflineDebugSuite/linux/KSST64`。
- 如果你希望严格只执行命令字面值 `decompress **.tne`，请确保 `decompress` 已在 `PATH` 中，并修改脚本去掉 fallback 逻辑。
