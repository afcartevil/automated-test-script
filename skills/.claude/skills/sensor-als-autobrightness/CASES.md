# 典型案例

## 案例1：自动背光正常现象的log打印

### 现象

光感在首笔数据上报过后，会定时器循环打印实时光感算法值；当光感值 `g_data` 发生剧烈变化时，背光不会立刻变化，而是在上层防抖机制通过后再逐步变暗。

### 分析过程

1. 在 `scp_log_9__2026_0421_161456` 中查看光感首笔数据上报后的实时算法日志，可看到原始通道数据、原始ALS、算法估算值和最终 `g_data`。
2. 继续搜索关键词 `g_data`，确认光感值在运行期间连续变化。
3. 当 `g_data` 剧烈变化为 `0` 时，先观察 `brightness` 是否短时间保持不变。
4. 在防抖机制时间过去后，继续观察 `brightness` 是否开始缓慢降低。
5. 再到 `main_log_1__2026_0421_161456` 中查看 `brightness_val`，确认上层持续下发写背光节点值，屏幕亮度连续变暗。
6. 结合SCP侧 `brightness` 和上层 `brightness_val` 的连续变化，得出自动背光行为正常。

### 根因

该案例不是异常，而是自动背光的正常现象。光感值发生剧烈变化后，上层存在防抖机制，所以背光值不会立即变化，而是延迟后缓慢调整。

### 关键日志

```text
[426850.475](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2676: ch0[0]:30704, ch1[0]:20782, ch2[0]: 6876, ch3[0]:80896
[426850.475](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2723: : unify ori ALS = 80896, G = 20782 G_data_ratio = 20782
[426850.475](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2807: DisplayData Brightness_2:68 R:182,G:182,B182
[426850.475](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2809: unify estimate ALS = 10882, G = 0, noise ALS = 70014, G = 20782
[426850.475](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:10882.000000,g_data = 0,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17

        行  3092: [426849.395](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.774607,g_data = 427,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3101: [426849.455](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.775507,g_data = 427,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3110: [426849.516](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.774760,g_data = 427,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3121: [426849.575](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.774503,g_data = 427,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3130: [426849.635](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.773162,g_data = 426,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3139: [426849.695](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.769858,g_data = 425,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3150: [426849.755](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.761292,g_data = 413,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3159: [426849.815](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.757177,g_data = 402,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3168: [426849.875](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.755167,g_data = 398,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3179: [426849.935](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.753668,g_data = 396,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3188: [426849.995](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.754816,g_data = 399,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3197: [426850.055](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.755599,g_data = 401,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3206: [426850.116](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.755473,g_data = 400,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17

//刚开始背光值brightness不变
        行  3226: [426850.235](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.758034,g_data = 382,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3235: [426850.295](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.758034,g_data = 382,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3246: [426850.355](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.758034,g_data = 382,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3255: [426850.415](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:2.758034,g_data = 382,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3264: [426850.475](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:10882.000000,g_data = 0,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3275: [426850.535](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:10659.000000,g_data = 0,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3284: [426850.595](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:10430.000000,g_data = 0,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3293: [426850.655](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:10294.000000,g_data = 0,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3302: [426850.716](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:10203.000000,g_data = 0,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3313: [426850.775](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:10151.000000,g_data = 0,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17

//防抖机制过了，brightness开始慢慢降低
        行  3840: [426854.075](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:7730.000000,g_data = 0,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3851: [426854.135](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:7725.000000,g_data = 0,brightness:68,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3863: [426854.195](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:8182.000000,g_data = 0,brightness:67,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3872: [426854.255](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:8412.000000,g_data = 0,brightness:67,als_algo_timer_count:0,brightness_st:2,g_lcm_dim_count:17
        行  3882: [426854.316](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:66,als_algo_timer_count:1,brightness_st:0,g_lcm_dim_count:17
        行  3889: [426854.375](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:66,als_algo_timer_count:2,brightness_st:0,g_lcm_dim_count:17
        行  3897: [426854.435](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:65,als_algo_timer_count:3,brightness_st:0,g_lcm_dim_count:17
        行  3902: [426854.495](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:65,als_algo_timer_count:4,brightness_st:0,g_lcm_dim_count:17
        行  3912: [426854.555](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:64,als_algo_timer_count:5,brightness_st:0,g_lcm_dim_count:17
        行  3917: [426854.615](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:64,als_algo_timer_count:6,brightness_st:0,g_lcm_dim_count:17
        行  3925: [426854.675](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:63,als_algo_timer_count:7,brightness_st:0,g_lcm_dim_count:17
        行  3932: [426854.735](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:63,als_algo_timer_count:8,brightness_st:0,g_lcm_dim_count:17
        行  3940: [426854.795](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:62,als_algo_timer_count:9,brightness_st:0,g_lcm_dim_count:17
        行  3945: [426854.855](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:62,als_algo_timer_count:10,brightness_st:0,g_lcm_dim_count:17
        行  3953: [426854.916](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:61,als_algo_timer_count:11,brightness_st:0,g_lcm_dim_count:17
        行  3960: [426854.975](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:61,als_algo_timer_count:12,brightness_st:0,g_lcm_dim_count:17
        行  3968: [426855.035](0)[0] deputy.TRAN_ALS stk3bfx_als_algo 2847: :dim_process cg ratio:0.000000,g_data = 0,brightness:60,als_algo_timer_count:13,brightness_st:0,g_lcm_dim_count:17

        行 45041: 04-22 16:23:36.207050  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.206680) brightness_val(846)
        行 45043: 04-22 16:23:36.224179  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.206228) brightness_val(844)
        行 45045: 04-22 16:23:36.240965  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.205777) brightness_val(842)
        行 45047: 04-22 16:23:36.258235  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.205327) brightness_val(840)
        行 45049: 04-22 16:23:36.273861  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.204878) brightness_val(838)
        行 45051: 04-22 16:23:36.291638  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.204430) brightness_val(837)
        行 45053: 04-22 16:23:36.307859  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.203983) brightness_val(835)
        行 45055: 04-22 16:23:36.323555  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.203538) brightness_val(833)
        行 45057: 04-22 16:23:36.340693  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.203093) brightness_val(831)
        行 45060: 04-22 16:23:36.357534  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.202650) brightness_val(829)
        行 45062: 04-22 16:23:36.374095  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.202207) brightness_val(828)
        行 45064: 04-22 16:23:36.390295  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.201767) brightness_val(826)
        行 45066: 04-22 16:23:36.407980  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.201327) brightness_val(824)
        行 45068: 04-22 16:23:36.423938  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.200888) brightness_val(822)
        行 45070: 04-22 16:23:36.441859  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.200449) brightness_val(820)
        行 45072: 04-22 16:23:36.457009  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.200013) brightness_val(819)
        行 45074: 04-22 16:23:36.474338  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.199578) brightness_val(817)
        行 45076: 04-22 16:23:36.490681  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.199143) brightness_val(815)
        行 45082: 04-22 16:23:36.506388  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.198710) brightness_val(813)
        行 45084: 04-22 16:23:36.523639  1042  1042 W hwcomposer: [LEDDEV]  calculateBrightness: brightness(0.198277) brightness_val(811)
```

## 扩展文档

- 自动背光流程：自动背光代码流程
- Sensor MTK数据链路：Sensor_MTK数据流框架解析
