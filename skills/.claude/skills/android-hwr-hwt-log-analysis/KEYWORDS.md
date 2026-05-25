# HWR 关键字速查

## 一级总检索串

```text
HWT|HW reboot|wdt|wdtk|kick|timeout|failed|error|lastpc|systracker|bus timeout|ufs|SYS_LAST_CPU_BUS|SYS_REBOOT_REASON|oops_in_progress
```

## 分支关键词

### 喂狗链路
```text
wdtk|kick|cpu|timeout|watchdog
```

### 总线/存储超时
```text
lastpc|systracker|bus timeout|ufs|mmc|io timeout
```

### 地址映射
```text
oops_in_progress|kernel offset|addr2line|vmlinux
```

## 示例与解读

### 1) HWR 标志
```text
HWT ... -> HW reboot
```
解读: 说明已从超时抓现场阶段升级到硬复位阶段。

### 2) 喂狗缺失
```text
wdtk ... cpu1 timeout
```
解读: CPU1 可能卡死或长期阻塞，优先追 CPU1 相关栈与日志。

### 3) 总线线索
```text
systracker ... addr=0x...
```
解读: 若存在地址，可映射到总线/模块并判断是否访问超时。
