# Hang 关键字速查

## 一级总检索串

```text
hang_detect|watchdog|D state|Uninterruptible|Thread info|__mutex_lock|ww_mutex_lock|rwsem|futex|do_translation_fault|folio_wait_bit_common|kswapd|ion|slab|blockio|timeout|binder|system_server
```

## 按分支检索

### 锁等待
```text
__mutex_lock|ww_mutex_lock|rwsem_down_*|futex|deadlock|owner
```

### 内存/缺页
```text
do_translation_fault|folio_wait_bit_common|kswapd|ion|slab|low|min
```

### I-O/文件系统
```text
blockio|wl|bio|blk|timeout|ufs|storage
```

### 服务链路
```text
binder|system_server|watchdog|main thread|blocked
```

## 日志示例与解读

### 1) D 状态线程
```text
init            D
```
解读: 线程处于不可中断睡眠，优先沿调用栈找等待点与 owner。

### 2) 锁等待
```text
mtk_drm_shutdown -> ww_mutex_lock
```
解读: 关机流程锁等待，优先转 DRM 模块确认锁持有关系。

### 3) cgroup 锁阻塞
```text
cgroup_file_write -> __mutex_lock
```
解读: 典型互斥锁阻塞，需要继续追 owner 线程。

### 4) 缺页等待
```text
do_translation_fault -> folio_wait_bit_common
```
解读: 可能是缺页或内存压力触发，结合 kswapd/内存指标判断。
