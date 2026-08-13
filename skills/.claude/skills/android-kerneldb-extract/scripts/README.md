# android-kerneldb-extract 脚本说明

## `kerneldb_extract_all.sh`

- **环境**：Linux（与 `KSST64`、`aee_extract` 二进制一致）。
- **用法**：编辑脚本内 `SKILL_ROOT` 为本 skill 根目录的绝对路径后执行：

  ```bash
  bash kerneldb_extract_all.sh /path/to/LOG_ROOT
  ```

- **行为**：在 `LOG_ROOT` 下递归查找 `*.dbg`，对每个文件在其所在目录执行 `aee_extract`，再对该目录下每个 `*.dbg.DEC` 目录执行 `printf '\nq\n' | KSST64 ./<dir>/`。

## KSST64 不响应管道时

若仍卡在交互提示，说明程序可能绑定 `/dev/tty`。可改用（在 `.dbg` 所在目录）：

```bash
{ sleep 1; printf '\n'; sleep 1; printf 'q\n'; } | script -qfec "./SpOfflineDebugSuite/linux/KSST64 ./xxx.dbg.DEC/" /dev/null
```

将 `SpOfflineDebugSuite/linux/KSST64` 换为 `$SKILL_ROOT/tools/SpOfflineDebugSuite/linux/KSST64` 的绝对路径。
