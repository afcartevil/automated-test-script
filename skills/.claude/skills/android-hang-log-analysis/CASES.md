# Hang 典型案例

## 案例1: 关机流程锁等待

### 现象
关机过程中系统长时间无响应，最终触发 hang 检测。

### 分析过程
1. `SYS_HANG_DETECT_RAW` 发现 `init D`。
2. 调用链出现 `mtk_drm_shutdown -> ww_mutex_lock`。
3. 结合关机场景判定为 DRM 路径锁等待，继续追 owner。

### 结论
初步指向 DRM 模块锁竞争/死锁风险，需要 owner 线程进一步闭环。

## 案例2: cgroup 互斥锁阻塞

### 现象
系统关键线程阻塞，watchdog 报警。

### 分析过程
1. 栈中命中 `cgroup_file_write -> __mutex_lock`。
2. 被阻塞线程长期 D 状态。
3. 继续查找持锁线程，建立阻塞因果链。

### 结论
属于典型互斥锁阻塞，需要模块侧定位持锁路径和释放条件。

## 案例3: 缺页等待引发 Hang

### 现象
系统在高负载后出现卡死并触发 hang。

### 分析过程
1. 栈命中 `do_translation_fault -> folio_wait_bit_common`。
2. 在 `SYS_KERNEL_LOG` 中检查内存水位与回收行为。
3. 发现回收压力高，线程长期不可运行。

### 结论
根因方向为内存压力/缺页等待，需结合内存分配路径继续优化。
