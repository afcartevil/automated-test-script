# KE 关键字速查

## 一级总检索串

```text
Exception Class|Exception Type|CRDISPATCH_KEY|Kernel panic - not syncing|BUG|Oops|ATF crash|Unhandled Exception in EL3|assert|hang_detect|watchdog|HWT|HWR|OCP reboot|PMIC_Shutdown|OC_SDN_STS|PG_SDN_STS|POFFSTS|PONSTS|SYS_REBOOT_REASON
```

## 按分支检索

### KE-Oops/Panic
```text
Kernel panic - not syncing|BUG|Oops|Call trace|backtrace|pc|lr|kernel offset
```

### ATF_CRASH
```text
ATF crash|Unhandled Exception in EL3|PANIC in|assert|bl31
```

## 示例与解读

### 1) ATF exception
```text
Unhandled Exception in EL3
```
解读: 归到 ATF exception 分支，若有 `SYS_TFA_BL31_RAMDUMP` 优先转 MTK。

### 2) Kernel panic
```text
Kernel panic - not syncing: Fatal exception
```
解读: 归到 KE-Panic 分支，继续做 backtrace 与符号映射。

