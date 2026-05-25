# Bootup Issue 关键字速查

## 一级总检索串

```text
BOOTPROF|pl_lk|kernel|zygote|system_server|BOOT_Animation:END|check_low_battery|vbat|shutdown,thermal|fs_mgr_mount_all returned unexpected error|dm-verity device corrupted|androidboot.bootreason=reboot_longkey|Kernel panic|watchdog
```

## 分阶段关键词

### 上电前期 / 电源路径

```text
PONSTS|POFFSTS|PG_SDN_STS|OC_SDN_STS|power not good|check_low_battery|vbat
```

### LK(ABL) / 引导链

```text
pl_lk|lk|boot|vbmeta|metadata|avb|verified boot
```

### Kernel / 驱动与挂载

```text
Kernel panic|watchdog|probe timeout|mount|dm-verity|pstore|last_kmsg
```

### init-Framework

```text
Starting service 'zygote'|system_server|InitFatalReboot|Failed to initialize property area
```

### Recovery 分支

```text
recovery|fastboot|slot|A/B|userdata|dynamic partition
```

## 高频场景检索模板

1. 低电问题  
`check_low_battery|vbat`

2. 温度关机  
`shutdown,thermal|HandlePowerctlMessage`

3. 挂载失败  
`fs_mgr_mount_all returned unexpected error`

4. 分区校验失败  
`dm-verity device corrupted`

5. 按键误触发重启  
`androidboot.bootreason=reboot_longkey`
