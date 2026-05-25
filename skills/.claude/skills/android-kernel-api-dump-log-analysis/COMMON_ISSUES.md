# Kernel API Dump 常见问题对照

| 序号 | 现象 | 特征 | 根因方向 | 建议动作 |
|---|---|---|---|---|
| 1 | APMCU 读某地址 permission deny | Parser 给出 Read violation + address | master 非法访问或地址错误 | 核对调用路径与地址计算 |
| 2 | 写 violation 且 region 已分配他模块 | Write violation + region_id | 权限未覆盖合法业务写 | owner 与 MTK 对齐 MPU 策略 |
| 3 | 日志能搜到 reserved 名但无 LK | SYS_KERNEL_LOG 有区间、无申请栈 | 缺映射证据 | 补同项目 LK/UART |
| 4 | 仅有 Parser 无 owner | 无法映射模块 | 芯片内部表不外发 | 升级 MTK 并附全字段 |
| 5 | CRDISPATCH_KEY 已指 master | 关键字含模块名 | 先转该模块自检 | 自检后再决定是否提 MTK |

## 快速原则

- 结论必须能回答：**谁在访问、访问了哪、是否允许、谁该改**。
- 无 owner 闭环时不得写死“某模块根因”，只能写待验证项与补证计划。
